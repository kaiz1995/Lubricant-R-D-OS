"""Freeze and verify the WGO_001 workflow-demonstration closeout."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "data/real_cases/WGO_001"
PHYSICAL = CASE / "s1a/physical"
SYNTHETIC_GATE = PHYSICAL / "synthetic_replay/gate_result.json"
OWNER_EXAMPLE = PHYSICAL / "physical_release_candidate/review_examples/OWNER_INPUT_PROPOSAL_EXAMPLE.json"
EXAMPLE_REPLAY = PHYSICAL / "physical_release_candidate/review_examples/OWNER_INPUT_RESOLUTION_EXAMPLE_REPLAY.json"
CANDIDATE = PHYSICAL / "physical_release_candidate/PHYSICAL_RELEASE_CANDIDATE.json"
PREFLIGHT = PHYSICAL / "physical_release_candidate/RELEASE_FINALIZATION_ENTRY_PREFLIGHT.json"
MANIFEST = PHYSICAL / "S1A_STAGE_A_RELEASE_MANIFEST.json"
CLOSEOUT = CASE / "PROJECT_DEMO_CLOSEOUT.json"

INPUTS = [SYNTHETIC_GATE, OWNER_EXAMPLE, EXAMPLE_REPLAY, CANDIDATE, PREFLIGHT, MANIFEST]
DOWNSTREAM = {
    "PHYSICAL_STAGE_A": "HOLD",
    "STAGE_A2": "HOLD",
    "S1B": "HOLD",
    "S2": "HOLD",
    "PHASE_3_4": "NO_CHANGE",
}
PROHIBITED = {
    "METHOD_QUALIFIED": False,
    "KNOWN_GOOD": False,
    "KNOWN_BAD": False,
    "PHYSICAL_RELEASE_APPROVED": False,
    "ASA4_OPTIMAL_OR_EFFECTIVE": False,
}
SYNTHETIC_PROHIBITED = {key: PROHIBITED[key] for key in ("METHOD_QUALIFIED", "KNOWN_GOOD", "KNOWN_BAD", "PHYSICAL_RELEASE_APPROVED")}
COMPLETED_SCOPE = [
    "S1A_EXECUTION_PACKAGE_AUTHORING",
    "SYNTHETIC_9_RUN_REPLAY",
    "NEGATIVE_REGRESSION_FIXTURES_5_OF_5",
    "OWNER_INPUT_EXAMPLE_SCHEMA",
    "OWNER_INPUT_EXAMPLE_MAPPING_9_OF_9",
    "PHYSICAL_ENTRY_GUARDS",
]
NOT_EXECUTED_OR_UNVERIFIED = [
    "PHYSICAL_S1A_STAGE_A",
    "REAL_OWNER_INPUTS",
    "METHOD_QUALIFICATION",
    "MATERIAL_PERFORMANCE_OR_EFFICACY",
    "PHYSICAL_RELEASE",
    "S1B",
    "S2",
]
CLOSURE_AUTHORIZATION = {
    "decision": "CLOSE_AS_DEMO",
    "authorized_by": "USER_CONFIRMED_IN_CODEX_THREAD",
    "authorized_at": "2026-08-24",
    "reference": "CODEX_THREAD_USER_CONFIRMATION_2026-08-24",
    "scope": "DEMO_WORKFLOW_ONLY_NOT_TECHNICAL_APPROVAL",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_inputs(synthetic: dict, example: dict, replay: dict, candidate: dict, preflight: dict, manifest: dict) -> None:
    assert synthetic["scope"] == "SYNTHETIC_DEMO_ONLY"
    assert synthetic["result"] == "WORKFLOW_VALIDATED" and synthetic["WORKFLOW_VALIDATED"] is True
    assert synthetic["synthetic_stage_a_result"] == "PROMISING"
    assert synthetic["state_transition_allowed"] is False
    assert synthetic["qualification_claims"] == SYNTHETIC_PROHIBITED

    assert example["status"] == "EXAMPLE_SCHEMA_ACCEPTED"
    assert example["scope"] == "DEMO_EXAMPLE_ONLY"
    assert example["owner_review"]["decision"] == "ACCEPT_EXAMPLE_SCHEMA"
    assert example["state_transition_allowed"] is False

    assert replay["example_stage_status"] == "COMPLETE"
    assert replay["completion_gate"] == "PASS_EXAMPLE_ONLY"
    assert replay["workflow_result"] == "EXAMPLE_WORKFLOW_VALIDATED"
    assert replay["physical_consistency_review"] == "NOT_EVALUATED"
    assert replay["state_transition_allowed"] is False

    assert candidate["status"] == "HOLD_NOT_READY"
    assert candidate["owner_input_status"] == "UNRESOLVED_OWNER_INPUT_REQUIRED"
    assert candidate["state_transition_allowed"] is False
    assert candidate["physical_execution_authorized"] is False
    assert candidate["downstream_state"] == DOWNSTREAM
    assert len(candidate["required_resolution_before_consistency_pass"]) == 10
    assert candidate["execution_order"] is None and candidate["owner_authorization"] is None

    assert preflight["status"] == "BLOCKED_AS_DESIGNED"
    assert preflight["entry_allowed"] is False and preflight["state_transition_allowed"] is False
    assert preflight["owner_resolution_coverage"]["total_required"] == 10
    assert preflight["owner_resolution_coverage"]["resolved_items"] == 0
    assert preflight["execution_order"] is None and preflight["release_hashes"] is None
    assert preflight["manifest_final_values"] is None and preflight["final_owner_authorization"] is None

    assert manifest["release_status"] == "DRAFT_NOT_RELEASED"
    assert len(manifest["artifacts"]) == 5
    assert all(artifact["sha256"] is None for artifact in manifest["artifacts"])
    assert manifest["approved_by"] is None and manifest["release_date"] is None


def build_closeout(input_hashes: dict[str, str]) -> dict:
    return {
        "artifact_id": "WGO_001_PROJECT_DEMO_CLOSEOUT_V1",
        "scope": "WORKFLOW_DEMONSTRATION_ONLY",
        "project_disposition": "CLOSED_AS_DEMO",
        "closure_authorization": CLOSURE_AUTHORIZATION,
        "demo_workflow_status": "COMPLETE",
        "physical_program_status": "PAUSED_NOT_EXECUTED",
        "completed_scope": COMPLETED_SCOPE,
        "not_executed_or_unverified": NOT_EXECUTED_OR_UNVERIFIED,
        "historical_evidence_disposition": "PRESERVED_AS_DESCRIPTIVE_NOT_RECLASSIFIED",
        "WORKFLOW_VALIDATED": True,
        "synthetic_stage_a_result": "PROMISING",
        "state_transition_allowed": False,
        "workflow_validation_meaning": "WORKFLOW_VALIDATED does not equal METHOD_QUALIFIED.",
        "qualification_claims": PROHIBITED,
        "physical_release_candidate_status": "HOLD_NOT_READY",
        "release_finalization_preflight_status": "BLOCKED_AS_DESIGNED",
        "manifest_status": "DRAFT_NOT_RELEASED",
        "manifest_final_hashes": [None, None, None, None, None],
        "downstream_state": DOWNSTREAM,
        "resume_trigger": "EXPLICIT_REAL_OWNER_REENTRY_REQUIRED",
        "resume_requirements": {
            "real_owner_inputs_required": 10,
            "next_checks": ["PHYSICAL_CONSISTENCY_REVIEW", "RELEASE_FINALIZATION_ENTRY_PREFLIGHT"],
        },
        "prohibited_actions": [
            "GENERATE_EXECUTION_ORDER",
            "CALCULATE_RELEASE_HASHES",
            "POPULATE_MANIFEST_FINAL_VALUES",
            "RECORD_FINAL_OWNER_AUTHORIZATION",
            "START_PHYSICAL_STAGE_A",
            "START_STAGE_A2",
            "START_S1B",
            "START_S2",
        ],
        "source_artifact_sha256": input_hashes,
    }


def validate_closeout(closeout: dict, input_hashes: dict[str, str]) -> None:
    assert closeout["scope"] == "WORKFLOW_DEMONSTRATION_ONLY"
    assert closeout["project_disposition"] == "CLOSED_AS_DEMO"
    assert closeout["closure_authorization"] == CLOSURE_AUTHORIZATION
    assert closeout["demo_workflow_status"] == "COMPLETE"
    assert closeout["physical_program_status"] == "PAUSED_NOT_EXECUTED"
    assert closeout["completed_scope"] == COMPLETED_SCOPE
    assert closeout["not_executed_or_unverified"] == NOT_EXECUTED_OR_UNVERIFIED
    assert closeout["historical_evidence_disposition"] == "PRESERVED_AS_DESCRIPTIVE_NOT_RECLASSIFIED"
    assert closeout["WORKFLOW_VALIDATED"] is True
    assert closeout["synthetic_stage_a_result"] == "PROMISING"
    assert closeout["state_transition_allowed"] is False
    assert closeout["workflow_validation_meaning"] == "WORKFLOW_VALIDATED does not equal METHOD_QUALIFIED."
    assert closeout["qualification_claims"] == PROHIBITED
    assert closeout["physical_release_candidate_status"] == "HOLD_NOT_READY"
    assert closeout["release_finalization_preflight_status"] == "BLOCKED_AS_DESIGNED"
    assert closeout["manifest_status"] == "DRAFT_NOT_RELEASED"
    assert closeout["manifest_final_hashes"] == [None, None, None, None, None]
    assert closeout["downstream_state"] == DOWNSTREAM
    assert closeout["resume_trigger"] == "EXPLICIT_REAL_OWNER_REENTRY_REQUIRED"
    assert closeout["resume_requirements"] == {
        "real_owner_inputs_required": 10,
        "next_checks": ["PHYSICAL_CONSISTENCY_REVIEW", "RELEASE_FINALIZATION_ENTRY_PREFLIGHT"],
    }
    assert closeout["source_artifact_sha256"] == input_hashes
    assert "GENERATE_EXECUTION_ORDER" in closeout["prohibited_actions"]
    assert "RECORD_FINAL_OWNER_AUTHORIZATION" in closeout["prohibited_actions"]


def rejects_promotion_injection(closeout: dict, input_hashes: dict[str, str]) -> None:
    for key in ("METHOD_QUALIFIED", "PHYSICAL_RELEASE_APPROVED", "ASA4_OPTIMAL_OR_EFFECTIVE"):
        forged = copy.deepcopy(closeout)
        forged["qualification_claims"][key] = True
        try:
            validate_closeout(forged, input_hashes)
        except AssertionError:
            continue
        raise AssertionError(f"{key}=true injection accepted")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write only the derived project demo closeout")
    args = parser.parse_args()

    input_hashes_before = {path.relative_to(ROOT).as_posix(): sha256(path) for path in INPUTS}
    synthetic, example, replay, candidate, preflight, manifest = map(load, INPUTS)
    validate_inputs(synthetic, example, replay, candidate, preflight, manifest)
    closeout = build_closeout(input_hashes_before)
    validate_closeout(closeout, input_hashes_before)
    rejects_promotion_injection(closeout, input_hashes_before)

    if args.write:
        CLOSEOUT.write_bytes(canonical_bytes(closeout))
    else:
        assert CLOSEOUT.exists(), "missing closeout; run with --write"
        assert CLOSEOUT.read_bytes() == canonical_bytes(closeout), "stale closeout; run with --write"
    assert {path.relative_to(ROOT).as_posix(): sha256(path) for path in INPUTS} == input_hashes_before
    print("PASS DEMO_CLOSEOUT=CLOSED_AS_DEMO WORKFLOW=COMPLETE PHYSICAL=PAUSED_NOT_EXECUTED PROMOTION_INJECTION_REJECTED=3/3")


if __name__ == "__main__":
    main()
