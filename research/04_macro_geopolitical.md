# Macro & Top-Down Factors for Swing Trading US Stocks: A Signal-Gating Framework

## Overview

This report translates macro/top-down conditions into mechanical, daily-trackable rules and a quantifiable 0–100 "risk-on/risk-off" modifier for gating individual US stock swing signals (holds of a few days to one month). The central thesis: on a swing timeframe, the **surprise** relative to consensus — not the absolute number — drives equity reactions; effects from scheduled data are largest in the first 30–90 minutes and typically persist a few days to two weeks; and a small set of publicly free indicators (VIX, 2s10s, HY OAS, DXY, breadth, put/call) can be standardized into a single composite that scales position size and tightens setup requirements. Use the macro layer as a **gate and a position-size multiplier**, not a primary entry signal: it answers "how aggressive should I be right now" rather than "what should I buy."

Key mechanical principles:
- Markets price the *expected* outcome in advance; only the actual-minus-consensus gap moves price. Track consensus on an economic calendar.
- Scheduled-release reactions are front-loaded (first 30–90 min) and usually resolved within days to ~2 weeks; FOMC effects are the largest and most durable.
- Regime matters: the same indicator (e.g., falling yields) is bullish or bearish depending on *why* it is moving.
- Geopolitical shocks are usually shallow and fast-recovering (−4.7% total average drawdown, bottoming in 19 days and fully recovering in 42 days, per LPL Research) unless they trigger an oil/inflation/recession chain.

---

## Economic Releases (Timing + Typical Equity Reaction)

All times US Eastern. Track the official calendars: **BLS** (CPI, jobs), **BEA** (PCE, GDP), **Federal Reserve** (FOMC), **ISM** (PMIs), plus aggregators (Investing.com, Trading Economics, Forex Factory, FXStreet) for consensus estimates.

### Why "surprise" beats the absolute number
The market has already priced the consensus forecast. Price reacts to the **actual-minus-expected gap**. Example: in May 2021, core CPI consensus was +0.3% MoM; actual printed +0.9% (a +0.6 surprise) and the Nasdaq dropped ~150 points within minutes (LSEG). A study of the 2021–2025 high-inflation regime found S&P 500 cumulative abnormal returns exceeding 1% on disinflationary CPI surprises, with a notable **asymmetry**: downside-inflation surprises (good news) produced large, statistically significant positive reactions while upside surprises produced negative but less significant moves (*Applied Economics Letters*). Track surprises mechanically as a z-score: (actual − consensus) / historical std of the surprise.

### CPI (Consumer Price Index) — BLS, ~8:30 AM, mid-month
- Releases around the middle of the month for the prior month at 8:30 AM ET (BLS).
- **Core CPI MoM** is the cleanest market mover (strips food/energy). A core print near 0.2% reads "cooling"; near 0.4% reads "too hot" (EBC).
- Reaction: hot CPI → sell growth/long-duration/tech, rate-sensitive sectors; financials can rise on higher-rate expectations. Soft CPI → risk-on rally, growth outperforms. Reaction concentrated in first minutes; repricing of Fed path can extend the bias ~1 week.
- Magnitude: large surprises have produced 1.5–2.5% intraday S&P moves and 2–3.5% Nasdaq moves in recent hot-print scenarios (TradingKey); the Nov 2022 downside surprise (7.7% vs 8.0% expected) produced a 5.5% S&P day and 7.4% Nasdaq spike with the 10Y yield falling ~28 bps.

### Jobs Report / Nonfarm Payrolls (NFP) — BLS, 8:30 AM, first Friday
- "Employment Situation," 8:30 AM ET, typically the first Friday of the month (BLS); called the "king" of announcements (NY Fed/Andersen-Bollerslev).
- Watch: headline payrolls, the unemployment rate (0.2% moves matter), average hourly earnings (wage inflation), and the **two-month net revision** (can move markets on its own).
- Regime-dependent reaction: in a hot-inflation regime a strong jobs print is often *bearish* for equities (implies fewer Fed cuts); when growth fears dominate, strong jobs is bullish. NFP is generally positively correlated with the USD.

