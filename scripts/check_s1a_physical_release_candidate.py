"""Validate the isolated S1a Physical Release Candidate without live release artifacts."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/PHYSICAL_RELEASE_CANDIDATE.json"
REVIEW = ROOT / "data/real_cases/WGO_001/s1a/physical/physical_release_candidate/CONSISTENCY_REVIEW.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(candidate: dict, review: dict) -> None:
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
    assert all(value is None for key, value in candidate["physical_event_detection_rule"].items() if key != "status")
    assert candidate["protocol_version"] is None
    assert candidate["bench_and_equipment_identities"] is None
    assert candidate["blocking_and_execution_order_provenance"] is None
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
        "protocol version", "bench and equipment identities",
        "blocking conditions and execution-order provenance", "Owner physical release sign-off",
    }
    assert required.issubset(candidate["required_resolution_before_consistency_pass"])
    assert all(value == "HOLD" for key, value in candidate["downstream_state"].items() if key != "PHASE_3_4")
    assert candidate["downstream_state"]["PHASE_3_4"] == "NO_CHANGE"
    assert review["status"] == "HOLD_NOT_READY"
    assert review["synthetic_replay_dependency"] == "NONE"
    assert review["state_transition_allowed"] is False
    assert all(check["status"] == "HOLD" for check in review["checks"] if check["check"] != "candidate_is_independent_from_synthetic_replay")
 

def rejects_injection(candidate: dict, review: dict, field: str, value: object) -> None:
    mutated = copy.deepcopy(candidate)
    if field == "threshold_db":
        mutated["physical_event_detection_rule"][field] = value
    else:
        mutated[field] = value
    with TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "candidate.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        try:
            validate(load(path), review)
        except AssertionError:
            return
    raise AssertionError(f"injection accepted: {field}")


def main() -> None:
    candidate, review = load(CANDIDATE), load(REVIEW)
    validate(candidate, review)
    rejects_injection(candidate, review, "threshold_db", 65)
    rejects_injection(candidate, review, "protocol_version", "PHYSICAL_PROTOCOL_V1")
    rejects_injection(candidate, review, "execution_order", [{"planned_run_order": 1}])
    print("PASS PHYSICAL_RELEASE_CANDIDATE=HOLD_NOT_READY SYNTHETIC_IMPORT=FORBIDDEN TRANSITION=false INJECTION_REJECTED=3/3")


if __name__ == "__main__":
    main()
