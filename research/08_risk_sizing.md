# Risk Management & Position Sizing for a Signal-Only Swing-Trading System (US Stocks)

## Overview

This is a complete, capital-agnostic rulebook for a signal-only swing-trading system on US individual stocks (holding periods of a few days to one month, user places all orders manually). Every rule is expressed as a percentage of, or a formula taking as input, **current account equity (E)** — nothing is hardcoded to a dollar amount, so the identical logic runs at $500 and at $500,000.

Three core conclusions drive everything below:

1. **Position size must be derived from risk, not from a fixed dollar or share count.** The master equation is `Shares = (E × risk%) / (Entry − Stop)`. Risk per trade should sit at 1% (default) to a 2% ceiling. This single rule — sizing as a fixed fraction of *current* equity — is the "anti-martingale" property that automatically shrinks bets after losses and grows them after wins, and is what keeps an account alive long enough for an edge to matter.

2. **At ~$500 the dominant enemy is friction and granularity, not strategy.** Fractional shares (available at Fidelity, Schwab, Robinhood, Webull, and Interactive Brokers) make percentage-based sizing physically possible at small equity, but the bid-ask spread and slippage — fixed in percentage terms regardless of your size — impose a structural drag that is the same percentage at $500 as at $50,000. The real constraint at $500 is concurrency: you can hold only a few genuinely independent positions.

3. **Survival is governed by drawdown math and portfolio heat, and the base rates are brutal.** A 50% drawdown requires a 100% gain to recover. Credible academic evidence is unambiguous: in Chague, De-Losso & Giovannetti (2020), "Day Trading for a Living?" (SSRN 3423101), of Brazilian equity-futures day traders who persisted more than 300 days, "97% of all individuals … lost money. Only 1.1% earned more than the Brazilian minimum wage and only 0.5% earned more than the initial salary of a bank teller — all with great risk." The rules below are explicitly designed around that asymmetry: small per-trade risk, capped aggregate "heat," correlation awareness, and hard halt thresholds.

A note on the regulatory backdrop: the **Pattern Day Trader (PDT) $25,000 rule was eliminated effective June 4, 2026.** Per FINRA Regulatory Notice 26-10, "FINRA has adopted new intraday margin standards to replace in their entirety the outdated day trading margin requirements, including … the $25,000 pattern day trader minimum equity requirement," with phase-in permitted "over a period of 18 months, until October 20, 2027." The SEC approved the amendment to Rule 4210 on April 14, 2026. It is now largely irrelevant to a swing trader, but the threshold and its successor "intraday margin" framework are covered below because they still shape margin mechanics.

---

## Position sizing formulas (equity-driven)

### (a) Fixed-fractional position sizing
Fixed-fractional sizing risks a constant fraction `f` of current equity on each trade. The "risk" is defined by the distance from entry to stop, not the notional position value.

- **Risk budget per trade:** `RiskDollars = E × f`, where f = 0.01 (default) to 0.02 (ceiling).
- **Shares:** `Shares = RiskDollars / (Entry − Stop)` for a long.
- **Notional/capital deployed:** `Notional = Shares × Entry` (this can be larger than RiskDollars — it is the position value, not the risk).

Because `f` multiplies *current* equity, the dollar bet self-adjusts. This is Van Tharp's CPR framework: **C** (capital at risk) ÷ **R** (risk per unit) = **P** (position size). Van Tharp characterizes fixed-fractional sizing as "anti-martingale" — sizing off a fixed percentage of current capital naturally reduces size after losses, the opposite of the ruinous martingale instinct to double down.

**R-multiples and expectancy:** Define **R** = the dollar amount risked on a trade (1R = your initial risk). Every outcome is then expressed as a multiple of R: a trade exited at +2R made twice what you risked; a stopped-out trade is −1R. A system's *expectancy* is its mean R-multiple. Van Tharp's widely cited benchmark is roughly +0.5R per trade for a strong edge.

