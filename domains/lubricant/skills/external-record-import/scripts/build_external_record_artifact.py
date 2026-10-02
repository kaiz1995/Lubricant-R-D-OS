"""Build the only permitted external-record artifact from preflight-valid input."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from external_record_policy import ARTIFACT_FIELDS, expected_decision_fields
from preflight_external_record_import import errors_for


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_external_record_artifact.py <input.json> <temporary-file>")
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
    record = data["external_record"]
    artifact = {
        "schema_version": "0.1.0",
        "artifact_type": "external_record",
        "project_id": record["project_reference"],
        "stage": "DRAFT",
        "evidence_scope": record["evidence_scope"],
        "source": record["source"],
        "evidence_id": record["evidence_id"],
        **expected_decision_fields(record),
        "evidence": record["evidence"],
        **{field: record[field] for field in ARTIFACT_FIELDS},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
