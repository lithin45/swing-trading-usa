# Strategy review — improving the trades (2026-06-10)

**Scope:** full project deep-dive (signal core, backtest/experiment history, live ops state) plus an
external evidence review of swing-trading strategies (academic + practitioner, decay-adjusted),
to answer: *how good is the system, and what should we add — price action or anything else?*

**Method:** four parallel deep-reads (signal-generation logic; backtest + git-history experiment
evidence; live paper-trading/ops state; external strategy research with ~40 cited sources),
cross-checked by hand against `config/settings.yaml`, `scoring/engine.py`, `scoring/levels.py`,
`exits.py`, `factors/f08_momentum.py`, and `persistence/`. Companion to
`docs/audit-2026-06-10.md` (compliance/engineering audit, same day).

---

## 1. Verdict on the current system

**Engineering: strong.** 306 green tests, point-in-time S&P 500 backtesting, honest negative
results in commit messages, shared live/backtest signal path, paper-only execution. This is a
better foundation than most retail systems ever reach.

**Strategy: one validated, thin, regime-dependent edge.** Long-only momentum
(52w-high-proximity-dominant blend, GREEN-regime-only, shallow-pullback limit entries,
no-chase ≤3 ATR, 3-ATR stop, full exit at 2R or 20 bars):

| Window | Result | Nature |
|---|---|---|
| 2022–24 (in-sample, brutal tape) | −0.012R, PF 0.97 | survival, not profit |
| 2025-01 → 2026-06 (untouched holdout) | **+0.118R, PF 1.27, 54.7% win, CAGR +6.6%, maxDD −8.6%** | the real edge |
| 2017–19 (second untouched window) | +0.112R, PF 1.28 | agrees |
| Combo's actual value-add | 2022–23 bleed cut **−35.7R → −2.8R** | crash protection |

**Live: day one.** Paper trading effectively started 2026-06-09 under the *old* config; tonight's
21:30 UTC run is the first execution of the validated combo. 1 fill, 1 same-day stop-out so far.
There is **no live evidence yet** — every improvement decision below rests on backtest + external
evidence, and the paper account's job for the next 3–6 months is to measure live-vs-backtest drift.

**Expectation setting:** at ~150 trades/yr × +0.11R × ~1% risk, this is a mid-single-digit CAGR
system with −9 to −15% drawdowns at current sizing, *before* the 20–50% live degradation the brief
itself predicts. The improvements below aim to (a) cut the left tail, (b) add uncorrelated trade
flow for the chop regimes where momentum bleeds, (c) nudge R/trade — not to transform it.

## 2. Where the money is actually made and lost (backtest diagnostics)

From the experiment ledger autopsies (`scripts/diagnose_trades.py`, commits a20fea2 / 2a3707d era):

- **Losses are concentrated in early "noise deaths":** ~48% of trades died <10 bars at ≈ −0.9R
  (2-ATR era); even at 3-ATR stops, 0–5-bar holds average −0.44 to −0.9R. **This is the single
  biggest loss bucket.**
- **Survivors carry the edge:** 10–20-bar holds average **+0.33R**; target exits average +1.96R.
- **Time-stop exits are profitable** (+0.3 to +0.47R mean) — the 20-bar cut captures drift.
- **Gap-stops cost −1.3R each** and are irreducible by stop placement (a stop is fiction across a gap).
- **Regime dominates:** both base and combo earn in trending tape and bleed in crash/chop; the
  combo's contribution is making the bleed survivable.

Implication: the highest-leverage *in-engine* lever is anything that avoids the first-five-bar
noise deaths without forfeiting the survivors; the highest-leverage *portfolio* lever is a return
stream that earns when momentum chops.

## 3. Already tested — do not retry

| Variant | Result | Verdict |
|---|---|---|
| Deeper pullback entry (`zone_low`) | −0.164R vs −0.134R base | adverse selection — rejected |
| Diversify 16 positions @ 0.5% | −0.101R, no edge gain | rejected |
| 12-1-dominant momentum weights | marginal, order-dependent | rejected (likely noise) |
| Staged exits (partial @2R + trail) | PF 0.77 vs 0.89 legacy (2022–24) | reverted 2026-06-10 |
| Removing the time-stop | time-stop exits are +EV | keep the time-stop |

Also: ~9 variants were evaluated against 2022–24 before the combo was chosen. Selection risk is
real — **no further tuning against 2022–24** without the overfitting controls in §6.

## 4. The "price action" question, answered with evidence

Most of what retail content calls price action **fails rigorous testing** and should not be built:

- **Candlestick patterns** — rejected by every bootstrap-rigorous test (Marshall et al. 2006/2008
  and successors). No value at swing horizons.
