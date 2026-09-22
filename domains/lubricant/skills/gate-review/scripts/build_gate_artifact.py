"""Build the only permitted Phase 3 Gate-review artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from gate_review_policy import expected_decision_fields, final_status
from preflight_gate_review import errors_for


def main() -> int:
    if len(sys.argv) != 3: print("Usage: python build_gate_artifact.py <input.json> <temporary-file>"); return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try: data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, input_path)
    if errors: print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    project = json.loads((input_path.parent / data["project_artifact"]).read_text(encoding="utf-8")); experiment = json.loads((input_path.parent / data["experiment_artifact"]).read_text(encoding="utf-8")); optimization = json.loads((input_path.parent / data["optimization_artifact"]).read_text(encoding="utf-8")); request = {**data["gate"], "evidence_scope": optimization["evidence_scope"]}
    artifact = {"schema_version": "0.1.0", "artifact_type": "gate", "project_id": project["project_id"], "stage": "VERIFIED", "evidence_scope": optimization["evidence_scope"], **expected_decision_fields(request), "evidence": request["evidence"], "experiment_reference": experiment["experiment_id"], **{key: request[key] for key in ("gate_id", "scope", "satisfied_conditions", "unsatisfied_conditions", "evidence_gaps", "risks")}, "gate_status": final_status(request, optimization["evidence_scope"])}
    output_path.parent.mkdir(parents=True, exist_ok=True); output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
