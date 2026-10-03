from __future__ import annotations
"""Phase 4.2 constrained mixture DOE engine.

Deterministic First: same input bytes produce byte-identical envelopes.
Simplex lattice (Scheffe m=1/2) and D-optimal greedy determinant maximization.
# ponytail: greedy det is a first-order D-optimal approximation; upgrade path
# is Fedorov exchange algorithm if candidate set grows beyond a few hundred points.
"""
import hashlib
import itertools
import json
import math
import sys
from pathlib import Path

from .factorial import (
    effect_columns,
    half_fraction_runs,
    plot_error_term,
    split_plot_error_terms,
    split_plot_runs,
    two_level_runs,
)


ENGINE_NAME = "doe"
ENGINE_VERSION = "0.1.0"
CONVERGENCE_THRESHOLD = 1e-12
# Grid resolution for the per-component feasible-range sweep in
# _build_doe_candidates; 8 gives >= 17 feasible candidates per component
# before de-duplication.
GRID_STEPS = 8
TOL = 1e-9
# Tiered-degradation guardrail for the exhaustive first p-subset scan in the
# D-optimal channel: C(n, p) grows factorially. Up to this many combinations the
# scan runs exhaustively (still the best seed quality); beyond it the engine
# degrades deterministically to a greedy max-volume seed (_greedy_max_volume_seed)
# instead of refusing, so large-q designs stay runnable. The downstream
# single-point-exchange and grow-to-n_sel loops are full-candidate scans either way.
MAX_COMBINATIONS = 500000

# WP-04a factorial channel. Two-level factors only; TAGUCHI_ROBUST is declared in the
# input contract but deliberately deferred (plan: "TAGUCHI_ROBUST 可后置"), so it is
# rejected with an explicit reason instead of being answered approximately.
FACTORIAL_DESIGN_TYPES = ("FULL_FACTORIAL", "FRACTIONAL_FACTORIAL", "SPLIT_PLOT")
DEFERRED_DESIGN_TYPES = ("TAGUCHI_ROBUST",)
MAX_FULL_FACTORIAL_FACTORS = 8
HALF_FRACTION_MIN_FACTORS, HALF_FRACTION_MAX_FACTORS = 3, 7

# WP-04b resource-constrained channel. BAYESIAN_SEQUENTIAL stops being a bare enum
# label and becomes a runnable (deterministic, non-probabilistic) greedy path: it
# picks the batch that maximises accumulated information per bench slot instead of
# returning a fixed matrix. The plan's downgrade clause ("只做资源可行性过滤 +
# 人工排序") is why there is no posterior sampling here.
SEQUENTIAL_DESIGN_TYPES = ("BAYESIAN_SEQUENTIAL",)
FACTOR_CHANNEL_DESIGN_TYPES = FACTORIAL_DESIGN_TYPES + SEQUENTIAL_DESIGN_TYPES
RESOURCE_ENVELOPE_FIELDS = ("bench_slots", "lot_capacity", "cycle_days", "cost_cap", "external_test_lead_time")
FACTOR_ROLES = ("WHOLE_PLOT", "SUB_PLOT")


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
    schema = schemas.get("doe_input.schema.json")
    if schema is None:
        return ["doe_input.schema.json not found"]
    v = Draft202012Validator(schema, registry=registry)
    errs = sorted(v.iter_errors(data), key=lambda e: list(e.path))
    return [e.message for e in errs]


def _digest_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _lu_det(matrix):
    """Determinant via LU with partial pivoting. Pure stdlib."""
    n = len(matrix)
    a = [row[:] for row in matrix]
    det_sign = 1.0
    det = 1.0
    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot_row][col]) < 1e-300:
            return 0.0
        if pivot_row != col:
            a[col], a[pivot_row] = a[pivot_row], a[col]
            det_sign = -det_sign
        det *= a[col][col]
        for r in range(col + 1, n):
            factor = a[r][col] / a[col][col]
            for c in range(col, n):
                a[r][c] -= factor * a[col][c]
    return det_sign * det


def _greedy_max_volume_seed(rows, p):
    """Deterministic greedy max-volume seed for the D-optimal channel.

    Replaces the exhaustive first-p-subset scan when C(n, p) exceeds
    MAX_COMBINATIONS: instead of refusing, the engine starts the downstream
    single-point exchange from this seed. Selection maximises the spanned volume
    step by step via incremental orthogonalization (modified Gram-Schmidt): at
    each step the candidate with the largest orthogonal-residual norm against the
    orthonormal basis of the already-selected rows is added. The residual norm is
    exactly the factor by which the spanned volume would grow, which is why this
    stands in for det(X'X) here: before p rows are selected the information
    matrix is singular (det identically 0) and at this scale determinants
    underflow, while residual norms stay numerically well-behaved.

    Determinism: sums use math.fsum (project style, cf. _xtx_info_matrix), ties
    resolve strictly to the lowest candidate index (strict > comparison), no
    randomness anywhere. rows is n x p (row length may differ from n); the loop
    below walks each row by its own length. Stops early once the best residual
    norm is <= 0.0 (rank exhausted) so a rank-deficient pool can never spin.

    Returns the set of selected row indices.
    """
    n = len(rows)
    dim = len(rows[0])
    selected = []
    basis = []  # orthonormal vectors spanning the selected rows
    while len(selected) < p:
        best_idx, best_norm = None, 0.0
        for idx in range(n):
            if idx in selected:
                continue
            residual = list(rows[idx])
            for b in basis:
                proj = math.fsum(residual[k] * b[k] for k in range(dim))
                for k in range(dim):
                    residual[k] -= proj * b[k]
            norm = math.sqrt(math.fsum(v * v for v in residual))
            if norm > best_norm:
                best_idx, best_norm = idx, norm
        if best_idx is None or best_norm <= 0.0:
            break
        # orthogonalize the winner against the basis and append it normalized
        residual = list(rows[best_idx])
        for b in basis:
            proj = math.fsum(residual[k] * b[k] for k in range(dim))
            for k in range(dim):
                residual[k] -= proj * b[k]
        norm = math.sqrt(math.fsum(v * v for v in residual))
        basis.append([v / norm for v in residual])
        selected.append(best_idx)
    return set(selected)


