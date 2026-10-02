"""End-to-end checks for the WP-13 intra-stage revision mechanism (REVISE).

Plan §WP-13 acceptance, proven here against the real state-machine validator:

  1. Consecutive REVISE inside one stage: version increments, stage never moves,
     the `accepted_stages` prefix assertion still holds.
  2. Using REVISE to change the stage is rejected.
  3. `PROCESS_ONLY` reuses the original signoff; `FORMULA_OR_CTQ` without a fresh
     technical review is rejected.
  4. "Freeze formula -> swap kettle -> reproduce": three reproductions complete
     inside the PROCESS_WINDOW_DEFINED stage WITHOUT ever triggering a full-chain
     ROLLBACK.
  5. REVISE then GO / ROLLBACK / FREEZE keep behaving normally.

The same before/after events live in fixtures/state-machine/{valid,invalid}.json;
this file replays the chain so the "no full-chain rollback" claim is runnable,
not just a single-event assertion.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATE_SCRIPT = ROOT / "scripts/validate_state_machine.py"
CONTRACT_PATH = ROOT / "contracts" / "state-machine.json"
FIXTURES = ROOT / "fixtures" / "state-machine"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_state_machine", VALIDATE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STAGE = "PROCESS_WINDOW_DEFINED"
QUESTION = "Does the process window survive a bench swap?"


def state(version: int, evidence, stage: str = STAGE, **overrides) -> dict:
    value = {
        "project_id": "WGO-001",
        "stage": stage,
        "status": "ACTIVE",
        "version": version,
        "decision_question": QUESTION,
        "evidence_scope": "PHYSICAL",
        "evidence": list(evidence),
    }
    value.update(overrides)
    return value


def accepted_prefix(stages: list[str], stage: str = STAGE) -> list[str]:
    return stages[: stages.index(stage) + 1]


def revise_event(stages: list[str], before_version: int, impact: str, **revision) -> dict:
    record = {"reason": "bench reproduction", "operator": "R&D owner", "impact": impact}
    record.update(revision)
    return {
        "kind": "REVISE",
        "gate_status": "GO",
        "before": state(before_version, ["E-PW-001"]),
        "after": state(before_version + 1, ["E-PW-001", "E-PW-NEW"]),
        "accepted_stages": accepted_prefix(stages),
        "revision": record,
    }


def revise_chain(stages: list[str]) -> list[dict]:
    """Three PROCESS_ONLY reproductions, all reusing the review of version 7."""
    return [
        revise_event(stages, 7, "PROCESS_ONLY", reuses_review_of=7, revision_index=1),
        revise_event(stages, 8, "PROCESS_ONLY", reuses_review_of=7, revision_index=2),
        revise_event(stages, 9, "PROCESS_ONLY", reuses_review_of=7, revision_index=3),
    ]


def main() -> int:
    validator = load_validator()
    contract = read_json(CONTRACT_PATH)
    stages = contract["stages"]
    assert contract["actions"]["REVISE"] == {
        "gate_status": "GO", "before_statuses": ["ACTIVE"], "after_status": "ACTIVE",
    }, contract["actions"]["REVISE"]

    # --- Acceptance 1 + 4: three reproductions inside PROCESS_WINDOW_DEFINED ----
    prefix = accepted_prefix(stages)
    chain = revise_chain(stages)
    version = chain[0]["before"]["version"]
    for event in chain:
        assert event["before"]["stage"] == STAGE == event["after"]["stage"], event
        assert event["after"]["version"] == event["before"]["version"] + 1, event
        assert event["accepted_stages"] == prefix, "REVISE must not shrink the accepted chain"
        assert validator.validate(event) is None, validator.validate(event)
        # stage never moves and the accepted prefix never shrinks ->
        # no full-chain ROLLBACK is ever needed for this reproduction.
        version = event["after"]["version"]
    assert version == 10, version

    # Control: ROLLBACK cannot do this in place, so REVISE is the only channel.
    # A "rollback to the current stage" is illegal (must move *down*), and a
    # rollback to a nearer stage forces the prefix to shrink = full-chain retreat.
    in_place_rollback = {
        "kind": "ROLLBACK", "gate_status": "HOLD",
        "before": state(11, ["E-PW-001"]),
        "after": state(12, ["E-PW-001", "E-PW-NEW"], status="HOLD"),
        "accepted_stages": prefix,
        "revision": {"reason": "r", "operator": "o", "impact": "i"},
    }
    assert validator.validate(in_place_rollback) == "ROLLBACK must return to the nearest accepted stage", \
        validator.validate(in_place_rollback)
    # The alternative the fix removes: a real ROLLBACK back to MODEL_BUILT shrinks
    # the accepted chain (整链回退), which the REVISE chain above never did.
    retreat = {
        "kind": "ROLLBACK", "gate_status": "HOLD",
        "before": state(11, ["E-PW-001"]),
        "after": state(12, ["E-PW-001", "E-PW-NEW"], stage="MODEL_BUILT", status="HOLD"),
        "accepted_stages": accepted_prefix(stages, "MODEL_BUILT"),
        "revision": {"reason": "r", "operator": "o", "impact": "i"},
    }
    assert validator.validate(retreat) is None, validator.validate(retreat)
    assert len(retreat["accepted_stages"]) < len(prefix), "ROLLBACK does shrink the chain"

    # --- Acceptance 2: REVISE cannot move the stage ----------------------------
    moves_stage = revise_event(stages, 7, "PROCESS_ONLY", reuses_review_of=7)
    moves_stage["after"]["stage"] = "VERIFIED"
    assert validator.validate(moves_stage) == "REVISE must not change the stage", validator.validate(moves_stage)

    # --- Acceptance 3: impact signoff rules ------------------------------------
    # PROCESS_ONLY reuses the original review and passes (already in the chain);
    # it must cite a version that already exists.
    assert validator.validate(revise_event(stages, 7, "PROCESS_ONLY", reuses_review_of=7)) is None
    assert validator.validate(revise_event(stages, 7, "PROCESS_ONLY", reuses_review_of=99)) == \
        "REVISE PROCESS_ONLY impact must reuse an existing reviewed version"
    # FORMULA_OR_CTQ without a fresh review is rejected...
    formula = revise_event(stages, 10, "FORMULA_OR_CTQ")
    assert validator.validate(formula) == "REVISE FORMULA_OR_CTQ impact requires a fresh technical review", \
        validator.validate(formula)
    # ...and accepted only when the re-review covers the NEW version.
    formula["revision"]["re_review"] = {"technical_reviewer": "Lead tribologist", "reviewed_version": 11}
    assert validator.validate(formula) is None, validator.validate(formula)
    stale = revise_event(stages, 10, "FORMULA_OR_CTQ")
    stale["revision"]["re_review"] = {"technical_reviewer": "Lead tribologist", "reviewed_version": 10}
    assert validator.validate(stale) == "REVISE FORMULA_OR_CTQ review must cover the new version", \
        validator.validate(stale)
    # A missing revision record is rejected.
    no_record = revise_event(stages, 7, "PROCESS_ONLY")
    no_record.pop("revision")
    assert validator.validate(no_record) == "REVISE requires reason, operator, and impact", \
        validator.validate(no_record)

    # --- Acceptance 5: REVISE then GO / ROLLBACK / FREEZE behave normally -------
    # GO: REVISE leaves PROCESS_WINDOW_DEFINED at version 10; the routed GO step
    # to VERIFIED still preserves the version (NEW_PRODUCT chain).
    go = {
        "kind": "GO", "gate_status": "GO", "project_type": "NEW_PRODUCT",
        "before": state(10, ["E-PW-001"]),
        "after": state(10, ["E-PW-001"], stage="VERIFIED"),
    }
    assert validator.validate(go) is None, validator.validate(go)
    # FREEZE (WP-06): only from APPLIED, version preserved, with a freeze record;
    # a VERIFIED project must first pass application validation (GO to APPLIED).
    go_applied = {
        "kind": "GO", "gate_status": "GO", "project_type": "NEW_PRODUCT",
        "before": state(10, ["E-PW-001"], stage="VERIFIED"),
        "after": state(10, ["E-PW-001"], stage="APPLIED"),
    }
    assert validator.validate(go_applied) is None, validator.validate(go_applied)
    freeze = {
        "kind": "FREEZE", "gate_status": "FREEZE",
        "before": state(10, ["E-PW-001"], stage="APPLIED"),
        "after": state(10, ["E-PW-001"], stage="FROZEN", status="FROZEN"),
        "freeze_record": {"reason": "applied", "evidence_package": ["E-PW-001"]},
    }
    assert validator.validate(freeze) is None, validator.validate(freeze)

    # --- The ≤3 cap is a soft, non-blocking convention -------------------------
    over_cap = revise_event(stages, 10, "PROCESS_ONLY", reuses_review_of=7, revision_index=4)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        assert validator.validate(over_cap) is None, "the cap must not block a legal REVISE"
    assert "WARNING" in buffer.getvalue() and "#4" in buffer.getvalue(), buffer.getvalue()

    # --- Fixtures agree with the runnable chain --------------------------------
    valid = read_json(FIXTURES / "valid.json")
    invalid = read_json(FIXTURES / "invalid.json")
    revise_valid = [case for case in valid if case["event"]["kind"] == "REVISE"]
    revise_invalid = [case for case in invalid if case["event"]["kind"] == "REVISE"]
    assert len(revise_valid) == 4, [case["name"] for case in revise_valid]
    assert len(revise_invalid) == 5, [case["name"] for case in revise_invalid]
    for case in revise_valid:
        assert validator.validate(case["event"]) is None, case["name"]
    for case in revise_invalid:
        assert validator.validate(case["event"]) == case["expected_reason"], case["name"]

    print("PASS: intra-stage REVISE chain holds the stage, keeps the accepted prefix, "
          "enforces impact signoff, and never forces a full-chain ROLLBACK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
