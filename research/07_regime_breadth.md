# Market-Gate Framework for a US Swing-Trading Signal System

## Overview

**Bottom line: For a few-days-to-one-month swing system in liquid US stocks, the single most important top-down decision is whether the broad market is in a confirmed uptrend with broad participation, calm-to-normal volatility, and low cross-stock correlation — and you should only deploy full size when all four pillars (regime, breadth, volatility, correlation) agree.** When they don't, the master gate should mechanically cut size or move you to cash, because swing setups that work in trends fail in chop, and single-name edges evaporate when correlations spike.

This report builds a four-pillar "master market-gate" that overrides individual stock signals:
1. **Regime** — are the major indices (SPX, QQQ, IWM) trending up, down, or chopping?
2. **Breadth** — are most stocks participating, or is leadership narrow?
3. **Volatility** — is the VIX calm, elevated, or in panic; is the term structure normal or stressed?
4. **Correlation** — are stocks moving independently (good for stock-picking) or in lockstep (risk-on/risk-off)?

The gate produces a **GREEN / YELLOW / RED** state plus a **0–100 multiplier** that scales position size and trade frequency. The framework is designed to be computed by hand or in a spreadsheet from mostly free data (StockCharts symbols, FRED, Yahoo Finance, CBOE), and is S&P/NYSE-centric to match liquid large/mid-cap stocks.

A foundational caveat applies throughout: market-timing overlays are widely shown to reduce returns if used clumsily, and the academic literature (e.g., Guy Metcalfe, "The Mathematics of Market Timing," 2018) shows that naive timing is more likely to lose than win before costs. The purpose of this gate is **risk management and survival of a small, scaling account**, not return maximization. It should reduce drawdowns and keep you solvent through bad regimes so you can compound in good ones.

---

## Regime detection (uptrend / downtrend / chop)

### Core moving-average framework
The backbone of regime detection is the relationship of price to the 20-, 50-, and 200-day simple moving averages (DMAs) on SPX (S&P 500), QQQ (Nasdaq 100), and IWM (Russell 2000).

- **Stacked bullish ("MA stack"):** price > 20-DMA > 50-DMA > 200-DMA, with the 50- and 200-DMA both rising. This is the textbook confirmed uptrend (what Mark Minervini and others call a "Stage 2 uptrend").
- **Stacked bearish:** price < 20-DMA < 50-DMA < 200-DMA, both longer MAs falling — confirmed downtrend.
- **The 200-DMA is the master trend filter.** A simple, robust rule used by many systematic traders: only take longs when the index is above its 200-DMA. Backtests (QuantifiedStrategies) show the 200-DMA reduces max drawdown about as well as more complex signals.

### Golden cross / death cross and their real reliability
A **golden cross** is the 50-DMA crossing above the 200-DMA; a **death cross** is the reverse. These are slow, headline-grabbing signals — on the S&P 500 they occur roughly once every 2–3 years.

The evidence on reliability is nuanced, and you should not treat either as a standalone trade trigger:
- **Golden cross is the more useful of the two.** Per Dow Jones Market Data (reported by MarketWatch, July 1, 2025), after a golden cross the S&P 500 was higher one year later more than 71% of the time, with an average one-year return of more than 10% — versus an ~8% average for any 12-month period since 1928. Following death crosses the average 12-month return has been much weaker (roughly 3.5% in some datasets).
- **Death cross is a poor sell signal.** Rob Hanna of Quantifiable Edges, using Norgate data back to 1928, found that "36 of the 49 instances (73.5%) actually saw the SPX realize gains while the Death Cross was in effect," with an average drawdown of 13.2% per trade — but the few large losers (1929–1933, 2008) were devastating, and a portfolio invested only during death crosses never returned to breakeven over 97 years. The death cross marked bottoms, not tops, in March 2020 and 2015–2016.
- **Practical use:** treat the golden cross as bullish confirmation and the death cross as a risk-management prompt (reduce size, tighten stops, demand higher setup quality) rather than an automatic exit. Studies suggest the death cross correctly identifies sustained downtrends only about 60% of the time, improved by adding breadth/volume confirmation.

A faster variant useful for swing timeframes: the **20/50 DMA cross** while price is above the 200-DMA gives earlier entries while respecting the larger trend.

### Distinguishing trend from chop
This is the crucial regime question for a swing trader, because the same momentum setup that wins in a trend gets chopped to pieces in a range.

