# Thematic & Cyclical Overlay for Swing Trading US Stocks: A Systematic Signal-Generation Module

## TL;DR

- **Build a single 0–100 Thematic-Tailwind Score (TTS)** for each watchlist name from four sub-scores — Theme Momentum (35%), Sector-Rotation Alignment (25%), Cycle Position (20%), and Broad-Market Risk Context (20%) — then **multiply it down by a Froth penalty and hard-cap it** so an overheated theme can never produce a high score even when price momentum is screaming. Every core input is free (price/volume, sector & theme ETFs, CBOE put/call, FINRA margin, FRED, Google Trends, public filings).
- **Froth detection is the highest-value piece** and should use William O'Neil's quantified climax-top rules: a momentum stock trading **70–100%+ above its 200-day MA**, a **25–50% run in 2–3 weeks** after a months-long advance, an exhaustion gap on the largest volume of the move, plus theme-level confirmation (CBOE equity put/call < 0.45, AAII bulls >2σ, parabolic FINRA margin debt, all-time-high Google Trends). History (dot-com 2000, 3D printing 2014, cannabis/Tilray 2018, 2021 SPAC/EV) shows the worst swing losses come from buying parabolic themes in their final 1–3 weeks.
- **Detect rotation and cycle position from measured relative strength, not guesswork:** rank the 11 sector SPDRs by RS vs SPY and by Relative Rotation Graph (RRG) quadrant (Improving→Leading = rotating in; Leading→Weakening→Lagging = rotating out), and read each industrial cycle (semis via book-to-bill/memory pricing, energy via oil + rig count, housing via the 10-yr yield/mortgage rates + NAHB HMI) from free public indicators. Treat the classic Stovall sector model as a macro map, not a mechanical trigger.

## Key Findings

1. **A standalone-but-integrable overlay is the right architecture.** The module answers one question per stock — *is the thematic/cyclical backdrop a tailwind or headwind right now, and is froth risk dominant?* — and outputs a 0–100 score that gates the size/eligibility of an underlying technical/momentum signal. It does not generate entries itself.

2. **Froth must act as a penalty/cap, not an additive factor.** This is the single most important design decision for a days-to-weeks horizon. An un-penalized momentum system is *most* enthusiastic exactly when a theme is parabolic and about to top.

3. **O'Neil/IBD climax-top rules are the most authoritative, automatable froth framework.** The 70–100%+ extension above the 200-day MA, the 25–50% climax run, consecutive up-day patterns, the largest one-day gain/widest weekly spread, and exhaustion gaps are all computable from price/volume alone.

4. **Relative strength (RS line vs SPY) and the RRG are the backbone of both theme detection and sector rotation.** They are free, visual, and quantifiable, and they reveal leadership shifts before they are obvious on the index.

5. **Every industrial cycle has a small set of free leading indicators.** Semis: SEMI book-to-bill + DRAM/NAND pricing. Energy: WTI + Baker Hughes rig count + EIA inventories. Housing: 10-year yield/mortgage rates + NAHB HMI + starts/permits. Materials: copper + ISM new orders + the dollar.

6. **Historical bubbles share a quantifiable topping signature** — parabolic price, valuation disconnected from fundamentals (extreme price-to-sales), a flood of new issuance (IPOs/SPACs), retail/options mania, and narrowing breadth — all captured by the Froth Score components.

## Details

### Overview

The module is organized around three nested cycles, each carrying tailwind/headwind information that a stock inherits:

- **Theme/narrative cycle** (fastest, behavioral) — drives Theme Momentum and Froth.
- **Sector-rotation/business cycle** (medium) — drives Sector-Rotation Alignment.
- **Industrial/commodity cycle** (slowest, fundamental) — drives Cycle Position.

Design principles: (1) **froth is the priority** and is treated as a penalty/cap; (2) **free/cheap data first**, with paid feeds noted as optional upgrades; (3) **rules over judgment**, with the few judgment points explicitly flagged.

### Theme detection

