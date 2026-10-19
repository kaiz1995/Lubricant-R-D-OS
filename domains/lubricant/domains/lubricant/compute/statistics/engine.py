from __future__ import annotations
"""Phase 4.3 Statistics Engine: deterministic OLS + Type I ANOVA + lack-of-fit.

Deterministic First: same input bytes produce byte-identical envelopes.
F-distribution CDF via regularized incomplete beta (Lentz continued fraction),
per Numerical Recipes 3rd ed. section 6.4 and Lentz 1976 (Applied Optics 15, 668).
# ponytail: pure-stdlib numerics; upgrade path is scipy.stats.f if third-party
dependencies become acceptable. Anchors locked in numerical_validation tests.
"""
import datetime
import hashlib
import json
import math
import sys
from fractions import Fraction
from pathlib import Path

ENGINE_NAME = "statistics"
ENGINE_VERSION = "0.1.0"
METHOD = "OLS_ANOVA_V1"
BETACF_EPS = 3e-16
BETACF_MAX_ITER = 500
SINGULAR_TOL = 1e-12

# --- Step 12 constants (PRECISION_GREASE_DEV batch 2, plan section 7.1) -----
# Planning constants are fixed by the pack so that a sample-size question can
# never be answered by two different numbers in two different documents.
VARIANCE_INPUT_TYPE = "VARIANCE_ANALYSIS"
METHOD_VARIANCE = "NESTED_VARIANCE_V1"
POWER_METHOD = "TWO_SAMPLE_TWO_SIDED_Z_V1"
CI_METHOD = "SATTERSWAITE_ON_MEAN_SQUARE_CONTRAST"
DEFAULT_ALPHA = 0.05
DEFAULT_TARGET_POWER = 0.80
DEFAULT_K = 3.0
# n ~ 16/(delta/sigma)^2 at alpha=0.05 / power 0.80. Reproduces the pack table:
# k>=3 -> n=2, k=2 -> n=4, k=1.5 -> n=8, k<=1 -> n=16 per arm.
PLANNING_NUMERATOR = 16.0
# Below k=3 the rule is "do NOT add replicates, change the method or the
# criterion": under 2 bench positions per round and 30 days per round a k=1.5
# question needs about 8 months, so a project cannot afford two of them a year.
K_MIN_VIABLE = 3.0
BENCH_ROUND_DAYS = 30
BENCH_POSITIONS_PER_ROUND = 2
# Smallest reliably detectable difference ~ 4*sigma/sqrt(n). The square root is
# the point: quadrupling the bench effort only halves the resolution.
RESOLUTION_CONSTANT = 4.0
# df below this means the sample standard deviation is too weak to read alone
# (df=2, i.e. n=3, carries roughly +/-50% relative error) and the CI must be
# reported instead of a bare point estimate.
SMALL_SAMPLE_DF = 5
GAMMA_EPS = 3e-16
GAMMA_MAX_ITER = 500
QUANTILE_ITERATIONS = 200
VERDICT_CONSISTENT_DIFFERENCE = "CONSISTENT_DIFFERENCE"
VERDICT_NO_DETECTABLE_DIFFERENCE = "NO_DETECTABLE_DIFFERENCE"
VERDICT_UNDERPOWERED = "UNDERPOWERED"
VERDICT_REPLICATE_INCONSISTENT = "REPLICATE_INCONSISTENT"
VARIANCE_VERDICTS = (
    VERDICT_CONSISTENT_DIFFERENCE,
    VERDICT_NO_DETECTABLE_DIFFERENCE,
    VERDICT_UNDERPOWERED,
    VERDICT_REPLICATE_INCONSISTENT,
)
VARIANCE_REQUESTS = ("VARIANCE_COMPONENTS", "POWER_ANALYSIS", "CONSISTENCY_CHECK")
EXCLUSION_CENSORED = "CENSORED_NOT_AN_END_POINT"
EXCLUSION_CONFOUNDED = "CONFOUNDED_OBSERVATION"
EXCLUSION_IDENTITY = "MATERIAL_IDENTITY_CONFLICT"


def _load_schemas():
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    schema_dir = Path(__file__).resolve().parents[2] / "schemas"
    schemas = {}
    for p in schema_dir.glob("*.json"):
        schemas[p.name] = json.loads(p.read_text(encoding="utf-8"))
    registry = Registry()
    for s in schemas.values():
        if "$id" in s:
            registry = registry.with_resource(s["$id"], Resource.from_contents(s))
    return schemas, registry


def _validate_schema_named(data, schema_name):
    """Validate against a named schema from the domain schema directory.

    Split out of _validate_input_schema so the variance path validates against
    variance_input.schema.json while the legacy path keeps validating against
    statistics_input.schema.json, with no shared mutable state between them.
    """
    schemas, registry = _load_schemas()
    from jsonschema import Draft202012Validator
    schema = schemas.get(schema_name)
    if schema is None:
        return [schema_name + " not found"]
    validator = Draft202012Validator(schema, registry=registry)
    errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    return [error.message for error in errors]


def _validate_input_schema(data):
    return _validate_schema_named(data, "statistics_input.schema.json")


def _digest_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _betacf(a, b, x):
    """Continued fraction for incomplete beta (modified Lentz). NR 6.4."""
    tiny = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, BETACF_MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < BETACF_EPS:
            break
    return h


