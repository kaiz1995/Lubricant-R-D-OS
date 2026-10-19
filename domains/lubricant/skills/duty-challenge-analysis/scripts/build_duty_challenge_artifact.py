"""Build the only permitted CHALLENGES_DEFINED member from preflight-valid input.

The builder is deterministic assembly: the category set it may record comes from the
policy layer, which is gated on the project type. For the six oil routes that is the
twelve original categories; for ``PRECISION_GREASE_DEV`` it is the grease set (the eight
grease challenges plus the shared values that still describe a grease challenge), with the
three oil-only values rejected outright.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from duty_challenge_policy import allowed_categories, is_precision_grease
from preflight_duty_challenge import duty_errors, errors_for, project_type


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_duty_challenge_artifact.py <input.json> <temporary-file>")
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
    resolved = data["duty_artifact"]
    if not Path(resolved).is_absolute():
        resolved = str(input_path.parent / resolved)
    _, duty = duty_errors(Path(resolved))
    route_type = project_type(data, input_path, duty)
    challenge = data["challenge"]
    # Policy gate before assembly: the category must be in the set the policy layer allows
    # for this project type. Preflight already rejected the oil-only values on the grease
    # route; this repeats the check at the construction boundary so the builder can never
    # assemble a grease artifact around a category its own route forbids.
    category = challenge.get("category")
    if category not in allowed_categories(route_type):
        print(f"HOLD: challenge.category {category} is not recordable for this project type; no artifact generated")
        return 1

    challenge_evidence = data.get("challenge_evidence")
    artifact = {
        "schema_version": "0.1.0", "artifact_type": "challenge", "project_id": duty["project_id"],
        "stage": "CHALLENGES_DEFINED",
        "decision_question": f"Which duty-derived challenge is recorded for duty profile {duty.get('duty_id')}?",
        "hypothesis": f"{challenge.get('description')}",
        "uncertainty": f"Evidence gap remains open: {challenge.get('evidence_gap')}",
        "evidence": [
            *[{key: item[key] for key in ("evidence_id", "statement", "source", "status")} for item in challenge_evidence],
        ],
        "decision_rule": "Record only fully evidenced duty conditions and explicitly supplied challenge levels.",
        "result": (
            f"The supplied {challenge.get('category')} challenge is recorded without failure, CTQ, test, "
            "or formulation conclusions."
        ),
        "decision": "GO", "next_action": "Define failure and CTQ relationships.",
        "duty_reference": challenge.get("duty_reference"), "challenge_id": challenge.get("challenge_id"),
        "category": category, "description": challenge.get("description"),
        "severity": challenge.get("severity"), "exposure": challenge.get("exposure"),
        "lubricant_sensitivity": challenge.get("lubricant_sensitivity"),
        "evidence_gap": challenge.get("evidence_gap"), "priority": challenge.get("priority"),
    }
    if is_precision_grease(route_type):
        # Record the route fact in uncertainty rather than in a new artifact field: the
        # challenge contract's shape is frozen, and the category set is what downstream
        # reads. Nothing here changes oil-route output.
        artifact["uncertainty"] = (
            f"Precision-gear grease route: challenge categories are restricted to the grease set. "
            f"Evidence gap remains open: {challenge.get('evidence_gap')}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
