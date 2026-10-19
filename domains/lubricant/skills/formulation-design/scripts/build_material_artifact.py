"""Build the only permitted material record from preflight-valid input."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from material_policy import MATERIAL_FIELDS, expected_decision_fields
from preflight_material import errors_for, resolved_path


# The stage constant the material contract fixes for this record. ``material`` is a
# companion artifact of the design-space step, not a stage of its own: no route stage
# and no panel entry was created for it.
MATERIAL_STAGE = "DESIGN_SPACE_DEFINED"


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_material_artifact.py <input.json> <temporary-file>")
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
    material = data["material"]
    artifact = {
        "schema_version": "0.1.0", "artifact_type": "material", "project_id": project["project_id"],
        "stage": MATERIAL_STAGE, "evidence_scope": data["evidence_scope"],
        **expected_decision_fields(material, data["evidence_scope"]), "evidence": data["evidence"],
        **{field: material[field] for field in MATERIAL_FIELDS},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
