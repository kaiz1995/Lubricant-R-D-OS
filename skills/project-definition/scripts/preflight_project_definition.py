"""Deterministically reject incomplete Project Definition input before an artifact is written."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


TEXT_FIELDS = (
    "project_id", "project_name", "project_type", "product_family", "business_objective",
    "technical_objective", "risk_class", "owner",
)
LIST_FIELDS = ("hard_constraints", "benchmark_products", "success_criteria")
PROJECT_TYPES = {"NEW_PRODUCT", "IMPROVEMENT", "COST_DOWN", "CUSTOMIZATION", "EXPLORATION", "CORRECTIVE_ACTION"}
RISK_CLASSES = {"LOW", "MEDIUM", "HIGH", "STRATEGIC"}
MEASUREMENT_FIELDS = ("value", "unit", "source", "method_version", "material_batch", "formula_version")
EVIDENCE_FIELDS = ("evidence_id", "statement", "source", "status")


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def errors_for(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]

    errors = [field for field in TEXT_FIELDS if not has_text(data.get(field))]
    if has_text(data.get("project_id")) and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", data["project_id"]):
        errors.append("project_id has invalid characters")
    if data.get("project_type") not in PROJECT_TYPES:
        errors.append("project_type is invalid")
    if data.get("risk_class") not in RISK_CLASSES:
        errors.append("risk_class is invalid")

    for field in LIST_FIELDS:
        value = data.get(field)
        if not isinstance(value, list) or not value or not all(has_text(item) for item in value):
            errors.append(field)

    target_cost = data.get("target_cost")
    if not isinstance(target_cost, dict):
        errors.append("target_cost")
    else:
        for field in MEASUREMENT_FIELDS:
            if field == "value":
                if not isinstance(target_cost.get(field), (int, float)) or isinstance(target_cost.get(field), bool):
                    errors.append(f"target_cost.{field}")
            elif not has_text(target_cost.get(field)):
                errors.append(f"target_cost.{field}")

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
