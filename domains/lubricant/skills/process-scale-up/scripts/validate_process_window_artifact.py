"""Validate one deterministic PROCESS_WINDOW_DEFINED process artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from preflight_process_scale_up import schema_dir
from scale_up_policy import expected_decision_fields, has_gap, window_evidence_reference


def semantic_errors(artifact: dict) -> list[str]:
    errors: list[str] = []
    if artifact.get("stage") != "PROCESS_WINDOW_DEFINED":
        errors.append("stage must be PROCESS_WINDOW_DEFINED")
    window = artifact.get("process_window")
    if not isinstance(window, dict):
        errors.append("process_window")
        return errors
    window_id = window.get("window_id")
    if window.get("validated") is not True:
        errors.append("process_window.validated must be true for a fixed process window")
    if window.get("evidence_reference") != window_evidence_reference(window_id):
        errors.append(f"process_window.evidence_reference must be {window_evidence_reference(window_id)}")
    for field, value in expected_decision_fields(artifact.get("process_id"), window_id, not has_gap(artifact)).items():
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
    print("PASS: deterministic process-window artifact conforms to the process contract at PROCESS_WINDOW_DEFINED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