**Anatomy of a thematic wave.** Thematic waves follow a repeatable lifecycle blending the Gartner Hype Cycle (Innovation Trigger → Peak of Inflated Expectations → Trough of Disillusionment → Slope of Enlightenment → Plateau of Productivity), the Minsky bubble model (Displacement → Boom → Euphoria → Profit-taking → Panic), and Jean-Paul Rodrigue's "Four Stages of a Bubble" (Stealth → Awareness → Mania → Blow-off). STOXX's investable-theme framework adds a commercial lens (Ideation → Innovation → Commercialization → Maturity, drawing on diffusion-of-innovations theory).

Practical four-phase trading map:

| Phase | Behavioral signature | Tradeability |
|---|---|---|
| **1. Stealth / Displacement** | Quiet accumulation; theme ETF starts outperforming SPY; little media; flat Google Trends | Best risk/reward but hard to detect; thin confirmation |
| **2. Awareness / Boom** | Breadth broadens; new entrants/IPOs; analyst upgrades; capex announcements; rising Trends | **Sweet spot for swing trading** — momentum + improving breadth |
| **3. Mania / Euphoria** | Vertical price, "this time is different," retail mania, call-option frenzy, IPO/SPAC surge | High return but froth penalty escalating fast — trade smaller, tighter stops |
| **4. Blow-off / Distribution** | Climax volume, breadth divergence, parabolic exhaustion, then panic | Avoid new longs; froth cap should zero out the theme score |

The analytical key is **inferring the phase from measurable indicators**, all observable from free/cheap data:

1. **Relative strength of theme ETF vs SPY (backbone).** RS line = theme ETF ÷ SPY, with a 50-day EMA overlay. RS rising and above its EMA = inflow/leadership; falling/below = rotation out. A theme ETF RS line making new highs while the theme is *not yet* widely discussed is the cleanest Phase 1→2 signal (practitioner basis: IBD/O'Neil "RS Line" and Julius de Kempenaer's RRG work). Representative theme ETFs: AI/robotics (BOTZ, ROBO, IRBO), semis (SMH, SOXX), quantum (QTUM), nuclear/uranium (URA, URNM, NLR), solar/clean (TAN, ICLN), biotech (XBI, IBB), EVs (DRIV, LIT), cyber (CIBR, HACK).

2. **Breadth of participation.** Percentage of theme constituents above their own 50-day MA and making new 20-day highs. Healthy Phase 2 = >60–70% above the 50-day. Index new high while participation falls = **breadth divergence** = narrowing toward a top.

3. **New entrants / IPOs / SPACs.** A wave of theme-tagged public listings reliably marks maturation toward froth. Jay Ritter's IPO research (University of Florida) shows IPO waves coincide with overvaluation. Track theme-tagged IPOs/SPACs per quarter.

4. **Media velocity & Google Trends.** Google Search Volume Index is a validated proxy for *retail* attention (Da, Engelberg & Gao, "In Search of Attention," *Journal of Finance*, 2011). Rising-but-not-extreme = Phase 2; vertical spike to all-time-high search = Phase 3 warning. Free via Google Trends/pytrends.

5. **Analyst upgrades & capex announcements.** A cluster of upgrades plus large capex/order announcements (data-center buildouts, fab capex) confirms the fundamental leg. Free via filings/news.

6. **Options activity.** Rising call volume/skew on theme leaders confirms Phase 2 momentum and becomes a froth signal in Phase 3.

7. **Thematic ETF inflows.** State Street's monthly US-listed ETF flow reports and etf.com/CFRA flow tools localize the money. Sustained inflows = confirmation; *parabolic* inflows = late-stage crowding.

**Human-judgment flag:** mapping ETF/keyword sets to a theme and judging whether a catalyst is structurally real (AI compute demand) vs pure narrative (many 2021 SPACs) requires human input.

### Bubble/froth detection (highest priority)

Froth runs at two levels — theme/sector ("is the whole wave overheated?") and individual stock ("is *this name* parabolic?") — and produces a **Froth Score 0–100** that becomes a penalty/cap.

**Technical froth — O'Neil/IBD climax-top framework** (William O'Neil, *How to Make Money in Stocks* and *24 Essential Lessons for Investment Success*; IBD), the most authoritative quantified practitioner source:

