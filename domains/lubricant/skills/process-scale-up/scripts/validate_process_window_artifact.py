"""Validate one deterministic fixed process-window process artifact.

Two stages are legal and neither is inferred from anything but the artifact itself:
``PROCESS_WINDOW_DEFINED`` (the frozen on-demand window of the oil routes) and
``PROCESS_SCALE_VALIDATED`` (the precision-grease route's step-15 stage). The stage
selects the wording of the decision block, so both are re-asserted on the frozen
artifact rather than taken on trust. ``validated`` is a fixed-window marker that the
builder forces; the validator re-checks it and re-checks the PROCESS-WINDOW citation a
design freeze must use for MANUFACTURABILITY_ACCEPTABLE.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from preflight_process_scale_up import schema_dir
from scale_up_policy import GREASE_STAGE, ON_DEMAND_STAGE, expected_decision_fields, has_gap, window_evidence_reference


def semantic_errors(artifact: dict) -> list[str]:
    errors: list[str] = []
    stage = artifact.get("stage")
    if stage not in (ON_DEMAND_STAGE, GREASE_STAGE):
        errors.append(f"stage must be {ON_DEMAND_STAGE} or {GREASE_STAGE}")
    grease = stage == GREASE_STAGE
    window = artifact.get("process_window")
    if not isinstance(window, dict):
        errors.append("process_window")
        return errors
    window_id = window.get("window_id")
    if window.get("validated") is not True:
        errors.append("process_window.validated must be true for a fixed process window")
    if window.get("evidence_reference") != window_evidence_reference(window_id):
        errors.append(f"process_window.evidence_reference must be {window_evidence_reference(window_id)}")
    if grease:
        # One fixed-window record must not carry two batch identities. The check is
        # GATED ON THE GREASE STAGE: the oil routes legitimately record the baseline
        # batch in `material_batch_reference` and the amplified batch in
        # `batch_scale.batch_size.material_batch` (two different values by design),
        # so an unconditional comparison would fail every oil artifact.
        scale_batch = ((artifact.get("batch_scale") or {}).get("batch_size") or {}).get("material_batch")
        if artifact.get("material_batch_reference") != scale_batch:
            errors.append(
                "material_batch_reference must equal batch_scale.batch_size.material_batch on the "
                f"{GREASE_STAGE} record: one fixed-window record must not carry two batch identities"
            )
    for field, value in expected_decision_fields(artifact.get("process_id"), window_id, not has_gap(artifact), grease).items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic scale-up policy")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_process_window_artifact.py <artifact.json>")
        return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        schemas = schema_dir()
        loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in ("common.schema.json", "process.schema.json")}
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [error.message for error in Draft202012Validator(loaded["process.schema.json"], registry=registry).iter_errors(artifact)]
    errors.extend(semantic_errors(artifact))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    stage = artifact.get("stage")
    print(f"PASS: deterministic process-window artifact conforms to the process contract at {stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
