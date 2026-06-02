# Technical Analysis for Swing Trading US Stocks: An Evidence-Graded, Computable Rulebook

## Overview

**Bottom line:** For multi-day to multi-week holds of US single stocks, the techniques with the strongest empirical support are *trend/momentum* methods (moving-average trend filters, time-series and cross-sectional momentum, channel/Donchian breakouts) and *volatility-scaled risk management* (ATR-based stops and position sizing). Pure pattern-recognition and candlestick methods have weak-to-mixed evidence and should be treated as secondary confirmation, not primary signals. Critically, the academic record shows that the same simple rules that "worked" in-sample (Brock, Lakonishok & LeBaron 1992) largely stopped beating the market out-of-sample once data-snooping was accounted for (Sullivan, Timmermann & White 1999) and after transaction costs — so the realistic goal is a small, decaying edge that must be ruthlessly protected from costs and over-optimization, not a holy grail.

This report grades each technique by (a) strength of evidence, (b) win-rate/false-signal data where it exists, and (c) a precise computable rule. It ends with a summary table mapping each signal to its required inputs and an independent 0–100 sub-score so you can mix and weight them yourself.

**Key framing facts (with sources):**
- **Brock, Lakonishok & LeBaron (1992,** *Journal of Finance* 47(5):1731–1764**)** found variable-length moving-average rules on the Dow (1897–1986) produced — verbatim — "a daily return for buy periods of 0.042 percent which is about 12 percent at an annual rate. The corresponding daily return for the sell periods is -0.025 percent which is about -7 percent at an annual rate." That is a ~0.067%/day (~19% annualized) buy-sell spread in-sample.
- **Sullivan, Timmermann & White (1999,** *Journal of Finance* 54(5):1647–1691**)** applied White's Reality Check bootstrap to a universe of 7,846 technical trading rules on 100 years of daily DJIA data, and concluded (verbatim) that "the best technical trading rule does not provide superior performance when used to trade in the subsequent 10-year post-sample period" (1987–1996) — the in-sample edge was "completely reversed."
- **Jegadeesh & Titman (1993,** *Journal of Finance* 48(1):65–91**):** the 12-month-formation/3-month-holding winner-minus-loser portfolio earned **1.31%/month** (no lag; t=3.74) and 1.49%/month with a one-week lag; the widely used 6-month/6-month strategy earned **0.95%/month** (t=3.07). The paper documents that strategies "generate significant positive returns over three- to twelve-month holding periods" and that "part of the abnormal returns generated in the first year after portfolio formation dissipates in the following two years." This is the empirical bedrock for "buy strength."
- **Moskowitz, Ooi & Pedersen (2012,** *Journal of Financial Economics* 104(2):228–250**),** verbatim: "We document significant 'time series momentum' in equity index, currency, commodity, and bond futures for each of the 58 liquid instruments we consider. We find persistence in returns for one to 12 months that partially reverses over longer horizons" (dataset Jan 1985–Dec 2009).
- Academic skepticism is real: most TA studies that find profits suffer from data-snooping, survivorship bias, and ignore costs. For a $500 account, costs/slippage are the dominant adversary.

**Account-size note:** All rules below are percentage- or volatility-based. With ~$500, use a broker with zero commissions and fractional shares (so percentage sizing is feasible), and concentrate on liquid stocks/ETFs to minimize spread, which is the largest cost burden for small accounts.

---

## Indicators (with computable rule definitions)

Notation: `C[t]` = close at bar t (daily bars). `H`, `L`, `O` = high/low/open. `SMA(n)`, `EMA(n)` = simple/exponential moving averages. All rules evaluated on the daily close unless noted.

