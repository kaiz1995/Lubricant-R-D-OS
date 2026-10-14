"""Deterministically reject incomplete Project Definition input before an artifact is written.

The allowed ``project_type`` set is READ from ``project.schema.json`` instead of being
listed here. The schema is the authority for the enum, and the seventh route
(``PRECISION_GREASE_DEV``) is one of its values; a second hardcoded list in this file
drifted from the schema and refused that route's own charter. The read is fail-closed:
an unreadable or malformed enum is a HOLD, never an "accept anything" default. The guard
in ``allow_set_guard_errors`` checks the other direction -- the six legacy oil values
must still be in the enum -- so a schema edit that dropped an oil type holds here
instead of silently breaking that route. When the schema is present (the pack ships it
in ``schemas/``, and ``scripts/install_domain_skill.py`` deploys it beside the skill),
every verdict and every message for the six oil routes is byte-for-byte what it was.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from project_definition_policy import (
    SchemaError,
    allow_set_guard_errors,
    allowed_project_types,
)


TEXT_FIELDS = (
    "project_id", "project_name", "project_type", "product_family", "business_objective",
    "technical_objective", "risk_class", "owner",
)
LIST_FIELDS = ("hard_constraints", "success_criteria")
RISK_CLASSES = {"LOW", "MEDIUM", "HIGH", "STRATEGIC"}
MEASUREMENT_FIELDS = ("value", "unit", "source", "method_version", "material_batch", "formula_version")
EVIDENCE_FIELDS = ("evidence_id", "statement", "source", "status")

# Block 2's enumerations, mirroring project.schema.json. Held here as a set so the
# preflight reports a readable message instead of the schema's raw enum dump.
REDUCER_MODEL_SIZES = {"14", "17", "20", "25", "32"}
STRUCTURE_FORMS = {"CUP", "HAT", "ULTRA_FLAT", "OTHER"}
REDUCER_REQUIRED_FIELDS = ("model_size", "structure_form", "friction_pair_materials")
REDUCER_FIELDS = set(REDUCER_REQUIRED_FIELDS) | {"reduction_ratio", "surface_treatment"}
APPLICATION_SCENARIOS = {"INDUSTRIAL_ROBOT", "COBOT", "SEMICONDUCTOR_MEDICAL", "AEROSPACE_DEFENSE"}
DELIVERY_FORMS = {"LAB", "PILOT", "PRODUCTION"}
CRITERIA_STATUSES = {"PROVISIONAL", "FIXED"}


def reducer_model_errors(value: object) -> list[str]:
    """Block 2 (reducer model and hardware carrier) shape, when it is supplied.

    Supplied means declared: a carrier that names its frame size but not its friction
    pair would let the duty step fill the gap with an assumption, so a partial block is
    refused rather than completed here.
    """
    if not isinstance(value, dict):
        return ["reducer_model must be an object"]
    errors: list[str] = []
    unknown = sorted(set(value) - REDUCER_FIELDS)
    if unknown:
        errors.append(f"reducer_model: unexpected={unknown}")
    for field in REDUCER_REQUIRED_FIELDS:
        if field == "friction_pair_materials":
            materials = value.get(field)
            if not isinstance(materials, list) or not materials or not all(has_text(item) for item in materials):
                errors.append(f"reducer_model.{field}")
        elif not has_text(value.get(field)):
            errors.append(f"reducer_model.{field}")
    if has_text(value.get("model_size")) and value["model_size"] not in REDUCER_MODEL_SIZES:
        errors.append("reducer_model.model_size is invalid")
    if has_text(value.get("structure_form")) and value["structure_form"] not in STRUCTURE_FORMS:
        errors.append("reducer_model.structure_form is invalid")
    return errors


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def measurement_errors(value: object, label: str) -> list[str]:
    """Validate a common.schema.json ``measurement`` object under ``label``.

    Messages keep the historical shape (``label`` for a non-object, ``label.field``
    for a bad field), so callers that relied on the old target_cost wording still
    match it byte for byte.
    """
    if not isinstance(value, dict):
        return [label]
    errors: list[str] = []
    for field in MEASUREMENT_FIELDS:
        if field == "value":
            if not isinstance(value.get(field), (int, float)) or isinstance(value.get(field), bool):
                errors.append(f"{label}.{field}")
        elif not has_text(value.get(field)):
            errors.append(f"{label}.{field}")
    return errors


def errors_for(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]

    try:
        allowed_types = allowed_project_types()
    except SchemaError as error:
        return [
            f"cannot read the project_type allow-set: {error}; refusing all input (fail-closed)"
        ]

    errors = allow_set_guard_errors(allowed_types)
    errors.extend(field for field in TEXT_FIELDS if not has_text(data.get(field)))
    if has_text(data.get("project_id")) and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", data["project_id"]):
        errors.append("project_id has invalid characters")
    if data.get("project_type") not in allowed_types:
        errors.append("project_type is invalid")
    if data.get("risk_class") not in RISK_CLASSES:
        errors.append("risk_class is invalid")

    for field in LIST_FIELDS:
        value = data.get(field)
        if not isinstance(value, list) or not value or not all(has_text(item) for item in value):
            errors.append(field)

    # A benchmark is OPTIONAL background (2026-10-15 refactor): the real comparator is
    # built as a physical dossier at step 4, so naming one here is never a gate. The
    # legacy waiver field stays legal on charters that already carry it, and a grease
    # project that names no benchmark at all is now accepted without one -- the previous
    # rule made an absent benchmark a HOLD, which the user's own project could not satisfy.
    benchmarks = data.get("benchmark_products")
    if benchmarks is not None:
        if not isinstance(benchmarks, list) or not all(has_text(item) for item in benchmarks):
            errors.append("benchmark_products must be a list of non-empty strings when supplied")

    # Block 2 (the reducer model and hardware carrier) is the grease route's real starting
    # point, so when it is supplied it must be complete: a half-declared carrier would let
    # the duty step invent the rest. It stays OPTIONAL here so every oil charter is
    # unaffected.
    reducer = data.get("reducer_model")
    if reducer is not None:
        errors.extend(reducer_model_errors(reducer))
    if data.get("application_scenario") is not None and data["application_scenario"] not in APPLICATION_SCENARIOS:
        errors.append("application_scenario is invalid")
    if data.get("delivery_form") is not None and data["delivery_form"] not in DELIVERY_FORMS:
        errors.append("delivery_form is invalid")
    if data.get("cost_position") is not None and data["cost_position"] != "CEILING":
        errors.append("cost_position must be CEILING when supplied: a precision-gear grease charter holds cost as a ceiling, never as a reduction target")
    if data.get("success_criteria_status") is not None and data["success_criteria_status"] not in CRITERIA_STATUSES:
        errors.append("success_criteria_status must be PROVISIONAL or FIXED")

    # Cost is a CONSTRAINT, never a CRITERION. The schema makes target_cost optional
    # and requires cost_basis_reason in its place, so this mirrors that rule instead
    # of demanding a cost target the contract no longer requires: on a grease charter
    # the cost is a ceiling to respect, not a target to optimise toward. target_cost
    # keeps its historical measurement validation when supplied (the six oil routes
    # are unaffected -- their charters set it and every message here is unchanged).
    target_cost = data.get("target_cost")
    if target_cost is None:
        if not has_text(data.get("cost_basis_reason")):
            errors.append("target_cost (or cost_basis_reason when no cost target is set)")
    else:
        errors.extend(measurement_errors(target_cost, "target_cost"))
    cost_ceiling = data.get("cost_ceiling")
    if cost_ceiling is not None:
        errors.extend(measurement_errors(cost_ceiling, "cost_ceiling"))

    evidence = data.get("source_evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("source_evidence")
    else:
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                errors.append(f"source_evidence[{index}]")
                continue
            for field in EVIDENCE_FIELDS[:-1]:
                if not has_text(item.get(field)):
                    errors.append(f"source_evidence[{index}].{field}")
            if item.get("status") != "OBSERVED":
                errors.append(f"source_evidence[{index}].status must be OBSERVED")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_project_definition.py <input.json>")
        return 1
    try:
        data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    print("READY: input can form a PROJECT_DEFINED charter only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