def _regularized_beta(x, a, b):
    """I_x(a,b) regularized incomplete beta function."""
    if a <= 0 or b <= 0:
        raise ValueError("beta parameters must be positive")
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    ln_front = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                + a * math.log(x) + b * math.log(1.0 - x))
    front = math.exp(ln_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def f_cdf(f_value, df1, df2):
    """F distribution CDF: P(F <= f)."""
    if df1 <= 0 or df2 <= 0 or f_value < 0:
        return float("nan")
    if f_value == 0:
        return 0.0
    if math.isinf(f_value):
        return 1.0
    ratio = df2 / df1 / f_value
    x = 1.0 / (1.0 + ratio)
    return _regularized_beta(x, df1 / 2.0, df2 / 2.0)


def f_pvalue(f_value, df1, df2):
    """Upper-tail p-value: P(F > f)."""
    if math.isinf(f_value):
        return 0.0
    return max(0.0, min(1.0, 1.0 - f_cdf(f_value, df1, df2)))


def _normal_cdf(z):
    """Standard normal CDF. math.erf is exact to double precision, so the
    power calculation needs no table and stays pure stdlib."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _normal_ppf(p):
    """Inverse standard normal CDF by bisection on _normal_cdf.

    Why bisection instead of a rational approximation: the engine's contract is
    byte-identical output for identical input, so every quantile must be a pure
    function of the probability with no iteration-count surprises. 200 halvings
    on [-40, 40] reach double precision and then repeat, so the result is exact
    and reproducible.
    """
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return float("inf")
    lo, hi = -40.0, 40.0
    for _ in range(QUANTILE_ITERATIONS):
        mid = 0.5 * (lo + hi)
        if _normal_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _regularized_gamma_p(a, x):
    """Lower regularized incomplete gamma P(a, x), the chi-square CDF kernel.

    Series for x < a+1, continued fraction (modified Lentz) otherwise: the same
    structure and the same reasoning as _betacf above. NR 3rd ed. section 6.2.
    """
    if x <= 0.0:
        return 0.0
    if x < a + 1.0:
        ap = a
        total = 1.0 / a
        delta = total
        for _ in range(GAMMA_MAX_ITER):
            ap += 1.0
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * GAMMA_EPS:
                break
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b if abs(b) > tiny else 1.0 / tiny
    h = d
    for i in range(1, GAMMA_MAX_ITER + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < GAMMA_EPS:
            break
    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return 1.0 - q


def chi2_cdf(x, df):
    """Chi-square CDF: P(X <= x)."""
    if df <= 0:
        return float("nan")
    if x <= 0.0:
        return 0.0
    return _regularized_gamma_p(df / 2.0, x / 2.0)


def chi2_quantile(p, df):
    """Inverse chi-square CDF: x with P(X <= x) = p.

    Bracket-and-bisect on chi2_cdf. Deterministic, monotone, and immune to the
    small-df accuracy loss of the closed-form approximations, which matters
    because the variance components are read at df = 2 and df = 3.
    """
    if df <= 0:
        return float("nan")
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return float("inf")
    hi = max(1.0, float(df))
    steps = 0
    while chi2_cdf(hi, df) < p and steps < QUANTILE_ITERATIONS:
        hi *= 2.0
        steps += 1
    lo = 0.0
    for _ in range(QUANTILE_ITERATIONS):
        mid = 0.5 * (lo + hi)
        if chi2_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _satterthwaite_interval(terms, alpha):
    """Confidence interval on a variance quantity written as c1*MS1 + c2*MS2 + ...

    terms: list of (coefficient, mean_square, df). Satterthwaite's
    approximation, which is the standard way to put an interval on a variance
    component built from a difference of mean squares; a naive chi-square
    interval on a difference understates the width badly.

    Returns (point_variance, low, high, df_effective, truncated).

    Two deliberate fail-safe behaviours, both one-sided in the safe direction:
    - A negative moment estimate is not a physical variance, so it is truncated
      to zero and flagged with a lower bound of zero.
    - Satterthwaite's df collapses toward zero as the point estimate does (the
      classic "this component is indistinguishable from zero" case), at which
      point df*point/chi2 collapses too and the raw formula returns absurd values
      like 1e8. Whenever that happens the upper bound falls back to the sum of
      the positive-coefficient chi-square upper bounds, which is a genuine upper
      bound on the quantity (since the negative terms can only reduce it). The
      reported interval can therefore be too wide, never too narrow: the engine
      must never claim less noise than the data supports.
    """
    point = math.fsum(coefficient * ms for coefficient, ms, _ in terms)
    denominator = math.fsum(
        ((coefficient * ms) ** 2) / df for coefficient, ms, df in terms if df > 0
    )
    if denominator <= 0.0:
        return point, 0.0, 0.0, 0.0, point <= 0.0
    conservative_high = 0.0
    for coefficient, ms, df in terms:
        if coefficient > 0.0:
            conservative_high += coefficient * df * ms / chi2_quantile(alpha / 2.0, df)
    magnitude = max(point, 0.0)
    df_eff = (magnitude * magnitude) / denominator
    if point <= 0.0 or df_eff < 1.0:
        return max(0.0, point), 0.0, conservative_high, df_eff, True
    low = df_eff * point / chi2_quantile(1.0 - alpha / 2.0, df_eff)
    high = min(df_eff * point / chi2_quantile(alpha / 2.0, df_eff), conservative_high)
    return point, max(0.0, low), high, df_eff, False


def _lu_decompose(a):
    """In-place LU with partial pivoting. Returns (LU, perm, sign) or None if singular."""
    n = len(a)
    lu = [row[:] for row in a]
    perm = list(range(n))
    sign = 1.0
    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(lu[r][col]))
        if abs(lu[pivot_row][col]) < 1e-300:
            return None
        if pivot_row != col:
            lu[col], lu[pivot_row] = lu[pivot_row], lu[col]
            perm[col], perm[pivot_row] = perm[pivot_row], perm[col]
            sign = -sign
        for r in range(col + 1, n):
            factor = lu[r][col] / lu[col][col]
            lu[r][col] = factor
            for c in range(col + 1, n):
                lu[r][c] -= factor * lu[col][c]
    return lu, perm, sign


def _lu_solve(lu_data, rhs):
    lu, perm, _ = lu_data
    n = len(lu)
    b = [rhs[perm[i]] for i in range(n)]
    for i in range(1, n):
        s = b[i]
        for j in range(i):
            s -= lu[i][j] * b[j]
        b[i] = s
    for i in range(n - 1, -1, -1):
        s = b[i]
        for j in range(i + 1, n):
            s -= lu[i][j] * b[j]
        b[i] = s / lu[i][i]
    return b


def _mat_inverse(a):
    """Matrix inverse via LU solve on identity columns."""
    n = len(a)
    lu_data = _lu_decompose(a)
    if lu_data is None:
        return None
    inv = []
    for i in range(n):
        e = [0.0] * n
        e[i] = 1.0
        inv.append(_lu_solve(lu_data, e))
    # transpose rows to columns
    return [[inv[j][i] for j in range(n)] for i in range(n)]


def _xtx_xty(X, y):
    p = len(X[0])
    n = len(X)
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for k in range(n):
        rk = X[k]
        yk = y[k]
        for i in range(p):
            ri = rk[i]
            xty[i] += ri * yk
            for j in range(i, p):
                v = ri * rk[j]
                xtx[i][j] += v
                if i != j:
                    xtx[j][i] += v
    return xtx, xty


def _build_design_matrix(design_points, sorted_ids, model_order):
    """Scheffe uncentered design matrix. Column order: linear terms by component
    lex order, then interaction terms x_i*x_j for i<j in lex order."""
    q = len(sorted_ids)
    pairs = [(i, j) for i in range(q) for j in range(i + 1, q)]
    terms = ["x_" + sid for sid in sorted_ids]
    if model_order == "QUADRATIC":
        terms.extend("x_" + sorted_ids[i] + "*x_" + sorted_ids[j] for i, j in pairs)
    X = []
    for dp in design_points:
        props = dp["proportions"]
        row = [props[sid] for sid in sorted_ids]
        if model_order == "QUADRATIC":
            row.extend(props[sorted_ids[i]] * props[sorted_ids[j]] for i, j in pairs)
        X.append(row)
    return X, terms


def _validate_business(data):
    reasons = []
    ids = [c["component_id"] for c in data["components"]]
    if len(ids) != len(set(ids)):
        reasons.append("duplicate component_id")
    tol = 1e-9
    seen_runs = set()
    for dp in data["design_points"]:
        rr = dp["run_reference"]
        if rr in seen_runs:
            reasons.append("duplicate design_point run_reference " + rr)
        seen_runs.add(rr)
        prop_sum = math.fsum(dp["proportions"].values())
        if abs(prop_sum - 1.0) > tol:
            reasons.append("proportions sum " + repr(prop_sum) + " != 1.0 for run_reference " + rr)
        extra = set(dp["proportions"]) - set(ids)
        if extra:
            reasons.append("unknown component in proportions: " + sorted(extra)[0] + " for run_reference " + rr)
    run_to_dp = {dp["run_reference"]: dp for dp in data["design_points"]}
    obs_pairs = set()
    for obs in data["observations"]:
        rr = obs["run_reference"]
        if rr not in run_to_dp:
            reasons.append("observation run_reference not found in design_points: " + rr)
        pair = (rr, obs["ctq_reference"])
        if pair in obs_pairs:
            reasons.append("duplicate observation for " + rr + " / " + obs["ctq_reference"])
        obs_pairs.add(pair)
    return reasons


def _ols(X, y):
    """Full-model OLS: returns (beta, xtx_inv, rss) or (None, None, None) if singular."""
    xtx, xty = _xtx_xty(X, y)
    lu_data = _lu_decompose(xtx)
    if lu_data is None:
        return None, None, None
    lu, _, _ = lu_data
    diag = [abs(lu[i][i]) for i in range(len(lu))]
    if max(diag) == 0 or min(diag) < SINGULAR_TOL * max(diag):
        return None, None, None
    beta = _lu_solve(lu_data, xty)
    xtx_inv = _mat_inverse(xtx)
    if xtx_inv is None:
        return None, None, None
    n = len(X)
    fitted = []
    for row in X:
        fitted.append(math.fsum(row[i] * beta[i] for i in range(len(beta))))
    residuals = [y[k] - fitted[k] for k in range(n)]
    rss = math.fsum(e * e for e in residuals)
    return beta, xtx_inv, rss


def _reduced_model_rss(X, y, n_terms):
    """RSS of model using only first n_terms columns. For ANOVA Type I."""
    Xr = [row[:n_terms] for row in X]
    beta, _, rss = _ols(Xr, y)
    if beta is None:
        return None
    return rss


def _anova_type1(X, y, terms, df_error, mse):
    """Sequential (Type I) SS per term. Returns rows list."""
    rows = []
    mean_y = math.fsum(y) / len(y)
    prev_rss = math.fsum((v - mean_y) ** 2 for v in y)
    first_is_intercept = all(abs(row[0] - 1.0) <= 1e-12 for row in X)
    for k in range(1, len(terms) + 1):
        rss_k = _reduced_model_rss(X, y, k)
        if rss_k is None:
            return None
        ss = prev_rss if k == 1 and first_is_intercept else max(0.0, prev_rss - rss_k)
        f_val = (ss / 1.0) / mse if mse > 0 else float("inf")
        p_val = f_pvalue(f_val, 1, df_error)
        rows.append({
            "source": terms[k - 1],
            "row_type": "TERM",
            "sum_squares": ss,
            "df": 1,
            "mean_square": ss,
            "f_value": min(f_val, 1e300),
            "p_value": p_val
        })
        prev_rss = rss_k
    rows.append({
        "source": "RESIDUAL",
        "row_type": "RESIDUAL",
        "sum_squares": prev_rss,
        "df": df_error,
        "mean_square": mse
    })
    return rows


def _lack_of_fit(X, y, beta, design_points, sse):
    """Pure error from replicated design points; LOF = SSE - PE."""
    n = len(y)
    # group observations by identical proportion vectors
    groups = {}
    for k, dp in enumerate(design_points):
        key = tuple(round(dp["proportions"][sid], 12) for sid in sorted(dp["proportions"]))
        groups.setdefault(key, []).append(k)
    m_distinct = len(groups)
    df_pe = n - m_distinct
    if df_pe <= 0:
        return {"status": "NOT_APPLICABLE"}
    ss_pe = 0.0
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        gmean = math.fsum(y[k] for k in idxs) / len(idxs)
        ss_pe += math.fsum((y[k] - gmean) ** 2 for k in idxs)
    p = len(beta)
    df_lof = m_distinct - p
    ss_lof = max(0.0, sse - ss_pe)
    if df_lof <= 0 or ss_pe <= 0 or df_pe <= 0:
        return {"status": "COMPUTED", "sum_squares_lof": ss_lof, "df_lof": max(0, df_lof),
                "sum_squares_pe": ss_pe, "df_pe": df_pe, "f_value": 0.0, "p_value": 1.0}
    f_val = (ss_lof / df_lof) / (ss_pe / df_pe)
    return {"status": "COMPUTED", "sum_squares_lof": ss_lof, "df_lof": df_lof,
            "sum_squares_pe": ss_pe, "df_pe": df_pe,
            "f_value": min(f_val, 1e300), "p_value": f_pvalue(f_val, df_lof, df_pe)}


def _safe_sqrt(value):
    """sqrt that maps non-positive input (including -0.0) to exactly 0.0.

    Variance components are estimated as differences of mean squares and can
    come out numerically negative; a negative variance is not physical and must
    never reach math.sqrt as a domain error.
    """
    return math.sqrt(value) if value > 0.0 else 0.0


def effect_size(group_a, group_b):
    """Cohen's-d class standardized difference between two groups.

    Pooled sigma is the within-group pooled standard deviation
    sqrt(((n_a-1)s_a^2 + (n_b-1)s_b^2)/(n_a+n_b-2)).

    WHY: grease batch-to-batch spread is naturally large and n is small, so a
    raw mean difference says nothing about whether the gap is worth chasing.
    Without an effect size the owner cannot tell a 30 h gap that is pure noise
    from a 30 h gap that is real, and both look like "a difference".

    Returns a dict; cohens_d is None (with a note) when it is not definable
    (fewer than 2 groups of data, or zero pooled sigma with unequal means).
    The sign of d is kept so the direction of the difference survives.
    """
    a = [float(v) for v in group_a]
    b = [float(v) for v in group_b]
    n_a, n_b = len(a), len(b)
    df = n_a + n_b - 2
    mean_a = math.fsum(a) / n_a if n_a else 0.0
    mean_b = math.fsum(b) / n_b if n_b else 0.0
    difference = mean_a - mean_b
    if n_a < 2 or n_b < 2 or df < 1:
        return {
            "n_a": n_a, "n_b": n_b, "df": max(0, df),
            "mean_a": mean_a, "mean_b": mean_b, "mean_difference": difference,
            "pooled_sigma": None, "cohens_d": None,
            "magnitude": "NOT_ESTIMABLE",
            "note": "effect size not estimable: each group needs at least 2 values (df >= 1)"
        }
    var_a = math.fsum((v - mean_a) ** 2 for v in a) / (n_a - 1)
    var_b = math.fsum((v - mean_b) ** 2 for v in b) / (n_b - 1)
    pooled_variance = ((n_a - 1) * var_a + (n_b - 1) * var_b) / df
    pooled_sigma = _safe_sqrt(pooled_variance)
    if pooled_sigma <= 0.0:
        if difference == 0.0:
            return {
                "n_a": n_a, "n_b": n_b, "df": df,
                "mean_a": mean_a, "mean_b": mean_b, "mean_difference": 0.0,
                "pooled_sigma": 0.0, "cohens_d": 0.0, "magnitude": "NEGLIGIBLE",
                "note": "identical groups with zero spread inside both groups"
            }
        return {
            "n_a": n_a, "n_b": n_b, "df": df,
            "mean_a": mean_a, "mean_b": mean_b, "mean_difference": difference,
            "pooled_sigma": 0.0, "cohens_d": None,
            "magnitude": "NOT_ESTIMABLE",
            "note": "pooled sigma is zero while the means differ: the standardized difference is undefined, not infinite"
        }
    d = difference / pooled_sigma
    magnitude = _effect_magnitude(abs(d))
    return {
        "n_a": n_a, "n_b": n_b, "df": df,
        "mean_a": mean_a, "mean_b": mean_b, "mean_difference": difference,
        "pooled_sigma": pooled_sigma, "cohens_d": d, "magnitude": magnitude,
        "note": "Cohen's d thresholds: <0.2 negligible, <0.5 small, <0.8 medium, otherwise large"
    }


def _effect_magnitude(absolute_d):
    if absolute_d < 0.2:
        return "NEGLIGIBLE"
    if absolute_d < 0.5:
        return "SMALL"
    if absolute_d < 0.8:
        return "MEDIUM"
    return "LARGE"


def power_analysis(n, delta, sigma, alpha=DEFAULT_ALPHA):
    """Two-sided two-sample power of a per-arm n against a true difference delta.

    Returns the power as a float in [0, 1]. Method: the standard normal
    approximation POWER_METHOD = TWO_SAMPLE_TWO_SIDED_Z_V1, i.e.
    power = Phi(delta/(sigma*sqrt(2/n)) - z_(1-alpha/2))
          + Phi(-delta/(sigma*sqrt(2/n)) - z_(1-alpha/2)).

    WHY this must be reported next to every "no difference" statement: a low
    power is what turns "we could not measure it" into the wrong reading "there
    is no difference". The caller uses the value to choose between
    NO_DETECTABLE_DIFFERENCE and UNDERPOWERED; those two are not synonyms.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    if delta < 0 or sigma < 0:
        raise ValueError("delta and sigma must be non-negative")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    z_critical = _normal_ppf(1.0 - alpha / 2.0)
    if delta == 0.0:
        return alpha
    if sigma == 0.0:
        # Separation is infinite: the difference is larger than any noise.
        return 1.0
    noncentrality = delta / (sigma * math.sqrt(2.0 / n))
    return min(1.0, max(0.0, _normal_cdf(noncentrality - z_critical)
                       + _normal_cdf(-noncentrality - z_critical)))