**ADX (Average Directional Index, Wilder, 14-period default):**
- ADX **< 20** = weak/absent trend → choppy, range-bound. Trend-following and breakout setups fail; mean-reversion is favored.
- ADX **> 25** = trend present and tradeable (the standard swing-trading threshold).
- ADX **> 40** = strong trend.
- For swing trading on daily charts, practitioners use the standard 14-period ADX with a 25 threshold for trend confirmation and 50 for strong trends. ADX measures trend strength, not direction — pair with +DI/–DI or price/MA structure for direction.

**Choppiness Index (CHOP, E.W. Dreiss, 14-period, scale 0–100, Fibonacci bands):**
- CHOP **> 61.8** = choppy/consolidating market → avoid directional trend trades, favor range strategies or stand aside.
- CHOP **< 38.2** = strong trend (either direction) → trend/breakout setups favored.
- Between 38.2 and 61.8 = transition; reduce size or wait for clarity.
- CHOP is non-directional; combine with a directional tool. Formula: `100 * LOG10(SUM(ATR(1), n) / (MaxHi(n) − MinLo(n))) / LOG10(n)`.

**Other practical chop tests:**
- **Distance/spread between MAs:** when the 20-, 50-, and 200-DMA are tightly bunched and intertwined, the market is range-bound; when they fan out and stack in order with positive slope, a trend is established.
- **MA slope:** a flat or oscillating 50-DMA signals chop; a steadily rising/falling 50-DMA signals trend.
- **Percent of days closing in a tight range** or repeated failed breakouts also flag chop.

### Why swing trading works in trends and fails in chop
Swing strategies are predominantly momentum/breakout-based: buy strength expecting continuation over days to weeks. In a **trend**, breakouts follow through and pullbacks resume in the trend's direction — momentum has positive expectancy. In **chop**, breakouts fail (false breakouts stop you out), prices mean-revert to a balance point, and momentum traders "suffer repeated small losses in non-trending phases" (Hedged). Mean-reversion strategies have the opposite profile — they win in ranges (win rates often 60–70%) and get run over in strong trends. The regime determines which tool has an edge; the master gate's job is to keep you trading momentum only when the regime supports it.

**Concrete regime rules (SPX as primary, QQQ/IWM as confirmation):**
- **Uptrend (full risk-on):** SPX above rising 200-DMA AND above 50-DMA; 50 > 200; ADX > 20–25; CHOP < ~50.
- **Chop (reduce):** SPX oscillating around a flattish 50-DMA; ADX < 20; CHOP > 61.8.
- **Downtrend (risk-off):** SPX below falling 200-DMA and 50-DMA; no new longs.

---

## Breadth indicators

Breadth measures how many stocks are participating, independent of the cap-weighted index level. Because the S&P 500 and Nasdaq are cap-weighted, a handful of mega-caps can hold the index up while most stocks weaken — breadth exposes this.

### Percent of stocks above moving averages
The most directly actionable breadth tool for a swing trader.
- **Above 200-DMA** (StockCharts: `$SPXA200R` for S&P 500, `$NYA200R` for NYSE, `$NDXA200R` for Nasdaq 100; Barchart `$MMTH` for NYSE): the share of stocks in long-term uptrends.
  - **> 60–70% = broadly bullish/healthy participation.** (StockCharts' Arthur Hill flagged `$SPXA200R` hitting 70% in late August 2025 as the year's strongest breadth.)
  - **30–70% = neutral/mixed.**
  - **< 30% = market weakness; < 20% = washed-out/oversold, often near major bottoms.** Readings above ~89–92% (since 2000, seen only in 2002, 2009, 2021) mark rare, overbought extremes that historically reverted.
- **Above 50-DMA** (`$SPXA50R`, `$NYA50R`): a faster, more volatile medium-term gauge, better for overbought/oversold. Crosses 50% far more often (more whipsaw); StockCharts recommends smoothing with a 20-day MA. Used for tactical exposure: e.g., > 60% maintain full long exposure, 40–60% reduce to half, < 40% exit/cash; < 20% = oversold (wait for turn-up before buying).
- The 50% threshold works best on the longer (150-/200-day) versions; the 50-day version is best for overbought/oversold extremes.