### (b) Volatility-based / ATR-based position sizing
ATR (Average True Range, typically 14-period) measures a stock's recent average daily range. Setting the stop as a multiple of ATR makes stop distance — and therefore share count — adapt automatically to each stock's volatility.

- **Stop distance:** `StopDistance = ATR × M`, where M (the multiplier) is commonly 1.5–2 for tighter swing stops and 2.5–3 for wider trend stops. Swing-trading default ≈ 2× ATR.
- **Stop price (long):** `Stop = Entry − (ATR × M)`.
- **Shares:** `Shares = (E × f) / (ATR × M)`.

Worked illustration of the volatility-normalizing effect: with $500 risk, a volatile biotech (ATR×M = $10) gets 50 shares while a calm utility (ATR×M = $2) gets 250 shares — same dollar risk, position size scaled to volatility. Higher volatility ⇒ wider stop ⇒ fewer shares. (On any given bar there is roughly a 50% chance price moves 1 ATR against you on noise alone, which is why a 1× stop whipsaws and 2× is the swing default.)

### (c) The core 1–2% risk math
The unifying equation, valid at any equity level:

```
Shares = (E × risk%) / (Entry − Stop)        [long]
Shares = (E × risk%) / (Stop − Entry)        [short]
StopDistance = ATR × M     (ATR variant)
Always round DOWN to keep realized risk ≤ target.
```

**Worked examples at multiple equity tiers** (1% risk, entry $50, stop $47 ⇒ $3 stop distance):

| Equity E | Risk $ (1%) | Shares = Risk$/$3 | Notional (Shares×$50) | Notional as % of E |
|---|---|---|---|---|
| $500 | $5.00 | 1.67 (fractional) | $83 | 16.7% |
| $2,000 | $20.00 | 6.67 | $333 | 16.7% |
| $10,000 | $100.00 | 33.3 | $1,667 | 16.7% |
| $50,000 | $500.00 | 166.7 | $8,333 | 16.7% |
| $250,000 | $2,500.00 | 833.3 | $41,667 | 16.7% |

Notice the notional is always 16.7% of equity for this stop width — the math is fully scale-invariant. At $500, the required position is **1.67 shares**, which is only purchasable via fractional shares; a whole-share-only broker would force rounding to 1 share (0.6% realized risk) or 2 shares (1.2% risk), distorting the intended risk.

A second ATR-based example at two tiers (1% risk, entry $100, ATR = $2.50, M = 2 ⇒ stop distance $5, stop at $95):
- At E = $10,000: RiskDollars = $100 ⇒ `Shares = 100 / 5 = 20 shares` (notional $2,000 = 20% of equity).
- At E = $500: RiskDollars = $5 ⇒ `Shares = 5 / 5 = 1 share` (notional $100 = 20% of equity) — still whole-share-feasible here, but any wider ATR or lower-risk setting pushes it fractional.

**Kelly criterion (optional refinement, used capped):** The Kelly fraction `f* = (bp − q)/b` (b = reward/risk odds, p = win prob, q = 1−p) gives the geometric-growth-maximizing bet. Example: 40% win rate at 2:1 ⇒ f* = (2×0.4 − 0.6)/2 = 10%. **Full Kelly is far too aggressive for discretionary stock trading** — estimation error in p and b causes severe overbetting and 40–50%+ drawdowns (MacLean, Thorp & Ziemba, *The Kelly Capital Growth Investment Criterion*, 2011, show small errors in expected-return estimates produce massive overbetting under full Kelly). Standard practice is fractional Kelly (¼ to ½). For this system, treat fixed-fractional 1–2% as the governing rule and use Kelly only as a sanity ceiling: if 1–2% exceeds half-Kelly, the edge estimate is probably too optimistic.

---

## Constraints by account-size tier

The fundamental insight: **percentage rules are identical across tiers, but their practical *executability* changes.** Friction (spread + slippage) is roughly constant as a *percentage*, while granularity and concurrency improve as equity grows.

