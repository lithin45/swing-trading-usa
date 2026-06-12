# Strategy uplift session — 2026-06-10/11 (overnight + day, autonomous)

**TL;DR: the backtests were lying, not just the strategy underperforming.** Three
structural defects made every prior number partly fictional: a data provider
silently truncating history (carving multi-month holes into the cache), zombie
signals from those holes eating the monthly entry budget, and a drawdown halt
that bricked the account forever once hit. All three are fixed and tested. On
clean data the deployed combo is modestly positive in 2 of 3 development
windows. Five pre-registered strategy changes were then tested against the
clean baselines — **every one of them lost; nothing was deployed from them**,
and all 27 trials are in the ledger. The deployed change set is: data fixes +
the non-absorbing drawdown brake.

## 1. The five diseases

| # | Disease | Evidence | Status |
|---|---|---|---|
| 1 | **Provider truncation → cache holes.** Alpaca's free IEX feed serves only ~6y of history from today regardless of the requested start. Union-merge caching of those responses left a 210-day hole (2019-12-30→2020-07-27) in dozens of symbols; coverage checks pass on min/max so refetches no-op'd forever. | TGT/KLAC/AES/CDW… all shared the identical gap | FIXED: loader start-truncation guard prefers deeper-history providers; full-span refill (660 ok / 84 = genuinely delisted) |
| 2 | **Zombie signals.** The backtest had no staleness gate (live has `max_staleness_days: 4`). Symbols frozen at a hole's edge kept re-signaling at their frozen momentum high. | 35/38 "unfilled" orders in 2020-21 were zombies; they consumed **all 7 budget slots in 5 separate months of 2020** | FIXED: `_build_symbol_data` mirrors the live gate |
| 3 | **Absorbing halt.** Once drawdown hit −15%, no new entries were allowed; with no entries, equity never recovers → dead until a human notices. Live had the same defect. | 2017-19 replay: 306/752 days halted, missed all of 2019 (CAGR 7.7%→2.1%) | FIXED: trailing 1y high-water mark + resume at 25% size after a 10-session pause; identical logic in backtest `halt_state` and live `gates.py`; **deployed in settings.yaml** |
| 4 | **Size strangulation** (constraint, not bug). Effective risk per fill ≈ 0.3% vs the nominal 1%: tier (0.66) × regime × macro × vol scalar (0.4–1.0) × derisk (0.5) compound. | tier multiplier turned out to be a **no-op in practice** — the budget's top-7 ranking already selects High-tier signals only | Knob made configurable; **not** flipped (tested: no effect) |
| 5 | **Budget cost** (mandate, quantified). The ≤7 entries/month ceiling costs ~3.7pp CAGR/yr at identical per-trade edge. | no_budget on 2020-21: +3.84% CAGR vs +0.11% (zombie-era numbers; direction robust) | Mandate respected; cost documented for the user's decision |

Also fixed en route: offline cache reads now honor the requested date range
(the cause of the 20-hour matrix stall on 2026-06-11 — three concurrent
processes each holding 660 full-history frames swapped the machine to a
standstill).

## 2. Clean-data picture (all rows ledgered, `r3`/`r4`)

Development windows, deployed combo (`base`) vs every candidate:

### 2015-16 (chop + two corrections — hostile)
| variant | n | exp (R) | PF | CAGR | maxDD |
|---|---|---|---|---|---|
| base | 129 | −0.064 | 0.86 | −0.5% | −16.1% |
| market | 128 | −0.088 | 0.82 | −0.4% | −16.4% |
| brake | 141 | −0.037 | 0.92 | −2.2% | −20.3% |
| tier_flat | 129 | −0.064 | 0.86 | −0.5% | −16.1% |
| hold40 | 66 | −0.228 | 0.62 | −3.5% | −16.6% |
| staged_v2 | 122 | −0.089 | 0.78 | −3.0% | −15.3% |
| smart_hold | 122 | −0.083 | 0.80 | −3.1% | −15.2% |

