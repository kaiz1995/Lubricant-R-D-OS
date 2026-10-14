"""Reject incomplete knowledge-archive input before a knowledge_asset artifact is built.

Step 17 (knowledge-archive) closes a project by landing the six knowledge assets as one
``knowledge_asset`` record at ``KNOWLEDGE_ARCHIVED``. Upstream is ``project.json`` and the
gate is fail-closed: a missing or schema-invalid charter, an unrecordable asset block, an
artifact-level evidence GAP, or a workspace whose artifact names violate the canonical-name
contract all stop the skill before anything is written.

A project that cannot close its knowledge is NOT an input error. The caller records what
exists, the builder derives the status, and the record stays ``DRAFT_KNOWLEDGE`` with the
shortfall printed as a NOTE. Inventing an asset to make the record close is the one failure
this preflight exists to prevent (red line NO Synthetic Closure / NO Invented Assets).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from knowledge_archive_policy import (
    ASSET_ENTRY_FIELDS,
    ASSET_KEYS,
    ASSET_STATUSES,
    EVIDENCE_STATUSES,
    EVIDENCE_SCOPES,
    INPUT_FIELDS,
    QUALIFICATION_VALUES,
    QUALIFIED_ASSET_FIELDS,
    QUALIFIED_ASSET_KEY,
    STAGE,
    asset_requirement,
    cost_criterion_errors,
    has_gap,
    has_text,
    is_absence_marker,
    present_keys,
    status_notes,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "project.schema.json", "knowledge_asset.schema.json")
UPSTREAM_FIELDS = {"project_artifact"}
ABSENCE_HINT = "record an explicit absence marker such as MISSING when no document exists"


def _ensure_naming_checker_importable() -> bool:
    """Probe the shared naming checker in both layouts (reference-material precedent).

    Repository layout: the module lives in the pack-level ``scripts/`` tree.
    Deployed layout: the installer copies it beside this skill's scripts once the LEAD
    registers the skill. If neither candidate holds the file the preflight still runs; the
    naming contract is then unenforced here, exactly like knowledge_retrieval.
    """
    for candidate in (SKILL_ROOT / "scripts", SKILL_ROOT.parents[1] / "scripts"):
        if (candidate / "check_artifact_naming.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return True
    return False


_NAMING_AVAILABLE = _ensure_naming_checker_importable()

if _NAMING_AVAILABLE:
    import check_artifact_naming  # noqa: E402


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def workspace_naming_errors(input_path: Path) -> list[str]:
    """Enforce the canonical-name contract on the workspace holding the input.

    The request file lives in the workspace root, so ``input_path.parent`` is the
    workspace. A bare staging directory without ``project.json`` is not treated as a
    workspace (keeps ad-hoc preflight invocations working). A mangled artifact name is
    invisible to the stage-gate panel, so every violation here is a HOLD.
    """
    if not _NAMING_AVAILABLE:
        return []
    workspace = input_path.parent
    if not (workspace / "project.json").is_file():
        return []
    try:
        _, violations = check_artifact_naming.check_workspace(str(workspace))
    except OSError:
        return []
    return [f"workspace naming: {violation}" for violation in violations]


def upstream_errors(path: Path) -> tuple[list[str], dict | None]:
    """Validate the upstream project charter: schema, stage, status and decision."""
    try:
        schemas = {name: json.loads((schema_dir() / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"project_artifact cannot be read: {error}"], None
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [
        f"project_artifact: {error.message}"
        for error in Draft202012Validator(schemas["project.schema.json"], registry=registry).iter_errors(artifact)
    ]
    if not errors and (
        artifact.get("stage") != "PROJECT_DEFINED"
        or artifact.get("status") != "ACTIVE"
        or artifact.get("decision") != "GO"
    ):
        errors.append("project_artifact must be PROJECT_DEFINED, ACTIVE, and GO")
    return errors, artifact if not errors else None


def asset_entry_errors(value: object, key: str, workspace: Path | None = None,
                       project_id: str | None = None) -> list[str]:
    label = f"knowledge_assets.{key}"
    if not isinstance(value, dict):
        return [label]
    fields = QUALIFIED_ASSET_FIELDS if key == QUALIFIED_ASSET_KEY else ASSET_ENTRY_FIELDS
    unknown = sorted(set(value) - fields)
    missing = sorted(set(ASSET_ENTRY_FIELDS) - set(value))
    if unknown or missing:
        return [f"{label}: unexpected={unknown or 'none'} missing={missing or 'none'}"]
    errors: list[str] = []
    reference = value.get("artifact_reference")
    if not has_text(reference):
        errors.append(f"{label}.artifact_reference must be a non-empty string; {ABSENCE_HINT}")
    if not isinstance(value.get("present"), bool):
        errors.append(f"{label}.present must be a boolean")
    if key == QUALIFIED_ASSET_KEY:
        qualification = value.get("qualification")
        if qualification is not None and qualification not in QUALIFICATION_VALUES:
            errors.append(f"{label}.qualification must be QUALIFIED, PROVISIONAL, or UNQUALIFIED")
        if qualification is not None and not has_text(value.get("qualification_reference")):
            errors.append(f"{label}.qualification_reference is required whenever a qualification is recorded")
    # E7=A resolution runs AFTER the cost-criterion check (which is a whole-request rule
    # in archive_errors), so a reference that reads as a cost CTQ is reported as that,
    # not merely as an unresolvable path.
    if has_text(reference) and workspace is not None and not errors:
        if value.get("present") is True:
            errors.extend(asset_reference_errors(reference, label, workspace, project_id, key))
        elif value.get("present") is False and not is_absence_marker(reference):
            errors.append(
                f"{label}.artifact_reference {reference!r} records an absence, so it must be one of the "
                f"explicit absence markers ({ABSENCE_HINT})"
            )
    return errors


def asset_reference_errors(reference: str, label: str, workspace: Path,
                           project_id: str | None, key: str) -> list[str]:
    """Resolve one present:true reference and check what it points at (E7=A)."""
    path = Path(reference)
    if not path.is_absolute():
        path = workspace / path
    if not path.is_file():
        return [
            f"{label}.artifact_reference {reference!r} does not resolve to a file in the workspace: a present "
            "asset must cite the record itself, not a document number"
        ]
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label}.artifact_reference {reference!r} cannot be read as a record: {error}"]
    if not isinstance(record, dict) or not has_text(record.get("artifact_type")):
        return [
            f"{label}.artifact_reference {reference!r} is not an artifact record: a cited asset must carry an "
            "artifact_type and a stage"
        ]
    expected_type, allowed_stages = asset_requirement(key)
    if record.get("artifact_type") != expected_type:
        return [
            f"{label}.artifact_reference {reference!r} carries artifact_type {record.get('artifact_type')!r}, "
            f"but this asset must cite a {expected_type!r} record"
        ]
    if record.get("stage") not in allowed_stages:
        return [
            f"{label}.artifact_reference {reference!r} carries stage {record.get('stage')!r}, which is not one "
            f"of the stages this asset may cite ({', '.join(allowed_stages)})"
        ]
    if project_id is not None and record.get("project_id") not in (None, project_id):
        return [
            f"{label}.artifact_reference {reference!r} belongs to project {record.get('project_id')!r}, not to "
            f"this project {project_id!r}: an asset may only be cited from its own project"
        ]
    return []


def knowledge_assets_errors(value: object, workspace: Path | None = None,
                            project_id: str | None = None) -> list[str]:
    if not isinstance(value, dict):
        return ["knowledge_assets must be the six-asset object"]
    unknown = sorted(set(value) - set(ASSET_KEYS))
    missing = sorted(set(ASSET_KEYS) - set(value))
    if unknown or missing:
        return [f"knowledge_assets must contain exactly the six assets; unexpected={unknown or 'none'} missing={missing or 'none'}"]
    errors: list[str] = []
    for key in ASSET_KEYS:
        errors.extend(asset_entry_errors(value.get(key), key, workspace, project_id))
    return errors


def evidence_errors(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["evidence"]
    errors: list[str] = []
    for index, item in enumerate(value):
        label = f"evidence[{index}]"
        if not isinstance(item, dict) or set(item) != {"evidence_id", "statement", "source", "status"}:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"{label}.status")
    return errors


def archive_errors(data: dict, workspace: Path | None = None,
                   project_id: str | None = None) -> list[str]:
    errors: list[str] = []
    if not has_text(data.get("project_artifact")):
        errors.append("project_artifact")
    if data.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("evidence_scope must be SYNTHETIC or PHYSICAL")
    if data.get("asset_status") not in ASSET_STATUSES:
        errors.append("asset_status must be DRAFT_KNOWLEDGE or CLOSED_KNOWLEDGE")
    # Cost is a whole-request rule and runs FIRST: a reference that reads as a cost CTQ
    # must be reported as that error, not merely as a path that fails to resolve (E7=A
    # resolution runs below, on the entries the cost check cleared).
    assets = data.get("knowledge_assets")
    if isinstance(assets, dict):
        references = [
            entry.get("artifact_reference")
            for entry in assets.values()
            if isinstance(entry, dict)
        ]
        errors.extend(cost_criterion_errors(references))
    errors.extend(knowledge_assets_errors(assets, workspace, project_id))
    errors.extend(evidence_errors(data.get("evidence")))
    if not errors and has_gap(data):
        errors.append(
            "evidence contains GAP; a missing knowledge asset belongs on its asset entry as present=false, "
            "not on the request as an open gap"
        )
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != INPUT_FIELDS:
        extra = sorted(set(data) - INPUT_FIELDS)
        missing = sorted(INPUT_FIELDS - set(data))
        return [
            "input must contain only the knowledge-archive input fields; "
            f"unexpected={extra or 'none'} missing={missing or 'none'}"
        ]
    errors: list[str] = []
    project_path = resolved_path(data.get("project_artifact"), input_path)
    project_id: str | None = None
    if project_path is None:
        errors.append("project_artifact")
    else:
        upstream_problems, project = upstream_errors(project_path)
        errors.extend(upstream_problems)
        if isinstance(project, dict):
            project_id = project.get("project_id")
    errors.extend(archive_errors(data, input_path.parent, project_id))
    errors.extend(workspace_naming_errors(input_path))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_knowledge_archive.py <input.json>")
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
    present = present_keys(data["knowledge_assets"])
    print(f"READY: input can form one {STAGE} knowledge_asset record ({len(present)}/6 assets present)")
    for line in status_notes(data["asset_status"], data["knowledge_assets"], data["evidence_scope"]):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
