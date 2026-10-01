"""Build the only permitted process artifact from preflight-valid input."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from preflight_process_definition import errors_for, resolved_path
from process_policy import expected_decision_fields


PROCESS_ARTIFACT_FIELDS = (
    "process_id", "project_reference", "process_step", "batch_scale", "amplification_factor",
    "process_window", "control_points", "cpk", "material_batch_reference", "factor_role",
)


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_process_artifact.py <input.json> <temporary-file>")
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
    design_space = json.loads(resolved_path(data["design_space_artifact"], input_path).read_text(encoding="utf-8"))
    process = data["process"]
    artifact = {
        "schema_version": "0.1.0", "artifact_type": "process", "project_id": design_space["project_id"], "stage": "DESIGN_SPACE_DEFINED",
        "evidence_scope": process["evidence_scope"],
        **expected_decision_fields(process), "evidence": process["evidence"],
        **{field: process[field] for field in PROCESS_ARTIFACT_FIELDS},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
