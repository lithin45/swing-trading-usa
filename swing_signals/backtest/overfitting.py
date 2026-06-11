"""Overfitting controls (research file 11 §7): PSR, Deflated Sharpe, CSCV PBO.

The 2026-06 experiment program evaluated ~10 variants against 2022–24 before the
combo was chosen — every number from that window is selected, and selection
inflates Sharpe. These are the standard corrections:

- **PSR** (Bailey & López de Prado 2012): probability that the TRUE Sharpe
  exceeds a benchmark ``sr_star``, given the observed Sharpe, track length, and
  the non-normality of returns (skew/kurtosis widen the estimator's variance).
- **Expected max SR** (the "false strategy theorem"): how high the best of N
  skill-less trials is expected to score by luck alone — the proper benchmark
  once N configurations were tried.
- **DSR** = PSR evaluated at that expected-max benchmark. DSR ≥ 0.95 ⇒ the edge
  survives its own selection process at 95% confidence.
- **PBO** via CSCV (Bailey, Borwein, López de Prado & Zhu 2017): from a T×N
  matrix of per-period returns across trials, the probability that the
  in-sample winner ranks below median out-of-sample.

Everything is computed on PER-PERIOD (daily) returns — annualization cancels in
the ratios and only obscures the math. No scipy: Φ via ``math.erf``, Φ⁻¹ via
Acklam's rational approximation (|ε| < 1.15e-9, far below estimation noise).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations

EULER_GAMMA = 0.5772156649015329


# ---------------------------------------------------------------------------
# Normal CDF / inverse CDF (no scipy dependency)
# ---------------------------------------------------------------------------

def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# Acklam's inverse-normal coefficients (standard published values).
_A = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
      1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
_B = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
      6.680131188771972e+01, -1.328068155288572e+01)
_C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
      -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
      3.754408661907416e+00)
_P_LOW, _P_HIGH = 0.02425, 1.0 - 0.02425


def norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam). Raises on p outside (0, 1)."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"norm_ppf needs 0 < p < 1, got {p}")
    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / \
               ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
    if p > _P_HIGH:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / \
               ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q / \
           (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0)


# ---------------------------------------------------------------------------
# Moments + Sharpe (per-period)
# ---------------------------------------------------------------------------

def _moments(returns: list[float]) -> tuple[float, float, float, float]:
    """(mean, std, skew, kurtosis) — population moments; kurtosis is Pearson (normal=3)."""
    n = len(returns)
    if n < 2:
        return 0.0, 0.0, 0.0, 3.0
    mean = sum(returns) / n
    devs = [r - mean for r in returns]
    m2 = sum(d * d for d in devs) / n
    std = math.sqrt(m2)
    if std == 0:
        return mean, 0.0, 0.0, 3.0
    m3 = sum(d ** 3 for d in devs) / n
    m4 = sum(d ** 4 for d in devs) / n
    return mean, std, m3 / std ** 3, m4 / std ** 4


def sharpe_per_period(returns: list[float]) -> float:
    """Plain per-period Sharpe (mean/std, rf=0). Annualize with √252 if you must."""
    mean, std, _, _ = _moments(returns)
    return mean / std if std > 0 else 0.0


# ---------------------------------------------------------------------------
# PSR / expected-max SR / DSR
# ---------------------------------------------------------------------------

def probabilistic_sharpe(
    sr_hat: float, sr_star: float, n_obs: int, skew: float = 0.0, kurt: float = 3.0
) -> float:
    """P[true SR > sr_star | observed sr_hat over n_obs returns with given moments]."""
    if n_obs < 2:
        return 0.0
    denom = 1.0 - skew * sr_hat + (kurt - 1.0) / 4.0 * sr_hat ** 2
    if denom <= 0:  # extreme moments — estimator variance blows up; no confidence
        return 0.0
    z = (sr_hat - sr_star) * math.sqrt(n_obs - 1.0) / math.sqrt(denom)
    return norm_cdf(z)


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """E[max SR of n skill-less trials] — the luck benchmark (false strategy theorem).

    ``var_sr`` is the variance of PER-PERIOD trial Sharpe ratios. With one trial
    there was no selection, so the benchmark is 0 (plain PSR).
    """
    if n_trials <= 1 or var_sr <= 0:
        return 0.0
    e = math.e
    return math.sqrt(var_sr) * (
        (1.0 - EULER_GAMMA) * norm_ppf(1.0 - 1.0 / n_trials)
        + EULER_GAMMA * norm_ppf(1.0 - 1.0 / (n_trials * e))
    )


@dataclass(frozen=True)
class DeflatedSharpe:
    sr_hat: float          # observed per-period Sharpe
    sr_benchmark: float    # E[max SR] under n_trials
    psr_vs_zero: float     # P[true SR > 0]
    dsr: float             # P[true SR > benchmark] — the deflated number
    n_obs: int
    n_trials: int
    skew: float
    kurt: float


def deflated_sharpe(
    returns: list[float], *, n_trials: int, var_sr_trials: float
) -> DeflatedSharpe:
    """DSR for one strategy's per-period returns, deflated by its selection breadth.

    ``n_trials`` is how many configurations were effectively tried (the trial
    ledger's count); ``var_sr_trials`` the variance of their per-period Sharpes.
    Both inputs must come from honest bookkeeping — an understated N overstates
    the DSR, which defeats the point.
    """
    mean, std, skew, kurt = _moments(returns)
    sr_hat = mean / std if std > 0 else 0.0
    bench = expected_max_sharpe(n_trials, var_sr_trials)
    return DeflatedSharpe(
        sr_hat=sr_hat,
        sr_benchmark=bench,
        psr_vs_zero=probabilistic_sharpe(sr_hat, 0.0, len(returns), skew, kurt),
        dsr=probabilistic_sharpe(sr_hat, bench, len(returns), skew, kurt),
        n_obs=len(returns),
        n_trials=n_trials,
        skew=skew,
        kurt=kurt,
    )


# ---------------------------------------------------------------------------
# CSCV — probability of backtest overfitting
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PBOResult:
    pbo: float                 # fraction of splits where the IS winner ranks below OOS median
    n_splits: int
    n_trials: int
    n_obs: int
    logits: tuple[float, ...]  # one λ per split (negative = IS winner underperformed OOS)


def cscv_pbo(returns_matrix: list[list[float]], n_blocks: int = 8) -> PBOResult:
    """CSCV probability of backtest overfitting from a T×N per-period return matrix.

    ``returns_matrix[t][n]`` = period-t return of trial n (all trials over the SAME
    dates). Rows are cut into ``n_blocks`` contiguous blocks; for every half/half
    block combination the in-sample winner's out-of-sample relative rank becomes a
    logit; PBO = share of logits ≤ 0. Contiguous blocks preserve serial structure
    (the paper's recommendation for autocorrelated P&L).
    """
    t_obs = len(returns_matrix)
    if t_obs == 0:
        raise ValueError("empty returns matrix")
    n_trials = len(returns_matrix[0])
    if n_trials < 2:
        raise ValueError("CSCV needs at least 2 trials")
    if n_blocks % 2 != 0:
        raise ValueError("n_blocks must be even")
    if t_obs < n_blocks:
        raise ValueError(f"need at least {n_blocks} observations, got {t_obs}")

    # Cut rows into n_blocks contiguous blocks (sizes differ by at most 1).
    base, extra = divmod(t_obs, n_blocks)
    blocks: list[list[list[float]]] = []
    start = 0
    for b in range(n_blocks):
        size = base + (1 if b < extra else 0)
        blocks.append(returns_matrix[start:start + size])
        start += size

    def sr_of(rows: list[list[float]], trial: int) -> float:
        return sharpe_per_period([row[trial] for row in rows])

    logits: list[float] = []
    for combo in combinations(range(n_blocks), n_blocks // 2):
        in_rows = [row for b in combo for row in blocks[b]]
        out_rows = [row for b in range(n_blocks) if b not in combo for row in blocks[b]]
        is_sr = [sr_of(in_rows, n) for n in range(n_trials)]
        oos_sr = [sr_of(out_rows, n) for n in range(n_trials)]
        winner = max(range(n_trials), key=lambda n: is_sr[n])
        # Relative OOS rank of the IS winner in (0,1): 1 = best, ranks average ties.
        better = sum(1 for v in oos_sr if v > oos_sr[winner])
        equal = sum(1 for v in oos_sr if v == oos_sr[winner]) - 1
        rank = n_trials - better - equal / 2.0  # average rank, 1..n_trials
        omega = rank / (n_trials + 1.0)
        logits.append(math.log(omega / (1.0 - omega)))

    pbo = sum(1 for v in logits if v <= 0) / len(logits)
    return PBOResult(
        pbo=pbo, n_splits=len(logits), n_trials=n_trials, n_obs=t_obs,
        logits=tuple(logits),
    )
