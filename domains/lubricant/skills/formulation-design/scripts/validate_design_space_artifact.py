"""Validate one deterministic design-space artifact.

The validator sees the artifact without its upstream charter, so it detects the
grease extension from the artifact itself: a record that carries
``baseline_process_reference``, ``feasibility_regions``, or a variable with
``material_reference`` / ``role`` is held to the whole grease rule set. A record
that carries none of them keeps exactly the pre-change rule set, which is what
the six oil routes produce.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from design_space_policy import effective_route_is_grease, expected_decision_fields
from preflight_formulation_design import design_space_errors, load_materials, schema_dir


SCHEMA_NAMES = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json")
DESIGN_SPACE_FIELDS = ("design_space_id", "scope", "variables", "ctq_references", "qualified_test_method_references", "constraints", "evidence")
OPTIONAL_DESIGN_SPACE_FIELDS = ("process_reference", "baseline_process_reference", "feasibility_regions")
GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"


def semantic_errors(artifact: dict, artifact_path: Path | None = None) -> list[str]:
    design_space = {field: artifact.get(field) for field in DESIGN_SPACE_FIELDS}
    for field in OPTIONAL_DESIGN_SPACE_FIELDS:
        if artifact.get(field) is not None:
            design_space[field] = artifact[field]
    # The artifact itself decides whether the grease rules apply; a record that
    # uses the extension is checked as the grease route, and one that does not is
    # checked exactly as before. Material records are read from the artifact's own
    # directory, which is where a workspace keeps them.
    project_type = GREASE_PROJECT_TYPE if effective_route_is_grease(None, design_space) else None
    # Material records are read from the artifact's own directory, which is where a
    # workspace keeps them. No explicit list is passed, so the scan is what runs.
    materials = load_materials({}, artifact_path) if artifact_path is not None else []
    errors = design_space_errors(design_space, None, None, project_type, materials)
    for field, value in expected_decision_fields(design_space, project_type).items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic design-space policy")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_design_space_artifact.py <artifact.json>")
        return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        schemas = schema_dir()
        loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [error.message for error in Draft202012Validator(loaded["design_space.schema.json"], registry=registry).iter_errors(artifact)]
    if artifact.get("stage") != "DESIGN_SPACE_DEFINED":
        errors.append("stage must be DESIGN_SPACE_DEFINED")
    errors.extend(semantic_errors(artifact, Path(sys.argv[1]).resolve()))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: deterministic design-space artifact conforms to the Stage 4 contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
