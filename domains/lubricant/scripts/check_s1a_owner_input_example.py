"""Validate the self-contained, non-promotable S1a Owner-input review example."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/review_examples/OWNER_INPUT_PROPOSAL_EXAMPLE.json"

REQUIRED = {
    "GOOD_CHARACTERIZATION_CANDIDATE": {"sample_id", "material_identity", "supplier_or_product_code", "batch_or_container_id", "formula_or_composition", "water_content", "water_measurement_method", "preparation_sop", "evidence_reference"},
    "BAD_CHARACTERIZATION_CANDIDATE": {"definition_choice", "sample_id", "material_identity", "formula_or_composition", "batch_or_container_id", "preparation_sop", "safety_handling_reference", "qc_acceptance", "identity_conflict_disposition", "evidence_reference"},
    "BENCH_REFERENCE_BLANK": {"sample_id", "material_identity", "supplier_or_product_code", "batch_or_container_id", "container_id", "new_unused_confirmation", "no_additive_confirmation", "no_artificial_contamination_confirmation", "handling_sop", "evidence_reference"},
    "PHYSICAL_EVENT_DETECTION_RULE_V1": {"threshold_db", "comparator", "signal_source", "sampling_interval", "instrument_resolution", "weighting_rule", "rounding_rule", "filtering_rule", "persistence_rule", "missing_sample_rule", "manual_timestamp_rule"},
    "Q2B_FINAL_CHECKPOINTS": {"checkpoints_h"},
    "PROTOCOL_VERSION": {"protocol_version", "protocol_artifact_reference"},
    "BENCH_AND_EQUIPMENT_IDENTITIES": {"bench_id", "noise_instrument_id", "equipment_configuration_reference", "operator_qualification_reference"},
    "BLOCKING_AND_EXECUTION_ORDER_GENERATION_RULE": {"blocking_rule", "order_generation_method", "seed_policy"},
}


def main() -> None:
    example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert example["status"] == "EXAMPLE_SCHEMA_ACCEPTED"
    assert example["evidence_status"] == "ASSISTANT_PROPOSED_EXAMPLE_ASSUMPTION"
    assert set(example["labels"]) == {"ASSISTANT_PROPOSED_EXAMPLE", "EXAMPLE_SCHEMA_ACCEPTED", "NOT_OWNER_APPROVED", "NOT_FOR_PHYSICAL_RELEASE", "NOT_FOR_EXECUTION"}
    assert example["source_isolation"] == "INDEPENDENT_OF_SYNTHETIC_REPLAY_AND_LIVE_PHYSICAL_RELEASE_ARTIFACTS"
    assert example["promotion_policy"] == "NEVER_AUTOMATIC_MANUAL_OWNER_REENTRY_REQUIRED"
    assert example["state_transition_allowed"] is False and example["physical_execution_authorized"] is False
    assert example["physical_method_authority"] == "NONE"
    assert set(example["proposed_inputs"]) == set(REQUIRED) | {"OWNER_PARAMETER_FREEZE_CONFIRMATION"}
    for group, fields in REQUIRED.items():
        assert set(example["proposed_inputs"][group]) == fields
        for value in example["proposed_inputs"][group].values():
            assert set(value) == {"proposed_value"}
            assert value["proposed_value"] is not None
    freeze = example["proposed_inputs"]["OWNER_PARAMETER_FREEZE_CONFIRMATION"]
    assert freeze == {"owner": {"proposed_value": "EXAMPLE OWNER NAME TO BE RE-ENTERED"}, "confirmed_at": None, "approval_reference": None, "freeze_status": "NOT_CONFIRMED"}
    event = example["proposed_inputs"]["PHYSICAL_EVENT_DETECTION_RULE_V1"]
    assert event["threshold_db"] == {"proposed_value": 70.0}
    assert event["sampling_interval"] == {"proposed_value": "EXAMPLE: 2 seconds"}
    assert event["instrument_resolution"] == {"proposed_value": "EXAMPLE: 0.5 dB"}
    assert event["weighting_rule"] == {"proposed_value": "EXAMPLE: A-weighting"}
    assert event["persistence_rule"] == {"proposed_value": "EXAMPLE: continuous >=70 dB for 10 seconds"}
    assert event["manual_timestamp_rule"] == {"proposed_value": "EXAMPLE: record event time to nearest 10 seconds"}
    assert example["proposed_inputs"]["Q2B_FINAL_CHECKPOINTS"]["checkpoints_h"] == {"proposed_value": [1.5, 3.0]}
    assert event["threshold_db"]["proposed_value"] != 65
    assert "5 seconds" not in event["persistence_rule"]["proposed_value"]
    assert example["proposed_inputs"]["Q2B_FINAL_CHECKPOINTS"]["checkpoints_h"]["proposed_value"] != [1, 2]
    assert example["release_manifest"] == {"final_values": None, "artifact_hashes": None, "final_authorization": None}
    assert example["execution_order"] is None and example["execution_order_provenance"] is None
    assert example["owner_review"] == {
        "decision": "ACCEPT_EXAMPLE_SCHEMA", "reviewed_by": "USER_CONFIRMED_IN_CODEX_THREAD", "reviewed_at": "2026-08-24",
        "review_reference": "CODEX_THREAD_CONFIRMATION_2026-08-24",
        "allowed_decisions": ["ACCEPT_EXAMPLE_SCHEMA", "REQUEST_EXAMPLE_REVISION", "REJECT_EXAMPLE"],
        "acceptance_scope": "EXAMPLE_SCHEMA_ONLY_NOT_PHYSICAL_APPROVAL",
    }
    assert example["downstream_state"] == {"PHYSICAL_STAGE_A": "HOLD", "STAGE_A2": "HOLD", "S1B": "HOLD", "S2": "HOLD", "PHASE_3_4": "NO_CHANGE"}
    assert set(example["prohibited_claims"]) == {"METHOD_QUALIFIED", "KNOWN_GOOD", "KNOWN_BAD", "PHYSICAL_RELEASE_APPROVED"}
    print("PASS EXAMPLE_SCHEMA_ACCEPTED_NOT_PHYSICAL_APPROVAL TRANSITION=false EXECUTION=false")


if __name__ == "__main__":
    main()