- **Extension above the 200-day/40-week MA.** IBD Sell Rule: prepare to sell when a stock trades **70–100%+ above its 200-day MA** (70% shows exhaustion). Per IBD/MarketSmith summarizing O'Neil's research, a climax run is "a stretch to 70% or 100% beyond the 200-day moving average." At its 2000 peak Charles Schwab traded ~210% above its 40-week line; TASER in 2004 was >100% above its 200-day. O'Neil keys extension off the **200-day, not the 50-day** — this is the single most useful automatable froth trigger for individual momentum names.
- **Climax run.** After a months-long advance, an unusually rapid **25–50%+ run over two to three weeks**, typically ≥18 weeks after a base breakout.
- **Consecutive up days:** 7 of 8, or 8 of 10.
- **Largest one-day gain / widest weekly spread of the entire move** — sell into that strength.
- **Exhaustion gap** on the largest volume of the whole advance.
- **P/E expansion:** sell when the P/E has expanded **+130% from the level at the original base breakout**.

Example (Tesla, January 2021 climax top, per IBD): up 32% in three prior weeks and 43% in five; biggest one-day gain of the run on Jan 8, 2021; 11 up days in a row; multiple gap-ups described as exhaustion gaps.

**Additional automatable technical measures:**
- **Distance from mean in σ:** price >2σ above the 20-period mean (upper Bollinger Band, %B > 1.0) = overbought; **>3σ** = genuine statistical extreme (~99.7% tail). Use 50-day or weekly mean for swing froth.
- **Weekly RSI > 70 (overbought), > 80 (reversal-risk).** Caveat: in strong trends RSI "walks the band" and stays >70 for weeks — never use alone.
- **Volume climax/exhaustion:** blow-off-day volume often 200%+ of average with downside follow-through. Parabolic blow-off tops typically retrace ~50%+ of the prior advance in a fraction of the build time.
- **Accelerating ROC / parabolic curve:** shallower pullbacks, steepening slope toward vertical.
- **Breadth divergence** at theme level (index new high, participation rolling over).

**Sentiment/behavioral froth (theme & market level):**
- **CBOE equity put/call extreme lows.** Normal ≈ 0.60–0.70; **< 0.40–0.45 = excessive optimism/complacency** (contrarian sell context). Free from CBOE/StockCharts ($CPCE). **Caveat:** low P/C is statistically a *weaker* top-timing signal than high P/C is at bottoms, and the post-2020 retail/0DTE boom has distorted it — use as confirming, not triggering.
- **VIX — critical nuance.** Major tops do *not* form at the VIX's lowest readings; sub-12 VIX signals complacency but typically *precedes* the top by months. In 2000 and 2007 the final top came with VIX rising back to ~16+. Watch for a **bullish VIX/price divergence** (index higher highs, VIX higher lows). Free via FRED (VIXCLS).
- **AAII bull-bear extremes.** Bullishness >2σ above mean is a froth marker. Per AAII ("Investor Sentiment as a Contrarian Indicator," aaii.com), "Bullish sentiment reached its highest levels on January 6, 2000—the height of the tech bubble—at 75.0%," against a survey average of ~38.8% (SD ~10.5%). Free, weekly (Thursdays).
- **FINRA margin debt.** Margin-debt peaks have led major tops: the 2007 cycle peaked July 2007 (~3 months before the October top); the 2021 cycle peaked October 2021 (~3 months before the January 2022 top). Use as: (a) parabolic + rising = late-cycle risk; (b) rolling over while price makes new highs = leveraged de-risking warning. Free, monthly (published ~3rd week, one-month lag); margin-debt/GDP gives multi-cycle context.
- **Retail mania / "this time is different" / IPO-SPAC surges.** Qualitative but powerful; the 2021 SPAC peak and zero-revenue EV "story stock" mania are modern templates.
- **Valuation froth.** Extreme price-to-sales is the most useful metric for profitless theme stocks (P/E often unusable).

**Historical bubble case studies — topping signatures:**

