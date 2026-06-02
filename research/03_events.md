# Event-Driven Catalysts for a US Swing-Trading Signal Engine

## TL;DR

- **The two strongest, still-usable swing catalysts are post-earnings-announcement drift (PEAD) and analyst estimate-revision/guidance momentum** — both are best traded by entering *after* the catalyst and riding the drift 2–6 weeks; the single most important small-account rule is to never hold a binary event (earnings, FDA decision) through the announcement because of uncontrollable overnight gap risk.
- **Most documented edges have decayed and are largest precisely in illiquid small-caps where slippage eats the profit** (Chordia et al. found transaction costs consume 70–100% of PEAD profit in illiquid names; the S&P 500 index-inclusion abnormal return has collapsed from ~7.4% in the 1990s to ~0.3% in the last decade). Favor liquid names and treat academic magnitudes as upper bounds.
- **Tradability ranking (0–100):** PEAD (82) and estimate revisions (78) are core; buybacks (58), dividend initiations/cuts (55), spinoffs (52) are secondary; FDA/biotech (48, run-up only) and M&A targets (38) are specialist/avoid; index inclusion (30), stock splits (25), and product launches (22) are weak/decayed.

## Key Findings

1. **PEAD is the anchor signal.** Bernard & Thomas (1989, 1990) showed prices drift in the direction of the earnings surprise for ≥60 trading days, with ~25–30% of the drift concentrated around the next three quarterly announcements. The clean, repeatable, gap-risk-free way to trade it is to enter *after* the print and ride 20–60 days — not to gamble through the announcement.
2. **Estimate-revision momentum drives much of PEAD and is still robust.** "Beat-and-raise" is the highest-conviction setup; "beat but guidance cut" rarely produces sustained upside.
3. **Binary events are account-killers for small accounts.** Biotech FDA decisions and earnings can gap 10–60%+ overnight; only the *pre-catalyst run-up* (with a hard exit before the event) or the *post-catalyst drift* are risk-controllable.
4. **Several "famous" edges have largely disappeared:** the S&P 500 index effect, stock splits, and product-launch reactions are weak or near-zero on average.
5. **Calendar data quality is itself a risk:** estimated vs confirmed earnings dates, and the fact that the FDA does not publish PDUFA dates (all calendars aggregate company disclosures), are the two biggest data-reliability traps.

## Details

### Overview and two cross-cutting truths

This report maps eight catalyst categories to a swing-trading signal engine for US single stocks — holds of a few days to one month, percentage-based rules, signal-only, small but scaling account. Two truths shape everything: (1) many edges have **decayed** as they became widely known and as liquidity/trading costs fell (PEAD and the index effect are the clearest cases); (2) most academic magnitudes were measured on **equal-weighted or small-cap-tilted portfolios** where the effect is largest but illiquidity and slippage are worst — exactly the names a small account *can* trade but where the net edge erodes. Treat published magnitudes as ceilings.

### 2.1 Earnings — PEAD, the earnings-announcement premium, and gap risk

**PEAD** is the best-documented anomaly in finance. Ball & Brown (1968) first observed it; Bernard & Thomas (1989, 1990) formalized it, showing the top-vs-bottom standardized-unexpected-earnings (SUE) decile spread was positive in 41 of 48 quarters (1974–1985), drift persisting ≥60 trading days, with ~25–30% concentrated in three-day windows around subsequent earnings. Zero-investment SUE portfolios earned ~8–9% per quarter before costs. Direction: prices drift in the direction of the surprise (up for beats, down for misses); the effect is stronger in smaller firms.

**The edge has decayed.** Chordia, Subrahmanyam & Tong (2014) and others document PEAD weakening toward insignificance in the most liquid US stocks, attributing it to improved liquidity, lower costs, and arbitrage. Critically, Chordia et al. (*Financial Analysts Journal*) found **transaction costs consume 70–100% of PEAD profits** because the drift concentrates in illiquid stocks; a long-only top-SUE-decile strategy earned ~90 bps/month (~10% annually) gross over 1972–2005. Implication: the drift is largest exactly where a small trader faces the worst slippage — so favor liquid mid-caps to capture *some* drift without paying it all back in spread.

**Earnings-announcement premium (pre-earnings).** Frazzini & Lamont (2007, NBER WP 13090) document that stocks on average rise around scheduled announcements: "monthly strategies earning excess returns of between 7% and 18% per year, with Sharpe ratios larger than other popular anomalies," driven by attention-based small-investor buying and high announcement-period volume. The international replication (Barber et al.) pegs the US premium at over 7% per year (~59.7 bps/month). This is a real *average* edge — but for any single name the outcome is binary.

