# Backtesting and Validating a Multi-Factor Swing Trading Strategy: A Practical Guide for the Solo Retail Developer

## TL;DR
- **Validate before you trust.** A multi-factor swing system that scores and ranks US stocks must survive three things before risking real money: bias-free backtesting (survivorship, lookahead, and overfitting controls), realistic cost modeling, and a forward (paper) test of at least 1–3 months / 100+ trades. Expect live results to run materially below backtest — McLean & Pontiff (*Journal of Finance*, 2016) found out-of-sample returns ~26% lower than in-sample (58% lower after publication) across 97 predictors, and a QuantPedia analysis of 355 strategies found Sharpe ratios degrade ~33% on average (44% at the median) out-of-sample.
- **Use vectorbt for research, a custom pandas backtester for the portfolio engine.** For a solo Python developer building a cross-sectional scoring system on a scaling small account, the best combination is Alphalens (factor validation) + vectorbt (fast parameter sweeps) + a thin custom pandas backtester for the actual ranked-portfolio rebalance logic. Backtrader is the friendliest event-driven option if you want one framework and intend to go semi-live; zipline-reloaded fits if you specifically want its Pipeline factor API.
- **The biggest killers are overfitting and survivorship bias, not framework choice.** Combine a survivorship-bias-free universe (delisted stocks included), point-in-time signal timing (execute on next open, never the signal-bar close), walk-forward / purged cross-validation, and the deflated Sharpe ratio to discount the many configurations you tried. Keep parameters few and the logic simple.

## Key Findings

1. **A swing strategy is forgiving on cost but unforgiving on bias.** Holding for days-to-a-month means turnover is moderate, so transaction costs are far less corrosive than for intraday trading — but the same holding period makes survivorship and lookahead bias dominant error sources, because the backtest spans many names over many years.
2. **Survivorship bias is large and one-directional — it always flatters you.** Free data (Yahoo, broker feeds) excludes delisted stocks. Hendrik Bessembinder (2018, *Journal of Financial Economics* 129(3): 440–457) found that 57.4% of all CRSP common stocks since 1926 had lifetime buy-and-hold returns *below* one-month Treasury bills, and of the 25,967 stocks studied, 9,187 were delisted with a median lifetime return of −91.95%. Ignoring those failures inflates backtests by documented multiples of percentage points per year.
3. **Composite scoring needs factor-level validation, not just portfolio-level returns.** Use the Information Coefficient (Spearman rank correlation between factor score and forward return) and quantile spreads (Alphalens) to test each factor's marginal contribution and check redundancy via factor correlation before combining. Combining signals that "backtest well together" is a known overfitting trap (NBER w21329).
4. **Overfitting is measurable.** Bailey & López de Prado's Deflated Sharpe Ratio (DSR) and Probability of Backtest Overfitting (PBO via CSCV) explicitly discount a Sharpe ratio for the number of trials run and for non-normal returns. With enough configurations, a Sharpe of 2+ can arise purely from luck.
5. **Costs for a small US account are dominated by the spread, not commissions.** Retail equity commissions are effectively zero (PFOF-subsidized), so the realistic cost is the bid-ask spread plus slippage: roughly 1–3 bps each way for liquid large-caps, but hundreds of bps for illiquid small-caps. Market impact is negligible for a small account.
6. **Paper trading is the final gate.** Run the live signal system in paper/forward mode for weeks-to-months, comparing realized fills, IC, and trade distribution against backtest expectations before committing capital.

## Details

### 1. Overview — Why validation matters and what the pipeline looks like

Backtesting is the scientific method applied to trading: you formalize a hypothesis (the scoring rule) and test it against history. But a backtest is a single measurement under one set of conditions, and if the parameters were tuned on the same data, "the backtest is not even that — it is a strategy that already knows the answers to the test." For a *multi-factor* system the danger is amplified, because every additional factor, weight, and threshold is another degree of freedom you can (accidentally) fit to noise.

