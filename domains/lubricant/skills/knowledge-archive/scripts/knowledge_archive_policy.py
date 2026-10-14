"""Deterministic knowledge-archive policy: the six-asset closure rule.

Step 17 (knowledge-archive) closes a project by landing the six knowledge assets the
redesign names - recommended formula, feasible design space, critical failure
boundaries, evidence package, material knowledge, model - as one ``knowledge_asset``
artifact at ``KNOWLEDGE_ARCHIVED``. Before this skill existed the schema had no producer
at all, so the retrieval index was permanently empty; this module is the single place
where the closure status is judged, and it is shared by the preflight, the builder, and
the validator so the three scripts cannot disagree.

Four rules, all fail-closed:

1. THE STATUS IS DERIVED, NOT CLAIMED. ``CLOSED_KNOWLEDGE`` is legal only when all six
   assets are present AND the evidence package is present and QUALIFIED. Anything short
   of that caps the record at ``DRAFT_KNOWLEDGE``. The builder downgrades a larger claim
   (it never upgrades one), and the validator re-derives the rule from the frozen
   artifact, so a hand edit cannot turn five assets plus a promise into a closed record.
   Stated boundary: a DRAFT record with all six assets present is legal - draft is always
   the safe direction - and the validator accepts it as long as the CLOSED case stays
   inside the rule.

2. A SYNTHETIC PROJECT CAN NEVER CLOSE. Synthetic evidence caps the record at
   ``DRAFT_KNOWLEDGE`` and force-marks it ``SYNTHETIC_DEMO_ONLY`` (red line NO Synthetic
   Closure). The marker is derived from the evidence scope, never supplied.

3. COST NEVER ENTERS A CTQ CRITERION (redesign section 6.3). Cost is a constraint
   (step 6 filter / step 14 constraint / step 16 ceiling check), never a criterion, and a
   knowledge record that archived a cost criterion would freeze that error into reuse.
   The archive therefore refuses an asset reference that declares itself a cost CTQ:
   the identity must not read as a cost criterion (``CTQ-COST``-style or a cost keyword),
   because the correct place for cost is the cost ceiling, not the criteria chain.

4. THE CLOSURE DECISION IS ``GO``, NOT ``FREEZE``. ``GO``/``HOLD`` live in the common
   decision vocabulary and say "this record may be retained for reuse" / "it may not".
   ``FREEZE`` is a different thing in this system - the signed ``APPLIED -> FROZEN``
   gate action - and step 20 does not sit at that gate, so the archive never claims it
   (the same wording rule for CLOSE, which requires ``FROZEN -> CLOSED``).
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SKILL_ROOT = Path(__file__).resolve().parents[1]

ASSET_KEYS = (
    "recommended_formula",
    "feasible_design_space",
    "critical_failure_boundaries",
    "evidence_package",
    "material_knowledge",
    "model",
)
QUALIFIED_ASSET_KEY = "evidence_package"
QUALIFICATION_VALUES = ("QUALIFIED", "PROVISIONAL", "UNQUALIFIED")
ASSET_STATUSES = ("DRAFT_KNOWLEDGE", "CLOSED_KNOWLEDGE")
EVIDENCE_SCOPES = ("SYNTHETIC", "PHYSICAL")
EVIDENCE_STATUSES = ("OBSERVED", "ASSUMED", "GAP")
SYNTHETIC_MARKER = "SYNTHETIC_DEMO_ONLY"
STAGE = "KNOWLEDGE_ARCHIVED"
ASSET_ENTRY_FIELDS = {"artifact_reference", "present"}
QUALIFIED_ASSET_FIELDS = {"artifact_reference", "present", "qualification_reference", "qualification"}
INPUT_FIELDS = {"project_artifact", "asset_status", "knowledge_assets", "evidence_scope", "evidence"}
# Cost-as-CTQ detection: an identity token check, deliberately narrow so it never
# fires on an ordinary criterion. It looks for a cost term inside a CTQ identity.
COST_TERMS = ("COST", "COST_TARGET", "价格", "成本", "PRICE")
STAGE_CONSTANT_IN_PROJECT = "PROJECT_DEFINED"

# E7=A: an asset reference is a WORKSPACE FILE reference. ``present=false`` is the only
# way to record an absence, and it must say so with one of these explicit markers - a
# fabricated (or leftover) document number is what this gate exists to refuse.
ABSENCE_MARKERS = ("MISSING", "NOT_SUPPLIED")
ABSENCE_HINT = "record an explicit absence marker such as MISSING when no document exists"

# Which record actually carries each asset, and at which stage it may be cited. The
# reference is resolved and checked against this table, so a document number, a
# dangling file name, or the wrong kind of record is a HOLD rather than a claim.
# ``recommended_formula`` cites the step-16 optimization record: it registers the
# optimization request and the non-inferiority criterion, and the archive never claims
# a computed recommendation (E4=B). No stage value here depends on the optional
# renaming item (H-1 optional 1), which is deliberately not part of this change.
ASSET_REQUIREMENTS = {
    "recommended_formula": ("optimization", ("NON_INFERIORITY_PASSED",)),
    "feasible_design_space": ("design_space", ("DESIGN_SPACE_DEFINED",)),
    "critical_failure_boundaries": ("failure_ctq", ("FAILURE_CTQ_DEFINED",)),
    "evidence_package": ("application", ("APPLIED",)),
    "material_knowledge": ("material", ("DESIGN_SPACE_DEFINED",)),
    "model": ("model", ("MODEL_BUILT",)),
}
# The evidence package's qualification reference is the gate record that verified the
# chain, so it must resolve as well and be that kind of record.
QUALIFICATION_REQUIREMENT = ("gate", ("VERIFIED",))


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_absence_marker(value: object) -> bool:
    """True when a reference records an absence instead of naming a workspace file."""
    return has_text(value) and value.strip() in ABSENCE_MARKERS


def asset_requirement(key: str) -> tuple[str, tuple[str, ...]]:
    """The (artifact_type, legal stages) a knowledge asset key must resolve to."""
    return ASSET_REQUIREMENTS[key]


def has_gap(container: dict) -> bool:
    evidence = container.get("evidence")
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("status") == "GAP" for item in evidence
    )


def asset_entries(value: object) -> dict:
    """The ``knowledge_assets`` block as a plain mapping (empty when malformed)."""
    return value if isinstance(value, dict) else {}


def present_keys(knowledge_assets: object) -> list[str]:
    """The six asset keys recorded ``present: true``, in canonical order."""
    assets = asset_entries(knowledge_assets)
    return [key for key in ASSET_KEYS if isinstance(assets.get(key), dict) and assets[key].get("present") is True]


def missing_keys(knowledge_assets: object) -> list[str]:
    """The six asset keys NOT recorded ``present: true``, in canonical order."""
    present = set(present_keys(knowledge_assets))
    return [key for key in ASSET_KEYS if key not in present]


def derived_assets(knowledge_assets: object, workspace, project_id: object) -> dict:
    """The six entries with ``present`` replaced by its derived value (E7=A).

    The declared flag is not an authority: the builder records the presence the
    workspace justifies, so the archived record cannot carry a ``present: true`` whose
    reference names nothing. A citation that resolves with the flag declared false is
    the one disagreement that survives the preflight; it is recorded as present and
    made audible as a NOTE (never a HOLD), so a request stays readable.
    """
    assets = asset_entries(knowledge_assets)
    resolved: dict = {}
    for key in ASSET_KEYS:
        entry = assets.get(key)
        if not isinstance(entry, dict):
            resolved[key] = entry
            continue
        resolved[key] = {**entry, "present": derived_present(entry, key, workspace, project_id)}
    return resolved


def derived_present(entry: object, key: str, workspace, project_id: object) -> bool:
    """True only when the entry cites a real, matching record of this project.

    An absence marker is absence. A reference that does not resolve is absence too:
    ``present`` is derived from the workspace, never simply believed.
    """
    if not isinstance(entry, dict):
        return False
    reference = entry.get("artifact_reference")
    if not has_text(reference) or is_absence_marker(reference):
        return False
    artifact_type, stages = ASSET_REQUIREMENTS[key]
    label = f"knowledge_assets.{key}.artifact_reference"
    return not reference_file_errors(label, reference, artifact_type, stages, workspace, project_id)


def presence_notes(knowledge_assets: object, workspace, project_id: object) -> list[str]:
    """NOTE lines where the declared ``present`` flag disagrees with the derivation."""
    assets = asset_entries(knowledge_assets)
    notes: list[str] = []
    for key in ASSET_KEYS:
        entry = assets.get(key)
        if not isinstance(entry, dict):
            continue
        declared = entry.get("present")
        if not isinstance(declared, bool):
            continue
        derived = derived_present(entry, key, workspace, project_id)
        if declared != derived:
            notes.append(
                f"NOTE: knowledge_assets.{key}.present was declared {declared!r} but the workspace derives "
                f"{derived!r}; the record uses the derived value"
            )
    return notes


def reference_errors(entry: object, key: str, workspace, project_id: object) -> list[str]:
    """What is wrong with one asset entry's citation, judged against the workspace.

    ``present=false`` records an absence: an absence marker is accepted, and a citation
    that still resolves is accepted too - the flag is not the authority, that
    disagreement is a NOTE (see :func:`presence_notes`). A token that names no record at
    all - a document number, a dangling name - is a HOLD, because a citation nobody can
    read is the one failure this gate exists to prevent. ``present=true`` must resolve
    to a real workspace artifact: canonical or suffixed file name, the file exists,
    valid JSON, valid against its own contract, and carrying the artifact type, stage
    and ``project_id`` this asset requires.
    """
    label = f"knowledge_assets.{key}.artifact_reference"
    if not isinstance(entry, dict):
        return []
    reference = entry.get("artifact_reference")
    if not has_text(reference):
        return [f"{label} must be a non-empty string; {ABSENCE_HINT}"]
    if entry.get("present") is False and is_absence_marker(reference):
        return []
    artifact_type, stages = ASSET_REQUIREMENTS[key]
    return reference_file_errors(label, reference, artifact_type, stages, workspace, project_id)


def qualification_errors(package: object, workspace, project_id: object) -> list[str]:
    """The evidence package's qualification reference, resolved and checked the same way."""
    if not isinstance(package, dict):
        return []
    reference = package.get("qualification_reference")
    if not has_text(reference):
        return []
    artifact_type, stages = QUALIFICATION_REQUIREMENT
    label = f"knowledge_assets.{QUALIFIED_ASSET_KEY}.qualification_reference"
    return reference_file_errors(label, reference, artifact_type, stages, workspace, project_id)