**IV crush and gap risk.** Implied volatility rises into earnings and collapses 30–70% overnight afterward ("IV crush"), which is why long options into earnings usually lose even when direction is right. For a stock position the danger is the overnight gap, which no intraday stop can protect against.

**Enter before vs after?** For a signal-only small account: **enter AFTER the print** to harvest PEAD. Holding through earnings is a binary bet with uncontrollable gap risk; the cleaner, repeatable edge is to let the surprise resolve, confirm direction/magnitude (gap + SUE + guidance), then ride the drift 20–60 days.

**Data needed:** consensus EPS/revenue estimates, actual reported EPS/revenue (for SUE/surprise), guidance, earnings date with BMO/AMC timing, opening gap, post-print analyst revisions.

### 2.2 Guidance changes and analyst estimate revisions

Estimate-revision momentum is among the most robust still-usable edges. Givoly & Lakonishok, Stickel, Womack (1996), and Chan, Jegadeesh & Lakonishok show stocks with the largest upward EPS revisions outperform those with the largest downward revisions over 6–12 months, drifting because analysts update slowly ("conservatism"). Mill Street Research confirms estimate-revision breadth still forecasts relative returns, enhanced when combined with price momentum and valuation. Revisions trickle in over 2–4 weeks after a report — the mechanism behind much of PEAD.

The most powerful single setup is **beat-AND-raise**: beating and raising forward guidance forces analysts to revise models upward across the board. "Beat but guidance cut" rarely produces sustained upward drift; **guidance withdrawal** is strongly negative (loss of visibility). Drift unfolds over weeks, fitting the swing window. **Enter AFTER** the revision is visible — the signal *is* the revision. **Data needed:** consensus estimate time series, guidance text, count/breadth of revising analysts, price-target changes.

### 2.3 Dividends, splits, and buybacks

**Dividend initiations/omissions** are genuine signaling events with multi-week drift. Michaely, Thaler & Womack (1995, *Journal of Finance* 50(2):573–608) found a ~3.4% average excess announcement return for initiations and ~−7.0% for omissions, and quantified the *drift*: in the 12 months after (excluding the event month) there is a significant positive market-adjusted return of **+7.5% for initiations and −11.0% for omissions**, with a long-initiations/short-omissions rule earning positive returns in 22 of 25 years. Routine *increases/declarations* by already-paying firms are mostly anticipated and weak. **Ex-dividend mechanics:** the stock drops by roughly the dividend amount on the ex-date — mechanical, not an edge; do not trade it as a signal.

**Stock splits** carry a modest positive announcement/attention effect (a few percent; Ikenberry et al. documented positive abnormal returns) but it is small, a signaling artifact, and has decayed — among the weakest catalysts.

**Buybacks.** Ikenberry, Lakonishok & Vermaelen (1995) is the landmark: open-market repurchase announcements earn a positive announcement return (~3% short-term) and long-horizon drift (~12% buy-and-hold abnormal over four years, strongest for low market-to-book firms); Peyer & Vermaelen (2009) confirmed it, and a ~2.4% 30-day abnormal return is documented. **But** post-2001 long-horizon abnormal returns are much lower, with many buybacks now driven by management compensation rather than undervaluation. For swing trading, the pop plus a multi-week drift is tradable but modest; favor low-valuation firms with large authorizations relative to market cap.

**Enter:** AFTER announcement for buybacks/initiations/cuts. **Data needed:** dividend declaration/ex/record/pay dates, amount and history, split announcements/ratios, buyback authorization 8-Ks with size vs market cap.

### 2.4 Mergers & Acquisitions

