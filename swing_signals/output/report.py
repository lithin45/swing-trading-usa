"""Format the daily signal report (plain text / Markdown-friendly).

A glanceable ranked table of actionable longs with entry zone, ATR stop, target,
R, and suggested shares — plus the regime line and a no-trade summary so you can
see *why* nothing fired. This is decision support: you place every order manually.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from ..config_loader import Settings
    from ..market.base import MarketState
    from ..scoring.engine import EngineResult, Signal


def _fmt_money(x: float | None) -> str:
    return f"{x:.2f}" if x is not None else "—"


def _row(sig: Signal) -> str:
    zone = f"{_fmt_money(sig.entry_zone_low)}-{_fmt_money(sig.entry_zone_high)}"
    reasons = "; ".join(sig.reasons[:2])
    return (
        f"{str(sig.rank):>2} {sig.ticker:<6} {sig.conviction_score:>5.1f} "
        f"{sig.conviction_tier:<6} {zone:<17} {_fmt_money(sig.stop_price):>8} "
        f"{_fmt_money(sig.target_price):>8} {sig.reward_risk:>4} "
        f"{sig.suggested_shares:>8.3g}  {reasons}"
    )


def format_report(
    result: EngineResult,
    *,
    settings: Settings,
    today: date,
    regime: MarketState,
    macro: MarketState | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"SWING SIGNALS — {today}")
    lines.append(
        f"Equity ${settings.account.equity:,.2f} | risk/trade "
        f"{settings.account.risk_pct:.2%} (ceiling {settings.account.risk_pct_ceiling:.2%}) | "
        f"max {settings.risk.max_positions} positions, "
        f"heat cap {settings.risk.portfolio_heat_cap:.0%}"
    )
    regime_reasons = "; ".join(regime.reasons[:3])
    lines.append(
        f"Market regime: {regime.state} (score {regime.score}, size x{regime.multiplier}) "
        f"— {regime_reasons}"
    )
    if macro is not None:
        macro_reasons = "; ".join(macro.reasons[:3])
        lines.append(
            f"Macro modifier: {macro.state} (score {macro.score}, size x{macro.multiplier}) "
            f"— {macro_reasons}"
        )
    lines.append("")

    if regime.veto:
        lines.append("⛔ REGIME VETO — no new longs today. (Signals below are informational.)")
        lines.append("")

    if result.actionable:
        lines.append(f"ACTIONABLE LONGS ({len(result.actionable)}):")
        lines.append(
            f"{'#':>2} {'SYM':<6} {'CONV':>5} {'TIER':<6} {'ENTRY ZONE':<17} "
            f"{'STOP':>8} {'TARGET':>8} {'R':>4} {'SHARES':>8}  REASONS"
        )
        lines.append("-" * 100)
        for sig in result.actionable:
            lines.append(_row(sig))
            if sig.chandelier_stop is not None:
                lines.append(
                    f"     trail (Chandelier) ≈ {sig.chandelier_stop:.2f} | "
                    f"risk {sig.suggested_risk_pct:.2%} | agree {sig.agreement_score:.0%}"
                )
    else:
        lines.append("ACTIONABLE LONGS: none today.")

    lines.append("")
    if result.no_trades:
        shown = result.no_trades[:12]
        lines.append(f"NO-TRADE ({len(result.no_trades)}):")
        for sig in shown:
            flagstr = ",".join(sig.flags) if sig.flags else "—"
            lines.append(f"  {sig.ticker:<6} [{flagstr}] {sig.explanation}")
        if len(result.no_trades) > len(shown):
            lines.append(f"  …and {len(result.no_trades) - len(shown)} more")

    lines.append("")
    lines.append(
        "Decision support only — review and place any orders manually. Not financial advice."
    )
    return "\n".join(lines)
