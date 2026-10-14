"""Reject incomplete material-registration input before a material artifact is built.

The design space (step 6) requires every material-bearing variable to reference a
``material`` record and refuses a reference that does not resolve to one. Until this
skill shipped, nothing produced those records: the only way a design space could be
built was to place the material files by hand. This preflight closes that gap.

The request is the charter, the evidence scope, the artifact-level evidence, and one
``material`` block. The block is checked STRUCTURALLY here - identity, chemistry,
properties, cost - rather than through the authority schema, because the block is not
yet a complete artifact (it carries no decision block and no stage). The builder
assembles the complete record and the validator checks it against
``schemas/material.schema.json``, which is the one place the full contract is applied.

Fail-closed: an unreadable charter, a missing or invalid upstream, or a malformed
material block stops the skill before anything is written. One rule is deliberately
NOT a refusal: a property the supplier has not supplied is recorded with
``status: GAP`` - on the property entry itself - and the material still enters the
design space. Recording the absence is the honest record; inventing a value is the one
failure this preflight exists to prevent, and an artifact-level evidence GAP is the same
recorded absence, so it is said out loud (a NOTE) rather than refused.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from material_policy import (
    EVIDENCE_SCOPES,
    INPUT_FIELDS,
    evidence_errors,
    gap_property_ids,
    has_gap,
    has_text,
    material_shape_errors,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "project.schema.json")
UPSTREAM_SCHEMA = "project.schema.json"
UPSTREAM_STAGE = "PROJECT_DEFINED"
UPSTREAM_INVARIANT = "project_artifact must be PROJECT_DEFINED, ACTIVE, and GO"


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def upstream_errors(path: Path) -> tuple[list[str], dict | None]:
    """Validate the upstream project charter: schema, stage, status and decision."""
    try:
        schemas = schema_dir()
        common = json.loads((schemas / "common.schema.json").read_text(encoding="utf-8"))
        project = json.loads((schemas / UPSTREAM_SCHEMA).read_text(encoding="utf-8"))
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"project_artifact cannot be read: {error}"], None
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    registry = registry.with_resource(project["$id"], Resource.from_contents(project))
    errors = [
        f"project_artifact: {error.message}"
        for error in Draft202012Validator(project, registry=registry).iter_errors(artifact)
    ]
    if not errors and (
        artifact.get("stage") != UPSTREAM_STAGE
        or artifact.get("status") != "ACTIVE"
        or artifact.get("decision") != "GO"
    ):
        errors.append(UPSTREAM_INVARIANT)
    return errors, artifact if not errors else None


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != INPUT_FIELDS:
        extra = sorted(set(data) - INPUT_FIELDS)
        missing = sorted(INPUT_FIELDS - set(data))
        return [
            "input must contain only the material-registration input fields; "
            f"unexpected={extra or 'none'} missing={missing or 'none'}"
        ]
    errors: list[str] = []
    project_path = resolved_path(data.get("project_artifact"), input_path)
    if project_path is None:
        errors.append("project_artifact")
    else:
        upstream_problems, _ = upstream_errors(project_path)
        errors.extend(upstream_problems)
    if data.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("evidence_scope must be SYNTHETIC or PHYSICAL")
    errors.extend(evidence_errors(data.get("evidence")))
    errors.extend(material_shape_errors(data.get("material")))
    return errors


def gap_notes(evidence: object, material: object) -> list[str]:
    """The recorded GAPs, said out loud so no gap is ever silent.

    Neither a GAP property entry nor a GAP artifact-level evidence item is an
    error here: both are the recorded absence of a supplier value, and refusing
    the record would push the caller back towards inventing one.
    """
    notes: list[str] = []
    material_id = material.get("material_id") if isinstance(material, dict) else None
    gaps = gap_property_ids(material)
    if gaps:
        notes.append(
            f"NOTE: material {material_id} records {len(gaps)} property GAP(s) ({', '.join(gaps)}); "
            "the gap is recorded, never filled in"
        )
    if has_gap(evidence):
        notes.append(
            f"NOTE: material {material_id} carries an artifact-level evidence item with status GAP; "
            "the recorded absence stays recorded"
        )
    return notes


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_material.py <input.json>")
        return 1
    input_path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, input_path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    print("READY: input can form one material record only")
    for line in gap_notes(data.get("evidence"), data.get("material")):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
