# "Smart Money" Signals for Swing Trading US Stocks: A Brutally Honest, Evidence-Based Evaluation

## Overview

"Smart money" signals attempt to infer the intentions of informed or institutional traders from observable data — option flow, insider filings, fund holdings, short interest, and off-exchange prints — and use those inferences to predict the underlying stock over a swing horizon (a few days to one month). This report evaluates six signal families specifically for a **signal-only, manual-execution** system trading US single-name equities on the swing timeframe, with a small-but-scaling account and no institutional data budget.

The blunt overall takeaways:

1. **The signals with the strongest, most replicated academic support are insider buying (especially opportunistic, clustered buys) and short-interest/borrow-cost effects.** Both have decades of peer-reviewed evidence, are largely free or cheap, and operate on horizons compatible with swing trading.
2. **Options-derived signals split sharply.** The genuinely predictive option signals (volatility skew/smirk, put-call-parity implied-volatility spread) require computed metrics from full option chains, while the publicly-observable raw flow signals (put/call volume) decay within 1–2 days. Most retail "unusual options activity" (UOA) alert products oversell a real but weak and noisy edge.
3. **Two families are largely marketing relative to their hype: dark-pool "sentiment/print" products and most UOA alert services.** The underlying data is real, but the directional interpretation sold to retail is not supported.
4. **13F cloning is a timeframe mismatch for swing trading** — the 45-day-plus reporting lag makes it useless for a days-to-weeks horizon, though it has mild value for longer holds.

A unifying theme: the *direction* of an informed trade is usually the hard part. Option flow doesn't tell you whether a print is opening or closing, a hedge or a bet, one leg of a spread or a standalone position. Insider buying is the rare signal where the direction is unambiguous — an executive writing a personal check to buy stock does it for one reason.

---

## 1. Unusual Options Activity (UOA): sweeps, blocks, large orders

### Predictive value (swing timeframe)

The academic foundation is real but narrower than marketers imply. Jun Pan and Allen Poteshman ("The Information in Option Volume for Future Stock Prices," *Review of Financial Studies*, 2006) found that option volume contains information about future stock prices — but crucially, that **most of the predictive power comes from signed buy-to-open volume data that is NOT publicly available.** Their key warning: "publicly observable option signals are able to predict stock returns for only the next one or two trade days," and those moves subsequently reverse, suggesting price pressure rather than information. This is a direct hit against retail UOA: by the time you see the flow and act manually, the one-to-two-day edge is largely gone.

There is genuine evidence that *certain* UOA matters. Informed traders are demonstrably more active in options before scheduled news (earnings, M&A). Studies of M&A targets find abnormally high pre-announcement option volume. A recent finance-school study (Cuyler Strong, Wayne State) found that while large option trades are *in general not predictive*, a specific subset — large trades in options near expiration that have not yet reached their strike — is associated with statistically significant positive abnormal returns.

The core problems for a swing trader:
- **Opening vs. closing is unknown.** A large call buy could be opening a bullish bet or closing a short call / monetizing a hedge.
- **Hedging flow contaminates the signal.** A big put buy may be portfolio insurance, not a directional view.
- **Multi-leg strategies look like directional bets.** One leg of a spread, collar, or roll appears on the tape as a standalone aggressive order.
- **Latency.** The informational half-life is 1–2 days per Pan-Poteshman; manual retail execution rarely captures it.

**Verdict:** Real but weak and fast-decaying on the swing timeframe. Best used as a *confirmation/context* overlay around catalysts (earnings, FDA, M&A rumors), not as a standalone swing entry trigger. The marketing ("follow the smart money") substantially oversells it.

### Access / cost