### Tier 1 — ~$500 (micro)
- **Fractional shares are mandatory.** Minimum fractional/dollar-based order: **$1 at Fidelity, Robinhood, and Interactive Brokers** (IBKR's documented minimum is "either 0.0001 shares or USD/EUR 1"); **$5 at Schwab** (Stock Slices, limited to S&P 500 names, up to 30 slices per order) **and Webull.** Without fractional shares, the position-sizing math at $500 routinely produces sub-1-share quantities and cannot be honored.
- **Concurrency:** With 1% risk and realistic stop widths, you can *mathematically* open many tiny positions, but each becomes trivially small in notional. Practical limit: **2–4 concurrent positions**; more than that produces positions so small that fixed percentage frictions dominate.
- **Friction is the silent killer.** Zero-commission brokers (all five listed) removed explicit commissions, but the bid-ask spread is a real cost: a $0.10 spread on a $5.35 speculative stock is 1.87% one-way, versus roughly 0.0024% on a $410 mega-cap (a $0.01 spread). Trading low-priced/illiquid names at $500 can cost 1–2%+ per round trip in spread alone — comparable to your entire per-trade risk budget. Robinhood and Webull also route orders for payment-for-order-flow, which can produce slightly worse fills; using limit orders mitigates this.
- **Implication:** trade liquid, higher-priced large caps (tight spreads), keep concurrency low, and accept that compounding is slow.

### Tier 2 — low thousands ($2,000–$10,000)
- Fractional shares still useful but whole-share rounding error becomes minor (at $10k, a 1% risk = $100, comfortably several whole shares of most stocks).
- **Concurrency rises to ~4–8 positions** while keeping each meaningful.
- Spread/slippage drag falls as a share of P&L because position notionals are larger relative to the fixed spread.
- A standard margin account above $2,000 unlocks intraday buying power under the post-June-2026 framework; the $2,000 minimum for *leveraged/margin* trades persists (confirmed by broker guidance such as Firstrade's PDT-change notice: "the $25,000 minimum equity requirement for day trading will no longer apply. Your margin account is only required to maintain the standard $2,000 minimum equity").

### Tier 3 — tens of thousands ($25,000+)
- Whole shares everywhere; fractional irrelevant for sizing precision.
- **Concurrency of 8–12+ independent positions** feasible — enough to diversify across sectors and cap correlation risk meaningfully.
- Spread/slippage becomes negligible as a percentage on liquid names.
- **PDT note:** historically $25,000 was the gate for day trading in a margin account. **As of June 4, 2026 the PDT designation and its $25,000 minimum are abolished**, replaced by a risk-based intraday margin standard. For a swing trader (positions held overnight, not closed same-day) PDT never bit in practice, but the change removes any lingering concern about occasional same-day exits.

**Minimum practical position size rule of thumb:** keep each position's notional large enough that the round-trip spread is a small fraction (say <10%) of your per-trade risk budget. At 1% risk, that argues for trading names where the round-trip spread is well under 0.1% of position value — i.e., liquid stocks.

---

## Stop/drawdown rules

### Initial stop placement
- **Percentage-based:** `Stop = Entry × (1 − s)`, s commonly 3–8% for multi-day/large-cap swing trades.
- **ATR-based (preferred, volatility-adaptive):** `Stop = Entry − (ATR × M)`, M ≈ 2 for swings. A 1× ATR stop triggers on noise ~50% of the time; 2× filters most noise; 3× is for high-conviction/wide trades.
- **Stop drives size, never the reverse.** Place the stop at a logical invalidation level first, then solve for shares. Sizing first and placing the stop arbitrarily inverts the discipline and produces inconsistent risk.

### Trailing stops for swing trades
- **Chandelier Exit (Chuck LeBeau):** `Trail = HighestHigh(22) − ATR(22) × 3`. Trails up only, never down; the 22-period lookback ≈ one trading month, fitting the holding window. Tighten to 2–2.5× ATR once deep in profit. The 3× multiplier "provides a buffer that is three times the volatility," giving normal pullbacks room while still catching genuine reversals.
- **Moving-average trail:** exit on a close beyond the 20-EMA (short trend) or 50-EMA (medium trend).
- **Swing-low trail:** ride higher-highs/higher-lows, exit on a close below the prior swing low (place it ~1 ATR below structure to avoid stop-hunting).

### Account-level drawdown / halt rules (all % of current equity)
- **Per-trade risk:** 1% default, 2% absolute ceiling.
- **Daily loss limit:** a common construction is **Daily limit = 3 × per-trade risk** (≈3% at 1% risk; "3% is the most anyone should be losing in a single day"). For swing trading, where few trades trigger per day, a **weekly loss limit (~5–6%)** is more relevant; halt new entries when hit.
- **Monthly loss limit:** **~10%** is a widely used "step back and review" threshold (with daily 1% risk over ~20 trading days, 10–20% is the empirical band; 10% is the conservative ceiling).
- **Max-drawdown halt:** reduce size at **−5% to −10%** from equity peak; **hard stop for structural review at −15% to −20%.** Professionals typically target max drawdown under 20%; retail accounts routinely suffer 30–50%, which is where the recovery math turns lethal.
- **De-risking ladder:** cut per-trade risk by 25–50% once in a defined drawdown (e.g., halve risk to 0.5% after the account is down ~10% from peak); restore only after recovering to within a set band of the peak. **Never increase size to "make it back faster"** — doubling size after a 50% drawdown and taking another 50% loss produces a 75% drawdown needing a 300% gain.

### The drawdown-recovery math (why limits are strict)
Required recovery gain = `1 / (1 − D) − 1`, where D is the drawdown fraction:

| Drawdown D | Gain required to recover |
|---|---|
| 5% | 5.3% |
| 10% | 11.1% |
| 20% | 25% |
| 25% | 33.3% |
| 30% | 42.9% |
| 50% | 100% |
| 75% | 300% |

The relationship is convex: losses compound against you faster than linearly. A 50% loss needs a 100% gain merely to break even; a 75% loss needs 300%. This asymmetry — combined with the behavioral fact that losses hurt more than equal gains (Tversky & Kahneman's 1992 "Advances in Prospect Theory," *Journal of Risk and Uncertainty* 5:297–323, empirically estimated the loss-aversion coefficient λ ≈ 2.25, i.e., losses are weighted about 2.25× more heavily than equivalent gains) — is the entire justification for small per-trade risk and hard halts. Preventing a deep drawdown is vastly easier than climbing out of one.

---

## Portfolio-level risk

### Portfolio heat (total open risk)
**Portfolio heat = the sum of open risk across all positions, as a % of equity** — i.e., what you lose if every open stop is hit at once.

```
Heat = Σ [ Sharesᵢ × (Entryᵢ − Stopᵢ) ] / E
```

With each trade risking 1%, five open positions = 5% heat; with 2% each, five positions = 10% heat. **Cap total heat at roughly 6% (conservative) to 10% (aggressive).** A common professional band is 6–10% for retail; some institutions run 3–6%. Above ~10%, a single correlated market event can inflict an account-threatening loss even with "correct" per-trade sizing.

A practical concurrency consequence: at 2% risk and a 10% heat cap, you can hold at most **5 positions**; at 1% risk, **10 positions**. This is *why* small accounts (limited to a few positions by friction) should generally use the 1% risk setting — it lets them reach their concurrency ceiling without breaching heat.

### Correlation risk
Per-trade sizing assumes positions are independent. They are not. **Three oil stocks are effectively one larger bet on oil; in a crash, correlations spike toward 1.0 and "diversified" positions move together.** Holding multiple correlated positions silently multiplies your true risk beyond the per-trade budget.

Methods to control it (capital-agnostic):
- **Count correlated positions as one.** If three holdings are in the same sector/factor and each risks 1%, treat the cluster as ~3% of *concentrated* risk, not three independent 1% bets.
- **Sector concentration cap:** limit any single sector to **~20–30% of total portfolio heat** (and/or a max number of positions per sector, e.g., 2).
- **Correlation-adjusted sizing:** when adding a position correlated with an existing one, reduce its size (e.g., halve the new position's risk) so the *cluster* stays within a single-position-equivalent risk budget.
- **Volatility-regime scaling:** lower the heat cap in turbulent markets (e.g., 5% calm, 3% volatile, 2% crisis).

### Daily heat/risk review (system check)
Before adding any position, the system should compute: current total heat, sector heat distribution, and whether the new position would breach the heat cap or any sector cap. Reject or downsize the signal if so.

---

## Realistic expectations

### Expectancy is the master metric
```
Expectancy ($) = (Win% × AvgWin$) − (Loss% × AvgLoss$)
Expectancy (R) = (Win% × AvgWin_R) − (Loss% × AvgLoss_R)   [mean R-multiple]
Break-even win rate = 1 / (1 + R)    where R = reward:risk
```
Break-even win rates: at 1:1 you need >50%; at 2:1 you need 33.3%; at 3:1 you need 25%; at 5:1 you need 16.7%. **This is why a low win rate can be highly profitable** — a 2:1 system can be wrong 60% of the time and still make money. Van Tharp's benchmark: +0.5R per trade is a strong edge; anything above ~+0.3R over 200+ trades is genuinely tradeable; below ~+0.1R you break even after costs.

### Win-rate / risk-reward ranges by style
- **Swing trading (3–10+ day holds):** typically **40–55% win rate** paired with **2:1 to 3:1** reward:risk. This is the band most profitable retail traders occupy; realistic expectancy ≈ **+0.3R to +0.6R**.
- **Trend following (weeks–months):** ~30–40% win rate, 3:1 to 5:1+, with a handful of big winners driving most P&L — requires tolerating long losing streaks.
- Higher reward:risk inherently lowers win rate (bigger targets are hit less often), so optimize the *combination* for expectancy, not win rate alone.

### Why most retail accounts fail (the base rates)
The academic evidence is sobering and remarkably consistent across markets:

- **Barber & Odean (2000), "Trading Is Hazardous to Your Wealth"** (*Journal of Finance* 55(2)): "Of 66,465 households with accounts at a large discount broker during 1991 to 1996, those that trade most earn an annual return of 11.4 percent, while the market returns 17.9 percent. The average household … turns over 75 percent of its portfolio annually." That ~6.5-point annual penalty is the cost of overtrading.
- **Barber, Lee, Liu & Odean — Taiwan studies.** In "Do Individual Day Traders Make Money? Evidence from Taiwan" (working paper, 2004; sample 1995–1999), day trading accounted for "over 20 percent of total volume," and "in the typical six month period, more than eight out of ten day traders lose money." In the published follow-up, "The Cross-Section of Speculator Skill: Evidence from Day Trading" (*Journal of Financial Markets* 18, 2014; sample 1992–2006), the central finding is verbatim: **"Less than 1% of the day trader population is able to predictably and reliably earn positive abnormal returns net of fees"** (~4,000 of ~450,000 day traders in the average year). A companion paper ("Do Day Traders Rationally Learn About Their Ability?") documents that **more than 75% of day traders quit within two years**, with poor performers most likely to quit (one-, two-, and three-year survival rates of 44%, 24%, and 15%).
- **Chague, De-Losso & Giovannetti (2020), "Day Trading for a Living?":** of Brazilian equity-futures day traders who persisted 300+ days, **97% lost money**, only **1.1% earned more than the Brazilian minimum wage**, only 0.5% more than a bank teller's starting salary, and there was **no evidence of learning** with experience.
- **Jordan & Diltz (2003):** ~64% of US day traders lost money.
- **DALBAR QAIB** behavior-gap research: even passive average equity-fund investors chronically underperform the index. Per DALBAR's 2025 QAIB report (released March 31, 2025), the Average Equity Investor earned 16.54% in 2024 versus the S&P 500's 25.02% — an **848-basis-point lag**, which DALBAR called "the second-largest investor performance gap of the past decade" — driven by bad timing (panic selling and return chasing).

**Dominant failure drivers:** undercapitalization (friction overwhelms a tiny edge), overtrading (costs compound), oversizing (one bad cluster wipes out months of gains), and behavioral errors (cutting winners, letting losers run — the prospect-theory trap). Position sizing — not entry selection — is the variable most associated with the spread between survival and ruin.

### Realistic return expectation
Be deliberately humble. The market's long-run return is ~9–10%/year. A disciplined retail swing trader with a genuine, small positive edge (+0.3R to +0.5R) might realistically aim to modestly beat that on a risk-adjusted basis — but the *first* objective at $500 is to not blow up while compounding slowly and proving the edge over 100+ trades. Spectacular return claims are a red flag, not a target.

---

## Summary table: hard rules the system must enforce

All rules are functions of current account equity **E**, ATR, and the trade's entry/stop. The system reads E live and recomputes every rule on each signal.

| # | Rule | Computable form (input = current equity E) | Default / threshold |
|---|---|---|---|
| 1 | Per-trade risk budget | `RiskDollars = E × risk%` | risk% = 1% default, 2% hard ceiling |
| 2 | Position size (long) | `Shares = (E × risk%) / (Entry − Stop)`, round **down** | — |
| 3 | Position size (short) | `Shares = (E × risk%) / (Stop − Entry)`, round **down** | — |
| 4 | ATR stop distance | `StopDistance = ATR × M`; `Stop = Entry − ATR×M` (long) | M = 2 (swing default); 1.5–3 range |
| 5 | Percentage stop (alt) | `Stop = Entry × (1 − s)` | s = 3–8% |
| 6 | Min position viability | reject if round-trip spread > 10% of `RiskDollars` | trade liquid names |
| 7 | Fractional-share flag | if `Shares` < 1 whole share, require fractional-enabled broker | $1 min (Fidelity/RH/IBKR), $5 (Schwab/Webull) |
| 8 | Portfolio heat cap | `Heat = Σ[Sharesᵢ×(Entryᵢ−Stopᵢ)] / E` must stay ≤ cap | ≤ 6% conservative, ≤ 10% max |
| 9 | Max concurrent positions | `floor(HeatCap% / risk%)` | e.g., 10 at 1%/10%; 5 at 2%/10% |
| 10 | Sector concentration cap | sector heat ≤ X% of total; max N positions/sector | ≤ 25–30% of heat; N = 2 |
| 11 | Correlation adjustment | for a position correlated with an open one, halve its risk% | treat cluster as 1 position |
| 12 | Trailing stop (Chandelier) | `Trail = HighestHigh(22) − ATR(22)×3`, up-only | tighten to 2–2.5× deep in profit |
| 13 | Daily loss halt | halt new entries if day's loss ≥ `E × 3%` | 3× per-trade risk |
| 14 | Weekly loss halt | halt if week's loss ≥ `E × 5–6%` | review |
| 15 | Monthly loss halt | halt if month's loss ≥ `E × 10%` | mandatory review |
| 16 | Drawdown de-risking | if equity ≤ peak ×(1−0.10), cut risk% by 50% | restore near peak |
| 17 | Hard drawdown stop | full halt + structural review if equity ≤ peak ×(1−0.15 to 0.20) | 15–20% |
| 18 | Recovery-gain awareness | `ReqGain = 1/(1−D) − 1` surfaced to user at each drawdown | informational guardrail |
| 19 | Expectancy gate | track mean R over rolling 50–100 trades; flag if < +0.1R | pause/review sub-edge |
| 20 | Kelly sanity ceiling | if chosen risk% > ½·Kelly f*, warn (edge likely overestimated) | use ¼–½ Kelly |

**Implementation note:** every threshold above is a percentage or a closed-form formula taking E as input, so the system scales continuously from $500 to any size with no hardcoded dollar values. The only dollar-denominated external constraints are broker fractional-share minimums ($1–$5) and the residual $2,000 margin-account floor for leveraged trades — both are floors the system should be *aware* of (rule 7), not parameters it sets.

---

## Recommendations (staged, with thresholds that change them)

**Stage 0 — before any live trade (any equity):** Hardcode the master sizing equation and rounding-down rule. Default to **1% risk**. Trade only liquid large-caps (tight spreads). Require fractional-share capability at the broker. Paper-trade or micro-trade until you have 50+ logged trades with a measured mean R.

**Stage 1 — ~$500 to ~$2,000 (survival/proof phase):**
- Risk 1% per trade; **2–4 concurrent positions max**; total heat ≤ 6%.
- Trade only names where round-trip spread < 0.1% of notional.
- Goal is not returns — it's proving expectancy ≥ +0.3R over 100+ trades while keeping max drawdown < 15%.
- **Threshold to advance:** consistent positive expectancy (mean R ≥ +0.3 over a rolling 100-trade window) AND equity sustainably above ~$2,000.
- **Threshold to halt/revert:** mean R < +0.1R over 50 trades → stop, review the signal source.

**Stage 2 — ~$2,000 to ~$25,000 (scaling phase):**
- Keep 1% risk; expand to **4–8 positions**; heat cap 6–8%; enforce sector cap (≤2 positions/sector, ≤25–30% of heat).
- Introduce Chandelier trailing stops to let winners run.
- **Threshold to advance:** stable expectancy maintained through at least one adverse market regime (e.g., a 10%+ market pullback) without breaching the −15% drawdown halt.

**Stage 3 — $25,000+ (mature phase):**
- Optionally raise risk toward (never above) 2% only if half-Kelly supports it; **8–12 positions**; heat cap up to 10%.
- Add volatility-regime heat scaling (cut heat cap to 3–5% in high-VIX environments).
- Continue de-risking ladders and hard halts unchanged — they are scale-invariant.

**Universal halt triggers (never override):** daily −3%, weekly −5–6%, monthly −10%, and a full structural review at −15–20% from peak.

---

## Caveats

- **Regulatory timing:** The PDT/$25,000 elimination took effect **June 4, 2026**, but brokers have until **October 20, 2027** to fully implement; verify your specific broker's status. The $2,000 minimum for margin/leveraged trading remains. For a cash-account, non-leveraged swing trader, none of this is a binding constraint.
- **Fractional-share frictions:** fractional shares are marked "not held" (broker has price/time discretion), cannot be transferred between brokers (they're liquidated on transfer), and carry no voting rights. Schwab's program is limited to S&P 500 names. These are operational, not risk-sizing, concerns.
- **Spread/slippage figures cited from general trading sources** describe mechanics that apply across asset classes; exact spreads vary by name and time of day — always check the live quote. Several percentage thresholds (heat caps, daily/weekly/monthly limits, ATR multipliers) are *conventions* from reputable trading educators and prop-firm practice, not laws of nature; backtest and tune them to your specific signal's R-distribution.
- **Retail-failure statistics come from different markets and instruments** (US households, Taiwanese and Brazilian day traders) and largely study *day* trading, which is higher-frequency and higher-cost than the swing trading described here. The direction of the evidence (most active retail traders lose net of costs; costs and oversizing are the main killers) transfers cleanly, but the precise percentages are not a forecast of swing-trading outcomes. The DALBAR methodology has been criticized for how it computes the "behavior gap," so treat its exact basis-point figures as directional.
- **Kelly and expectancy depend on accurate inputs.** Win rate and reward:risk estimated from too few trades (under ~50–100) are statistically meaningless; do not size off them. When uncertain, bet less — overbetting is far more damaging than underbetting.
- **This is an educational risk-management framework, not investment advice.** No position-sizing rule converts a negative-expectancy signal into a profitable one; it only controls the rate of ruin. The edge must come from the signal itself.