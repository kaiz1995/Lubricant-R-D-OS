"""Build the only permitted DUTY_DEFINED artifact from preflight-valid input."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from preflight_duty_definition import DUTY_FIELDS, errors_for, project_errors, resolved_path


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_duty_artifact.py <input.json> <temporary-file>")
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
    _, project = project_errors(resolved_path(data["project_artifact"], input_path))
    duty = data["duty"]
    artifact = {
        "schema_version": "0.1.0", "artifact_type": "duty", "project_id": project["project_id"],
        "stage": "DUTY_DEFINED", "decision_question": f"Can supplied duty profile {data['duty_id']} be recorded?",
        "hypothesis": "Supplied duty conditions can define the project duty profile.",
        "uncertainty": "Declared assumptions remain assumed; this record does not derive a challenge, failure, CTQ, test, or performance conclusion.",
        "evidence": [{key: duty[name][key] for key in ("evidence_id", "statement", "source", "status")} for name in DUTY_FIELDS],
        "decision_rule": "Record only complete duty conditions linked to an active Project Charter and preserve their declared evidence statuses.",
        "result": "The supplied duty profile is recorded with its declared evidence statuses and without downstream conclusions.",
        "decision": "GO", "next_action": "Record a supplied duty-derived challenge.",
        "duty_id": data["duty_id"], "project_reference": project["project_id"], "duty": duty,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
