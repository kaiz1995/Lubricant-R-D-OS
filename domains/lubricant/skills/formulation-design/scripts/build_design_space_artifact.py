"""Build the only permitted Stage 4 artifact from preflight-valid input."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from design_space_policy import expected_decision_fields
from preflight_formulation_design import errors_for, resolved_path


DESIGN_SPACE_FIELDS = ("design_space_id", "scope", "variables", "ctq_references", "qualified_test_method_references", "constraints")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_design_space_artifact.py <input.json> <temporary-file>")
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
    design_space = data["design_space"]
    artifact = {
        "schema_version": "0.1.0", "artifact_type": "design_space", "project_id": project["project_id"], "stage": "DESIGN_SPACE_DEFINED",
        **expected_decision_fields(design_space), "evidence": design_space["evidence"],
        **{field: design_space[field] for field in DESIGN_SPACE_FIELDS},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
