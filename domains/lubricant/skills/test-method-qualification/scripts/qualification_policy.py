"""Deterministic Stage 3 qualification decision policy shared by builder and validator."""

from __future__ import annotations


ROLES = {"C", "D", "P"}
METRICS = {"REPEATABILITY", "DISCRIMINATION", "SENSITIVITY", "MECHANISM_RELEVANCE", "BENCHMARK_RANKING", "FIELD_RELEVANCE", "COST", "DURATION"}
QUALIFICATION_STATUSES = {"PENDING", "QUALIFIED", "NOT_QUALIFIED"}


def metric_names(method: dict) -> set[str]:
    metrics = method.get("qualification_metrics")
    return {item.get("metric") for item in metrics if isinstance(item, dict) and isinstance(item.get("metric"), str)} if isinstance(metrics, list) else set()


def role_metric_errors(method: dict) -> list[str]:
    roles, metrics = method.get("role"), metric_names(method)
    if not isinstance(roles, list) or any(role not in ROLES for role in roles):
        return ["role is invalid"]
    errors = []
    if "D" in roles and "DISCRIMINATION" not in metrics:
        errors.append("role D requires DISCRIMINATION")
    if "P" in roles:
        if "MECHANISM_RELEVANCE" not in metrics:
            errors.append("role P requires MECHANISM_RELEVANCE")
        if not ({"FIELD_RELEVANCE", "BENCHMARK_RANKING"} & metrics):
            errors.append("role P requires FIELD_RELEVANCE or BENCHMARK_RANKING")
    return errors


def go_qualification_errors(method: dict) -> list[str]:
    errors = role_metric_errors(method)
    if method.get("qualification_status") != "QUALIFIED":
        errors.append("qualification_status is not QUALIFIED")
    if method.get("evidence_scope") != "PHYSICAL":
        errors.append("qualification requires PHYSICAL evidence_scope; source declaration alone is not approval")
    if not isinstance(method.get("qualification_basis"), list) or not method["qualification_basis"]:
        errors.append("qualification_basis is empty")
    evidence = method.get("evidence")
    if not isinstance(evidence, list) or not any(isinstance(item, dict) and item.get("status") == "OBSERVED" for item in evidence):
        errors.append("OBSERVED qualification evidence is missing")
    return errors


def expected_decision_fields(method: dict) -> dict[str, str]:
    method_id, name = method.get("method_id", ""), method.get("name", "")
    role_text = "/".join(method.get("role", [])) if isinstance(method.get("role"), list) else ""
    qualified = not go_qualification_errors(method)
    return {
        "decision_question": f"Is {method_id} ({name}) qualified to measure the target failure/CTQ?",
        "hypothesis": f"{method_id} can provide role-bound measurement evidence for the target failure/CTQ.",
        "uncertainty": "This qualification uses supplied standard/method provenance; its authenticity and validity are not independently verified, and it does not prove product risk, field prediction, or product performance.",
        "decision_rule": f"Qualify only when {role_text} role metrics, OBSERVED evidence, qualification basis, and PHYSICAL evidence scope are complete; PHYSICAL is a source declaration, not approval.",
        "result": f"{method_id} is {'qualified' if qualified else 'not qualified'} for its recorded roles to measure the target failure/CTQ from supplied provenance and evidence only.",
        "decision": "GO" if qualified else "HOLD",
        "next_action": f"Register {method_id} as an eligible response for later design and retain the Evidence Stack." if qualified else "Retain the Evidence Stack and close the recorded qualification gaps.",
    }