- **Cup-and-handle / VCP / flat-base stats (Bulkowski/IBD/Minervini)** — selection-biased,
  no benchmark adjustment, no peer-reviewed support. Folklore dressed as statistics.
- **Eyeballed support/resistance** — no robust US-equity evidence at swing horizons.
- **Non-catalyst gap continuation** — most catalyst-free gaps fade intraday.
- **Classic SUE-based PEAD in large caps** — dead since ~2006 (Martineau 2022, *Critical Finance
  Review*); most retail "earnings drift" content cites pre-decimalization effect sizes.
- **Opening-range breakout** — documented edge (Zarattini-Aziz) but 5-minute intraday with
  leverage; incompatible with this EOD system.

What survives quantification is largely **what the system already trades**: trend/momentum,
52-week-high proximity (George-Hwang), long-only breakout right-skew (Wilcox-Crittenden 2005;
Zarattini-Pagani-Wilcox 2025: 66k trades 1950–2024, properties stable OOS 2005–2024 — the best
recent evidence that the existing core is a live, persistent edge). The one well-evidenced
price-action-adjacent feature *not* yet in the system is **volume-shock confirmation**
(high-volume return premium — Gervais-Kaniel-Mingelgrin 2001 JF, replicated across ~41 markets:
unusual-volume stocks outperform over the following ~20 days).

## 5. Ranked roadmap of strategy additions

Calibration: McLean & Pontiff (2016) — published anomalies decay ~26% OOS, ~58% post-publication.
Haircut every published number ~50%+ and validate everything on this repo's own broad-universe,
point-in-time harness (2017–19 + 2025–26 holdout discipline) before deploying.

### Tier 1 — protect the edge you have (build first)

1. **Earnings-date veto (no-hold-through-earnings) for the core sleeve.** A 3-ATR stop cannot
   contain a −15% earnings gap (−3R to −5R realized); one such event erases ~30–45 trades of
   expectancy at +0.11R/trade. Announcement-day moves have grown structurally (Beaver et al.
   2018/2020). Cost: forfeits the Savor-Wilson announcement premium — acceptable; it is
   compensation for exactly the risk the stop framework cannot manage. *Evidence grade A
   (mechanical). Effort: small (earnings calendar + exit/no-entry rule + backtest replay).*
2. **Trade-budget enforcement (≤7 entries/month) + per-name cooldown + cadence histogram** —
   the audit P0. Also a quality filter: the budget forces the bar up in hot months. Must be in the
   signal engine (so alerts respect it) and mirrored in the backtester.
3. **Continuous vol-managed exposure (de-lever-only) softening the binary regime cliff.**
   Barroso-Santa-Clara 2015 (momentum Sharpe 0.53→0.97, kurtosis 18→2.7, skew −2.5→−0.4);
   Daniel-Moskowitz 2016 (crashes are forecastable: high-vol post-decline rebounds). Implement as
   an exposure dial ∝ min(1, target-vol/realized-vol) × trend gate — never levering up, which
   dodges the Cederburg et al. 2020 critique of generic vol management. The system already has the
   inputs (ATR, VIX, regime score); this converts GREEN/not-GREEN whipsaw into graduated
   participation. *Evidence grade A for momentum specifically. Overfit risk: low (1–2 params).*

### Tier 2 — attack the loss buckets (one pre-registered experiment each)

4. **Entry-confirmation test against the noise-death bucket.** Candidates (test separately, on
   2022–24 only, then holdout): (a) require the signal to persist a second consecutive day before
   entry; (b) enter on strength only — buy-stop above the signal-day high instead of a pullback
   limit; (c) volume-shock requirement at entry (signal-day volume in top decile vs trailing 50d —
   the GKM feature). Each directly targets the −0.9R first-five-bars bucket; each will cut trade
   count, so judge on expectancy × frequency, not expectancy alone.
5. **Post-earnings continuation sleeve (the surviving form of PEAD).** Enter day +1 after a
   confirmed print only when: large positive day-0 abnormal return/gap AND abnormal volume AND
   positive Claude-scored call/PR text tone (PEAD.txt, JFQA 2023 — text-based drift persisted
   2008–2019 when numeric PEAD was dead; Brandt et al. 2008 for reaction-based sorting). Hold
   5–20 days under existing stop/size discipline. The Claude news pipeline already built is
   precisely the required infrastructure. *Regime-independent trade flow — fires in chop too.
   Keep it to those 3 conditions; no parameter search.*

### Tier 3 — diversify the return stream (after Tiers 1–2 prove out)