| Bubble | Peak | Quantified froth signature |
|---|---|---|
| **Dot-com / Nasdaq** | Mar 10, 2000 (Nasdaq 5,048) | Nasdaq P/E ~200; Cisco peaked at a **$555.4B market cap** with a **P/E ~201** (per Liberty Through Wealth) and P/S ~200x on ~$19B revenue; only ~14% of Nasdaq-100 tech IPOs profitable; ~74% of internet cos. negative cash flow; **AAII bulls 75.0% on Jan 6, 2000** (AAII). Nasdaq fell 78% to Oct 2002; Cisco fell ~80%. |
| **3D printing** | Early Jan 2014 | Entering 2014, DDD P/S 21.0, trailing P/E 209, fwd P/E 75.3; SSYS P/S 16.3, fwd P/E 58.3. By Jan 2016: DDD −93%, SSYS −88%, VJET −90%. |
| **Cannabis (Tilray)** | Sep 19, 2018 | Hit **~$300 intraday** (2:50pm), closed +40% at $214.06, **up >1,100% since its July $17 IPO**; **market cap ~$28B** vs ~$41M projected 2018 sales; **halted 5× by Nasdaq** in the session for volatility (CNBC, Bloomberg); lost ~two-thirds within days. |
| **2021 SPAC/EV/meme** | Feb 2021 (SPACs) | **613 SPAC IPOs raising ~$162.5B, 63% of all IPOs** (SPACInsider via Motley Fool); >$100B of zero-revenue EV valuations vs <$1B projected 2021 revenue; de-SPAC mean share price ~$3.85 by Dec 2022. |

Common signature: parabolic price, valuation disconnected from fundamentals, a flood of new issuance, retail/options mania, narrowing breadth.

**Human-judgment flag:** distinguishing a durable secular theme that survives its froth (the internet did; Amazon endured an ~88%+ drawdown and recovered) from a fad that won't (Tilray, most 2021 SPACs) is a judgment call. The froth penalty protects the trade either way; the judgment governs re-entry after the shakeout.

### Sector rotation

**Classic Stovall model mapped to the 11 GICS sector SPDRs.** Sam Stovall's *S&P Guide to Sector Rotation* holds that sectors lead in a repeatable sequence as the economy moves through the business cycle, with the **stock market leading the economy by ~6 months**:

| Cycle phase | Leading sectors | SPDR ETFs |
|---|---|---|
| **Early recovery** (from market bottom) | Technology, Consumer Discretionary, Financials, Industrials, Materials, Real Estate | XLK, XLY, XLF, XLI, XLB, XLRE |
| **Mid cycle / full expansion** | Technology, Industrials, Communication Services | XLK, XLI, XLC |
| **Late cycle / market top** | Energy, Materials (inflation hedges) | XLE, XLB |
| **Early recession** | Consumer Staples, Healthcare, Utilities (defensives) | XLP, XLV, XLU |
| **Late recession / bottoming** | Utilities → then Tech/Financials/Discretionary turn first | XLU → XLK, XLF, XLY |

Caveat: Molchanov et al. ("The myth of business cycle sector rotation," *International Journal of Finance & Economics*, 2024) find the strict Stovall sequence is an unreliable standalone timing strategy. **Use it as a macro map; let measured relative strength be the final arbiter.**

**Detecting rotation in real time (automatable):**

1. **RS ratio of each sector ETF vs SPY.** For XLK, XLE, XLF, XLV, XLY, XLP, XLI, XLB, XLU, XLRE, XLC: compute RS = sector ÷ SPY with a 50-day EMA; rank all 11 by RS trend and RS momentum.

2. **Relative Rotation Graphs (RRG).** De Kempenaer's RRG (StockCharts, developed 2004–05; launched on Bloomberg 2011, StockCharts 2014) plots each sector on **JdK RS-Ratio** (x, relative trend, 100 = neutral) and **JdK RS-Momentum** (y), creating four quadrants traversed clockwise:
   - **Leading** (Ratio >100, Momentum >100): strong uptrend, still gaining.
   - **Weakening** (>100, <100): uptrend losing momentum.
   - **Lagging** (<100, <100): relative downtrend.
   - **Improving** (<100, >100): downtrend gaining momentum → potential next leaders.
   Actionable read: sectors moving **Improving→Leading with a 0–90° heading** are being rotated *into*; sectors rolling **Leading→Weakening→Lagging** are being rotated *out of*. Tail length = momentum strength. Weekly RRG for positioning, daily for timing. **Breadth read:** many sectors clustering toward Leading = broad/healthy; one or two doing all the work = narrow/fragile.

