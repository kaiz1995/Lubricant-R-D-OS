"""Reject incomplete reference-material input before a reference artifact is built.

Stage 4 (reference-material) exists because Stage 5 cannot prove that a test stand
separates a good sample from a bad one unless both exist as physical objects. Upstream
is ``project.json`` and this gate is fail-closed: a missing or schema-invalid charter,
an unrecordable dossier, a request that admits an artifact-level evidence GAP, or a
workspace whose artifact names violate the canonical-name contract all stop the skill
before anything is written.

An ABSENT reference material is not an input error. The caller records the side with
``resolution: UNRESOLVED`` (identity fields carry an explicit absence marker such as
``MISSING``), the record is still built, and the missing side is carried downstream as
``DISCRIMINATION_EVIDENCE_INCOMPLETE``. Inventing a sample to make the input look
valid is the one failure this preflight exists to prevent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from reference_material_policy import (
    DOSSIER_INPUT_FIELDS,
    EVIDENCE_FIELDS,
    EVIDENCE_SCOPES,
    EVIDENCE_STATUSES,
    HISTORY_ITEM_FIELDS,
    INPUT_FIELDS,
    RESOLVED,
    RESOLUTIONS,
    RUNG_ORDER,
    SIDES,
    TIERS,
    derive_downstream_flag,
    has_gap,
    has_text,
    input_notes,
    recorded_side,
    resolved_count,
    tier_from_input,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "project.schema.json", "reference.schema.json")
UPSTREAM_SCHEMA = "project.schema.json"
UPSTREAM_STAGE = "PROJECT_DEFINED"
UPSTREAM_INVARIANT = "project_artifact must be PROJECT_DEFINED, ACTIVE, and GO"
ROUTED_PROJECT_TYPE = "PRECISION_GREASE_DEV"
ABSENCE_HINT = "record an explicit absence marker such as MISSING when no document exists"
IDENTITY_FIELDS = ("reference_id", "material_identity", "formula_identity", "storage_sop", "safety_reference")


def _ensure_naming_checker_importable() -> bool:
    """Probe the shared naming checker in both layouts (gate-review precedent).

    Repository layout: the module lives in the pack-level ``scripts/`` tree.
    Deployed layout: the installer copies it beside this skill's scripts
    (install_domain_skill.py maps reference-material -> check_artifact_naming.py).
    If neither candidate holds the file the preflight still runs; the naming
    contract is then unenforced here, exactly like knowledge_retrieval.
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


def evidence_errors(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["evidence"]
    errors: list[str] = []
    for index, item in enumerate(value):
        label = f"evidence[{index}]"
        if not isinstance(item, dict) or not set(item) <= EVIDENCE_FIELDS:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"{label}.status")
    return errors


def history_item_errors(value: object, label: str) -> list[str]:
    """Structural errors only. A recordable-but-unsupported item is NOT an error here.

    An item that is missing its mechanism binding, or that carries an absence marker
    where evidence should be, cannot be written into the artifact (the reference
    contract requires both fields non-empty). Rather than invent a mechanism - or
    refuse to record the truth - the builder drops that item, keeps the dossier, and
    records it UNRESOLVED. Only an item that is not an object, or that carries unknown
    fields, makes the whole request unrecordable.
    """
    if not isinstance(value, list):
        return [f"{label} must be an array"]
    errors: list[str] = []
    for index, item in enumerate(value):
        item_label = f"{label}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_label} must be an object")
            continue
        unknown = sorted(set(item) - HISTORY_ITEM_FIELDS)
        if unknown:
            errors.append(f"{item_label}: unexpected={unknown}")
    return errors