### FOMC Meetings / Rate Decisions — Federal Reserve, 2:00 PM, 8x/year
- Statement at 2:00 PM ET; Chair press conference at 2:30 PM. Eight scheduled meetings per year.
- **Largest and most durable** scheduled-release effect. The 10Y rate, S&P 500, and EUR/USD are at least **8x more volatile** on FOMC days than non-event days (Rosa, NY Fed). News absorption takes ~90 minutes; effects do not fully revert next day.
- **Pre-FOMC drift**: the S&P 500 rose on average **49 bps in the 24 hours before** scheduled announcements (Lucca & Moench, NY Fed Staff Report 512), and these returns historically did not revert — accounting for approximately **80% of the annual U.S. equity premium since 1994** ("a staggering 80% of the annual U.S. equity premium since 1994 was earned in the 24 hours before FOMC announcements"). FOMC-day returns are ~5x average daily returns since 1980 (Quantpedia).
- Post-COVID nuance: since 2020, stock/bond markets often move *opposite* during the press conference vs the initial statement reaction, tied to Powell's wording (CEPR). Swing implication: the statement reaction can reverse 30 minutes later — wait for the press conference to settle.
- SEP/"dot plot" meetings (quarterly) carry extra weight.

### PCE (Personal Consumption Expenditures Price Index) — BEA, 8:30 AM, end of month
- Released in the monthly Personal Income & Outlays report, ~end of month, normally 8:30 AM ET (BEA). The **Fed's preferred inflation gauge**; **core PCE** (ex food/energy) is the key number.
- Because CPI and PPI come out ~2 weeks earlier, PCE is often partially anticipated, so the surprise (and reaction) tends to be smaller than CPI — but a core-PCE surprise still moves yields → USD → gold → equity futures in that order.

### GDP — BEA, 8:30 AM, quarterly (three estimates)
- Advance, second, and third estimates released ~8:30 AM ET in successive months. Advance estimate moves markets most. PCE price data are embedded in the GDP release.
- Swing relevance is moderate: GDP is backward-looking; the embedded inflation deflator and consumption components can surprise.

### PMIs — ISM & S&P Global, 9:45/10:00 AM
- **ISM Manufacturing PMI**: first business day of month, 10:00 AM ET. **ISM Services PMI**: third business day, 10:00 AM ET (ISM). S&P Global flash PMIs release ~9:45 AM around the 23rd.
- 50 = expansion/contraction line; ~42.3 is the level historically consistent with overall GDP growth (ISM). Services PMI matters more for the US (services >80% of economy).
- Sub-indexes drive the reaction more than the headline: **New Orders** (demand/growth) and **Prices Paid** (inflation). A PMI that rises on demand is bullish; one that rises on prices is bearish for rate-sensitive stocks. ISM ranks below FOMC and NFP in market impact (~9 bps pre-announcement drift; Rosa).

### Tracking calendars and consensus
- Primary: BLS schedule pages, BEA release schedule, Federal Reserve FOMC calendar, ISM ROB calendar.
- Aggregators with consensus: Investing.com, Trading Economics, Forex Factory, FXStreet, CME FedWatch (rate-cut probabilities from fed funds futures), Cleveland Fed Inflation Nowcasting (daily CPI/PCE nowcast).

---

## Rate/Dollar Regime

### Interest rates and "equity duration"
Stocks are valued as the present value of future cash flows; a higher discount rate (driven by Treasury yields) lowers valuations. **Equity duration** = sensitivity of a stock's price to rate changes; the further out the cash flows, the higher the duration (QV Investors). Mechanically: a guaranteed $100 in one year is worth $98.04 at a 2% discount rate but $95.24 at 5% — the business didn't change, only the discount math (Traders Agency).