**Specific risks of deploying an unvalidated signal system with real money:**
- **Inflated expectations from bias.** Survivorship and lookahead bias systematically push backtested returns above what is achievable. A strategy that looks like it returns 15%/yr can be a real ~8% — or negative — once failures and realistic timing are included.
- **Overfit parameters.** Optimized parameters frequently "add no value" out-of-sample (Ernie Chan): there were not enough independent trades to make them statistically meaningful, so they captured noise.
- **Cost blindness.** Ignoring spread/slippage overstates returns; the effect compounds with turnover.
- **Execution/behavioral gap.** Even a signal-only system requires the human to place orders faithfully. Live performance is typically well below backtest — McLean & Pontiff documented a ~26% in-sample-to-out-of-sample return decay (rising to 58% post-publication); short-term strategies suffer the largest drops.

**A realistic end-to-end validation pipeline:**
1. Assemble a **survivorship-bias-free, point-in-time** universe with split/dividend adjustment.
2. **Factor research** — validate each factor individually (IC, quantile spread, turnover) with Alphalens before combining.
3. **Composite construction** — standardize (z-score/rank), weight, combine; define the ranking and rebalance rules.
4. **Portfolio backtest** with realistic execution (next-open fills) and **cost model**.
5. **Robustness** — parameter-sensitivity sweeps, walk-forward / purged CV, deflated Sharpe / PBO.
6. **Paper/forward test** for 1–3 months / 100+ trades.
7. **Go live small**, scale only as live metrics track the backtest.

### 2. Framework recommendation

| Framework | Paradigm | Speed | Learning curve | Multi-asset / universe | Maintenance | Cost | Best for |
|---|---|---|---|---|---|---|---|
| **backtrader** | Event-driven | Moderate (Python loop) | Gentle, very well documented | Yes, supports many data feeds | Mature but last formal release May 2019; community PRs only | Free (OSS) | Solo traders wanting one tool from research to semi-live; broker integrations (IBKR, OANDA, Alpaca) |
| **vectorbt (OSS)** | Vectorized / array | Extremely fast (NumPy + Numba) | Steep; needs comfort with arrays/broadcasting | Excellent for large sweeps and many assets | Actively developed | Free (Apache + Commons Clause) | Fast parameter sweeps, factor/signal research, robustness analysis |
| **vectorbt PRO** | Vectorized + Rust | Fastest; chunking, parallel | Steep | Best; dynamic universes, CV, walk-forward built in | Actively developed, private docs | ~$20/mo (annual saver) or lifetime; personal-use license | Power users wanting PRO features at low cost |
| **zipline-reloaded** | Event-driven | Moderate | Moderate-to-hard (install friction historically) | Pipeline API is purpose-built for dynamic equity universes & factors | Community fork (Stefan Jansen et al.), actively maintained | Free (OSS) | Long/short equity factor research with rotating universes |
| **Custom pandas** | Either | You control it | You own all the bugs | As much as you build | You maintain it | Free | Cross-sectional ranked-portfolio rebalance logic that frameworks fit awkwardly |

**Recommendation.** For this project — a cross-sectional, multi-factor *scoring* system on a small, scaling, signal-only account — the strongest setup is a **hybrid**:
- **Alphalens** to validate factors (it ingests a factor Series + prices and returns IC, quantile returns, turnover).
- **vectorbt (open source)** for fast parameter sweeps and signal-level research; upgrade to **vectorbt PRO (~$20/month)** only if you need its built-in walk-forward/CV and want the extra speed.
- **A thin custom pandas backtester** for the actual periodic rebalance: rank by composite score each rebalance date, select top-N (or top quantile), size by percentage rules, fill at next open. This is the part frameworks handle awkwardly, and writing it yourself makes the scoring logic fully testable.

