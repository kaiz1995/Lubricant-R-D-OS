"""Build the only permitted REFERENCE_MATERIAL_RESOLVED artifact from preflight-valid input.

Deterministic assembly only. Every judgment - which dossiers may be recorded RESOLVED,
which ladder rung the set achieved, and the downstream discrimination flag - lives in
``reference_material_policy`` so this builder and the validator cannot disagree.

The builder never invents a reference material. A side with no support is recorded
UNRESOLVED with an empty ``history_evidence`` list, which the artifact contract permits
for an unresolved entry, and the set carries
``downstream_flag: DISCRIMINATION_EVIDENCE_INCOMPLETE``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from reference_material_policy import (
    DOSSIER_ARTIFACT_FIELDS,
    derive_downstream_flag,
    expected_decision_fields,
    recorded_side,
    tier_from_input,
)
from preflight_reference_material import errors_for, resolved_path, upstream_errors


def build_artifact(data: dict, project: dict) -> dict:
    """Assemble the reference artifact. Pure function of validated input + charter."""
    known_good = recorded_side(data.get("known_good"), "known_good")
    known_bad = recorded_side(data.get("known_bad"), "known_bad")
    tier = tier_from_input(data.get("known_good"), data.get("known_bad"))
    downstream_flag = derive_downstream_flag(known_bad)
    reference_id = data["reference_id"]
    evidence_scope = data["evidence_scope"]
    evidence = data["evidence"]
    artifact = {
        "schema_version": "0.1.0",
        "artifact_type": "reference",
        "project_id": project["project_id"],
        "stage": "REFERENCE_MATERIAL_RESOLVED",
        "evidence_scope": evidence_scope,
        **expected_decision_fields(
            reference_id, evidence_scope, known_good, known_bad, tier, downstream_flag, evidence
        ),
        "evidence": evidence,
        "reference_id": reference_id,
        "known_good": [{field: dossier.get(field) for field in DOSSIER_ARTIFACT_FIELDS} for dossier in known_good],
        "known_bad": [{field: dossier.get(field) for field in DOSSIER_ARTIFACT_FIELDS} for dossier in known_bad],
        "tier": tier,
        "downstream_flag": downstream_flag,
    }
    return artifact


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_reference_artifact.py <input.json> <temporary-file>")
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
    _, project = upstream_errors(resolved_path(data["project_artifact"], input_path))
    artifact = build_artifact(data, project)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"BUILT: {output_path} stage={artifact['stage']} tier={artifact['tier']} "
        f"decision={artifact['decision']} downstream_flag={artifact['downstream_flag']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