### 2020-21 (crash + V-recovery + trend)
| variant | n | exp (R) | PF | CAGR | maxDD |
|---|---|---|---|---|---|
| base | 138 | +0.004 | 1.01 | −1.2% | −14.7% |
| market | 138 | −0.024 | 0.95 | −2.8% | −15.3% |
| brake | 138 | +0.004 | 1.01 | −1.6% | −14.7% |
| tier_flat | 138 | +0.004 | 1.01 | −1.2% | −14.7% |
| hold40 | 110 | **+0.168** | **1.35** | **+6.2%** | −12.2% |
| staged_v2 | 138 | −0.014 | 0.96 | −1.6% | −15.6% |
| smart_hold | 138 | −0.009 | 0.98 | −1.2% | −14.7% |

### 2022-24 (bear + chop + recovery — the old selection window)
| variant | n | exp (R) | PF | CAGR | maxDD |
|---|---|---|---|---|---|
| base | 163 | +0.067 | 1.16 | +2.4% | −11.4% |
| market | 160 | −0.000 | 1.00 | −0.4% | −12.0% |
| brake | 163 | +0.067 | 1.16 | +2.4% | −11.4% |
| tier_flat | 163 | +0.067 | 1.16 | +2.4% | −11.4% |
| hold40 | 68 | −0.324 | 0.54 | −5.7% | −16.5% |
| staged_v2 | 69 | −0.290 | 0.43 | −5.3% | −15.1% |
| smart_hold | 165 | +0.035 | 1.09 | +0.2% | −14.0% |

**Honest revisions this forces:**
- The "+0.082R 2020-21 pass" reported on 2026-06-10 was an accident: zombies
  consumed the budget during exactly the months that would have traded into the
  COVID crash. Clean 2020-21 base is **breakeven** (PF 1.01).
- The old "2022-24 = −0.012R" was zombie-contaminated in the other direction:
  clean base is **+0.067R / PF 1.16** there. Net: the deployed combo is better
  than the old numbers said on the hostile window, worse on the COVID window.
- 2015-16 is genuinely negative (−0.064R) — a real regime weakness (extended
  low-trend chop), not an artifact.

**Why every candidate lost (one line each):**
- `market` — paying the spread up-front loses to resting limits once data is
  honest; the old "market wins" diagnostic was a zombie artifact.
- `tier_flat` — the monthly budget's conviction ranking already admits only
  High-tier signals; the Medium-tier multiplier never binds.
- `hold40` — momentum exits are regime-dependent: +0.168R in trend, −0.23 to
  −0.32R in chop. An unconditional longer leash is net-negative.
