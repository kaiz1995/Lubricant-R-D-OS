"""Validate one imported PHYSICAL EXPERIMENT_RUNNING artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from preflight_experiment_import import SCHEMA_NAMES, has_text, schema_dir, timestamp_ok


RESULT = "Physical execution record imported from supplied records only; not owner approval, method qualification, product performance, or release approval."
NEXT_ACTION = "Retain the supplied raw records for existing downstream validation without inferring performance."


def main() -> int:
    if len(sys.argv) != 2: print("Usage: python validate_experiment_artifact.py <artifact.json>"); return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")); directory = schema_dir()
        schemas = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    except (OSError, json.JSONDecodeError) as error: print(f"FAIL: cannot read artifact or schemas: {error}"); return 1
    registry = Registry()
    for schema in schemas.values(): registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [error.message for error in Draft202012Validator(schemas["experiment.schema.json"], registry=registry).iter_errors(artifact)]
    if artifact.get("evidence_scope") != "PHYSICAL": errors.append("evidence_scope must be PHYSICAL")
    if artifact.get("stage") != "EXPERIMENT_RUNNING": errors.append("stage must be EXPERIMENT_RUNNING")
    if artifact.get("result") != RESULT or artifact.get("next_action") != NEXT_ACTION or artifact.get("decision") != "GO": errors.append("artifact must retain the import-only decision boundary")
    for index, run in enumerate(artifact.get("runs", [])):
        execution = run.get("execution_provenance") if isinstance(run, dict) else None
        if not isinstance(execution, dict) or not timestamp_ok(execution.get("executed_at")) or not all(has_text(execution.get(field)) for field in ("operator_reference", "instrument_reference", "calibration_reference", "raw_record_reference")):
            errors.append(f"runs[{index}] execution provenance")
    if errors:
        for error in errors: print(f"FAIL: {error}")
        return 1
    print("PASS: imported PHYSICAL experiment record conforms to the provenance-only contract"); return 0


if __name__ == "__main__": raise SystemExit(main())
