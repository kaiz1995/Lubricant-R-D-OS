"""Validate one deterministic Phase 3 optimization request artifact.

The validator recomputes the canonical decision block from the artifact's own fields.
The grease route is inferred from the artifact itself: ``stage == NON_INFERIORITY_PASSED``
is the precision-grease step-14 stage and can only be produced by that route, so the
grease wording, the variance citation, and the trust region are re-asserted on the frozen
artifact rather than taken on trust. Oil artifacts keep the original wording, word for word.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from optimization_policy import GREASE_STAGE, TRUST_REGION_FIELD, expected_decision_fields, trust_region_from_boundary, trust_region_summary
from preflight_optimization import SCHEMAS, schema_dir


def as_boundary(trust_region: dict) -> dict:
    """Project an artifact trust region back to the boundary shape the box rule checks."""
    bounds = trust_region.get("variable_bounds") if isinstance(trust_region, dict) else None
    bounds = bounds if isinstance(bounds, list) else []
    return {
        "variable_references": [item.get("component_id") for item in bounds if isinstance(item, dict)],
        "region_statement": trust_region.get("region_statement") if isinstance(trust_region, dict) else None,
        "lower_bounds": {item.get("component_id"): item.get("lower") for item in bounds if isinstance(item, dict)},
        "upper_bounds": {item.get("component_id"): item.get("upper") for item in bounds if isinstance(item, dict)},
    }


def main() -> int:
    if len(sys.argv) != 2: print("Usage: python validate_optimization_artifact.py <artifact.json>"); return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")); directory = schema_dir(); schemas = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMAS}
    except (OSError, json.JSONDecodeError) as error: print(f"FAIL: cannot read artifact or schemas: {error}"); return 1
    registry = Registry()
    for schema in schemas.values(): registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [error.message for error in Draft202012Validator(schemas["optimization.schema.json"], registry=registry).iter_errors(artifact)]
    grease = artifact.get("stage") == GREASE_STAGE
    trust_region = artifact.get(TRUST_REGION_FIELD) if grease else None
    for field, value in expected_decision_fields(artifact, grease, trust_region).items():
        if artifact.get(field) != value: errors.append(f"{field} must equal the deterministic optimization policy")
    if grease:
        # The trust region on a grease artifact must be in the engine's enforceable box
        # form: a statement with no numeric bounds would leave the engine unable to keep
        # a recommendation inside the model's region.
        if not isinstance(trust_region, dict):
            errors.append(f"{TRUST_REGION_FIELD} is required on a {GREASE_STAGE} artifact")
        elif trust_region_from_boundary(as_boundary(trust_region)) is None:
            errors.append(f"{TRUST_REGION_FIELD} must be an enforceable box (non-empty variable_bounds, lower <= upper, numeric)")
        elif trust_region_summary(trust_region) is None:
            errors.append(f"{TRUST_REGION_FIELD} must carry a region_statement and at least one variable bound")
        if not isinstance(artifact.get("variance_reference"), str) or not artifact.get("variance_reference", "").strip():
            errors.append(f"variance_reference is required on a {GREASE_STAGE} artifact: the variance verdict that admitted this round must be cited")
    if errors:
        for error in errors: print(f"FAIL: {error}")
        return 1
    print("PASS: deterministic optimization request conforms to the Phase 3 contract"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
