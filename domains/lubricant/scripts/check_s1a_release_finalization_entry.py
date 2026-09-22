"""Check whether real S1a Release Finalization may be entered."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHYSICAL = ROOT / "data/real_cases/WGO_001/s1a/physical"
RUN_PLAN = PHYSICAL / "run_plan.json"
MANIFEST = PHYSICAL / "S1A_STAGE_A_RELEASE_MANIFEST.json"
CANDIDATE = PHYSICAL / "physical_release_candidate/PHYSICAL_RELEASE_CANDIDATE.json"
OWNER_REQUEST = PHYSICAL / "physical_release_candidate/OWNER_INPUT_REQUEST.json"
CONSISTENCY_REVIEW = PHYSICAL / "physical_release_candidate/CONSISTENCY_REVIEW.json"
PREFLIGHT = PHYSICAL / "physical_release_candidate/RELEASE_FINALIZATION_ENTRY_PREFLIGHT.json"

STRICT_ORDER = [
    "A_OWNER_FREEZES_REQUIRED_PARAMETERS",
    "B_FINAL_EXECUTION_ORDER_GENERATED",
    "C_EXECUTION_ARTIFACTS_UPDATED",
    "D_JSON_AND_SEMANTIC_VALIDATION_COMPLETED",
    "E_SHA256_CALCULATED",
    "F_RELEASE_MANIFEST_POPULATED",
    "G_HASHES_VERIFIED",
    "H_OWNER_FINAL_AUTHORIZATION_RECORDED",
    "I_RELEASE_STATUS_SET_TO_RELEASED_FOR_EXECUTION",
]
DEFERRED_AFTER_ENTRY = [
    "formal_execution_order",
    "execution_order_provenance",
    "execution_artifacts_updated",
    "release_hashes",
    "manifest_final_values",
    "final_owner_authorization",
]
DOWNSTREAM_STATE = {
    "PHYSICAL_STAGE_A": "HOLD",
    "STAGE_A2": "HOLD",
    "S1B": "HOLD",
    "S2": "HOLD",
    "PHASE_3_4": "NO_CHANGE",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_inputs(run_plan: dict, candidate: dict, owner_request: dict, review: dict, manifest: dict) -> None:
    assert run_plan["release_finalization"]["strict_order"] == STRICT_ORDER
    assert run_plan["release_finalization"]["status"] == "NOT_STARTED"
    assert run_plan["release_gate"]["current_state"] == "DRAFT_NOT_RELEASED"
    assert candidate["status"] == "HOLD_NOT_READY"
    assert candidate["owner_input_status"] == "UNRESOLVED_OWNER_INPUT_REQUIRED"
    assert candidate["owner_parameter_freeze_confirmation"]["status"] == "UNRESOLVED_OWNER_INPUT_REQUIRED"
    assert candidate["ten_hour_censoring_semantics"] == {
        "status": "UNRESOLVED_OWNER_INPUT_REQUIRED",
        "administrative_right_censor_h": None,
        "no_event_within_window_interpretation": None,
        "event_not_observed_recording_rule": None,
    }
    assert owner_request["status"] == "OPEN_UNRESOLVED"
    assert owner_request["collection_rules"]["physical_method_authority"] == "NONE_UNTIL_OWNER_SIGNOFF"
    assert set(owner_request["inputs"]) == {
        "GOOD_CHARACTERIZATION_CANDIDATE", "BAD_CHARACTERIZATION_CANDIDATE", "BENCH_REFERENCE_BLANK",
        "PHYSICAL_EVENT_DETECTION_RULE_V1", "Q2B_FINAL_CHECKPOINTS", "TEN_HOUR_CENSORING_SEMANTICS",
        "PROTOCOL_VERSION", "BENCH_AND_EQUIPMENT_IDENTITIES", "BLOCKING_AND_EXECUTION_ORDER_GENERATION_RULE",
        "OWNER_PARAMETER_FREEZE_CONFIRMATION",
    }
    assert {item["candidate_resolution_key"] for item in owner_request["inputs"].values()} == set(candidate["required_resolution_before_consistency_pass"])
    assert review["status"] == "HOLD_NOT_READY"
    assert review["review_result"] == "UNRESOLVED_INPUTS_REMAIN"
    assert review["state_transition_allowed"] is False
    assert manifest["release_status"] == "DRAFT_NOT_RELEASED"
    assert manifest["approved_by"] is None and manifest["release_date"] is None
    assert manifest["protocol_version"] is None


def build_preflight(run_plan: dict, candidate: dict, owner_request: dict, review: dict, manifest: dict) -> dict:
    return {
        "artifact_id": "WGO_001_S1A_RELEASE_FINALIZATION_ENTRY_PREFLIGHT_V1",
        "purpose": "REAL_RELEASE_FINALIZATION_ENTRY_CHECK_ONLY",
        "status": "BLOCKED_AS_DESIGNED",
        "evaluation_mode": "CURRENT_STATE_BLOCKED_ASSERTION",
        "entry_allowed": False,
        "release_finalization_started": False,
        "state_transition_allowed": False,
        "physical_execution_authorized": False,
        "physical_method_authority": "NONE",
        "entry_blockers": [
            "OWNER_INPUTS_UNRESOLVED",
            "OWNER_PARAMETER_FREEZE_NOT_CONFIRMED",
            "TEN_HOUR_CENSORING_SEMANTICS_UNRESOLVED",
            "PHYSICAL_CONSISTENCY_NOT_PASSED_AND_OWNER_METHOD_AUTHORITY_NONE",
        ],
        "owner_resolution_coverage": {
            "required_items": candidate["required_resolution_before_consistency_pass"],
            # ponytail: current-state HOLD assertion; derive readiness dynamically when real Owner inputs are supplied.
            "resolved_items": 0,
            "total_required": 10,
        },
        "accepted_example_schema_version": "V1_9_GROUPS_NOT_SUFFICIENT_FOR_PHYSICAL_ENTRY",
        "deferred_after_entry": DEFERRED_AFTER_ENTRY,
        "strict_order_after_entry": run_plan["release_finalization"]["strict_order"],
        "source_artifacts": {
            "run_plan": "data/real_cases/WGO_001/s1a/physical/run_plan.json",
            "physical_release_candidate": "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/PHYSICAL_RELEASE_CANDIDATE.json",
            "owner_input_request": "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/OWNER_INPUT_REQUEST.json",
            "consistency_review": "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/CONSISTENCY_REVIEW.json",
            "release_manifest": "data/real_cases/WGO_001/s1a/physical/S1A_STAGE_A_RELEASE_MANIFEST.json",
        },
        "source_states": {
            "run_plan_release_gate": run_plan["release_gate"]["current_state"],
            "candidate": candidate["status"],
            "owner_input_request": owner_request["status"],
            "consistency_review": review["review_result"],
            "manifest": manifest["release_status"],
        },
        "execution_order": None,
        "execution_order_provenance": None,
        "release_hashes": None,
        "manifest_final_values": None,
        "final_owner_authorization": None,
        "downstream_state": DOWNSTREAM_STATE,
        "prohibited_claims": [
            "METHOD_QUALIFIED",
            "PHYSICAL_RELEASE_APPROVED",
            "STAGE_A2_STARTED",
            "S1B_STARTED",
            "S2_STARTED",
        ],
    }


def validate_preflight(preflight: dict) -> None:
    assert preflight["status"] == "BLOCKED_AS_DESIGNED"
    assert preflight["evaluation_mode"] == "CURRENT_STATE_BLOCKED_ASSERTION"
    assert preflight["entry_allowed"] is False
    assert preflight["release_finalization_started"] is False
    assert preflight["state_transition_allowed"] is False
    assert preflight["physical_execution_authorized"] is False
    assert preflight["physical_method_authority"] == "NONE"
    assert preflight["entry_blockers"] == [
        "OWNER_INPUTS_UNRESOLVED",
        "OWNER_PARAMETER_FREEZE_NOT_CONFIRMED",
        "TEN_HOUR_CENSORING_SEMANTICS_UNRESOLVED",
        "PHYSICAL_CONSISTENCY_NOT_PASSED_AND_OWNER_METHOD_AUTHORITY_NONE",
    ]
    assert preflight["owner_resolution_coverage"] == {
        "required_items": [
            "GOOD_CHARACTERIZATION_CANDIDATE identity", "BAD_CHARACTERIZATION_CANDIDATE identity",
            "BENCH_REFERENCE_BLANK identity", "physical Event Detection Rule V1", "Q2-B final checkpoints",
            "ten-hour administrative right-censoring semantics", "protocol version", "bench and equipment identities",
            "blocking and execution-order generation rule", "Owner parameter freeze confirmation",
        ],
        "resolved_items": 0,
        "total_required": 10,
    }
    assert preflight["accepted_example_schema_version"] == "V1_9_GROUPS_NOT_SUFFICIENT_FOR_PHYSICAL_ENTRY"
    assert preflight["deferred_after_entry"] == DEFERRED_AFTER_ENTRY
    assert preflight["strict_order_after_entry"] == STRICT_ORDER
    assert preflight["source_artifacts"] == {
        "run_plan": "data/real_cases/WGO_001/s1a/physical/run_plan.json",
        "physical_release_candidate": "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/PHYSICAL_RELEASE_CANDIDATE.json",
        "owner_input_request": "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/OWNER_INPUT_REQUEST.json",
        "consistency_review": "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/CONSISTENCY_REVIEW.json",
        "release_manifest": "data/real_cases/WGO_001/s1a/physical/S1A_STAGE_A_RELEASE_MANIFEST.json",
    }
    assert preflight["execution_order"] is None
    assert preflight["execution_order_provenance"] is None
    assert preflight["release_hashes"] is None
    assert preflight["manifest_final_values"] is None
    assert preflight["final_owner_authorization"] is None
    assert preflight["downstream_state"] == DOWNSTREAM_STATE
    assert preflight["prohibited_claims"] == [
        "METHOD_QUALIFIED", "PHYSICAL_RELEASE_APPROVED", "STAGE_A2_STARTED", "S1B_STARTED", "S2_STARTED",
    ]


def future_fields_cannot_bypass_entry(run_plan: dict, candidate: dict, owner_request: dict, review: dict, manifest: dict) -> None:
    forged_candidate, forged_manifest = copy.deepcopy(candidate), copy.deepcopy(manifest)
    forged_candidate["execution_order"] = [{"planned_run_order": 1}]
    forged_candidate["blocking_and_execution_order_provenance"] = {"source": "forged"}
    forged_candidate["owner_authorization"] = {"owner": "forged"}
    forged_manifest["artifacts"][0]["sha256"] = "0" * 64
    validate_inputs(run_plan, forged_candidate, owner_request, review, forged_manifest)
    forged_preflight = build_preflight(run_plan, forged_candidate, owner_request, review, forged_manifest)
    validate_preflight(forged_preflight)


def rejects_entry_injection(preflight: dict) -> None:
    forged = copy.deepcopy(preflight)
    forged["entry_allowed"] = True
    try:
        validate_preflight(forged)
    except AssertionError:
        return
    raise AssertionError("entry_allowed=true injection accepted")


def verify_artifact(expected: dict) -> None:
    assert PREFLIGHT.exists(), "missing preflight; run with --write"
    assert PREFLIGHT.read_bytes() == canonical_bytes(expected), "stale preflight; run with --write"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write only the derived entry preflight")
    args = parser.parse_args()
    run_plan, candidate, owner_request, review, manifest = map(load, [RUN_PLAN, CANDIDATE, OWNER_REQUEST, CONSISTENCY_REVIEW, MANIFEST])
    validate_inputs(run_plan, candidate, owner_request, review, manifest)
    preflight = build_preflight(run_plan, candidate, owner_request, review, manifest)
    validate_preflight(preflight)
    future_fields_cannot_bypass_entry(run_plan, candidate, owner_request, review, manifest)
    rejects_entry_injection(preflight)
    if args.write:
        PREFLIGHT.write_bytes(canonical_bytes(preflight))
    else:
        verify_artifact(preflight)
    print("PASS FINALIZATION_ENTRY=BLOCKED_AS_DESIGNED ENTRY=false FUTURE_FIELDS_CANNOT_BYPASS=1/1 ENTRY_INJECTION_REJECTED=1/1")


if __name__ == "__main__":
    main()
