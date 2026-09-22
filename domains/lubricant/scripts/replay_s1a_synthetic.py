"""Deterministic integrity replay for the S1A synthetic-demo records only."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "real_cases" / "WGO_001" / "s1a" / "physical" / "synthetic_replay"
CLEAN = DATA / "clean_9_run_records.json"
NEGATIVE = DATA / "negative_fixtures.json"
RAW = DATA / "synthetic_raw_traces.json"
FROZEN = DATA / "frozen_demo_inputs.json"
EVALUATION = DATA / "stage_a_evaluation.json"
GATE = DATA / "gate_result.json"
ISOLATION = {
    "scope": "SYNTHETIC_DEMO_ONLY",
    "classification_labels": ["SYNTHETIC", "DEMO", "NOT_FOR_PHYSICAL_EXECUTION"],
    "evidence_status": "SYNTHETIC_DEMO_ASSUMPTION",
    "physical_method_authority": "NONE",
    "physical_execution_authorized": False,
    "notice": "NOT_FOR_PHYSICAL_EXECUTION",
}
ROLES = (
    "BENCH_REFERENCE_BLANK",
    "GOOD_CHARACTERIZATION_CANDIDATE",
    "BAD_CHARACTERIZATION_CANDIDATE",
)


def fail(message: str) -> None:
    raise ValueError(message)


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def canonical(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def check_isolation(name: str, artifact: dict) -> None:
    for key, expected in ISOLATION.items():
        if artifact.get(key) != expected:
            fail(f"{name}: {key}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_trace_for(record: dict, raw: dict, raw_hash: str) -> dict:
    reference = record.get("raw_signal_reference")
    expected = f"synthetic_raw_traces.json#/traces/{record['run_id']}"
    if reference != expected or record.get("raw_signal_sha256") != raw_hash:
        fail(f"{record['run_id']}: raw reference or hash")
    trace = raw["traces"].get(record["run_id"])
    if not trace:
        fail(f"{record['run_id']}: missing trace")
    return trace


def check_event_semantics(record: dict, trace: dict, event_rule: dict) -> None:
    if record.get("event_definition") != "FIRST_REACH_65_DB" or record.get("stop_reason_version") != "STOP_REASON_V1":
        fail(f"{record['run_id']}: event or stop-reason version")
    hits = [
        point["time_h"] for point in trace["time_noise_db"]
        if point["noise_db"] >= event_rule["threshold_db"]
    ]
    occurred = bool(hits)
    if occurred:
        if trace.get("persistence_seconds") != event_rule["persistence_seconds"]:
            fail(f"{record['run_id']}: persistence")
        if (not record.get("event_occurred") or record.get("event_time_h") != min(hits)
                or record.get("censoring_type") is not None or record.get("censor_time_h") is not None
                or record.get("method_outcome") != "EVENT_REACHED" or record.get("stop_reason") != "EVENT_REACHED"):
            fail(f"{record['run_id']}: event semantics")
    elif (record.get("event_occurred") or record.get("event_time_h") is not None
          or record.get("censoring_type") != "ADMINISTRATIVE_RIGHT_CENSOR"
          or record.get("censor_time_h") != 10 or record.get("method_outcome") != "NO_EVENT_WITHIN_10H"
          or record.get("stop_reason") != "ADMINISTRATIVE_10H_END"):
        fail(f"{record['run_id']}: censor semantics")


def detect_fixture(record: dict) -> str | None:
    if record.get("run_status") == "INVALID_RUN":
        return ("INVALID_RUN_REQUIRES_DEVIATION_AND_EXCLUDE_FROM_Q1_Q2"
                if record.get("deviation") and not eligible_for_q1_q2(record) else None)
    if record.get("execution_order_deviation"):
        return ("EXECUTION_ORDER_DEVIATION_ACTUAL_NOT_EQUAL_PLANNED_WITH_REASON_REQUIRED"
                if record.get("actual_run_order") != record.get("planned_run_order") and record.get("deviation_reason") else None)
    if record.get("stop_reason") == "OTHER_DOCUMENTED":
        return ("OTHER_DOCUMENTED_REQUIRES_NONEMPTY_SPECIFIC_DETAIL"
                if isinstance(record.get("stop_reason_detail"), str) and record["stop_reason_detail"].strip() else None)
    if not record.get("raw_signal_reference"):
        return "RAW_SIGNAL_REFERENCE_REQUIRED"
    if record.get("event_occurred") and (record.get("censoring_type") or record.get("censor_time_h") is not None
                                        or record.get("method_outcome") != "EVENT_REACHED"
                                        or record.get("stop_reason") != "EVENT_REACHED"):
        return "EVENT_AND_CENSORING_OUTCOME_INCONSISTENT"
    return None


def eligible_for_q1_q2(record: dict) -> bool:
    return record.get("run_status") == "VALID_RUN"


def summarize_noise(records: list[dict], checkpoints: list[int]) -> dict:
    result: dict[str, dict[str, dict[str, float]]] = {}
    for hour in checkpoints:
        by_role: dict[str, list[float]] = defaultdict(list)
        for record in records:
            values = {point["time_h"]: point["noise_db"] for point in record["noise_measurements"]}
            by_role[record["reference_role"]].append(values[hour])
        result[f"{hour}h"] = {
            role: {
                "min_db": min(values), "max_db": max(values),
                "range_db": max(values) - min(values),
                "within_role_range_le_1_db": max(values) - min(values) <= 1,
            }
            for role, values in sorted(by_role.items())
        }
    return result


def validate_frozen_inputs(frozen: dict, clean: dict) -> tuple[dict, list[int]]:
    check_isolation("frozen", frozen)
    if frozen.get("fixture_status") != "PASS_FREEZE" or frozen.get("overwrite_policy") != "FROZEN_DO_NOT_OVERWRITE":
        fail("frozen input status")
    if frozen.get("source_policy") != "FIXTURE_LOCAL_ONLY_NO_LIVE_PHYSICAL_ARTIFACTS":
        fail("frozen source policy")
    paths = {CLEAN.name: CLEAN, RAW.name: RAW, NEGATIVE.name: NEGATIVE}
    if frozen.get("fixture_sha256") != {name: sha256(path) for name, path in paths.items()}:
        fail("frozen fixture hash")
    inputs = frozen["demo_inputs"]
    references = inputs["references"]
    records = clean["records"]
    actual_order = [
        {"planned_run_order": row["planned_run_order"], "run_id": row["run_id"], "role": row["reference_role"]}
        for row in sorted(records, key=lambda row: row["planned_run_order"])
    ]
    if actual_order != inputs["planned_order"]:
        fail("frozen planned order")
    checkpoints = inputs["q2b_checkpoints_h"]
    for row in records:
        if row["sample_id"] != references[row["reference_role"]]["sample_id"]:
            fail(f"{row['run_id']}: frozen reference identity")
        if [point["time_h"] for point in row["noise_measurements"]] != checkpoints:
            fail(f"{row['run_id']}: frozen q2b checkpoints")
    return inputs["event_rule"], checkpoints


def validate_clean(clean: dict, raw: dict, raw_hash: str, event_rule: dict, checkpoints: list[int]) -> tuple[list[dict], dict]:
    check_isolation("clean", clean)
    check_isolation("raw", raw)
    records = clean.get("records", [])
    if len(records) != 9:
        fail("clean record count")
    if [item.get("planned_run_order") for item in records] != list(range(1, 10)):
        fail("planned order")
    if [item.get("actual_run_order") for item in records] != list(range(1, 10)):
        fail("actual order")
    blocks: dict[str, list[dict]] = defaultdict(list)
    roles: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        if record.get("run_status") != "VALID_RUN" or record.get("execution_order_deviation") or record.get("deviation"):
            fail(f"{record['run_id']}: clean validity")
        if record.get("stop_reason") == "OTHER_DOCUMENTED":
            fail(f"{record['run_id']}: other stop reason")
        blocks[record["block_id"]].append(record)
        roles[record["reference_role"]].append(record)
        trace = raw_trace_for(record, raw, raw_hash)
        check_event_semantics(record, trace, event_rule)
    if len(blocks) != 3 or any({row["reference_role"] for row in block} != set(ROLES) for block in blocks.values()):
        fail("three blocks by role")
    if set(roles) != set(ROLES) or any(len(rows) != 3 for rows in roles.values()):
        fail("three records by role")
    status = {
        role: {
            "event_occurred_values": sorted({row["event_occurred"] for row in rows}),
            "consistent": len({row["event_occurred"] for row in rows}) == 1,
            "status": "EVENT" if rows[0]["event_occurred"] else "ADMINISTRATIVE_RIGHT_CENSOR_10H",
        }
        for role, rows in sorted(roles.items())
    }
    if not all(item["consistent"] for item in status.values()):
        fail("q2a consistency")
    if any(row.get("censor_time_h") != 10 for row in roles["GOOD_CHARACTERIZATION_CANDIDATE"]):
        fail("good censoring")
    if not all(row["event_occurred"] and row["event_time_h"] < 10 for row in roles["BAD_CHARACTERIZATION_CANDIDATE"]):
        fail("bad discrimination")
    blank_times = [row["event_time_h"] for row in roles["BENCH_REFERENCE_BLANK"]]
    blank_range = round(max(blank_times) - min(blank_times), 10)
    if blank_range > 0.2:
        fail("blank stability")
    q2b = summarize_noise(records, checkpoints)
    if not all(data["within_role_range_le_1_db"] for checkpoint in q2b.values() for data in checkpoint.values()):
        fail("q2b range")
    return records, {
        "q2a": status,
        "q2b": q2b,
        "blank": {"event_time_h": sorted(blank_times), "range_h": blank_range, "range_le_0_2_h": True},
    }


def validate_negative(clean: dict, negative: dict) -> list[dict]:
    check_isolation("negative", negative)
    base = {record["run_id"]: record for record in clean["records"]}
    results = []
    for fixture in negative.get("fixtures", []):
        merged = copy.deepcopy(base.get(fixture.get("base_run_id")))
        if merged is None:
            fail(f"{fixture.get('fixture_id')}: base")
        merged.update(copy.deepcopy(fixture.get("overrides", {})))
        detected = detect_fixture(merged)
        if detected != fixture.get("expected_detection"):
            fail(f"{fixture['fixture_id']}: detection")
        results.append({"fixture_id": fixture["fixture_id"], "expected_detection": detected, "detected": True})
    if len(results) != 5:
        fail("negative fixture count")
    return results


def build_outputs(raw_hash: str, frozen_hash: str, metrics: dict, negative: list[dict]) -> tuple[dict, dict]:
    evaluation = {
        "artifact_id": "WGO_001_S1A_STAGE_A_EVALUATION_V1",
        **ISOLATION,
        "frozen_demo_inputs_sha256": frozen_hash,
        "raw_trace_sha256": raw_hash,
        "q2_a_event_status_consistency": metrics["q2a"],
        "q2_b_noise_db": {"criterion": "within_role_range_db <= 1", "checkpoints": metrics["q2b"]},
        "blank_stability": metrics["blank"],
        "gross_discrimination": {
            "GOOD_CHARACTERIZATION_CANDIDATE": "ALL_3_ADMINISTRATIVE_RIGHT_CENSOR_10H",
            "BAD_CHARACTERIZATION_CANDIDATE": "ALL_3_EVENT_REACHED_BEFORE_10H",
            "passed": True,
        },
        "invalid_count": 0,
        "deviation_count": 0,
        "negative_fixture_detections": negative,
        "stage_a_demo_decision": "PROMISING",
        "state_transition_allowed": False,
        "prohibited_claims": ["METHOD_QUALIFIED", "KNOWN_GOOD", "KNOWN_BAD", "PHYSICAL_RELEASE_APPROVED"],
    }
    result = "WORKFLOW_VALIDATED" if evaluation["stage_a_demo_decision"] == "PROMISING" else "WORKFLOW_DEFECT_FOUND"
    gate = {
        "artifact_id": "WGO_001_S1A_SYNTHETIC_REPLAY_GATE_V1",
        **ISOLATION,
        "frozen_demo_inputs_sha256": frozen_hash,
        "result": result,
        "WORKFLOW_VALIDATED": result == "WORKFLOW_VALIDATED",
        "stage_a_demo_decision": evaluation["stage_a_demo_decision"],
        "synthetic_stage_a_result": evaluation["stage_a_demo_decision"],
        "state_transition_allowed": False,
        "qualification_claims": {
            "METHOD_QUALIFIED": False,
            "KNOWN_GOOD": False,
            "KNOWN_BAD": False,
            "PHYSICAL_RELEASE_APPROVED": False,
        },
        "holds": {"Physical Stage A": "HOLD", "Stage A2": "HOLD", "S1b": "HOLD", "S2": "HOLD"},
        "reason": "Synthetic replay validates workflow controls only; it is not physical-method, material, or release evidence.",
    }
    check_isolation("evaluation", evaluation)
    check_isolation("gate", gate)
    if gate["result"] not in {"WORKFLOW_VALIDATED", "WORKFLOW_DEFECT_FOUND"}:
        fail("gate result")
    return evaluation, gate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="rebuild derived evaluation and gate outputs; frozen fixtures are never modified")
    args = parser.parse_args()
    clean, negative, raw, frozen = load(CLEAN), load(NEGATIVE), load(RAW), load(FROZEN)
    raw_hash = sha256(RAW)
    frozen_hash = sha256(FROZEN)
    stale_hashes = [record for record in clean["records"] if record.get("raw_signal_sha256") != raw_hash]
    if stale_hashes:
        fail("frozen clean raw hashes are unset or stale")
    event_rule, checkpoints = validate_frozen_inputs(frozen, clean)
    records, metrics = validate_clean(clean, raw, raw_hash, event_rule, checkpoints)
    if records != clean["records"]:
        fail("clean mutation")
    negative_results = validate_negative(clean, negative)
    evaluation, gate = build_outputs(raw_hash, frozen_hash, metrics, negative_results)
    expected_evaluation, expected_gate = canonical(evaluation), canonical(gate)
    if args.write:
        EVALUATION.write_text(expected_evaluation, encoding="utf-8")
        GATE.write_text(expected_gate, encoding="utf-8")
    if not EVALUATION.exists() or not GATE.exists():
        fail("checked-in outputs missing")
    if EVALUATION.read_text(encoding="utf-8") != expected_evaluation or GATE.read_text(encoding="utf-8") != expected_gate:
        fail("checked-in output differs from replay")
    print("PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
