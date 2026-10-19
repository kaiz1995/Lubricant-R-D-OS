"""Deterministic material-registration policy: shape rules and the decision block.

The design space requires every material-bearing variable to reference a
``material`` record and refuses a reference that does not resolve to one - but
before this module existed nobody produced those records, so the only way a
design space could be built was to place the material files by hand. This
producer closes that gap: one material record per physical material, carrying
identity (supplier / trade name / lot), chemistry family, a non-empty property
list, and a dated price.

``material`` is NOT a stage of any project-type route and no stage constant was
invented for it. It is a companion artifact of the step that already owns
``DESIGN_SPACE_DEFINED`` (exactly as ``process-baseline.json`` is a companion of
the same step), which is why the route table and the stage-gate panel are
untouched by this file.

The authority is ``schemas/material.schema.json``: the builder and the validator
both load it, so a record cannot drift from the contract. The preflight checks
the request's own ``material`` block structurally (the block is not yet a
complete artifact - it has no decision block and no stage), which is why the
shape rules below exist in this module rather than only in the schema.

One rule is deliberately not a refusal: a property the supplier has not supplied
is recorded with ``status: GAP``. Recording the absence is the honest record and
the material still enters the design space; inventing a number is what the
contract forbids.
"""

from __future__ import annotations

import re


INPUT_FIELDS = {"project_artifact", "evidence_scope", "evidence", "material"}
MATERIAL_FIELDS = ("material_id", "category", "identity", "chemistry", "properties", "cost")
PROPERTY_FIELDS = {"property_id", "value", "unit", "source", "evidence_id", "status"}
EVIDENCE_FIELDS = {"evidence_id", "statement", "source", "status", "claim_class"}
EVIDENCE_REQUIRED_FIELDS = {"evidence_id", "statement", "source", "status"}
EVIDENCE_STATUSES = {"OBSERVED", "ASSUMED", "GAP"}
EVIDENCE_SCOPES = {"SYNTHETIC", "PHYSICAL"}
CATEGORIES = ("BASE_OIL", "THICKENER_RAW", "ADDITIVE", "SOLID_FILLER", "SEAL", "COATING")
BASE_OIL_FAMILIES = ("PAO", "ESTER", "MINERAL", "ETHER", "SILICONE", "OTHER")
PROPERTY_STATUSES = ("OBSERVED", "ASSUMED", "GAP")
# The date shape the material contract fixes for a price snapshot.
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def has_text(value: object) -> bool:
    """True for a non-empty, non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def is_number(value: object) -> bool:
    """True for a finite real number (booleans are not numbers here)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def property_errors(value: object, label: str) -> list[str]:
    """One property entry: the recorded value, its provenance, and its status."""
    if not isinstance(value, dict):
        return [label]
    unknown = sorted(set(value) - PROPERTY_FIELDS)
    missing = sorted(PROPERTY_FIELDS - set(value))
    if unknown or missing:
        return [f"{label}: unexpected={unknown or 'none'} missing={missing or 'none'}"]
    errors: list[str] = []
    if not has_text(value.get("property_id")):
        errors.append(f"{label}.property_id must be a non-empty string")
    recorded = value.get("value")
    if isinstance(recorded, bool) or not isinstance(recorded, (int, float, str)):
        errors.append(f"{label}.value must be a number or a non-empty string")
    elif isinstance(recorded, str) and not recorded.strip():
        errors.append(f"{label}.value must be a number or a non-empty string")
    for field in ("unit", "source", "evidence_id"):
        if not has_text(value.get(field)):
            errors.append(f"{label}.{field} must be a non-empty string")
    if value.get("status") not in PROPERTY_STATUSES:
        errors.append(f"{label}.status must be one of {list(PROPERTY_STATUSES)}")
    return errors