def required_n_for_k(k, alpha=DEFAULT_ALPHA, target_power=DEFAULT_TARGET_POWER):
    """Planner output for k = delta/sigma: how many runs, rounds and days.

    At the pack defaults (alpha=0.05, power 0.80) the frozen planning rule
    n ~ PLANNING_NUMERATOR/(delta/sigma)^2 = 16/k^2 is used verbatim so the
    numbers reproduce the frozen step-12 table (k>=3 -> 2, k=2 -> 4,
    k=1.5 -> 8, k<=1 -> 16 per arm). Off the defaults the general form
    2*(z_alpha/2 + z_power)^2 / k^2 is used instead; it is an approximation and
    the returned power is verified against the target afterwards.

    WHEN k < K_MIN_VIABLE (3) the design rule is NOT "add replicates": at
    BENCH_POSITIONS_PER_ROUND = 2 and BENCH_ROUND_DAYS = 30 a k=1.5 question
    needs about 8 months, so a project cannot afford two such answers a year.
    The requirement then moves onto the method instead: SIGMA_MAX = delta/k.
    """
    if k <= 0.0:
        raise ValueError("k must be positive")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if not 0.0 < target_power < 1.0:
        raise ValueError("target_power must be in (0, 1)")
    if alpha == DEFAULT_ALPHA and target_power == DEFAULT_TARGET_POWER:
        numerator = PLANNING_NUMERATOR
    else:
        z_critical = _normal_ppf(1.0 - alpha / 2.0)
        numerator = 2.0 * (z_critical + _normal_ppf(target_power)) ** 2
    per_arm = max(2, int(math.ceil(numerator / (k * k) - 1e-12)))
    # Verify-and-bump: the closed forms above are approximations, so the answer
    # is only accepted once the achieved power actually reaches the target.
    guard = 0
    while _power_for_k(per_arm, k, alpha) < target_power and guard < 1000:
        per_arm += 1
        guard += 1
    achieved = _power_for_k(per_arm, k, alpha)
    total_runs = per_arm * 2
    bench_rounds = int(math.ceil(total_runs / float(BENCH_POSITIONS_PER_ROUND)))
    calendar_days = bench_rounds * BENCH_ROUND_DAYS
    return {
        "k": k,
        "alpha": alpha,
        "target_power": target_power,
        "per_arm_n": per_arm,
        "total_runs": total_runs,
        "bench_rounds_occupied": bench_rounds,
        "calendar_days": calendar_days,
        "calendar_months": round(calendar_days / float(BENCH_ROUND_DAYS), 2),
        "achieved_power": achieved,
        "planning_numerator": numerator,
        "bench_positions_per_round": BENCH_POSITIONS_PER_ROUND,
        "bench_round_days": BENCH_ROUND_DAYS,
        "k_min_viable": K_MIN_VIABLE,
        "feasible": k >= K_MIN_VIABLE,
        "design_rule": ("k < K_MIN_VIABLE: do NOT increase n -- change the method or the "
                        "criterion (SIGMA_MAX = delta/k)" if k < K_MIN_VIABLE else
                        "k >= K_MIN_VIABLE: the pack planning rule n ~ 16/k^2 applies")
    }


def _power_for_k(n, k, alpha):
    """Power depends on k and n only: noncentrality = k*sqrt(n/2)."""
    z_critical = _normal_ppf(1.0 - alpha / 2.0)
    noncentrality = k * math.sqrt(n / 2.0)
    return min(1.0, max(0.0, _normal_cdf(noncentrality - z_critical)
                       + _normal_cdf(-noncentrality - z_critical)))


def sigma_max_requirement(delta, k=DEFAULT_K):
    """SIGMA_MAX = delta / k -- the method-qualification threshold.

    This is the pack's answer to a resolution problem that cannot be bought
    with bench time: instead of asking for more replicates, it asks the method
    itself to be repeatable enough that a k-fold separation is visible at
    n ~ 2-3. If the method cannot deliver, the method fails qualification --
    "the method is unqualified" is not "the data is insufficient".

    WGO_001 real case: delta = 1.5 h (additive 4.5 h vs blank 2.5 h), k = 3
    -> SIGMA_MAX_REQUIREMENT = 0.5 h.
    """
    if k <= 0.0:
        raise ValueError("k must be positive")
    return delta / k


def resolution_table(sigma, n_values, delta=None, k=None):
    """Smallest reliably detectable difference ~ RESOLUTION_CONSTANT * sigma / sqrt(n).

    One row per n. The square root is the whole message: going from n=3 to n=12
    quadruples the bench effort and only halves the smallest visible difference,
    so bench time is a bad place to buy resolution. Bigger signal, lower sigma
    and pairing are the levers that do not consume bench positions.

    `detectable` compares each row against the frozen separation requirement:
    against `delta` directly when it is supplied, otherwise against the
    SIGMA_MAX requirement sigma/k implied by the frozen k (equivalent to
    k >= RESOLUTION_CONSTANT/sqrt(n)). None when neither is available.
    """
    rows = []
    for n in n_values:
        if n < 1:
            raise ValueError("n_values must be >= 1")
        detectable_difference = RESOLUTION_CONSTANT * sigma / math.sqrt(float(n))
        if delta is not None:
            detectable = detectable_difference <= delta
        elif k is not None:
            detectable = detectable_difference <= sigma / k
        else:
            detectable = None
        rows.append({
            "replicates_per_group": int(n),
            "detectable_difference": detectable_difference,
            "detectable": detectable,
            "note": ("scales as 1/sqrt(n): quadrupling replicates only halves this value"
                     if n > 1 else "single replicate: no within-arm error estimate exists")
        })
    return rows


def sigma_confidence_interval(n, sample_sigma, alpha=DEFAULT_ALPHA):
    """Confidence interval for a sigma estimated from n observations.

    Chi-square interval on the variance, then square-rooted:
    sigma * sqrt((n-1)/chi2_(1-alpha/2, n-1)) <= sigma_true <=
    sigma * sqrt((n-1)/chi2_(alpha/2, n-1)).

    Reports both the 95 % interval and `relative_standard_error`
    = 1/sqrt(2*(n-1)), which is the pack's "pm 50 % at n=3" figure quoted in
    the step-12 table (n=3 -> 50 %, n=6 -> 32 %, n=10 -> 24 %).

    WHY: the pack's instruction is "start with uncertainty and let it converge",
    so a bare point estimate is a lie about precision. At n=3 the interval is
    wide enough that the honest reading is "sigma is of order this value",
    never a decision-grade number.
    """
    if n < 2:
        return {
            "n": n, "df": 0, "sample_sigma": sample_sigma,
            "confidence_level": 1.0 - alpha,
            "sigma_low": 0.0, "sigma_high": None,
            "relative_standard_error": None,
            "small_sample": True,
            "limitation": "a single observation carries no replicate information: sigma is not estimable, only bounded"
        }
    df = n - 1
    low = sample_sigma * math.sqrt(df / chi2_quantile(1.0 - alpha / 2.0, df))
    high = sample_sigma * math.sqrt(df / chi2_quantile(alpha / 2.0, df))
    relative_standard_error = 1.0 / math.sqrt(2.0 * df)
    small_sample = df < SMALL_SAMPLE_DF
    limitation = None
    if small_sample:
        limitation = ("df=" + str(df) + ": a sample standard deviation at this df carries roughly "
                      "+/-" + str(int(round(100.0 * relative_standard_error))) + "% relative error; "
                      "report the interval, never the point estimate alone")
    return {
        "n": n, "df": df, "sample_sigma": sample_sigma,
        "confidence_level": 1.0 - alpha,
        "sigma_low": low, "sigma_high": high,
        "relative_standard_error": relative_standard_error,
        "small_sample": small_sample,
        "limitation": limitation
    }


def consistency_check(observations):
    """Same-arm replicate agreement. Outcome contradiction outranks every number.

    Two failure modes, both mapped to REPLICATE_INCONSISTENT:
    1. Same arm (one group_reference) with mutually contradictory OUTCOMES:
       one replicate produced the event, another ran to the end without it.
       Judged on the outcome flags alone -- the measured values are ignored, so
       no arithmetic can average the contradiction away.
    2. Material identity conflict: two replicates that claim the same
       sample_id but come from different batch_id. Those are different things
       wearing the same name (WGO_001: the photo said ASA#2, the worksheet said
       ASA#4, and the pair had to be discarded). They are never averaged.

    `observations` uses the canonical internal shape produced by
    _variance_observations: observation_reference / group_reference / level /
    sample_id / batch_id / run_reference / value / at / event_occurred, plus the
    internal `_censored` flag. Censored replicates have an UNKNOWN outcome, not
    a "no event" outcome, so they never count as a contradiction; they are
    simply outside the outcome comparison.
    """
    by_group = {}
    identity = {}
    outcomes = {}
    order = []
    for observation in observations:
        censored_here = bool(observation.get("_censored"))
        by_group.setdefault(observation["group_reference"], []).append(observation)
        sample_id = observation.get("sample_id")
        batch_id = observation.get("batch_id")
        if sample_id is not None and batch_id is not None:
            identity.setdefault(sample_id, set()).add(batch_id)
        if not censored_here and "event_occurred" in observation:
            outcomes.setdefault(observation["group_reference"], set())
            outcomes[observation["group_reference"]].add(bool(observation["event_occurred"]))
        if observation["group_reference"] not in order:
            order.append(observation["group_reference"])
    inconsistent_arms = []
    for group_reference in order:
        seen = outcomes.get(group_reference)
        if seen and len(seen) > 1:
            members = by_group[group_reference]
            inconsistent_arms.append({
                "group_reference": group_reference,
                "with_event": sorted(member["observation_reference"] for member in members
                                     if not member.get("_censored")
                                     and member.get("event_occurred") is True),
                "without_event": sorted(member["observation_reference"] for member in members
                                        if not member.get("_censored")
                                        and member.get("event_occurred") is False),
                "observations": sorted(member["observation_reference"] for member in members)
            })
    identity_conflicts = []
    for sample_id in sorted(identity):
        batches = sorted(identity[sample_id])
        if len(batches) > 1:
            identity_conflicts.append({
                "sample_id": sample_id,
                "batch_ids": batches,
                "reason": "replicates share a sample_id but differ in batch_id: "
                          "different things with the same name, never averaged"
            })
    if inconsistent_arms or identity_conflicts:
        return {
            "verdict": VERDICT_REPLICATE_INCONSISTENT,
            "arms_checked": len(order),
            "observations_checked": len(observations),
            "inconsistent_arms": inconsistent_arms,
            "material_identity_conflicts": identity_conflicts,
            "basis": ("OUTCOME_ONLY_NO_NUMBERS_USED" if inconsistent_arms
                      else "MATERIAL_IDENTITY_ONLY"),
            "note": "REPLICATE_INCONSISTENT is judged on outcomes and material identity, "
                    "never on the numbers"
        }
    return {
        "verdict": "CONSISTENT",
        "arms_checked": len(order),
        "observations_checked": len(observations),
        "inconsistent_arms": [],
        "material_identity_conflicts": [],
        "basis": "OUTCOME_ONLY_NO_NUMBERS_USED",
        "note": "same-arm replicates agree on outcome"
    }