- **Growth / long-duration (tech, biotech, high-P/E, non-dividend payers)**: most rate-sensitive; sell off hardest when long yields rise; benefit most when rates fall. Track vs the **10Y yield** and **2Y yield**.
- **Value / short-duration (mature, high current cash flow, dividend payers)**: less rate-sensitive. The IWD/IWF (value/growth) ratio tracks the 5Y yield closely.
- **Financials/banks**: benefit from a **steeper curve** (borrow short, lend long → wider net interest margin). A steepening 2s10s in 2025 drove record bank profits and NIM expansion (Angel Oak); inversion compresses NIM and tightens credit.
- **REITs & utilities**: rate-sensitive on two counts — heavy debt loads and dividend yields that compete with Treasuries. Rising rates hurt; falling rates help.
- **High-debt companies**: rising rates raise refinancing costs and compress margins.

**Yield curve (2s10s)**: 10Y minus 2Y. Inversion (2Y > 10Y) historically precedes recessions (6–24 month lead). The re-steepening *after* inversion (un-inversion) has preceded recession onset in 1989, 2007, 2019 (eco3min). The NY Fed's recession model uses the **3m10y** spread (T10Y3M). *Why* it steepens matters: bull steepener (2s falling faster, rate cuts) is risk-on; bear steepener (10s rising faster, inflation/supply) is risk-off.

### Real yields vs nominal yields
- **Real yield** = nominal yield − expected inflation ≈ 10Y TIPS yield. Equity duration math runs off real rates; rising real yields are the cleanest headwind for long-duration growth.
- **Gold**: strongly inversely correlated to 10Y real (TIPS) yields — median ~−0.63 over the past decade, negative ~85% of the time (BullionVault); PIMCO estimates a 100 bps rise in 10Y real yields historically cut the real gold price ~18% ("gold's real duration of 18 years"). Note this relationship **broke in 2024–2025** (gold rallied with positive real yields, driven by central-bank buying) — flag this as a regime caveat.

### Dollar (DXY) regime
DXY = USD vs a basket (euro 57.6%, yen 13.6%, GBP 11.9%, CAD 9.1%, SEK 4.2%, CHF 3.6%; ICE). Rule of thumb: every **10% sustained rise in DXY shaves ~2–4% off S&P 500 EPS**, concentrated in multinationals (Apple ~60% overseas revenue, Microsoft ~50%; heygotrade). The S&P 500 derives **41% of revenue abroad** (FactSet/Apollo, Jan 2025: "41% of revenue in S&P 500 companies comes from abroad"; 59% is domestic).
- **Strong dollar**: hurts large-cap multinationals/exporters (translation drag) and commodity-linked names; relatively favors **domestic small caps** (Russell 2000 — domestically focused), regional banks, utilities.
- **Weak dollar**: tailwind for multinationals' overseas earnings, commodity stocks, EM exposure. WisdomTree: a weak-dollar six-month window historically preceded ~6% S&P EPS growth vs ~4% average.
- Mechanical regime filter: **DXY vs its 200-day moving average** — sustained above = strength regime (tilt domestic), below = weakness regime (tilt multinational/commodity). Caveat: the DXY–S&P correlation is unstable and has drifted toward zero as supply chains regionalize.

---

## Political/Policy Factors

### Elections and the 4-year cycle
- The S&P 500 averaged **11.3% in presidential election years from 1928 to 2016** (Morgan Stanley, citing Morningstar/Ibbotson Associates: "the average return for the S&P 500 index during presidential election years was 11.3 percent"), with **83% positive** — leaving four negative years (1932, 1940, 2000, 2008). The **Presidential Election Cycle Theory** (Hirsch): year 3 strongest (~17.2%), years 1, 2, 4 below the ~10% average (WT Wealth). Volatility rises in the months before an election as policy uncertainty peaks, then subsides once the outcome is known.
- Practical swing takeaway: these are weak, low-frequency tendencies — use election-cycle effects only as a mild contextual tilt, not a trade trigger.

