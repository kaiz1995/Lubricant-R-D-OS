"""Replay the accepted S1a Owner-input example without touching physical release data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW_EXAMPLES = ROOT / "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/review_examples"
SOURCE = REVIEW_EXAMPLES / "OWNER_INPUT_PROPOSAL_EXAMPLE.json"
REPLAY = REVIEW_EXAMPLES / "OWNER_INPUT_RESOLUTION_EXAMPLE_REPLAY.json"

REQUIRED_GROUPS = {
    "GOOD_CHARACTERIZATION_CANDIDATE",
    "BAD_CHARACTERIZATION_CANDIDATE",
    "BENCH_REFERENCE_BLANK",
    "PHYSICAL_EVENT_DETECTION_RULE_V1",
    "Q2B_FINAL_CHECKPOINTS",
    "PROTOCOL_VERSION",
    "BENCH_AND_EQUIPMENT_IDENTITIES",
    "BLOCKING_AND_EXECUTION_ORDER_GENERATION_RULE",
    "OWNER_PARAMETER_FREEZE_CONFIRMATION",
}
FORBIDDEN_CLAIMS = {
    "KNOWN_BAD",
    "KNOWN_GOOD",
    "METHOD_QUALIFIED",
    "PHYSICAL_RELEASE_APPROVED",
    "OWNER_INPUT_RESOLVED_FOR_PHYSICAL",
}
LABELS = [
    "EXAMPLE_MAPPING_ONLY",
    "NOT_OWNER_APPROVED",
    "NOT_FOR_PHYSICAL_RELEASE",
    "NOT_FOR_EXECUTION",
]
DOWNSTREAM_STATE = {
    "PHYSICAL_STAGE_A": "HOLD",
    "STAGE_A2": "HOLD",
    "S1B": "HOLD",
    "S2": "HOLD",
    "PHASE_3_4": "NO_CHANGE",
}


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_source() -> tuple[dict, str]:
    source_bytes = SOURCE.read_bytes()
    return json.loads(source_bytes.decode("utf-8")), hashlib.sha256(source_bytes).hexdigest()


def unwrap(group: dict) -> dict:
    normalized = {}
    for key, value in group.items():
        normalized[key] = value["proposed_value"] if isinstance(value, dict) and set(value) == {"proposed_value"} else value
    return normalized


def validate(source: dict) -> None:
    assert source["status"] == "EXAMPLE_SCHEMA_ACCEPTED"
    assert source["scope"] == "DEMO_EXAMPLE_ONLY"
    assert source["state_transition_allowed"] is False
    assert source["physical_execution_authorized"] is False
    assert source["physical_method_authority"] == "NONE"
    assert set(source["proposed_inputs"]) == REQUIRED_GROUPS
    for group_name, group in source["proposed_inputs"].items():
        if group_name == "OWNER_PARAMETER_FREEZE_CONFIRMATION":
            continue
        assert group
        for value in group.values():
            assert set(value) == {"proposed_value"}
            assert value["proposed_value"] is not None
    assert source["owner_review"]["decision"] == "ACCEPT_EXAMPLE_SCHEMA"
    assert source["release_manifest"] == {"final_values": None, "artifact_hashes": None, "final_authorization": None}
    assert source["execution_order"] is None and source["execution_order_provenance"] is None
    assert {"METHOD_QUALIFIED", "PHYSICAL_RELEASE_APPROVED"}.issubset(set(source["prohibited_claims"]))
    assert source["proposed_inputs"]["Q2B_FINAL_CHECKPOINTS"]["checkpoints_h"]["proposed_value"] == [1.5, 3.0]
    assert source["proposed_inputs"]["OWNER_PARAMETER_FREEZE_CONFIRMATION"]["freeze_status"] == "NOT_CONFIRMED"


def derived_artifact(source: dict, source_sha256: str) -> dict:
    normalized_inputs = {name: unwrap(source["proposed_inputs"][name]) for name in sorted(REQUIRED_GROUPS)}
    return {
        "artifact_id": "WGO_001_S1A_OWNER_INPUT_RESOLUTION_EXAMPLE_REPLAY_V1",
        "status": "PASS_EXAMPLE_MAPPING_ONLY",
        "result": "EXAMPLE_SCHEMA_REPLAYED_NOT_RESOLVED",
        "workflow_result": "EXAMPLE_WORKFLOW_VALIDATED",
        "scope": "DEMO_EXAMPLE_ONLY",
        "labels": LABELS,
        "evidence_status": "ASSISTANT_PROPOSED_EXAMPLE_ASSUMPTION",
        "source": {"path": "OWNER_INPUT_PROPOSAL_EXAMPLE.json", "sha256": source_sha256},
        "source_isolation": "READS_ACCEPTED_EXAMPLE_PROPOSAL_ONLY",
        "mapping_coverage": "9/9",
        "normalized_example_inputs": normalized_inputs,
        "physical_consistency_review": "NOT_EVALUATED",
        "real_owner_input_status": "OPEN_UNRESOLVED",
        "no_write_targets": [
            "physical_release_candidate/PHYSICAL_RELEASE_CANDIDATE.json",
            "physical_release_candidate/OWNER_INPUT_REQUEST.json",
            "physical_release_candidate/CONSISTENCY_REVIEW.json",
            "s1a/physical/synthetic_replay/*",
            "Phase_3_4_frozen_artifacts/*",
        ],
        "state_transition_allowed": False,
        "physical_execution_authorized": False,
        "finalization_allowed": False,
        "physical_method_authority": "NONE",
        "execution_order": None,
        "execution_order_provenance": None,
        "release_manifest": {"final_values": None, "artifact_hashes": None, "final_authorization": None},
        "final_authorization": None,
        "prohibited_claims": sorted(FORBIDDEN_CLAIMS),
        "downstream_state": DOWNSTREAM_STATE,
    }


def validate_replay(replay: dict, source_sha256: str) -> None:
    assert replay["status"] == "PASS_EXAMPLE_MAPPING_ONLY"
    assert replay["result"] == "EXAMPLE_SCHEMA_REPLAYED_NOT_RESOLVED"
    assert replay["workflow_result"] == "EXAMPLE_WORKFLOW_VALIDATED"
    assert replay["scope"] == "DEMO_EXAMPLE_ONLY"
    assert replay["labels"] == LABELS
    assert replay["evidence_status"] == "ASSISTANT_PROPOSED_EXAMPLE_ASSUMPTION"
    assert replay["source"] == {"path": "OWNER_INPUT_PROPOSAL_EXAMPLE.json", "sha256": source_sha256}
    assert replay["source_isolation"] == "READS_ACCEPTED_EXAMPLE_PROPOSAL_ONLY"
    assert replay["mapping_coverage"] == "9/9"
    assert set(replay["normalized_example_inputs"]) == REQUIRED_GROUPS
    assert replay["physical_consistency_review"] == "NOT_EVALUATED"
    assert replay["real_owner_input_status"] == "OPEN_UNRESOLVED"
    assert replay["no_write_targets"] == [
        "physical_release_candidate/PHYSICAL_RELEASE_CANDIDATE.json",
        "physical_release_candidate/OWNER_INPUT_REQUEST.json",
        "physical_release_candidate/CONSISTENCY_REVIEW.json",
        "s1a/physical/synthetic_replay/*",
        "Phase_3_4_frozen_artifacts/*",
    ]
    assert replay["state_transition_allowed"] is False
    assert replay["physical_execution_authorized"] is False
    assert replay["finalization_allowed"] is False
    assert replay["physical_method_authority"] == "NONE"
    assert replay["execution_order"] is None and replay["execution_order_provenance"] is None
    assert replay["release_manifest"] == {"final_values": None, "artifact_hashes": None, "final_authorization": None}
    assert replay["final_authorization"] is None
    assert replay["prohibited_claims"] == sorted(FORBIDDEN_CLAIMS)
    assert replay["downstream_state"] == DOWNSTREAM_STATE


def verify_artifact(path: Path, expected: dict) -> None:
    assert path.exists(), f"missing derived artifact: {path.name}; run with --write"
    assert path.read_bytes() == canonical_bytes(expected), f"stale derived artifact: {path.name}; run with --write"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write only the derived example replay artifact")
    args = parser.parse_args()

    source_before = sha256(SOURCE)
    source, source_sha256 = load_source()
    assert source_before == source_sha256
    validate(source)
    replay = derived_artifact(source, source_sha256)
    validate_replay(replay, source_sha256)
    if args.write:
        REPLAY.write_bytes(canonical_bytes(replay))
    else:
        verify_artifact(REPLAY, replay)
    assert sha256(SOURCE) == source_before
    print("PASS EXAMPLE_MAPPING_ONLY WORKFLOW=VALIDATED MAPPING=9/9 PHYSICAL_REVIEW=NOT_EVALUATED TRANSITION=false EXECUTION=false")


if __name__ == "__main__":
    main()