def reference_file_errors(label, reference, artifact_type, stages, workspace, project_id) -> list[str]:
    """Resolve one file citation and check it against the artifact it must name."""
    name = Path(reference).name
    if name != reference or not reference.endswith(".json"):
        return [
            f"{label} {reference!r} is not a workspace file: cite the file name of the record that carries "
            "this asset (canonical '<type>.json' or suffixed '<type>-<project_id>-<id>.json'), not a "
            "document number"
        ]
    stem = name[: -len(".json")]
    if stem != artifact_type and not stem.startswith(artifact_type + "-"):
        return [
            f"{label} {reference!r} is not the name of a {artifact_type!r} record: legal names are "
            f"'{artifact_type}.json' or '{artifact_type}-<project_id>-<id>.json'"
        ]
    path = referenced_path(reference, workspace)
    if path is None or not path.is_file():
        return [f"{label} {reference!r} is not a workspace file: no such record beside the request"]
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} {reference!r} cannot be read as JSON: {error}"]
    if not isinstance(artifact, dict):
        return [f"{label} {reference!r} is not a JSON object"]
    actual_type = artifact.get("artifact_type")
    if actual_type != artifact_type:
        return [
            f"{label} {reference!r} resolves to artifact_type {actual_type!r}, but this asset requires "
            f"{artifact_type!r}"
        ]
    actual_stage = artifact.get("stage")
    if actual_stage not in stages:
        return [
            f"{label} {reference!r} is at stage {actual_stage!r}, but this asset requires one of "
            + ", ".join(stages)
        ]
    actual_project = artifact.get("project_id")
    if actual_project != project_id:
        return [f"{label} {reference!r} belongs to project {actual_project!r}, not to this project {project_id!r}"]
    return _schema_errors(path, artifact, artifact_type)