On announcement the target jumps toward (but below) the offer price; the residual is the **arbitrage spread**, compensation for deal-failure risk. Per the standard sample (summarized in Van Tassel, NY Fed Staff Report 761), "the median target stock price jumps 27% after the announcement and trades at a 3.5% spread" to the offer. Mitchell & Pulvino (2001), analyzing 4,750 deals (1963–1998), found risk-arbitrage earned **annual abnormal returns of 9.25% excluding transaction costs but only 3.54% including them** (the portfolio's raw annualized return was ~6.2%), with payoffs resembling **selling uncovered index puts** — fine in normal/rising markets, large losses in severe down markets. ~90–95% of announced US deals complete; typical spreads run 3–10% gross, ~7–12% annualized for diversified pros (the 2024 opportunity set averaged ~10.9% effective yield).

**For a small swing account, M&A is mostly NOT an edge.** The target's big move happens in the first seconds; by the time retail sees it, the residual is a low-single-digit return over months with catastrophic break risk (Mitchell & Pulvino: arbitrageurs earned ~2% on successful deals but lost ~2.8% on canceled ones). The negative skew ("pennies in front of a bulldozer") is poorly suited to a concentrated small account. Acquirers typically dip modestly (especially in stock deals). Break risk concentrates in antitrust-scrutiny deals (e.g., Kroger/Albertsons, blocked Dec 2024) and non-credible buyers. **Enter:** only cash deals, high closing probability, acceptable annualized spread; avoid wide-spread "cheap" deals. **Data needed:** offer terms (cash/stock), current target price (spread), expected close, regulatory status, acquirer financing.

### 2.5 Spinoffs

Cusatis, Miles & Woolridge (1993) found spinoffs and parents outperformed benchmarks by ~10%/year and ~6%/year over the three post-spin years (1965–1988), much tied to elevated takeover activity. Later work (McConnell, Ozbilgin & Wahal 2001) found weaker, outlier-sensitive results. There is often a ~15-day window of slightly negative returns immediately post-spin (forced selling by holders who don't want the small entity), turning positive after ~60 days. This is a multi-month-to-multi-year edge; the swing-tradable piece is the post-spin forced-selling dip and recovery. **Enter:** AFTER the spin, buying first-weeks weakness. **Data needed:** Form 10 / 10-12B SEC filings, record/distribution dates, when-issued trading, index implications.

### 2.6 Index inclusions/deletions

The classic "index effect" has **structurally collapsed.** Greenwood & Sammon, "The Disappearing Index Effect" (*Journal of Finance* 80(2), April 2025, pp. 657–698), find **the abnormal return on S&P 500 addition fell from an average of 7.4% in the 1990s to 0.3% over the past decade**, with deletions at just −0.1% (2010–2020) and the 2010s direct-inclusion average at −0.6% (ex-Tesla, the 2020 inclusion effect was −3 basis points). They attribute the decline mainly to increased liquidity and the rise of cross-index migrations (a stock added to the S&P 500 is usually dropped from the S&P 400/600 at once, offsetting demand). Worse, Morningstar/academic work (Sandifer et al.) finds added firms *underperform* matched peers over 1–5 years (−28% at one year, −55% at five) — inclusion marks a performance peak, a potential long-run *sell* signal. **Tradable remnant:** only the small, crowded mechanical demand between announcement (after close, ~5 trading days before effective) and the effective-date close, plus a "buy the rumor, sell the rebalance" fade. **Enter:** day after announcement, exit at/near effective-date close. **Data needed:** S&P DJI press releases, added ticker, float/AUM context.

### 2.7 FDA / regulatory decisions (biotech)

Biotech catalysts are the highest-volatility, most binary events. Singh, Rocafort, Cai, Siah & Lo (2022, *PLOS One*), an event study of 13,807 trials, found early-stage biotech firms show by far the largest abnormal returns, with Phase 3 and 2/3 readouts moving stocks most. Rothenstein et al. found a +27% vs −4% spread between Phase 3 winners and losers in the run-up window. Hwang (2013) found median cumulative abnormal returns of +0.8% (positive) vs −2.0% (negative) in *large* biopharma — muted by diversification — with **asymmetric reactions: failures hit harder and persist longer.** Recent work on 2011–2019 Phase 3 announcements confirms stronger reactions to failures.

There is a documented **run-up into PDUFA dates/readouts** (drift up as uncertainty resolves toward expected approval) and an **IV crush / "sell the news"** dynamic on approval (often priced in). Approvals often produce only +1–5% pops or even declines if priced in or if label/reimbursement disappoints; CRLs and Phase 3 failures produce 30–70%+ drops on small-caps. **Enter before vs after?** The only risk-controlled swing edge is the **pre-catalyst run-up — enter weeks before and EXIT 1–3 days BEFORE the binary date.** Holding a small-cap biotech through a PDUFA/Phase 3 readout is the single most dangerous trade for a small account. **Data needed:** PDUFA target dates, AdCom dates, trial phase/primary-completion dates, cash runway, prior FDA interactions. **PDUFA dates come from company disclosures, not the FDA.**

### 2.8 Product launches and major company events

Weak, unreliable catalysts. Apple event studies show near-zero or slightly negative average abnormal returns on launch day — classic "sell the news" (e.g., Vision Pro, June 2023, reversed to close lower; iPhone launches average ~−0.2% on the day, rebounding ~2.8% over the following month per Barron's-cited data). Fewer than half of Apple media events are positive-return events; anticipation is priced in early. Tradable remnant: a low-conviction fade of hyped launches, or a post-launch-month recovery. **Enter:** generally fade hype or stand aside. **Data needed:** event calendars, pre-event sentiment/run-up, options-implied move.

## Calendars / Data Sources

### Earnings calendars — estimated vs confirmed
**Estimated** dates are algorithmically predicted from historical patterns and routinely slip; **confirmed** dates come from company press releases. BMO/AMC timing is the most error-prone field everywhere.
- **Wall Street Horizon (TMX)** — institutional gold standard, 11,000+ global companies, 40+ event types; explicitly tags confirmation status/source; DateBreaks alerts every 5 minutes. Custom/institutional pricing.
- **Earnings Whispers** — retail favorite, "Only Confirmed Dates" filter; free tier plus paid Investor (~$49.95/mo) and institutional downloads.
- **Benzinga** — `date_confirmed` and projected/confirmed flags; self-reported 99.975% accuracy (Q2 2022, vendor claim); enterprise pricing.
- **Nasdaq Data Link / Zacks ZEA** — 7,000+ companies, **predicted (estimated)** dates plus EPS estimates; subscription.
- **Finnhub** — best free tier (60 calls/min, no card); dates are estimates.
- **Financial Modeling Prep** — calendar with BMO/AMC field; ~$59/mo Premium (calendar is a paid endpoint).
- **EODHD** — aggregated calendar; free 20 calls/day, Calendar API ~$19.99/mo, Fundamentals feed ~€59.99/mo.
- **Polygon.io** — strong for prices/corporate actions, weak as a forward earnings-date source; $0–$199/mo individual tiers.

### Corporate actions (dividends, splits, buybacks)
- **Polygon.io** — structured dividends (declaration/ex/record/pay, type) and splits at low cost; best value for retail/devs.
- **Intrinio** (via Exchange Data International) — 45+ corporate-action types; enterprise/custom pricing.
- **EODHD** — forward dividend/split calendar; full declaration/record/pay only for major US tickers (JSON).
- **FMP** — dividend and split calendars; cheap tiers.
- **Woodseer** (now OptionMetrics) — specialist forward dividend *forecasting* (undeclared future ex-dates/amounts), 32,000+ securities; datasets start ~$12,000 — institutional.
- Buyback authorizations: scrape **8-K filings on SEC EDGAR** (free); no clean retail API.

### M&A / merger-arb trackers
- **InsideArbitrage** — dedicated retail/prosumer merger-arb tool, auto-calculated spreads and annualized returns; free tier (current month) plus Premium.
- **Accelerate AlphaRank Merger Monitor** — free research/commentary, proprietary AA→CCC closing-probability ratings and effective-yield; SPAC coverage.
- **Bloomberg / Deal Reporter (Mergermarket) / S&P Capital IQ** — institutional, paywalled, earliest deal intelligence.

### Index changes
- **S&P Dow Jones Indices press releases** (press.spglobal.com) — authoritative and free; changes announced typically ~5 trading days before the effective date (methodology floor: at least 3 business days), after market close (~5:15 pm ET). Quarterly rebalances ~second Friday of Mar/Jun/Sep/Dec. No reliable free prediction service; bank analyst candidate lists are speculative.

### FDA / biotech calendars
**Critical caveat: the FDA does not publish PDUFA dates.** Every PDUFA calendar aggregates company disclosures (8-Ks, press releases); dates slip and 3-month extensions are common.
- **BioPharmCatalyst** — long-standing retail standard, free calendar + premium.
- **BPIQ** — 600+ biotechs, 1,800+ assets, catalyst/PDUFA calendars + API; free tier (current + next month) plus paid.
- **FDA Tracker** — integrates PDUFA + trial completion + cash runway.
- **RTTNews / BiopharmaWatch / MarketBeat / Dan Sfera (Substack)** — free editorial PDUFA calendars; cross-check against company 8-Ks.
- **Benzinga FDA Calendar API** — NDA/BLA filings, decisions, special statuses; enterprise.
- Clinical trials: **ClinicalTrials.gov** (free) for primary-completion dates.

### Spinoff calendars
- **SEC EDGAR Form 10 / 10-12B filings** — free, authoritative, but labor-intensive and misses 8-K-only and foreign-domiciled spins.
- **StockSpinoffInvesting** — leading retail spinoff calendar + research, ~$97/mo or ~$697/yr; free calendar available.
- **The Spin-Off Report (PCS Research/Horizon Kinetics)** — institutional.

*Self-reported accuracy figures (Benzinga, Earnings Whispers, Woodseer) are vendor marketing claims, not independently audited.*

## Recommendations

Staged, concrete build order for the signal engine, with thresholds that would change the plan. Parameters marked **(JC)** are judgment calls where academic evidence is thin.

**Stage 1 — Core long signals (build first):**
- **PEAD module.** Trigger: SUE in top decile OR earnings-day gap ≥ +5%, AND beat-and-raise confirmation. Filter: avg daily $ volume ≥ $10M **(JC)**, price > $5, gap holds above prior close after the first 30–60 min. Entry: day +1 after the gap stabilizes. Stop: ~5–8% below entry **(JC)**. Exit: ride 20–40 trading days or until the next earnings date; trail/exit on close below a chosen moving average.
- **Estimate-revision module.** Trigger: net upward revision breadth over trailing 4 weeks, or explicit guidance raise. Entry after revision visible; hold 2–4 weeks; exit on revision-breadth flattening or guidance cut.

**Stage 2 — Secondary confirmations:**
- **Buybacks:** authorization ≥ ~5% of shares **(JC)** AND low P/B; enter after 8-K, hold 2–4 weeks (~2–3% expected), time-stop.
- **Dividend initiations:** long after announcement, hold weeks (drift +7.5% over 12 months historically). **Cuts/omissions:** short/avoid (−11% drift). Never trade ex-dividend mechanics.

**Stage 3 — Opportunistic/specialist:**
- **Spinoffs:** buy post-spin forced-selling weakness (first ~15 days), hold toward the 60-day+ recovery.
- **Index inclusion:** buy day after S&P announcement, exit at/near effective-date close — small, crowded.
- **FDA/biotech:** pre-catalyst run-up only — enter 2–4 weeks before, **EXIT 1–3 days before the binary date**, size at a fraction of normal.

**Avoid as primary signals:** M&A targets, stock splits, product launches.

**Benchmarks that change the plan:** if live PEAD/revision trades net less than transaction costs after 50+ trades, tighten the liquidity filter (raise the $ volume floor) and the SUE threshold. If a biotech run-up trade is still open within 3 days of a PDUFA/readout, force the exit regardless of P&L. If account equity falls below the broker's intraday-margin or $2,000 leverage threshold, switch to a cash account and trade only settled funds.

## Caveats

- **PDT rule change (timing-sensitive).** As of June 4, 2026 (FINRA Regulatory Notice 26-10, SEC approval April 14, 2026, 18-month phase-in to Oct 20, 2027), the $25,000 pattern-day-trader minimum and the PDT designation are eliminated, replaced by intraday margin standards (margin accounts above $2,000 gain intraday buying power; deficits unresolved >5 business days above the lesser of 5% of equity or $1,000 trigger a 90-day restriction). Schwab stops counting day trades June 8, 2026. Swing trades held overnight were never the core PDT concern; cash-account settlement (T+1) remains a real constraint. Confirm your specific broker's implementation date.
- **Effect decay is ongoing and uneven.** PEAD and the index effect have decayed materially; whether they decay further is unknown. The literature disagrees on PEAD's current significance (Chordia et al. find near-zero in liquid US stocks; some recent studies still detect it, especially in less-liquid/international names).
- **Academic magnitudes overstate net retail returns.** They are typically gross, equal-weighted, and small-cap-tilted; a small account trading liquid names will capture a fraction of headline figures, and trading illiquid names will lose most of it to spread/impact.
- **Vendor accuracy and PDUFA sourcing are weak points.** Estimated earnings dates slip; PDUFA dates are not published by the FDA and must be cross-checked against company 8-Ks. Build date-change monitoring into the engine.
- **Negative-skew events (M&A, holding through binaries) can ruin a small account in one print** even with a good win rate; position sizing (cap binary-adjacent risk at ~0.5–1% of account, cleaner drift trades ~1–2%, **JC**) matters more than signal selection here.