def _censor_index(data):
    """Map observation_reference -> censoring entry, and validate the flags.

    Censoring is never an end-point. The four flags
    (event_occurred / event_time / censoring_type / stop_reason) exist because a
    right-censored value recorded in `event_time` silently poisons every
    variance estimate downstream: the observation looks like a finished run
    while it only means "we stopped watching".
    """
    index = {}
    reasons = []
    for entry in data.get("censoring", []):
        reference = entry["observation_reference"]
        if reference in index:
            reasons.append("duplicate censoring entry for observation_reference " + reference)
            continue
        index[reference] = entry
        censoring_type = entry["censoring_type"]
        stop_reason = str(entry.get("stop_reason") or "").strip()
        if censoring_type != "NONE":
            if entry.get("event_occurred") is not False:
                reasons.append("censored observation " + reference
                               + " has event_occurred=true: an event that occurred is not censored")
            if entry.get("event_time") is not None:
                reasons.append("censored observation " + reference
                               + " carries event_time: a censoring time must never be recorded as an endpoint")
            if not stop_reason:
                reasons.append("censored observation " + reference
                               + " has no stop_reason: reject fail-closed, an unexplained stop is not an observation")
        elif entry.get("event_occurred") is True and entry.get("event_time") is None:
            reasons.append("observation " + reference
                           + " reports event_occurred=true without an event_time")
    known = {obs["observation_reference"] for obs in data.get("observations", [])}
    for reference in sorted(index):
        if reference not in known:
            reasons.append("censoring entry references unknown observation_reference " + reference)
    return index, reasons


def _instant_key(text):
    """ISO-8601 instant -> comparable float (UTC seconds). None if unparseable.

    Naive timestamps are read as UTC so that a comparison is always total;
    mixing naive and aware values must never depend on the host timezone, or
    the engine would stop being deterministic across machines.
    """
    if text is None:
        return None
    text = str(text).strip()
    if not text:
        return None
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment.timestamp()


def _confounded_references(observations, intervention_events):
    """Observation references inside a confounds=true intervention window.

    Why: WGO_001 had one apparently clean pair (8 h vs 6 h, delta = 2 h) that
    straddled an "equipment re-adjusted and re-tested" event; the arithmetic
    gave sigma ~ 1.77 h with no explanatory power. A confounded observation may
    be recorded but must be excluded from the variance estimate.

    Fail-closed details, all deliberate:
    - An intervention without `until` is open-ended: everything at or after it
      stays suspect until someone records an end, so no confounder is silently
      dropped by omission.
    - An unparseable `at` is a rejection, never a silent "no window".
    - If any confounds=true window exists, every observation must carry a
      parseable `at`, otherwise the engine cannot prove the observation is
      outside the window and must refuse rather than guess.
    """
    reasons = []
    confounded = set()
    windows = []
    for event in intervention_events:
        start = _instant_key(event.get("at"))
        if start is None:
            reasons.append("intervention_events[] entry " + str(event.get("event_id"))
                           + " has an unparseable at: an unreadable window would silently hide a confounder")
            continue
        if event.get("until") is not None:
            end = _instant_key(event.get("until"))
            if end is None:
                reasons.append("intervention_events[] entry " + str(event.get("event_id"))
                               + " has an unparseable until")
                continue
            if end < start:
                reasons.append("intervention_events[] entry " + str(event.get("event_id"))
                               + " ends before it starts")
                continue
        else:
            end = float("inf")
        windows.append((event, start, end))
    if reasons:
        return confounded, reasons
    confounds_any = any(event.get("confounds") for event, _, _ in windows)
    for observation in observations:
        reference = observation["observation_reference"]
        moment = _instant_key(observation.get("at"))
        if moment is None:
            if confounds_any:
                reasons.append("observation " + reference
                               + " has no parseable at while a confounds=true intervention exists: "
                                 "the engine cannot prove it is outside the window")
            continue
        for event, start, end in windows:
            if event.get("confounds") and start <= moment <= end:
                confounded.add(reference)
                break
    return confounded, reasons


def _material_identity_conflicts(observations):
    """Replicates sharing a sample_id across different batch_ids.

    Material identity must be verifiable: an observation traces to sample_id +
    batch_id. A pair that disagrees on batch_id is not a replicate pair, it is
    two different materials sharing a label, and averaging them is the exact
    error that made WGO_001 discard its only clean pair.
    """
    mapping = {}
    for obs in observations:
        mapping.setdefault(obs["sample_id"], set()).add(obs["batch_id"])
    conflicted_samples = {sample_id for sample_id, batches in mapping.items() if len(batches) > 1}
    return {obs["observation_reference"] for obs in observations
            if obs["sample_id"] in conflicted_samples}


def _nested_stats(observations):
    """Group sizes for the three-level nested layout, with balance flags.

    Levels: BATCH (preparation kettle) > BENCH (a run/round) > MEASUREMENT
    (a repeat reading inside one run). No equal-n assumption anywhere; every
    expected-mean-square coefficient below is computed from the observed group
    sizes.

    Note on the BENCH level: because runs are nested inside batches, the bench
    component absorbs both round-to-round bench variation and sample-to-sample
    spread inside one batch. That is the honest reading for grease -- soap fibre
    structure is uneven inside a single kettle -- but it must be stated, because
    it means sigma_bench is not a pure instrument repeatability figure.
    """
    batches = {}
    order = []
    for obs in observations:
        batch_id = obs["batch_id"]
        if batch_id not in batches:
            batches[batch_id] = {}
            order.append(batch_id)
        batches[batch_id].setdefault(obs["run_reference"], []).append(obs["value"])
    counters = {
        "batch_count": len(order),
        "run_count": 0,
        "observation_count": 0,
        "batches_with_one_run": 0,
        "runs_with_one_observation": 0,
        "unbalanced": False,
        "run_sizes": [],
    }
    for batch_id in order:
        runs = batches[batch_id]
        counters["run_count"] += len(runs)
        if len(runs) == 1:
            counters["batches_with_one_run"] += 1
        for values in runs.values():
            counters["observation_count"] += len(values)
            counters["run_sizes"].append(len(values))
            if len(values) == 1:
                counters["runs_with_one_observation"] += 1
    counters["unbalanced"] = len(set(counters["run_sizes"])) > 1
    return batches, order, counters


def _nested_mean_squares(observations):
    """SS / df / mean squares and the expected-mean-square weights.

    Derivation for the nested random-effects layout
    y_ijk = mu + b_i + r_ij + e_ijk, with Var(b) = sigma_batch^2,
    Var(r) = sigma_bench^2, Var(e) = sigma_meas^2, a batches, n_i runs inside
    batch i (n_ij readings inside run ij), N_i readings in batch i, N total:

      E[MS_meas]  = sigma_meas^2
      E[MS_bench] = sigma_meas^2 + k_meas * sigma_bench^2
          k_meas  = (N - sum_i N_i/n_i) / df_bench
      E[MS_batch] = sigma_meas^2 + k_bench * sigma_bench^2 + k_batch * sigma_batch^2
          k_batch = (N - sum_i N_i^2/N) / df_batch
          k_bench = (sum_i (N_i/n_i) - sum_i (N_i/n_i) * N_i / N) / df_batch

    All three weights collapse to the textbook balanced values (m, m, m*n) when
    every run carries the same number of readings; each was verified by hand on
    the balanced layout.

    Returns the mean squares, their dfs, the weights, and `not_estimable`
    reasons for every level this layout cannot separate.
    """
    batches, order, counters = _nested_stats(observations)
    a_batches = counters["batch_count"]
    total_n = counters["observation_count"]
    reasons = []
    ss_measurement = 0.0
    df_measurement = 0
    ss_bench = 0.0
    df_bench = 0
    batch_sizes = {}
    readings_per_run_sum = 0.0
    weighted_batch_reading_sum = 0.0
    for batch_id in order:
        runs = batches[batch_id]
        values_all = [v for values in runs.values() for v in values]
        batch_n = len(values_all)
        batch_sizes[batch_id] = batch_n
        batch_mean = math.fsum(values_all) / batch_n
        run_count = len(runs)
        df_bench += run_count - 1
        readings_per_run_sum += batch_n / run_count
        weighted_batch_reading_sum += (batch_n / run_count) * batch_n
        for values in runs.values():
            run_n = len(values)
            run_mean = math.fsum(values) / run_n
            ss_bench += run_n * (run_mean - batch_mean) ** 2
            ss_measurement += math.fsum((v - run_mean) ** 2 for v in values)
            df_measurement += run_n - 1
    grand_mean = math.fsum(
        batch_sizes[batch_id] * (math.fsum(
            v for values in batches[batch_id].values() for v in values)
            / batch_sizes[batch_id])
        for batch_id in order) / total_n
    ss_batch = 0.0
    for batch_id in order:
        batch_n = batch_sizes[batch_id]
        batch_mean = math.fsum(
            v for values in batches[batch_id].values() for v in values) / batch_n
        ss_batch += batch_n * (batch_mean - grand_mean) ** 2
    df_batch = a_batches - 1
    ms_measurement = ss_measurement / df_measurement if df_measurement > 0 else None
    ms_bench = ss_bench / df_bench if df_bench > 0 else None
    ms_batch = ss_batch / df_batch if df_batch > 0 else None
    if ms_measurement is None:
        reasons.append("sigma_meas not estimable: no run carries two or more replicate readings")
    if ms_bench is None:
        reasons.append("sigma_bench not estimable: no batch carries two or more runs")
    if ms_batch is None:
        reasons.append("sigma_batch not estimable: fewer than two batches")
    k_meas = None
    if df_bench > 0:
        candidate = (total_n - readings_per_run_sum) / df_bench
        if candidate > 0.0:
            k_meas = candidate
        else:
            reasons.append("sigma_bench not estimable: the expected-mean-square weight is zero for this layout")
    k_batch = None
    k_bench = None
    if df_batch > 0:
        candidate_batch = (total_n - math.fsum(batch_sizes[b] ** 2 for b in order) / total_n) / df_batch
        if candidate_batch > 0.0:
            k_batch = candidate_batch
        else:
            reasons.append("sigma_batch not estimable: the expected-mean-square weight is zero for this layout")
        k_bench = (readings_per_run_sum - weighted_batch_reading_sum / total_n) / df_batch
        if k_bench < 0.0:
            k_bench = 0.0
    return {
        "ss_measurement": ss_measurement,
        "df_measurement": df_measurement,
        "ms_measurement": ms_measurement,
        "ss_bench": ss_bench,
        "df_bench": df_bench,
        "ms_bench": ms_bench,
        "ss_batch": ss_batch,
        "df_batch": df_batch,
        "ms_batch": ms_batch,
        "k_meas": k_meas,
        "k_batch": k_batch,
        "k_bench": k_bench,
        "counters": counters,
        "not_estimable": reasons
    }


