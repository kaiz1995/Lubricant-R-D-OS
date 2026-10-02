"""End-to-end checks for the WP-08 gate signoff fields.

Plan §WP-08 acceptance, proven here against the real state-machine validator,
the real schemas, and the real fixtures:

  1. A FREEZE whose after state lacks `technical_reviewer` is rejected.
  2. A FREEZE with an unresolved (OPEN) dissent is rejected; a RESOLVED
     dissent passes while staying on record.
  3. The signoff is a record only: no authority/permission judgement exists
     anywhere in the adjudication code (static self-check) and no
     `authority_level` field exists in the contract or the schemas.
  4. WP-13 migration: the REVISE re-review may reference the real gate
     artifact (`gate_review_id`), and PROCESS_ONLY may cite the original gate
     (`reuses_review_of` as gate_id string), so V3 "who approved this?" can be
     resolved through the cited gate's `technical_reviewer`; the legacy
     embedded forms keep passing (no historical regression).

The FREEZE adjudication lives in scripts/validate_state_machine.py (the
ruling point), NOT in gate_review_policy.py — that file only maps the roles.
"""

from __future__ import annotations

import importlib.util
import json
import tokenize
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
VALIDATE_SCRIPT = ROOT / "scripts/validate_state_machine.py"
CONTRACT_PATH = ROOT / "contracts" / "state-machine.json"
FIXTURES = ROOT / "fixtures" / "state-machine"
SCHEMAS = ROOT / "schemas"
POLICY_SCRIPT = ROOT / "skills/gate-review/scripts/gate_review_policy.py"
BUILD_SCRIPT = ROOT / "skills/gate-review/scripts/build_gate_artifact.py"
PREFLIGHT_SCRIPT = ROOT / "skills/gate-review/scripts/preflight_gate_review.py"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def state(version: int, stage: str, *, status: str = "ACTIVE", **overrides) -> dict:
    value = {
        "project_id": "WGO-001",
        "stage": stage,
        "status": status,
        "version": version,
        "decision_question": "May the applied project be frozen?",
        "evidence_scope": "PHYSICAL",
        "evidence": ["E-701", "E-702"],
    }
    value.update(overrides)
    return value


def freeze_event(after_overrides: dict | None = None) -> dict:
    after = state(5, "FROZEN", status="FROZEN")
    if after_overrides:
        after.update(after_overrides)
    return {
        "kind": "FREEZE", "gate_status": "FREEZE",
        "before": state(5, "APPLIED"),
        "after": after,
        "freeze_record": {"reason": "all conditions met", "evidence_package": "EP-001"},
    }


SIGNED = {
    "technical_reviewer": "Lead tribologist",
    "reviewed_at": "2026-09-28T09:30:00Z",
    "approver": "R&D section manager",
    "approved_at": "2026-09-28T10:15:00Z",
}

OPEN_DISSENT = [{"reviewer": "Process engineer", "comment": "Kettle swap not shown.", "status": "OPEN"}]
RESOLVED_DISSENT = [{"reviewer": "Process engineer", "comment": "Shown by E-703.", "status": "RESOLVED"}]


def schema_validator(kind: str, registry: Registry) -> Draft202012Validator:
    return Draft202012Validator(read_json(SCHEMAS / f"{kind}.schema.json"), registry=registry)