def dossier_errors(value: object, side: str, index: int) -> list[str]:
    label = f"{side}[{index}]"
    if not isinstance(value, dict):
        return [label]
    unknown = sorted(set(value) - DOSSIER_INPUT_FIELDS)
    missing = sorted(DOSSIER_INPUT_FIELDS - set(value))
    if unknown or missing:
        return [f"{label}: unexpected={unknown or 'none'} missing={missing or 'none'}"]
    errors: list[str] = []
    for field in IDENTITY_FIELDS:
        if not has_text(value.get(field)):
            errors.append(f"{label}.{field} must be a non-empty string; {ABSENCE_HINT}")
    resolution = value.get("resolution")
    if resolution not in RESOLUTIONS:
        errors.append(f"{label}.resolution must be RESOLVED or UNRESOLVED")
    rung = value.get("selection_rung")
    if rung not in TIERS:
        errors.append(f"{label}.selection_rung must be DIRECT_HISTORY, LONG_RUN_NO_EVENT, or UNRESOLVED")
    elif resolution == RESOLVED and rung not in RUNG_ORDER:
        errors.append(
            f"{label}.selection_rung must be DIRECT_HISTORY or LONG_RUN_NO_EVENT to claim RESOLVED; "
            "the ladder ends at UNRESOLVED"
        )
    errors.extend(history_item_errors(value.get("history_evidence"), f"{label}.history_evidence"))
    return errors


def reference_errors(data: dict) -> list[str]:
    errors: list[str] = []
    if not has_text(data.get("reference_id")):
        errors.append("reference_id")
    if data.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("evidence_scope must be SYNTHETIC or PHYSICAL")
    for side in SIDES:
        dossiers = data.get(side)
        if not isinstance(dossiers, list):
            errors.append(f"{side} must be an array of dossiers (an empty array is an open recording)")
            continue
        for index, dossier in enumerate(dossiers):
            errors.extend(dossier_errors(dossier, side, index))
    errors.extend(evidence_errors(data.get("evidence")))
    if not errors and has_gap(data.get("evidence")):
        errors.append(
            "evidence contains GAP; a missing reference material belongs on the dossier as resolution "
            "UNRESOLVED, not on the request as an open gap"
        )
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != INPUT_FIELDS:
        extra = sorted(set(data) - INPUT_FIELDS)
        missing = sorted(INPUT_FIELDS - set(data))
        return [
            "input must contain only the reference-material input fields; "
            f"unexpected={extra or 'none'} missing={missing or 'none'}"
        ]
    errors: list[str] = []
    project_path = resolved_path(data.get("project_artifact"), input_path)
    if project_path is None:
        errors.append("project_artifact")
    else:
        upstream_problems, _ = upstream_errors(project_path)
        errors.extend(upstream_problems)
    errors.extend(reference_errors(data))
    errors.extend(workspace_naming_errors(input_path))
    return errors


def project_type_notes(project: dict | None) -> list[str]:
    """A non-precision route is legal but worth saying out loud (never a HOLD)."""
    if not isinstance(project, dict):
        return []
    project_type = project.get("project_type")
    if project_type == ROUTED_PROJECT_TYPE:
        return []
    return [
        f"NOTE: project_type={project_type} is not {ROUTED_PROJECT_TYPE}; "
        "stage REFERENCE_MATERIAL_RESOLVED is not on that route"
    ]


def gate_lines(data: dict) -> list[str]:
    """The release rule, computed deterministically so the caller sees it up front."""
    known_good = recorded_side(data.get("known_good"), "known_good")
    known_bad = recorded_side(data.get("known_bad"), "known_bad")
    resolved_good, total_good = resolved_count(known_good)
    resolved_bad, total_bad = resolved_count(known_bad)
    flag = derive_downstream_flag(known_bad)
    tier = tier_from_input(data.get("known_good"), data.get("known_bad"))
    counts = f"known_good {resolved_good}/{total_good} RESOLVED, known_bad {resolved_bad}/{total_bad} RESOLVED"
    if resolved_good or resolved_bad:
        return [f"GATE: at least one side RESOLVED ({counts}) -> decision GO; tier={tier}; downstream_flag={flag}"]
    return [
        f"GATE: no side RESOLVED ({counts}) -> decision HOLD; tier={tier}; downstream_flag={flag}; "
        "Stage 5 must not proceed on this reference set"
    ]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_reference_material.py <input.json>")
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
    _, project = upstream_errors(resolved_path(data["project_artifact"], input_path))
    print("READY: input can form one REFERENCE_MATERIAL_RESOLVED record")
    for line in gate_lines(data):
        print(line)
    for line in project_type_notes(project):
        print(line)
    for line in input_notes(data):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