3. **ETF flows as confirmation.** State Street's monthly flow reports corroborate the RS read; cyclicals (Energy/Materials/Industrials) taking a disproportionate share of sector flows signals a risk-on leadership change.

**For the module:** each stock's sector gets a **Sector-Rotation Alignment sub-score** from its sector's RRG quadrant and RS rank — strongly positive in Leading, positive in Improving, negative in Weakening, strongly negative in Lagging.

### Industrial cycles

These slower fundamental cycles set the multi-month backdrop; assess "where are we" from free public indicators.

**Semiconductors.** SEMI **book-to-bill** (monthly; orders ÷ billings for North American equipment makers; >1.0 expanding, <1.0 contracting) is a leading indicator. Memory pricing (DRAM/NAND, TrendForce) — rising ASPs signal upcycle; the current cycle has been driven by AI-related memory pricing and supply discipline more than unit growth. Capex (TSMC/Samsung/Micron/Intel) leads capacity 12–18 months out. SOX/SMH typically lead the fundamental cycle; the historical ~4-year cycle has been partly distorted by the AI memory supercycle (judgment flag).

**Energy/oil.** WTI/Brent trend (FRED: DCOILWTICO) is the master variable. Baker Hughes rig count (weekly, Fri 1pm ET) leads future supply but reflects drilling *intent*, and post-2020 capital discipline has weakened the rig→production link (rig count fell ~20% in 2023, ~5% in 2024, ~7% in 2025). EIA weekly crude inventories. Interaction: oilfield services (rig-count sensitive) vs E&Ps (price sensitive); rising oil + rising rigs = tailwind, oil rolling over while rigs lag = headwind building.

**Materials/commodities.** Copper ("Dr. Copper"), broad commodity indices, the US dollar (inverse), and ISM Manufacturing PMI new orders. Rising PMI new orders + weak dollar + rising copper = cyclical tailwind for XLB.

**Housing/homebuilders.** Mortgage rates / 10-year Treasury yield (FRED: MORTGAGE30US, DGS10) are *the* leading driver — a falling 10-year yield is a leading positive for homebuilders (lower borrowing costs + bigger buyer pool), and the stocks tend to rally on the *trend* of falling rates before a specific level. NAHB/Wells Fargo HMI (monthly builder sentiment, >50 net positive) is leading. Housing starts & permits (Census; permits lead starts), new/existing home sales, Case-Shiller prices. Watch builders' controlled-vs-owned land ratio for risk. Housing is a classic *leading* sector for the whole economy.

Each watchlist stock in these industries inherits a **Cycle-Position sub-score** from the relevant indicator set. The broader business cycle can be read from ISM PMI (>50 expansion) and the 2s10s yield curve (FRED: T10Y2Y) as a recession lead.

### Stock-to-theme mapping

Build a small static "tag sheet" per name (the main one-time human-judgment input, reviewed periodically):

1. **GICS sector** → one of the 11 sector SPDRs (Sector-Rotation sub-score).
2. **Dominant theme(s)** → one or more theme ETFs/Google Trends keyword sets (Theme-Momentum + Froth sub-scores). E.g., NVDA → AI + semis (SMH, BOTZ); CCJ → nuclear/uranium (URA, URNM); DHI → housing.
3. **Industrial/commodity cycle** (if applicable) → the relevant indicator set (Cycle-Position sub-score).

**Scoring backdrop as tailwind vs headwind.** Each mapped dimension produces a signed contribution: theme ETF RS vs SPY rising & above EMA = tailwind (Phase 2 = max tailwind, Phase 4 = max headwind); sector RRG quadrant/RS rank (Leading/Improving = tailwind); industry indicators improving = tailwind.

