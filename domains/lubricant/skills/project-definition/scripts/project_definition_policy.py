"""Deterministic project-definition policy shared by the preflight and the builder.

Two rules live here, because in both cases a second copy would drift:

1. **The allowed ``project_type`` set is READ from ``project.schema.json``, never
   mirrored here.** ``schemas/project.schema.json`` is the authority for the enum, and
   the seventh route (``PRECISION_GREASE_DEV``) exists there as one enum value. A second
   hardcoded list in the preflight did exactly what duplicated lists do: it kept the six
   oil values and silently refused the route's own charter even though the schema had
   already been widened for it. Reading the enum removes the second list, so a schema
   change and the preflight verdict can no longer disagree. The read is fail-closed: an
   unreadable/malformed enum is a HOLD, never an "accept anything" default, and it never
   degrades into a permissive fallback.

   ``LEGACY_PROJECT_TYPES`` is kept, but only as a *guard* in the other direction: the
   six oil values must still be present in the enum. Shared pack schemas may only gain
   optional properties and enum values (pure-increment rule), so a schema edit that
   dropped an oil type would be a contract violation; the guard turns that into a
   fail-closed HOLD naming the lost type instead of silently breaking an oil route.

2. **The charter's decision fields are derived from the input alone** -- no lookup, no
   project-specific text, no invented numbers. The wording is templated on
   ``project_id`` / ``project_type`` exactly as ``bench_policy.expected_decision_fields``
   templates the bench record, so the builder is deterministic and the decision can be
   recomputed from the same input by any later reader.
"""

from __future__ import annotations

import json
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "project.schema.json")

# The charter stage is a constant MARKER, not a progress field: seven pack preflights
# hard-require ``stage == "PROJECT_DEFINED"`` on the project artifact, and
# scripts/check_artifact_naming.py encodes the same invariant (PROJECT_STAGE_CONSTANT).
# The charter is therefore never advanced past this value.
PROJECT_STAGE = "PROJECT_DEFINED"

# The six oil routes. Listed explicitly so the guard is a lookup and never an implicit
# "anything not in the enum" default.
LEGACY_PROJECT_TYPES = (
    "NEW_PRODUCT",
    "IMPROVEMENT",
    "COST_DOWN",
    "CUSTOMIZATION",
    "EXPLORATION",
    "PROCESS_ROBUSTNESS",
)

# Project-content fields copied verbatim from preflight-valid input into the charter.
# Every name is a declared property of project.schema.json (the artifact/decision fields
# the builder sets itself are excluded), so a copied field can never trip the schema's
# unevaluatedProperties. Order here is the artifact's field order.
PROJECT_FIELDS = (
    "project_name",
    "project_type",
    "product_family",
    "business_objective",
    "technical_objective",
    "hard_constraints",
    "target_cost",
    "cost_ceiling",
    "cost_basis_reason",
    "benchmark_products",
    "benchmark_waiver_reason",
    "success_criteria",
    "risk_class",
    "owner",
)

# project.schema.json#/$defs/artifact.evidence items (common.schema.json evidence_item).
# The input key is source_evidence; this is the mapping's target shape.
EVIDENCE_FIELDS = ("evidence_id", "statement", "source", "status", "claim_class")
INPUT_EVIDENCE_FIELD = "source_evidence"


class SchemaError(RuntimeError):
    """The allow-set cannot be read from the canonical or deployed schema pair."""


def has_text(value: object) -> bool:
    """True for a non-empty, non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def schema_dir() -> Path:
    """The canonical pack schemas, or the deployed ``references/`` copy beside the skill.

    Same resolution rule as validate_project_artifact.py: the canonical pair wins in the
    pack tree, the deployed copy (written by scripts/install_domain_skill.py) serves a
    deployed bundle that cannot reach back into the pack.
    """
    canonical = SKILL_ROOT.parents[1] / "schemas"
    if all((canonical / name).is_file() for name in SCHEMA_NAMES):
        return canonical
    return SKILL_ROOT / "references"


def allowed_project_types() -> tuple[str, ...]:
    """The ``project_type`` enum exactly as declared by project.schema.json.

    Raises :class:`SchemaError` when the schema (or its enum) cannot be read, so the
    caller fails closed instead of guessing a set.
    """
    path = schema_dir() / "project.schema.json"
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        values = schema["properties"]["project_type"]["enum"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise SchemaError(f"cannot read the project_type enum from {path}: {error}") from error
    if not isinstance(values, list) or not values or not all(has_text(value) for value in values):
        raise SchemaError(f"project_type enum in {path} is not a non-empty list of strings")
    return tuple(values)


def allow_set_guard_errors(allowed: tuple[str, ...]) -> list[str]:
    """Guard: every legacy oil value must still be allowed by the schema enum."""
    missing = [project_type for project_type in LEGACY_PROJECT_TYPES if project_type not in set(allowed)]
    if not missing:
        return []
    return [
        "project_type guard: project.schema.json no longer allows the legacy oil "
        f"type(s) {', '.join(missing)}; refusing all input (fail-closed)"
    ]


def has_gap(data: dict) -> bool:
    """True when the supplied evidence already declares a GAP."""
    evidence = data.get(INPUT_EVIDENCE_FIELD)
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("status") == "GAP" for item in evidence
    )


def evidence_for(data: dict) -> list[dict]:
    """Map the input's source_evidence onto the charter's evidence items, verbatim.

    Only the schema's own evidence fields are carried, so no input key can leak past
    ``additionalProperties: false``. Nothing is added, upgraded or downgraded: an
    item's status stays exactly the status the input declared.
    """
    items = data.get(INPUT_EVIDENCE_FIELD)
    if not isinstance(items, list):
        return []
    return [
        {field: item[field] for field in EVIDENCE_FIELDS if field in item}
        for item in items
        if isinstance(item, dict)
    ]


def expected_decision_fields(data: dict) -> dict[str, str]:
    """The seven canonical decision fields, derived from the input only."""
    project_id = data.get("project_id", "")
    project_type = data.get("project_type", "")
    ready = not has_gap(data)
    return {
        "decision_question": (
            f"Is the supplied brief sufficient to open project {project_id} as a {project_type} charter?"
        ),
        "hypothesis": (
            f"{project_id} records the classification, objectives, constraints, cost target, "
            "benchmark and evidence a Project Charter requires."
        ),
        "uncertainty": (
            "The supplied objectives, constraints, cost target, benchmark and evidence are not "
            "independently verified by this skill; the record makes no performance claim."
        ),
        "decision_rule": (
            "Record the charter only when the classification, objectives, constraints, cost "
            "target, benchmark (or an explicit waiver reason) and OBSERVED evidence are supplied."
        ),
        "result": f"{project_id} is {'sufficient' if ready else 'not sufficient'} to open a {project_type} Project Charter.",
        "decision": "GO" if ready else "HOLD",
        "next_action": (
            f"Proceed to the next stage of the {project_type} route."
            if ready
            else "Resolve the recorded gap, then re-run preflight and build."
        ),
    }
