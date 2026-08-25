"""Validate the language-agnostic V0 project-state transition contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts" / "state-machine.json").read_text(encoding="utf-8"))
FIXTURES = ROOT / "fixtures" / "state-machine"


def read_cases(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_state(state: object) -> str | None:
    if not isinstance(state, dict):
        return "before and after must be state objects"
    for field in CONTRACT["required_state_fields"]:
        if field not in state:
            return f"state is missing {field}"
    if state["stage"] not in CONTRACT["stages"]:
        return "state has an unknown stage"
    if state["status"] not in CONTRACT["project_statuses"]:
        return "state has an unknown project status"
    if state["evidence_scope"] not in {"SYNTHETIC", "PHYSICAL"}:
        return "state has an unknown evidence scope"
    if state["stage"] not in CONTRACT["lifecycle_stage_sets"][state["status"]]:
        return f"state status {state['status']} is not valid at stage {state['stage']}"
    if not isinstance(state["version"], int) or state["version"] < 1:
        return "state version must be a positive integer"
    if not has_text(state["project_id"]) or not has_text(state["decision_question"]):
        return "state project_id and decision_question must be non-empty"
    if not isinstance(state["evidence"], list) or not state["evidence"]:
        return "state evidence must be retained as a non-empty list"
    return None


def same(before: dict, after: dict, fields: tuple[str, ...]) -> bool:
    return all(before[field] == after[field] for field in fields)


def retains_evidence(before: dict, after: dict) -> bool:
    return all(item in after["evidence"] for item in before["evidence"])


def required_record(event: dict, key: str, fields: list[str], reason: str) -> str | None:
    record = event.get(key)
    if not isinstance(record, dict) or any(not record.get(field) for field in fields):
        return reason
    return None


def lifecycle_error(kind: object, gate: object, before: dict, after: dict) -> str | None:
    rule = CONTRACT["actions"].get(kind)
    if not rule:
        return "event kind is not supported"
    if before["status"] in CONTRACT["terminal_project_statuses"]:
        return "Terminal project status cannot advance"
    if before["status"] == "FROZEN" and kind != "CLOSE":
        return "FROZEN project can only be closed without modification"
    if before["status"] == "DRAFT":
        return "DRAFT project cannot pass a Gate transition"
    if gate != rule["gate_status"]:
        return f"{kind} requires {rule['gate_status']} gate status"
    if before["status"] not in rule["before_statuses"] or after["status"] != rule["after_status"]:
        return f"{kind} requires project lifecycle {', '.join(rule['before_statuses'])} → {rule['after_status']}"
    return None


def validate(event: object) -> str | None:
    if not isinstance(event, dict):
        return "event must be an object"
    before, after = event.get("before"), event.get("after")
    for state in (before, after):
        error = validate_state(state)
        if error:
            return error

    kind, gate = event.get("kind"), event.get("gate_status")
    if gate not in CONTRACT["gate_statuses"]:
        return "gate status must be GO, HOLD, PIVOT, KILL, or FREEZE"
    scopes = {before["evidence_scope"], after["evidence_scope"]}
    if len(scopes) != 1:
        return "state transition evidence_scope must be retained"
    if before["evidence_scope"] == "SYNTHETIC" and kind != "HOLD":
        return "SYNTHETIC state permits HOLD only"
    error = lifecycle_error(kind, gate, before, after)
    if error:
        return error

    stages = CONTRACT["stages"]
    before_index, after_index = stages.index(before["stage"]), stages.index(after["stage"])
    immutable = ("project_id", "decision_question", "evidence")

    if kind == "GO":
        if after_index != before_index + 1 or after["stage"] in ("FROZEN", "CLOSED"):
            return "GO must advance exactly one stage"
        if before["status"] == "HOLD":
            if not retains_evidence(before, after) or len(after["evidence"]) <= len(before["evidence"]):
                return "GO from HOLD requires newly added evidence"
            if not same(before, after, ("project_id", "decision_question", "version")):
                return "GO must preserve the current project version and decision question"
            return None
        if not same(before, after, immutable + ("version",)):
            return "GO must preserve the current project version and evidence"
        return None

    if kind == "HOLD":
        if not same(before, after, immutable + ("stage", "version")):
            return "HOLD must preserve stage, version, decision question, and evidence"
        return None

    if kind == "PIVOT":
        branch = event.get("preserved_branch")
        branch_error = validate_state(branch)
        if branch_error:
            return "PIVOT requires an active new branch and preserved prior branch"
        if after["version"] <= before["version"] or after["decision_question"] == before["decision_question"]:
            return "PIVOT must create a new decision question and version"
        if branch["status"] != CONTRACT["actions"]["PIVOT"]["preserved_status"] or not same(before, branch, immutable + ("stage", "version")):
            return "PIVOT must preserve the prior branch as PIVOTED"
        return None

    if kind == "KILL":
        if not same(before, after, immutable + ("stage", "version")):
            return "KILL must retain the current project as KILLED"
        record_error = required_record(event, "termination", CONTRACT["termination_fields"], "KILL requires a retained reason and evidence")
        if record_error:
            return record_error
        if not all(item in event["termination"]["evidence"] for item in before["evidence"]):
            return "KILL must retain current evidence in the termination record"
        return None

    if kind == "ROLLBACK":
        accepted = event.get("accepted_stages")
        if not isinstance(accepted, list) or not accepted or accepted[-1] != after["stage"]:
            return "ROLLBACK must return to the nearest accepted stage"
        if accepted != stages[: after_index + 1] or after_index >= before_index:
            return "ROLLBACK must return to the nearest accepted stage"
        if after["version"] <= before["version"] or not same(before, after, ("project_id", "decision_question")):
            return "ROLLBACK must create a new revision without replacing the decision question"
        if not retains_evidence(before, after):
            return "ROLLBACK must retain prior evidence"
        return required_record(event, "revision", CONTRACT["revision_fields"], "ROLLBACK requires reason, operator, and impact")

    if kind == "FREEZE":
        if before["stage"] != "VERIFIED" or after["stage"] != "FROZEN":
            return "FREEZE requires VERIFIED to FROZEN"
        if not same(before, after, immutable + ("version",)):
            return "FREEZE must preserve the verified project evidence"
        return required_record(event, "freeze_record", CONTRACT["freeze_record_fields"], "FREEZE requires a freeze record and evidence package")

    if kind == "CLOSE":
        if before["stage"] != "FROZEN" or after["stage"] != "CLOSED":
            return "CLOSE requires FROZEN to CLOSED"
        if not same(before, after, immutable + ("version",)):
            return "CLOSE cannot modify a frozen project"
        return None

    return "event kind is not supported"


def main() -> int:
    failures: list[str] = []
    valid_cases, invalid_cases = read_cases("valid.json"), read_cases("invalid.json")
    for case in valid_cases:
        reason = validate(case["event"])
        if reason:
            failures.append(f"valid {case['name']}: {reason}")
        else:
            print(f"valid {case['name']}: PASS")
    for case in invalid_cases:
        reason = validate(case["event"])
        expected = case["expected_reason"]
        if reason != expected:
            failures.append(f"invalid {case['name']}: expected {expected!r}, got {reason!r}")
        else:
            print(f"invalid {case['name']}: REJECTED: {reason}")
    synthetic = json.loads(json.dumps(valid_cases[0]["event"]))
    synthetic["before"]["evidence_scope"] = synthetic["after"]["evidence_scope"] = "SYNTHETIC"
    reason = validate(synthetic)
    if reason != "SYNTHETIC state permits HOLD only":
        failures.append(f"synthetic-go: expected synthetic rejection, got {reason!r}")
    else:
        print("invalid synthetic-go: REJECTED: SYNTHETIC state permits HOLD only")
    print(f"valid={len(valid_cases)} invalid={len(invalid_cases)} failures={len(failures)}")
    for failure in failures:
        print(failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
