"""Build the only permitted Phase 3 statistical-model request artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from preflight_statistical_analysis import errors_for
from statistical_analysis_policy import expected_decision_fields


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_model_artifact.py <input.json> <temporary-file>"); return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try: data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, input_path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    def load(key: str) -> dict: return json.loads((input_path.parent / data[key]).read_text(encoding="utf-8"))
    project, method, design_space, experiment = (load(key) for key in ("project_artifact", "test_method_artifact", "design_space_artifact", "experiment_artifact"))
    request = data["analysis"]
    artifact = {"schema_version": "0.1.0", "artifact_type": "model", "project_id": project["project_id"], "stage": "MODEL_BUILT", **expected_decision_fields(request), "evidence": request["evidence"], "experiment_reference": experiment["experiment_id"], "design_space_reference": design_space["design_space_id"], "test_method_references": [method["method_id"]], "engine_handoff": "PHASE4_DETERMINISTIC_ENGINE", **{key: request[key] for key in ("model_id", "requested_analyses", "response_references")}}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