### Advance-decline line (NYSE A-D line, `$NYAD`)
The cumulative running total of daily (advancers − decliners). It confirms or diverges from the index:
- **Confirmation:** A-D line making new highs with the index = healthy, broad rally.
- **Bearish divergence:** index makes a new high but the A-D line makes a lower high = narrowing participation, classic late-stage topping warning. The A-D line diverged before the 2000 dot-com top and ahead of the 2008 crisis (per Corporate Finance Institute, cited by Britannica Money).
- **Bullish divergence:** index makes a lower low but A-D line makes a higher low = sellers exhausting, possible bottom.
- Note: the A-D line gives equal weight to all issues and can swing sharply day-to-day, so weigh it over longer periods and confirm with other tools.

### New highs vs new lows and the Hindenburg Omen
NYSE/Nasdaq 52-week new highs minus new lows (`$NYHL`, `$NYHGH`, `$NYLOW`) gauges leadership health. In a healthy market, expansion is one-sided (many new highs OR many new lows, not both).

The **Hindenburg Omen** (Jim Miekka, building on Norman Fosback's High-Low Logic Index) flags a "split market" where both new highs and new lows are simultaneously elevated. Commonly cited criteria, all on the same day:
1. NYSE Composite/S&P 500 above its 50-DMA (uptrend / positive 50-day rate-of-change).
2. Both new 52-week highs AND new lows each exceed ~2.8% of NYSE issues (some sources use 2.2%).
3. The McClellan Oscillator is negative.
A single signal is unreliable (significant declines follow only ~20–25% of the time, per SentimenTrader/StockCharts), but **clusters** of signals within ~30 days are the meaningful warning — clusters preceded 1987, 2000, 2008, and the 2020 decline. StockCharts symbol: `!BINYHOD`. The signal is invalidated once the McClellan Oscillator returns above zero. Use it as a yellow-flag risk reducer, never a standalone short trigger.

### McClellan Oscillator and Summation Index
Developed by Sherman and Marian McClellan; think of the Oscillator as the "MACD of the A-D line."
- **McClellan Oscillator** (`$NYMO`) = 19-day EMA − 39-day EMA of (ratio-adjusted) net advances. Positive = bullish breadth momentum; negative = bearish. Readings beyond roughly ±50 to ±100 mark short-term extremes; it's an input to the Hindenburg Omen.
- **McClellan Summation Index** (`$NYSI`) = running cumulative total of the Oscillator; the intermediate/long-term breadth trend. Above zero = bullish, below zero = bearish. The McClellans note it is calibrated to be neutral at +1000 and generally moves between 0 and +2000. Per McClellan and Greg Morris's framework, prolonged downtrends typically end with the Summation Index below about −1200 to −1300; major tops form above about +1600; and a strong rise crossing above +1900 after gaining ~3600 points from a low has historically launched durable bull moves (averaging 13+ months, with the typical run lasting 22–24 months).

### Breadth thrusts (Zweig Breadth Thrust)
A powerful bullish initiation signal from Martin Zweig. The ZBT = 10-day EMA of NYSE advances / (advances + declines). A buy signal fires when this ratio surges from **below 0.40 to above 0.615 within 10 trading days** — a stampede from washed-out to broad participation. Historically these signals have preceded strong intermediate-to-long-term advances; research cited on TradingView (Bulkowski; Kirkpatrick & Dahlquist) found classic ZBT signals preceded market advances ~83% of the time since 1950, with average gains of ~22–25% over the following 11–12 months, though true signals are rare. StockCharts symbols `!BINYBT` / digital `!BINYBTD`. A fired ZBT is a strong reason to flip the gate to GREEN even if longer MAs haven't fully reset.

### What breadth divergences warn about
Narrow leadership (index up, breadth down) signals fragility: fewer stocks carrying the market, rising odds of a choppy pause or correction. For a swing trader this means **fewer healthy setups and lower follow-through** — a reason to tighten the gate even when the headline index looks strong.

---

## Volatility regime

### VIX absolute levels (consensus bands)
The VIX (`^VIX`; FRED `VIXCLS`, history to 1990) is 30-day implied volatility of the S&P 500 from SPX option prices. Consensus interpretation bands across J.P. Morgan/Chase, Questrade, and others:
- **< 15: low/calm** — complacency, stable bull conditions.
- **15–20: normal/baseline** — modest uncertainty.
- **20–25: rising concern**, more pronounced swings.
- **25–30: heightened fear**, headline-driven trading.
- **> 30: high fear** — corrections/downturns; "extreme uncertainty."
- **> 40: panic/crisis.**
- **> 50: extreme distress / capitulation zone** — paradoxically often near bottoms.

Reference spikes (per Macroption's VIX records): the intraday all-time high was **89.53 on Oct 24, 2008**; the **record close of 80.86 on Nov 20, 2008** stood until March 16, 2020, when VIX closed at **82.69** (reaching 83.56 intraday); the August 5, 2024 yen-carry unwind printed a **65.73 intraday high** (closing 38.56); and the highest close outside 2008–09 and March 2020 was **52.33 on April 8, 2025**. The long-run average is around 19–20.

**Key nuance:** VIX measures expected magnitude, not direction; it can stay elevated or depressed far longer than expected, so it is not a precise timing tool. A low VIX is not always "safe" — it can reflect suppressed/sold volatility (watch VVIX) that snaps higher.

### VIX term structure: contango vs backwardation
Compare spot VIX to 3-month VIX (`^VIX3M`, formerly VXV; FRED `VXVCLS`). The ratio **VIX/VIX3M** captures the curve shape:
- **VIX/VIX3M < 1.0 = contango** (near-term < longer-term): normal, calm regime. The curve is in contango roughly 80–85% of the time (CBOE: >80% of days since 2010; Eco3min: contango ~85% of 1990–2025 trading days).
- **VIX/VIX3M > 1.0 = backwardation** (near-term > longer-term): acute near-term stress — flash crashes, geopolitical shocks, crises. Backwardation is rare (~15–20% of days) but has preceded essentially all major drawdowns. It's a fast, leading risk-regime signal that often flips before slower macro indicators.
- Practical reading: persistent healthy contango supports a constructive risk score; flattening or sustained backwardation should cut the gate's volatility score. Deep backwardation (ratio > ~1.10) marks panic/dislocation — best opportunities to re-enter come after the ratio "hooks" and starts mean-reverting, not while it is still spiking.

### Volatility and position sizing (inverse-vol / vol targeting)
A core risk-management principle: scale exposure inversely to volatility so dollar risk stays roughly constant.
- **ATR-based sizing:** Position size = (Account equity × risk %) ÷ (ATR × multiplier), typically a 14-period ATR with a 1.5–3.0× multiplier. When ATR rises, size falls automatically.
- **Volatility targeting (VT):** set a target portfolio volatility and scale positions up when realized vol is low, down when high. Trend-following research (Concretum Group) shows VT produces smoother equity curves and higher hit ratios than fixed sizing, at the cost of some upside.
- **At the gate level:** use the VIX regime to set a portfolio-wide exposure cap (e.g., full size when VIX < 20, half when 20–30, minimal/none when > 30), layered on top of per-trade ATR sizing. Caveat (Alvarez Quant Trading): inverse-vol sizing can over-size apparently "low-vol" names that then gap, so cap single-name size regardless.

### Stand aside vs. buy-the-capitulation
Elevated volatility cuts two ways:
- **Mid-range elevated VIX (20–35) in a downtrend = stand aside.** This is the dangerous "grinding lower / whipsaw" zone where swing longs get chopped.
- **Extreme VIX spikes (> 35–40, ideally > 50) = potential capitulation buy zone.** The signal is not the VIX peak itself but the **roll-over** — VIX making a fresh high while the S&P makes a higher low (bullish divergence), then VIX falling back below ~30. Confirm capitulation with: volume 2–5× the 20-day average, a wide-range reversal candle closing near its high (long lower wick), and extreme sentiment (AAII bears > 50%, equity put/call > 1.2–1.5). VIX has closed above 50 only a handful of times in two decades, each near a cyclical low (2008, 2020, April 2025) — but extremes can persist (2008 had multiple capitulation points before the March 2009 bottom, and the March 2020 ~82 close preceded a 100%+ 12-month rally), so size for ambiguity and use stops below the capitulation low.

### Realized vs implied volatility
Implied (VIX) is the market's forward expectation; realized (historical) is what actually happened. Implied typically exceeds subsequent realized (the variance risk premium). When implied >> realized, fear is elevated relative to actual movement (often a fade/contrarian setup); when realized > implied, the market is under-pricing the turbulence it is actually experiencing.

---

## Correlation

### The concept and why it matters for stock-picking
Average pairwise correlation measures how much individual stocks move together versus independently. **When correlations spike toward 1, single-name selection stops adding value — everything moves with the index in a risk-on/risk-off fashion, and stock-picking "becomes irrelevant"** (ON the Market / Patricia Ji). For a discretionary swing trader whose edge is picking the right stocks, a correlation spike is a direct threat: your careful setup selection gets overwhelmed by the macro tide. Low correlation = a "stock picker's market" with more dispersion and more idiosyncratic opportunity.

### CBOE Implied Correlation Index — and a critical scaling caveat
The CBOE Implied Correlation Index measures the market's expectation of average correlation among the top 50 value-weighted S&P 500 stocks, derived from index vs. single-stock option implied volatilities (no pricing model; uses delta-relative implied vols). Per CBOE's official methodology: "Positive correlation spikes indicate lower expected diversification benefits, increased systematic risk, and a higher likelihood of experiencing extreme tail events associated with sudden market movements."

**There are two generations of this index on different scales — do not compare them directly:**
- **Legacy index (KCJ/ICJ/JCJ, 2007–~2021):** quoted ~0–100+. Calm readings ~20–50, crisis readings 70–90+. Per CBOE's methodology document: "The highest closing index level of 105.93 occurred on November 20, 2008 for KCJ with a maturity of January 2009. On this day, the CBOE Volatility Index (VIX) reached its record high close of 80.86."
- **Current index (COR1M `^COR1M`, COR3M `^COR3M`, plus COR6M/COR1Y, launched July 2021, new proprietary methodology):** trades at much lower absolute numbers. As of the May 29, 2026 close (Yahoo Finance delayed quotes): **COR3M ≈ 8.60, COR1M ≈ 6.33, COR1Y ≈ 13.57**, with the companion **DSPX ≈ 42.01**. In 2022's bear market COR1M rose from ~13 to over 50; in the March 2025 risk-off it jumped ~17% to 24.33; its trailing-year range has spanned roughly 1 to 59. Readings below ~10 on short-term implied correlation have recently been treated as a contrarian warning (crowded dispersion trades, VIX vulnerable to spikes).

The companion **CBOE S&P 500 Dispersion Index (DSPX `^DSPX`, launched September 2023)** measures expected 30-day dispersion (VIX-style). High DSPX + low implied correlation = the classic "calm index / lively constituents" stock-picker's regime; the spread tends to spike around earnings season (January, April, July, October).

### Realized pairwise correlation: the numbers
Realized average pairwise correlation among S&P 500 stocks:
- **Baseline/normal: ~0.20–0.35** (S&P DJI dispersion dashboards show recent monthly readings ~0.20–0.30; an extreme-calm low of ~0.16 was hit in early 2021, per Bloomberg).
- **Crisis spike: ~0.70–0.85.** In 2020 the gauge began the year at 0.19 and spiked to 0.85 in mid-March at the COVID-selloff peak, leveling off around 0.8 — the highest in about eight years (Bloomberg, cited in the Journal of Banking & Finance). In 2008, asset-class correlations approached 1.0 ("everything fell together"); academic/practitioner sources note equity correlations jumped from ~0.35 to over 0.80 in 2008.
- Implied correlation tends to run above subsequent realized correlation — the **correlation risk premium**, estimated at ~18 points in Driessen, Maenhout & Vilkov (1996–2003 data) and ~6.7–8.9 points in Faria, Kosowski & Wang (2021, 91-day options).

### Detecting correlation regime changes and what to do
- **Track** `^COR3M`/`^COR1M` (CBOE/Yahoo) and/or compute a rolling 1-month average pairwise correlation of your watchlist, or proxy it via sector-ETF dispersion.
- **Rising/high correlation → reduce single-name exposure.** When correlation spikes, (a) cut the number of concurrent positions (they're really one bet), (b) reduce total size, or (c) express the view through the index (SPY/QQQ) instead of single names, since stock selection adds little. Crucially, high correlation usually coincides with market stress/drawdowns, so it reinforces the volatility and regime pillars.
- **Falling/low correlation in an uptrend → favorable for stock-picking,** the best environment for a discretionary swing book — but watch for extreme lows as a contrarian caution.
- **Portfolio rule of thumb:** practitioners commonly keep average pairwise correlation across core holdings below ~0.7 and weight-adjust pairs above ~0.8; for aggressive accounts some cap any single pair at 0.6.

---

## How to compute a master market-gate (green/yellow/red + 0–100 multiplier)

The gate aggregates the four pillars into one score that **overrides** individual stock signals. The design philosophy mirrors published composite models (e.g., Arthur Hill / TrendInvestorPro's Composite Breadth Model and The Trade Risk's green/yellow/red breadth cycles), which combine the A-D line, new highs/lows, and percent-above-MA into a single color-coded regime read.

### Step 1 — Score each pillar 0–25 (100 total)

**A. Regime (0–25):**
- SPX > rising 200-DMA: +8
- SPX > 50-DMA and 50 > 200 (bullish stack): +6
- QQQ and IWM also above their 200-DMA (confirmation): +4
- ADX(14) > 25 with price/MA pointing up (trend, not chop): +4
- CHOP(14) < 50: +3
- (Subtract heavily if SPX < falling 200-DMA → near 0.)

**B. Breadth (0–25):**
- % above 200-DMA (`$SPXA200R`) > 60%: +8 (40–60%: +4; <40%: 0; <20% washed-out: treat as oversold flag for the volatility pillar)
- % above 50-DMA (`$SPXA50R`) > 50%: +5
- NYSE A-D line confirming (no bearish divergence): +5
- McClellan Summation Index (`$NYSI`) > 0 and rising: +4
- No active Hindenburg Omen cluster: +3 (active cluster → 0 and force at most YELLOW)
- (A fired Zweig Breadth Thrust overrides to full breadth score and biases the gate to GREEN.)

**C. Volatility (0–25):**
- VIX < 15: +10; 15–20: +8; 20–25: +5; 25–30: +2; >30: 0; >40: 0 (but arm capitulation watch)
- VIX/VIX3M < 0.95 (healthy contango): +10; 0.95–1.0: +5; >1.0 (backwardation): 0
- VIX falling over last 5 days (not spiking): +5

**D. Correlation (0–25):**
- Implied correlation (COR3M/COR1M) in low-to-normal range / not spiking (judge against its own recent range/percentile): +12
- Realized pairwise correlation of watchlist < ~0.5: +8
- Correlation falling or stable (not rising sharply): +5
- (Correlation spiking toward crisis levels → near 0.)

### Step 2 — Map total score to GREEN / YELLOW / RED + multiplier

| Total score | State | Multiplier | Action |
|---|---|---|---|
| **70–100** | 🟢 GREEN | **80–100%** | Full size, full trade frequency, all qualified long setups |
| **40–69** | 🟡 YELLOW | **30–60%** | Half size or less, only A+ setups, fewer concurrent positions, tighter stops |
| **0–39** | 🔴 RED | **0–20%** | No new longs regardless of setup quality; manage/close existing; mostly cash; consider index hedges or capitulation-buy watch only |

The multiplier scales roughly linearly within bands (e.g., score 85 → ~90% size; score 50 → ~45% size). Use it to set both **per-trade size** (multiply your normal risk % by the multiplier) and **max concurrent positions**.

### Step 3 — Hard overrides (these beat the score)
- **RED trumps everything:** if SPX is below a falling 200-DMA **or** VIX/VIX3M is in sustained backwardation **or** implied correlation is spiking to crisis levels → **no new longs**, regardless of how good an individual stock looks. This is the core "gate overrides signal" rule.
- **Hindenburg Omen cluster** or A-D bearish divergence → cap at YELLOW even if the score is high (narrow, fragile rally).
- **Capitulation exception:** in RED with VIX > ~40 and rolling over, plus capitulation confirmation (volume 2–5× average, reversal candle, AAII bears > 50%), you may take small starter longs in leaders — but at minimum size, with stops under the capitulation low.
- **Zweig Breadth Thrust fired** → GREEN bias for the following weeks.

### Practical implementation notes (small, scaling, manual account)
- **Compute once daily after the close** (most breadth symbols are end-of-day). A 10–15 minute checklist: pull SPX/QQQ/IWM MA status, `$SPXA200R`/`$SPXA50R`, `$NYAD`, `$NYSI`/`$NYMO`, `^VIX` + `^VIX3M`, `^COR3M`. Record the four sub-scores and total in a spreadsheet; chart the gate state over time.
- **Smooth the signal** to avoid whipsaw: require the state to hold for 2 consecutive closes before acting, or use a 3–5 day average of the total score. (StockCharts notes the 50-DMA breadth version especially whipsaws; smoothing with a 20-day MA helps.)
- **As the account scales:** the framework is size-agnostic — the multiplier governs the fraction of your normal risk budget deployed, so the same gate works from a four-figure to six-figure account. At larger sizes the correlation pillar matters more (you'll hold more names), so lean harder on reducing concurrent positions when correlation rises.
- **Keep the override discipline absolute.** The entire value of the gate is that it stops you from taking great-looking setups in bad regimes — which is exactly when discretion tends to fail. Pre-commit to "RED = no new longs" in writing.
- **Backtest/forward-test the weights on your own setups.** The point allocations above are a sensible starting template, not optimized values; practitioners (Alvarez, Enlightened Stock Trading) stress that you should test thresholds against your actual strategy rather than assuming fixed levels.

---

## Summary table of data sources

| Indicator | Specific ticker / series | Best source(s) | Free / paid | API? | Notes |
|---|---|---|---|---|---|
| S&P 500 / Nasdaq / Russell price + MAs | `$SPX`/SPY, QQQ, IWM | Yahoo Finance, StockCharts, TradingView, Stooq | Free | Yahoo (unofficial); Tiingo/Polygon/Alpha Vantage (official) | Compute 20/50/200-DMA, golden/death cross yourself |
| ADX, Choppiness Index | n/a (computed) | TradingView, StockCharts, thinkorswim | Free (charting) | Alpha Vantage has ADX endpoint | 14-period standard for swing |
| % above 200-DMA | `$SPXA200R`, `$NYA200R`, `$NDXA200R`; Barchart `$MMTH` (NYSE) | StockCharts, Barchart | Free to view; StockCharts sub for real-time | No public API | EOD; the key breadth gauge |
| % above 50-DMA | `$SPXA50R`, `$NYA50R`, `$NDXA50R` | StockCharts, Barchart | Free to view | No | Faster, more whipsaw |
| NYSE Advance-Decline line | `$NYAD` (issues), `$NYADV`/`$NYDEC` | StockCharts, Barchart, thinkorswim | Free to view | No | Intraday since 1992 on StockCharts |
| New highs / new lows | `$NYHL`, `$NYHGH`, `$NYLOW`; `$NAHL` (Nasdaq) | StockCharts | Free to view | No | Inputs to Hindenburg Omen |
| McClellan Oscillator | `$NYMO` (ratio-adj), `$NAMO`; `$NYMOT` unadj | StockCharts, mcoscillator.com | Free to view; McClellan sub for data | No | 19/39-day EMA of net advances |
| McClellan Summation Index | `$NYSI`, `$NASI` | StockCharts, mcoscillator.com | Free to view | No | >0 bullish; bottoms < −1200 |
| Zweig Breadth Thrust | `!BINYBT` (+ digital `!BINYBTD`) | StockCharts | StockCharts sub | No | Buy: <0.40→>0.615 in 10 days |
| Hindenburg Omen | `!BINYHOD` | StockCharts | StockCharts sub | No | Watch clusters, not singles |
| VIX (implied vol) | `^VIX`; FRED `VIXCLS` | FRED (free, full history to 1990), Yahoo, CBOE | Free | FRED API (free key); Yahoo | EOD on FRED; intraday on CBOE/Yahoo |
| VIX 3-month | `^VIX3M`; FRED `VXVCLS` | FRED, Yahoo, CBOE | Free | FRED API | Compute VIX/VIX3M ratio for term structure |
| Implied correlation | `^COR1M`, `^COR3M`, `^COR1Y` (current); legacy KCJ/ICJ/JCJ | CBOE (official, EOD), Yahoo Finance | Free | CBOE Global Indices Feed (paid real-time) | New methodology since 2021 — low absolute numbers |
| Dispersion index | `^DSPX` | CBOE, Yahoo | Free | CBOE feed (paid) | Launched Sept 2023 |
| Realized correlation / dispersion | S&P 500 realized correlation | S&P DJI Dispersion/Volatility/Correlation Dashboard | Free (reports) | No | Baseline ~0.2–0.3; crisis ~0.8 |
| Economic / macro context | VIX, 10-yr yield `DGS10`, credit spreads | FRED | Free | FRED API (free) | Good for credit-stress overlay |
| Backtesting / EOD history | full US equity history | Norgate Data, Tiingo, EODHD, Polygon | Paid (Tiingo cheap; Norgate for AmiBroker) | Yes | Polygon free = 1-yr history; Alpha Vantage free = 25 calls/day; Finnhub free = 60 calls/min (20-min delayed) |
| General charting / screening | all of the above | TradingView, Finviz, StockCharts, Barchart | Freemium | TradingView (no official data API) | Finviz good for breadth/heatmaps |

**Data-source guidance for a small account:** Start free — **FRED** (VIX, VIX3M, yields; free API key) + **Yahoo Finance** (indices, `^COR3M`, `^DSPX`) + **StockCharts free charts** (all `$`-prefixed breadth symbols) cover ~90% of the gate. If you want programmatic/automated computation, **Tiingo** (cheap, clean EOD) or **Polygon** (paid tiers) are the best-value APIs; **Alpha Vantage**'s free tier (25 calls/day) is too thin for production but fine for prototyping. For full historical backtesting of the gate's weights, **Norgate Data** (with AmiBroker) is the practitioner standard. Real-time intraday breadth/McClellan/Zweig/Hindenburg data requires a **StockCharts** subscription.

---

## Recommendations

**Stage 1 — Build the minimum viable gate (week 1).** Implement the Regime and Volatility pillars only, using free data: SPX 50/200-DMA status + slope, ADX(14), `^VIX`, and the `^VIX`÷`^VIX3M` ratio. Rule: trade full size only when SPX > rising 200-DMA, VIX < 20, and VIX/VIX3M < 1.0; go to cash when SPX < falling 200-DMA or the term structure inverts. This alone captures most of the drawdown-avoidance benefit.

**Stage 2 — Add Breadth (weeks 2–4).** Layer in `$SPXA200R` (>60% bullish / <30% weak), the `$NYAD` A-D line for divergence checks, and `$NYSI` (>0 bullish). Start logging the Hindenburg Omen (`!BINYHOD`) and Zweig Breadth Thrust (`!BINYBT`) as flags. Begin recording the full 0–100 score daily even before you trade it, to build a feel.

**Stage 3 — Add Correlation and go live with the multiplier (month 2+).** Track `^COR3M`/`^COR1M` against their own recent range and compute a rolling pairwise correlation of your watchlist. Switch position sizing to the GREEN/YELLOW/RED multiplier, with the hard overrides enforced.

**Stage 4 — Validate and tune (ongoing).** Tag every trade with the gate state at entry and review win rate, average R, and drawdown by state. You should see materially better expectancy in GREEN than YELLOW, and losses concentrated in trades taken against the gate.

**Benchmarks/thresholds that should change your behavior:**
- **Flip to RED / cash:** SPX closes below a falling 200-DMA; or VIX/VIX3M > 1.0 for 2+ days; or implied correlation spikes sharply toward crisis levels; or a Hindenburg Omen cluster with VIX rising.
- **Flip to GREEN / full size:** SPX reclaims a rising 200-DMA with `$SPXA200R` > 60%, VIX < 20 in contango, and correlation low/falling; or a confirmed Zweig Breadth Thrust.
- **Arm the capitulation-buy exception only when** VIX > 40 and rolling over with volume 2–5× average and AAII bears > 50% — and even then, minimum size with a stop under the low.

---

## Caveats and limitations

- **Timing overlays can hurt returns if mishandled.** The academic evidence (Metcalfe 2018) is that naive market timing more often loses than wins before costs. This gate is for **drawdown control and account survival**, not alpha; expect it to give up some upside in exchange for smaller losses and steadier compounding.
- **Lagging signals.** Golden/death crosses, the 200-DMA, and the Summation Index are lagging by construction — they confirm regimes already underway and will be late at turns. Faster pillars (VIX term structure, McClellan Oscillator, breadth thrust) partly offset this.
- **False signals and whipsaw,** especially from the 50-DMA breadth measure, single Hindenburg Omens (~20–25% hit rate), and the death cross (which marked bottoms in 2020 and 2015–16). Require confirmation and smoothing.
- **Correlation index scaling trap.** The current COR1M/COR3M trade at far lower absolute numbers than the legacy KCJ/ICJ (which hit 105.93 in 2008) — judge them by their own recent range/percentile, not by the old "70–90 = crisis" rule.
- **Thresholds are templates, not laws.** The exact point weights and band cutoffs should be tuned to your own setups and risk tolerance via testing; different assets and regimes warrant different levels.
- **Data timeliness.** Most breadth symbols are end-of-day; build the gate as an after-close daily routine. Free APIs have meaningful limits (Polygon free = 1-year history; Alpha Vantage free = 25 calls/day; Yahoo is unofficial and can break).
- **The gate informs whether and how much to trade, not what to buy.** It sits on top of — and overrides — your individual stock signal engine; it does not replace setup selection, stops, or per-trade risk management.