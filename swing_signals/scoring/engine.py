"""Scoring engine (file 10): factor sub-scores -> one transparent decision.

Design pattern (file 10 §4): permission first, then strength. Hard gates
(data-integrity, liquidity, regime veto) can suppress a trade regardless of score;
the composite + agreement check decide conviction; ATR levels (file 01) and
equity sizing (file 08) produce the entry zone / stop / target / shares. Every
signal carries full per-factor attribution and a human-readable explanation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from ..factors import indicators as ind
from ..factors import register_builtins
from ..factors.base import NEUTRAL
from ..factors.registry import all_factors
from ..risk.base import position_size
from ..risk.vol_sizing import vol_scalar
from .levels import compute_levels

if TYPE_CHECKING:
    from ..context import RunContext, SymbolData
    from ..factors.base import SubScore
    from ..market.base import MarketState

_TIER_MULT = {"High": 1.0, "Medium": 0.66, "Low": 0.33, "None": 0.0}


def composite_score(
    subscores: list[SubScore], weights: dict[str, float]
) -> tuple[float, dict[str, dict[str, float]]]:
    """Weighted average of factor sub-scores, with full per-factor attribution.

    Sub-scores marked ``ok=False`` are excluded (never treated as neutral); weights
    renormalize over the factors that computed. Returns (score 0-100, attribution).
    """
    usable = [s for s in subscores if s.ok and weights.get(s.name, 0) > 0]
    wsum = sum(weights[s.name] for s in usable)
    if wsum <= 0:
        return NEUTRAL, {}
    attribution: dict[str, dict[str, float]] = {}
    score = 0.0
    for s in usable:
        w = weights[s.name] / wsum
        contribution = s.value * w
        score += contribution
        attribution[s.name] = {
            "value": round(s.value, 2),
            "weight": round(w, 4),
            "contribution": round(contribution, 2),
        }
    return score, attribution


def agreement_ratio(
    subscores: list[SubScore], weights: dict[str, float], direction: str
) -> float:
    """Weighted fraction of *firing* factors whose sign matches the direction."""
    firing = [
        s for s in subscores
        if s.ok and weights.get(s.name, 0) > 0 and abs(s.value - NEUTRAL) > 1e-9
    ]
    wsum = sum(weights[s.name] for s in firing)
    if wsum <= 0:
        return 1.0
    agree = sum(
        weights[s.name] for s in firing if (s.value > NEUTRAL) == (direction == "LONG")
    )
    return agree / wsum


@dataclass
class Signal:
    ticker: str
    signal_date: date
    direction: str  # LONG | NO-TRADE
    conviction_score: float
    conviction_tier: str
    reference_price: float | None = None
    atr: float | None = None
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None
    stop_price: float | None = None
    stop_distance_atr: float | None = None
    target_price: float | None = None
    reward_risk: float | None = None
    suggested_risk_pct: float | None = None
    suggested_shares: float | None = None
    chandelier_stop: float | None = None
    regime_state: str | None = None
    rank: int | None = None
    factor_contributions: dict = field(default_factory=dict)
    agreement_score: float | None = None
    flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    explanation: str = ""


@dataclass
class EngineResult:
    actionable: list[Signal]  # ranked LONG signals, capped to the heat/position budget
    no_trades: list[Signal]   # everything filtered out, with reasons
    regime_state: str
    regime_veto: bool


def _tier_of(score: float, cfg) -> str:
    if score >= cfg.tier_high:
        return "High"
    if score >= cfg.tier_medium:
        return "Medium"
    if score >= cfg.tier_low:
        return "Low"
    return "None"


def _liquidity_ok(sd: SymbolData, settings) -> tuple[bool, float, float]:
    assert sd.ohlcv is not None  # caller gates on data integrity before this runs
    close = sd.ohlcv["close"]
    volume = sd.ohlcv["volume"]
    price = float(close.iloc[-1])
    dollar_vol = float((close * volume).rolling(20).median().iloc[-1])
    ok = price >= settings.universe.min_price and dollar_vol >= settings.universe.min_dollar_volume
    return ok, price, dollar_vol


def generate_signals(
    data: dict[str, SymbolData],
    ctx: RunContext,
    regime: MarketState,
    macro_multiplier: float = 1.0,
) -> EngineResult:
    settings = ctx.settings
    weights = settings.active_factor_weights()
    sig_date = ctx.trading_day or date.today()

    # Instantiate the factors that are both configured (active) and registered.
    register_builtins()
    registered = all_factors()
    factors = {name: registered[name]() for name in weights if name in registered}
    missing = [name for name in weights if name not in registered]

    actionable: list[Signal] = []
    no_trades: list[Signal] = []

    for ticker, sd in data.items():
        # --- hard gate: data integrity ---
        if not sd.ok or sd.ohlcv is None:
            no_trades.append(Signal(
                ticker=ticker, signal_date=sig_date, direction="NO-TRADE",
                conviction_score=NEUTRAL, conviction_tier="None",
                flags=["DATA_INTEGRITY"], reasons=list(sd.issues),
                explanation=f"{ticker}: skipped — data issue ({'; '.join(sd.issues)})",
            ))
            continue

        # --- factors -> composite + agreement ---
        subscores = [f.compute(sd, ctx) for f in factors.values()]
        score, attribution = composite_score(subscores, weights)
        direction = "LONG"  # long-only v1
        agreement = agreement_ratio(subscores, weights, direction)
        reasons = [r for s in subscores if s.ok for r in s.reasons]
        flags = list(missing and ["FACTORS_PENDING"] or [])

        # --- hard gate: market regime (veto, or green-only-entries selectivity) ---
        green_only = settings.regime.green_only_entries and regime.state != "GREEN"
        if regime.veto or green_only:
            why = (
                f"regime {regime.state} vetoes new longs" if regime.veto
                else f"green-only entries: regime {regime.state} is not GREEN"
            )
            no_trades.append(Signal(
                ticker=ticker, signal_date=sig_date, direction="NO-TRADE",
                conviction_score=round(score, 1), conviction_tier="None",
                regime_state=regime.state, factor_contributions=attribution,
                agreement_score=round(agreement, 2), flags=flags + ["REGIME_VETO"],
                reasons=reasons,
                explanation=f"{ticker}: no-trade — {why}",
            ))
            continue

        # --- hard gate: momentum eligibility (long-only into strength) ---
        # When the momentum factor is active it must confirm a long-eligible name
        # (uptrend + positive 12-1 + near the 52-week high); an unavailable score
        # (too little history) is treated as ineligible — fail-safe toward not
        # trading. Disabled momentum => no gate (backward compatible).
        mom_ss = next((s for s in subscores if s.name == "momentum"), None)
        if mom_ss is not None:
            eligible = mom_ss.ok and bool(mom_ss.raw.get("eligible", False))
            if not eligible:
                why = (
                    mom_ss.reasons[-1]
                    if (mom_ss.ok and mom_ss.reasons)
                    else "momentum unconfirmed"
                )
                no_trades.append(Signal(
                    ticker=ticker, signal_date=sig_date, direction="NO-TRADE",
                    conviction_score=round(score, 1), conviction_tier="None",
                    regime_state=regime.state, factor_contributions=attribution,
                    agreement_score=round(agreement, 2),
                    flags=flags + ["MOMENTUM_INELIGIBLE"], reasons=reasons,
                    explanation=f"{ticker}: no-trade — {why}",
                ))
                continue

        # --- hard gate: liquidity ---
        liq_ok, price, dollar_vol = _liquidity_ok(sd, settings)
        if not liq_ok:
            no_trades.append(Signal(
                ticker=ticker, signal_date=sig_date, direction="NO-TRADE",
                conviction_score=round(score, 1), conviction_tier="None",
                regime_state=regime.state, factor_contributions=attribution,
                flags=flags + ["LIQUIDITY_FAIL"], reasons=reasons,
                explanation=(f"{ticker}: no-trade — illiquid (price ${price:.2f}, "
                             f"$vol ${dollar_vol/1e6:.1f}M)"),
            ))
            continue

        # --- hard gate: extension (don't chase) — veto entries too many ATRs above
        # the 20-EMA. Momentum ranking concentrates in the MOST extended names; the
        # most extended are also the most mean-reversion-prone right after entry.
        max_ext = settings.scoring.max_extension_atr
        if max_ext > 0:
            ind_row = sd.indicators or {}
            ema20 = (
                float(ind_row["ema20"]) if "ema20" in ind_row
                else float(ind.ema(sd.ohlcv["close"], 20).iloc[-1])
            )
            atr_ext = (
                float(ind_row["atr14"]) if "atr14" in ind_row
                else float(ind.atr(
                    sd.ohlcv["high"], sd.ohlcv["low"], sd.ohlcv["close"],
                    settings.risk.atr_period,
                ).iloc[-1])
            )
            if atr_ext > 0 and (price - ema20) / atr_ext > max_ext:
                no_trades.append(Signal(
                    ticker=ticker, signal_date=sig_date, direction="NO-TRADE",
                    conviction_score=round(score, 1), conviction_tier="None",
                    regime_state=regime.state, factor_contributions=attribution,
                    agreement_score=round(agreement, 2),
                    flags=flags + ["EXTENSION"], reasons=reasons,
                    explanation=(f"{ticker}: no-trade — extended "
                                 f"{(price - ema20) / atr_ext:.1f} ATR above EMA20 "
                                 f"(cap {max_ext:.1f})"),
                ))
                continue

        tier = _tier_of(score, settings.scoring)

        # --- soft gates: conviction + agreement thresholds ---
        reject = None
        if score < settings.scoring.composite_min:
            reject = (
                f"below conviction threshold "
                f"({score:.0f} < {settings.scoring.composite_min:.0f})"
            )
        elif agreement < settings.scoring.agreement_min:
            flags.append("LOW_AGREEMENT")
            reject = (
                f"low factor agreement "
                f"({agreement:.0%} < {settings.scoring.agreement_min:.0%})"
            )
        if reject:
            no_trades.append(Signal(
                ticker=ticker, signal_date=sig_date, direction="NO-TRADE",
                conviction_score=round(score, 1), conviction_tier=tier,
                regime_state=regime.state, factor_contributions=attribution,
                agreement_score=round(agreement, 2), flags=flags, reasons=reasons,
                explanation=f"{ticker}: no-trade — {reject}",
            ))
            continue

        # --- levels (ATR) + sizing (equity, conviction- and regime-scaled) ---
        atr14 = float(
            ind.atr(
                sd.ohlcv["high"], sd.ohlcv["low"], sd.ohlcv["close"],
                settings.risk.atr_period,
            ).iloc[-1]
        )
        levels = compute_levels(
            ref_price=price, atr=atr14,
            high=sd.ohlcv["high"], low=sd.ohlcv["low"], close=sd.ohlcv["close"],
            stop_atr_mult=settings.risk.atr_stop_multiple, rr_target=settings.risk.rr_target,
            chandelier_lookback=settings.risk.chandelier_lookback,
            chandelier_mult=settings.risk.chandelier_multiple,
        )
        # Volatility-scaled sizing: shrink size for high-ATR names / high-vol markets.
        # Flows everywhere via conviction_mult -> effective risk %, so it sizes down
        # the engine's shares, the backtest, and the live order (which sizes off
        # suggested_risk_pct) alike. Only ever reduces size (caps at 1.0).
        vscalar = 1.0
        if settings.sizing.vol_scaling_enabled:
            vscalar = vol_scalar(
                atr_pct=(atr14 / price * 100.0) if price > 0 else None,
                vol_target_atr_pct=settings.sizing.vol_target_atr_pct,
                market_vol_score=regime.raw.get("vol_pillar"),
                scalar_min=settings.sizing.vol_scalar_min,
                scalar_max=settings.sizing.vol_scalar_max,
            )
        conviction_mult = _TIER_MULT[tier] * regime.multiplier * macro_multiplier * vscalar
        size = position_size(
            equity=settings.account.equity, entry=levels.entry, stop=levels.stop,
            risk_pct=settings.account.risk_pct, risk_pct_ceiling=settings.account.risk_pct_ceiling,
            fractional=settings.account.fractional_shares, conviction_mult=conviction_mult,
            max_notional_pct=settings.risk.max_position_notional_pct,
        )
        if size.shares <= 0:
            no_trades.append(Signal(
                ticker=ticker, signal_date=sig_date, direction="NO-TRADE",
                conviction_score=round(score, 1), conviction_tier=tier,
                regime_state=regime.state, factor_contributions=attribution,
                flags=flags + ["SIZE_ZERO"], reasons=reasons + size.reasons,
                explanation=f"{ticker}: no-trade — sizes to 0 shares ({'; '.join(size.reasons)})",
            ))
            continue

        explanation = (
            f"LONG {ticker} | conviction {score:.0f} ({tier}) | regime {regime.state} | "
            f"agree {agreement:.0%} | entry {levels.entry_zone_low}-{levels.entry_zone_high} "
            f"stop {levels.stop} ({levels.stop_distance_atr}xATR) target {levels.target} "
            f"RR {levels.reward_risk} | ~{size.shares:.3g} sh @ {size.risk_pct:.2%} risk"
        )
        actionable.append(Signal(
            ticker=ticker, signal_date=sig_date, direction="LONG",
            conviction_score=round(score, 1), conviction_tier=tier,
            reference_price=round(price, 4), atr=round(atr14, 4),
            entry_zone_low=levels.entry_zone_low, entry_zone_high=levels.entry_zone_high,
            stop_price=levels.stop, stop_distance_atr=levels.stop_distance_atr,
            target_price=levels.target, reward_risk=levels.reward_risk,
            suggested_risk_pct=round(size.risk_pct, 4), suggested_shares=round(size.shares, 4),
            chandelier_stop=levels.chandelier_stop, regime_state=regime.state,
            factor_contributions=attribution, agreement_score=round(agreement, 2),
            flags=flags, reasons=reasons, explanation=explanation,
        ))

    # --- rank LONGs and cap to the position / portfolio-heat budget ---
    actionable.sort(key=lambda s: s.conviction_score, reverse=True)
    selected: list[Signal] = []
    heat = 0.0
    heat_cap = settings.risk.portfolio_heat_cap
    sector_counts: dict[str, int] = {}
    max_per_sector = settings.risk.max_per_sector
    for sig in actionable:
        if len(selected) >= settings.risk.max_positions:
            sig.flags.append("CAPPED_MAX_POSITIONS")
            no_trades.append(sig_to_no_trade(sig, "max positions reached"))
            continue
        if heat + (sig.suggested_risk_pct or 0) > heat_cap + 1e-9:
            sig.flags.append("CAPPED_HEAT")
            no_trades.append(sig_to_no_trade(sig, "portfolio heat cap reached"))
            continue
        # Correlation cap: limit concurrent names sharing a sector/theme so a basket
        # of, say, semis counts as one crowded bet (sector populated by the caller;
        # None => uncapped, e.g. in the backtest).
        sd_sec = data[sig.ticker].sector if sig.ticker in data else None
        if sd_sec and sector_counts.get(sd_sec, 0) >= max_per_sector:
            sig.flags.append("CAPPED_SECTOR")
            no_trades.append(sig_to_no_trade(sig, f"max per sector reached ({sd_sec})"))
            continue
        heat += sig.suggested_risk_pct or 0
        if sd_sec:
            sector_counts[sd_sec] = sector_counts.get(sd_sec, 0) + 1
        sig.rank = len(selected) + 1
        selected.append(sig)

    return EngineResult(
        actionable=selected, no_trades=no_trades,
        regime_state=regime.state, regime_veto=regime.veto,
    )


def sig_to_no_trade(sig: Signal, why: str) -> Signal:
    sig.direction = "NO-TRADE"
    sig.explanation = f"{sig.ticker}: deferred — {why} (would-be conviction {sig.conviction_score})"
    return sig