def _model_matrix(candidates, model_order):
    q = len(candidates[0])
    pairs = list(itertools.combinations(range(q), 2))
    rows = []
    for cand in candidates:
        row = [float(v) for v in cand]
        if model_order == "QUADRATIC":
            row.extend(float(cand[i]) * float(cand[j]) for i, j in pairs)
        rows.append(row)
    return rows


def _xtx_info_matrix(sel_rows, p):
    xtx = [[0.0] * p for _ in range(p)]
    for rk in sel_rows:
        for i in range(p):
            ri = rk[i]
            if ri == 0.0:
                continue
            xtx[i][i] += ri * ri
            for j in range(i + 1, p):
                xtx[i][j] += ri * rk[j]
                xtx[j][i] += ri * rk[j]
    return xtx


def _feasible(fracs, lowers, uppers, total, tol=1e-9):
    for i, v in enumerate(fracs):
        if v < lowers[i] - tol or v > uppers[i] + tol:
            return False
    return abs(math.fsum(fracs) - total) <= tol


def _simplex_lattice(m, q, lowers, uppers, total):
    points = []
    structural = 0
    for counts in itertools.combinations_with_replacement(range(m + 1), q):
        if sum(counts) != m:
            continue
        perms = set(itertools.permutations(counts))
        structural += len(perms)
        for perm in perms:
            fracs = tuple(float(v) / m for v in perm)
            if _feasible(fracs, lowers, uppers, total):
                points.append(fracs)
    points.sort(key=lambda t: t)
    return points, structural


def _feasible_range(i, lowers, uppers, total):
    """Range of x_i that can be hit while the others absorb the remainder."""
    others_lo = math.fsum(lowers[j] for j in range(len(lowers)) if j != i)
    others_hi = math.fsum(uppers[j] for j in range(len(uppers)) if j != i)
    return max(lowers[i], total - others_hi), min(uppers[i], total - others_lo)


def _allocate(remaining, idxs, lowers, uppers):
    """Split `remaining` over `idxs` proportionally to slack, inside bounds.

    Water-filling over the AVAILABLE amount: the active components' lower bounds
    are consumed first, then the remainder is split in proportion to headroom. A
    component that overshoots is pinned at its bound and the residual is re-split
    among the rest. Iteration order is fixed, so the result is deterministic.

    This replaces equal splitting, which cannot allocate a small remainder across
    components whose caps are much smaller than remainder / (q - 1).
    """
    n = len(idxs)
    if n == 0:
        return [] if abs(remaining) <= TOL else None
    lo = [lowers[j] for j in idxs]
    hi = [uppers[j] for j in idxs]
    base = math.fsum(lo)
    cap = math.fsum(hi)
    if remaining < base - TOL or remaining > cap + TOL:
        return None

    x = [0.0] * n
    rem = float(remaining)
    active = list(range(n))
    while active:
        act_lo = math.fsum(lo[k] for k in active)
        head = math.fsum(hi[k] - lo[k] for k in active)
        avail = rem - act_lo
        if avail < -TOL or avail > head + TOL:
            return None
        if head <= TOL:
            trial = {k: lo[k] + avail / len(active) for k in active}
        else:
            trial = {k: lo[k] + avail * (hi[k] - lo[k]) / head for k in active}
        bad = [k for k, v in trial.items() if v > hi[k] + TOL or v < lo[k] - TOL]
        if not bad:
            for k, v in trial.items():
                x[k] = v
            break
        k = max(bad, key=lambda k: max(trial[k] - hi[k], lo[k] - trial[k]))
        x[k] = min(max(trial[k], lo[k]), hi[k])
        rem -= x[k]
        active.remove(k)
    if abs(math.fsum(x) - remaining) > 1e-9:
        return None
    return x


def _snap_proportions(pt, total):
    """Nudge components so math.fsum(pt) == total exactly.

    Grid-sweep candidates are rounded to 12 decimals, which can leave their fsum
    off the mixture total by ~1e-12, while the envelope (and the tests) promise
    mass fractions that sum to exactly 1.0. Iteratively re-deriving the largest
    component from the fsum of the others converges within a few passes: after
    the first correction the residual is ulp-scale. Returns None when it cannot
    converge, so the caller can fall back to the unsnapped point.
    """
    out = list(pt)
    for _ in range(8):
        if math.fsum(out) == total:
            return out
        k = max(range(len(out)), key=lambda i: abs(out[i]))
        others = [out[i] for i in range(len(out)) if i != k]
        out[k] = total - math.fsum(others)
    return out if math.fsum(out) == total else None


