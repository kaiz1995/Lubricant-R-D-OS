"""Build the only permitted fixed process-window artifact from preflight-valid input.

ADDITIVE (plan section 4.4.3 item 3-8): on the precision-grease route (recognized from
an upstream optimization artifact whose stage is NON_INFERIORITY_PASSED) the artifact
lands at ``PROCESS_SCALE_VALIDATED`` and its decision block states the semantics of
``validated``: the field means the window has been FIXED, not that a scale-up experiment
verified it. ``validated`` is FORCED here and can never be claimed by the caller: it is
not part of the input field set, so a supplied value is rejected by the preflight.
The on-demand PROCESS_WINDOW_DEFINED path is byte-identical to before.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from preflight_process_scale_up import GREASE_UPSTREAM_STAGE, errors_for, resolved_path
from scale_up_policy import expected_decision_fields, has_gap, window_evidence_reference, window_stage


# Carried over unchanged from the DESIGN_SPACE_DEFINED process record.
PROCESS_ARTIFACT_FIELDS = (
    "process_id", "project_reference", "process_step", "batch_scale", "amplification_factor",
    "process_window", "control_points", "cpk", "material_batch_reference", "factor_role",
)


def build_artifact(process: dict, optimization: dict, scale_up: dict) -> dict:
    """Assemble the fixed-window artifact. Pure function of validated input + upstreams."""
    grease = optimization.get("stage") == GREASE_UPSTREAM_STAGE
    window_id = scale_up["window_id"]
    return {
        "schema_version": "0.1.0",
        "artifact_type": "process",
        "project_id": process["project_id"],
        "stage": window_stage(grease),
        "evidence_scope": scale_up["evidence_scope"],
        **expected_decision_fields(process["process_id"], window_id, not has_gap(scale_up), grease),
        "evidence": [*process["evidence"], *scale_up["evidence"]],
        **{field: process[field] for field in PROCESS_ARTIFACT_FIELDS},
        "amplification_factor": scale_up["amplification_factor"],
        "batch_scale": scale_up["batch_scale"],
        "process_window": {
            "window_id": window_id,
            "basis": scale_up["basis"],
            # FORCED, never claimed: the input field set has no `validated`, so the builder
            # is the only writer. It records that the window has been fixed at the fixed
            # stage; it is not a scale-up experiment verification statement.
            "validated": True,
            "evidence_reference": window_evidence_reference(window_id),
        },
    }


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
    optimization = json.loads(resolved_path(data["optimization_artifact"], input_path).read_text(encoding="utf-8"))
    artifact = build_artifact(process, optimization, data["scale_up"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path} stage={artifact['stage']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