**When a custom backtester is the right call (QuantStart's framing):** when your logic is a cross-sectional rank-and-rebalance that doesn't map cleanly onto single-asset signal APIs, when you want complete transparency into fills and costs, and when you want to avoid a framework's hidden default behaviors. **Critical caveat:** Yin, Miki, Lesnichenko & Gural, "Implementation Risk in Portfolio Backtesting" (arXiv:2603.20319, March 19, 2026), found that single-engine backtests routinely hide cost-model and fill-ordering bugs — they identified "a library default in Backtrader that silently divides the user-specified commission rate by 100 before applying it," which produced a 97% divergence on a zero-cost benchmark that collapsed to exactly 0% after correction. The lesson: whatever you build, **cross-check a few backtests against a second engine.** Note also that vectorbt, despite the name, steps sequentially row-by-row and "there is no built-in mechanism that would prevent you from cheating such as executing on/after close" — you must enforce next-bar execution yourself.

### 3. How to backtest a multi-factor scoring system

**Cross-sectional vs time-series.** A swing scoring system that ranks a *universe* of stocks at each rebalance is fundamentally **cross-sectional**: at each date you compare stocks against each other and buy the best-ranked. (A time-series approach instead asks whether each stock's own signal is above/below its own history.) Most multi-factor stock-selection models are cross-sectional rank-and-select.

**Standardization / z-scoring.** Before combining factors of different units (e.g., a momentum percentage and a valuation ratio), normalize each factor *cross-sectionally* at each date. The standard recipe (per the BQuant/Quantopian factor workflow):
1. Compute each factor value per stock per date.
2. Convert to a **cross-sectional z-score**: `z = (x − mean_across_stocks) / std_across_stocks`.
3. **Winsorize/cap outliers** — e.g., clip z-scores beyond ±2 (or ±3) standard deviations, or use rank instead of raw values to reduce outlier sensitivity.
4. Build the **composite** as a weighted sum of standardized factors.

**Weighting schemes (NBER w21329 taxonomy):** quantile sorts, **rank-weighted** (weight by cross-sectional rank), and **z-score-weighted** (weight by standardized score). For a retail project, **equal-weighting standardized factors** is the robust default; the alternative — weighting factors by their Information Coefficient or IC/IR — adds parameters and overfitting risk. The discipline literature warns that subjective factor weighting "depends on the experience of the researcher" and that more elaborate weighting is easily overfit.

**Testing each factor's marginal contribution.** Use **Alphalens** on each candidate factor:
- **Information Coefficient (IC):** the Spearman rank correlation between the factor score and N-period forward returns. Rank IC reduces outlier sensitivity. Track the *mean IC*, its *standard deviation*, and the *IC/IR* (mean IC ÷ std of IC, a risk-adjusted measure of factor consistency). A small but persistent positive mean IC (even ~0.02–0.05) that is stable over time is more valuable than a high but erratic one.
- **Quantile spread:** sort stocks into quantiles by factor; you want a monotonic fan-out where top quantiles earn more than bottom quantiles over your holding period (test 1/5/10/21-day forward returns to match your swing horizon).
- **Turnover / rank autocorrelation:** how often names churn between quantiles — high turnover means high cost.

**Factor correlation and redundancy.** Compute the correlation matrix of your standardized factors. Highly correlated factors (e.g., several momentum variants) are redundant — they don't add independent information but do add overfitting surface. Prune to a small set of weakly-correlated factors. Critically, the NBER paper warns: signals "backtest well together" does not imply any of them, or the combination, has real predictive power, because each is typically signed to predict positive in-sample returns; t-statistic critical values for multi-signal strategies "can be several times standard levels."

**Rebalancing logic.** Define explicitly: rebalance frequency (e.g., weekly or on signal); selection rule (top-N or top-quantile); position sizing (your percentage-based rules); and entry/exit timing. For a swing strategy holding days-to-a-month, a common structure is to re-score daily, enter new top-ranked names at next open, and exit when a name falls out of the top quantile or hits a percentage stop/target.

**Structuring the backtest so the scoring logic is testable.** Modularize (this is vectorbt's design philosophy and good practice generally): separate (a) data ingestion, (b) per-factor computation, (c) standardization/combination into a composite, (d) ranking/selection, (e) sizing, (f) execution/fills, (g) performance analytics. Each stage should be independently unit-testable — e.g., assert that on a fixed date your composite score and rank match a hand-computed example, and that no future data enters the score.

### 4. Bias avoidance

**Lookahead bias.** Using information that wasn't available at decision time. Concrete mitigations:
- **Signal timing / execution price.** If a signal is computed from today's *close*, you cannot trade at today's close — execute at the **next open** (or later). vectorbt will happily let you "buy after close" on the same bar, so you must explicitly shift signals. Backtrader's event loop enforces next-bar execution more naturally.
- **Point-in-time data.** Fundamentals must reflect what was *known* then (e.g., earnings as of their release date, not restated). Index membership must be point-in-time (don't assume today's S&P 500 was the universe five years ago).
- **No back-adjustment leakage.** (Chan's futures example: back-adjusting prices using future contract data introduces lookahead — relevant if you ever extend to futures.)
- **Beware low-frequency data quirks (Chan).** Consolidated daily OHLC can quote a high/low that never existed at a tradeable size; for sensitive strategies use the closing *mid* price and add explicit cost.

**Survivorship bias.** Datasets that include only currently-listed stocks omit bankruptcies, mergers, and delistings — and "if a dataset does not explicitly mention the inclusion of delisted stocks, you can assume it has survivorship bias" (QuantRocket). Broker and Yahoo feeds typically have it. Mitigations:
- Use a **survivorship-bias-free** dataset that includes delisted stocks with point-in-time index membership (Norgate Data, QuantRocket, CRSP, EODHD all advertise this).
- Include each stock's data up to its delisting date, and model the delisting outcome (a bankruptcy delisting = a near-total loss on that position; a merger may be neutral/positive).
- If you *must* use biased data, limit the backtest to a few recent years (bias grows with lookback) — but this worsens overfitting risk, so a clean dataset is strongly preferred. This matters most for strategies touching cheap/illiquid small-caps, where distress delistings are common (recall Bessembinder's 9,187 delisted stocks with a −91.95% median lifetime return).

**Overfitting (curve-fitting, p-hacking, multiple testing).** The deepest danger. Mitigations:
- **Keep parameters few and the logic simple.** Chan and others advocate simple, linear strategies as "an antidote to overfitting and data-snooping." Prefer the simpler of two variants with indistinguishable performance.
- **Parameter-sensitivity analysis.** Require the edge to survive a ±10% perturbation of each parameter; a result that evaporates under small changes is fit to noise.
- **Account for multiple testing with the Deflated Sharpe Ratio (DSR).** Bailey & López de Prado (2014, *Journal of Portfolio Management* 40(5): 94–107) show that when you try many configurations and keep the best, the maximum Sharpe is inflated even if all candidates are pure noise. DSR discounts the observed Sharpe for (a) the number of (effectively independent) trials, (b) the variance of Sharpe across trials, and (c) skewness/kurtosis and sample length. **Record every configuration you test** so you can estimate the number of trials — this is required to compute DSR honestly.
- **Probability of Backtest Overfitting (PBO).** Via Combinatorially Symmetric Cross-Validation (CSCV), PBO estimates the probability that the configuration that looked best in-sample will underperform the median out-of-sample. A PBO near 50% means your selection procedure has no predictive value.
- **Minimum backtest length.** Bailey et al. show that a backtest can be "too short" to support the number of trials run; insufficient data essentially guarantees data-snooping bias.
- **Develop for the whole universe, not single names; do not backtest until research is complete** (López de Prado's anti-overfitting rules).

### 5. Cost modeling for a small US account

**Commissions / the zero-commission landscape.** Major US retail brokers (Schwab, Fidelity, Robinhood, IBKR Lite, E*Trade) charge **$0 commission** on US-listed stock and ETF trades, subsidized largely by **payment for order flow (PFOF)** — wholesalers like Citadel Securities, Virtu, and G1 Execution Services pay brokers for retail order flow and execute at or inside the NBBO. PFOF remains legal and intact as of 2025–2026: the SEC withdrew 14 proposed rules including the Rule 615 "Order Competition Rule" on **June 12, 2025** (effective June 17, 2025, per SEC release 33-11377), stating it "did not intend to issue final rules with respect to the proposals." The surviving transparency tool is the **amended Rule 605 execution-quality framework**, whose compliance date the SEC extended from December 14, 2025 to **August 1, 2026** (per Federal Register 90 FR 47552, Oct. 2, 2025): "Beginning on August 1, 2026, market centers, brokers, and dealers subject to Rule 605 must begin to collect the information needed." Practical implication: model commission as $0 for US equities, but do not assume zero *total* cost — the cost moved into the spread.

**Bid-ask spread (the dominant cost).** Model crossing the spread on entry and exit:
- **Liquid large-caps (S&P 500 names like AAPL):** roughly **1–3 bps** effective spread each way; up to ~15 bps quoted; spikes to ~20 bps in stress (e.g., March 2020). Ernie Chan: "1 or 2 bps are common for SPX stocks." Academic effective-spread estimates for very liquid names run ~2.8–3.2 bps.
- **Illiquid small/micro-caps:** spreads of **hundreds of bps** (Stockopedia: "small caps can often have spreads of 500 or more" basis points); SEC small-cap studies show multi-cent quoted spreads.

**Slippage.** The gap between expected and realized fill. The most concrete practitioner number: **Ernie Chan applied ~5 bps per side (≈10 bps round-trip)** of transaction cost in his book's S&P 500 example, on top of using the mid price. A widely-used convention is to charge **half the bid-ask spread from mid per fill** (equivalently one full spread round-trip); a generic fixed assumption of **0.1% (10 bps) per trade** for liquid names, scaled up for illiquidity/volatility, is common. Note: QuantConnect/LEAN defaults slippage to **zero** and explicitly tells users to add their own model ("By default, Lean models slippage with a constant value of 0... It's up to the users of Lean to create their own slippage models") — never rely on a framework's default.

**Market impact.** For a small (even scaling) retail account, your order is tiny relative to daily volume, so impact is **negligible** for liquid names — worth noting only as you scale into small-caps, where even a small dollar order can be a meaningful fraction of daily volume. Impact is inherently non-linear; institutions model it with quadratic functions, but a retail swing trader can safely set it ~0 for liquid stocks and instead cap position size as a fraction of average daily volume for small-caps.

**How costs interact with holding period and turnover.** Costs scale roughly with **turnover**, so a swing strategy (days-to-a-month holds) is far more cost-tolerant than intraday trading. Quantified contrast: Yin et al. (arXiv:2603.20319, 2026) found cost-driven return divergence **below 0.75 percentage points for 12 of 15 benchmarks** but reaching **3.71% of total return for high-turnover rotation strategies** under the heaviest cost regime — "roughly $37M per year for a $1B portfolio." Academic factor-cost work (Li, Chow et al., *Financial Analysts Journal*, 2019) shows implicit market-impact costs "may substantially erode a strategy's expected excess returns," driven by "the rate of turnover and the concentration of turnover." Practical rule: estimate annual cost drag ≈ (round-trip cost per trade) × (annual turnover); for a monthly-rebalance large-cap strategy this is small, but verify it doesn't consume your edge — and be especially careful if your scoring favors high-turnover small-cap names.

### 6. Metrics to track

| Metric | Formula / intuition | Good vs bad | Key limitation |
|---|---|---|---|
| **CAGR** | Compound annual growth rate = (End/Start)^(1/yrs) − 1 | Context-dependent; compare to benchmark (SPY) | Says nothing about risk/path |
| **Sharpe ratio** | (mean return − rf) / std of returns, annualized (×√252 for daily) | **>1 good, >2 excellent, >3 suspicious** | Assumes i.i.d. normal returns; punishes upside volatility; inflated by multiple testing |
| **Sortino ratio** | Like Sharpe but denominator = downside deviation only | Higher than Sharpe = positive skew (good) | Needs a target/MAR choice |
| **Calmar ratio** | Annualized return ÷ max drawdown | **>1 good, >3 excellent** | Looks "juicy" in calm periods with no big drawdown |
| **Max drawdown** | Largest peak-to-trough decline | Determines survival; a 50% DD needs a 100% gain to recover, a 75% DD needs 300% | Single worst event; ignores frequency of small losses |
| **Win rate** | % of trades profitable | **Misleading alone** | A 30%-win strategy can be highly profitable if winners >> losers |
| **Expectancy** | (Win% × avg win) − (Loss% × avg loss) | Must be **positive** | Needs many trades to stabilize |
| **Profit factor** | Gross profit ÷ gross loss | **>1 profitable; 1.5 solid; 2+ strong** | Sensitive to a few outlier trades |

**Which matter most for a swing strategy:** prioritize **expectancy and profit factor** (you have discrete trades), **max drawdown and Calmar** (survival and psychological tolerance — can you actually hold through the worst stretch?), and **Sharpe/Sortino** for risk-adjusted comparison. **Win rate alone is the classic trap.** No single metric suffices — a robust strategy passes several filters. Statistical caveats: you need a meaningful **sample size** — roughly 30 trades is a bare minimum to see a pattern, 100+ for basic statistics, 200+ for reliable Sharpe/Sortino. And per the DSR literature, a high Sharpe means little until deflated for the number of trials you ran. Also examine the **equity curve shape**: two strategies with identical Sharpe can have very different smoothness.

### 7. Walk-forward and paper-trading process

**Out-of-sample testing and train/test splits.** The cardinal rule: never evaluate on data used to choose parameters. Chan advocates same-size in-sample/out-of-sample, accepting at least 1/3 of the sample as out-of-sample. A simple 70/30 or 80/20 split is the entry-level approach but yields a single, path-dependent estimate.

**Walk-forward analysis (WFA).** Repeatedly optimize on an in-sample window, then test on the *next* out-of-sample window, roll forward, and concatenate only the out-of-sample segments into the final equity curve. Two flavors:
- **Rolling (fixed-length) window** — the conservative default; forces the strategy to prove itself under recent conditions and gives a cleaner signal about adaptation to changing regimes.
- **Anchored (expanding) window** — keeps all history; useful for structurally stable patterns, but "makes overfitting harder to detect because the later windows have so much training data that almost any parameters will look reasonable." **Start with rolling.**

**Using WFA to detect overfitting:** if out-of-sample performance is dramatically worse than in-sample across windows, the strategy is overfit. Beware the meta-overfitting trap: if you test many WFA configurations (window sizes, fitness functions) and pick the one with the best out-of-sample curve, you've overfit the *validation process itself*.

**Cross-validation pitfalls in time series.** Standard k-fold CV assumes i.i.d. observations and **shuffles** data — invalid for time series, because (a) it trains on the future to predict the past, and (b) overlapping labels (a multi-day forward return) leak information across the train/test boundary. López de Prado's fixes:
- **Purging:** remove training observations whose labels overlap in time with the test set.
- **Embargoing:** drop a buffer of observations immediately after each test set before resuming training.
- **Combinatorial Purged Cross-Validation (CPCV):** generate many train/test path combinations so every observation is tested multiple times, producing a *distribution* of out-of-sample outcomes and a lower probability of false discovery. Research finds CPCV superior to plain walk-forward at preventing overfitting (lower PBO, higher DSR), though it's more complex to implement — a reasonable "phase 2" upgrade once your basic walk-forward is solid.

**Paper trading / forward testing — the final check.** This deploys the signal system on **live, unseen, real-time data** without real money. It catches what backtests cannot: unfilled orders, real spreads at your actual fill times, latency, data glitches, and — even for a signal-only system — whether *you* execute the manual orders faithfully and on time.
- **How long:** consensus is **2–4 weeks minimum, and 1–3 months / ~50–100+ trades** to span varied conditions. For a swing strategy with multi-day holds, lean toward the longer end so you accumulate enough closed trades.
- **What to compare against the backtest:** realized fill prices vs assumed (next-open) prices; realized per-trade cost vs your cost model; **live IC vs backtest IC** (expect live IC to be roughly half of backtest IC — that's normal, not failure); trade frequency, win rate, expectancy, and drawdown shape; and the set of names selected (to confirm no live-vs-backtest universe mismatch).
- **Detecting divergence:** a 20–50% performance reduction from backtest to live is common and expected (consistent with McLean & Pontiff's ~26% and QuantPedia's ~33% average Sharpe decay); short-horizon strategies degrade most. **Red flags** that mean *stop and re-investigate*: live IC near zero or negative; realized costs materially above your model; fills consistently worse than next-open; or live drawdown exceeding the worst backtested drawdown. Use the empirical paper-trade costs/slippage to **recalibrate the backtest** (a 30–60 day "paper mirror" to calibrate slippage and commission is good practice), then re-validate.

### 8. Validation checklist before going live

**Data & universe**
- [ ] Universe is **survivorship-bias-free** (includes delisted stocks) with **point-in-time** index membership.
- [ ] Prices are **split- and dividend-adjusted**; fundamentals are point-in-time (as-reported, with correct release dates).
- [ ] Sufficient history spanning multiple regimes (bull, bear, ≥1 high-volatility event).

**Signal timing & logic**
- [ ] No lookahead: signals computed from close are executed at **next open** (or later), enforced in code.
- [ ] Each pipeline stage (factors → standardize → combine → rank → size → fill) is **unit-tested** against a hand-computed example.
- [ ] Cross-checked a sample backtest against a **second engine** to catch cost/fill bugs.

**Factor & composite validation**
- [ ] Each factor validated individually (mean IC, IC/IR, quantile spread, turnover) — weak/erratic factors dropped.
- [ ] Factor correlation matrix checked; redundant factors pruned.
- [ ] Composite uses a **small** number of weakly-correlated, standardized (z-scored/ranked, winsorized) factors; weighting is simple (equal-weight default).

**Cost realism**
- [ ] Commission = $0 (US equities), but **spread + slippage modeled** (≥1 full spread round-trip; ~5–10 bps for liquid large-caps, much more for small-caps).
- [ ] Position size capped as a fraction of average daily volume for any illiquid names.
- [ ] Annual cost drag ≈ round-trip cost × turnover computed and confirmed not to consume the edge.

**Robustness & overfitting**
- [ ] **Every configuration tested was logged** (count of trials known).
- [ ] Parameter-sensitivity check: edge survives ±10% perturbation of each parameter.
- [ ] Walk-forward (rolling) analysis done; out-of-sample ≈ in-sample, not dramatically worse.
- [ ] **Deflated Sharpe Ratio** and/or **PBO** computed; Sharpe remains meaningful after deflation.
- [ ] Sample size ≥100 trades; key metrics (expectancy, profit factor, Calmar, max DD) all acceptable.

**Forward test & launch**
- [ ] Paper-traded **1–3 months / 100+ trades**; live IC, costs, fills, and drawdown tracked vs backtest.
- [ ] No red flags (live IC ~0, costs >> model, fills << next-open, DD > worst backtest).
- [ ] Backtest recalibrated with empirical paper-trade costs and re-validated.
- [ ] **Go live small**, with predefined thresholds for scaling up (or shutting down) based on live-vs-expected divergence.

## Recommendations

**Stage 1 — Tooling (week 1).** Install Alphalens + vectorbt; acquire a survivorship-bias-free dataset (Norgate or QuantRocket are the standard retail-affordable choices; CRSP if you have academic access). Do **not** start research on Yahoo/broker data — the survivorship bias alone can flip your conclusions. Write the thin custom pandas rebalance engine and unit-test it.

**Stage 2 — Factor validation (weeks 2–4).** Run each candidate factor through Alphalens. **Threshold to proceed:** keep only factors with a stable, positive mean IC and a monotonic quantile spread at your swing horizon (1–21 days). Drop redundant (highly correlated) factors. Combine the survivors equal-weighted into the composite.

**Stage 3 — Portfolio backtest (weeks 4–6).** Backtest the ranked rebalance with next-open fills and the cost model (≥1 spread round-trip). **Threshold to proceed:** positive expectancy, profit factor >1.3, Calmar >1, max drawdown within your personal tolerance, over ≥100 trades and multiple regimes.

**Stage 4 — Robustness (weeks 6–8).** Run parameter-sensitivity (±10%), rolling walk-forward, and compute the **Deflated Sharpe Ratio** using your logged trial count. **Threshold to proceed:** out-of-sample ≈ in-sample; DSR still indicates significance; PBO well below 50%. If it fails, **simplify** (fewer factors/parameters) rather than re-optimize.

**Stage 5 — Forward test (months 3–4+).** Paper trade for 1–3 months / 100+ trades. **Threshold to go live:** live IC ≥ ~50% of backtest IC, realized costs ≈ modeled, fills ≈ next-open, drawdown < worst backtest.

**Stage 6 — Live, small and scaling.** Start with a small fraction of intended capital. Scale up in steps only while live metrics track expectations (allowing the normal 20–50% haircut). **Shut-down trigger:** live drawdown exceeds worst backtested drawdown, or live IC goes to zero/negative over a meaningful sample.

**What would change these recommendations:** if you find your scoring favors illiquid small-caps, cost modeling and ADV-based position caps move from "minor" to "decisive," and you should re-weight toward liquid names or accept much lower capacity. If you intend to eventually automate execution, switch the primary engine to backtrader (broker integrations) earlier. If you want institutional-grade overfitting control, graduate from walk-forward to CPCV.

## Caveats

- **Live ≠ backtest, always.** A 20–50% performance reduction is normal (McLean & Pontiff: ~26% in-sample-to-out-of-sample; QuantPedia: ~33% average Sharpe decay across 355 strategies); treat the backtest as a feasibility study, not a forecast.
- **The base rate for stock-picking is brutal.** Bessembinder's finding — 57.4% of individual US stocks underperformed T-bills over their lifetimes, with the best-performing 4.3% (1,092 of 25,967 firms) accounting for the entire net wealth gain and just 86 stocks accounting for $16 trillion (half the market total) — means a poorly-diversified active strategy faces strong headwinds. Diversify across enough names and respect that the edge from any factor is small.
- **Some cited figures are from practitioner blogs/vendors, not peer-reviewed sources** — particularly specific bid-ask and slippage rules of thumb. These are directional conventions, not laws. The academic anchors (Bailey & López de Prado on DSR/PBO, NBER w21329 on multi-signal overfitting, Bessembinder on stock returns, McLean & Pontiff on out-of-sample decay, the FAJ factor-cost paper) are the firmer ground.
- **Overfitting can sneak in through the validation process itself** — choosing the best walk-forward configuration, or repeatedly tweaking after seeing out-of-sample results, re-introduces the bias you were trying to remove. Decide the validation protocol *before* you run it.
- **Framework defaults can silently corrupt results** (zero slippage, the Backtrader commission-default divide-by-100 bug, same-bar execution). Always inspect and override defaults, and cross-check engines.
- **Regulatory/cost landscape is shifting:** Rule 605's expanded execution-quality disclosure takes effect August 1, 2026, which may change how you assess your broker's fill quality; PFOF and zero commissions remain in place for now (Rule 615 and proposed Regulation Best Execution were withdrawn in June 2025) but are periodically subject to reform proposals.