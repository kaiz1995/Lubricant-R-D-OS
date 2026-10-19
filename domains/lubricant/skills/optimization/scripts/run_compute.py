"""Run the optimization engine behind the evidence-scope boundary.

stdin JSON needs top-level evidence_scope in {SYNTHETIC, PHYSICAL}.
stdout: {"evidence_scope", "input_sha256", "result", "usage_constraints"?}

ADDITIVE (precision-grease step 14, plan section 4.4.3 item 3-4): the caller may supply
the model's applicability boundary as ``model_trust_region`` (the same shape the
statistical-analysis handoff declares). It is translated here into the engine's
``trust_region`` box so a recommended point outside the model's validated region is
removed or explicitly degraded rather than recommended silently. When the key is absent
the payload is passed through untouched, byte for byte, so every oil request and the
frozen gold output are unchanged.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ENGINE = "optimization"
USAGE_CONSTRAINTS = [
    "SYNTHETIC_DEMO_ONLY",
    "NOT_FOR_PHYSICAL_RELEASE",
    "CANNOT_QUALIFY_METHOD",
]
# Kept in sync with optimization_policy (deployed copies are separate files, so the
# names are duplicated here as plain constants rather than imported across skills).
MODEL_TRUST_REGION_INPUT_FIELD = "model_trust_region"
TRUST_REGION_FIELD = "trust_region"


def _canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _trust_region_from_boundary(boundary):
    """The model's applicability boundary in the engine's enforceable box form, or None.

    Returns (region, error_message). The boundary must declare a numeric lower and upper
    bound for at least one variable; a statement with no box cannot be enforced, so it is
    refused here rather than silently dropped.
    """
    if not isinstance(boundary, dict):
        return None, "model_trust_region must be an object"
    allowed = {"variable_references", "region_statement", "lower_bounds", "upper_bounds", "unit", "basis", "source"}
    unknown = sorted(set(boundary) - allowed)
    if unknown:
        return None, f"model_trust_region: unexpected={unknown}"
    variables = boundary.get("variable_references")
    statement = boundary.get("region_statement")
    if not isinstance(variables, list) or not variables or not all(isinstance(item, str) and item.strip() for item in variables):
        return None, "model_trust_region.variable_references must be a non-empty array of non-empty strings"
    if not isinstance(statement, str) or not statement.strip():
        return None, "model_trust_region.region_statement must be a non-empty string"
    lower = boundary.get("lower_bounds") or {}
    upper = boundary.get("upper_bounds") or {}
    if not isinstance(lower, dict) or not isinstance(upper, dict):
        return None, "model_trust_region lower_bounds and upper_bounds must be objects when supplied"
    bounds = []
    for name in variables:
        if name in lower and name in upper:
            low, high = lower[name], upper[name]
            if isinstance(low, bool) or isinstance(high, bool) or not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
                return None, f"model_trust_region bounds for {name} must be numbers"
            if low > high:
                return None, f"model_trust_region: lower bound of {name} exceeds its upper bound, so the region is empty"
            bounds.append({"component_id": name, "lower": float(low), "upper": float(high)})
    if not bounds:
        return None, "model_trust_region must declare numeric lower_bounds and upper_bounds for at least one variable: a boundary with no enforceable box cannot constrain a recommendation"
    region = {"region_statement": statement, "mode": "EXCLUDE", "variable_bounds": bounds}
    if boundary.get("basis") is not None:
        region["basis"] = boundary["basis"]
    return region, None


def _engine_root():
    script = Path(__file__).resolve()
    candidates = [
        script.parents[1] / "engine" / "lubricant",
        script.parents[3] / "domains" / "lubricant",
    ]
    for candidate in candidates:
        if (candidate / "compute" / "__main__.py").is_file():
            return candidate
    return None


def _import_engines(engine_root):
    """Make the engine tree importable, including the optimization absolute import."""
    sys.path.insert(0, str(engine_root.parent))
    sys.path.insert(0, str(engine_root.parents[1]))
    if not (engine_root.parents[1] / "domains").is_dir():
        # Installed layout has no real domains package; alias the engine tree under
        # the domains.* namespace used by the frozen optimization engine import.
        import types

        import lubricant.compute.cost.engine as cost_twin

        domains = types.ModuleType("domains")
        domains.__path__ = []
        sys.modules["domains"] = domains
        sys.modules["domains.lubricant"] = sys.modules["lubricant"]
        sys.modules["domains.lubricant.compute"] = sys.modules["lubricant.compute"]
        sys.modules["domains.lubricant.compute.cost"] = sys.modules["lubricant.compute.cost"]
        sys.modules["domains.lubricant.compute.cost.engine"] = cost_twin
    from lubricant.compute.__main__ import ENGINES  # noqa: E402

    return ENGINES


def main():
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as error:
        print(f"FAIL: input JSON failed: {error}", file=sys.stderr)
        return 1
    if not isinstance(data, dict) or "evidence_scope" not in data:
        print("FAIL: top-level evidence_scope is required", file=sys.stderr)
        return 1
    scope = data["evidence_scope"]
    if scope not in {"SYNTHETIC", "PHYSICAL"}:
        print(f"FAIL: evidence_scope must be SYNTHETIC or PHYSICAL, got {scope!r}", file=sys.stderr)
        return 1
    engine_root = _engine_root()
    if engine_root is None:
        print("FAIL: lubricant engine tree not found", file=sys.stderr)
        return 1
    payload = {key: value for key, value in data.items() if key != "evidence_scope"}
    if MODEL_TRUST_REGION_INPUT_FIELD in payload:
        # The model's applicability boundary travels input-side; the engine consumes the
        # box form under its own key. A boundary that cannot be enforced is refused.
        boundary = payload.pop(MODEL_TRUST_REGION_INPUT_FIELD)
        region, region_error = _trust_region_from_boundary(boundary)
        if region_error:
            print(f"FAIL: {region_error}", file=sys.stderr)
            return 1
        payload[TRUST_REGION_FIELD] = region
    raw = _canonical(payload)
    try:
        result = _import_engines(engine_root)[ENGINE](payload, raw)
    except Exception as error:
        print(f"FAIL: {ENGINE} engine failed: {error}", file=sys.stderr)
        return 1
    output = {
        "evidence_scope": scope,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "result": result,
    }
    if scope == "SYNTHETIC":
        output["usage_constraints"] = USAGE_CONSTRAINTS
    sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