def variance_components(data, noise_scope_group_reference=None):
    """Nested (BATCH / BENCH / MEASUREMENT) variance decomposition for step 12.

    Estimates sigma_meas, sigma_bench, sigma_batch and sigma_total with a
    confidence interval for each, using the expected-mean-square method for
    unequal n (balance is never assumed).

    Three data-quality rules are enforced before any number is produced:
    1. Censored observations are excluded from every estimate -- a right-censored
       value means "we stopped watching", never an endpoint.
    2. Confounded observations (inside an intervention window declared
       confounds=true) are excluded and listed.
    3. Replicates sharing a sample_id across different batch_ids are excluded
       and reported; they are never averaged.

    `noise_scope_group_reference` restricts the decomposition to one formulation
    arm. This is not cosmetic: batch and bench spread must be measured WITHIN a
    single formulation. Pooling two formulations into one nested tree would put
    the between-formulation difference straight into sigma_batch and inflate the
    noise scale until a real difference looks like scatter -- the exact failure
    this step exists to prevent.

    Estimable levels are walked bottom-up: the deepest estimable level is the
    residual, and every level above it is the standard difference
    sigma^2_L = (MS_L - MS_below) / k_L with k_L from _nested_mean_squares. A
    level the layout cannot separate is reported as null, not as zero, so a
    missing component can never be mistaken for a zero one.

    Returns a dict. status is "COMPUTED" when at least one level is estimable,
    otherwise "NOT_ESTIMABLE" with `reasons`, which the caller turns into a
    REJECTED envelope -- never an exception.
    """
    observations = data.get("observations", [])
    scope_note = None
    censor_index, reasons = _censor_index(data)
    if reasons:
        return {"status": "NOT_ESTIMABLE", "reasons": reasons}
    # Confounding and identity are checked over EVERY observation, not just the
    # scoped ones: the data-quality report must be complete, or an unusable
    # observation outside the noise scope would vanish without a trace.
    confounded, reasons = _confounded_references(observations, data.get("intervention_events", []))
    if reasons:
        return {"status": "NOT_ESTIMABLE", "reasons": reasons}
    conflicted = _material_identity_conflicts(observations)
    usable_all = []
    excluded = []
    for observation in observations:
        reference = observation["observation_reference"]
        censor = censor_index.get(reference)
        if censor is not None and censor["censoring_type"] != "NONE":
            excluded.append({
                "observation_reference": reference,
                "reason": EXCLUSION_CENSORED,
                "detail": "censoring_type=" + censor["censoring_type"]
                          + " stop_reason=" + str(censor.get("stop_reason"))
            })
            continue
        if reference in confounded:
            excluded.append({
                "observation_reference": reference,
                "reason": EXCLUSION_CONFOUNDED,
                "detail": "falls inside an intervention window declared confounds=true"
            })
            continue
        if reference in conflicted:
            excluded.append({
                "observation_reference": reference,
                "reason": EXCLUSION_IDENTITY,
                "detail": "sample_id " + str(observation["sample_id"])
                          + " appears under more than one batch_id"
            })
            continue
        usable_all.append(observation)
    censored_count = sum(1 for entry in excluded if entry["reason"] == EXCLUSION_CENSORED)
    confounded_count = sum(1 for entry in excluded if entry["reason"] == EXCLUSION_CONFOUNDED)
    identity_count = sum(1 for entry in excluded if entry["reason"] == EXCLUSION_IDENTITY)
    usable = usable_all
    if noise_scope_group_reference is not None:
        usable = [observation for observation in usable_all
                  if observation["group_reference"] == noise_scope_group_reference]
        if not usable:
            return {"status": "NOT_ESTIMABLE",
                    "reasons": ["no usable observation belongs to the declared noise scope group "
                                + noise_scope_group_reference + ": the noise scale would be "
                                "estimated from nothing"]}
        scope_note = ("sigma components estimated within group_reference "
                      + noise_scope_group_reference
                      + " only: pooling formulations would fold the between-formulation "
                        "difference into sigma_batch")
    if not usable:
        return {"status": "NOT_ESTIMABLE",
                "reasons": ["no usable observation remains after censoring, confounding and "
                            "material-identity exclusions"]}
    stats = _nested_mean_squares(usable)
    levels = []
    if stats["df_measurement"] > 0 and stats["ms_measurement"] is not None:
        levels.append(("MEASUREMENT", stats["ms_measurement"], stats["df_measurement"]))
    if stats["df_bench"] > 0 and stats["ms_bench"] is not None:
        levels.append(("BENCH", stats["ms_bench"], stats["df_bench"]))
    if stats["df_batch"] > 0 and stats["ms_batch"] is not None:
        levels.append(("BATCH", stats["ms_batch"], stats["df_batch"]))
    if not levels:
        return {"status": "NOT_ESTIMABLE",
                "reasons": stats["not_estimable"] or ["the layout carries no df at any level"]}
    weight_of = {
        "MEASUREMENT": 1.0,
        "BENCH": stats["k_meas"] if stats["k_meas"] is not None else 1.0,
        "BATCH": stats["k_batch"] if stats["k_batch"] is not None else 1.0,
    }
    # Bottom-up: deepest estimable level is the residual, each higher level is a
    # difference of mean squares divided by its expected-mean-square weight.
    component_terms = {}
    component_variance = {}
    for index, (name, ms_value, df_value) in enumerate(levels):
        if index == 0:
            component_variance[name] = ms_value
            component_terms[name] = [(1.0, ms_value, df_value)]
            continue
        below_name, below_ms, below_df = levels[index - 1]
        weight = weight_of[name]
        component_variance[name] = max(0.0, (ms_value - below_ms) / weight)
        component_terms[name] = [(1.0 / weight, ms_value, df_value),
                                 (-1.0 / weight, below_ms, below_df)]
    intervals = {}
    truncated_any = False
    for name in ("MEASUREMENT", "BENCH", "BATCH"):
        if name not in component_terms:
            intervals[name] = (None, None, 0.0)
            continue
        (_, low, high, df_effective,
         truncated) = _satterthwaite_interval(component_terms[name], DEFAULT_ALPHA)
        intervals[name] = (low, high, df_effective)
        truncated_any = truncated_any or truncated
    total_terms = []
    # sigma^2_total is the sum of the level variances, so its contrast is the
    # sum of the level contrasts; coefficients are accumulated per mean square
    # so a mean square that appears in two contrasts is only counted once.
    accumulated = {}
    for name in ("MEASUREMENT", "BENCH", "BATCH"):
        for coefficient, ms_value, df_value in component_terms.get(name, []):
            key = (ms_value, df_value)
            accumulated[key] = accumulated.get(key, 0.0) + coefficient
    total_terms = [(coefficient, ms_value, df_value)
                   for (ms_value, df_value), coefficient in sorted(accumulated.items())
                   if coefficient != 0.0]
    variance_measurement = component_variance.get("MEASUREMENT")
    variance_bench = component_variance.get("BENCH")
    variance_batch = component_variance.get("BATCH")
    variance_total = math.fsum(
        value for value in (variance_measurement, variance_bench, variance_batch)
        if value is not None)
    if total_terms:
        (_, low_total, high_total, df_total_effective,
         truncated_total) = _satterthwaite_interval(total_terms, DEFAULT_ALPHA)
    else:
        low_total = high_total = 0.0
        df_total_effective = 0.0
    limitations = []
    for name, label in (("MEASUREMENT", "sigma_meas"), ("BENCH", "sigma_bench"),
                        ("BATCH", "sigma_batch")):
        df_effective = intervals[name][2]
        if 0.0 < df_effective < SMALL_SAMPLE_DF:
            relative_error = 100.0 / math.sqrt(2.0 * df_effective)
            error_text = (str(int(round(relative_error))) + "%"
                          if relative_error < 1000.0 else
                          "a large fraction of the estimate")
            limitations.append(
                label + " has effective df=" + str(int(round(df_effective)))
                + ": a sample standard deviation at this df carries roughly +/-"
                + error_text
                + " relative error, so the confidence interval is the honest answer, "
                  "not the point estimate (n=3 is roughly +/-50%)")
    for name, label in (("MEASUREMENT", "sigma_meas"), ("BENCH", "sigma_bench"),
                        ("BATCH", "sigma_batch")):
        if name not in component_terms:
            limitations.append(label + " not estimable in this layout: reported as null, never as zero")
    if variance_measurement is None and variance_bench is not None:
        limitations.append("no run carries a replicate reading, so the measurement level is absent: "
                           "sigma_bench is the two-level residual and includes measurement noise")
    for index, (name, ms_value, df_value) in enumerate(levels):
        if index == 0:
            continue
        below_name, below_ms, below_df = levels[index - 1]
        if ms_value < below_ms and component_variance[name] == 0.0:
            limitations.append(name + " level came out negative from the mean-square "
                               "difference: truncated to zero and the interval upper bound widened "
                               "conservatively, so it is never understated")
    if stats["counters"]["unbalanced"]:
        limitations.append("unbalanced nested design: variance components were derived from "
                           "expected-mean-square coefficients computed for unequal n "
                           "(equal n was never assumed)")
    if stats["counters"]["batches_with_one_run"]:
        limitations.append(str(stats["counters"]["batches_with_one_run"])
                           + " batch(es) carry a single run: their bench and batch variation "
                             "cannot be separated")
    if stats["counters"]["runs_with_one_observation"]:
        limitations.append(str(stats["counters"]["runs_with_one_observation"])
                           + " run(s) carry a single reading: they cannot inform sigma_meas")
    for reason in stats["not_estimable"]:
        if reason not in limitations:
            limitations.append(reason)
    if censored_count:
        limitations.append(str(censored_count) + " censored observation(s) excluded from every "
                           "estimate (a censoring time is never an end-point)")
    if confounded_count:
        limitations.append(str(confounded_count) + " confounded observation(s) excluded from every "
                           "estimate (inside an intervention window)")
    if identity_count:
        limitations.append(str(identity_count) + " observation(s) with a material-identity conflict "
                           "excluded and never averaged")
    if scope_note is not None:
        limitations.append(scope_note)
    return {
        "status": "COMPUTED",
        "sigma_meas": (_safe_sqrt(variance_measurement)
                       if variance_measurement is not None else None),
        "sigma_meas_ci_low": (None if intervals["MEASUREMENT"][0] is None
                              else _safe_sqrt(intervals["MEASUREMENT"][0])),
        "sigma_meas_ci_high": (None if intervals["MEASUREMENT"][1] is None
                               else _safe_sqrt(intervals["MEASUREMENT"][1])),
        "sigma_bench": _safe_sqrt(variance_bench) if variance_bench is not None else None,
        "sigma_bench_ci_low": (None if intervals["BENCH"][0] is None
                               else _safe_sqrt(intervals["BENCH"][0])),
        "sigma_bench_ci_high": (None if intervals["BENCH"][1] is None
                                else _safe_sqrt(intervals["BENCH"][1])),
        "sigma_batch": _safe_sqrt(variance_batch) if variance_batch is not None else None,
        "sigma_batch_ci_low": (None if intervals["BATCH"][0] is None
                               else _safe_sqrt(intervals["BATCH"][0])),
        "sigma_batch_ci_high": (None if intervals["BATCH"][1] is None
                                else _safe_sqrt(intervals["BATCH"][1])),
        "sigma_total": _safe_sqrt(variance_total),
        "sigma_total_ci_low": _safe_sqrt(low_total),
        "sigma_total_ci_high": _safe_sqrt(high_total),
        "variance_meas": variance_measurement,
        "variance_bench": variance_bench,
        "variance_batch": variance_batch,
        "variance_total": variance_total,
        "df_meas": intervals["MEASUREMENT"][2],
        "df_bench": intervals["BENCH"][2],
        "df_batch": intervals["BATCH"][2],
        "df_total": df_total_effective,
        "mean_squares": {
            "measurement_within_bench": stats["ms_measurement"],
            "bench_within_batch": stats["ms_bench"],
            "batch": stats["ms_batch"]
        },
        "ems_coefficients": {"k_meas": stats["k_meas"], "k_batch": stats["k_batch"],
                             "k_bench": stats["k_bench"]},
        "confidence_level": 1.0 - DEFAULT_ALPHA,
        "ci_method": CI_METHOD,
        "observations_used": len(usable),
        "observations_excluded": len(excluded),
        "excluded_observations": excluded,
        "censored_excluded": censored_count,
        "confounded_excluded": confounded_count,
        "identity_conflicts_excluded": identity_count,
        "structure": {
            "batch_count": stats["counters"]["batch_count"],
            "run_count": stats["counters"]["run_count"],
            "observation_count_used": stats["counters"]["observation_count"],
            "balanced": not stats["counters"]["unbalanced"],
            "runs_with_one_observation": stats["counters"]["runs_with_one_observation"],
            "batches_with_one_run": stats["counters"]["batches_with_one_run"]
        },
        "limitations": limitations
    }


