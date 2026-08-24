"""Validate the isolated S1a Physical Release Candidate without live release artifacts."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/PHYSICAL_RELEASE_CANDIDATE.json"
REVIEW = ROOT / "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/CONSISTENCY_REVIEW.json"
OWNER_INPUT_REQUEST = ROOT / "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/OWNER_INPUT_REQUEST.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(candidate: dict, review: dict, request: dict) -> None:
    assert candidate["status"] == "HOLD_NOT_READY"
    assert candidate["physical_execution_authorized"] is False
    assert candidate["state_transition_allowed"] is False
    assert candidate["source_isolation"] == "INDEPENDENT_OF_SYNTHETIC_REPLAY_FIXTURES"
    for identity in candidate["reference_identities"].values():
        assert identity["identity_status"] == "UNRESOLVED_OWNER_INPUT_REQUIRED"
        assert all(value is None for key, value in identity.items() if key != "identity_status")
    assert candidate["owner_record"] == {"owner": None, "recorded_at": None, "physical_release_signoff": "NOT_SATISFIED"}
    assert candidate["quarantined_synthetic_values"]["import_rule"].startswith("FORBIDDEN")
    assert candidate["physical_event_detection_rule"]["status"] == "UNRESOLVED_OWNER_INPUT_REQUIRED"
    assert candidate["q2b"] == {"status": "UNRESOLVED_OWNER_INPUT_REQUIRED", "checkpoints_h": None}
    assert candidate["ten_hour_censoring_semantics"] == {
        "status": "UNRESOLVED_OWNER_INPUT_REQUIRED",
        "administrative_right_censor_h": None,
        "no_event_within_window_interpretation": None,
        "event_not_observed_recording_rule": None,
    }
    assert all(value is None for key, value in candidate["physical_event_detection_rule"].items() if key != "status")
    assert candidate["protocol_version"] is None
    assert candidate["bench_and_equipment_identities"] is None
    assert candidate["blocking_and_execution_order_generation_rule"] is None
    assert candidate["blocking_and_execution_order_provenance"] is None
    assert candidate["owner_parameter_freeze_confirmation"] == {
        "status": "UNRESOLVED_OWNER_INPUT_REQUIRED", "owner": None,
        "confirmed_at": None, "approval_reference": None,
    }
    assert candidate["owner_authorization"] is None
    assert candidate["execution_order"] is None
    assert set(candidate["quarantined_synthetic_values"]) == {"source_artifacts", "import_rule"}
    assert candidate["quarantined_synthetic_values"]["import_rule"] == "FORBIDDEN: no value from SYNTHETIC_DEMO_ONLY artifacts may populate this physical candidate."
    assert all(isinstance(path, str) for path in candidate["quarantined_synthetic_values"]["source_artifacts"])
    assert candidate["release_manifest"]["final_values"] is None
    assert candidate["release_manifest"]["artifact_hashes"] is None
    required = {
        "GOOD_CHARACTERIZATION_CANDIDATE identity", "BAD_CHARACTERIZATION_CANDIDATE identity",
        "BENCH_REFERENCE_BLANK identity", "physical Event Detection Rule V1", "Q2-B final checkpoints",
        "ten-hour administrative right-censoring semantics",
        "protocol version", "bench and equipment identities",
        "blocking and execution-order generation rule", "Owner parameter freeze confirmation",
    }
    assert required.issubset(candidate["required_resolution_before_consistency_pass"])
    assert all(value == "HOLD" for key, value in candidate["downstream_state"].items() if key != "PHASE_3_4")
    assert candidate["downstream_state"]["PHASE_3_4"] == "NO_CHANGE"
    assert review["status"] == "HOLD_NOT_READY"
    assert review["synthetic_replay_dependency"] == "NONE"
    assert review["state_transition_allowed"] is False
    assert all(check["status"] == "HOLD" for check in review["checks"] if check["check"] != "candidate_is_independent_from_synthetic_replay")

    assert request["purpose"] == "REAL_OWNER_INPUT_COLLECTION_ONLY"
    assert request["status"] == "OPEN_UNRESOLVED"
    assert request["source_isolation"] == "INDEPENDENT_OF_SYNTHETIC_REPLAY_FIXTURES"
    assert request["collection_rules"] == {
        "synthetic_defaults_or_imports": "FORBIDDEN",
        "unanswered_value": None,
        "state_transition_allowed": False,
        "physical_execution_authorized": False,
        "physical_method_authority": "NONE_UNTIL_OWNER_SIGNOFF",
        "final_release_authorization": "DEFERRED_UNTIL_HASH_VERIFICATION",
    }
    assert {item["candidate_resolution_key"] for item in request["inputs"].values()} == set(candidate["required_resolution_before_consistency_pass"])
    assert set(request["inputs"]) == {
        "GOOD_CHARACTERIZATION_CANDIDATE", "BAD_CHARACTERIZATION_CANDIDATE",
        "BENCH_REFERENCE_BLANK", "PHYSICAL_EVENT_DETECTION_RULE_V1",
        "Q2B_FINAL_CHECKPOINTS", "TEN_HOUR_CENSORING_SEMANTICS", "PROTOCOL_VERSION", "BENCH_AND_EQUIPMENT_IDENTITIES",
        "BLOCKING_AND_EXECUTION_ORDER_GENERATION_RULE", "OWNER_PARAMETER_FREEZE_CONFIRMATION",
    }
    assert request["prohibited_actions"] == [
        "GENERATE_EXECUTION_ORDER", "RECORD_EXECUTION_ORDER_PROVENANCE", "CALCULATE_RELEASE_HASHES",
        "POPULATE_MANIFEST_FINAL_VALUES", "RECORD_FINAL_OWNER_AUTHORIZATION",
        "START_PHYSICAL_EXECUTION", "START_STAGE_A2", "START_S1B", "START_S2",
    ]
    assert request["downstream_state"] == candidate["downstream_state"]
    assert set(request["inputs"]["GOOD_CHARACTERIZATION_CANDIDATE"]["fields"]) == {
        "sample_id", "material_identity", "supplier_or_product_code", "batch_or_container_id",
        "formula_or_composition", "water_content", "water_measurement_method", "preparation_sop",
        "evidence_reference",
    }
    assert set(request["inputs"]["BAD_CHARACTERIZATION_CANDIDATE"]["fields"]) == {
        "definition_choice", "sample_id", "material_identity", "formula_or_composition",
        "batch_or_container_id", "preparation_sop", "safety_handling_reference", "qc_acceptance",
        "identity_conflict_disposition", "evidence_reference",
    }
    assert set(request["inputs"]["BENCH_REFERENCE_BLANK"]["fields"]) == {
        "sample_id", "material_identity", "supplier_or_product_code", "batch_or_container_id",
        "container_id", "new_unused_confirmation", "no_additive_confirmation",
        "no_artificial_contamination_confirmation", "handling_sop", "evidence_reference",
    }
    assert set(request["inputs"]["PHYSICAL_EVENT_DETECTION_RULE_V1"]["fields"]) == set(candidate["physical_event_detection_rule"]) - {"status"}
    assert set(request["inputs"]["Q2B_FINAL_CHECKPOINTS"]["fields"]) == {"checkpoints_h"}
    assert set(request["inputs"]["TEN_HOUR_CENSORING_SEMANTICS"]["fields"]) == {
        "administrative_right_censor_h", "no_event_within_window_interpretation", "event_not_observed_recording_rule",
    }
    assert set(request["inputs"]["PROTOCOL_VERSION"]["fields"]) == {"protocol_version", "protocol_artifact_reference"}
    assert set(request["inputs"]["BENCH_AND_EQUIPMENT_IDENTITIES"]["fields"]) == {
        "bench_id", "noise_instrument_id", "equipment_configuration_reference", "operator_qualification_reference",
    }
    assert set(request["inputs"]["BLOCKING_AND_EXECUTION_ORDER_GENERATION_RULE"]["fields"]) == {"blocking_rule", "order_generation_method", "seed_policy"}
    assert set(request["inputs"]["OWNER_PARAMETER_FREEZE_CONFIRMATION"]["fields"]) == {"owner", "confirmed_at", "approval_reference"}
    assert all(slot_is_empty(slot) for slot in input_slots(request["inputs"]))
    assert all(value is None for value in input_values(request["inputs"]))
    assert review["deferred_finalization_checks"] == [
        {"check": "owner_authorization_exists", "status": "DEFERRED_NOT_EVALUATED"},
        {"check": "physical_owner_signoff_exists", "status": "DEFERRED_NOT_EVALUATED"},
        {"check": "formal_execution_order_exists", "status": "DEFERRED_NOT_EVALUATED"},
        {"check": "execution_order_provenance_exists", "status": "DEFERRED_NOT_EVALUATED"},
        {"check": "manifest_final_values_and_hashes_exist", "status": "DEFERRED_NOT_EVALUATED"},
    ]


def input_values(node: object):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"current_value", "response"}:
                yield value
            else:
                yield from input_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from input_values(value)


def input_slots(node: object):
    if isinstance(node, dict):
        if "current_value" in node or "response" in node:
            yield node
        for value in node.values():
            yield from input_slots(value)


def slot_is_empty(slot: dict) -> bool:
    return {"current_value", "response"}.issubset(slot) and slot["current_value"] is None and slot["response"] is None
 

def rejects_injection(candidate: dict, review: dict, request: dict, path: tuple[str, ...], value: object) -> None:
    mutated = copy.deepcopy(request)
    target = mutated
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with TemporaryDirectory() as temp_dir:
        request_path = Path(temp_dir) / "request.json"
        request_path.write_text(json.dumps(mutated), encoding="utf-8")
        try:
            validate(candidate, review, load(request_path))
        except AssertionError:
            return
    raise AssertionError(f"injection accepted: {'.'.join(path)}")


def rejects_candidate_injection(candidate: dict, review: dict, request: dict, field: str, value: object) -> None:
    mutated = copy.deepcopy(candidate)
    mutated[field] = value
    try:
        validate(mutated, review, request)
    except AssertionError:
        return
    raise AssertionError(f"injection accepted: {field}")


def main() -> None:
    candidate, review, request = load(CANDIDATE), load(REVIEW), load(OWNER_INPUT_REQUEST)
    validate(candidate, review, request)
    rejects_injection(candidate, review, request, ("inputs", "GOOD_CHARACTERIZATION_CANDIDATE", "fields", "sample_id", "response"), "WGO001-S1A-GCC-20260401")
    rejects_injection(candidate, review, request, ("inputs", "PHYSICAL_EVENT_DETECTION_RULE_V1", "fields", "threshold_db", "current_value"), 65)
    rejects_injection(candidate, review, request, ("inputs", "Q2B_FINAL_CHECKPOINTS", "fields", "checkpoints_h", "response"), [1, 2])
    rejects_injection(candidate, review, request, ("inputs", "TEN_HOUR_CENSORING_SEMANTICS", "fields", "administrative_right_censor_h", "response"), 10)
    rejects_candidate_injection(candidate, review, request, "owner_authorization", {"owner": "demo"})
    rejects_candidate_injection(candidate, review, request, "execution_order", [{"planned_run_order": 1}])
    rejects_candidate_injection(candidate, review, request, "blocking_and_execution_order_provenance", {"source": "premature"})
    print("PASS PHYSICAL_RELEASE_CANDIDATE=HOLD_NOT_READY OWNER_REQUEST=EMPTY SYNTHETIC_IMPORT=FORBIDDEN TRANSITION=false INJECTION_REJECTED=7/7")


if __name__ == "__main__":
    main()