def main() -> int:
    validator = load_module("validate_state_machine", VALIDATE_SCRIPT)
    contract = read_json(CONTRACT_PATH)
    stages = contract["stages"]

    # --- Acceptance 1: no technical_reviewer -> no FREEZE ----------------------
    missing_reviewer = freeze_event()
    reason = validator.validate(missing_reviewer)
    assert reason == "FREEZE requires a technical_reviewer signoff on the after state", reason
    signed = freeze_event(SIGNED)
    assert validator.validate(signed) is None, validator.validate(signed)

    # The precondition is contract-expressible: the FREEZE action declares it.
    signoff_rule = contract["actions"]["FREEZE"]["requires_signoff"]
    assert signoff_rule == {
        "reviewer_field": "technical_reviewer",
        "dissent_field": "dissent",
        "open_dissent_status": "OPEN",
    }, signoff_rule

    # --- Acceptance 2: unresolved dissent forces rejection ----------------------
    blocked = freeze_event({**SIGNED, "dissent": OPEN_DISSENT})
    assert validator.validate(blocked) == "FREEZE is blocked by an unresolved dissent", \
        validator.validate(blocked)
    # A RESOLVED dissent is not unresolved: the FREEZE passes and the
    # disagreement stays on the record for V3 traceability.
    resolved = freeze_event({**SIGNED, "dissent": RESOLVED_DISSENT})
    assert validator.validate(resolved) is None, validator.validate(resolved)

    # --- Acceptance 3: signoff is a record only, no authentication --------------
    # Static self-check: the adjudication and mapping CODE contains no
    # authority/permission logic. Comments and docstrings document the
    # record-only rule, so only code identifiers are inspected (tokenize):
    # NAME tokens exclude COMMENT/STRING prose.
    banned_identifiers = {"authority_level", "authorize", "authorise", "permission", "is_admin", "role_check"}
    for script in (VALIDATE_SCRIPT, POLICY_SCRIPT, BUILD_SCRIPT, PREFLIGHT_SCRIPT):
        names: set[str] = set()
        with open(script, encoding="utf-8") as handle:
            for token in tokenize.generate_tokens(handle.readline):
                if token.type == tokenize.NAME:
                    names.add(token.string)
        offenders = names & banned_identifiers
        assert not offenders, f"{script.name} must not contain the identifiers {sorted(offenders)}"
    # And the contract/schemas declare no authority field either.
    assert "authority_level" not in json.dumps(contract), "contract must not rank authorities"
    for schema_name in ("gate.schema.json", "design_freeze.schema.json", "common.schema.json"):
        assert "authority_level" not in (SCHEMAS / schema_name).read_text(encoding="utf-8"), schema_name

    # --- Schema level: the signoff fields validate, dissent items are closed ---
    registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema = read_json(path)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    gate_schema = schema_validator("gate", registry)
    base_gate = {
        "schema_version": "0.1.0", "artifact_type": "gate",
        "project_id": "WGO-001", "stage": "APPLIED", "evidence_scope": "PHYSICAL",
        "decision_question": "d", "hypothesis": "h", "uncertainty": "u",
        "decision_rule": "r", "result": "res", "decision": "GO",
        "next_action": "n",
        "evidence": [{"evidence_id": "E-1", "statement": "s", "source": "bench", "status": "OBSERVED"}],
        "gate_id": "GATE-001", "experiment_reference": "EXP-001", "scope": "s",
        "gate_status": "GO", "satisfied_conditions": ["c"], "unsatisfied_conditions": [],
        "evidence_gaps": [], "risks": [],
    }
    errors = list(gate_schema.iter_errors({**base_gate, **SIGNED, "dissent": RESOLVED_DISSENT}))
    assert not errors, [error.message for error in errors]
    # An OPEN dissent item is representable on the gate record (FREEZE is
    # adjudicated by the state machine, not the schema).
    errors = list(gate_schema.iter_errors({**base_gate, **SIGNED, "dissent": OPEN_DISSENT}))
    assert not errors, [error.message for error in errors]
    # dissent items are closed objects: an unknown field is rejected.
    bad_item = [{**OPEN_DISSENT[0], "authority_level": "admin"}]
    errors = list(gate_schema.iter_errors({**base_gate, **SIGNED, "dissent": bad_item}))
    assert errors, "an unknown dissent field must be rejected"
    # design_freeze carries the same record-only signoff inside freeze_record.
    freeze_schema = schema_validator("design_freeze", registry)
    design_freeze = {
        "schema_version": "0.1.0", "artifact_type": "design_freeze",
        "project_id": "WGO-001", "stage": "FROZEN", "evidence_scope": "PHYSICAL",
        "decision_question": "May the verified formulation be frozen for release?",
        "hypothesis": "All stage-7 freeze conditions are satisfied on physical evidence.",
        "uncertainty": "None beyond the recorded risk review.",
        "evidence": [{"evidence_id": "E-1", "statement": "s", "source": "bench", "status": "OBSERVED"}],
        "decision_rule": "Freeze only when all eight freeze conditions are satisfied.",
        "result": "Every freeze condition is satisfied and evidenced.",
        "decision": "FREEZE", "next_action": "Close the project and release the knowledge assets.",
        "freeze_record": {
            "reason": "r", "evidence_package": "EP-001", "evidence_scope": "PHYSICAL",
            "evidence_status": "OBSERVED",
            "freeze_conditions": [
                {"condition_id": cid, "satisfied": True,
                 "evidence_reference": ("PROCESS-WINDOW:PW-001" if cid == "MANUFACTURABILITY_ACCEPTABLE" else "E-1")}
                for cid in (
                    "CRITICAL_CTQ_SATISFIED", "CRITICAL_RISK_EVIDENCE_SUFFICIENT", "COST_TARGET_MET",
                    "RAW_MATERIAL_SUPPLY_ACCEPTABLE", "MANUFACTURABILITY_ACCEPTABLE",
                    "CRITICAL_BENCHMARK_NO_DEGRADATION", "COMPATIBILITY_PASSED", "RISK_REVIEW_PASSED",
                )
            ],
            **SIGNED,
            "dissent": RESOLVED_DISSENT,
        },
    }
    errors = list(freeze_schema.iter_errors(design_freeze))
    assert not errors, [error.message for error in errors]

    # --- Skill layer: the gate request admits the optional signoff record ------
    # preflight_gate_review.gate_request_errors accepts the base request plus the
    # optional signoff fields (records only) and still rejects unknown fields.
    import sys

    skill_scripts = str(PREFLIGHT_SCRIPT.parent)
    sys.path.insert(0, skill_scripts)
    try:
        preflight = load_module("preflight_gate_review", PREFLIGHT_SCRIPT)
    finally:
        sys.path.remove(skill_scripts)
    base_request = {
        "gate_id": "GATE-001", "scope": "s", "gate_status": "HOLD",
        "satisfied_conditions": ["c"], "unsatisfied_conditions": [], "evidence_gaps": [], "risks": [],
        "reason": "r",
        "evidence": [{"evidence_id": "E-1", "statement": "s", "source": "bench", "status": "OBSERVED"}],
    }
    signed_request = {**base_request, "technical_reviewer": "t", "reviewed_at": "x",
                      "approver": "a", "approved_at": "b", "dissent": RESOLVED_DISSENT}
    assert preflight.gate_request_errors(signed_request, "p", "e", "PHYSICAL") == [], \
        preflight.gate_request_errors(signed_request, "p", "e", "PHYSICAL")
    unknown = {**signed_request, "authority_level": "admin"}
    assert preflight.gate_request_errors(unknown, "p", "e", "PHYSICAL") == \
        ["gate must contain only the required review fields"], \
        preflight.gate_request_errors(unknown, "p", "e", "PHYSICAL")
    missing = {k: v for k, v in base_request.items() if k != "scope"}
    assert preflight.gate_request_errors(missing, "p", "e", "PHYSICAL") == \
        ["gate must contain only the required review fields"], \
        preflight.gate_request_errors(missing, "p", "e", "PHYSICAL")

    # --- Acceptance 4: WP-13 migration — REVISE resolves signoff via gates -----
    # V3 "who approved this?" is answered by resolving the cited gate artifact.
    gate_registry = {
        "GATE-PW-007": {"gate_id": "GATE-PW-007", "technical_reviewer": "Lead tribologist",
                        "approver": "R&D section manager", "reviewed_version": 7},
        "GATE-RE-012": {"gate_id": "GATE-RE-012", "technical_reviewer": "Senior formulator",
                        "approver": "R&D section manager", "reviewed_version": 12},
    }

    def resolve_signoff(gate_review_id: str) -> dict:
        return gate_registry[gate_review_id]

    def revise_event(before_version: int, revision: dict) -> dict:
        stage = "PROCESS_WINDOW_DEFINED"
        return {
            "kind": "REVISE", "gate_status": "GO",
            "before": state(before_version, stage, decision_question="Q"),
            "after": state(before_version + 1, stage, decision_question="Q"),
            "accepted_stages": stages[: stages.index(stage) + 1],
            "revision": {"reason": "r", "operator": "o", "impact": "i", **revision},
        }

    # PROCESS_ONLY, gate-reference form: passes, and the ORIGINAL signoff is
    # reachable through the cited gate's technical_reviewer.
    reuse = revise_event(12, {"impact": "PROCESS_ONLY", "reuses_review_of": "GATE-PW-007"})
    assert validator.validate(reuse) is None, validator.validate(reuse)
    original = resolve_signoff(reuse["revision"]["reuses_review_of"])
    assert original["technical_reviewer"] == "Lead tribologist", original
    # Legacy integer form still passes (no historical regression).
    legacy_reuse = revise_event(12, {"impact": "PROCESS_ONLY", "reuses_review_of": 7})
    assert validator.validate(legacy_reuse) is None, validator.validate(legacy_reuse)
    # FORMULA_OR_CTQ, referenced form: technical_reviewer is resolved from the
    # cited fresh re-review gate, so the embedded minimal record is not needed.
    reference = revise_event(11, {"impact": "FORMULA_OR_CTQ",
                                  "re_review": {"gate_review_id": "GATE-RE-012", "reviewed_version": 12}})
    assert validator.validate(reference) is None, validator.validate(reference)
    fresh = resolve_signoff(reference["revision"]["re_review"]["gate_review_id"])
    assert fresh["technical_reviewer"] == "Senior formulator" and fresh["reviewed_version"] == 12, fresh
    # The referenced review must cover the NEW version.
    stale_reference = revise_event(11, {"impact": "FORMULA_OR_CTQ",
                                        "re_review": {"gate_review_id": "GATE-RE-012", "reviewed_version": 11}})
    assert validator.validate(stale_reference) == "REVISE FORMULA_OR_CTQ review must cover the new version", \
        validator.validate(stale_reference)
    # Legacy embedded form still passes and still fails when incomplete.
    legacy_re_review = revise_event(11, {"impact": "FORMULA_OR_CTQ",
                                         "re_review": {"technical_reviewer": "Lead tribologist",
                                                       "reviewed_version": 12}})
    assert validator.validate(legacy_re_review) is None, validator.validate(legacy_re_review)
    broken = revise_event(11, {"impact": "FORMULA_OR_CTQ",
                               "re_review": {"gate_review_id": "  ", "reviewed_version": 12}})
    assert validator.validate(broken) == "REVISE FORMULA_OR_CTQ impact requires a fresh technical review", \
        validator.validate(broken)

    # --- Fixtures agree with the runnable checks --------------------------------
    valid_cases, invalid_cases = read_json(FIXTURES / "valid.json"), read_json(FIXTURES / "invalid.json")
    freeze_valid = [case for case in valid_cases if case["event"]["kind"] == "FREEZE"]
    freeze_invalid = [case for case in invalid_cases if case["event"]["kind"] == "FREEZE"]
    assert [case["name"] for case in freeze_valid][-2:] == [
        "freeze-locks-the-applied-project", "freeze-records-signoff-with-resolved-dissent",
    ], [case["name"] for case in freeze_valid]
    assert [case["name"] for case in freeze_invalid][-2:] == [
        "freeze-without-technical-reviewer-is-rejected", "freeze-with-unresolved-dissent-is-rejected",
    ], [case["name"] for case in freeze_invalid]
    for case in freeze_valid:
        assert validator.validate(case["event"]) is None, case["name"]
    for case in freeze_invalid:
        assert validator.validate(case["event"]) == case["expected_reason"], case["name"]
    migration_valid = [case for case in valid_cases if case["name"] in (
        "revise-formula-change-can-cite-a-gate-review", "revise-process-only-can-cite-the-original-gate-review",
    )]
    migration_invalid = [case for case in invalid_cases if case["name"] in (
        "revise-formula-change-gate-reference-cannot-be-empty", "revise-process-only-gate-reference-cannot-be-empty",
    )]
    assert len(migration_valid) == 2 and len(migration_invalid) == 2
    for case in migration_valid:
        assert validator.validate(case["event"]) is None, case["name"]
    for case in migration_invalid:
        assert validator.validate(case["event"]) == case["expected_reason"], case["name"]

    print("PASS: gate signoff is recorded on gate/design_freeze, FREEZE adjudicates it "
          "(no reviewer -> rejected, OPEN dissent -> rejected), the record stays "
          "authority-free, and the REVISE gate references resolve to the real signoff "
          "while legacy forms never regress")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
