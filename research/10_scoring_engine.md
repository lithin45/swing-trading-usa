# File 10 — Combining Factor Sub-Scores into a Single Swing-Trade Decision

*Standalone reference for a solo retail trader. Signal-only system (manual order placement), US individual equities, holding horizon of a few days to ~1 month, percentage-based account-risk rules, small account scaling up. References files 01–09 by number. Where the contents of those files are assumed rather than known, this is flagged explicitly.*

---

## TL;DR

- **Build a transparency-first engine: hard rule-based gates (regime + risk) wrapped around an equal-weighted composite score.** Treat machine learning as an *optional later layer*, never the core — a solo retail trader lacks the independent data and the interpretability needed to run a black box safely.
- **Derive entry zone, stop, and target from the adaptive ATR logic in file 01 (ATR-multiple / Chandelier-style), not fixed percentages**, and scale position size by a conviction tier *within* the per-trade risk caps of file 08 (1% rule as the default; optional fractional Kelly capped at the file 08 limit).
- **Defeat overfitting, not weak models:** default to equal weights, shrink any deviation, use purged/embargoed walk-forward validation, hold factors to a high evidence bar (López de Prado; Harvey-Liu-Zhu t > 3.0), and add an explicit confluence/agreement check so conflicting factors trigger reduced-conviction or no-trade.

---

## Key Findings

1. **Equal weighting is the right default, and it is empirically defensible.** DeMiguel, Garlappi & Uppal (2009, *Review of Financial Studies* 22(5):1915–1953) evaluated 14 optimized allocation models across seven empirical datasets and concluded, verbatim: *"none is consistently better than the 1/N rule in terms of Sharpe ratio, certainty-equivalent return, or turnover... the gain from optimal diversification is more than offset by estimation error."* The same estimation-error logic applies to factor weights.

2. **Interpretability is a design requirement, not a luxury.** Rudin (2019) argues practitioners should "stop explaining black box machine learning models for high stakes decisions and use interpretable models instead," because post-hoc explanations of black boxes can be misleading. A weighted composite with full per-factor attribution is inherently faithful to what the model computes.

3. **ML can add value but needs scale you don't have.** Gu, Kelly & Xiu (2020, *RFS* 33(5):2223–2273) found tree ensembles and neural nets best-performing for cross-sectional return prediction — verbatim: *"We identify the best-performing methods (trees and neural networks) and trace their predictive gains to allowing nonlinear predictor interactions missed by other methods."* But that study spanned **~30,000 US stocks over 60 years (1957–2016) with 94 firm characteristics, 8 macro series, and 74 industry dummies (over 900 signals)** — breadth a retail trader cannot replicate.

4. **Overfitting is the dominant risk.** López de Prado shows walk-forward backtests are "easy to overfit because only 1 history is tested," and Harvey, Liu & Zhu (2016, *RFS* 29(1):5–68), surveying ≥316 published factors, conclude that *"a newly discovered factor needs to clear a much higher hurdle, with a t-ratio greater than 3.0... most claimed research findings in financial economics are likely false."*