### Sector-specific policy sensitivities
- **Healthcare/pharma**: drug-pricing policy and tariff threats. In 2025–26, "most favored nation" pricing deals and threatened pharma tariffs (floated up to 200–250%) drove volatility; >12 major drugmakers signed price-cut deals in exchange for 3-year tariff exemptions (CNBC).
- **Energy**: drilling/regulation, OPEC, demand expectations. Tariff-driven recession fears cut oil ~15% in early 2025 (Fidelity).
- **Defense**: military-spending and conflict-driven; "Buy American" and defense manufacturing supported by public spending (YCharts).
- **Financials**: deregulation and curve steepening are tailwinds.
- **Tech**: antitrust and semiconductor/export policy; CHIPS Act funding supported domestic chipmakers.
- **Clean energy**: subsidy-dependent (sensitive to IRA-type rollbacks).
- **Tariffs (industrials/autos/semis/retail)**: 25% Section 232 auto tariffs (April 2025); modeled 25% auto/pharma/semi tariffs would raise auto/pharma prices 8.5–10.5% (Yale Budget Lab). Retail is on the front line (imported goods). Industrials can be long-run beneficiaries via reshoring. On "Tariff Day" (April 2, 2025) the Nasdaq entered correction; SMH (semis ETF) fell >30% then recovered to +18% YTD by July — illustrating the typical sharp-drop/recovery policy pattern.

### Pricing policy uncertainty: the EPU Index
The **Economic Policy Uncertainty (EPU) Index** (Baker, Bloom, Davis 2016) is newspaper-based; spikes near tight elections, wars, debt-ceiling fights, and (in 2025) tariff announcements. Higher EPU → **higher stock-price volatility** and reduced investment/employment in policy-sensitive sectors (defense, healthcare, infrastructure, finance). Available daily on FRED as **USEPUINDXD**; trade-policy and monetary-policy sub-indices also published (policyuncertainty.com). The ECB notes policy uncertainty commands a larger risk premium during weak-market periods.

---

## Geopolitical Factors

### Typical pattern: shallow, fast, "buy the fear"
Across 20+ major geopolitical shocks since WWII, the S&P 500 averaged a ~**1% one-day decline** (George Smith/LPL) and a **−4.7% total drawdown**, bottoming in **19 days** and fully recovering in **42 days** (LPL Research: "prior geopolitical events have led to total average drawdowns of only -4.7%. The average time to reach a market bottom is 19 days, and the average time to fully recover losses is 42 days"). Hartford Funds: stocks are higher one year later ~70% of the time. The **"buy the invasion" pattern**: the 2003 Iraq invasion bottomed at the moment of maximum fear; the Dow rose 2.3% the next day and the S&P gained ~26–30% over the next 12 months — resolution of *uncertainty*, not the conflict, was the catalyst.
- Cuban Missile Crisis (1962): ~7% drop, recovered in ~2 weeks.
- 9/11 (2001): ~11% first-week drop, recovered in ~1 month (within a continuing dot-com bear).
- Russia-Ukraine (2022): only ~5.3% two-day drop, but landed on a Fed-tightening bear market.

### The critical caveat: oil/recession chain
The exceptions are shocks that trigger sustained **oil spikes, higher inflation, and tighter financial conditions** → recession. The 1973 Yom Kippur War/oil embargo led to a >40% decline; the 1990 Iraq-Kuwait invasion preceded a recession (heygotrade). Rule: a self-contained shock recovers; one that disrupts energy/supply chains and feeds inflation can extend into a bear market.

### Sector reactions
- **Energy/oil**: up on Middle East conflict, supply disruptions.
- **Defense**: up on war/escalation.
- **Semiconductors**: down on Taiwan/China tensions (supply-chain risk).
- **Shipping/logistics**: react to supply-chain/route disruptions (e.g., Hormuz, Red Sea).
- **Gold, Treasuries, USD, JPY/CHF**: safe-haven bids on risk-off.

### Duration
Most geopolitical effects on broad indices are resolved within **days to weeks**; sector effects (energy, defense) can persist as long as the conflict/supply situation does. Swing rule: fade the initial panic in broad indices only if data show no recession/oil-shock chain; trade the sector winners (energy/defense first, then cyclicals as resolution appears).

---

## How to Compute a Macro Risk-On/Off Modifier (0–100)