def material_shape_errors(value: object) -> list[str]:
    """Every structural reason this ``material`` block cannot be recorded. Empty = it can.

    Shared by preflight, builder and validator so the three scripts cannot
    disagree about the same request. The block is the INPUT shape (identity plus
    the material's own fields); the complete artifact additionally carries the
    common artifact fields, which is what the schema validates.
    """
    if not isinstance(value, dict):
        return ["material must be an object"]
    unknown = sorted(set(value) - set(MATERIAL_FIELDS))
    missing = sorted(set(MATERIAL_FIELDS) - set(value))
    if unknown or missing:
        return [f"material: unexpected={unknown or 'none'} missing={missing or 'none'}"]
    errors: list[str] = []
    if not has_text(value.get("material_id")):
        errors.append("material.material_id must be a non-empty string")
    if value.get("category") not in CATEGORIES:
        errors.append(f"material.category must be one of {list(CATEGORIES)}")
    identity = value.get("identity")
    if not isinstance(identity, dict) or set(identity) != {"supplier", "trade_name", "lot"}:
        errors.append("material.identity must carry exactly supplier, trade_name, and lot")
    else:
        for field in ("supplier", "trade_name", "lot"):
            if not has_text(identity.get(field)):
                errors.append(f"material.identity.{field} must be a non-empty string")
    chemistry = value.get("chemistry")
    if not isinstance(chemistry, dict) or not {"base_oil_family"} <= set(chemistry) <= {"base_oil_family", "notes"}:
        errors.append("material.chemistry must carry base_oil_family and may carry notes")
    elif chemistry.get("base_oil_family") not in BASE_OIL_FAMILIES:
        errors.append(f"material.chemistry.base_oil_family must be one of {list(BASE_OIL_FAMILIES)}")
    elif "notes" in chemistry and not isinstance(chemistry.get("notes"), str):
        errors.append("material.chemistry.notes must be a string")
    properties = value.get("properties")
    if not isinstance(properties, list) or not properties:
        errors.append(
            "material.properties must be a non-empty array: a material with no recorded property at all "
            "is not a design-space input"
        )
    else:
        for index, item in enumerate(properties):
            errors.extend(property_errors(item, f"material.properties[{index}]"))
    cost = value.get("cost")
    if not isinstance(cost, dict) or set(cost) != {"value", "unit", "price_timestamp"}:
        errors.append("material.cost must carry exactly value, unit, and price_timestamp")
    else:
        recorded = cost.get("value")
        if isinstance(recorded, bool) or not is_number(recorded) or recorded < 0:
            errors.append("material.cost.value must be a non-negative number")
        if not has_text(cost.get("unit")):
            errors.append("material.cost.unit must be a non-empty string")
        if not DATE_RE.fullmatch(cost.get("price_timestamp") or ""):
            errors.append("material.cost.price_timestamp must be an ISO date (YYYY-MM-DD)")
    return errors


def evidence_errors(value: object) -> list[str]:
    """Artifact-level evidence: non-empty, well-formed, and no unknown field."""
    if not isinstance(value, list) or not value:
        return ["evidence"]
    errors: list[str] = []
    for index, item in enumerate(value):
        label = f"evidence[{index}]"
        if not isinstance(item, dict) or not EVIDENCE_REQUIRED_FIELDS <= set(item) <= EVIDENCE_FIELDS:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"{label}.status")
    return errors


def has_gap(evidence: object) -> bool:
    """True when an evidence item records an unresolved gap."""
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("status") == "GAP" for item in evidence
    )


def gap_property_ids(material: object) -> list[str]:
    """The property ids recorded as GAP, in recorded order."""
    if not isinstance(material, dict):
        return []
    properties = material.get("properties")
    if not isinstance(properties, list):
        return []
    return [
        item.get("property_id")
        for item in properties
        if isinstance(item, dict) and item.get("status") == "GAP" and has_text(item.get("property_id"))
    ]


def expected_decision_fields(material: dict, evidence_scope: object) -> dict[str, str]:
    """The canonical decision block, recomputed identically by builder and validator.

    ``decision`` is GO when the material block itself is recordable: a GAP
    property is NOT a blocker. Recording that the supplier has not supplied a
    value is the honest record, and refusing the whole material for it would
    push the caller back to inventing a number - the one thing the contract
    forbids. The gap is named in the result and the next action instead.
    """
    material_id = material.get("material_id") if isinstance(material, dict) else None
    identity = material.get("identity") if isinstance(material, dict) and isinstance(material.get("identity"), dict) else {}
    trade_name = identity.get("trade_name")
    lot = identity.get("lot")
    properties = material.get("properties") if isinstance(material, dict) and isinstance(material.get("properties"), list) else []
    recorded = [item for item in properties if isinstance(item, dict) and item.get("status") != "GAP"]
    gaps = gap_property_ids(material)
    ready = not material_shape_errors(material)
    scope_prefix = (
        "Synthetic test fixture / NOT_FOR_PHYSICAL_EXECUTION: this record cannot authorize stage advancement. "
        if evidence_scope == "SYNTHETIC"
        else ""
    )
    return {
        "decision_question": (
            f"Can material {material_id} ({trade_name}, lot {lot}) be registered as a design-space "
            "material with a traceable property set?"
        ),
        "hypothesis": (
            f"A material whose identity, lot, chemistry family, and properties are recorded can enter "
            "design space {material_id} without any property being invented."
        ),
        "uncertainty": (
            f"{scope_prefix}The recorded properties are supplied values, not independently verified "
            "measurements, so a property the supplier has not supplied stays a recorded GAP rather than "
            "an assumed number."
        ),
        "decision_rule": (
            "Register a material only with identity (supplier / trade name / lot), a chemistry family, at "
            "least one recorded property, and a dated price; a property the supplier has not supplied is "
            "recorded with status GAP rather than omitted or invented."
        ),
        "result": (
            f"Material {material_id} is {'recorded' if ready else 'not recorded'}; recorded properties "
            f"{len(recorded)}, recorded GAPs {len(gaps)}"
            + (f" ({', '.join(gaps)})" if gaps else "")
            + "."
        ),
        "decision": "GO" if ready else "HOLD",
        "next_action": (
            f"Use material {material_id} as a design-space input and resolve any recorded GAP before a "
            "property-dependent claim is made from it."
            if ready
            else f"Retain the supplied material data and close the recorded shape errors before material "
            f"{material_id} enters a design space."
        ),
    }