6. **Short-term mean-reversion sleeve on liquid ETFs (SPY/QQQ/sector SPDRs) + top-liquidity
   mega-caps, in uptrends only.** RSI(2)/multi-day-pullback class, 3–10 day holds, time-stop, ~0.5%
   risk-equivalent sizing, Connors-published parameters as-is (no re-optimization), validated on
   this repo's holdouts. Rationale: short-term reversal is the only common factor negatively
   correlated with momentum — it earns exactly where the core bleeds. Decayed in broad single-stock
   universes post-2015 (Alvarez); persistent at index/ETF level (~0.5–0.9%/trade historically on
   SPY — assume half). Structural conflict to resolve deliberately: Connors-style MR works
   *because* it has no price stop; cap it with size + time-stop instead, or accept the documented
   drag from stops.
7. **Industry/sector relative-strength gate + same-calendar-month seasonality tie-breaker**
   (Moskowitz-Grinblatt 1999; Heston-Sadka 2008 / Keloharju 2016). Cheap ranking features, partial
   overlap with the existing RS core — incremental, low overfit risk, never standalone sleeves.

### Not worth building (beyond §4's folklore list)

- Regime-*up*-sizing (levering up in GREEN) — return-seeking in the direction the evidence
  punishes; revisit only after a year of live data.
- Turn-of-month / overnight-only strategies — decayed (US) / cost-destroyed at retail.
- More entry patterns of any kind — the evidence says manage exposure and events, not add patterns.

## 6. Prerequisites before ANY new tuning (from the audit, now strategy-critical)

1. **Trial ledger + Deflated Sharpe + PBO (CSCV)** — ~9 trials already burned against 2022–24;
   every additional experiment must be logged and the selection penalty computed.
2. **±10% parameter-sensitivity sweeps** on the deployed thresholds (composite 70, agreement 0.70,
   extension 3.0, stop 3.0, vol-target 2.5) — confirm the combo sits on a plateau, not a spike.
3. **Loss-halt replay in the backtester** (gates exist live-only) and **persistent validation
   artifacts** in `docs/validation/` (the 2017–19 window currently lives only in session notes).
4. **Persist rejected setups** (`no_trades`) — today they are never written anywhere
   (`persist_daily_run` saves `actionable` only), so near-miss analysis and budget-rejection
   audit trails are impossible.

## 7. Operational fixes that directly affect trade quality (this week)

1. **Wire Telegram (or SMTP) alerts** — all alert secrets are empty in CI: signals currently go
   nowhere except CI stdout and the dashboard. For a system you act on, this is the cheapest
   highest-value fix that exists.
2. **Set the healthchecks.io dead-man's switch** (`SWING_HEALTHCHECK_URL` is empty) — GitHub
   auto-disables schedules after 60 days of repo inactivity, and a silent stall would be invisible.
3. **Mitigate GitHub cron starvation** — intraday `manage` fired 1 of ~16 expected slots on
   2026-06-10; the daily run fired 86 minutes late. Until improved, the standalone protective
   STOP-DAY orders are the real intraday safety (they worked on 2026-06-09). Options: accept and
   document, or add an external trigger/second scheduler.
4. Intraday workflow `concurrency` group; orphan-adoption stop fallback; Neon preflight check
   (audit P1 #7–9). Rotate any keys exposed in pre-fix CI logs if not already done.

## 8. Recommended sequence

| Phase | Content | Gate to proceed |
|---|---|---|
| A (days) | Ops wiring (§7.1–.2), budget P0 + cooldown + cadence histogram, earnings veto, persist `no_trades` | tests green; cadence histogram shows the bar does the work |
| B (week) | Validation infra (§6): trial ledger, DSR/PBO, sensitivity sweeps, halt replay, `docs/validation/` | combo confirmed on a parameter plateau |
| C (weeks, one at a time) | Pre-registered experiments: vol-managed exposure → entry-confirmation variants → volume-shock feature | each validated on holdouts, logged in the trial ledger |
| D (after C) | Post-earnings sleeve, then ETF mean-reversion sleeve (paper-first as separate sleeves) | each sleeve independently +EV on holdout + uncorrelated in sleeve P&L |
| Throughout | Paper account accumulates live-vs-backtest evidence; **no real capital** until ≥3–6 months of paper tracks the backtest within tolerance | go/no-go report per the mandate |

---

*Produced 2026-06-10 by Claude (Fable 5) from four parallel deep-dives + manual verification.
Companion to `docs/audit-2026-06-10.md`. Sources for §4–5 are cited inline in the external
research brief (session artifact); key anchors: McLean-Pontiff 2016; Martineau 2022; PEAD.txt
JFQA 2023; Brandt et al. 2008; Gervais-Kaniel-Mingelgrin 2001; Barroso-Santa-Clara 2015;
Daniel-Moskowitz 2016; Cederburg et al. 2020; Zarattini-Pagani-Wilcox 2025; Alvarez (Connors
research) decay studies; Savor-Wilson 2016; Beaver et al. 2018/2020; Moskowitz-Grinblatt 1999;
Heston-Sadka 2008; Lou-Polk-Skouras 2019.*