def referenced_path(reference: object, workspace) -> Path | None:
    """The workspace file a citation names (absolute citations are honoured).

    Mirrors the resolution rule the preflight uses for ``project_artifact``
    (``input_path.parent / value``); the workspace is passed in explicitly so this
    module stays pure of the preflight's own path handling.
    """
    if not has_text(reference):
        return None
    path = Path(reference)
    return path if path.is_absolute() else Path(workspace) / path


def schema_dir() -> Path:
    """Where this skill's own authority schemas live (pack layout, then deployed).

    Mirrors ``preflight_knowledge_archive.schema_dir`` but is defined here too so the
    policy module stays importable without the preflight (the preflight imports this
    module, never the other way round).
    """
    canonical = SKILL_ROOT.parents[1] / "schemas"
    if (canonical / "common.schema.json").is_file():
        return canonical
    return SKILL_ROOT / "references"


def _schema_errors(path: Path, artifact: dict, artifact_type: str) -> list[str]:
    """Validate a resolved record against its own contract (fail-closed)."""
    schema_name = f"{artifact_type}.schema.json"
    try:
        schemas = {
            "common.schema.json": json.loads((schema_dir() / "common.schema.json").read_text(encoding="utf-8")),
            schema_name: json.loads((schema_dir() / schema_name).read_text(encoding="utf-8")),
        }
    except (OSError, json.JSONDecodeError) as error:
        return [f"{path.name} cannot be checked against {schema_name}: {error}"]
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator(schemas[schema_name], registry=registry)
    return [
        f"{path.name} is not a valid {artifact_type}: {error.message}" for error in validator.iter_errors(artifact)
    ]