### 1. Moving Averages (trend filter) — Evidence: MODERATE-STRONG as a filter; WEAK as a standalone crossover signal
- **SMA/EMA slope and price-vs-MA:** The robust, well-supported use is as a *regime filter*, not a trigger. Long-only above a long MA, flat/short below.
- **Golden/Death cross (50/200):** On the S&P 500 index it captures major bull runs and avoids deep bear markets, but generates few signals (~33 in 66 years per QuantifiedStrategies' S&P backtest), is heavily lagging, and underperforms buy-and-hold on a total-return basis; its real value is drawdown reduction. On individual stocks it produces more whipsaws. Index backtests show ~67–79% "win rate" but that is the diversified upper bound, not what single stocks deliver. The death cross is best used as an exit rule, not a short trigger (S&P has historically averaged positive 12-month returns after many death crosses).
- **Computable rules:**
  - Trend filter: `LONG_OK = C[t] > SMA(200)` and `SMA(50)[t] > SMA(50)[t-5]` (rising 50-day).
  - Faster swing filter: `C[t] > EMA(20) > EMA(50)` (stacked EMAs).
  - Golden cross: `SMA(50)[t] > SMA(200)[t]` AND `SMA(50)[t-1] <= SMA(200)[t-1]`.
  - Pullback-to-MA entry (higher evidence than crossover): in an uptrend (`C > SMA(50)`), buy when price pulls back to touch/near EMA(20) then closes back up: `L[t] <= EMA(20) AND C[t] > EMA(20) AND C[t] > C[t-1]`.

### 2. Momentum / Relative Strength — Evidence: STRONG (best-documented anomaly)
- Cross-sectional momentum (Jegadeesh-Titman 1993) and time-series momentum (Moskowitz-Ooi-Pedersen 2012) are among the most replicated effects in finance. For swing horizons, a 3–12 month lookback is the empirically supported window; the effect is strongest in the first ~3 months and partially reverses after ~12 months. Jegadeesh-Titman note the strategy loses ~7% on average each January but is positive in other months.
- **Computable rules:**
  - Time-series momentum filter: `MOM_OK = (C[t] / C[t-126]) - 1 > 0` (6-month return positive; 126 trading days).
  - Relative-strength rank: rank your universe by 126-day return; only take longs in the top quartile/decile.
  - Skip-month convention (reduces short-term reversal contamination): use return from t-21 to t-252.

### 3. RSI (Wilder, 14) — Evidence: MIXED; the 2-period mean-reversion variant has the most concrete backtests
- Standard RSI(14) overbought (70) / oversold (30) as a standalone reversal signal has weak evidence in trending stocks.
- **RSI(2) mean reversion (Connors):** Buy when RSI(2) < 10 (lower = stronger edge; Connors found returns higher buying on a dip below 5 than below 10) while price is above the 200-day SMA; exit on close above SMA(5) or when RSI(2) > 70/90. Connors found in large backtests that adding a hard stop-loss *hurt* performance for this specific mean-reversion system — a counterintuitive but well-documented result. The vanilla version has decayed over time; one quant replication (Quantitativo) revived it by tilting toward lower market-cap names and trading many instruments in parallel.
- **RSI divergence:** price makes a lower low while RSI makes a higher low (bullish). Weak/anecdotal as a standalone; better as confirmation.
- **Computable rules:**
  - Mean-reversion long: `C[t] > SMA(200) AND RSI(2)[t] < 10`. Exit: `C[t] > SMA(5)`.
  - Momentum-regime RSI: in swing trend-following, use RSI(14) > 50 as a momentum confirmation (not >70 as a sell).
  - Bullish divergence (computable): `L[t] < min(L[t-1..t-15]) AND RSI(14)[t] > RSI(14) at that prior low`.

### 4. MACD (12,26,9) — Evidence: WEAK-MODERATE; lagging; works better filtered by trend
- Signal-line crossovers alone are lagging and prone to whipsaw in choppy markets; backtests show variable performance, best in trending/volatile regimes and worst in flat markets (QuantifiedStrategies reports a trend-following MACD case at ~6.78% annualized ROI, profit factor ~1.09 — a thin standalone edge). Filtering with a 50/200-SMA trend rule improves results. The histogram (MACD–signal difference, Aspray 1986) is a slightly earlier momentum-velocity read.
- **Computable rules:**
  - Filtered bullish cross: `C[t] > SMA(50) AND MACD_line[t] > Signal[t] AND MACD_line[t-1] <= Signal[t-1]`.
  - Histogram momentum: `Hist[t] > 0 AND Hist[t] > Hist[t-1]` (rising momentum) as a confirmation flag.
  - MACD divergence: same construction as RSI divergence; treat as weak confirmation only.

### 5. ATR (Average True Range, 14) — Evidence: STRONG for risk management (not a directional signal)
- ATR is the workhorse of *adaptive* stops and sizing. It does not predict direction; it measures volatility so stops/targets scale with the instrument and regime. ATR-adaptive exits beat fixed-percentage exits in published comparisons (e.g., Chandelier 22/3 produced a 1.61 profit factor vs 1.28 for a fixed 10% trailing stop and 1.09 for a fixed 5% stop in a StratBase daily backtest).
- **Computable definitions:**
  - `TR[t] = max(H[t]-L[t], |H[t]-C[t-1]|, |L[t]-C[t-1]|)`; `ATR(14) = Wilder-smoothed average of TR`.
  - Stop: `stop = entry - k*ATR(14)`, k typically 2–3 for swing.
  - Volatility position sizing: `shares = (equity * risk_pct) / (k*ATR(14))`.

### 6. Volume confirmation, Relative Volume, OBV — Evidence: MODERATE for breakout confirmation
- Volume confirmation of breakouts is one of the more supported volume ideas: breakouts on volume ≥1.5× the 20-day average are more likely to hold; low-volume breakouts more often fail. Bulkowski's data, however, adds nuance — *very* high volume on breakout day does not materially improve performance and can triple failure rates in some studies (use as a binary confirm, not "more is always better").
- OBV (cumulative up/down volume, Granville) is best as a trend-confirmation/divergence overlay, most useful on daily/weekly charts; largely anecdotal as a standalone trigger.
- **Computable rules:**
  - Relative volume confirm: `RVOL = Volume[t] / SMA(Volume,20)[t]; confirm if RVOL >= 1.5`.
  - OBV trend confirm: `OBV[t] > EMA(OBV,20)[t]` and OBV making higher highs with price.

### 7. Bollinger Bands (20, 2σ) — Evidence: MODERATE; regime-dependent (squeeze-breakout vs mean-reversion)
- Two distinct uses that must be matched to regime: (1) **Squeeze breakout** (bandwidth in low percentile → trade the breakout) has positive expectancy over 5–10 bar holds with ~55–60% directional accuracy but larger winners than losers; (2) **mean reversion** (fade band touches back to the middle) shows >60% win rates only in *confirmed ranging* markets and collapses in trends. John Bollinger himself stresses bands are descriptive, not predictive; band touches are not automatic signals. Option Samurai's backtest found 2–3 days outside the band is the "sweet spot," with closes 2 consecutive days below the lower band tending to revert upward.
- **Computable definitions:**
  - `mid = SMA(20)`, `upper/lower = mid ± 2*stdev(C,20)`. `%B = (C-lower)/(upper-lower)`. `BandWidth = (upper-lower)/mid`.
  - Squeeze: `BandWidth[t] <= 20th percentile of BandWidth over last 126 bars`. Breakout long: squeeze active AND `C[t] > upper` AND RVOL≥1.5.
  - Mean-reversion long (range regime only, flat SMA20): `C[t] < lower AND RSI(2) < 10`; target = mid.

### 8. VWAP and Anchored VWAP — Evidence: WEAK-MODERATE (practitioner), little peer-reviewed
- Session VWAP is intraday and largely irrelevant to multi-day holds. **Anchored VWAP (AVWAP)** — cumulative volume-weighted average price from a chosen anchor (earnings, breakout day, swing low, major-volume day) — is the swing-relevant version; concept introduced by Paul Levine and popularized by Brian Shannon. It represents the average cost basis of participants since the anchor, acting as adaptive support/resistance. Evidence is practitioner-based, not academically validated; use as a confluence level.
- **Computable definition:** from anchor bar a: `AVWAP[t] = Σ(TypicalPrice[i]*Vol[i]) / Σ(Vol[i])` for i=a..t, `TypicalPrice=(H+L+C)/3`. Bullish if `C > AVWAP` anchored at last major low/earnings; dips to AVWAP in an uptrend are candidate entries.

### 9. ADX/DMI (14, Wilder 1978) — Evidence: MODERATE as a trend-strength *filter*
- ADX measures trend strength (not direction). The widely used threshold is ADX>25 = trending, <20 = choppy/avoid. Used to gate trend-following entries (take DI crossovers / breakouts only when ADX>25) it can reduce whipsaws. It is lagging and non-directional; practitioner tests (Liberated Stock Trader, not peer-reviewed) suggest ADX(14) crossing 20 outperformed the S&P 500 by ~28% over a recent decade.
- **Computable rules:**
  - Trend gate: `ADX(14) > 25` required for breakout/trend entries.
  - Directional: `+DI > -DI` for longs.

### 10. Donchian / Keltner Channels — Evidence: MODERATE-STRONG (Donchian breakouts have the trend-following pedigree)
- Donchian channel breakouts (N-day high/low) are the classic, well-documented trend-following entry (Turtle system lineage). Channel breakouts are among the trend-following families that survived costs in several multi-market studies (Sobreira & Louro on MSCI indices found trend-following families — moving averages and channel breakouts — dominated contrarian rules after costs, stronger in emerging/frontier than advanced markets). Keltner channels (EMA ± ATR multiple) are an ATR-based envelope used similarly and as the squeeze partner to Bollinger Bands (TTM Squeeze = BB inside Keltner).
- **Computable rules:**
  - Donchian breakout long: `C[t] > max(H[t-1..t-20])` (20-day high breakout).
  - Donchian exit: `C[t] < min(L[t-1..t-10])` (10-day low).
  - Keltner: `mid=EMA(20); upper/lower = mid ± 2*ATR(10)`.

### 11. Parabolic SAR — Evidence: WEAK as signal; usable as a trailing-exit mechanic
- SAR accelerates toward price over time; useful only in sustained trends, whipsaws badly in ranges. Best role is a mechanical trailing stop, not entry.

### 12. Stochastic Oscillator — Evidence: WEAK-MIXED, similar profile to RSI; mean-reversion oriented
- %K/%D crossovers in overbought/oversold zones; weak standalone, marginally better as confirmation within a trend filter.

### Chart patterns & candlesticks — Evidence: MIXED-to-WEAK; the most folklore-laden area
- **Lo, Mamaysky & Wang (2000,** *Journal of Finance* 55(4):1705–1765**)** — the most rigorous academic test (nonparametric kernel-regression pattern detection, US stocks 1962–1996): several patterns (incl. head-and-shoulders, double bottoms) carry *some* incremental information, especially for NASDAQ stocks, but the authors caution that "patterns that are optimal for detecting statistical anomalies need not be optimal for indicating trading profits, and vice versa" — i.e., statistical detectability ≠ profits after costs.
- **Bulkowski** (large practitioner database, ~30,000+ patterns; *Encyclopedia of Chart Patterns*) provides the most granular stats but is not peer-reviewed and is subject to selection/measurement choices. His own work ("Do Chart Patterns Still Work?") shows pattern reliability has *declined over the decades* and failure rates have risen (failures in 1991 were about a third of 2007 levels) — a direct warning about regime change and crowding.
- **Candlesticks:** Marshall, Young & Rose (2006, *Journal of Banking & Finance* 30(8):2303–2323), testing individual DJIA component stocks 1 Jan 1992–31 Dec 2002, concluded verbatim that "candlestick trading strategies do not have value for Dow Jones Industrial Average (DJIA) stocks. This is further evidence that this market is informationally efficient." Some markets/timeframes (Taiwan; certain 3-day reversal patterns via Caginalp-Laurent exits in Lu et al.) show edges, but the weight of rigorous evidence says candlesticks are weak standalone signals in liquid US equities. Treat as timing/context only.
- **Patterns with comparatively better Bulkowski data (up-breakouts, bull market):** high-and-tight flag (~22% 1-month gain but rare), Eve & Eve double bottom (~9%/12%/13% at 1/2/3 months), ascending/inverted scallops, falling wedge, rectangle bottom, flag. Bulkowski's cross-cutting findings: throwbacks hurt performance (97% of pattern types perform better post-breakout *without* a throwback); tall patterns and breakout-day gaps help; head-and-shoulders top is the best-performing down-breakout pattern.

---

## Entry logic (precise, computable composite examples)

These are *examples* of combining a trend filter + momentum + a trigger + volume confirmation — the pairing structure with the best evidence for reducing false signals (trend filter + oscillator/breakout). Express each as boolean conditions on daily closes; the user can weight components via the sub-scores.

**A. Trend-pullback long (highest evidence base — momentum + trend):**
```
LONG if:
  C > SMA(200)                      # long-term regime up
  AND EMA(20) > EMA(50)             # intermediate uptrend
  AND (C/C[-126] - 1) > 0           # 6-month momentum positive
  AND L[t] <= EMA(20) AND C[t] > EMA(20)   # pullback to rising 20-EMA, recaptured
  AND RSI(14) > 40 AND RSI(14) crossing up
  AND RVOL >= 1.0                   # not on collapsing volume
Entry trigger: buy next open, or stop-entry above H[t].
```

**B. Breakout-from-consolidation long (Donchian + squeeze + volume):**
```
LONG if:
  C > SMA(200) AND ADX(14) > 20
  AND BandWidth in bottom 20th percentile (last 126 bars)   # squeeze
  AND C[t] > max(H[t-1..t-20])      # 20-day high breakout
  AND RVOL >= 1.5                   # volume confirmation
Entry trigger: close above the 20-day high (avoid intrabar fakeouts).
```

**C. Mean-reversion long (range regime only — Connors-style):**
```
LONG if:
  C > SMA(200)                      # only buy dips in uptrending names
  AND SMA(20) slope ~flat (range)   # |SMA20[t]-SMA20[t-10]|/C < 1%
  AND RSI(2) < 10
Exit: C > SMA(5) (no hard stop in pure Connors version; see caveat).
```

**General entry discipline:** require the *close* to satisfy conditions (reduces intrabar whipsaw), and prefer stop-entry orders above the signal bar high for breakouts so you only get filled if momentum follows through.

---

## Exit/stop logic (emphasis on adaptive)

**Initial stop (choose one, all adaptive):**
- **ATR stop (preferred default):** `stop = entry - 2*ATR(14)` (use 2.5–3 for more volatile names). Adapts to instrument volatility automatically.
- **Swing/structure stop:** `stop = min(L[t-1..t-5]) - 0.1*ATR(14)` (just below the most recent swing low). Often tighter; pair with ATR to pick the wider/safer of the two for survival, or the tighter for better R:R.
- **Volatility-percent sanity check:** convert ATR distance to %; if `2*ATR/entry > 15%`, the name may be too volatile for a $500 account's diversification.

**Position sizing (percentage-based, account-adaptive — fixed fractional):**
```
risk_dollars = equity * risk_pct        # risk_pct = 0.5%–1.0% for a small/unproven account
stop_distance = entry - stop            # from ATR or structure
shares = floor(risk_dollars / stop_distance)   # use fractional shares if available
```
Dollar risk scales with equity, so as the $500 grows the size grows automatically and no rule is tied to a fixed dollar amount. Note that wider stops (higher volatility) automatically produce smaller positions — volatility dictates trade size, not capital risk. Start at 0.5–1% per trade while the system is unproven live; the 1–2% range is the common ceiling. Cap total open risk (e.g., ≤5% aggregate) and watch correlation (multiple longs in one sector ≈ one bigger trade). For tiny accounts, spread and slippage can consume a large share of planned risk — a structural reason to keep `risk_pct` low and trade only liquid names.

**Profit targets / trailing (adaptive):**
- **R-multiple targets:** define `R = entry - stop`. Take partial profit at +1R to +1.5R (e.g., sell half), move stop to breakeven, let the rest trail. R-multiple thinking is the most robust framework for consistency.
- **Chandelier exit (preferred trailing; LeBeau):** `long_stop = HighestHigh(22) - 3*ATR(22)`; trails up only. ATR-adaptive; beat fixed 5%/10% trailing stops on profit factor in published comparisons. Use 2–2.5× for tighter swing trails; raise the multiplier for more volatile (e.g., tech) names.
- **Moving-average trail:** exit on close below EMA(20) (tighter) or SMA(50) (looser) for trend rides.
- **Parabolic SAR trail:** mechanical acceleration trail for strong trends; whipsaws in ranges.
- **Resistance-target:** set target at the next significant prior swing high / AVWAP from a major high / measured-move projection of the pattern.
- **Time-based exit:** momentum decays after the holding window; for swing horizons, exit if the thesis hasn't worked in N bars (e.g., 10–20 trading days) and the trade is flat — frees capital and respects momentum's ~3-month front-loading.
- **Death-cross / structure exit** for longer holds: close on 50<200 cross or on a 10-day-low Donchian break.

**Partial profit-taking** is well-aligned with how these edges behave (momentum front-loaded, breakouts run): scale out to bank the high-probability portion, trail the remainder for the fat tail.

---

## Reliability notes (evidence grading & honest caveats)

**Tier 1 — Strongest evidence (use as primary drivers):**
- **Momentum / relative strength (3–12mo):** Jegadeesh-Titman 1.31%/mo (12/3 no lag) and 0.95%/mo (6/6); Moskowitz-Ooi-Pedersen time-series momentum across 58 instruments. Robust, replicated, but crowded and subject to occasional sharp crashes; reverses after ~12 months.
- **Trend filter (price vs long MA):** robust as a regime gate; BLL found large buy-sell spreads in-sample but STW showed out-of-sample decay — so use it to *filter*, not to time precisely.
- **ATR-based stops & volatility sizing:** strong, consistent evidence that adaptive beats fixed.

**Tier 2 — Moderate / regime-dependent:**
- Donchian/channel breakouts (trend-following families survived costs in several markets per Sobreira & Louro, stronger in emerging than US, profitability weak/decaying in advanced markets recently).
- Volume confirmation of breakouts (≥1.5× 20-day avg).
- Bollinger squeeze breakouts (positive expectancy, ~55–60% directional, asymmetric payoff); BB mean-reversion only in confirmed ranges.
- ADX>25 trend gate.
- MACD only when trend-filtered.

**Tier 3 — Weak / mixed / mostly anecdotal (confirmation only):**
- Candlestick patterns (Marshall et al.: no edge in liquid US/Japanese markets).
- Most classic chart patterns standalone (Lo-Mamaysky-Wang: some info, but profits-after-costs unproven; Bulkowski: reliability declining over decades).
- RSI/Stochastic overbought-oversold as standalone reversal signals (RSI(2) mean-reversion is the exception with concrete, though decaying, backtests).
- VWAP/AVWAP (practitioner evidence only).
- Parabolic SAR / single-line crossovers as standalone triggers.

**Failure modes & overfitting traps (these dominate live results):**
- **Data-snooping / multiple comparisons:** STW (1999) is the canonical warning — search 7,846 rules and the "best" one is likely luck; it failed out-of-sample. Use White's Reality Check / Hansen's SPA test or a Bonferroni-style penalty; reserve a true hold-out set; prefer rules motivated by a documented anomaly (momentum) over rules found by grid search.
- **Curve-fitting / over-optimization:** every parameter you tune (MA length, RSI threshold, ATR multiple) burns a degree of freedom. Prefer round, canonical parameters; test parameter *stability* (does 18/22 also work, not just 20?).
- **Look-ahead bias:** never use bar t's close to trade at bar t's open; signal on close, execute next bar. Don't use restated fundamentals or survivorship-cleaned universes.
- **Survivorship bias:** backtest on a point-in-time universe including delisted names; otherwise momentum/trend results are inflated.
- **Transaction costs, slippage, spread — the small-account killer:** Park & Irwin's review found that of 92 modern TA studies, 58 were positive but most are compromised by data-snooping and inadequate cost treatment; the COVID-meltdown study (MDPI 2022) found many rules profitable *before* costs but few survived after. For a $500 account, even commission-free, the bid-ask spread and slippage on illiquid names can equal or exceed your per-trade edge. Trade only liquid names (e.g., price > $5, dollar-volume > $20M/day), and model costs explicitly in backtests (assume you pay the spread + slippage).
- **Regime change:** edges decay as they get crowded (Bulkowski's rising failure rates; STW's out-of-sample reversal; "vanilla" RSI(2) decay). Monitor live performance against backtest and retire rules that break.
- **The backtest-to-live gap:** even valid backtests overstate live results due to costs, execution lag, psychology, and decay. Discount expectations; paper-trade first.

**Synthesis recommendation:** Build a *trend/momentum core* (Tier 1) gated by a regime filter, trigger with a breakout or pullback (Tier 2), confirm with volume, and manage exclusively with ATR-adaptive stops, sizing, and trailing. Use Tier 3 tools only to nudge a score, never to originate a trade.

---

## Summary table: signal → inputs → independent 0–100 sub-score

Sub-scores are designed to be computed **independently** (each is self-contained on the listed inputs) so you can mix/weight them yourself. Each maps a condition to a 0–100 contribution; 50 = neutral. Suggested logic given per row; tune to taste.

| # | Signal | Inputs needed (data/params) | Evidence tier | Computable 0–100 sub-score (independent) |
|---|--------|------------------------------|---------------|-------------------------------------------|
| 1 | Long-term trend filter | Daily close; SMA(200) | T1 | `100 if C>1.02*SMA200; 70 if C>SMA200; 30 if C<SMA200; 0 if C<0.98*SMA200` |
| 2 | Intermediate trend (stacked EMAs) | EMA(20), EMA(50) | T1/T2 | `100 if C>EMA20>EMA50; 60 if C>EMA50 only; 20 otherwise` |
| 3 | Time-series momentum (6mo) | Close 126d ago | T1 | `clip(50 + 1000*(C/C[-126]-1), 0,100)` (scaled 6-mo return) |
| 4 | Relative-strength rank | 126-day return of universe | T1 | `percentile_rank(126d_return) across universe → 0–100` |
| 5 | Pullback-to-EMA20 quality | EMA20, ATR(14), C, L | T1/T2 | `100 if (0<=(EMA20-L)/ATR14<=0.5 and C>EMA20); decay to 0 as gap grows` |
| 6 | Donchian 20-day breakout | 20-day high, close | T2 | `100 if C>20dHigh; 60 if within 1*ATR below; 0 if <prior 10d low` |
| 7 | Bollinger squeeze + breakout | SMA20, stdev20, BandWidth pctile | T2 | `100 if squeeze(BW<=20pct) AND C>upper; 60 if squeeze only; 50 neutral` |
| 8 | Bollinger mean-reversion (range only) | %B, SMA20 slope | T2 | `if range regime: 100 if %B<0; 75 if %B<0.1; else 50. If trending: 50 (disable)` |
| 9 | RSI(2) oversold (mean-rev) | RSI(2), SMA200 | T2/T3 | `if C>SMA200: 100 if RSI2<5; 85 if <10; 60 if <20; else 50` |
| 10 | RSI(14) momentum confirm | RSI(14) | T2/T3 | `clip((RSI14-30)*2, 0,100)` (higher RSI→higher, capped) |
| 11 | RSI/MACD bullish divergence | RSI(14) or MACD, swing lows | T3 | `75 if divergence present; 50 if none` (confirmation nudge only) |
| 12 | MACD trend-filtered cross | MACD(12,26,9), SMA50 | T2/T3 | `if C>SMA50: 100 on fresh bull cross; 70 if hist>0 & rising; else 40` |
| 13 | MACD histogram momentum | MACD histogram | T3 | `clip(50 + scale*Hist_slope, 0,100)` |
| 14 | ADX trend-strength gate | ADX(14), +DI/-DI | T2 | `100 if ADX>30 & +DI>-DI; 70 if ADX>25; 40 if ADX<20` |
| 15 | Relative volume confirm | Volume, SMA(Vol,20) | T2 | `clip(min(RVOL,3)/3*100, 0,100)`; gate breakouts at RVOL≥1.5 |
| 16 | OBV trend confirm | OBV, EMA(OBV,20) | T3 | `75 if OBV>EMA(OBV,20) & rising; 50 flat; 25 falling` |
| 17 | Anchored VWAP position | Price/volume from anchor bar | T3 | `80 if C>AVWAP (from last major low) & rising; 50 at; 20 below` |
| 18 | ATR volatility regime | ATR(14), ATR(14) 100d avg | T1 (risk) | `informational: ATR/price percentile → use for sizing, not direction` |
| 19 | Chart pattern (Bulkowski-graded) | OHLC pattern detection | T3 | `map pattern's historical 2-mo gain & (1−failure%) → 0–100; <50 if rare/declining` |
| 20 | Candlestick reversal | OHLC single/multi-bar | T3 | `60 if confirmed reversal at support in uptrend; else 50` (weak nudge) |
| 21 | Golden/death cross state | SMA50, SMA200 | T2 | `70 if 50>200; 30 if 50<200` (regime, low resolution) |
| 22 | Initial stop (ATR) | entry, ATR(14), k | T1 (risk) | not a score — outputs `stop=entry−k*ATR14` |
| 23 | Position size | equity, risk_pct, stop_distance | T1 (risk) | not a score — outputs `shares=equity*risk_pct/stop_distance` |
| 24 | Chandelier trailing exit | HighestHigh(22), ATR(22) | T1 (risk) | not a score — outputs `trail=HH22−3*ATR22` |
| 25 | Time-based exit | bars in trade, P&L | T2 (risk) | not a score — exit if flat after N bars |

**How to combine (your choice):** compute the directional sub-scores (rows 1–21), drop neutral-50 contributors, then take a weighted average with weights reflecting the evidence tiers (e.g., T1 ×3, T2 ×2, T3 ×1). Trade only when the composite exceeds a threshold you calibrate AND the regime gate (row 14) and trend filter (row 1) are satisfied. Rows 22–25 are risk modules applied to every trade regardless of score.

---

## Recommendations (staged, with benchmarks that change them)

**Stage 0 — Infrastructure (before any live trade):**
1. Choose a zero-commission broker with fractional shares. Restrict your universe to liquid names: `price > $5 AND 20-day median dollar-volume > $20M`. This single filter neutralizes the biggest small-account threat (spread/slippage).
2. Build a point-in-time backtester (include delisted tickers) that signals on close and executes next-bar open, and that charges a realistic cost = half-spread + 1–2 ticks slippage per side. Treat any strategy that's only profitable at zero cost as failed.

**Stage 1 — Validate the Tier-1 core (paper/tiny size):**
3. Implement just three modules: (a) regime filter `C>SMA200` + rising 50-SMA; (b) 6-month time-series momentum positive; (c) ATR(2× to 3×) stop with 0.5–1% fixed-fractional sizing and a Chandelier(22,3) trail. Add the trend-pullback entry (setup A). Trade this for ≥30–50 trades.
4. **Benchmark to advance:** live/paper profit factor > 1.3 *after modeled costs* and max drawdown < 20%. If you don't clear this, do **not** add complexity — the problem is usually costs or execution, not too few indicators.

**Stage 2 — Add selective Tier-2 confirmation:**
5. Layer in the breakout setup (B) with ADX>25 and RVOL≥1.5 volume confirmation, and the squeeze breakout. Keep RSI(2) mean-reversion (setup C) as a *separate* sub-strategy used only in flat-SMA20 regimes.
6. **Benchmark:** each added module must improve out-of-sample profit factor or reduce drawdown on a held-out period; otherwise cut it (guard against data-snooping).

**Stage 3 — Scale and maintain:**
7. As equity grows, fixed-fractional sizing scales automatically; only then consider raising `risk_pct` from 1% toward (but not above) 2%. Cap aggregate open risk at ~5% and treat same-sector longs as correlated.
8. **Ongoing kill-switches:** if a sub-strategy's rolling 30-trade profit factor falls below 1.0, or live results diverge from backtest by more than ~1 standard error for two consecutive quarters, retire or re-derive it (regime change/crowding).

**What would change these recommendations:** stronger evidence that a specific pattern survives costs out-of-sample would promote it from Tier 3; persistent post-cost underperformance of the momentum core (consistent with continued post-STW efficiency gains) would push you toward pure risk-management/position-trading or away from active TA entirely.

## Caveats

- **The literature is genuinely divided and cost-sensitive.** In-sample profitability (BLL 1992) repeatedly fails to survive out-of-sample correction for data-snooping (STW 1999) and transaction costs. Take every "win rate" — especially the 67–79% golden-cross and 52–73% MACD figures from practitioner blogs — as upper bounds under idealized, often single-asset or index, conditions, not what a $500 retail account nets on single stocks.
- **Source quality varies.** The strongest claims here rest on peer-reviewed work (Jegadeesh-Titman, Moskowitz-Ooi-Pedersen, Lo-Mamaysky-Wang, Brock et al., Sullivan et al., Marshall et al.). Many indicator win-rate statistics come from vendor/practitioner blogs (QuantifiedStrategies, StratBase, Option Samurai, Liberated Stock Trader) whose backtests are not independently verified, are often on forex/crypto/indices rather than US single stocks, and frequently omit full cost accounting — they are cited as directional/practitioner evidence, not proof.
- **Momentum reverses and crashes.** The very effect underpinning the Tier-1 core (Jegadeesh-Titman) dissipates after ~12 months and suffers periodic sharp drawdowns; time-series momentum performs best in extreme markets and can whipsaw in transitions.
- **Bulkowski's own data shows pattern reliability declining over decades** — a built-in warning that historical pattern statistics may overstate current edge.
- **None of this is investment advice.** It is an evidence-graded engineering specification. Validate every rule on your own point-in-time data with realistic costs before risking capital, and expect live results to fall short of backtests.