def decide_variance_verdict(consistency, difference, sigma, preregistered_delta,
                            power, per_arm_n, k_required=DEFAULT_K,
                            alpha=DEFAULT_ALPHA, target_power=DEFAULT_TARGET_POWER):
    """Choose exactly one of the four verdicts, and say why.

    Conflating UNDERPOWERED with NO_DETECTABLE_DIFFERENCE is the most expensive
    error in grease R&D: it converts "we cannot measure it" into "there is no
    difference" and so justifies a wrong product decision on a design that was
    never capable of answering the question. The two are separate values here on
    purpose, and the decision order below is what keeps them separate.

    Decision order (each step can only make the claim weaker, never stronger):
      1. Replicate contradiction outranks every number. An arm in which one run
         produced the event and another ran to completion has no mean worth
         comparing, so the verdict is REPLICATE_INCONSISTENT regardless of what
         the arithmetic says.
      2. |difference| > k_required * sigma is a separated signal -> the verdict
         is CONSISTENT_DIFFERENCE (replicates already agreed in step 1).
      3. Otherwise the question is only answerable if the design could have
         answered it. If nothing was compared, or sigma is unknown or zero, or
         power < target_power, or the method's own repeatability exceeds the
         frozen SIGMA_MAX = delta/k requirement, the verdict is UNDERPOWERED --
         never NO_DETECTABLE_DIFFERENCE.
      4. Only with a powered design and no separated difference is
         NO_DETECTABLE_DIFFERENCE justified.

    k_observed = |difference| / sigma; k_ratio = (delta / sigma) / k_required, so
    k_ratio >= 1 means the measured repeatability meets the frozen requirement.
    """
    sigma_max = (sigma_max_requirement(preregistered_delta, k_required)
                 if preregistered_delta is not None else None)
    k_observed = (abs(difference) / sigma if difference is not None
                  and sigma is not None and sigma > 0.0 else None)
    k_ratio = (preregistered_delta / sigma / k_required
               if preregistered_delta is not None and sigma is not None and sigma > 0.0
               else None)
    basis = None
    if consistency is not None and consistency.get("verdict") == VERDICT_REPLICATE_INCONSISTENT:
        if consistency.get("inconsistent_arms"):
            basis = ("same-arm replicates contradict on outcome (one event, one no-event): judged "
                     "on the outcome flags alone, no arithmetic used")
        else:
            basis = ("replicates share a sample_id across different batch_ids: different things "
                     "with the same name, never averaged")
        verdict = VERDICT_REPLICATE_INCONSISTENT
    elif k_observed is not None and k_observed > k_required:
        basis = ("observed difference " + repr(difference) + " exceeds k_required*sigma = "
                 + repr(k_required) + "*" + repr(sigma) + " (k_observed " + repr(k_observed)
                 + " > " + repr(k_required) + ")")
        verdict = VERDICT_CONSISTENT_DIFFERENCE
    else:
        underpowered = []
        if difference is None:
            underpowered.append("no comparison was performed: the difference question is "
                                "unanswered, which is not the same as answered negatively")
        if sigma is None:
            underpowered.append("sigma is not estimable from this design: without a noise scale "
                                "no difference can be judged real or negligible")
        elif sigma <= 0.0:
            underpowered.append("sigma is zero: the layout carries no replicate spread to "
                                "separate a signal from")
        if power is None:
            underpowered.append("power could not be computed, so the design's ability to detect "
                                "the pre-registered difference is unknown")
        elif power < target_power:
            underpowered.append("power " + repr(power) + " < target " + repr(target_power)
                                + ": the design cannot resolve the pre-registered difference")
        if k_ratio is not None and k_ratio < 1.0:
            underpowered.append("measured sigma exceeds the SIGMA_MAX = delta/k requirement "
                                "(k_ratio " + repr(k_ratio) + " < 1): the method itself is "
                                "unqualified, which is not a data-shortage problem")
        # NOTE: a small OBSERVED difference is not evidence of low power -- it is
        # the plain NO_DETECTABLE_DIFFERENCE case, provided the design was
        # capable. Only an unresolvable DESIGN (power, sigma, or an unqualified
        # method) makes the verdict UNDERPOWERED. Treating "difference looks
        # small" as underpowered would flip the two verdicts back into each
        # other, which is the exact confusion this function exists to prevent.
        if underpowered:
            basis = "; ".join(underpowered)
            verdict = VERDICT_UNDERPOWERED
        else:
            basis = ("the design was powered (" + repr(power) + " >= " + repr(target_power)
                     + "), sigma is estimable, the pre-registered delta is resolvable, and no "
                       "difference exceeding k_required*sigma was found")
            verdict = VERDICT_NO_DETECTABLE_DIFFERENCE
    return {
        "verdict": verdict,
        "basis": basis,
        "k_required": k_required,
        "k_observed": k_observed,
        "k_ratio": k_ratio,
        "sigma_max_requirement": sigma_max,
        "target_power": target_power,
        "alpha": alpha,
        "per_arm_n": per_arm_n,
        "verdicts_available": list(VARIANCE_VERDICTS)
    }


def _arm_values(observations, group_reference):
    """Values of one comparison arm, plus its replicate and batch counts.

    Censored, confounded and identity-conflicted observations are already gone
    before this is called: an arm mean must never be computed over a censoring
    time or over two materials wearing one label.
    """
    values = [observation["value"] for observation in observations
              if observation["group_reference"] == group_reference]
    runs = {observation["run_reference"] for observation in observations
            if observation["group_reference"] == group_reference}
    batches = {observation["batch_id"] for observation in observations
               if observation["group_reference"] == group_reference}
    return {
        "group_reference": group_reference,
        "n": len(values),
        "values": values,
        "mean": math.fsum(values) / len(values) if values else None,
        "run_count": len(runs),
        "batch_count": len(batches)
    }


def _replicate_structure_summary(data, usable, excluded):
    """Echo the declared replicate structure and compare it with the data.

    One replicate_structure entry describes one group, so the comparison is
    group-to-group: declared entries at a level vs distinct observed groups at
    that level (BATCH -> distinct batch_id, BENCH -> distinct run_reference,
    MEASUREMENT -> readings). Comparing the declared `n` to an observation count
    would be meaningless, because `n` means "size of that group", not "number of
    observations at this level".

    The declared and observed counts disagreeing is not an error by itself --
    runs get lost -- but the caller must see both, because a variance component
    computed from fewer groups than were planned is a weaker statement than the
    plan assumed. Reporting only the observed counts would hide that.
    """
    declared = []
    for entry in data.get("replicate_structure", []):
        declared.append({
            "level": entry["level"],
            "n": entry["n"],
            "group_reference": entry["group_reference"],
            "sample_reference": entry.get("sample_reference"),
            "batch_reference": entry.get("batch_reference")
        })
    declared_groups = {}
    for entry in declared:
        declared_groups[entry["level"]] = declared_groups.get(entry["level"], 0) + 1
    observed_groups = {
        "BATCH": len({observation["batch_id"] for observation in usable}),
        "BENCH": len({observation["run_reference"] for observation in usable}),
        "MEASUREMENT": len(usable),
    }
    observed_groups = {level: count for level, count in observed_groups.items() if count}
    shortfalls = []
    for level in sorted(declared_groups):
        planned = declared_groups[level]
        actual = observed_groups.get(level, 0)
        if actual < planned:
            shortfalls.append({
                "level": level,
                "declared_groups": planned,
                "observed_groups": actual,
                "note": "fewer groups than declared at this level: the component is estimated "
                        "from a weaker design than planned"
            })
    return {
        "declared": declared,
        "declared_groups_by_level": declared_groups,
        "observed_groups_by_level": observed_groups,
        "shortfalls": shortfalls,
        "usable_observations": len(usable),
        "excluded_observations": len(excluded)
    }


def _validate_variance_business(data):
    """Business rules for the variance input, applied after schema validation.

    Fail-closed wherever a silent assumption could hide a data-quality defect.
    """
    reasons = []
    seen_observations = set()
    for observation in data["observations"]:
        reference = observation["observation_reference"]
        if reference in seen_observations:
            reasons.append("duplicate observation_reference " + reference)
        seen_observations.add(reference)
    arms = data.get("comparison_arms")
    group_references = {observation["group_reference"] for observation in data["observations"]}
    if arms is not None:
        for key in ("arm_a_group_reference", "arm_b_group_reference"):
            if arms[key] not in group_references:
                reasons.append("comparison_arms." + key + " " + arms[key]
                               + " does not match any observation group_reference")
        if arms["arm_a_group_reference"] == arms["arm_b_group_reference"]:
            reasons.append("comparison_arms names the same group twice: there is nothing to compare")
    for entry in data.get("censoring", []):
        if entry["censoring_type"] != "NONE" and not str(entry.get("stop_reason") or "").strip():
            reasons.append("censored observation " + entry["observation_reference"]
                           + " carries no stop_reason: reject fail-closed, an unexplained stop "
                             "is not an observation")
    return reasons


def _variance_observations(data):
    """Canonical internal observation shape for the variance path.

    One shape for every downstream consumer, so the censoring flag, the material
    identity and the confounder timestamp are always resolved the same way. The
    internal `_censored` flag never reaches the output envelope; it exists so no
    code path can accidentally treat a censoring time as a result.

    Material identity is not optional: sample_id + batch_id are carried through
    verbatim, because an observation that cannot be traced to a specific sample
    from a specific batch cannot be used as a replicate at all.
    """
    observations = []
    for entry in data["observations"]:
        observations.append({
            "observation_reference": entry["observation_reference"],
            "level": entry["level"],
            "group_reference": entry["group_reference"],
            "sample_id": entry["sample_id"],
            "batch_id": entry["batch_id"],
            "run_reference": entry["run_reference"],
            "value": float(entry["value"]),
            "at": entry.get("at"),
            "event_occurred": entry.get("event_occurred"),
            "event_time": entry.get("event_time"),
            "_censored": False
        })
    censor_index, _ = _censor_index(data)
    for observation in observations:
        entry = censor_index.get(observation["observation_reference"])
        if entry is not None and entry["censoring_type"] != "NONE":
            observation["_censored"] = True
    return observations


def _variance_power_block(preregistered_delta, sigma_for_power, per_arm_n, alpha, target_power):
    """Power and required-n block over the frozen planning constants.

    The frozen sigma is preferred over the freshly estimated one whenever both
    exist: step 12 compares against the method-characterisation noise, it does
    not re-estimate it. Re-estimating sigma inside the design loop is exactly
    the mistake the pack forbids, because estimating sigma needs an order of
    magnitude more data than using a known sigma does.

    status is NOT_COMPUTABLE (with a reason) when there is no delta or no sigma;
    it never silently returns a default power, because a fabricated power is
    what makes an UNDERPOWERED design look conclusive.
    """
    if preregistered_delta is None or sigma_for_power is None:
        return {
            "status": "NOT_COMPUTABLE",
            "reason": ("power needs both a pre-registered difference and a sigma scale; "
                       + ("pre-registered delta is absent" if preregistered_delta is None
                          else "no sigma is available (neither frozen nor estimable)")),
            "power": None,
            "per_arm_n": per_arm_n,
            "alpha": alpha,
            "target_power": target_power
        }
    if sigma_for_power <= 0.0:
        return {
            "status": "COMPUTED",
            "power": 1.0 if preregistered_delta > 0.0 else alpha,
            "per_arm_n": per_arm_n,
            "alpha": alpha,
            "target_power": target_power,
            "sigma_used": sigma_for_power,
            "k_ratio": None,
            "required_n": None,
            "note": "sigma is zero: any non-zero difference is infinitely separated"
        }
    k = preregistered_delta / sigma_for_power
    return {
        "status": "COMPUTED",
        "power": power_analysis(per_arm_n, preregistered_delta, sigma_for_power, alpha),
        "per_arm_n": per_arm_n,
        "alpha": alpha,
        "target_power": target_power,
        "sigma_used": sigma_for_power,
        "k_ratio": k,
        "required_n": required_n_for_k(k, alpha, target_power),
        "note": ("k >= K_MIN_VIABLE: the pack planning rule n ~ 16/k^2 applies"
                 if k >= K_MIN_VIABLE else
                 "k < K_MIN_VIABLE: do NOT increase n -- change the method or the criterion "
                 "(SIGMA_MAX = delta/k)")
    }


