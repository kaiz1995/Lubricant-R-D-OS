"""Validate one Challenge Map member against the canonical or deployed schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from duty_challenge_policy import category_errors


SKILL_ROOT = Path(__file__).resolve().parents[1]


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    names = ("common.schema.json", "project.schema.json", "challenge.schema.json")
    if all((canonical / name).is_file() for name in names):
        return canonical
    return SKILL_ROOT / "references"


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
        print("Usage: python validate_duty_challenge_artifact.py <artifact.json>")
        return 1
    artifact_path = Path(sys.argv[1])
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        schemas = schema_dir()
        common = json.loads((schemas / "common.schema.json").read_text(encoding="utf-8"))
        project = json.loads((schemas / "project.schema.json").read_text(encoding="utf-8"))
        challenge = json.loads((schemas / "challenge.schema.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1

    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    registry = registry.with_resource(project["$id"], Resource.from_contents(project))
    registry = registry.with_resource(challenge["$id"], Resource.from_contents(challenge))
    errors = sorted(Draft202012Validator(challenge, registry=registry).iter_errors(artifact), key=lambda error: list(error.path))
    if errors:
        for error in errors:
            location = "/".join(map(str, getattr(error, "path", ()))) or "<root>"
            print(f"FAIL: {location}: {error.message}")
        return 1
    if artifact.get("stage") != "CHALLENGES_DEFINED":
        print("FAIL: stage: must be CHALLENGES_DEFINED")
        return 1
    # Policy layer: the shared enum keeps the oil-only values legal for every route, so a
    # grease-route record is re-checked here. The project type comes from a sibling
    # project.json when the workspace has one; an oil workspace resolves to the legacy set
    # and passes exactly as before.
    project_type = sibling_project_type(artifact_path)
    route_type = project_type if isinstance(project_type, str) and project_type else None
    policy_errors = category_errors(artifact.get("category"), route_type)
    if policy_errors:
        for error in policy_errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: challenge artifact conforms to the Challenge Map member contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