**Multi-theme stocks** (e.g., NVDA = AI + data centers + semis): compute the theme sub-score for each theme; take the **weighted maximum** for the tailwind (best non-frothy theme drives it) but apply the froth penalty from the **most overheated** theme. Rationale: a stock benefits from its best tailwind but is endangered by froth in *any* of its themes — a deliberately conservative asymmetry matching the "froth is priority" principle. Optionally weight themes by revenue centrality (judgment input).

### How to compute a Thematic-Tailwind Score (0–100)

**Structure** — four sub-scores (each 0–100), combined then capped/penalized by froth:

| Component | Weight | What it measures | Primary free data |
|---|---|---|---|
| **Theme Momentum (TM)** | 35% | Strength & phase of the stock's best theme | Theme ETF RS vs SPY, breadth, Google Trends, flows |
| **Sector-Rotation Alignment (SR)** | 25% | Is the stock's sector being rotated into? | 11 sector SPDR RS vs SPY, RRG quadrant |
| **Cycle Position (CP)** | 20% | Industrial/commodity/business-cycle backdrop | FRED, SEMI book-to-bill, rig count, NAHB, ISM, yield curve |
| **Broad-Market Risk Context (MR)** | 20% | Is the overall tape risk-on? | % stocks > 200-day MA, SPY vs 200-day, VIX, credit context |

**Step 1 — Raw weighted score**
```
Raw = 0.35·TM + 0.25·SR + 0.20·CP + 0.20·MR
```

**Step 2 — Froth Score (0–100) → multiplier.** Froth = **max** of stock-level and theme-level froth (worst case governs).

*Stock-level (FS_stock):*
- Extension above 200-day MA: 0 at <25%, ramps to 100 at ≥100% (≈70 at 70%). **Weight 30%.**
- Climax run (% gain over trailing 10–15 sessions): 0 at <15%, 100 at ≥50%. Weight 20%.
- Distance above 50-day/weekly mean in σ: 0 at <1.5σ, 100 at ≥3σ. Weight 15%.
- Weekly RSI: 0 at <70, 100 at ≥85. Weight 10%.
- Volume climax (today ÷ 50-day avg, with up-gap): 0 at <2×, 100 at ≥4×. Weight 15%.
- Consecutive up-day pattern (7/8 or 8/10): binary 0/100. Weight 10%.

*Theme/market-level (FS_theme):* theme ETF extension above its own 200-day MA; CBOE equity put/call < 0.45 (ramp toward 0.35); AAII bullishness +1σ (50) → +2σ (100); margin debt parabolic / rolling-over-at-new-highs flag; Google Trends near all-time-high for theme keywords; IPO/SPAC surge flag (binary).

```
Froth = max(FS_stock, FS_theme)
FrothMultiplier = 1 − (Froth/100)^1.5
```
(Froth 50 → ≈0.65; 70 → ≈0.41; 90 → ≈0.15; 100 → 0. The 1.5 exponent makes the penalty bite hard near the top.)

**Step 3 — Cap and final score**
```
TTS = Raw · FrothMultiplier
```
Hard caps: if **Froth ≥ 80, cap TTS at 25** regardless of Raw. If stock-level extension exceeds 100% above the 200-day MA *and* a climax-run + exhaustion-gap pattern is present, cap TTS at **15** (active blow-off — no new longs).

**Step 4 — Interpretation bands**

| TTS | Meaning | Overlay action on the technical signal |
|---|---|---|
| **80–100** | Strong, clean tailwind (theme Phase 2, sector Leading/Improving, low froth) | Full position size; best risk/reward |
| **60–79** | Favorable, modest froth | Allow, normal size |
| **40–59** | Mixed / transitioning | Reduce size; require stronger technical confirmation |
| **20–39** | Headwind or meaningful froth | Avoid new longs; tighten stops on existing |
| **0–19** | Strong headwind or active blow-off | No new longs; froth cap active |

