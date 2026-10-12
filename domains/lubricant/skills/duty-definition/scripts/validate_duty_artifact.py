"""Validate one duty artifact against canonical or deployed schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from duty_definition_policy import dimension_errors, resolved_project_type


SKILL_ROOT = Path(__file__).resolve().parents[1]


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    names = ("common.schema.json", "duty.schema.json")
    return canonical if all((canonical / name).is_file() for name in names) else SKILL_ROOT / "references"


def sibling_project_type(artifact_path: Path) -> object:
    """The project type declared by the ``project.json`` beside this artifact, if any.

    The artifact itself records no project type. The workspace stores the charter beside the
    artifacts it governs, so when that file is present and readable it is the authoritative
    signal; when it is absent the policy falls back to the artifact's own shape. A failed
    read is never fatal: naming and schema checks own that verdict, and this gate must not
    fail closed on an unrelated file.
    """
    try:
        project = json.loads((artifact_path.parent / "project.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return project.get("project_type") if isinstance(project, dict) else None


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_duty_artifact.py <artifact.json>")
        return 1
    try:
        schemas = schema_dir()
        common = json.loads((schemas / "common.schema.json").read_text(encoding="utf-8"))
        duty = json.loads((schemas / "duty.schema.json").read_text(encoding="utf-8"))
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    registry = registry.with_resource(duty["$id"], Resource.from_contents(duty))
    errors = sorted(Draft202012Validator(duty, registry=registry).iter_errors(artifact), key=lambda error: list(error.path))
    if errors:
        for error in errors:
            location = "/".join(map(str, error.path)) or "<root>"
            print(f"FAIL: {location}: {error.message}")
        return 1
    # Policy layer: the shared contract keeps the grease dimensions optional, so a
    # grease-shaped artifact is re-checked here. The project type comes from a sibling
    # project.json when the workspace has one, else from the artifact's own shape: an oil
    # artifact carries no grease dimension and no grease charter, resolves to the legacy
    # set, and passes exactly as before.
    artifact_path = Path(sys.argv[1])
    project_type = sibling_project_type(artifact_path)
    policy_errors = dimension_errors(artifact.get("duty"), resolved_project_type(project_type, artifact.get("duty")))
    if policy_errors:
        for error in policy_errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: duty artifact conforms to the Duty Definition schema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
