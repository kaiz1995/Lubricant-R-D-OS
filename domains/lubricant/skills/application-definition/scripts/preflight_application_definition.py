"""Reject incomplete application-definition input before an application artifact is built.

The application verdict is fail-closed. Acceptance criteria may be empty, but an
undetermined threshold must be recorded with status GAP and the verdict cannot be
PASS; a PASS also requires a non-empty, OBSERVED life-claim boundary and no
counterexamples. The external blocker (application-判据 thresholds are not yet
owned) is handled exactly this way: leave the criterion GAP and the verdict
non-PASS rather than fabricate a PASS.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from application_policy import (
    BOUNDARY_FIELDS,
    CONDITION_FIELDS,
    COUNTEREXAMPLE_FIELDS,
    CRITERION_FIELDS,
    EVIDENCE_SCOPES,
    INPUT_FIELDS,
    OPERATORS,
    RESULTS,
    has_gap,
    has_text,
    is_finite_number,
    pass_blockers,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "application.schema.json")
EVIDENCE_FIELDS = {"evidence_id", "statement", "source", "status"}
PROCESS_WINDOW_PREFIX = "PROCESS-WINDOW:"


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def criterion_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, dict) or not set(value) <= CRITERION_FIELDS:
        return [label]
    errors: list[str] = []
    for field in ("criterion_id", "statement"):
        if not has_text(value.get(field)):
            errors.append(f"{label}.{field}")
    status = value.get("status")
    if status not in {"OBSERVED", "ASSUMED", "GAP"}:
        errors.append(f"{label}.status")
    if "threshold" not in value:
        # A criterion with no determined threshold MUST be explicitly GAP.
        if status != "GAP":
            errors.append(f"{label}.status must be GAP when threshold is not determined")
    else:
        if not is_finite_number(value.get("threshold")):
            errors.append(f"{label}.threshold must be a number")
        if value.get("operator") not in OPERATORS:
            errors.append(f"{label}.operator")
        for field in ("unit", "source", "evidence_id"):
            if not has_text(value.get(field)):
                errors.append(f"{label}.{field}")
        if status not in {"OBSERVED", "ASSUMED"}:
            errors.append(f"{label}.status must be OBSERVED or ASSUMED when a threshold is supplied")
    return errors


def counterexample_errors(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["application.counterexamples"]
    errors: list[str] = []
    for index, item in enumerate(value):
        label = f"application.counterexamples[{index}]"
        if not isinstance(item, dict) or set(item) != COUNTEREXAMPLE_FIELDS:
            errors.append(label)
            continue
        for field in sorted(COUNTEREXAMPLE_FIELDS):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
    return errors


def boundary_errors(value: object) -> list[str]:
    if not isinstance(value, dict) or not set(value) <= BOUNDARY_FIELDS or not {"claim_scope", "status", "validated_conditions"} <= set(value):
        return ["application.life_claim_boundary"]
    errors: list[str] = []
    if not has_text(value.get("claim_scope")):
        errors.append("application.life_claim_boundary.claim_scope")
    if value.get("status") not in {"OBSERVED", "ASSUMED", "GAP"}:
        errors.append("application.life_claim_boundary.status")
    conditions = value.get("validated_conditions")
    if not isinstance(conditions, list):
        errors.append("application.life_claim_boundary.validated_conditions")
        return errors
    for index, condition in enumerate(conditions):
        label = f"application.life_claim_boundary.validated_conditions[{index}]"
        if not isinstance(condition, dict) or set(condition) != CONDITION_FIELDS:
            errors.append(label)
            continue
        for field in ("condition_id", "parameter", "unit"):
            if not has_text(condition.get(field)):
                errors.append(f"{label}.{field}")
        lower, upper = condition.get("lower_bound"), condition.get("upper_bound")
        if not is_finite_number(lower):
            errors.append(f"{label}.lower_bound")
        if not is_finite_number(upper):
            errors.append(f"{label}.upper_bound")
        if is_finite_number(lower) and is_finite_number(upper) and lower > upper:
            errors.append(f"{label}.lower_bound must be <= upper_bound")
    return errors


def evidence_errors(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["application.evidence"]
    errors: list[str] = []
    for index, item in enumerate(value):
        label = f"application.evidence[{index}]"
        if not isinstance(item, dict) or set(item) != EVIDENCE_FIELDS:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in {"OBSERVED", "ASSUMED", "GAP"}:
            errors.append(f"{label}.status")
    return errors


def application_errors(value: object) -> list[str]:
    if not isinstance(value, dict) or set(value) != INPUT_FIELDS:
        if isinstance(value, dict):
            extra = sorted(set(value) - INPUT_FIELDS)
            missing = sorted(INPUT_FIELDS - set(value))
            return [f"application must contain only the application-definition input fields; unexpected={extra or 'none'} missing={missing or 'none'}"]
        return ["application must contain only the application-definition input fields"]
    errors: list[str] = []
    for field in ("application_id", "project_reference", "formula_reference", "source", "evidence_id"):
        if not has_text(value.get(field)):
            errors.append(f"application.{field}")
    window = value.get("process_window_reference")
    if not has_text(window):
        errors.append("application.process_window_reference")
    elif not window.startswith(PROCESS_WINDOW_PREFIX):
        errors.append(f"application.process_window_reference must be {PROCESS_WINDOW_PREFIX}<window_id>")
    bench_references = value.get("bench_references")
    if not isinstance(bench_references, list) or not all(has_text(item) for item in bench_references):
        errors.append("application.bench_references must be an array of bench ids")
    criteria = value.get("acceptance_criteria")
    if not isinstance(criteria, list):
        errors.append("application.acceptance_criteria")
    else:
        for index, criterion in enumerate(criteria):
            errors.extend(criterion_errors(criterion, f"application.acceptance_criteria[{index}]"))
    result = value.get("result")
    if result not in RESULTS:
        errors.append("application.result must be PASS, FAIL, INCONCLUSIVE, or GAP")
    if isinstance(criteria, list) and not criteria and result != "GAP":
        errors.append("application.result must be GAP when acceptance_criteria is empty")
    errors.extend(counterexample_errors(value.get("counterexamples")))
    errors.extend(boundary_errors(value.get("life_claim_boundary")))
    if value.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("application.evidence_scope must be SYNTHETIC or PHYSICAL")
    errors.extend(evidence_errors(value.get("evidence")))
    if result == "PASS":
        if has_gap(value):
            errors.append("application.evidence contains GAP; a PASS verdict is not allowed")
        errors.extend(pass_blockers(value))
    return errors


def errors_for(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != {"application"}:
        return ["input must contain only application"]
    return application_errors(data.get("application"))


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_application_definition.py <input.json>")
        return 1
    path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    print("READY: input can form one application record only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