def analyze_variance(data, input_bytes=None):
    """Step-12 variance assessment: is the difference real?

    Answers the three questions the pack says are unanswerable today:
    1. Is the difference between formulations larger than batch spread plus
       measurement repeatability?
    2. How repeatable is the bench itself, and is that good enough for the
       criterion's resolution?
    3. Which observations are censored, invalid or replicate-inconsistent?

    Output is an envelope in the existing engine shape (method / parameters /
    input_digest / status / rejection_reasons / result / evidence). Rejection is
    a REJECTED envelope carrying reasons -- never a raised exception -- so the
    caller can always record why the question could not be answered.
    """
    requested = set(data["analyses"])
    unknown = sorted(requested - set(VARIANCE_REQUESTS))
    if unknown:
        return _build_rejected(data, input_bytes,
                               ["unknown analysis requested: " + unknown[0]])
    schema_errors = _validate_schema_named(data, "variance_input.schema.json")
    if schema_errors:
        return _build_rejected(data, input_bytes,
                               ["input schema validation failed: " + schema_errors[0]])
    business_reasons = _validate_variance_business(data)
    if business_reasons:
        return _build_rejected(data, input_bytes, business_reasons)
    observations = _variance_observations(data)
    consistency = consistency_check(observations)
    arms = data.get("comparison_arms")
    # Noise is scoped to the reference arm (arm B) when two arms are declared.
    # Measuring batch/bench spread across both formulations would fold the
    # between-formulation difference into sigma_batch, which is precisely the
    # error that makes a real difference look like scatter.
    noise_scope = arms["arm_b_group_reference"] if arms is not None else None
    components = variance_components(data, noise_scope)
    if components["status"] != "COMPUTED":
        return _build_rejected(data, input_bytes, components["reasons"])
    alpha = data.get("alpha", DEFAULT_ALPHA)
    target_power = data.get("target_power", DEFAULT_TARGET_POWER)
    k_required = data.get("k_required", DEFAULT_K)
    preregistered_delta = data.get("preregistered_delta")
    frozen_sigma = data.get("frozen_sigma")
    control_band = data.get("control_band")
    excluded_references = {entry["observation_reference"]
                           for entry in components["excluded_observations"]}
    comparison_usable = [observation for observation in observations
                         if not observation["_censored"]
                         and observation["observation_reference"] not in excluded_references]
    arms = data.get("comparison_arms")
    difference = None
    effect = None
    arm_a = None
    arm_b = None
    if arms is not None:
        arm_a = _arm_values(comparison_usable, arms["arm_a_group_reference"])
        arm_b = _arm_values(comparison_usable, arms["arm_b_group_reference"])
        if arm_a["mean"] is not None and arm_b["mean"] is not None:
            difference = arm_a["mean"] - arm_b["mean"]
            effect = effect_size(arm_a["values"], arm_b["values"])
    sigma_total = components["sigma_total"]
    sigma_for_power = frozen_sigma if frozen_sigma is not None else sigma_total
    per_arm_n = arm_a["run_count"] if arm_a is not None and arm_a["run_count"] else \
        components["structure"]["run_count"]
    power_block = _variance_power_block(preregistered_delta, sigma_for_power,
                                        max(1, per_arm_n), alpha, target_power)
    decision = decide_variance_verdict(
        consistency, difference, sigma_total, preregistered_delta,
        power_block.get("power"), max(1, per_arm_n), k_required, alpha, target_power)
    resolution = resolution_table(
        preregistered_delta if preregistered_delta is not None else sigma_total,
        data.get("resolution_n_values", [2, 3, 6, 12]),
        delta=preregistered_delta,
        k=None if preregistered_delta is not None else k_required)
    if frozen_sigma is not None:
        sigma_estimate = sigma_confidence_interval(
            max(2, int(round(components["df_total"])) + 1), frozen_sigma, alpha)
    else:
        sigma_estimate = sigma_confidence_interval(
            max(2, int(round(components["df_total"])) + 1), sigma_total, alpha)
    result = {
        "verdict": decision["verdict"],
        "verdict_basis": decision["basis"],
        "verdict_values_available": decision["verdicts_available"],
        "variance_components": {
            "sigma_meas": components["sigma_meas"],
            "sigma_meas_ci_low": components["sigma_meas_ci_low"],
            "sigma_meas_ci_high": components["sigma_meas_ci_high"],
            "sigma_bench": components["sigma_bench"],
            "sigma_bench_ci_low": components["sigma_bench_ci_low"],
            "sigma_bench_ci_high": components["sigma_bench_ci_high"],
            "sigma_batch": components["sigma_batch"],
            "sigma_batch_ci_low": components["sigma_batch_ci_low"],
            "sigma_batch_ci_high": components["sigma_batch_ci_high"],
            "sigma_total": components["sigma_total"],
            "sigma_total_ci_low": components["sigma_total_ci_low"],
            "sigma_total_ci_high": components["sigma_total_ci_high"],
            "confidence_level": components["confidence_level"],
            "ci_method": components["ci_method"],
            "df_meas": components["df_meas"],
            "df_bench": components["df_bench"],
            "df_batch": components["df_batch"],
            "small_sample_warning": any("relative error" in limitation
                                        for limitation in components["limitations"])
        },
        "variance_balance": {
            "variance_meas": components["variance_meas"],
            "variance_bench": components["variance_bench"],
            "variance_batch": components["variance_batch"],
            "variance_total": components["variance_total"],
            "mean_squares": components["mean_squares"],
            "ems_coefficients": components["ems_coefficients"],
            "structure": components["structure"]
        },
        "replicate_structure": _replicate_structure_summary(
            data,
            [observation for observation in observations if not observation["_censored"]
             and observation["observation_reference"] not in excluded_references],
            components["excluded_observations"]),
        "data_quality": {
            "observations_total": len(observations),
            "observations_used": components["observations_used"],
            "observations_excluded": components["observations_excluded"],
            "censored_excluded": components["censored_excluded"],
            "confounded_excluded": components["confounded_excluded"],
            "identity_conflicts_excluded": components["identity_conflicts_excluded"],
            "excluded_observations": components["excluded_observations"],
            "rule_censoring": ("a censored observation is never an endpoint: right-censored values "
                               "are excluded from every estimate, and a censored observation "
                               "without a stop_reason is rejected fail-closed"),
            "rule_material_identity": ("every observation traces to sample_id + batch_id; replicates "
                                       "sharing a sample_id across batch_ids are different things "
                                       "with the same name and are never averaged"),
            "rule_confounding": ("observations inside an intervention window declared confounds=true "
                                 "are flagged and excluded from the variance estimate")
        },
        "consistency": consistency,
        "comparison": {
            "arm_a": arm_a,
            "arm_b": arm_b,
            "difference": difference,
            "effect_size": effect,
            "k_required": k_required,
            "k_observed": decision["k_observed"],
            "k_ratio": decision["k_ratio"],
            "sigma_max_requirement": decision["sigma_max_requirement"]
        },
        "power": power_block,
        "sigma_estimate_used": sigma_estimate,
        "frozen_inputs": {
            "frozen_sigma_reference": data.get("frozen_sigma_reference"),
            "frozen_sigma": frozen_sigma,
            "control_band": control_band,
            "preregistered_delta": preregistered_delta,
            "sigma_source": ("FROZEN_METHOD_CHARACTERIZATION" if frozen_sigma is not None
                             else "ESTIMATED_FROM_THIS_DESIGN")
        },
        "resolution_table": resolution,
        "limitations": components["limitations"]
    }
    if input_bytes is not None:
        digest = _digest_bytes(input_bytes)
    else:
        digest = _digest_bytes(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return {
        "schema_version": "0.1.0",
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "method": METHOD_VARIANCE,
        "parameters": {
            "analysis_type": VARIANCE_INPUT_TYPE,
            "variance_method": "EXPECTED_MEAN_SQUARE_NESTED_RANDOM_EFFECTS_V1",
            "ci_method": CI_METHOD,
            "power_method": POWER_METHOD,
            "levels": ["MEASUREMENT", "BENCH", "BATCH"],
            "alpha": alpha,
            "target_power": target_power,
            "k_required": k_required,
            "planning_numerator": PLANNING_NUMERATOR,
            "bench_round_days": BENCH_ROUND_DAYS,
            "bench_positions_per_round": BENCH_POSITIONS_PER_ROUND,
            "resolution_constant": RESOLUTION_CONSTANT,
            "requested_analyses": sorted(requested)
        },
        "input_digest": digest,
        "status": "OK",
        "rejection_reasons": [],
        "result": result,
        "evidence": [{
            "evidence_id": "variance-computation",
            "statement": ("deterministic nested variance decomposition (expected-mean-square, "
                          "unequal-n), Satterthwaite confidence intervals, two-sided power and a "
                          "resolution table computed by the engine; the four-value verdict is "
                          "decided by decide_variance_verdict with UNDERPOWERED kept separate from "
                          "NO_DETECTABLE_DIFFERENCE"),
            "source": "engine internal deterministic algorithm",
            "status": "OBSERVED"
        }]
    }


def _statistics_replicate_components(data, dps, y):
    """Design-point-level replicate scatter for a statistics input.

    A statistics input has no batch/bench nesting, but it DOES have replicated
    design points (the same formulation listed more than once), and those
    replicates are the only noise scale available without a variance input. So
    this is the honest two-level split the data supports:

      MS_within  = pooled within-formulation scatter  -> sigma_replicate
      MS_between = between-formulation-mean scatter
      F = MS_between / MS_within -> p_value

    That F test is literally the "is the difference between formulations real, or
    is it replicate scatter?" question, and it is the only form of it a
    statistics input can answer. The full three-level
    BATCH/BENCH/MEASUREMENT decomposition needs replicate_structure, censoring
    and intervention windows, which a statistics input does not carry: the
    caller must supply a variance input for that, and this function says so
    rather than quietly substituting the design-point split for it.
    """
    groups = {}
    for index, design_point in enumerate(dps):
        key = tuple(round(design_point["proportions"][component], 12)
                    for component in sorted(design_point["proportions"]))
        groups.setdefault(key, []).append(index)
    replicated = {key: indexes for key, indexes in groups.items() if len(indexes) > 1}
    df_within = sum(len(indexes) - 1 for indexes in replicated.values())
    ss_within = 0.0
    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        group_mean = math.fsum(y[index] for index in indexes) / len(indexes)
        ss_within += math.fsum((y[index] - group_mean) ** 2 for index in indexes)
    ms_within = ss_within / df_within if df_within > 0 else None
    sigma_replicate = _safe_sqrt(ms_within) if ms_within is not None else None
    group_means = [math.fsum(y[index] for index in indexes) / len(indexes)
                   for indexes in groups.values()]
    df_between = len(groups) - 1
    ms_between = None
    if df_between > 0:
        grand_mean = math.fsum(y) / len(y)
        ss_between = math.fsum(len(indexes) * (
            math.fsum(y[index] for index in indexes) / len(indexes) - grand_mean) ** 2
            for indexes in groups.values())
        ms_between = ss_between / df_between
    f_value = (ms_between / ms_within
               if ms_between is not None and ms_within not in (None, 0.0) else None)
    p_value = (f_pvalue(f_value, df_between, df_within)
               if f_value is not None and df_within > 0 else None)
    sigma_between = None
    if len(group_means) > 1:
        mean_of_means = math.fsum(group_means) / len(group_means)
        sigma_between = math.sqrt(math.fsum((value - mean_of_means) ** 2
                                            for value in group_means) / (len(group_means) - 1))
    note = ("design-point-level replicate split: MS_within estimates repeatability at a fixed "
            "formulation; the three-level BATCH/BENCH/MEASUREMENT decomposition requires a "
            "variance input with replicate_structure, censoring and intervention_events")
    if not replicated:
        note = ("no formulation is listed twice, so within-formulation repeatability is not "
                "estimable and the F test cannot separate a real difference from replicate "
                "scatter; add replicated design points or use a variance input")
    return {
        "status": "COMPUTED" if df_within > 0 else "NOT_ESTIMABLE",
        "scope": "DESIGN_POINT_LEVEL_SPLIT",
        "sigma_replicate": sigma_replicate,
        "sigma_replicate_ci_low": (None if sigma_replicate is None else
                                   sigma_confidence_interval(
                                       df_within + 1, sigma_replicate)["sigma_low"]),
        "sigma_replicate_ci_high": (None if sigma_replicate is None else
                                    sigma_confidence_interval(
                                        df_within + 1, sigma_replicate)["sigma_high"]),
        "sigma_between": sigma_between,
        "ms_within": ms_within,
        "ms_between": ms_between,
        "df_within": df_within,
        "df_between": df_between,
        "f_value": f_value,
        "p_value": p_value,
        "distinct_design_points": len(groups),
        "replicated_design_points": len(replicated),
        "note": note,
        "limitation": "sigma_replicate at df=" + str(df_within)
                      + " carries roughly +/-"
                      + str(int(round(100.0 / math.sqrt(2.0 * df_within))))
                      + "% relative error" if df_within > 0 else None
    }


def _statistics_native_sections(data, dps, y, mse, requested):
    """New gated result sections for a legacy STATISTICAL_ANALYSIS input.

    Only ever called when a caller explicitly asks for one of the step-12
    analysis names, so a legacy request produces byte-identical output to
    before. Each section reports exactly what this input can and cannot support:
    inventing a delta or an outcome flag here would be the same class of error as
    fabricating the verdict.
    """
    sections = {}
    if "VARIANCE_COMPONENTS" in requested:
        sections["variance_components"] = _statistics_replicate_components(data, dps, y)
    if "POWER_ANALYSIS" in requested:
        sigma = _safe_sqrt(mse) if mse else None
        sections["power_analysis"] = _variance_power_block(
            None, sigma, max(1, len(dps)), DEFAULT_ALPHA, DEFAULT_TARGET_POWER)
        sections["power_analysis"]["reason"] = (
            "a statistics input carries no pre-registered delta, so power cannot be computed "
            "from it: supply a variance input with preregistered_delta (step 3 criterion) "
            "and, ideally, the frozen sigma from step 5")
        sections["power_analysis"]["residual_sigma_squared"] = mse
    if "CONSISTENCY_CHECK" in requested:
        sections["consistency_check"] = {
            "verdict": "NOT_APPLICABLE",
            "reason": ("a statistics input carries no event_occurred / censoring / stop_reason "
                       "flags, so same-arm outcome agreement cannot be judged; the replicate "
                       "inconsistency rule needs a variance input"),
            "arms_checked": 0,
            "observations_checked": 0,
            "inconsistent_arms": [],
            "material_identity_conflicts": [],
            "note": "reporting NOT_APPLICABLE rather than CONSISTENT: an unchecked rule is not a passed rule"
        }
    return sections


def _skew_kurt(residuals):
    n = len(residuals)
    if n < 3:
        return 0.0, 0.0
    mean = math.fsum(residuals) / n
    m2 = math.fsum((e - mean) ** 2 for e in residuals) / n
    if m2 == 0:
        return 0.0, 0.0
    m3 = math.fsum((e - mean) ** 3 for e in residuals) / n
    m4 = math.fsum((e - mean) ** 4 for e in residuals) / n
    skew = m3 / (m2 ** 1.5)
    kurt = m4 / (m2 ** 2) - 3.0
    return skew, kurt


def analyze_statistics(data, input_bytes=None):
    """Generate a statistics result envelope from validated input.

    Dispatches on input_type so that one engine and one CLI channel serve both
    the legacy STATISTICAL_ANALYSIS object and the step-12 VARIANCE_ANALYSIS
    object. The legacy path is untouched: its result keys are still built exactly
    as before, and the new step-12 sections are only attached when the caller
    explicitly requests them, so an unmodified legacy input produces
    byte-identical output to before this change.
    """
    if isinstance(data, dict) and data.get("input_type") == VARIANCE_INPUT_TYPE:
        return analyze_variance(data, input_bytes)
    schema_errors = _validate_input_schema(data)
    if schema_errors:
        return _build_rejected(data, input_bytes, ["input schema validation failed: " + schema_errors[0]])
    reasons = _validate_business(data)
    if reasons:
        return _build_rejected(data, input_bytes, reasons)

    ctq = data["response_ctq"]
    obs_map = {}
    for obs in data["observations"]:
        if obs["ctq_reference"] != ctq:
            continue
        obs_map[obs["run_reference"]] = obs["value"]
    # filter design points to those with observations for this CTQ
    dps = [dp for dp in data["design_points"] if dp["run_reference"] in obs_map]
    y = [obs_map[dp["run_reference"]] for dp in dps]
    sorted_ids = sorted(c["component_id"] for c in data["components"])
    X, terms = _build_design_matrix(dps, sorted_ids, data["model_order"])
    p = len(terms)
    n = len(y)
    if n < p:
        return _build_rejected(data, input_bytes,
            ["model not estimable: insufficient observations (" + str(n) + ") for " + str(p) + " parameters"])
    beta, xtx_inv, rss_full = _ols(X, y)
    if beta is None:
        return _build_rejected(data, input_bytes, ["singular information matrix: design points do not support the requested model"])
    df_error = n - p
    mse = rss_full / df_error if df_error > 0 else 0.0

    # coefficients with SE / t / p
    coeffs = []
    for i, term in enumerate(terms):
        var_i = max(0.0, xtx_inv[i][i] * mse)
        se = math.sqrt(var_i)
        t_val = beta[i] / se if se > 0 else float("inf") if beta[i] > 0 else float("-inf") if beta[i] < 0 else 0.0
        p_val = f_pvalue(t_val * t_val, 1, df_error) if se > 0 else 0.0
        coeffs.append({"term": term, "estimate": beta[i], "std_error": se, "t_value": min(max(t_val, -1e300), 1e300), "p_value": p_val})

    # fit stats
    mean_y = math.fsum(y) / n
    sst = math.fsum((v - mean_y) ** 2 for v in y)
    r2 = 1.0 - rss_full / sst if sst > 0 else 1.0
    adj_r2 = (1.0 - (rss_full / df_error) / (sst / (n - 1))
              if sst > 0 and n > 1 and df_error > 0 else r2)

    # ANOVA Type I (only if requested or always? Always compute; requested_analyses gates output sections)
    # The Scheffe coefficient matrix has no explicit intercept, but its q
    # linear columns sum to one. Replace x_0 by that sum for nested Type I SS;
    # this preserves the full-model span without making OLS coefficients singular.
    q = len(sorted_ids)
    anova_X = [[math.fsum(row[:q])] + row[1:] for row in X]
    anova_terms = ["INTERCEPT"] + terms[1:]
    anova_rows = _anova_type1(anova_X, y, anova_terms, df_error, mse)
    if anova_rows is None:
        return _build_rejected(data, input_bytes, ["reduced model not estimable during Type I SS computation"])

    # residuals
    fitted = []
    for row in X:
        fitted.append(math.fsum(row[i] * beta[i] for i in range(p)))
    residuals = [y[k] - fitted[k] for k in range(n)]
    std_res = []
    sqrt_mse = math.sqrt(mse) if mse > 0 else 0.0
    for e in residuals:
        std_res.append(e / sqrt_mse if sqrt_mse > 0 else 0.0)
    skew, kurt = _skew_kurt(residuals)

    lof = _lack_of_fit(X, y, beta, dps, rss_full)

    requested = set(data["requested_analyses"])
    result = {
        "response_ctq": ctq,
        "coefficients": coeffs,
        "anova_table": anova_rows,
        "fit_statistics": {"r_squared": min(max(r2, 0.0), 1.0), "adj_r_squared": adj_r2, "sigma_squared": mse},
        "residual_analysis": {
            "residuals": [{"run_reference": dps[k]["run_reference"], "residual": residuals[k]} for k in range(n)],
            "standardized_residuals": [{"run_reference": dps[k]["run_reference"], "std_residual": std_res[k]} for k in range(n)],
            "skewness": skew,
            "kurtosis": kurt
        },
        "lack_of_fit": lof
    }
    # Step-12 sections are attached ONLY when explicitly requested. The guard is
    # what keeps the legacy gold fixture byte-identical: an input that asks only
    # for ANOVA / REGRESSION / RESIDUAL / LACK_OF_FIT must produce exactly the
    # result object it produced before this change.
    extra_sections = requested & set(VARIANCE_REQUESTS)
    if extra_sections:
        result.update(_statistics_native_sections(data, dps, y, mse, requested))

    if input_bytes is not None:
        digest = _digest_bytes(input_bytes)
    else:
        digest = _digest_bytes(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    envelope = {
        "schema_version": "0.1.0",
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "method": METHOD,
        "parameters": {
            "parameterization": "SCHEFFE_UNCENTERED_V1",
            "model_order": data["model_order"],
            "term_order": terms,
            "anova_type": "TYPE_I_SEQUENTIAL",
            "response_ctq": ctq
        },
        "input_digest": digest,
        "status": "OK",
        "rejection_reasons": [],
        "result": result,
        "evidence": [{
            "evidence_id": "statistics-computation",
            "statement": "deterministic OLS + Type I ANOVA computed from supplied design points and observations; F p-values via Lentz regularized incomplete beta (NR 6.4)",
            "source": "engine internal deterministic algorithm",
            "status": "OBSERVED"
        }]
    }
    return envelope


def _build_rejected(data, input_bytes, reasons):
    if input_bytes is not None:
        digest = _digest_bytes(input_bytes)
    elif isinstance(data, dict):
        digest = _digest_bytes(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    else:
        digest = _digest_bytes(b"")
    return {
        "schema_version": "0.1.0",
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "method": METHOD,
        "parameters": {},
        "input_digest": digest,
        "status": "REJECTED",
        "rejection_reasons": reasons,
        "result": {},
        "evidence": []
    }


def _write_output(path, envelope):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes((json.dumps(envelope, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def main():
    if len(sys.argv) != 3:
        print("Usage: python -m domains.lubricant.compute.statistics.engine <input.json> <output.json>", file=sys.stderr)
        return 2
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2])
    try:
        raw = inp.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        env = _build_rejected({}, raw if "raw" in locals() else b"", ["input read/parse failed: " + str(e)])
        _write_output(out, env)
        return 0
    env = analyze_statistics(data, raw)
    _write_output(out, env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