def _build_doe_candidates(params_or_total, *args):
    # Accept both dict-style and float-style total for test compatibility
    total = params_or_total["mixture_total"] if isinstance(params_or_total, dict) else params_or_total
    # Extract positional args: either (lowers, uppers, q) or (sorted_ids, lowers, uppers, q)
    if len(args) == 3:
        lowers, uppers, q = args
    else:
        _, lowers, uppers, q = args
    """Union of m=1/m=2 lattice points plus structural probes, feasible-filtered."""
    seen = set()
    candidates = []
    for m in (1, 2):
        pts, _ = _simplex_lattice(m, q, lowers, uppers, total)
        for pt in pts:
            key = tuple(round(v, 12) for v in pt)
            if key not in seen:
                seen.add(key)
                candidates.append(pt)
    tol = 1e-9
    extras = []
    for i in range(q):
        for bound_val in (lowers[i], uppers[i]):
            remaining = total - bound_val
            if q < 2:
                continue
            other_low_sum = math.fsum(lowers[j] for j in range(q) if j != i)
            other_up_sum = math.fsum(uppers[j] for j in range(q) if j != i)
            if remaining < other_low_sum - tol or remaining > other_up_sum + tol:
                continue
            # allocate the remainder by slack (water-filling) instead of equally,
            # and write the allocation into pt before the boundary check — the
            # previous code computed `share` but never stored it, so every bound
            # probe silently failed the sum check and was dropped.
            others = [j for j in range(q) if j != i]
            alloc = _allocate(remaining, others, lowers, uppers)
            if alloc is None:
                continue
            pt = [0.0] * q
            pt[i] = bound_val
            for j, v in zip(others, alloc):
                pt[j] = v
            if all(lowers[j] - tol <= pt[j] <= uppers[j] + tol for j in others):
                pt_tuple = tuple(round(v, 12) for v in pt)
                if abs(math.fsum(pt_tuple) - total) <= tol:
                    extras.append(pt_tuple)
    center_raw = [(lowers[i] + uppers[i]) / 2.0 for i in range(q)]
    csum = math.fsum(center_raw)
    if csum > 0:
        scale = total / csum
        cpt = tuple(round(min(max(center_raw[k] * scale, lowers[k]), uppers[k]), 12) for k in range(q))
        if abs(math.fsum(cpt) - total) <= tol:
            extras.append(cpt)
    # Per-component grid sweep. This is what makes a dominant-component mixture
    # estimable: sweeping the dominant component over its feasible range and
    # allocating the remainder by slack keeps every point feasible, where equal
    # splitting overflowed the minor components' caps and got the probe dropped.
    for i in range(q):
        lo_i, hi_i = _feasible_range(i, lowers, uppers, total)
        others = [j for j in range(q) if j != i]
        for step in range(GRID_STEPS + 1):
            frac = lo_i + (hi_i - lo_i) * step / GRID_STEPS
            alloc = _allocate(total - frac, others, lowers, uppers)
            if alloc is None:
                continue
            pt = [0.0] * q
            pt[i] = frac
            for j, v in zip(others, alloc):
                pt[j] = v
            key = tuple(round(v, 12) for v in pt)
            if key not in seen and _feasible(list(key), lowers, uppers, total):
                seen.add(key)
                candidates.append(key)

    # Axis midpoints, remainder allocated by slack rather than equally.
    for i in range(q):
        lo_i, hi_i = _feasible_range(i, lowers, uppers, total)
        others = [j for j in range(q) if j != i]
        alloc = _allocate(total - (lo_i + hi_i) / 2, others, lowers, uppers)
        if alloc is None:
            continue
        pt = [0.0] * q
        pt[i] = (lo_i + hi_i) / 2
        for j, v in zip(others, alloc):
            pt[j] = v
        key = tuple(round(v, 12) for v in pt)
        if key not in seen and _feasible(list(key), lowers, uppers, total):
            seen.add(key)
            candidates.append(key)

    for e in extras:
        if e not in seen:
            seen.add(e)
            candidates.append(e)
    # Exact-mass snap: the 12-decimal rounding in the sweeps above can leave a
    # candidate's fsum off the total by ~1e-12. The envelope promises proportions
    # summing to exactly 1.0, so every candidate is snapped before it is handed
    # to the model matrix and the runs. A candidate that cannot be snapped (or
    # would duplicate another after snapping) keeps its pre-snap form / is kept
    # only once, exactly as the dedup semantics above.
    snapped = []
    snapped_keys = set()
    for pt in candidates:
        spt = _snap_proportions(pt, total)
        if spt is None:
            spt = list(pt)
        key = tuple(round(v, 12) for v in spt)
        if key in snapped_keys:
            continue
        snapped_keys.add(key)
        snapped.append(tuple(spt))
    snapped.sort(key=lambda t: t)
    return snapped


def _validate_business(input_dict):
    reasons = []
    comps = input_dict["components"]
    ids = [c["component_id"] for c in comps]
    if len(ids) != len(set(ids)):
        reasons.append("duplicate component_id")
    for c in comps:
        if c["lower_bound"] > c["upper_bound"]:
            reasons.append(f"bounds inverted for {c['component_id']}: lower > upper")
    total = input_dict["mixture_total"]
    lowers_all = [c["lower_bound"] for c in comps]
    uppers_all = [c["upper_bound"] for c in comps]
    sum_low = math.fsum(lowers_all)
    sum_up = math.fsum(uppers_all)
    tol = 1e-9
    if sum_low > total + tol:
        reasons.append(f"infeasible bounds: sum of lower bounds {sum_low} exceeds mixture_total {total}")
    if sum_up < total - tol:
        reasons.append(f"infeasible bounds: sum of upper bounds {sum_up} below mixture_total {total}")
    for i, c in enumerate(comps):
        other_low_sum = sum_low - lowers_all[i]
        other_up_sum = sum_up - uppers_all[i]
        max_i = total - other_low_sum
        min_i = total - other_up_sum
        if uppers_all[i] < min_i - tol or lowers_all[i] > max_i + tol:
            reasons.append(f"component {c['component_id']} individually infeasible for mixture_total")
    if input_dict["design_type"] == "SIMPLEX_MIXTURE" and input_dict["target_runs"] != 0:
        reasons.append("target_runs must be 0 for SIMPLEX_MIXTURE: run count is lattice-determined")
    return reasons, lowers_all, uppers_all


