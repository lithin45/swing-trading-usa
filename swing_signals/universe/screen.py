"""Two-stage universe funnel — wide scan, narrow candidate set (research files 09/12).

1. Assemble the universe: S&P 500 ∪ thematic ∪ news-discovered, deduped.
2. Liquidity pre-filter + momentum eligibility (cheap, NO LLM): drop illiquid names
   and anything not in a confirmed uptrend near its highs.
3. Score the survivors on a cheap momentum+technical blend; take the top N.
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

from ..factors.f01_technical import TechnicalFactor
from ..factors.f08_momentum import MomentumFactor
from ..scoring.engine import _liquidity_ok
from .membership import sp500
from .thematic import thematic_symbols

if TYPE_CHECKING:
    from datetime import date

    from ..config_loader import Secrets, Settings
    from ..data.loader import DataLoader

log = logging.getLogger("swing_signals.universe")


def assemble_universe(extra: list[str] | None = None) -> list[str]:
    """S&P 500 ∪ thematic ∪ ``extra`` (news-discovered), deduped and sorted."""
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
    universe = assemble_universe(discovered)
    log.info("universe screen: scanning %d symbols (no LLM)", len(universe))

    # Cheap OHLCV-only load (news=False) — never fires hundreds of news-API calls.
    data = loader.load_watchlist(universe, asof, offline=offline, news=False)
    mom, tech = MomentumFactor(), TechnicalFactor()
    ctx = RunContext(
        settings=settings, secrets=secrets, trading_day=asof, equity=settings.account.equity
    )

    scored: list[tuple[str, float]] = []
    for sym, sd in data.items():
        if not sd.ok or sd.ohlcv is None:
            continue
        liq_ok, _price, _dvol = _liquidity_ok(sd, settings)
        if not liq_ok:
            continue
        ms = mom.compute(sd, ctx)  # momentum/technical ignore ctx, but pass it for type-safety
        if not ms.ok or not ms.raw.get("eligible"):
            continue  # long-only into strength
        ts = tech.compute(sd, ctx)
        pre = 0.6 * ms.value + 0.4 * (ts.value if ts.ok else 50.0)
        scored.append((sym, pre))

    scored.sort(key=lambda x: x[1], reverse=True)
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
    if not offline:
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
