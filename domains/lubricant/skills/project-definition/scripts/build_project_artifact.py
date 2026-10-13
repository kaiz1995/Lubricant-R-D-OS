"""Build the only permitted project artifact from preflight-valid input.

Shape: preflight -> build -> validate, the same three-script shape as the pack's other
skills (see skills/bench-registration/scripts/build_bench_artifact.py). This skill used
to ship only preflight + validate, so the charter had to be hand-assembled by the caller
(SKILL.md Step 2) and the stage could never be produced by the skill itself.

Determinism and honesty
-----------------------
* ``stage`` is the constant charter marker ``PROJECT_DEFINED`` (project_definition_policy
  .PROJECT_STAGE), never a progress field, and the deterministic decision fields come
  from ``project_definition_policy.expected_decision_fields`` -- computed from the input,
  not written by hand here.
* Nothing is invented: project-content fields are copied verbatim from the input, and
  the input's ``source_evidence`` becomes the charter's ``evidence`` unchanged. A datum
  the input does not supply stays absent (``target_cost`` / ``benchmark_products`` are
  the schema's own if/then cases), so a missing benchmark needs a recorded
  ``benchmark_waiver_reason`` and an unmeasured cost needs its own recorded reason --
  exactly as in the schema, never a fabricated value.
* Business rules are not duplicated: this script refuses input with the very same
  ``errors_for`` the preflight uses, so preflight and build can never disagree.
* The output path is the caller's temporary candidate, exactly as in bench-registration:
  the landed workspace artifact is the canonical stage name ``project.json`` (or the
  legal ``project-<project_id>-<id>.json``), written by SKILL.md Step 4 only after
  validate passes. A caller-chosen temp name (e.g. ``project.grease.json``) is a
  naming-contract violation if it lands, and scripts/check_artifact_naming.py says so.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from preflight_project_definition import errors_for
from project_definition_policy import (
    PROJECT_FIELDS,
    PROJECT_STAGE,
    evidence_for,
    expected_decision_fields,
)


def build_artifact(data: dict) -> dict:
    """Assemble the charter. Field order mirrors the pack's canonical project fixtures."""
    decision = expected_decision_fields(data)
    artifact = {
        "schema_version": "0.1.0",
        "artifact_type": "project",
        "project_id": data["project_id"],
        "stage": PROJECT_STAGE,
        "status": "ACTIVE",
        "decision_question": decision["decision_question"],
        "hypothesis": decision["hypothesis"],
        "uncertainty": decision["uncertainty"],
        "evidence": evidence_for(data),
        "decision_rule": decision["decision_rule"],
        "result": decision["result"],
        "decision": decision["decision"],
        "next_action": decision["next_action"],
        **{field: data[field] for field in PROJECT_FIELDS if field in data},
    }
    return artifact


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_project_artifact.py <input.json> <temporary-file>")
        return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    artifact = build_artifact(data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