- `staged_v2` — the chandelier trail still gives back more than it earns in
  chop (consistent with the original 2026-06-10 finding; 3-ATR stops didn't fix it).
- `smart_hold` (stagnation-cut at 15 bars + 40-bar backstop) — the 15-bar cut
  amputates the same slow trend-riders the longer backstop is meant to capture;
  lost to base on all three windows.
- `brake` — not alpha (≈ base everywhere calm) but **required**: it removes the
  absorbing state. Its visible cost: in windows that stay depressed (2015-16)
  it keeps trading at reduced size instead of freezing, so within-window DD
  prints deeper (−20.3% vs −16.1%); the absorbing alternative is an account
  that never trades again without manual intervention.

## 3. Holdout validation (untouched by every selection decision above)

Deployed config = combo + brake, clean data, halt replay + budget ON:

| window | n | exp (R) | PF | win | CAGR | maxDD | halted days |
|---|---|---|---|---|---|---|---|
| 2017-19 | 220 | +0.081 | **1.197** | 51.4% | **+4.15%** | −15.6% | **2** (was 306) |
| 2025-01→2026-06 | 109 | **+0.188** | **1.470** | 53.2% | **+9.21%** | −10.0% | 0 |

The brake did exactly what it was built for on 2017-19: 2 halted days instead
of 306, trading through the post-Q4-2018 recovery (CAGR 2.1%→4.15% vs the
absorbing halt). The 2025-26 window — the one closest to current conditions —
is the strongest clean result in the book, and it *improved* vs its
contaminated predecessor (+0.188R/PF 1.47 vs +0.118R/PF 1.27): the old number
was dragged down by zombie budget burn, not flattered.

**Verdict on go/no-go #1** (exp > 0 and PF ≥ 1.2 on ≥2 untouched windows): one
solid pass (2025-26), one borderline (2017-19 at PF 1.197, 0.003 under the
bar). Counted honestly: **not yet met**, but close, and now measured on
trustworthy data.

**Deflated Sharpe (go/no-go #2), N = 36 selection trials, var(SR) from the 39
recorded per-period Sharpes:**

| window | PSR (true SR > 0) | DSR (vs E[max SR of 36 luck trials]) |
|---|---|---|
| 2017-19 | 79.8% | **30.7%** |
| 2025-26 | 84.6% | **53.8%** |

Both far below the 95% bar: after 36 recorded tries, the measured edge is not
yet statistically distinguishable from selection luck. (Two caveats pulling
opposite directions: skew/kurtosis omitted → slightly optimistic; var(SR)
pooled across windows of different regimes overstates pure config dispersion →
conservative.) The one evidence channel that does NOT burn DSR is live paper
tracking — which is exactly what the checklist already requires next.

## 4. Where this leaves the go/no-go checklist

1. Expectancy > 0 and PF ≥ 1.2 on ≥ 2 untouched OOS windows — **not yet met**
   (one solid pass, one 0.003 under the bar; see §3).
2. DSR ≥ 0.95 vs ledger N — **30.7% / 53.8%** (see §3). The honest cost of 36
   recorded tries; only live paper evidence improves this without burning more N.
3. CSCV PBO — not re-run tonight (needs the per-period return matrix across
   the variant family; the per-variant trades CSVs exist under /tmp but curves
   were not persisted — flagged as follow-up).
4. ±10% sweeps — must be re-run on clean data (the 2026-06-10 sweep is
   contaminated; its absorbing-halt finding is what triggered tonight's brake).
5. Cadence ≤7/month — holds in every clean run (bar + cap both active).
6. 3–6 months live paper tracking — unchanged, still required.
7. Halt replay ON everywhere — yes, including all numbers in this document.

**Recommendation:** stay on paper. The system is now *honest*; it is not yet
*good*. The clean evidence says the edge is small (+0.07R on 2022-24, ~0 on
2020-21, negative in 2015-16-style chop), and the deployment mechanics
(brake) no longer destroy it. The highest-value next work is not more exit
tuning (five variants just died); it is the research roadmap's Tier-2/3 items:
entry confirmation against the noise-death bucket, the PEAD/text sleeve, and
the ETF mean-reversion sleeve — new return streams, not new knobs on this one.

## 5. Session cost accounting

- Trials burned tonight: 27 (3 diagnostics + 18 r3 + 6 r4) — all ledgered with
  per-period Sharpes; DSR's N reflects them.
- The 20-hour stall: offline reads returned full 13-year frames after the
  refill; three concurrent matrix processes swapped the machine to a
  standstill. Fixed (range-trimmed reads), post-mortem in commit 04d4bdf.
- Survivorship residual: 84 union members are genuinely delisted and
  unfetchable on free data (full list in the refill log); results remain
  OPTIMISTIC by roughly that coverage gap. EODHD/Norgate remains the honest
  upgrade path.

*Produced autonomously 2026-06-10→11 by Claude (Fable 5); user-authorized
full-autonomy session. Every number herein is reproducible from the ledger +
scripts (`experiment_broad_universe.py`, `run_validation_window.py`,
`diagnose_pipeline.py`, `refill_cache.py`).*