def evidence_package_qualified(knowledge_assets: object) -> bool:
    package = asset_entries(knowledge_assets).get(QUALIFIED_ASSET_KEY)
    return (
        isinstance(package, dict)
        and package.get("present") is True
        and package.get("qualification") == "QUALIFIED"
        and has_text(package.get("qualification_reference"))
    )


def derived_status(knowledge_assets: object, evidence_scope: object) -> str:
    """The highest legal asset status for these assets and this evidence scope."""
    if evidence_scope == "SYNTHETIC":
        return "DRAFT_KNOWLEDGE"
    if missing_keys(knowledge_assets) or not evidence_package_qualified(knowledge_assets):
        return "DRAFT_KNOWLEDGE"
    return "CLOSED_KNOWLEDGE"


def resolved_status(claimed: object, knowledge_assets: object, evidence_scope: object) -> str:
    """Downgrade-only resolution of the caller's claim against the derived status."""
    if claimed == "CLOSED_KNOWLEDGE" and derived_status(knowledge_assets, evidence_scope) == "CLOSED_KNOWLEDGE":
        return "CLOSED_KNOWLEDGE"
    return "DRAFT_KNOWLEDGE"


def status_notes(claimed: object, knowledge_assets: object, evidence_scope: object) -> list[str]:
    """Audible NOTE lines wherever the record did not reach the caller's claim."""
    resolved = resolved_status(claimed, knowledge_assets, evidence_scope)
    if claimed != "CLOSED_KNOWLEDGE" or resolved == "CLOSED_KNOWLEDGE":
        return []
    notes: list[str] = []
    if evidence_scope == "SYNTHETIC":
        notes.append(
            "NOTE: a SYNTHETIC project can never reach CLOSED_KNOWLEDGE; the record is capped at "
            "DRAFT_KNOWLEDGE and force-marked SYNTHETIC_DEMO_ONLY (NO Synthetic Closure)"
        )
        return notes
    missing = missing_keys(knowledge_assets)
    if missing:
        notes.append(
            "NOTE: CLOSED_KNOWLEDGE requires all six assets present; missing "
            + ", ".join(missing)
            + " -> DRAFT_KNOWLEDGE"
        )
    package = asset_entries(knowledge_assets).get(QUALIFIED_ASSET_KEY)
    if not evidence_package_qualified(knowledge_assets):
        qualification = package.get("qualification") if isinstance(package, dict) else None
        notes.append(
            "NOTE: CLOSED_KNOWLEDGE requires a present evidence package whose qualification is QUALIFIED "
            f"with a qualification_reference (got {qualification!r}) -> DRAFT_KNOWLEDGE"
        )
    return notes