### Inputs (all free, daily)
| Indicator | Source/ticker | Risk-on direction | Notes |
|---|---|---|---|
| VIX (level & vs 50-day MA) | CBOE; FRED VIXCLS | Lower = risk-on | Long-run median 17.62 (Cboe); typical range ~11.25–25.83; >~25 elevated |
| VIX term structure (VIX9D/VIX, VIX/VIX3M) | CBOE; vixcentral.com | Contango = risk-on | VIX/VIX3M > 1.0 = backwardation = stress (~16–20% of days) |
| 2s10s yield curve | FRED T10Y2Y | Steeper (bull) = risk-on | Context: bull vs bear steepener |
| HY credit spread (OAS) | FRED BAMLH0A0HYM2 | Tighter = risk-on | Long-term avg ~394 bps, median ~453 bps (ICE BofA); <300 complacency; >500 stress; >800 acute |
| IG spread / HY-IG | FRED BAMLC0A0CM / ratio | Tighter = risk-on | Leads equities 1–3 months |
| Dollar index (DXY) | ICE; vs 200-day MA | Weaker = risk-on (mild) | Unstable correlation |
| Breadth: % stocks > 200-day MA | $SPXA200R / $MMTH / $S5TH | Higher = risk-on | >70% bullish (can be overbought); <30% weak; <50 confirms bear |
| Breadth: % > 50-day MA | $SPXA50R | Higher = risk-on | >80% strong; <10% washed-out |
| Put/call ratio (total & equity) | CBOE; $CPC/$CPCE | Lower = greed/risk-on | Contrarian extremes below |
| Safe-haven demand | 20-day stock-minus-bond return; gold | Stocks > bonds = risk-on | CNN's method |
| Sector relative strength | XLU/XLK, staples/discretionary (XLP/XLY) | Cyclical leading = risk-on | Defensive leadership = risk-off |
| Economic Policy Uncertainty | FRED USEPUINDXD | Lower = risk-on | Spikes at elections/wars/tariffs |

### Put/call thresholds (contrarian)
- **Total put/call ($CPC)**: above **1.20** = excessive bearishness → contrarian bullish; below **0.70** = excessive bullishness → caution (StockCharts; smooth with 10-day SMA). Statistical study (2007–2022): average ~0.94; 5% extreme tails at **<0.72 (greed)** and **>1.23 (fear)** (Wall Street Courier; Britannica Money: <0.8 strong bullish sentiment, >1.2 strong bearish).
- **Equity-only ($CPCE)** runs structurally lower (~0.55–0.70 neutral; 200-day MA ~0.61). Do not apply total-PCR thresholds to equity-PCR.
- Caveat: post-2020 retail/0DTE options boom shifted distributions — prefer **rolling z-scores/percentiles** over fixed lines.

### CNN Fear & Greed as the canonical template
The CNN Fear & Greed Index (launched 2012) compiles **seven equally weighted** indicators, scoring each by how far it deviates from its average relative to normal divergence (effectively a z-score), then averaging to a 0–100 score (100 = max greed). The seven: (1) **Market momentum** — S&P 500 vs its 125-day MA; (2) **Stock price strength** — NYSE 52-week highs vs lows; (3) **Stock price breadth** — McClellan Volume Summation Index; (4) **Put/call options** — 5-day average; (5) **Market volatility** — VIX vs its 50-day MA; (6) **Safe-haven demand** — 20-day stock-minus-bond returns; (7) **Junk bond demand** — HY-minus-IG yield spread. Bands: 0–24 extreme fear, 25–44 fear, 45–55 neutral, 56–74 greed, 75–100 extreme greed. As of June 1, 2026 the index reads 59 (greed). Historic extremes: 12 (GFC, Sept 2008), 2 (COVID, March 2020), 3 (April 8, 2025 tariff low).

Other reference composites: **OFR Financial Stress Index** (signed standardized values, PCA/dynamic-factor weights, zero = normal) and **Chicago Fed NFCI** (105 variables, each z-scored, weighted by dynamic factor analysis; mean 0, SD 1; positive = tighter conditions).