- **Free / cheap:** Barchart and many brokers show unusual options volume and volume-vs-open-interest. OptionStrat Flow offers free flow with a 15-minute delay (~10% of total flow shown).
- **Paid retail UOA services:** Cheddar Flow (~$85–99/month), FlowAlgo (~$99–149/month, with reported 15-minute delay on some data), Unusual Whales (~$49–149/month), BlackBox Stocks (~$99.97/month). Independent reviews are candid that these are "intelligence, not a signal service." The "~90% of options traders lose money" claim repeated across these reviews is an industry rule-of-thumb, not a peer-reviewed statistic; the rigorous evidence on retail options losses comes from academic work (MIT Sloan's Eric So and co-authors document that retail options buyers incur bid-ask spreads effectively amounting to 9–10% of their investment, and a London Business School study found retail traders lost upward of US$2 billion in options premium from 2019–2021). Note that you are NOT trading options — so these are pure signal inputs, which is the appropriate use, but the value proposition is weak for the price on a small account.

---

## 2. Options Metrics: put/call ratio, IV rank/percentile, IV crush, open interest, skew, GEX

### Predictive value (swing timeframe)

**Put/Call ratio (P/C):** As a *contrarian sentiment* indicator at extremes it has modest support — Simon & Wiggins and others found P/C, VIX and TRIN have statistically significant contrarian forecasting power for the S&P over 10–30 day horizons. But Pan & Poteshman's caution applies: publicly available P/C predicts only 1–2 days for individual stocks. Volume-based P/C works on very short horizons (~2.5 days); open-interest P/C is slower (~12 days). Equity vs. index distinction matters: there is little evidence of informed trading in index options (more hedging), so index P/C is better treated as contrarian sentiment, equity P/C as weak directional.

**Implied volatility, IV rank/percentile, IV crush:** IV is a forecast of *magnitude, not direction.* It does not predict which way a stock moves. Its swing-relevant uses: (1) IV rank/percentile tells you whether options are historically cheap/expensive — relevant if you ever overlay option-based hedges, but for a stock-only trader it mainly flags expected event volatility; (2) IV crush around earnings is highly predictable — IV inflates pre-earnings and collapses after — which matters if holding through earnings. For a stock swing trader, elevated IV rank is mainly a *risk warning* (a large move is priced in) rather than a directional signal.

**Volatility skew/smirk:** This is one of the genuinely predictive option metrics. Xing, Zhang & Zhao ("What Does Individual Option Volatility Smirk Tell Us About Future Equity Returns?", *JFQA*, 2010, 45:3, pp. 641–662) found that "Stocks exhibiting the steepest smirks in their traded options underperform stocks with the least pronounced volatility smirks in their options by 10.9% per year on a risk-adjusted basis. This predictability persists for at least 6 months" — a horizon that comfortably includes swing trades. Steepest-smirk firms also had the worst subsequent earnings shocks. This is consistent with informed pessimists buying OTM puts.

**Implied volatility spread / put-call parity deviations:** Cremers & Weinbaum ("Deviations from Put-Call Parity and Stock Return Predictability," *JFQA*, 2010, 45:2, pp. 335–367) found that "stocks with relatively expensive calls outperform stocks with relatively expensive puts by 50 basis points per week" (51 bps in the SSRN working-paper version) — a weekly-horizon signal well-suited to swing trading. Doran & Krieger found this measure subsumes many other option signals. Caveat: a competing paper (Goncalves-Pinto et al.) argues part of the effect is stock-price-pressure-driven, not pure information.

**Open-interest changes:** Rising OI alongside volume confirms new positioning rather than closing; useful as a contextual filter but not a standalone signal.

**Gamma exposure (GEX) / dealer positioning:** This is heavily marketed (SpotGamma coined the retail term; products from InsiderFinance, etc.). The honest read from the peer-reviewed literature: **GEX is a genuine INTRADAY volatility-regime signal, not a swing-timeframe directional signal.** Baltussen, Da, Lammers & Martens ("Hedging Demand and Market Intraday Momentum," *Journal of Financial Economics*, 2021, 142:1, pp. 377–403) show that short-gamma hedging creates *intraday* momentum (the day's return predicts the last-30-minute return) — and critically this effect "reverts over the next days," the opposite of a swing follow-through. The asset studied is index/futures, not individual stocks. Ni, Pearson & Poteshman (*JFE*, 2005) document expiration-day price clustering ("pinning") that alters optionable-stock returns by ~16.5 bps — a same-day magnet effect. Ni, Pearson, Poteshman & White (*RFS*, 2021) find option-hedge rebalancing accounts for on the order of 13% of the daily absolute return of optioned stocks (on all days, not just expiration week) — but the effect is on *volatility/magnitude, explicitly non-directional.* The one multi-day single-stock result, Soebhag ("Option Gamma and Stock Returns," *Journal of Empirical Finance*, 2023), finds high-net-gamma stocks underperform low-net-gamma stocks by ~10%/year — but this is a cross-sectional *volatility-risk-premium* (low-gamma stocks are riskier and earn compensation), not a dealer-positioning directional-timing signal. SpotGamma's headline "78% of days SPX closes inside predicted range" is self-published marketing (a single-day volatility-range claim, internally inconsistent with the "76%" on its own stats page) and is not independently verified; SpotGamma itself concedes "high volatility does not predict direction, just magnitude." GEX is also far less reliable for small/mid-cap single names with thin option markets.

**Verdict:** Skew/smirk and the IV spread are the genuinely useful, swing-compatible option metrics. P/C is weak/contrarian-at-extremes. IV rank/crush are risk/timing context, not direction. GEX is an intraday volatility-regime tool, largely a timeframe mismatch for swing direction.

### Access / cost

- **Free:** CBOE publishes daily equity/index P/C ratios. Barchart shows IV rank/percentile free. thinkorswim/Schwab shows IV percentile, skew, and option statistics free to account holders. Skew and IV-spread can be computed from any free option chain with some effort.
- **Paid:** ORATS, LiveVol, IVolatility for clean historical IV surfaces and skew. SpotGamma/GEX products (~$30–100+/month) for pre-computed dealer-gamma levels — of limited value to a stock-only swing trader given the intraday/volatility nature of the signal.

---

## 3. Insider Buying/Selling via SEC Form 4

### Predictive value (swing timeframe)

This is the single best-supported "smart money" signal, with a well-documented buy/sell asymmetry:

- **Seyhun (1986, 1998):** insiders' purchases are more informative than sales; litigation risk discourages selling on negative private info.
- **Lakonishok & Lee ("Are Insider Trades Informative?", *Review of Financial Studies*, 2001, 14:1, pp. 79–111):** across all NYSE/AMEX/Nasdaq trades 1975–1995, "firms with extensive insider purchases during the prior six months outperform companies with extensive insider sales by 7.8% over the next 12 months. After controlling for size and book-to-market effects, the spread in returns decreases to 4.8%." The effect is concentrated in smaller firms, and insider *sales* show no meaningful underperformance (most sales are diversification/tax/liquidity driven). Predictive content rises when *multiple* insiders buy.
- **Cohen, Malloy & Pomorski ("Decoding Inside Information," *Journal of Finance*, 2012, 67:3):** the key refinement. Splitting insiders into "routine" (calendar-predictable) and "opportunistic" traders, only opportunistic trades predict returns — a long-short strategy on opportunistic trades "earns value-weight abnormal returns of 82 basis points per month (9.8 percent annualized, t=2.15), and equal-weight abnormal returns of 180 basis points per month (21.6 percent annualized, t=6.07)," while routine trades earn essentially zero. Opportunistic trades also predict future firm news.

**Timeframe fit:** The documented abnormal returns accrue over weeks to 12 months, with meaningful drift in the weeks after the filing. Form 4 must be filed within two business days of the trade, so the *information lag is short* — compatible with swing and position trades, though much of the abnormal return is captured over 1–12 months rather than days.

**Swing-relevant best practices supported by the literature:**
- **Cluster buys** (≥3 insiders buying within ~30 days) are the highest-conviction signal.
- **Role matters:** CEO/CFO purchases (especially equal to ≥1 year of salary, near 52-week lows) outweigh a single director's token buy.
- **Open-market purchases (transaction code P)** only — ignore option-exercise/grant noise.
- **Check the 10b5-1 flag:** pre-scheduled plan sales carry little information; discretionary sales are more informative (but still weakly so).
- A 2025 microcap study (arXiv) found the distance-from-52-week-high feature dominated, and counterintuitively, purchases disclosed *after* >10% price appreciation produced the highest abnormal returns — trend-confirming insider buys outperformed simple "buy-the-dip" insider buys.

**Verdict:** Genuinely useful, with the best academic pedigree of any signal here. The buy signal (clustered, opportunistic, senior-insider, open-market) is the highest-quality input in this entire report. Insider *selling* is mostly noise.

### Access / cost

- **Free:** SEC EDGAR (raw Form 4 XML, full-text search). OpenInsider.com — widely considered the best free aggregator, with preset "cluster buys," "CEO/CFO buys," "largest buys" views, updated within hours. Finviz and Yahoo Finance show recent insider transactions on stock pages.
- **Cheap paid / API:** SecForm4 (~$50/month tiers), Apify scrapers (~$0.10/alert), QuiverQuant, various real-time alert tools (~$5–50/month). For a small account, the free stack (EDGAR + OpenInsider) is fully sufficient.

---

## 4. Institutional 13F Filings

### Predictive value (swing timeframe)

**For swing trading: essentially useless due to timeframe mismatch.** 13Fs disclose long US equity positions as of quarter-end, filed up to 45 days later (and many filers wait until the very last day). By publication the positioning is 45–135 days stale. The honest framing: "by the time 13F filings reveal institutional positioning, the majority of the informational value has already evaporated" for fast strategies; alpha-decay studies (Di Mascio, Lines & Naik) imply a roughly four-month half-life.

Structural limits compound the lag:
- **Long-only US equities; no shorts, no most derivatives** (only long puts/calls reported, at notional that obscures intent). A reported 5% long could be fully hedged by invisible shorts/swaps.
- **No intra-quarter activity** — you see a snapshot, not the path.
- **Strategic delay / window-dressing:** Musto et al. find institutions deliberately use the lag to trade before front-runners; some funds window-dress holdings near reporting dates.
- **Survivorship:** "clone the best funds" backtests are contaminated by selecting funds known *ex post* to have survived and outperformed.

**Where 13F has *some* value (NOT swing):** Selectively cloning low-turnover, high-conviction managers can work for *long-horizon* holds even after the lag. Cohen, Polk & Silli ("Best Ideas") found managers' highest-conviction positions outperform; Angelini, Iqbal & Jivraj ("Systematic 13F Hedge Fund Alpha," 2019) built a conviction+consensus strategy on *longer-term-view* managers that beat the S&P 500 by ~3.8%/yr (Sharpe ~0.75) — but explicitly only after filtering out high-turnover funds whose data is stale on arrival. None of this is swing-compatible.

**Verdict:** Strong timeframe mismatch. For a days-to-one-month system, treat 13Fs as background context on who owns a name, never as a swing trigger.

### Access / cost

- **Free:** SEC EDGAR. Aggregators WhaleWisdom (with a backtester), HedgeFollow, Dataroma display holdings free; premium tiers add tools.

---

## 5. Short Interest, Days-to-Cover, and Squeeze Setups

### Predictive value (swing timeframe)

Two distinct effects, often conflated:

**(a) High short interest as a bearish signal.** Decades of evidence (Figlewski 1981; Senchack & Starks 1993; Asquith, Pathak & Ritter 2005; Boehmer, Jones & Zhang 2008; Rapach, Ringgenberg & Zhou 2016) show high short interest *predicts negative abnormal returns* — short sellers are informed (predominantly sophisticated institutions). This effect can be transient and is strongest in hard-to-borrow, high-short-selling-risk names. Engelberg, Reed & Ringgenberg show the predictive power is much stronger in the presence of news.

**(b) Squeeze fuel.** High short interest is *necessary but not sufficient* for a squeeze. The same crowded short that signals informed pessimism is also the fuel that, given a catalyst, forces covering. The two readings coexist: most of the time crowded shorts are "right" (negative drift); occasionally a catalyst flips it into a violent squeeze.

**Timeliness is the central problem.** FINRA short interest is reported twice monthly — firms must report by 6 p.m. ET on the second business day after the designated settlement date, and FINRA then consolidates and disseminates the data publicly, generally on the **eighth business day after the reporting settlement date**. So by publication the data can be roughly two weeks old. Days-to-cover (short interest ÷ avg daily volume) is derived from this lagged number.

**More timely, more predictive signals:** Cost-to-borrow (loan fee) and **utilization** (% of lendable inventory on loan) update daily and are stronger predictors. Boehmer, Huszár, Wang & Zhang (2018, 38 countries) found **days-to-cover and utilization** were the two most successful short-selling return predictors. Research on squeeze prediction (the borrow-market literature) finds **utilization is the single best predictor of short squeezes** — squeezes occur from loan recalls when nearly all lendable supply is out. Borrowing-fee-based long-short strategies have produced large returns with high Sharpe ratios. Option-implied borrow fees can even subsume short interest in predicting returns.

**Verdict:** Genuinely useful and swing-compatible — but the *free* FINRA short interest is too lagged to be the primary trigger. The real edge is in daily cost-to-borrow/utilization. The "squeeze trifecta" heuristic (SI >20% of float, days-to-cover >5, rising/elevated borrow fee) is a reasonable screen, but squeezes remain rare and hype-prone; treat squeeze-chasing as low-probability/high-variance, and high-SI-as-bearish as the more reliable everyday read.

### Access / cost

- **Free:** FINRA publishes bi-monthly short interest for all equities. Exchanges (Nasdaq, NYSE) and Cboe republish it. Finviz/Yahoo show short interest and days-to-cover. These are all lagged.
- **Paid (the timely edge):** Borrow-rate/utilization data from S3 Partners, Ortex, Fintel, ShortInterestTracker, and Interactive Brokers' borrow data (IBKR shows borrow fees/availability to account holders — a cheap route). Daily borrow data is where the actual swing edge lives; budget tools (Fintel/Ortex, ~$25–60/month) are accessible to a small account.

---

## 6. Dark Pool Activity and Large-Block Prints

### Predictive value (swing timeframe)

**This is the family most oversold to retail relative to its evidence.** Key facts:

- **A dark pool print is not inherently bullish or bearish.** It is a trade matched off-exchange with no displayed quote; every print has a buyer and a seller. You generally cannot tell which side was the aggressor or whether it was a hedge, an index rebalance, or portfolio restructuring. Marketing that treats a large print as a bullish "institutional accumulation" signal is unsupported.
- **FINRA ATS data is heavily lagged and coarse.** Under Rule 4552, ATSs report *weekly* aggregate volume by security, published on a delay (roughly two weeks for the relevant tier). It contains no price, no timestamp, no side. As one description puts it, "the insight gained is historical, not predictive of the immediate moment." Real-time "dark pool prints" sold by vendors are reconstructed from the consolidated tape (trades print to a Trade Reporting Facility within seconds), not from a special data feed.
- **Academic evidence points the *opposite* way from the marketing.** Brogaard & Pan ("Dark Pool Trading and Information Acquisition," *Review of Financial Studies*, 2022, 35:5, pp. 2625–2666) find more dark trading is associated with *greater information acquisition* and more firm-specific information in prices (measured around earnings) — i.e., dark pools host informed trading, but this is a market-quality finding about price *informativeness*, not a tradable retail "follow the prints" signal. Benefits also diminish/reverse at high levels of dark trading. None of this validates "dark pool index" sentiment products as swing predictors.
- **False signals are common** — many dark pool volume spikes are index rebalancing or other non-predictive flows. Correlation with subsequent moves is not universal.

**Verdict:** Largely marketing for swing-trading purposes. The data is real and academically interesting, but the directional, retail-facing interpretation (prints as support/resistance, "dark pool sentiment") lacks empirical support and the official data is too lagged/coarse to trade on a swing horizon. Lowest genuine usefulness of the six families, tied with 13F.

### Access / cost

- **Free:** FINRA ATS Transparency / OTC Transparency data (weekly, lagged, flat files; finra.org). Requires processing.
- **Paid:** TradeAlgo, Cheddar Flow, FlowAlgo, BlackBox and similar bundle "real-time dark pool prints" (reconstructed from the tape) into ~$85–150/month subscriptions. For a stock-only swing trader, low value relative to cost.

---

## Pitfalls (cross-cutting traps)

1. **Lookahead / lag bias.** 13F (45–135 days), FINRA short interest (~2 weeks), and FINRA ATS (~2 weeks) are all stale on arrival. Backtests that use "as-of-quarter-end" or "as-of-settlement" data instead of *publication date* dramatically overstate returns. Always align to when YOU could have acted.
2. **Opening vs. closing trades.** Option flow (and block prints) don't reveal whether a position is being opened or closed. A "bullish" call sweep may be someone closing a short call.
3. **Hedging-flow misreads.** Large put buys, index-option P/C, and many dark-pool blocks are hedges or rebalances, not directional bets. Index options especially are hedging-dominated (little informed trading).
4. **Multi-leg strategy fragments.** Spreads, collars, rolls, and combos print as individual aggressive orders; reading one leg as a standalone directional bet is a classic UOA error.
5. **Contrarian vs. directional confusion.** P/C at extremes is contrarian (high puts → bullish); but equity-level P/C also has weak *directional* informed-trading content. Mixing the two interpretations produces garbage.
6. **Magnitude vs. direction.** IV, IV rank, and GEX forecast *how much* a stock/market may move, not *which way*. Treating high IV or a GEX flip as directional is a category error.
7. **Overfitting to alerts.** UOA/flow services generate thousands of alerts; cherry-picking the winners ex post creates an illusion of edge. Track ALL alerts' forward returns, not the screenshots vendors post.
8. **Survivorship & window-dressing in 13F.** "Clone the legends" ignores funds that blew up; quarter-end window dressing distorts the snapshot.
9. **Short-data conflation.** High short interest is usually bearish (informed shorts), only occasionally squeeze fuel. Don't treat every heavily-shorted stock as a squeeze candidate. And don't trade on lagged bi-monthly SI when daily utilization/borrow tells a fresher story.
10. **Routine vs. opportunistic insiders.** Over half of insider trades are calendar-routine and carry essentially zero predictive power; failing to filter them (and 10b5-1 plan sales) dilutes the strong opportunistic-buy signal.
11. **Small-cap/thin-option caveats.** GEX and option-flow signals are unreliable where option markets are thin; insider/short effects are *stronger* in small caps, but so are liquidity/borrow constraints and manipulation risk.

---

## Summary Table

| Signal | Data needed | Free vs. paid access | Swing usefulness (0–100) |
|---|---|---|---|
| **Insider buying (Form 4, opportunistic/cluster)** | Open-market P-code buys; insider role; 10b5-1 flag; cluster detection | **Free** (SEC EDGAR, OpenInsider); cheap APIs optional | **80** |
| **Volatility skew/smirk & IV spread (put-call parity)** | Full option chain IVs (OTM put vs ATM call; ATM call vs put) | Mostly **free** to compute (broker chains, CBOE); paid for clean surfaces (ORATS) | **65** |
| **Short interest + cost-to-borrow/utilization** | Bi-monthly SI + days-to-cover (free); **daily borrow fee & utilization (paid)** | SI **free** (FINRA/exchanges); borrow/utilization **paid** (Ortex/Fintel/S3, IBKR) | **62** |
| **Unusual options activity (flow/sweeps/blocks)** | Real-time signed flow, size, expiry, OI context | Limited **free** (Barchart, OptionStrat delayed); **paid** alert services | **38** |
| **Put/call ratio + IV rank/crush + open interest** | Daily equity/index P/C; IV rank/percentile; OI changes | **Free** (CBOE, Barchart, broker platforms) | **35** |
| **Gamma exposure (GEX) / dealer positioning** | Full chain OI by strike; dealer-positioning model | Some **free** calculators; **paid** (SpotGamma) | **22** |
| **13F institutional holdings / cloning** | Quarterly long-equity holdings by manager | **Free** (EDGAR, WhaleWisdom, Dataroma) | **15** |
| **Dark pool activity / block prints** | ATS weekly volume (lagged); tape-reconstructed prints | ATS **free** (FINRA, lagged); **paid** real-time products | **15** |

*(Sub-scores reflect genuine predictive usefulness on the days-to-one-month timeframe for a small retail, signal-only, stock-only system — weighing strength of evidence, timeframe fit, signal-to-noise, and accessibility/cost.)*

---

## Recommendations

**Stage 1 — Build the free, high-evidence core first (do this before paying for anything):**
- Make **opportunistic insider cluster buys** your primary "smart money" trigger. Screen OpenInsider/EDGAR daily for: ≥2–3 insiders, open-market (code P), senior roles (CEO/CFO), non-10b5-1, ideally near multi-month lows or confirming an uptrend. This is the highest-quality, free signal in the report (Cohen-Malloy-Pomorski: 82 bps/month for opportunistic trades; Lakonishok-Lee: 4.8% risk-adjusted buy-vs-sell spread over 12 months).
- Add **volatility skew/smirk and the IV (put-call) spread** as a secondary directional overlay, computed from free broker option chains: steep put skew / expensive puts = caution/bearish; expensive calls = bullish tilt (Cremers-Weinbaum: 50 bps/week; Xing-Zhang-Zhao: smirk effect 10.9%/yr, persists 6 months).
- Use **free FINRA short interest** plus **IBKR borrow fees/availability** (cheap, if you have an IBKR account) to flag high-short-interest names and rising borrow costs.

**Stage 2 — Add one paid data source where the edge is real and timely (when the account can justify ~$25–60/month):**
- Prioritize **daily cost-to-borrow / utilization** (Ortex, Fintel, or S3) over any flow product. This is where short-side evidence concentrates and the data is fresh. Utilization is the best squeeze predictor; borrow fee is a strong return predictor.

**Stage 3 — Only if you have surplus budget and a tested process, trial (don't commit to) a flow tool:**
- A UOA/flow subscription (use the free trials) is justified *only* as catalyst-window confirmation (earnings/M&A), and only if you log every alert's forward return to verify it adds anything over your free core. Expect a weak, fast-decaying edge.

**What to skip for swing trading:**
- **13F cloning** as a swing trigger (timeframe mismatch — fine as ownership context only).
- **Dark-pool "sentiment/print" products** as directional signals (unsupported; data lagged/coarse).
- **GEX products** as single-stock swing-direction signals (it's an intraday volatility-regime tool).

**Benchmarks that would change these recommendations:**
- If FINRA moves short-interest reporting to **weekly/daily** — a proposed amendment to Rule 4560 was published in the Federal Register on May 18, 2026 (document 2026-09864), with eight commenters supporting weekly frequency — free short data would rise materially in usefulness and could displace paid borrow data for many names.
- If you begin **holding positions 1–3 months**, raise the weight on insider signals and selective 13F best-ideas cloning; the longer horizon better matches their documented alpha decay.
- If you log a flow tool's alerts for ~50–100 trades and forward returns are indistinguishable from random, cancel it — the prior is that it won't beat the free core.
- If you scale into **less-liquid small caps**, downweight GEX/flow (thin options) and upweight insider/short signals (stronger there), while respecting wider spreads and manipulation risk.

---

## Caveats

- **Cross-sectional, risk-adjusted, often value-weighted academic returns ≠ what a small retail account nets.** The cited abnormal returns (82 bps/month opportunistic insiders, 10.9%/yr smirk, 50 bps/week IV spread) come from diversified long-short portfolios with institutional execution; transaction costs, spreads, and concentration in a small manual book will erode them substantially.
- **Many effects are strongest in small caps**, exactly where spreads, borrow constraints, and manipulation risk are highest — the evidence and the executability pull in opposite directions.
- **Signals decay as they popularize.** Some insider/short effects have weakened post-publication and post-2008; flow and GEX edges are arbitraged quickly.
- **Marketing vs. evidence gap:** UOA alerts, dark-pool sentiment, and GEX products are sold with far more confidence than the peer-reviewed literature supports. The disputed mechanism behind the IV-spread effect (information vs. price pressure, per Goncalves-Pinto et al.) is a reminder that even "good" signals are contested.
- **This report covers signal predictive value, not full system design.** Position sizing, stops, catalyst calendars, and risk management determine whether even a real edge survives — none of which any single "smart money" signal provides.
- **Not investment advice.** Validate every signal on your own out-of-sample data before risking capital.