**Worked example (illustrative).** A semis/AI name: SMH RS vs SPY rising and above EMA with broad participation → TM = 85; XLK in Leading → SR = 80; book-to-bill >1 and memory prices rising → CP = 75; tape risk-on, >60% of stocks above 200-day → MR = 70. Raw = 0.35·85 + 0.25·80 + 0.20·75 + 0.20·70 = 78.75. But the stock is 60% above its 200-day, weekly RSI 78, up 35% in two weeks → FS_stock ≈ 62; moderate theme P/C and Trends → FS_theme ≈ 45; Froth = 62 → multiplier = 1 − 0.62^1.5 ≈ 0.51. **TTS ≈ 40** — the backdrop is excellent but the name is extended, so the overlay says "reduce size / wait for a pullback" — exactly the intended behavior.

**Implementation notes.** Update cadence: RS lines, extensions, RSI, volume → daily; RRG and breadth → daily/weekly; put/call and AAII → weekly; margin debt, book-to-bill, NAHB, ISM → monthly; theme tags → monthly or on major news. Compute stack: Python/pandas with free price data (Stooq, Yahoo), CBOE/StockCharts P/C series, FRED API, Google Trends (pytrends), and FINRA's downloadable margin file. Manual inputs: theme tagging, catalyst-reality judgment, narrative reading, re-entry decisions after a shakeout.

### Summary table of data sources

| Data source | What it measures | Free/Paid | Update frequency | How to access |
|---|---|---|---|---|
| Price/volume (Stooq, Yahoo Finance) | RS lines, extensions, MAs, RSI, Bollinger, volume/climax runs | Free | Daily (intraday paid) | CSV/API, pandas |
| Sector SPDRs (XLK,XLE,XLF,XLV,XLY,XLP,XLI,XLB,XLU,XLRE,XLC) | Sector RS vs SPY | Free | Daily | Price feeds |
| Theme ETFs (SMH, SOXX, BOTZ, URA, URNM, TAN, XBI, IBB, QTUM, LIT, CIBR…) | Theme RS vs SPY, theme froth (extension) | Free | Daily | Price feeds |
| StockCharts RRG | Sector/theme rotation quadrants (RS-Ratio, RS-Momentum) | Free/Freemium | Daily/Weekly | StockCharts.com |
| CBOE put/call ratios ($CPCE/$CPC) | Options sentiment froth | Free | Daily | CBOE / StockCharts |
| CBOE VIX (FRED: VIXCLS) | Volatility/complacency; top divergences | Free | Daily | FRED |
| AAII Sentiment Survey | Retail bull/bear extremes | Free | Weekly (Thu) | aaii.com |
| FINRA Margin Statistics | Leverage/froth, top-leading peaks | Free | Monthly (3rd wk, 1-mo lag) | finra.org (Excel) |
| Google Trends (pytrends) | Retail attention / theme heat | Free | Daily/Weekly | trends.google.com |
| FRED (DGS10, MORTGAGE30US, T10Y2Y, DCOILWTICO, ISM, VIXCLS…) | Macro/cycle: rates, yield curve, oil, PMI | Free | Daily–Monthly | FRED API |
| SEMI book-to-bill | Semiconductor equipment cycle | Free (headline) | Monthly | SEMI.org / news |
| DRAM/NAND pricing (TrendForce/DRAMeXchange) | Memory cycle | Free headlines / Paid detail | Monthly | TrendForce |
| Baker Hughes Rig Count | Oil/gas drilling cycle | Free | Weekly (Fri) | rigcount.bakerhughes.com |
| EIA petroleum data | Oil inventories/supply | Free | Weekly | eia.gov |
| NAHB/Wells Fargo HMI | Homebuilder sentiment | Free | Monthly | nahb.org |
| Census housing starts/permits, new home sales | Housing cycle | Free | Monthly | census.gov |
| State Street / etf.com / CFRA flow tools | ETF inflows/outflows by sector/theme | Free/Freemium | Daily/Monthly | ssga.com, etf.com |
| % stocks above 50/150/200-day MA breadth | Market & theme breadth, divergences | Free | Daily | StockCharts ($MMTH etc.) |
| Jay Ritter IPO data (Univ. of Florida) | IPO-wave context | Free | Periodic | site.warrington.ufl.edu/ritter |
| **Sentiment APIs (social/news NLP)** | Real-time narrative/media velocity | **Paid (optional)** | Real-time | Vendor APIs |
| **Institutional/options-flow / dark-pool feeds** | Smart-money positioning, call-skew detail | **Paid (optional)** | Real-time/Daily | Vendor APIs |
| **OptionMetrics / ORATS / Bloomberg** | Detailed options skew, IV, history | **Paid (optional)** | Daily | Vendor |