### Building your composite (mechanical recipe)
1. **Normalize** each series over a rolling **252-trading-day** lookback: z-score `z = (x − mean_252) / std_252`, or percentile-rank within the trailing window (percentile is more robust to outliers/skew).
2. **Sign/invert** so higher = risk-on: multiply by −1 for VIX, HY OAS, put/call, safe-haven demand, DXY (if treating USD strength as risk-off), EPU; leave breadth, momentum, bull-steepening as-is. (This mirrors the OFR/NFCI "signing" step — multiply the standardized value by −1 for indicators where high = bad.)
3. **Aggregate**: equal-weight average of signed z-scores (CNN approach, so no single input dominates), or use custom/PCA weights. A practical equal-weight starting set: VIX 20%, HY OAS 20%, breadth 15%, put/call 10%, term structure 10%, 2s10s 10%, DXY 5%, safe-haven 5%, sector RS 5%.
4. **Map to 0–100**: `score = 100 × Φ(z_composite)` (normal CDF; z=0→50, z=+1→84, z=−1→16), or linear clamp `50 + (z/3)×50`.
5. **Bands** (mirror CNN): **0–24 risk-off**, 25–44 cautious, **45–55 neutral**, 56–74 risk-on, **75–100 extreme greed** (overbought — also a contrarian caution).

### Using the score to gate individual stock signals
- **Score ≥ 55 (risk-on)**: full position sizing; take standard long setups; normal stops. Long-biased.
- **Score 45–55 (neutral)**: standard sizing but require cleaner setups; avoid lowest-quality signals.
- **Score 25–44 (cautious/risk-off)**: cut position size ~50%; require stronger confirmation (e.g., higher relative strength, tighter base); tighten stops; favor defensive sectors; reduce or avoid long exposure in long-duration growth.
- **Score < 25 (extreme risk-off)**: no new longs except A+ setups (or stand aside); smallest size; consider that extreme-fear readings are also contrarian bottoming zones — scale in cautiously only with price confirmation (e.g., breadth thrust, VIX backwardation easing).
- **Score > 75 (extreme greed)**: full participation but treat as a contrarian caution — tighten trailing stops, avoid adding into parabolic moves.
- **Hard overlays regardless of score**: avoid initiating new swing longs into the 24 hours before a major release (CPI, NFP, FOMC) unless the setup explicitly accounts for event risk; the pre-FOMC drift argues for a modest long bias into FOMC. In **VIX backwardation (VIX/VIX3M > 1.0)** or **HY OAS > 500 bps and rising**, force the score one band lower.

### Practical thresholds summary
- Risk-on: composite ≥ 55; VIX < 18 and contango; HY OAS < 350; breadth (% > 200-day) > 60%; put/call below average.
- Risk-off: composite ≤ 35; VIX > 25 or backwardation; HY OAS > 500 and widening; breadth < 40%; put/call total > 1.2.

---

## Summary Table of Data Sources

| Data | Best source | Ticker/series | Cost | API |
|---|---|---|---|---|
| Economic calendar + consensus | Investing.com, Trading Economics, Forex Factory, FXStreet | — | Free | Paid tiers |
| CPI | BLS | bls.gov/cpi | Free | — |
| NFP / jobs | BLS | Employment Situation | Free | — |
| PCE, GDP | BEA | bea.gov | Free | BEA API (free) |
| FOMC schedule/statements | Federal Reserve | federalreserve.gov | Free | — |
| Rate-cut probabilities | CME FedWatch | — | Free | — |
| Inflation nowcast | Cleveland Fed | — | Free | — |
| ISM PMIs | ISM | ismworld.org | Free (headline) | — |
| VIX | CBOE / FRED | VIXCLS | Free | FRED API (free) |
| VIX term structure | CBOE / vixcentral.com | VIX9D, VIX3M | Free | — |
| Treasury yields, 2s10s | FRED / US Treasury | DGS10, DGS2, T10Y2Y, T10Y3M | Free | FRED API (free) |
| Real yields (TIPS) | FRED | DFII10 | Free | FRED API |
| HY credit spread (OAS) | FRED (ICE BofA) | BAMLH0A0HYM2 | Free | FRED API |
| IG credit spread | FRED (ICE BofA) | BAMLC0A0CM | Free | FRED API |
| Dollar index (DXY) | ICE / brokers | DXY | Free (delayed) | Paid real-time |
| Breadth (% > 200/50-day MA) | StockCharts, Barchart | $SPXA200R, $SPXA50R, $MMTH, $S5TH | Free/freemium | — |
| Put/call ratios | CBOE; StockCharts | $CPC, $CPCE, $CPCI | Free | — |
| Sector ETFs (relative strength) | Any broker | XLU, XLK, XLP, XLY, etc. | Free | — |
| Economic Policy Uncertainty | FRED (Baker-Bloom-Davis) | USEPUINDXD | Free | FRED API |
| CNN Fear & Greed | CNN | — | Free | — |
| Financial conditions composites | Chicago Fed (NFCI); OFR (FSI) | NFCI | Free | FRED API |