def generate_doe(input_dict, input_bytes=None):
    """Generate a DOE result envelope from input dict + original raw bytes."""
    schema_errors = _validate_input_schema(input_dict)
    if schema_errors:
        return _build_rejected(input_dict, input_bytes,
            [f"input schema validation failed: {schema_errors[0]}"])
    if isinstance(input_dict, dict) and input_dict.get("input_type") == "MIXTURE_DOE_DESIGN":
        return _generate_mixture(input_dict, input_bytes)
    return _generate_factors(input_dict, input_bytes)


def _generate_mixture(input_dict, input_bytes):
    """Phase 4.2 constrained mixture channel (bounded probes, slack allocation,
    target_runs honoured, exhaustive scan guarded)."""
    reasons, _, _ = _validate_business(input_dict)
    if reasons:
        return _build_rejected(input_dict, input_bytes, reasons)

    comps = input_dict["components"]
    q = len(comps)
    sorted_ids = sorted(c["component_id"] for c in comps)
    id_to_bounds = {c["component_id"]: (c["lower_bound"], c["upper_bound"]) for c in comps}
    lowers_s = [id_to_bounds[cid][0] for cid in sorted_ids]
    uppers_s = [id_to_bounds[cid][1] for cid in sorted_ids]
    total = input_dict["mixture_total"]
    design_type = input_dict["design_type"]
    model_order = input_dict["model_order"]

    if design_type == "SIMPLEX_MIXTURE":
        m = 1 if model_order == "LINEAR" else 2
        points, structural_count = _simplex_lattice(m, q, lowers_s, uppers_s, total)
        if not points:
            return _build_rejected(input_dict, input_bytes,
                ["infeasible after lattice filtering: no feasible points remain"])
        method = "SIMPLEX_LATTICE_V1"
        selection_reason = f"simplex lattice m={m} q={q} bounded filtering retained {len(points)} of {structural_count} structural points"
    else:
        candidates = _build_doe_candidates(total, lowers_s, uppers_s, q)
        p = q + q * (q - 1) // 2
        target = input_dict["target_runs"]
        n_sel = max(target, p)
        if len(candidates) < p:
            return _build_rejected(input_dict, input_bytes,
                ["model not estimable with feasible candidates: fewer feasible points than model parameters"])
        sel_rows_full = _model_matrix(candidates, "QUADRATIC")
        if n_sel >= len(candidates):
            selected_idx = list(range(len(candidates)))
        else:
            # Tiered degradation instead of refusal: the exhaustive first p-subset
            # scan is factorial in the candidate count. Up to MAX_COMBINATIONS it
            # runs exhaustively (best seed quality); beyond it the scan would
            # effectively hang, so the seed comes from _greedy_max_volume_seed
            # instead. The exchange and grow loops below are full-candidate scans
            # and run identically in both tiers.
            n_combos = math.comb(len(candidates), p)
            if n_combos <= MAX_COMBINATIONS:
                # greedy start: exhaustive first p-subset scan in lex order
                best_det = -1.0
                best_combo = None
                for combo in itertools.combinations(range(len(candidates)), p):
                    rows = [sel_rows_full[k] for k in combo]
                    d = _lu_det(_xtx_info_matrix(rows, p))
                    if d > best_det:
                        best_det = d
                        best_combo = combo
                selected = set(best_combo)
            else:
                selected = _greedy_max_volume_seed(sel_rows_full, p)
            # greedy single-point exchange until no improvement beyond threshold
            while True:
                cur_rows = [sel_rows_full[k] for k in sorted(selected)]
                cur_det = _lu_det(_xtx_info_matrix(cur_rows, p))
                improved = False
                for out_i in sorted(selected):
                    for cand_i in range(len(candidates)):
                        if cand_i in selected or cand_i == out_i:
                            continue
                        trial = (selected - {out_i}) | {cand_i}
                        trial_rows = [sel_rows_full[k] for k in sorted(trial)]
                        trial_det = _lu_det(_xtx_info_matrix(trial_rows, p))
                        if trial_det > cur_det * (1.0 + CONVERGENCE_THRESHOLD):
                            selected = trial
                            improved = True
                            break
                    if improved:
                        break
                if not improved:
                    break
            # Grow from p to n_sel. Before this, target_runs was only honoured by
            # the n_sel >= len(candidates) shortcut, so a request for 12 points
            # silently returned p points. Each addition maximises the det(X'X)
            # gain; ties resolve to the lowest candidate index (strict >), which
            # keeps the growth deterministic.
            while len(selected) < n_sel:
                cur_det = _lu_det(_xtx_info_matrix([sel_rows_full[k] for k in sorted(selected)], p))
                best_add, best_gain = None, cur_det
                for cand_i in range(len(candidates)):
                    if cand_i in selected:
                        continue
                    trial = selected | {cand_i}
                    d = _lu_det(_xtx_info_matrix([sel_rows_full[k] for k in sorted(trial)], p))
                    if d > best_gain:
                        best_add, best_gain = cand_i, d
                if best_add is None:
                    break
                selected.add(best_add)
            selected_idx = sorted(selected)
        points = [candidates[k] for k in selected_idx]
        method = "D_OPTIMAL_GREEDY_DET_V1"
        selection_reason = f"D-optimal greedy determinant maximization over candidates={len(candidates)} target={target} quadratic Scheffe model"

    runs = []
    denom = 2.0 if (design_type == "SIMPLEX_MIXTURE" and model_order == "QUADRATIC") else 1.0
    # points already store exact fractions; no further scaling needed
    for idx, pt in enumerate(points, start=1):
        props = {}
        for sid, frac in zip(sorted_ids, pt):
            props[sid] = float(frac) / 1.0
        runs.append({"run_index": idx, "proportions": props})

    card = input_dict["experiment_card"]
    if input_bytes is not None:
        digest = _digest_bytes(input_bytes)
    else:
        digest = _digest_bytes(json.dumps(input_dict, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    envelope = {
        "schema_version": "0.1.0",
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "method": method,
        "parameters": {
            "design_type": design_type,
            "model_order": model_order,
            "target_runs": input_dict["target_runs"],
            "convergence_threshold": CONVERGENCE_THRESHOLD
        },
        "input_digest": digest,
        "status": "OK",
        "rejection_reasons": [],
        "decision_question": card["decision_question"],
        "hypothesis": card["hypothesis"],
        "decision_rule": card["decision_rule"],
        "expected_information_value": card["expected_information_value"],
        "variables_note": card["variables_note"],
        "constraints_note": card["constraints_note"],
        "responses_note": card["responses_note"],
        "doe_selection_reason": card["doe_selection_reason"],
        "result": {
            "design_type": design_type,
            "model_order": model_order,
            "runs": runs,
            "run_count": len(runs),
            "candidates_considered": len(points) if design_type == "SIMPLEX_MIXTURE" else len(candidates),
            "selection_reason": selection_reason
        },
        "evidence": [{
            "evidence_id": "doe-generation",
            "statement": f"deterministic point generation: {method}, {len(runs)} runs, proportions are normalized mass fractions summing to exactly 1.0",
            "source": "engine internal deterministic algorithm",
            "status": "OBSERVED"
        }]
    }
    return envelope


def _factor_levels(factor):
    """(low, high) of a varying factor, or None when the factor is held at hold_at."""
    if "hold_at" in factor:
        return None
    if "levels" in factor:
        return float(factor["levels"][0]), float(factor["levels"][1])
    return float(factor["range"]["lower"]), float(factor["range"]["upper"])


def _factor_role(factor, default_role):
    """Resolve a factor's split-plot role from the data, never from a hardcoded list.

    An explicit per-factor `role` wins; otherwise the process-level
    `process_factor_role` (mirroring process.factor_role) applies. Returns None when
    neither is supplied, so the caller can reject while naming the factor.
    """
    role = factor.get("role", default_role)
    return role if role in FACTOR_ROLES else None


def _factor_reasons(input_dict):
    """Fail-closed checks for the factor channel; also returns the varying factors by role."""
    design_type = input_dict["design_type"]
    factors = input_dict["factors"]
    default_role = input_dict.get("process_factor_role")
    reasons = []
    ids = [factor["factor_id"] for factor in factors]
    if len(ids) != len(set(ids)):
        reasons.append("duplicate factor_id")
    varying, whole, sub = [], [], []
    for factor in factors:
        levels = _factor_levels(factor)
        if levels is None:
            continue
        varying.append(factor)
        role = _factor_role(factor, default_role)
        if role is None:
            reasons.append(
                f"factor {factor['factor_id']} has no split-plot role: declare factors[].role "
                "or the process-level process_factor_role (mirror of process.factor_role)")
        elif role == "WHOLE_PLOT":
            whole.append(factor)
        else:
            sub.append(factor)
        if not levels[0] < levels[1]:
            reasons.append(f"factor {factor['factor_id']} levels must be strictly increasing ({levels[0]} >= {levels[1]})")
    if not varying:
        reasons.append("at least one factor must vary (levels or range); a design with only held factors has nothing to estimate")
    if design_type in DEFERRED_DESIGN_TYPES:
        reasons.append(f"design_type {design_type} is deferred beyond WP-04a and is not implemented")
    elif design_type not in FACTOR_CHANNEL_DESIGN_TYPES:
        reasons.append(f"design_type {design_type} is not a supported factorial design type")
    elif design_type == "SPLIT_PLOT":
        if not whole:
            reasons.append("SPLIT_PLOT requires at least one varying WHOLE_PLOT factor")
        if not sub:
            reasons.append("SPLIT_PLOT requires at least one varying SUB_PLOT factor")
    elif len(varying) < 2:
        reasons.append(f"{design_type} requires at least two varying factors")
    if design_type == "FULL_FACTORIAL" and len(varying) > MAX_FULL_FACTORIAL_FACTORS:
        reasons.append(f"FULL_FACTORIAL supports at most {MAX_FULL_FACTORIAL_FACTORS} varying factors")
    if design_type == "FRACTIONAL_FACTORIAL" and not HALF_FRACTION_MIN_FACTORS <= len(varying) <= HALF_FRACTION_MAX_FACTORS:
        reasons.append(
            f"FRACTIONAL_FACTORIAL implements the 2^(k-1) half fraction for "
            f"{HALF_FRACTION_MIN_FACTORS}..{HALF_FRACTION_MAX_FACTORS} varying factors")
    if input_dict["target_runs"] != 0:
        reasons.append(f"target_runs must be 0 for {design_type}: the run count is structure-determined")
    return reasons, whole, sub


def _resource_reasons(input_dict):
    """Fail-closed checks for the resource envelope (WP-04b)."""
    envelope = input_dict.get("resource_envelope")
    if envelope is None:
        return []
    reasons = []
    if set(envelope) != set(RESOURCE_ENVELOPE_FIELDS):
        reasons.append(f"resource_envelope must declare exactly {list(RESOURCE_ENVELOPE_FIELDS)}")
        return reasons
    for field in RESOURCE_ENVELOPE_FIELDS:
        value = envelope[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            reasons.append(f"resource_envelope.{field} must be a number")
    if reasons:
        return reasons
    if envelope["bench_slots"] < 1:
        reasons.append(f"resource_envelope.bench_slots must be >= 1, got {envelope['bench_slots']}")
    if envelope["lot_capacity"] < 1:
        reasons.append(f"resource_envelope.lot_capacity must be >= 1, got {envelope['lot_capacity']}")
    if envelope["cycle_days"] <= 0:
        reasons.append(f"resource_envelope.cycle_days must be > 0, got {envelope['cycle_days']}")
    if envelope["cost_cap"] < 0:
        reasons.append(f"resource_envelope.cost_cap must be >= 0, got {envelope['cost_cap']}")
    if envelope["external_test_lead_time"] < 0:
        reasons.append(
            f"resource_envelope.external_test_lead_time must be >= 0, got {envelope['external_test_lead_time']}")
    return reasons


def _effect_hypotheses(columns, runs, model_order):
    """Deterministic hypothesis list derived from the estimable effect columns.

    Hypothesis ids H1..Hk are assigned in the engine's canonical column order, so an
    id is stable for a given design regardless of the resource envelope. `gain` is the
    information a fully-observed contrast carries: aliased columns are discounted by
    their alias group size, and interaction columns that a LINEAR model pools into
    error are discounted further.
    """
    high_level = {}
    for column in columns:
        for factor_id in column["factors"]:
            if factor_id in high_level:
                continue
            # the high level is the largest value this factor actually takes in the runs
            values = sorted({run["settings"][factor_id] for run in runs if factor_id in run["settings"]})
            high_level[factor_id] = values[-1] if values else None
    hypotheses = []
    for index, column in enumerate(columns, start=1):
        aliases = column.get("aliases", [])
        gain = 1.0 / (1.0 + len(aliases))
        pooled = model_order == "LINEAR" and column["kind"] == "INTERACTION"
        if pooled:
            gain *= 0.5
        run_index = None
        for run in runs:
            if all(run["settings"].get(factor_id) == high_level[factor_id] for factor_id in column["factors"]):
                run_index = run["run_index"]
                break
        hypotheses.append({
            "hypothesis_reference": f"H{index}",
            "hypothesis_statement": f"effect {column['column_id']} is non-zero",
            "effect_reference": column["column_id"],
            "kind": column["kind"],
            "order": len(column["factors"]),
            "aliases": list(aliases),
            "pooled": pooled,
            "gain": gain,
            "run_index": run_index,
            # the corner that would resolve the effect when no run in the batch sits there
            "high_settings": {factor_id: high_level[factor_id] for factor_id in column["factors"]},
        })
    return hypotheses


def _recommended_runs(hypotheses, runs, envelope):
    """Rank hypotheses by information gain per bench slot and take what the next round allows."""
    by_index = {run["run_index"]: run for run in runs}
    ranked = sorted(hypotheses, key=lambda item: (-item["gain"], item["order"], item["effect_reference"]))
    limit = min(int(envelope["bench_slots"]), len(ranked))
    recommended = []
    for rank, hypothesis in enumerate(ranked[:limit], start=1):
        run_index = hypothesis["run_index"]
        run = by_index.get(run_index)
        if run is None:
            # no run in the batch isolates this effect: the recommendation is one extra run
            # at the all-high corner of the effect, which is the cheapest single run that
            # moves every factor of the effect away from its low level.
            run = {"settings": hypothesis["high_settings"]}
        reason = (
            f"tests {hypothesis['kind'].lower()} {hypothesis['effect_reference']} "
            f"({hypothesis['order']} factor(s), 1 contrast df)")
        if hypothesis["aliases"]:
            reason += f"; aliased with {', '.join(hypothesis['aliases'])}, so its estimate is confounded"
        if hypothesis["pooled"]:
            reason += "; a LINEAR model pools this interaction into error, so it is scheduled last"
        if run_index is None:
            reason += (
                "; no run in the current batch sets every factor of this effect to its high level, "
                "so this recommendation is one extra run at that corner")
        reason += "; one bench slot buys this contrast at the highest gain per slot still available"
        entry = {
            "rank": rank,
            "hypothesis_reference": hypothesis["hypothesis_reference"],
            "hypothesis_statement": hypothesis["hypothesis_statement"],
            "effect_reference": hypothesis["effect_reference"],
            "run_index": run_index,
            "settings": run["settings"],
            "slots_used": 1,
            "information_gain_per_slot": hypothesis["gain"],
            "discriminative_power_reason": reason,
        }
        if "whole_plot_index" in run:
            # split-plot scheduling hook: the caller executes the batch grouped by
            # whole plot, so a costly whole-plot change is paid once, not per run.
            entry["whole_plot_index"] = run["whole_plot_index"]
            entry["discriminative_power_reason"] += (
                f"; execute inside whole plot {run['whole_plot_index']} so the whole-plot level is set once")
        recommended.append(entry)
    return recommended


def _apply_resource_plan(result, input_dict, model_order):
    """Attach the WP-04b resource annotations to a factor-channel result.

    Runs nothing when the input declares no resource_envelope, which is what keeps
    every pre-WP-04b envelope (the mixture gold fixture included) byte-identical.
    """
    envelope = input_dict.get("resource_envelope")
    if envelope is None:
        return result
    runs = result["runs"]
    hypotheses = _effect_hypotheses(result["columns"], runs, model_order)
    recommended = _recommended_runs(hypotheses, runs, envelope)
    slots = sum(item["slots_used"] for item in recommended)
    result["resource_feasible"] = bool(runs) and len(runs) <= int(envelope["lot_capacity"]) and int(envelope["bench_slots"]) >= 1
    total_gain = math.fsum(item["information_gain_per_slot"] for item in recommended)
    result["information_gain_per_slot"] = total_gain / slots if slots else 0.0
    result["recommended_next_runs"] = recommended
    return result


def _frozen_formula_reasons(input_dict):
    """MIXTURE_PROCESS keeps the formula fixed, so every component must be a single point."""
    reasons = []
    components = input_dict["components"]
    ids = [component["component_id"] for component in components]
    if len(ids) != len(set(ids)):
        reasons.append("duplicate component_id")
    frozen = []
    for component in components:
        if component["lower_bound"] != component["upper_bound"]:
            reasons.append(
                f"MIXTURE_PROCESS_DOE_DESIGN freezes the formulation: component {component['component_id']} "
                "must have lower_bound == upper_bound; vary only factors[]")
        frozen.append(component["lower_bound"])
    total = input_dict["mixture_total"]
    if abs(math.fsum(frozen) - total) > 1e-9:
        reasons.append(f"frozen component proportions must sum to mixture_total {total}")
    return reasons


def _sequential_batch(factor_ids, candidates, limit):
    """Greedy D-optimal sequential batch: add the candidate that maximises det(X'X).

    Deterministic and free of posterior sampling: this is the plan's downgrade-level
    stand-in for a Bayesian sequential design ("只做资源可行性过滤 + 人工排序" was the
    floor; a greedy information criterion stays well above it while remaining pure
    stdlib and reproducible to the byte). Ties resolve to the lowest candidate index.
    """
    ordered = [tuple(run[factor_id] for factor_id in factor_ids) for run in candidates]
    selected = []
    while len(selected) < limit and len(selected) < len(ordered):
        best_index, best_det = None, -1.0
        for index in range(len(ordered)):
            if index in selected:
                continue
            rows = [ordered[k] for k in (*selected, index)]
            determinant = _lu_det(_xtx_info_matrix(rows, len(factor_ids)))
            if determinant > best_det:
                best_index, best_det = index, determinant
        if best_index is None:
            break
        selected.append(best_index)
    return [candidates[index] for index in sorted(selected)]


def _generate_factors(input_dict, input_bytes):
    """Two-level factorial / split-plot channel added by WP-04a."""
    input_type = input_dict["input_type"]
    design_type = input_dict["design_type"]
    model_order = input_dict["model_order"]
    reasons = _frozen_formula_reasons(input_dict) if input_type == "MIXTURE_PROCESS_DOE_DESIGN" else []
    factor_reasons, whole, sub = _factor_reasons(input_dict)
    reasons += factor_reasons
    reasons += _resource_reasons(input_dict)
    if design_type in SEQUENTIAL_DESIGN_TYPES and input_dict.get("resource_envelope") is None:
        reasons.append("BAYESIAN_SEQUENTIAL requires resource_envelope: the next batch must be bounded by bench_slots")
    if reasons:
        return _build_rejected(input_dict, input_bytes, reasons)

    varying_ids = tuple(sorted(factor["factor_id"] for factor in (*whole, *sub)))
    whole_ids = tuple(sorted(factor["factor_id"] for factor in whole))
    sub_ids = tuple(sorted(factor["factor_id"] for factor in sub))
    levels = {factor["factor_id"]: _factor_levels(factor) for factor in (*whole, *sub)}
    held = {factor["factor_id"]: float(factor["hold_at"]) for factor in input_dict["factors"] if "hold_at" in factor}
    replicates = int(input_dict.get("whole_plot_replicates", 1))

    whole_plot_indices = None
    if design_type == "SPLIT_PLOT":
        pairs = split_plot_runs(whole_ids, sub_ids, replicates)
        coded = [settings for _, settings in pairs]
        whole_plot_indices = [index for index, _ in pairs]
        method = "SPLIT_PLOT_2LEVEL_V1"
        structure = (f"split-plot 2^{len(whole_ids)} whole-plot x 2^{len(sub_ids)} sub-plot design "
                     f"with {replicates} whole-plot replicate(s)")
    elif design_type in SEQUENTIAL_DESIGN_TYPES:
        pool = two_level_runs(varying_ids)
        batch = _sequential_batch(varying_ids, pool, int(input_dict["resource_envelope"]["bench_slots"]))
        coded = batch
        replicates = 1
        method = "BAYESIAN_SEQUENTIAL_GREEDY_V1"
        structure = (f"sequential greedy batch of {len(batch)} run(s) drawn from the 2^{len(varying_ids)} candidate "
                     "lattice to maximise accumulated det(X'X) per bench slot (deterministic; no posterior sampling)")
    elif design_type == "FRACTIONAL_FACTORIAL":
        base = half_fraction_runs(varying_ids)
        coded = [run for _ in range(replicates) for run in base]
        method = "HALF_FRACTION_FACTORIAL_V1"
        structure = (f"2^{len(varying_ids) - 1} half fraction of the 2^{len(varying_ids)} two-level design "
                     "(generator: the last sorted factor equals the product of the others)")
    else:
        base = two_level_runs(varying_ids)
        coded = [run for _ in range(replicates) for run in base]
        method = "FULL_FACTORIAL_2LEVEL_V1"
        structure = f"full factorial 2^{len(varying_ids)} two-level design"
    if input_type == "MIXTURE_PROCESS_DOE_DESIGN":
        method = f"MIXTURE_PROCESS_{method}"

    frozen_proportions = None
    if input_type == "MIXTURE_PROCESS_DOE_DESIGN":
        frozen_proportions = {component["component_id"]: float(component["lower_bound"])
                              for component in sorted(input_dict["components"], key=lambda item: item["component_id"])}

    runs = []
    for index, code in enumerate(coded, start=1):
        settings = {factor_id: (levels[factor_id][1] if code[factor_id] > 0 else levels[factor_id][0]) for factor_id in varying_ids}
        settings.update(held)
        run = {"run_index": index, "settings": {key: settings[key] for key in sorted(settings)}}
        if whole_plot_indices is not None:
            run["whole_plot_index"] = whole_plot_indices[index - 1]
        if frozen_proportions is not None:
            run["fixed_proportions"] = frozen_proportions
        runs.append(run)

    columns = effect_columns(varying_ids, coded)
    run_count = len(runs)
    total_df = run_count - 1
    replicate_df = replicates - 1
    model_df = sum(1 for column in columns if column["kind"] == "MAIN_EFFECT") if model_order == "LINEAR" else len(columns)
    if design_type in SEQUENTIAL_DESIGN_TYPES:
        # A sequential batch is a partial step, not a completed model estimate: it
        # can never be "not estimable", the remaining df is simply what is still open.
        model_df = min(model_df, max(total_df - replicate_df, 0))
    remaining = total_df - replicate_df - model_df
    if remaining < 0:
        return _build_rejected(input_dict, input_bytes,
            [f"{model_order} model is not estimable: it needs {model_df} degrees of freedom "
             f"but only {total_df - replicate_df} are available"])
    if design_type == "SPLIT_PLOT":
        error_terms = split_plot_error_terms(2 ** len(whole_ids), 2 ** len(sub_ids), replicates, remaining)
    else:
        error_terms = plot_error_term(remaining)
    interaction_columns = [column for column in columns if column["kind"] == "INTERACTION"]
    if model_order == "LINEAR" and interaction_columns:
        pooled = (f"LINEAR model: {len(interaction_columns)} interaction column(s) are not estimated "
                  "and are pooled into this error term")
        last = error_terms[-1]
        last["pooling"] = f"{last['pooling']} {pooled}" if "pooling" in last else pooled
    degrees = {
        "total": total_df,
        "replicate": replicate_df,
        "model": model_df,
        "error": sum(term["degrees_of_freedom"] for term in error_terms),
    }
    aliased = [f"{column['column_id']}={'/'.join(column['aliases'])}" for column in columns if "aliases" in column]
    selection_reason = (f"{structure}, {run_count} structure-determined runs, {model_order} model, "
                        f"df(total={total_df}, replicate={replicate_df}, model={model_df}, error={degrees['error']}); "
                        "the run count is determined by the design structure, not by target_runs")
    if aliased:
        selection_reason += f"; aliased effects are reported per column ({', '.join(aliased)})"

    card = input_dict["experiment_card"]
    if input_bytes is not None:
        digest = _digest_bytes(input_bytes)
    else:
        digest = _digest_bytes(json.dumps(input_dict, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    parameters = {
        "design_type": design_type,
        "model_order": model_order,
        "target_runs": input_dict["target_runs"],
        "whole_plot_replicates": replicates,
        "factor_count": len(varying_ids),
        "whole_plot_factor_count": len(whole_ids),
        "sub_plot_factor_count": len(sub_ids),
        "run_count": run_count,
        "design_space_reference": input_dict.get("design_space_reference"),
    }
    envelope_resource = input_dict.get("resource_envelope")
    if envelope_resource is not None:
        parameters["resource_envelope"] = envelope_resource
    result = {
        "design_type": design_type,
        "model_order": model_order,
        "runs": runs,
        "run_count": run_count,
        "columns": columns,
        "error_terms": error_terms,
        "degrees_of_freedom": degrees,
        "selection_reason": selection_reason,
    }
    result = _apply_resource_plan(result, input_dict, model_order)
    evidence = [{
        "evidence_id": "doe-generation",
        "statement": f"deterministic factorial point generation: {method}, {run_count} structure-determined runs, coded levels -1/+1 mapped onto each factor's two levels; {len(columns)} effect column(s) and {len(error_terms)} error term(s) are reported without estimating any measurement",
        "source": "engine internal deterministic algorithm",
        "status": "OBSERVED",
    }]
    if envelope_resource is not None:
        evidence.append({
            "evidence_id": "doe-resource-plan",
            "statement": (
                f"resource-constrained next round under bench_slots={envelope_resource['bench_slots']} and "
                f"lot_capacity={envelope_resource['lot_capacity']}: {len(result['recommended_next_runs'])} recommended "
                "run(s) ranked by information gain per bench slot; this is a deterministic planning ordering, not a "
                "measurement, statistical-sufficiency, cost or performance conclusion"),
            "source": "engine internal deterministic algorithm",
            "status": "OBSERVED",
        })
    return {
        "schema_version": "0.1.0",
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "method": method,
        "parameters": parameters,
        "input_digest": digest,
        "status": "OK",
        "rejection_reasons": [],
        "decision_question": card["decision_question"],
        "hypothesis": card["hypothesis"],
        "decision_rule": card["decision_rule"],
        "expected_information_value": card["expected_information_value"],
        "variables_note": card["variables_note"],
        "constraints_note": card["constraints_note"],
        "responses_note": card["responses_note"],
        "doe_selection_reason": card["doe_selection_reason"],
        "result": result,
        "evidence": evidence,
    }


def compute_doe(input_dict, input_bytes=None):
    return generate_doe(input_dict, input_bytes)


def _build_rejected(input_dict, input_bytes, reasons):
    if input_bytes is not None:
        digest = _digest_bytes(input_bytes)
    elif isinstance(input_dict, dict):
        digest = _digest_bytes(json.dumps(input_dict, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    else:
        digest = _digest_bytes(b"")
    return {
        "schema_version": "0.1.0",
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "method": "DOE_GENERATION_V1",
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
        print("Usage: python -m domains.lubricant.compute.doe.engine <input.json> <output.json>", file=sys.stderr)
        return 2
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2])
    try:
        raw = inp.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        env = _build_rejected({}, raw if "raw" in locals() else b"", [f"input read/parse failed: {e}"])
        _write_output(out, env)
        return 0
    env = generate_doe(data, raw)
    _write_output(out, env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