5. **ATR-based adaptive stops/targets are the established, volatility-aware standard** (Wilder 1978; Le Beau's Chandelier Exit), and conviction-scaled sizing is mathematically consistent with the Kelly criterion — but only at a **fraction** of full Kelly.

---

## Details

### 1. Overview

This file specifies how to fuse the 8–15 normalized factor sub-scores produced by your earlier research files into one actionable swing-trade signal per stock: a **conviction score**, an **entry zone**, a **stop**, and an **exit/target**, plus a transparent record of *why* the signal fired.

**Architecture:** a **rule-based hard-gate layer** (regime + risk vetoes) wrapped around a **weighted-average composite score that starts at equal weights**. ML (logistic regression, random forests, gradient-boosted trees) is an **optional later layer**, not the core engine. Stops and targets come from **file 01's ATR-based adaptive logic**, never fixed percentages. Position size scales by conviction *within* the limits of file 08.

**Assumed contents of files 01–09** (correct as needed):
- **01 — Adaptive ATR exit/target logic.** ATR-multiple stops and targets, likely Chandelier-style trailing exits. *Treated as the single source of truth for stop/target math.*
- **02–06 — Individual factor families.** Assumed to include momentum/trend, mean-reversion, value/quality fundamentals, volume/liquidity, and sentiment/alt-data, each emitting a normalized sub-score. *(Exact split assumed.)*
- **07 — Market-regime gate.** Assumed to classify the broad market (e.g., SPY vs 200-day MA, breadth, VIX/volatility regime) into trade/no-trade states. Used here as a **hard gate**.
- **08 — Risk rules.** Assumed to define per-trade risk (e.g., 1% of equity), max concurrent positions, max sector/portfolio heat, and drawdown circuit-breakers. Used here as a **hard gate** and the position-sizing backbone.
- **09 — Assumed data-sourcing/universe-construction file** (data feeds, liquidity filters, survivorship handling). *(Content assumed.)*

The guiding principle is **López de Prado's warning**: with one short history and many tunable knobs, the dominant risk is not a weak model but an *overfit* one. Simplicity is a feature.

### 2. Combination approaches (with recommendation)

There are three broad ways to turn many sub-scores into one decision.

**(A) Rule-based gates (Boolean logic).** Hard conditions that must be true to trade ("regime is risk-on AND price > 200-day MA AND liquidity passes"). Transparent, robust, no fitting. Weakness: binary, discards magnitude information, and combinatorially explosive if overused.

**(B) Weighted scoring (linear composite).** Normalize each factor (z-score or percentile), multiply by a weight, sum to a composite. The standard multi-factor approach used by index providers. Transparent, fully decomposable, degrades gracefully. Weakness: linear/compensatory — a great score on one factor can mask a terrible score on another, so it needs gates and conflict checks layered on top.

**(C) ML / ensemble (logistic regression, random forests, gradient-boosted trees).** Learn the mapping from sub-scores to forward returns; can capture nonlinearities and interactions. Powerful at scale (Gu-Kelly-Xiu above) but data-hungry.

**Recommendation: (A) + (B) as the core, (C) optional and later.** Combine a rule-based gate layer with an equal-weighted composite — the transparency-first design, supported by DeMiguel et al. (equal weight is hard to beat out-of-sample) and Rudin (use inherently interpretable models for high-stakes decisions).

**If you add ML later:**
- Prefer **L1/L2-regularized logistic regression** first (interpretable coefficients, single decision boundary), then tree ensembles.
- **Random forests** are more robust to noise and overfit less readily; **gradient-boosted trees** can be more accurate but are more sensitive to overfitting on noisy data and harder to tune.
- Risks with limited retail data are severe: non-stationarity, tiny independent samples, and the multiple-testing "factor zoo." Treat any ML output as *one more factor feeding the transparent composite*, never the final arbiter.

### 3. Weighting scheme

**Start at equal weights; shrink any deviation hard.**

1. **Default = equal weight** across families first, then equal within each family — this stops a family with five correlated momentum variants from dominating.
2. **If you deviate, use 2–3 discrete conviction buckets** (e.g., 1.0 / 0.5) grounded in economic priors and out-of-sample evidence — not a continuous optimizer that fits noise.
3. **Shrinkage toward equal weights** (Ledoit-Wolf logic): `w_final = λ·w_equal + (1−λ)·w_estimated`, with λ large (0.5–0.8). Extreme estimated weights are mostly estimation error; pulling them toward equal weight improves out-of-sample stability.
4. **IC weighting (Grinold's Fundamental Law, IR ≈ IC·√Breadth) — use cautiously.** Retail IC estimates are noisy; if used, cap the influence and re-estimate rarely (annually).

**Avoiding overfitting with limited data:**
- **In-sample optimization is the enemy.** Bailey, Borwein, López de Prado & Zhu show selecting the best backtest among many is a multiple-testing problem producing "statistical mirages." More combinations tried = more certain overfit.
- **Walk-forward is mandatory but insufficient.** López de Prado proposes **Combinatorial Purged Cross-Validation** with **purging** (drop training rows whose labels overlap the test window) and **embargoing** (a gap after each test set) to stop leakage in time-series data.
- **Standard k-fold CV is dangerous in finance** because of temporal dependence and non-stationarity.
- **Raise the significance hurdle to t > 3.0** (Harvey, Liu & Zhu 2016).
- **Bias-variance:** complex models fit noise; in noisy markets irreducible error dominates, so the simpler model usually generalizes better. Use L1/L2 regularization to trade a little bias for much less variance.
- **Rule of thumb:** few parameters, round/standard values, and complexity must earn its keep on purged out-of-sample data.

### 4. Hard gates / overrides

A **hard gate** is a Boolean veto: fail it and the signal is suppressed **regardless of composite score**. A **soft adjustment** scales score or size but doesn't veto. Use hard gates for categorical, catastrophic-if-wrong conditions; soft adjustments for matters of degree.

**Design pattern — permission first, then strength:** regime gate → risk gate → direction → composite score → conflict check → sizing. As practitioners put it, conditions like regime and volatility "define permission, not entries… used only after the regime and direction are approved."

**Hard gates (vetoes):**
1. **Regime gate (file 07).** Risk-off (e.g., SPY below 200-day MA, or file 07's bearish/chaotic state) → suppress new long swing signals. The filter "keeps your strategy running only when the market is trending calmly and pauses it during chaotic or bearish phases."
2. **Risk gate (file 08).** Veto if per-trade risk exceeds cap, max concurrent positions reached, sector/portfolio heat exceeded, or a drawdown circuit-breaker is tripped.
3. **Liquidity/tradeability gate (file 09 assumed):** minimum price, dollar volume, spread.
4. **Data-integrity gate:** stale/missing required inputs → no signal.

**Soft adjustments:** volatility *level* scales size; earnings proximity reduces conviction (or hard-gates, your choice); minor factor disagreement reduces conviction.

**Why gates beat folding everything into the score:** a high composite must never "buy its way past" a bear regime or a blown risk limit. Gating preserves that guarantee; a purely additive score does not.

### 5. Final output spec (exact fields per signal)

| Field | Definition |
|---|---|
| `ticker` | Symbol |
| `timestamp` | Signal generation time / bar date |
| `direction` | LONG / SHORT / NO-TRADE |
| `conviction_score` | Composite, 0–100 (or normalized z), after gates |
| `conviction_tier` | None / Low / Medium / High |
| `reference_price` | Anchor (prior close or signal-bar close) |
| `atr` | Current ATR(14), absolute (file 01) |
| `entry_zone_low` / `entry_zone_high` | ATR-band entry zone |
| `stop_price` | ATR-based stop (file 01) |
| `stop_distance_atr` | Stop distance in ATR multiples |
| `target_price` | ATR / R-multiple target (file 01) |
| `reward_risk` | (target − entry) / (entry − stop) |
| `suggested_risk_pct` | Per-trade risk %, conviction-scaled within file 08 caps |
| `suggested_shares` | (equity × risk_pct) / (entry − stop), floored |
| `regime_state` | Pass/fail + value (file 07) |
| `risk_gate_state` | Pass/fail + binding constraint (file 08) |
| `factor_contributions` | Per-factor: raw score, weight, weighted contribution |
| `agreement_score` | Fraction of factors agreeing with direction / dispersion |
| `flags` | LOW_AGREEMENT, NEAR_EARNINGS, WIDE_STOP, etc. |
| `explanation` | Human-readable: top 3 factors, gates passed, why this tier |

**Entry zone, stop, target (ATR-based, file 01):**
- **Reference price:** prior close or signal-bar close.
- **Entry zone (a band, not a point):**
  - *Pullback (trend continuation):* zone around an MA / Keltner mid-line — e.g., `[EMA20 − 0.5·ATR, EMA20]`. Keltner channels (EMA ± multiple·ATR) are the canonical ATR-band tool; the middle EMA acts as a decision line where pullbacks find support.
  - *Breakout:* zone just above the level — e.g., `[breakout_level, breakout_level + 0.5·ATR]`, with a no-chase rule beyond the top of the zone.
- **Stop (adaptive, file 01):** a volatility stop at an ATR multiple. Wilder introduced ATR in *New Concepts in Technical Trading Systems* (1978); common practice is **1.5×–3× ATR** below entry for longs. The **Chandelier Exit** (Le Beau): `Highest High(22) − 3×ATR(22)` — a trailing stop "hanging" from the recent high. **Defer to file 01 for the exact multiple/lookback.**
- **Target/exit (adaptive, file 01):** a fixed R-multiple of the volatility-based stop distance (e.g., 2× the stop distance for 2:1), or an ATR projection (e.g., 4×ATR), or a multi-tier scale-out (partial at 2×ATR, trail the rest via Chandelier). Swing systems commonly target reward:risk in the 1:2–1:3 range; calibrate to your win rate.

**Conviction → position size (coordinated with file 08):**
1. **Simple (recommended start):** map tiers to a fraction of the per-trade risk cap — High = 1.0×, Medium = 0.66×, Low = 0.33× — over the 1% rule (Van Tharp's standard, which survives ~20 consecutive losses without ruin). Shares = (equity × risk_pct) / per-share stop distance (fixed-fractional / R-multiple sizing).
2. **Optional advanced — fractional Kelly.** The Kelly criterion (Kelly 1956; Thorp, "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market") sizes bets proportional to edge: `f* = W − (1−W)/R`. Because the bet scales with edge, it is conceptually consistent with conviction-based sizing. **Use only a fraction (½ or ¼ Kelly).** MacLean, Thorp & Ziemba (2010, *Quantitative Finance* 10(7):681–687) note "the Kelly criterion is relatively risky in the short term... it is possible, through bad scenarios, to lose most of one's wealth"; the Kelly property that there is an X% chance of the bankroll dropping to X% of its start implies roughly a 50% chance of a 50% drawdown at full Kelly. Practitioners use fractional Kelly to reduce ruin risk, volatility, and the impact of estimation error. **Cap whatever Kelly suggests at the file 08 per-trade limit.**

### 6. Conflict handling

When some factors are bullish and others bearish, the composite can hide the disagreement. Add an explicit agreement/dispersion check.

**Measures:** net score (can be near zero when factors cancel — a red flag if magnitudes are large); **agreement ratio** (fraction of weighted factors whose sign matches the net direction); **dispersion** (standard deviation of sub-scores — high dispersion + mild net = genuine conflict).

**Rules:**
1. **Confluence threshold:** require ≥ ~65–70% weighted agreement *and* a minimum composite. Conflicting signals mean "no confluence, therefore no trade."
2. **Veto on core factors:** if a designated core factor (trend direction, or the regime gate) opposes the trade, suppress regardless of composite.
3. **Weight by reliability:** down-weight low/unstable-IC factors; ensure factors span distinct dynamics (trend, momentum, value, volume, sentiment) to avoid *false confluence* from correlated factors measuring the same thing.
4. **Low agreement → reduce or stand aside:** moderate agreement flags `LOW_AGREEMENT` and cuts the conviction tier; poor agreement → NO-TRADE.
5. **Avoid analysis paralysis:** don't demand unanimity; calibrate the threshold to remove genuine conflict, not normal noise.

### 7. Pseudocode for the scoring engine

```python
# =====================================================================
# FILE 10 — SCORING ENGINE (signal-only; manual execution)
# Inputs: normalized factor sub-scores from files 02-06 (each ~0-100 or z)
# Gates:  file 07 (regime), file 08 (risk)
# Levels: file 01 (adaptive ATR stop/target)
# Design: transparency-first. Equal-weight default + hard gates.
# =====================================================================

# ---------- CONFIG (few, round, deliberately not over-tuned) ----------
FACTOR_FAMILIES = {            # group correlated factors; weight families equally
    "trend":      ["ma_slope", "adx_score"],
    "momentum":   ["roc_score", "rsi_pos"],
    "meanrev":    ["pullback_score"],
    "value_qual": ["valuation_z", "quality_z"],
    "volume":     ["dollar_vol_z", "obv_score"],
    "sentiment":  ["news_sent", "options_skew"],
}
WEIGHT_SHRINKAGE   = 0.7       # blend toward equal weight (Ledoit-Wolf logic)
AGREEMENT_MIN      = 0.65      # confluence threshold
COMPOSITE_MIN      = 60        # min conviction (0-100) to consider a trade
ATR_PERIOD         = 14        # defer exact value to file 01
RR_TARGET          = 2.0       # reward:risk; file 01 may override
BASE_RISK_PCT      = 0.01      # file 08 per-trade cap (1% equity)
CORE_FACTORS       = ["ma_slope"]   # opposing core factor => veto

# ---------- 1. WEIGHTS: equal-weight default + shrinkage ----------
def build_weights(estimated=None):
    # equal weight across families, then equal within family
    w_equal = {}
    n_fam = len(FACTOR_FAMILIES)
    for fam, members in FACTOR_FAMILIES.items():
        for f in members:
            w_equal[f] = (1.0 / n_fam) / len(members)
    if estimated is None:
        return w_equal
    # shrink any estimated weights toward equal weight
    return {f: WEIGHT_SHRINKAGE * w_equal[f] +
               (1 - WEIGHT_SHRINKAGE) * estimated.get(f, w_equal[f])
            for f in w_equal}

# ---------- 2. HARD GATES (vetoes; checked BEFORE scoring) ----------
def hard_gates_pass(ctx):
    reasons = []
    if not ctx.regime_ok:        reasons.append("REGIME_RISK_OFF")     # file 07
    if not ctx.risk_ok:          reasons.append("RISK_LIMIT_BLOCK")    # file 08
    if not ctx.liquidity_ok:     reasons.append("LIQUIDITY_FAIL")      # file 09
    if not ctx.data_ok:          reasons.append("DATA_INTEGRITY_FAIL")
    return (len(reasons) == 0), reasons

# ---------- 3. COMPOSITE SCORE + ATTRIBUTION ----------
def composite(scores, weights):
    contribs = {f: scores[f] * weights[f] for f in scores}   # full attribution
    raw = sum(contribs.values())
    return raw, contribs       # raw is on the 0-100 scale if inputs are

# ---------- 4. CONFLICT / AGREEMENT ----------
def agreement(scores, weights, direction):
    # neutral point = 50 on a 0-100 sub-score scale
    signed = {f: (scores[f] - 50) for f in scores}
    agree_w = sum(weights[f] for f in scores
                  if (signed[f] > 0) == (direction == "LONG"))
    total_w = sum(weights.values())
    ratio   = agree_w / total_w
    dispersion = pstdev(list(scores.values()))
    core_conflict = any((scores[c] - 50 > 0) != (direction == "LONG")
                        for c in CORE_FACTORS)
    return ratio, dispersion, core_conflict

# ---------- 5. ATR-BASED LEVELS (delegates to file 01) ----------
def atr_levels(ref_price, atr, direction, file01):
    stop   = file01.adaptive_stop(ref_price, atr, direction)   # e.g. Chandelier / k*ATR
    risk   = abs(ref_price - stop)
    target = file01.adaptive_target(ref_price, risk, atr, direction, RR_TARGET)
    if direction == "LONG":
        entry_zone = (ref_price - 0.5 * atr, ref_price)        # pullback band
    else:
        entry_zone = (ref_price, ref_price + 0.5 * atr)
    return entry_zone, stop, target, risk

# ---------- 6. CONVICTION -> SIZE (within file 08 caps) ----------
def position_size(equity, entry, stop, conviction_tier):
    tier_mult = {"High": 1.0, "Medium": 0.66, "Low": 0.33}[conviction_tier]
    risk_pct  = BASE_RISK_PCT * tier_mult          # never exceeds file 08 cap
    risk_dollars = equity * risk_pct
    per_share = abs(entry - stop)
    shares = int(risk_dollars / per_share) if per_share > 0 else 0
    return shares, risk_pct

def tier_of(score):
    if score >= 80: return "High"
    if score >= 70: return "Medium"
    if score >= COMPOSITE_MIN: return "Low"
    return "None"

# ---------- 7. MAIN: one stock -> one signal record ----------
def generate_signal(ticker, scores, ctx, equity, file01):
    weights = build_weights(estimated=None)        # equal-weight default
    gates_ok, gate_reasons = hard_gates_pass(ctx)
    if not gates_ok:
        return {"ticker": ticker, "direction": "NO-TRADE",
                "flags": gate_reasons, "regime_state": ctx.regime_ok,
                "risk_gate_state": ctx.risk_ok,
                "explanation": f"Vetoed by hard gate(s): {gate_reasons}"}

    raw, contribs = composite(scores, weights)
    direction = "LONG" if raw >= 50 else "SHORT"   # SHORT only if file 07 permits
    ratio, dispersion, core_conflict = agreement(scores, weights, direction)

    flags = []
    conv = raw                                     # already 0-100
    if core_conflict:                              # veto on core disagreement
        return {"ticker": ticker, "direction": "NO-TRADE",
                "flags": ["CORE_FACTOR_CONFLICT"],
                "explanation": "Core factor opposes net direction."}
    if ratio < AGREEMENT_MIN:
        flags.append("LOW_AGREEMENT")
        conv *= 0.5                                # soft cut, may drop below min
    if conv < COMPOSITE_MIN:
        return {"ticker": ticker, "direction": "NO-TRADE",
                "conviction_score": round(conv, 1), "flags": flags,
                "factor_contributions": contribs,
                "explanation": "Below conviction/agreement threshold."}

    tier = tier_of(conv)
    ref  = ctx.reference_price
    atr  = ctx.atr
    entry_zone, stop, target, risk = atr_levels(ref, atr, direction, file01)
    entry = entry_zone[1] if direction == "LONG" else entry_zone[0]
    shares, risk_pct = position_size(equity, entry, stop, tier)
    rr = abs(target - entry) / risk if risk > 0 else 0

    # top contributors for the human-readable explanation
    top = sorted(contribs.items(), key=lambda kv: kv[1], reverse=True)[:3]

    return {
        "ticker": ticker, "direction": direction,
        "conviction_score": round(conv, 1), "conviction_tier": tier,
        "reference_price": ref, "atr": atr,
        "entry_zone_low": round(entry_zone[0], 2),
        "entry_zone_high": round(entry_zone[1], 2),
        "stop_price": round(stop, 2),
        "stop_distance_atr": round(risk / atr, 2),
        "target_price": round(target, 2), "reward_risk": round(rr, 2),
        "suggested_risk_pct": round(risk_pct, 4),
        "suggested_shares": shares,
        "regime_state": ctx.regime_ok, "risk_gate_state": ctx.risk_ok,
        "factor_contributions": contribs,
        "agreement_score": round(ratio, 2), "dispersion": round(dispersion, 1),
        "flags": flags,
        "explanation": (f"{direction} {ticker} | tier={tier} conv={conv:.0f} | "
                        f"agree={ratio:.0%} | top: {[t[0] for t in top]} | "
                        f"stop {risk/atr:.1f}xATR, RR {rr:.1f} | gates: regime+risk OK"),
    }
```

**Notes:** Gates run **before** scoring, so no composite can override a veto. The composite is a pure weighted sum with **full per-factor attribution** retained — nothing hidden. Conflict handling is two-tiered (hard veto on core-factor disagreement; soft cut on low overall agreement). All price levels are **delegated to file 01**, so the engine never hard-codes a percentage stop. Position size is conviction-scaled but **bounded by file 08**. To add ML later: compute the model's probability as just *one more entry in `scores`*, keep it inside the same transparent composite, and never let it bypass the gates.

---

## Recommendations

**Stage 0 — Build the transparent core (now).** Implement §7 exactly: equal weights, hard gates (file 07 regime + file 08 risk), composite, agreement check, ATR levels from file 01, conviction-tier sizing over the 1% rule. Log every field in §5 for every candidate, including no-trades. *Benchmark to advance:* the engine reproduces, on historical bars, signals you would endorse manually, with explanations you trust.

**Stage 1 — Paper/live validate (months 1–6).** Trade signal-only on a paper or tiny live account. Keep the 1% (or sub-1%) per-trade cap regardless of conviction while the sample is small. Record realized R-multiples per tier. *Benchmark:* High-tier signals should show a higher realized win rate / expectancy than Low-tier; if not, your conviction score has no edge — fix the factors before touching weights.

**Stage 2 — Cautious weighting (only after ~100+ independent trades).** Consider modest deviations from equal weight via shrinkage (λ ≥ 0.6) and IC tiers, validated with purged/embargoed walk-forward. *Threshold to act:* a factor must clear a t > 3.0-style bar out-of-sample; otherwise leave it equal-weighted.

**Stage 3 — Optional ML layer (only with multi-year data + discipline).** Add an L1/L2 logistic model (then a random forest) as *one additional factor* in the composite, never as the gatekeeper. *Threshold to keep it:* it must improve purged out-of-sample expectancy *and* remain explainable (coefficients / SHAP you can read). If it can't beat the equal-weighted composite out-of-sample, drop it.

**Sizing escalation as the account scales:** keep fixed-fractional 1% sizing as the backbone; only consider fractional Kelly (¼→½) once you have a stable, multi-quarter estimate of W and R per tier, and always cap at the file 08 per-trade limit.

**What would change these recommendations:** evidence that a specific factor's IC is large and stable out-of-sample (justifies a weight bump); a realized drawdown approaching your file 08 circuit-breaker (tighten gates/sizing, don't loosen); or High-tier signals underperforming Low-tier (the scoring logic, not the sizing, is broken).

## Caveats

- **Files 01–09 are referenced from assumed contents.** Reconcile every cross-reference — especially file 01's exact ATR multiple/lookback and file 08's exact caps — against the real files; the engine delegates all level math to file 01 by design.
- **This is a signal generator, not an order router.** All output is a *suggestion* for manual placement.
- **Overfitting is the primary failure mode.** Every weight you tune and threshold you optimize spends degrees of freedom you don't have. Prefer equal weights, few parameters, purged out-of-sample testing, and a high evidence bar (t > 3).
- **ATR stops adapt to volatility but don't prevent gap risk** — overnight gaps in single stocks can blow through any stop. The file 08 per-trade risk cap, not the stop alone, governs survival.
- **Past relationships decay.** Published factors weaken after discovery (post-publication decay is well documented); revalidate periodically and expect live performance below backtest.
- **Some cited practitioner sources** (trading blogs, broker education pages) are secondary; the load-bearing claims here rest on the named peer-reviewed/primary sources (DeMiguel et al. 2009; Gu-Kelly-Xiu 2020; Harvey-Liu-Zhu 2016; López de Prado; Ledoit-Wolf; Wilder 1978; Le Beau; Kelly 1956 / Thorp; MacLean-Thorp-Ziemba 2010; Rudin 2019).