**The single most important free resource is the FRED API** (Federal Reserve Bank of St. Louis) — it carries VIX, all Treasury yields and spreads, ICE BofA credit spreads, real yields, EPU, and NFCI in one programmatic interface, ideal for computing the composite daily.

---

## Recommendations

**Stage 1 — Build the data layer.** Pull the FRED series daily (VIXCLS, T10Y2Y, T10Y3M, DGS10, DGS2, DFII10, BAMLH0A0HYM2, BAMLC0A0CM, USEPUINDXD, NFCI) plus breadth ($SPXA200R) and put/call ($CPC) from StockCharts/CBOE, and DXY from your broker. Maintain a rolling 252-day window per series.

**Stage 2 — Compute the composite.** Z-score each series over 252 days, sign so higher = risk-on, equal-weight (or use the suggested weights), map to 0–100 via the normal CDF. Log it daily alongside the CNN Fear & Greed reading as a sanity check.

**Stage 3 — Gate signals.** Apply the band rules: full size ≥55, half size 25–44, stand aside <25 (except A+ setups), contrarian caution >75. Force the score one band lower in VIX backwardation or HY OAS > 500 & rising.

**Stage 4 — Event overlay.** Maintain the economic calendar; flag the 24 hours before CPI/NFP/FOMC; avoid initiating fresh longs into those windows unless setups account for event risk; track surprises as z-scores to learn your universe's reaction.

**Benchmarks that change the rules:**
- HY OAS crossing **500 bps and rising** → shift to defensive posture regardless of composite.
- 2s10s **re-steepening from inversion** → raise recession vigilance (historically precedes downturns).
- VIX/VIX3M crossing **above 1.0** (backwardation) → near-term stress; reduce size.
- Breadth (% > 200-day) crossing **below 50%** → confirm bear regime; above 50% → confirm bull.
- DXY crossing its **200-day MA** → flip domestic vs multinational sector tilt.

---

## Caveats

- **Correlations are unstable.** The DXY–S&P link has drifted toward zero; the gold–real-yield relationship broke in 2024–25 (central-bank buying); equity-bond correlation has flipped signs historically. Re-estimate relationships periodically rather than hard-coding them.
- **Regime dependence.** The same data print is bullish or bearish depending on the dominant narrative (inflation vs growth). The 2021–25 CPI-reaction asymmetry shows reactions are regime-specific.
- **Thresholds drift.** Put/call distributions shifted post-2020 (retail/0DTE options); credit-spread "normal" ranges vary by cycle. Rolling percentiles/z-scores are more robust than fixed levels.
- **Macro is a gate, not an edge.** The composite improves *timing and sizing*; it does not pick stocks. Individual setups, relative strength, and risk management remain primary.
- **Speculative/forward content.** Several 2026-dated market sources cited contain forecasts and projections (e.g., DXY targets, Fed-path expectations); these are scenarios, not established facts, and are flagged as such.
- **Single-source numbers.** Some magnitude figures (e.g., the "10% DXY = 2–4% EPS" rule of thumb, sector EPS exposures) come from individual practitioner sources; treat as directional estimates, not precise constants.
- **Data gaps.** The 2025 government shutdown delayed/canceled some BLS releases (October 2025 CPI was canceled outright) — build tolerance for missing or combined prints into any automated calendar logic.