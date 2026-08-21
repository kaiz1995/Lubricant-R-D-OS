"""Build the only permitted Stage 3 artifact from preflight-valid input."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from preflight_test_method import errors_for, resolved_path
from qualification_policy import expected_decision_fields


METHOD_FIELDS = ("method_id", "name", "standard", "target_failure_reference", "role", "qualification_metrics", "qualification_basis", "qualification_status")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_test_method_artifact.py <input.json> <temporary-file>")
        return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, input_path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    project_path = resolved_path(data["project_artifact"], input_path)
    project = json.loads(project_path.read_text(encoding="utf-8"))
    method = {**data["test_method"], "evidence": data["evidence"]}
    artifact = {
        "schema_version": "0.1.0", "artifact_type": "test_method", "project_id": project["project_id"], "stage": "TEST_METHODS_QUALIFIED",
        **expected_decision_fields(method), "evidence": data["evidence"],
        **{field: method[field] for field in METHOD_FIELDS},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