def cost_criterion_errors(value: object) -> list[str]:
    """Asset references that declare themselves a cost CTQ.

    Cost is a constraint, never a criterion: a cost term inside a CTQ identity means the
    project built its criteria chain around price, which is exactly the error redesign
    section 6.3 forbids. Only CTQ identities are inspected; asset references that are not
    CTQs are never matched.
    """
    references = value if isinstance(value, list) else []
    errors: list[str] = []
    for index, reference in enumerate(references):
        if not has_text(reference):
            continue
        token = reference.upper()
        if "CTQ" not in token:
            continue
        if any(term.upper() in token for term in COST_TERMS):
            errors.append(
                f"asset_reference[{index}] {reference!r} reads as a cost CTQ criterion: cost must never appear "
                "as a CTQ criterion; it belongs in the project's cost ceiling (constraint), not in the criteria chain"
            )
    return errors


def expected_decision_fields(
    knowledge_assets: object, evidence_scope: object, asset_status: object, evidence: object
) -> dict[str, str]:
    """The canonical decision block, recomputed identically by builder and validator.

    Every input is a field of the artifact itself, so the validator can rebuild the whole
    block from the frozen artifact.
    """
    present = present_keys(knowledge_assets)
    missing = missing_keys(knowledge_assets)
    closed = asset_status == "CLOSED_KNOWLEDGE"
    gap = has_gap({"evidence": evidence})
    decision = "GO" if closed and not gap else "HOLD"
    if evidence_scope == "SYNTHETIC":
        scope_prefix = (
            "Synthetic test fixture / NOT_FOR_PHYSICAL_EXECUTION: this record cannot authorize stage "
            "advancement. "
        )
    else:
        scope_prefix = ""
    return {
        "decision_question": "Are the six knowledge assets complete and qualified enough to close this project's knowledge?",
        "hypothesis": (
            "A project that lands all six knowledge assets with a QUALIFIED evidence package can be archived as "
            "CLOSED_KNOWLEDGE and retrieved by later projects; anything short of that stays a draft."
        ),
        "uncertainty": (
            f"{scope_prefix}asset_status={asset_status}; {len(present)}/6 assets present. The archive records the "
            "assets the caller supplied; it does not re-verify their contents, and a DRAFT record carries no reuse "
            "guarantee beyond what its asset references state."
        ),
        "decision_rule": (
            "CLOSED_KNOWLEDGE is legal only when all six assets are present and the evidence package is present "
            "with qualification QUALIFIED and a qualification_reference; otherwise the record is capped at "
            "DRAFT_KNOWLEDGE. A SYNTHETIC project can never close. Cost never enters a CTQ criterion."
        ),
        "result": (
            f"knowledge archive recorded {len(present)}/6 assets as present"
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + f"; asset_status={asset_status}."
        ),
        "decision": decision,
        "next_action": (
            "Retain the CLOSED_KNOWLEDGE archive for retrieval by later projects; it does not freeze or release "
            "the design by itself."
            if closed
            else "Retain the DRAFT_KNOWLEDGE archive and complete the missing assets or the QUALIFIED evidence "
            "package before claiming closure."
        ),
    }
