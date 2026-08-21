"""Build the only permitted Phase 3 experiment-design request artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from doe_design_policy import expected_decision_fields
from preflight_doe_design import errors_for, resolved_path


REQUEST_FIELDS = ("experiment_design_id", "factor_references", "design", "run_plan", "responses", "guardrails", "expected_information_value", "mixture_total")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_experiment_design_artifact.py <input.json> <temporary-file>")
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
    project = json.loads(resolved_path(data["project_artifact"], input_path).read_text(encoding="utf-8"))
    method = json.loads(resolved_path(data["test_method_artifact"], input_path).read_text(encoding="utf-8"))
    design_space = json.loads(resolved_path(data["design_space_artifact"], input_path).read_text(encoding="utf-8"))
    request = data["experiment_design"]
    artifact = {
        "schema_version": "0.1.0", "artifact_type": "experiment_design", "project_id": project["project_id"], "stage": "EXPERIMENT_DESIGNED",
        **expected_decision_fields(request), "evidence": request["evidence"], "design_space_reference": design_space["design_space_id"], "test_method_references": [method["method_id"]],
        **{field: request[field] for field in REQUEST_FIELDS if field in request},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
