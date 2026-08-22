from __future__ import annotations
"""Phase 4.3 Statistics Engine: deterministic OLS + Type I ANOVA + lack-of-fit.

Deterministic First: same input bytes produce byte-identical envelopes.
F-distribution CDF via regularized incomplete beta (Lentz continued fraction),
per Numerical Recipes 3rd ed. section 6.4 and Lentz 1976 (Applied Optics 15, 668).
# ponytail: pure-stdlib numerics; upgrade path is scipy.stats.f if third-party
dependencies become acceptable. Anchors locked in numerical_validation tests.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

ENGINE_NAME = "statistics"
ENGINE_VERSION = "0.1.0"
METHOD = "OLS_ANOVA_V1"
BETACF_EPS = 3e-16
BETACF_MAX_ITER = 500
SINGULAR_TOL = 1e-12


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


def _validate_input_schema(data):
    schemas, registry = _load_schemas()
    from jsonschema import Draft202012Validator
    schema = schemas.get("statistics_input.schema.json")
    if schema is None:
        return ["statistics_input.schema.json not found"]
    v = Draft202012Validator(schema, registry=registry)
    errs = sorted(v.iter_errors(data), key=lambda e: list(e.path))
    return [e.message for e in errs]


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
    """Generate a statistics result envelope from validated input."""
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
