"""Validate one Failure/CTQ record against canonical or deployed contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from preflight_failure_ctq import evidence_errors, failure_ctq_errors, schema_dir
from failure_ctq_policy import policy_errors, resolved_project_type, unrouted_reference_errors


def sibling_project_type(artifact_path: Path) -> object:
    """The project type declared by the ``project.json`` beside this artifact, if any.

    The artifact records no project type. The workspace stores the charter beside the
    artifacts it governs, so when that file is present and readable it is the authoritative
    signal; without it the policy falls back to the artifact's own shape. A failed read is
    never fatal here.
    """
    try:
        project = json.loads((artifact_path.parent / "project.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return project.get("project_type") if isinstance(project, dict) else None


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_failure_ctq_artifact.py <artifact.json>")
        return 1
    artifact_path = Path(sys.argv[1])
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        schemas = schema_dir()
        common = json.loads((schemas / "common.schema.json").read_text(encoding="utf-8"))
        project = json.loads((schemas / "project.schema.json").read_text(encoding="utf-8"))
        challenge = json.loads((schemas / "challenge.schema.json").read_text(encoding="utf-8"))
        failure_ctq = json.loads((schemas / "failure_ctq.schema.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    registry = registry.with_resource(project["$id"], Resource.from_contents(project))
    registry = registry.with_resource(challenge["$id"], Resource.from_contents(challenge))
    registry = registry.with_resource(failure_ctq["$id"], Resource.from_contents(failure_ctq))
    errors = [error.message for error in Draft202012Validator(failure_ctq, registry=registry).iter_errors(artifact)]
    if artifact.get("stage") != "FAILURE_CTQ_DEFINED":
        errors.append("stage must be FAILURE_CTQ_DEFINED")
    errors.extend(failure_ctq_errors(artifact, None))
    # Policy layer: the project type comes from a sibling project.json when the workspace
    # has one, else the record's own shape (a CTQ declaring a criteria layer). An oil
    # record resolves to the legacy path and adds nothing, exactly as before.
    project_type = sibling_project_type(artifact_path)
    route_type = resolved_project_type(
        {"project_type": project_type} if isinstance(project_type, str) and project_type else None,
        artifact,
    )
    errors.extend(policy_errors(artifact, route_type))
    # The recorded CHALLENGES_DEFINED gap is recomputed rather than trusted: a marker
    # that does not name this artifact's own project_id is a fabricated link.
    errors.extend(unrouted_reference_errors(artifact, artifact.get("project_id")))
    errors.extend(evidence_errors(artifact.get("evidence")))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: failure/CTQ artifact conforms to the Stage 2 contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
