"""Two-stage universe funnel — wide scan, narrow candidate set (research files 09/12).

1. Assemble the universe: point-in-time S&P 500 (``universe.sp500_only``, the
   validated default), optionally ∪ thematic ∪ news-discovered for exploration.
2. Liquidity pre-filter + momentum eligibility + extension veto (cheap, NO LLM):
   drop illiquid names, anything not in a confirmed uptrend near its highs, and
   anything the engine's don't-chase gate would veto anyway.
3. Rank the survivors by the ENGINE'S OWN composite over the OHLCV-computable
   factors; take the top N. (Until 2026-06-12 this used an ad-hoc 0.6/0.4
   momentum/technical blend, which ordered the top-N differently than the engine
   orders signals — a name the engine ranked top-8 could miss the candidate list
   entirely, a live-vs-validated decision flip the backtest never sees.)
4. Merge news-surfaced movers that also cleared eligibility (a fresh catalyst may not
   yet rank top-N on its own).
5. Return the bounded candidate set the full pipeline then scores — only these reach
   the costly Claude news factor, which is what keeps cost at ~cents/day.

``resolve_universe`` is the entry point ``main.run`` calls; it falls back to the
static watchlist on any error so the daily job can never be broken by the screener.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..factors import indicators as ind
from ..factors.f01_technical import TechnicalFactor
from ..factors.f08_momentum import MomentumFactor
from ..factors.f09_setup import SetupFactor
from ..scoring.engine import _liquidity_ok, composite_score
from .membership import sp500
from .thematic import thematic_symbols

if TYPE_CHECKING:
    from datetime import date

    from ..config_loader import Secrets, Settings
    from ..data.loader import DataLoader

log = logging.getLogger("swing_signals.universe")


def assemble_universe(
    extra: list[str] | None = None, *, sp500_only: bool = False
) -> list[str]:
    """S&P 500 ∪ thematic ∪ ``extra`` (news-discovered), deduped and sorted.

    ``sp500_only`` drops the thematic and discovered names: every validated holdout
    traded point-in-time S&P 500 members only, and budget slots spent on names the
    validation never saw make the paper record unattributable to the tested strategy.
    """
    if sp500_only:
        return sorted(set(sp500()))
    syms = set(sp500()) | set(thematic_symbols()) | {s.upper() for s in (extra or [])}
    return sorted(syms)


def screen(
    settings: Settings,
    secrets: Secrets,
    *,
    asof: date,
    loader: DataLoader | None = None,
    offline: bool = False,
    discovered: list[str] | None = None,
) -> list[str]:
    """Run the cheap scan over the whole universe; return the top candidate symbols."""
    from ..context import RunContext
    from ..data.loader import DataLoader

    loader = loader if loader is not None else DataLoader(settings, secrets)
    sp500_only = settings.universe.sp500_only
    universe = assemble_universe(discovered, sp500_only=sp500_only)
    if sp500_only and (discovered or thematic_symbols()):
        log.info(
            "universe screen: restricted to S&P 500 members (the validated universe) — "
            "thematic/news-discovered names excluded (universe.sp500_only)"
        )
    log.info("universe screen: scanning %d symbols (no LLM)", len(universe))

    # Cheap OHLCV-only load (news=False) — never fires hundreds of news-API calls.
    data = loader.load_watchlist(universe, asof, offline=offline, news=False)
    mom, tech, setup = MomentumFactor(), TechnicalFactor(), SetupFactor()
    weights = settings.active_factor_weights()
    max_ext = settings.scoring.max_extension_atr
    ctx = RunContext(
        settings=settings, secrets=secrets, trading_day=asof, equity=settings.account.equity
    )

    scored: list[tuple[str, float]] = []
    for sym, sd in data.items():
        if not sd.ok or sd.ohlcv is None:
            continue
        liq_ok, price, _dvol = _liquidity_ok(sd, settings)
        if not liq_ok:
            continue
        ms = mom.compute(sd, ctx)  # factors ignore ctx here, but pass it for type-safety
        if not ms.ok or not ms.raw.get("eligible"):
            continue  # long-only into strength
        # Mirror the engine's don't-chase veto: an extended name is a guaranteed
        # engine rejection, so it must not burn a top_n_scan slot that could have
        # carried a tradable candidate (the backtest scores ALL members, so a slot
        # burned here is a live-only decision change).
        if max_ext > 0:
            ema20 = float(ind.ema(sd.ohlcv["close"], 20).iloc[-1])
            atr_ext = float(
                ind.atr(
                    sd.ohlcv["high"], sd.ohlcv["low"], sd.ohlcv["close"],
                    settings.risk.atr_period,
                ).iloc[-1]
            )
            if atr_ext > 0 and (price - ema20) / atr_ext > max_ext:
                continue
        # Rank by the engine's own composite over the OHLCV-computable factors —
        # with news at weight 0 this IS the engine's ranking key, so the top-N cut
        # and the engine's signal ranking can never disagree about ordering.
        subs = [ms, tech.compute(sd, ctx), setup.compute(sd, ctx)]
        pre, _ = composite_score(subs, weights)
        scored.append((sym, pre))

    # Alphabetical tie-break, matching the engine's ranking exactly.
    scored.sort(key=lambda x: (-x[1], x[0]))
    eligible = {s for s, _ in scored}
    top = [s for s, _ in scored[: settings.universe.top_n_scan]]

    # Merge news-discovered movers that also cleared eligibility (dedupe, keep order).
    disc = [s for s in (discovered or []) if s in eligible and s not in top]
    candidates = list(dict.fromkeys(top + disc))[: settings.universe.max_llm_candidates]
    log.info(
        "universe screen: %d eligible -> %d candidates (%d news-surfaced)",
        len(eligible), len(candidates), len(disc),
    )
    return candidates


def resolve_universe(
    settings: Settings,
    secrets: Secrets,
    loader: DataLoader,
    asof: date,
    *,
    offline: bool = False,
) -> list[str]:
    """The watchlist for today: static list, or the screened candidates (with fallback)."""
    if settings.watchlist.source != "universe_screen":
        return settings.watchlist.symbols

    discovered: list[str] = []
    if not offline and not settings.universe.sp500_only:
        try:
            from ..news.discovery import discover_movers

            discovered = discover_movers(settings, secrets)
        except Exception as exc:  # noqa: BLE001 - discovery is best-effort
            log.warning("news discovery failed (continuing without): %s", exc)

    try:
        picked = screen(
            settings, secrets, asof=asof, loader=loader, offline=offline, discovered=discovered
        )
    except Exception as exc:  # noqa: BLE001 - the screen must never break the daily job
        log.warning("universe screen failed (%s) — falling back to static watchlist", exc)
        return settings.watchlist.symbols

    if not picked:
        log.info("universe screen returned no candidates — using static watchlist")
        return settings.watchlist.symbols
    return picked
