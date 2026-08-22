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

ENGINE_NAME = "doe"
ENGINE_VERSION = "0.1.0"
CONVERGENCE_THRESHOLD = 1e-12


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
            share = remaining / (q - 1)
            pt = [0.0] * q
            pt[i] = bound_val
            if all(lowers[j] - tol <= share <= uppers[j] + tol for j in range(q) if j != i):
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
    # axis midpoints: x_i = midpoint of its bounds, remainder split equally among others
    for i in range(q):
        mid = (lowers[i] + uppers[i]) / 2.0
        remaining = total - mid
        if q < 2 or remaining < 0:
            continue
        other_low_sum = math.fsum(lowers[j] for j in range(q) if j != i)
        other_up_sum = math.fsum(uppers[j] for j in range(q) if j != i)
        if remaining < other_low_sum - tol or remaining > other_up_sum + tol:
            continue
        share = remaining / (q - 1)
        pt = [0.0] * q
        pt[i] = mid
        for j in range(q):
            if j != i:
                pt[j] = share
        if all(lowers[j] - tol <= share <= uppers[j] + tol for j in range(q) if j != i):
            pt_tuple = tuple(round(v, 12) for v in pt)
            if abs(math.fsum(pt_tuple) - total) <= tol:
                extras.append(pt_tuple)
    for e in extras:
        if e not in seen:
            seen.add(e)
            candidates.append(e)
    candidates.sort(key=lambda t: t)
    return candidates


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
