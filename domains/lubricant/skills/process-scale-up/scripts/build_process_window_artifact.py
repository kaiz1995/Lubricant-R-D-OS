"""Build the only permitted PROCESS_WINDOW_DEFINED process artifact from preflight-valid input."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from preflight_process_scale_up import errors_for, resolved_path
from scale_up_policy import expected_decision_fields, has_gap, window_evidence_reference


# Carried over unchanged from the DESIGN_SPACE_DEFINED process record.
PROCESS_ARTIFACT_FIELDS = (
    "process_id", "project_reference", "process_step", "batch_scale", "amplification_factor",
    "process_window", "control_points", "cpk", "material_batch_reference", "factor_role",
)


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_process_window_artifact.py <input.json> <temporary-file>")
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
    process = json.loads(resolved_path(data["process_artifact"], input_path).read_text(encoding="utf-8"))
    scale_up = data["scale_up"]
    window_id = scale_up["window_id"]
    artifact = {
        "schema_version": "0.1.0",
        "artifact_type": "process",
        "project_id": process["project_id"],
        "stage": "PROCESS_WINDOW_DEFINED",
        "evidence_scope": scale_up["evidence_scope"],
        **expected_decision_fields(process["process_id"], window_id, not has_gap(scale_up)),
        "evidence": [*process["evidence"], *scale_up["evidence"]],
        **{field: process[field] for field in PROCESS_ARTIFACT_FIELDS},
        "amplification_factor": scale_up["amplification_factor"],
        "batch_scale": scale_up["batch_scale"],
        "process_window": {
            "window_id": window_id,
            "basis": scale_up["basis"],
            "validated": True,
            "evidence_reference": window_evidence_reference(window_id),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
