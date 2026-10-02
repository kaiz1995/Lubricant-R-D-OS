"""Build the only permitted interface artifact from preflight-valid input."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from interface_policy import ARTIFACT_FIELDS, expected_decision_fields
from preflight_interface_definition import errors_for


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_interface_artifact.py <input.json> <temporary-file>")
        return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    interface = data["interface"]
    artifact = {
        "schema_version": "0.1.0",
        "artifact_type": "interface",
        "project_id": interface["project_reference"],
        "stage": "DRAFT",
        "evidence_scope": interface["evidence_scope"],
        "source": interface["source"],
        "evidence_id": interface["evidence_id"],
        **expected_decision_fields(interface),
        "evidence": interface["evidence"],
        **{field: interface[field] for field in ARTIFACT_FIELDS},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
