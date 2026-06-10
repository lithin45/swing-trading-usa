"""DataLoader — the orchestration the rest of the app talks to.

Builds the price-provider chain from config, layers the Parquet cache in front,
and assembles per-symbol data + market context. Resilience is the point:
cache-first → providers in order → stale-cache last resort, and the per-symbol
quality gate marks (never crashes on) bad/stale data so the engine can skip it.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from ..config_loader import Secrets, Settings
from ..context import MarketContext, SymbolData
from .alpaca_provider import AlpacaProvider
from .cache import OHLCVCache
from .fred_provider import FredProvider
from .market import build_market_context
from .quality import check_ohlcv_quality
from .retry import PermanentDataError
from .stooq_provider import StooqProvider
from .yfinance_provider import YfinanceProvider

log = logging.getLogger("swing_signals.data")


class DataLoader:
    def __init__(self, settings: Settings, secrets: Secrets) -> None:
        self.settings = settings
        self.secrets = secrets
        self.cache = OHLCVCache(settings.data.cache_dir)
        self.providers = self._build_price_providers()
        self.fred = FredProvider(_reveal(secrets.fred_api_key))
        self.news_providers = self._build_news_providers()

    # -- construction -------------------------------------------------------
    def _build_price_providers(self) -> list:
        providers: list = []
        for name in self.settings.data.provider_order:
            if name == "alpaca":
                ap = AlpacaProvider(
                    api_key=_reveal(self.secrets.alpaca_api_key),
                    secret_key=_reveal(self.secrets.alpaca_secret_key),
                )
                if ap.available:
                    providers.append(ap)
                else:
                    log.info("alpaca provider disabled (no SWING_ALPACA_API_KEY/SECRET_KEY)")
            elif name == "yfinance":
                providers.append(YfinanceProvider())
            elif name == "stooq":
                sp = StooqProvider(api_key=_reveal(self.secrets.stooq_api_key))
                if sp.available:
                    providers.append(sp)
                else:
                    log.info("stooq fallback disabled (no SWING_STOOQ_API_KEY)")
            else:
                log.warning("unknown price provider %r in provider_order; skipping", name)
        if not providers:
            raise ValueError("no usable price providers configured (check provider_order/keys)")
        return providers

    def _build_news_providers(self) -> list:
        """News hydration is opt-in: only when news_sentiment is active AND a key is present."""
        fc = self.settings.factors.get("news_sentiment")
        if not (fc and fc.enabled and fc.weight > 0):
            return []
        from ..news.aggregate import build_providers

        providers = build_providers(self.secrets)
        if providers:
            log.info("news hydration enabled: %s", [p.name for p in providers])
        return providers

    def _min_rows(self) -> int:
        # Enough history for the longest moving average we use (e.g. 200-DMA) + buffer.
        return max(self.settings.regime.spy_ma_days, 200) + 5

    # -- OHLCV with cache + fallback ---------------------------------------
    def get_ohlcv(
        self, symbol: str, start: str, end: str, *, asof: date | None = None, offline: bool = False
    ) -> pd.DataFrame:
        # 1) fresh cache short-circuits the network (idempotent re-runs).
        if asof is not None:
            fresh = self.cache.fresh_for(symbol, asof, self.settings.data.max_staleness_days)
            if fresh is not None:
                return fresh

        # 2) offline mode: cache only.
        if offline:
            cached = self.cache.get(symbol)
            if cached is not None:
                return cached
            raise PermanentDataError(f"offline: no cached data for {symbol}")

        # 3) try providers in order; cache each success.
        errors: list[str] = []
        for provider in self.providers:
            try:
                df = provider.get_ohlcv(symbol, start, end)
                self.cache.put(symbol, df)
                return df
            except Exception as exc:  # noqa: BLE001 - try the next provider
                errors.append(f"{provider.name}: {exc}")
                log.warning("provider %s failed for %s: %s", provider.name, symbol, exc)

        # 4) last resort: stale cache beats no data (the quality gate will flag it).
        cached = self.cache.get(symbol)
        if cached is not None:
            log.warning("using stale cache for %s after all providers failed", symbol)
            return cached
        raise PermanentDataError(f"all providers failed for {symbol}: {errors}")

    # -- public API ---------------------------------------------------------
    def load_symbol(
        self, symbol: str, asof: date, *, offline: bool = False, news: bool = True
    ) -> SymbolData:
        """Never raises — failures are recorded on SymbolData.issues (fail-loud).

        ``news=False`` loads OHLCV only — used by the universe screener's cheap scan
        over hundreds of names, so it never fires hundreds of news-API calls (news is
        hydrated only for the final candidate set).
        """
        start = (asof - timedelta(days=self.settings.data.lookback_days)).isoformat()
        end = (asof + timedelta(days=1)).isoformat()
        sd = SymbolData(symbol=symbol)
        try:
            sd.ohlcv = self.get_ohlcv(symbol, start, end, asof=asof, offline=offline)
        except Exception as exc:  # noqa: BLE001
            sd.issues.append(f"{symbol}: fetch failed ({exc})")
            return sd
        sd.issues.extend(
            check_ohlcv_quality(
                sd.ohlcv,
                symbol=symbol,
                asof=asof,
                min_rows=self._min_rows(),
                max_staleness_days=self.settings.data.max_staleness_days,
            )
        )
        # Opt-in news hydration (live only). Non-essential: a failure must never
        # fail the symbol's data gate — leave news=None and let the factor degrade.
        if news and self.news_providers and sd.ok and not offline:
            try:
                from ..news.aggregate import fetch_news

                items = fetch_news(symbol, asof, providers=self.news_providers)
                sd.news = [it.as_dict() for it in items]
            except Exception as exc:  # noqa: BLE001 - news is best-effort
                log.warning("news fetch failed for %s (continuing): %s", symbol, exc)
        return sd

    def load_watchlist(
        self, symbols: list[str], asof: date, *, offline: bool = False, news: bool = True
    ) -> dict[str, SymbolData]:
        """Load every symbol, concurrently when the universe is large.

        ``load_symbol`` is I/O-bound (network/cache) and per-symbol independent (each
        touches its own Parquet file), so a thread pool gives a near-linear speedup
        that makes an S&P-500-sized universe fetchable in a daily job. Falls back to
        a serial pass for tiny universes / ``max_workers == 1``. Results are returned
        in the original symbol order regardless of completion order.
        """
        workers = min(self.settings.data.max_workers, max(1, len(symbols)))
        if workers <= 1 or len(symbols) <= 1:
            return {sym: self.load_symbol(sym, asof, offline=offline, news=news) for sym in symbols}

        from concurrent.futures import ThreadPoolExecutor

        out: dict[str, SymbolData] = {sym: SymbolData(symbol=sym) for sym in symbols}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(self.load_symbol, sym, asof, offline=offline, news=news): sym
                for sym in symbols
            }
            for fut, sym in futures.items():
                try:
                    out[sym] = fut.result()
                except Exception as exc:  # noqa: BLE001 - load_symbol shouldn't raise; be safe
                    out[sym].issues.append(f"{sym}: load failed ({exc})")
        return out

    def load_market_context(self, asof: date, *, offline: bool = False) -> MarketContext:
        def _ohlcv(sym: str, start: str, end: str) -> pd.DataFrame:
            return self.get_ohlcv(sym, start, end, asof=asof, offline=offline)

        return build_market_context(
            get_ohlcv=_ohlcv,
            fred=self.fred,
            index_symbols=self.settings.data.index_symbols,
            fred_series=self.settings.data.fred_series,
            lookback_days=self.settings.data.lookback_days,
            asof=asof,
        )


def _reveal(secret) -> str | None:
    return secret.get_secret_value() if secret is not None else None
