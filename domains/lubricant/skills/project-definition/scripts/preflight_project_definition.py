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

    # benchmark_products is optional: a benchmark is only mandatory when one exists.
    # Without it, an explicit, recorded waiver reason is required (no silent skip).
    benchmarks = data.get("benchmark_products")
    benchmarks_valid = (
        isinstance(benchmarks, list)
        and bool(benchmarks)
        and all(has_text(item) for item in benchmarks)
    )
    if not benchmarks_valid and not has_text(data.get("benchmark_waiver_reason")):
        errors.append("benchmark_products (or benchmark_waiver_reason when no benchmark applies)")

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