## Recommendations

**Stage 1 — Minimum viable overlay (build first).** Implement (a) theme & sector RS lines vs SPY with 50-day EMA, (b) the O'Neil stock-level Froth Score (200-day extension + climax run + volume climax + weekly RSI), and (c) the TTS arithmetic with the froth multiplier and hard caps. This alone delivers the core protective value. *Benchmark to advance:* the overlay correctly flags and caps your most extended watchlist names (e.g., anything >70% above its 200-day) before you would otherwise buy them.

**Stage 2 — Add rotation and cycle context.** Layer in the 11-sector RRG quadrants (StockCharts), the Cycle-Position indicators for whichever industries your watchlist touches (semis book-to-bill, oil + rig count, 10-yr yield + NAHB), and the Broad-Market Risk Context (% stocks above 200-day, VIX). *Benchmark:* TTS meaningfully differentiates names in Leading vs Lagging sectors.

**Stage 3 — Add behavioral froth confirmation.** Wire in CBOE equity put/call (<0.45 flag), AAII bullishness (>2σ), FINRA margin debt (parabolic/divergence flag), and Google Trends for theme keywords. *Benchmark:* the theme-level Froth Score rises ahead of, not after, parabolic theme ETF behavior.

**Stage 4 — Optional paid upgrades** only after the free stack is validated: real-time options-flow/skew and social-sentiment APIs for faster Phase-3 detection.

**Operating rules / thresholds that change behavior:**
- **Cap, don't average:** never let high TM rescue a high-Froth name; the multiplier and the Froth≥80 → TTS≤25 cap are non-negotiable.
- **Position sizing by band:** full size only at TTS ≥ 60; half size 40–59; no new longs below 40.
- **Re-evaluate theme tags monthly** and on any major catalyst; this is the highest-leverage manual task.
- **Trip-wire for exits on open positions:** if a held name crosses 100% above its 200-day MA with a climax-run + exhaustion gap, treat as a scale-out/blow-off signal regardless of the technical system.

## Caveats

- **Sector-rotation timing is imperfect.** Academic evidence (Molchanov et al., 2024) shows the strict Stovall sequence underperforms simple market timing; treat it as a map and defer to measured RS/RRG.
- **Low put/call and low VIX are weak top-timers.** Both are statistically less reliable at calling tops than their high counterparts are at calling bottoms, and the post-2020 retail/0DTE options boom has distorted put/call interpretation. Use them only as confirming, secondary froth signals — never as standalone triggers. Note that major tops historically form as VIX *rises off* its lows (~16+), not at sub-12 readings.
- **RSI/Bollinger extremes persist in strong trends** ("walking the band"). Require price/volume climax confirmation; do not sell on an overbought oscillator alone.
- **Margin debt and book-to-bill lag** (one-month and monthly respectively) — they frame regime, not precise timing.
- **The "~30% of leaders top via a climax run" figure could not be tied to a primary O'Neil citation** and has been omitted from the headline claims; attribute the climax-top framework directly to O'Neil's *How to Make Money in Stocks* and IBD rather than to that unverified percentage.
- **Theme durability is a judgment call the model cannot make.** A frothy theme can be a generational technology (internet) or a fad (most 2021 SPACs); the froth penalty protects the swing trade either way, but re-entry after a shakeout requires human assessment of whether the underlying catalyst is real.
- **Backtest before trusting the weights.** The 35/25/20/20 weights, ramp thresholds, and 1.5 froth exponent are reasoned defaults, not optimized parameters — validate and tune them on your own watchlist history, and beware overfitting given the limited number of historical bubble episodes.
- **Forward-looking commentary in sources** (e.g., AI-supercycle projections, SpaceX/OpenAI IPO speculation, 2026/2027 IPO-wave scenarios) is speculation, not established fact, and should not be treated as confirmed in the module's logic.