"""End-to-end acceptance for the PRECISION_GREASE_DEV inner loop (plan section 8.2 E2E-2 / E2E-3).

Two scenarios plus one locked counter-example, driven over real workspaces with the
pack's own skill scripts (preflight -> build -> validate) and the pack's own decision points
(``skills/lubricant-rd-agent/scripts/route_step.py`` and
``scripts/validate_state_machine.py``):

  E2E-2 inner-loop iteration (``scenario_inner_loop_iteration``)
    One full bench round: batch production (grease-batch) -> screening PASS
    (grease-screening) -> bench runs (experiment-import bench path) -> variance
    CONSISTENT_DIFFERENCE (variance-assessment) -> the bench registration and the
    campaign carrier that bounds the loop (bench-registration, BENCH_RESOURCE_REGISTERED +
    CAMPAIGN_OPENED) -> the next-batch decision that opens round 2 (doe-design,
    NEXT_BATCH_DECIDED, with its declared competing explanations).
    Then the declared ring edge VARIANCE_ASSESSED -> BATCH_PRODUCED must be ALLOWed by
    BOTH the router and the state machine, the iteration must advance 1 -> 2 by
    RE-DRIVING the campaign producer with the round-1 entry taken from the built
    iteration-1 artifact, and every round-1 record must survive on disk (evidence
    append-only; the ring is an edge, not a ROLLBACK that voids the rounds it passes).
    The campaign producer's own gate is exercised as a gate: a record that drops round 1,
    or one whose current_iteration exceeds its cap, must be refused.

  E2E-3 inner-loop rework (``scenario_screening_rework``)
    The physical screen FAILs. The declared rework edge SCREENING_PASSED ->
    BATCH_PRODUCED must be ALLOWed by both decision points, the batch must be remade, and the
    whole workspace must contain NO bench_test record: a failed sample never occupies a
    bench slot (screening.schema.json: FAIL -> gate_to_bench BLOCKED; N14 of
    grease-screening).

  decision-3 boundary (``scenario_inter_ring_backtrack_denied``)
    Inter-ring backtracking (the bench shows the method unusable -> back to method
    qualification) is NOT an inner-loop edge and must stay DENIED in the router and in
    the state machine; the contract publishes no BACKTRACK action. The negative
    counterparts (dropping round-1 evidence, a missing iteration counter, iteration
    past max_iterations, a version bump on a ring edge, the exemption leaking into an oil
    route) are locked here too, so the ALLOW assertions above cannot pass against a
    validator that allows everything.

State-machine events are supplied to ``validate()`` as (before, after) pairs, so the
test has to assemble the pair. Where an assertion would only re-state that assembly
(``after["version"] == before["version"]``, ``after["evidence"] == before["evidence"] +
[new]``) the pair is NOT asserted against itself: the SAME rule is instead locked with
a refusal the validator computes (a version bump, a dropped round-1 record, a missing
counter), and the records the pair names are checked back on disk.

Records with no producing script usable here are assembled inline against their schemas
from ``fixtures/inner-loop/`` -- today that is the MODEL_BUILT record alone:
statistical-analysis's remaining oil-route upstream requirements (failure_ctq /
test_method) are not carried by this inner-loop-only workspace, and its REAL refusal is
asserted below rather than printed. The challenge path (C-1) and the experiment path (E-2)
are legal omissions on the grease route, so the probe asserts their ABSENCE from the
refusal. E2E-1 (``test_precision_grease_chain.py``) drives MODEL_BUILT for real on the
full route.
The campaign and next_batch records used to be inline fixtures as well; both are now
produced by their skills, so ``fixtures/inner-loop/campaign_iteration_*.json`` and
``next_batch_round_1.json`` are no longer read by this test (they stay on disk as
historical fixtures). This file modifies no product code.

Run from the repository root::

    python -B open-science/domains/lubricant/tests/lubricant_e2e/test_inner_loop_iteration.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
SCHEMAS = ROOT / "schemas"
CONTRACT = ROOT / "contracts" / "state-machine.json"
FIXTURES = ROOT / "fixtures" / "inner-loop"
ROUTE_SCRIPT = SKILLS / "lubricant-rd-agent" / "scripts" / "route_step.py"
STATE_MACHINE_SCRIPT = ROOT / "scripts" / "validate_state_machine.py"
NAMING_SCRIPT = ROOT / "scripts" / "check_artifact_naming.py"

PROJECT_TYPE = "PRECISION_GREASE_DEV"
PROJECT_ID = "PGD-IL-001"
CAMPAIGN_ID = "CMP-PGD-IL-001"
BENCH_ID = "BENCH-PGD-IL-01"
DESIGN_SPACE_ID = "DS-PGD-IL-001"
EXPERIMENT_DESIGN_ID = "ED-PGD-IL-001"
METHOD_ID = "TM-PGD-IL-001"
CTQ_ID = "CTQ-PGD-IL-001"
SIM = "Synthetic test fixture / NOT_FOR_PHYSICAL_EXECUTION"

# Round 1 (E2E-2): candidate A vs reference B, then the swap in round 2.
BATCH_CANDIDATE = ("BAT-PGD-IL-R1A", "SMP-PGD-IL-R1A", "FORM-PG-IL@v1")
BATCH_REFERENCE = ("BAT-PGD-IL-R1B", "SMP-PGD-IL-R1B", "FORM-PG-REF@v1")
BATCH_ROUND_2 = ("BAT-PGD-IL-R2A", "SMP-PGD-IL-R2A", "FORM-PG-IL@v1")
# E2E-3: the remade batch of the failed round-1 screen (no bench slot consumed).
BATCH_REWORK = ("BAT-PGD-IL-R1A-RW", "SMP-PGD-IL-R1A-RW", "FORM-PG-IL@v1")

ROUND_1_RUNS = (
    ("RUN-PGD-IL-R1A-1", BATCH_CANDIDATE[0], BATCH_CANDIDATE[1], 2.55),
    ("RUN-PGD-IL-R1A-2", BATCH_CANDIDATE[0], BATCH_CANDIDATE[1], 2.60),
    ("RUN-PGD-IL-R1B-1", BATCH_REFERENCE[0], BATCH_REFERENCE[1], 4.40),
    ("RUN-PGD-IL-R1B-2", BATCH_REFERENCE[0], BATCH_REFERENCE[1], 4.45),
)

# The ring edges the contract publishes (contracts/state-machine.json loop_edges).
RING_EDGE = ("VARIANCE_ASSESSED", "BATCH_PRODUCED", "LOOP_BACK")
REWORK_EDGE = ("SCREENING_PASSED", "BATCH_PRODUCED", "REWORK")

# The ring-edge rules the state machine enforces. The negative checks below pin the
# validator's OWN wording, so a rule that silently relaxed would fail here instead of
# passing on a pair the test assembled to satisfy it.
RING_VERSION_REASON = "GO ring-edge advance must preserve the project version and decision question"
RING_DROP_REASON = "GO ring-edge advance must retain prior evidence"
RING_COUNTER_REASON = "GO ring-edge advance must carry the inner-loop iteration counter"

# statistical-analysis's exact refusal of this route's own bench_test record (WP-14
# exempted bench_test from the GO demand because its contract fixes UNDECIDED; the probe
# below asserts this wording is GONE from the real output).
MODEL_BUILT_GAP = "bench_test_artifact must have decision GO"
# The campaign producer's own append-only / cap refusals the checks below pin.
CAMPAIGN_ROUND_ORDER_GAP = "rounds are recorded oldest first and 1-based"
CAMPAIGN_CAP_GAP = "must not exceed max_iterations"


# ---------------------------------------------------------------------------
# helpers (same conventions as tests/lubricant_e2e/test_precision_grease_chain.py)
# ---------------------------------------------------------------------------


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: Path, *arguments: object) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", script.name, *map(str, arguments)],
        cwd=script.parent,
        capture_output=True,
        text=True,
    )


def run_ok(script: Path, *arguments: object) -> subprocess.CompletedProcess:
    result = run(script, *arguments)
    assert result.returncode == 0, f"{script.name}\n{result.stdout}{result.stderr}"
    return result


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def schema_errors(kind: str, instance: object) -> list[str]:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema = read_json(path)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    schema = read_json(SCHEMAS / f"{kind}.schema.json")
    return [error.message for error in Draft202012Validator(schema, registry=registry).iter_errors(instance)]


def check_schema(kind: str, path: Path) -> dict:
    instance = read_json(path)
    errors = schema_errors(kind, instance)
    assert errors == [], f"{path.name} fails {kind}.schema.json: {errors}"
    return instance


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_digests(ws: Path) -> dict[str, str]:
    """Digest every non-request artifact in the workspace (the round's frozen records)."""
    return {
        path.name: digest(path)
        for path in sorted(ws.glob("*.json"))
        if not path.name.startswith("input-")
    }


def bench_test_records(ws: Path) -> list[str]:
    """Every bench_test record in the workspace, by canonical/suffixed name or artifact_type.

    Detector used for E2E-3's central claim ("no bench_test record consumed a bench
    slot"). It is exercised on the E2E-2 workspace, where four bench_test records exist,
    so the empty result in E2E-3 is evidence and not a broken detector.
    """
    hits: list[str] = []
    for path in sorted(ws.rglob("*.json")):
        if path.name == "bench_test.json" or path.name.startswith("bench_test-"):
            hits.append(str(path.relative_to(ws)))
            continue
        try:
            value = read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(value, dict) and value.get("artifact_type") == "bench_test":
            hits.append(str(path.relative_to(ws)))
    return hits


# ---------------------------------------------------------------------------
# stage inputs / upstream scaffolding (inline construction; inner-loop-only workspace)
# ---------------------------------------------------------------------------


def shared_decision(question: str) -> dict:
    """The canonical decision fields every stage artifact carries."""
    return {
        "decision_question": question,
        "hypothesis": f"{SIM}: the supplied record is sufficient for contract validation only.",
        "uncertainty": f"{SIM}: values are supplied for contract validation, not product evidence.",
        "decision_rule": "Record supplied values only.",
        "result": "Recorded for contract validation only.",
        "decision": "GO",
        "next_action": "Retain the record.",
    }


def evidence(evidence_id: str, statement: str) -> list[dict]:
    return [
        {
            "evidence_id": evidence_id,
            "statement": f"{SIM}: {statement}",
            "source": SIM,
            "status": "ASSUMED",
        }
    ]


def project_artifact() -> dict:
    return {
        "schema_version": "0.1.0",
        "artifact_type": "project",
        "project_id": PROJECT_ID,
        "stage": "PROJECT_DEFINED",
        "status": "ACTIVE",
        "evidence_scope": "PHYSICAL",
        **shared_decision("Proceed to the precision-gear grease inner-loop campaign?"),
        "evidence": evidence("E-PROJ-IL-001", "the charter is supplied for inner-loop acceptance only."),
        "project_name": "Precision-gear grease inner-loop acceptance campaign",
        "project_type": PROJECT_TYPE,
        "product_family": "Precision-gear (harmonic drive) grease",
        "business_objective": "Qualify a precision-gear grease against the OEM reference grease.",
        "technical_objective": "Maintain the required CTQ under the harmonic-drive duty.",
        "hard_constraints": ["Reference materials must exist as physical samples."],
        "target_cost": bound(120, "CNY/kg"),
        "benchmark_products": ["Synthetic OEM precision-gear grease reference"],
        "success_criteria": ["Critical CTQs have evidence."],
        "risk_class": "STRATEGIC",
        "owner": "R&D owner",
    }


def bound(value: float, unit: str) -> dict:
    return {
        "value": value,
        "unit": unit,
        "source": SIM,
        "method_version": "inner-loop-fixture-v1",
        "material_batch": "not_applicable",
        "formula_version": "baseline-v1",
    }


def design_space_artifact() -> dict:
    return {
        "schema_version": "0.1.0",
        "artifact_type": "design_space",
        "project_id": PROJECT_ID,
        "stage": "DESIGN_SPACE_DEFINED",
        "evidence_scope": "PHYSICAL",
        **shared_decision("Is the soap/base-oil space bounded for the inner-loop campaign?"),
        "evidence": evidence("E-DS-IL-001", "the bounded variable space is supplied for inner-loop acceptance only."),
        "design_space_id": DESIGN_SPACE_ID,
        "scope": f"{SIM}: precision-gear grease formulation variables.",
        "variables": [
            {
                "variable_id": "VAR-SOAP-CONCENTRATION",
                "variable_type": "FORMULATION_VARIABLE",
                "material_reference": "MAT-PG-IL-FA-001",
                "role": "REACTION_PRODUCT",
                "constraint_role": "INDEPENDENT",
                "lower_bound": bound(8.0, "mass percent"),
                "upper_bound": bound(14.0, "mass percent"),
                "constraint_rationale": f"{SIM}: below 8 percent the soap network does not form a stable grease.",
            },
            {
                "variable_id": "VAR-BASE-OIL-FRACTION",
                "variable_type": "MATERIAL_FAMILY",
                "material_reference": "MAT-PG-IL-BO-001",
                "role": "INPUT_MATERIAL",
                "lower_bound": bound(80.0, "mass percent"),
                "upper_bound": bound(92.0, "mass percent"),
                "constraint_rationale": f"{SIM}: the charged base oil fraction closes the charge side.",
            },
            {
                "variable_id": "VAR-SOAP-HOLD-TIME",
                "variable_type": "PROCESS_VARIABLE",
                "lower_bound": bound(20, "min"),
                "upper_bound": bound(60, "min"),
                "constraint_rationale": f"{SIM}: the saponification hold must complete before dehydration.",
            },
        ],
        "ctq_references": [CTQ_ID],
        "qualified_test_method_references": [METHOD_ID],
        "constraints": [
            {
                "constraint_id": "CONS-PG-IL-001",
                "kind": "MIXTURE_CLOSURE_INPUTS",
                "expression": "sum(inputs.mass_percent) == 100",
                "rationale": f"{SIM}: this closes the CHARGE only; the soap is generated in situ.",
                "evidence_id": "E-DS-IL-001",
            },
            "Use only the supplied variable bounds.",
        ],
    }


def experiment_design_artifact() -> dict:
    return {
        "schema_version": "0.1.0",
        "artifact_type": "experiment_design",
        "project_id": PROJECT_ID,
        "stage": "EXPERIMENT_DESIGNED",
        "evidence_scope": "PHYSICAL",
        "project_type": PROJECT_TYPE,
        **shared_decision("Which samples should the inner-loop round run?"),
        "evidence": evidence("E-ED-IL-001", "the two-sample paired round is supplied for inner-loop acceptance only."),
        "experiment_design_id": EXPERIMENT_DESIGN_ID,
        "design_space_reference": DESIGN_SPACE_ID,
        "test_method_references": [METHOD_ID],
        "factor_references": ["VAR-SOAP-CONCENTRATION", "VAR-BASE-OIL-FRACTION", "VAR-SOAP-HOLD-TIME"],
        "design": {
            "family": "RESOURCE_CONSTRAINED_GREEDY_SEQUENTIAL",
            "rationale": f"{SIM}: the inner loop runs small sequential rounds.",
            "effects_to_estimate": ["soap concentration effect", "base oil fraction effect", "soap hold time effect"],
        },
        "run_plan": {
            "target_count": 4,
            "replicate_count": 0,
            "center_point_count": 0,
            "randomized": True,
            "point_generation": "PHASE4_DETERMINISTIC_ENGINE",
        },
        # Required for the factor/sequential families (the engine consumes it there).
        "resource_envelope": {
            "bench_slots": 4,
            "lot_capacity": 8,
            "cycle_days": 30,
            "cost_cap": 60000,
            "external_test_lead_time": 14,
        },
        "responses": [{"ctq_reference": CTQ_ID, "test_method_reference": METHOD_ID, "role": "OPTIMIZATION_RESPONSE"}],
        "guardrails": ["Remain within DS-PGD-IL-001.", "Do not exceed the registered bench capacity per round."],
        "expected_information_value": {
            "classification": "RECOMMENDED",
            "decision_relevance": "Separates the candidate from the known-good reference.",
            "expected_information_gain": "Can inform the next-batch decision of the inner loop.",
            "cost": f"{SIM}: planning estimate only.",
            "duration": f"{SIM}: planning estimate only.",
            "redundancy": "No duplicate response is represented by this fixture.",
        },
    }


def batch_input(project_path: Path, design_space_path: Path, experiment_design_path: Path,
                batch_id: str, sample_id: str, formula_reference: str) -> dict:
    trajectory = [
        ("SAPONIFICATION", 195, 196, "degC", 5400, 3),
        ("SOAP_HOLD", 40, 41, "min", 2400, 3),
        ("DEHYDRATION", 115, 116, "degC", 1800, 5),
        ("PHASE_INVERSION", "visual inversion point", "visual inversion point", "qualitative", 420, "operator confirms the inversion point on the sight glass"),
        ("DILUTION_COOLING", 3.0, 3.1, "degC/min", 1800, 0.5),
        ("RIPENING", 12, 12, "h", 43200, 2),
        ("MILLING", 0.15, 0.16, "mm", 600, 0.02),
        ("HOMOGENIZATION", 12, 12.2, "MPa", 300, 0.5),
        ("VACUUM_DEAERATION", 5, 5.1, "kPa", 900, 0.5),
        ("FILLING", 1.2, 1.21, "kg/min", 600, 0.05),
    ]
    steps = []
    for index, (step_type, setpoint, actual, unit, duration_s, tolerance) in enumerate(trajectory, start=1):
        steps.append(
            {
                "step_type": step_type,
                "setpoint": setpoint,
                "actual": actual,
                "unit": unit,
                "duration_s": duration_s,
                "deviation": (round(actual - setpoint, 6) if isinstance(setpoint, (int, float)) else "none recorded"),
                "deviation_verdict": "WITHIN",
                "tolerance": tolerance,
                "source": f"{SIM}: kettle log KL-IL-001 line {index}",
                "evidence_id": "E-BAT-IL-001",
            }
        )
    return {
        "project_artifact": project_path.name,
        "design_space_artifact": design_space_path.name,
        "experiment_design_artifact": experiment_design_path.name,
        "evidence_scope": "PHYSICAL",
        "evidence": [
            {
                "evidence_id": "E-BAT-IL-001",
                "statement": f"{SIM}: kettle log KL-IL-001 records setpoint, actual, duration and a tolerance band for every executed step.",
                "source": f"{SIM}: kettle log KL-IL-001",
                "status": "OBSERVED",
            }
        ],
        "batch": {
            "batch_id": batch_id,
            "formula_reference": formula_reference,
            "scale_class": "LAB",
            "trajectory": steps,
            "raw_material_lots": ["LOT-SYN-IL-001", "LOT-SYN-IL-002"],
            "operator": "Operator OP-IL-01",
            "equipment": "5 L pilot kettle K-IL-01",
            "anomalies": [],
            "batch_verdict": "VALID",
        },
        "sample": {
            "sample_id": sample_id,
            "label": {
                "printed_text": f"{sample_id} | {batch_id} | {formula_reference} | 2026-10-06",
                "printed_at": "2026-10-06T09:40:00",
            },
            "prepared_at": "2026-10-06",
            "storage": "Sealed 1 kg drum at 25 degC, dry indoor cabinet, sample shelf S-03.",
            "chain_of_custody": [
                {
                    "from": "Kettle operator OP-IL-01",
                    "to": "Sample store SS-IL-01",
                    "at": "2026-10-06",
                    "purpose": "Store the freshly filled drum until the screening bench run is scheduled.",
                }
            ],
            "status": "IN_TRANSIT",
        },
    }


def screening_input(project_path: Path, batch_path: Path, sample_path: Path,
                    screening_id: str, sample_reference: str, failing_index: str | None,
                    bench_request: str | None) -> dict:
    """The frozen seven-index screen. ``failing_index`` flips one index to FAIL."""
    tests = [
        ("ST-IL-001", "PENETRATION", 265, "0.1 mm", 340),
        ("ST-IL-002", "WORKED_PENETRATION_CHANGE", 12, "0.1 mm", 30),
        ("ST-IL-003", "DROPPING_POINT", 185, "degC", "180 min"),
        ("ST-IL-004", "OIL_SEPARATION", 1.2, "percent mass", 5),
        ("ST-IL-005", "EVAPORATION_LOSS", 2.5, "percent mass", 3),
        ("ST-IL-006", "SHEAR_STABILITY", 8, "percent change", 10),
        ("ST-IL-007", "APPEARANCE_UNIFORMITY", "uniform", "visual grade", "uniform"),
    ]
    data = {
        "project_artifact": project_path.name,
        "batch_artifact": batch_path.name,
        "sample_artifact": sample_path.name,
        "evidence_scope": "PHYSICAL",
        "evidence": [
            {
                "evidence_id": "E-SC-IL-001",
                "statement": f"{SIM}: the screening lab worksheet records value, unit, limit and verdict for each screened index.",
                "source": SIM,
                "status": "ASSUMED",
            }
        ],
        "screening": {
            "screening_id": screening_id,
            "sample_reference": sample_reference,
            "tests": [
                {
                    "test_id": test_id,
                    "test_name": name,
                    "value": value,
                    "unit": unit,
                    "limit": limit,
                    "verdict": ("FAIL" if name == failing_index else "PASS"),
                }
                for test_id, name, value, unit, limit in tests
            ],
            "measurement_replicates": 3,
        },
    }
    if bench_request is not None:
        data["bench_request"] = bench_request
    return data


def bench_test_input(project_path: Path, run_id: str, batch_reference: str, sample_reference: str,
                     iteration: int, event_time: float, screening_artifacts: list[str]) -> dict:
    return {
        "project_artifact": project_path.name,
        # E-3: the screening artifacts that released this run's sample; the bench gate
        # resolves them and refuses a sample no PASS/RELEASED screen released.
        "screening_artifacts": list(screening_artifacts),
        "evidence_scope": "PHYSICAL",
        "evidence": [
            {
                "evidence_id": f"E-BT-{run_id}-001",
                "statement": f"{SIM}: bench log BL-{run_id} records the protocol version, the fixed setpoints, the ambient conditions and the end of the observation window.",
                "source": SIM,
                "status": "ASSUMED",
            }
        ],
        "bench_test": {
            "run_id": run_id,
            "bench_reference": BENCH_ID,
            "batch_reference": batch_reference,
            "sample_reference": sample_reference,
            # E-2: the step-14 modeling entry links its response references against the
            # CTQs the round's bench runs recorded.
            "ctq_reference": CTQ_ID,
            "protocol_version": "BENCH_PROTOCOL_V2",
            "setpoints": ["load 1.5 kN", "speed 1200 rpm", "temperature 80 degC"],
            "environment": {"temperature_c": 23.5, "humidity_percent": 45.0},
            "raw_record_reference": f"RAW-{run_id}",
            "event_occurred": True,
            "event_time": event_time,
            "censoring_type": "NONE",
            "stop_reason": "event observed inside the protocol window",
            "anomalies": [],
            "campaign_iteration": iteration,
        },
    }


def variance_input(project_path: Path, bench_test_paths: list[Path]) -> dict:
    observations = [
        ("OBS-IL-001", "ARM-CANDIDATE", BATCH_CANDIDATE[1], BATCH_CANDIDATE[0], "RUN-PGD-IL-R1A-1", 2.55),
        ("OBS-IL-002", "ARM-CANDIDATE", BATCH_CANDIDATE[1], BATCH_CANDIDATE[0], "RUN-PGD-IL-R1A-2", 2.60),
        ("OBS-IL-003", "ARM-REFERENCE", BATCH_REFERENCE[1], BATCH_REFERENCE[0], "RUN-PGD-IL-R1B-1", 4.40),
        ("OBS-IL-004", "ARM-REFERENCE", BATCH_REFERENCE[1], BATCH_REFERENCE[0], "RUN-PGD-IL-R1B-2", 4.45),
    ]
    return {
        "campaign_reference": CAMPAIGN_ID,
        "variance_id": "VAR-PGD-IL-001",
        "iteration": 1,
        "evidence_scope": "PHYSICAL",
        "input_mode": "RUN_RECORDS",
        "bench_test_artifacts": [path.name for path in bench_test_paths],
        "engine_input": {
            "input_type": "VARIANCE_ANALYSIS",
            "analyses": ["VARIANCE_COMPONENTS", "POWER_ANALYSIS", "CONSISTENCY_CHECK"],
            "preregistered_delta": 0.5,
            "comparison_arms": {
                "arm_a_group_reference": "ARM-CANDIDATE",
                "arm_b_group_reference": "ARM-REFERENCE",
            },
            "replicate_structure": [
                {"level": "BATCH", "n": 2, "group_reference": "ARM-CANDIDATE", "batch_reference": BATCH_CANDIDATE[0], "sample_reference": BATCH_CANDIDATE[1]},
                {"level": "BATCH", "n": 2, "group_reference": "ARM-REFERENCE", "batch_reference": BATCH_REFERENCE[0], "sample_reference": BATCH_REFERENCE[1]},
                {"level": "BENCH", "n": 2, "group_reference": "RUN-PGD-IL-R1A-1", "batch_reference": BATCH_CANDIDATE[0], "sample_reference": BATCH_CANDIDATE[1]},
                {"level": "BENCH", "n": 2, "group_reference": "RUN-PGD-IL-R1A-2", "batch_reference": BATCH_CANDIDATE[0], "sample_reference": BATCH_CANDIDATE[1]},
                {"level": "BENCH", "n": 2, "group_reference": "RUN-PGD-IL-R1B-1", "batch_reference": BATCH_REFERENCE[0], "sample_reference": BATCH_REFERENCE[1]},
                {"level": "BENCH", "n": 2, "group_reference": "RUN-PGD-IL-R1B-2", "batch_reference": BATCH_REFERENCE[0], "sample_reference": BATCH_REFERENCE[1]},
            ],
            "observations": [
                {
                    "observation_reference": reference,
                    "level": "MEASUREMENT",
                    "group_reference": arm,
                    "sample_id": sample,
                    "batch_id": batch,
                    "run_reference": run,
                    "value": value,
                    "at": ("2026-10-10T09:00:00Z" if value < 3 else "2026-10-11T09:00:00Z"),
                    "event_occurred": True,
                    "event_time": value,
                }
                for reference, arm, sample, batch, run, value in observations
            ],
            "censoring": [
                {
                    "observation_reference": reference,
                    "event_occurred": True,
                    "event_time": value,
                    "censoring_type": "NONE",
                    "stop_reason": "event observed inside the protocol window",
                }
                for reference, arm, sample, batch, run, value in observations
            ],
            "intervention_events": [],
        },
        "evidence": [
            {
                "evidence_id": "E-VAR-IL-001",
                "statement": f"{SIM}: variance assessment VAR-PGD-IL-001 is recorded for contract validation only.",
                "source": SIM,
                "status": "ASSUMED",
            }
        ],
    }


def bench_registration_input() -> dict:
    """The BENCH_RESOURCE_REGISTERED request for bench-registration's bench producer.

    The campaign carrier may only draw its slots from a bench registered for the same
    project and evidence scope, so the loop needs a real bench record: this request is
    driven through the skill in E2E-2 before the campaign is opened.
    """
    return {
        "bench": {
            "bench_id": BENCH_ID,
            "project_reference": PROJECT_ID,
            "bench_name": "Precision-gear grease inner-loop bench (acceptance fixture)",
            "location": "Synthetic bench location",
            "availability_window": [
                {"window_id": "W-1", "start": "2026-11-01", "end": "2026-12-30"},
                {"window_id": "W-2", "start": "2027-01-01", "end": "2027-03-01"},
            ],
            "cycle_days": 30,
            "cost_per_run": {"value": 12000, "unit": "CNY/run", "source": SIM},
            "source": SIM,
            "evidence_id": "EV-BENCH-PGD-IL-01",
            "evidence_scope": "PHYSICAL",
            "evidence": [
                {
                    "evidence_id": "EV-BENCH-PGD-IL-01",
                    "statement": f"{SIM}: bench availability supplied for contract validation only; not a booked capacity.",
                    "source": SIM,
                    "status": "ASSUMED",
                }
            ],
        }
    }


def round_entry(iteration: int, samples: list[str], *, stop_state: str = "CONTINUE",
                screening: str | None = None, variance: str | None = None, model: str | None = None,
                next_batch: str | None = None, bench_tests: list[str] | None = None) -> dict:
    """One campaign round entry (campaign.schema.json's iteration shape)."""
    return {
        "iteration": iteration,
        "samples": list(samples),
        "stop_state": stop_state,
        "screening_reference": screening,
        "variance_reference": variance,
        "model_reference": model,
        "next_batch_reference": next_batch,
        "bench_test_references": list(bench_tests or []),
    }


def campaign_request(current_iteration: int, iterations: list[dict]) -> dict:
    """The CAMPAIGN_OPENED request for bench-registration's campaign producer.

    ``max_iterations`` is omitted on purpose: the producer reads the contract's own
    published cap and records that provenance on the artifact, so the loop's only bound is
    never a number this test invented. The request references the bench record the
    workspace itself produced (written as ``bench.json`` in the same directory).
    """
    return {
        "project_artifact": "project.json",
        "bench_artifacts": ["bench.json"],
        "campaign": {
            "campaign_id": CAMPAIGN_ID,
            "project_reference": PROJECT_ID,
            "bench_references": [BENCH_ID],
            "current_iteration": current_iteration,
            "iterations": iterations,
            "pairing_design": {
                "paired": True,
                "description": f"{SIM}: the A/B pair runs in the same round and is swapped in the next round, so bench-to-bench drift cancels.",
            },
            "evidence_scope": "PHYSICAL",
            "source": SIM,
            "evidence_id": "E-CMP-IL-001",
            "evidence": [
                {
                    "evidence_id": "E-CMP-IL-001",
                    "statement": f"{SIM}: campaign {CAMPAIGN_ID} records the rounds supplied above.",
                    "source": SIM,
                    "status": "ASSUMED",
                }
            ],
        },
    }


def next_batch_request(campaign_name: str, design_name: str, variance_name: str) -> dict:
    """The NEXT_BATCH_DECIDED request for doe-design's next_batch producer.

    The two competing explanations are declared here and every proposed sample quotes its
    discriminating pair from those declarations, because the producer refuses to compose a
    hypothesis the input did not declare. The iteration pair is not supplied: the builder
    derives it from the campaign carrier.
    """
    return {
        "campaign_artifact": campaign_name,
        "experiment_design_artifact": design_name,
        "variance_artifact": variance_name,
        "next_batch": {
            "next_batch_id": "NEXT-PGD-IL-001",
            "stop_state": "CONTINUE",
            "bench_slots_required": 2,
            "information_gain_basis": (
                f"{SIM}: the round-2 pair is the round-1 pair swapped, so the A-minus-B contrast cancels "
                "bench-to-bench drift instead of measuring it; no single arm separates the two explanations."
            ),
            "competing_explanations": [
                {
                    "explanation_id": "EXPL-FORMULATION-EFFECT",
                    "statement": "The round-1 candidate/reference difference follows the formulation and travels with the formula.",
                },
                {
                    "explanation_id": "EXPL-BENCH-DRIFT",
                    "statement": "The round-1 difference is bench-to-bench drift that follows the run order.",
                },
            ],
            "proposed_samples": [
                {
                    "sample_reference": BATCH_ROUND_2[1],
                    "hypothesis": "EXPL-FORMULATION-EFFECT",
                    "separates": ["EXPL-FORMULATION-EFFECT", "EXPL-BENCH-DRIFT"],
                },
                {
                    "sample_reference": BATCH_REFERENCE[1],
                    "hypothesis": "EXPL-BENCH-DRIFT",
                    "separates": ["EXPL-FORMULATION-EFFECT", "EXPL-BENCH-DRIFT"],
                },
            ],
            "next_round_budget": {"bench_slots_remaining": 2, "calendar_days_remaining": 60},
            "evidence": [
                {
                    "evidence_id": "E-NB-IL-001",
                    "statement": f"{SIM}: the round-1 variance assessment records a consistent arm difference and round 1 ended CONTINUE.",
                    "source": SIM,
                    "status": "ASSUMED",
                },
                {
                    "evidence_id": "E-NB-IL-002",
                    "statement": f"{SIM}: the round's design declares two bench positions for the next round.",
                    "source": SIM,
                    "status": "ASSUMED",
                },
            ],
        },
    }


def model_probe_input(project_path: Path, artifact_names: dict[str, str]) -> dict:
    """The grease-route statistical-analysis request, used only to locate the MODEL_BUILT gap.

    C-1/E-2 shape: the challenge path and the experiment path are both legal omissions on
    the grease route, so the probe does not name them; everything the route DOES carry --
    the four inner-loop artifacts plus the campaign ledger (W1 shape: the counter has
    advanced past the recorded round) -- is supplied by path.
    """
    return {
        "project_artifact": project_path.name,
        "failure_ctq_artifact": "failure_ctq.json",
        "test_method_artifact": "test_method.json",
        "design_space_artifact": artifact_names["design_space"],
        "experiment_design_artifact": artifact_names["experiment_design"],
        "batch_artifact": artifact_names["batch"],
        "screening_artifact": artifact_names["screening"],
        "bench_test_artifact": artifact_names["bench_test"],
        "variance_artifact": artifact_names["variance"],
        "campaign_artifact": artifact_names["campaign"],
        "analysis": {
            "model_id": "MODEL-PGD-IL-001",
            "requested_analyses": ["ANOVA", "REGRESSION", "RESIDUAL"],
            "response_references": [{"ctq_reference": CTQ_ID, "test_method_reference": METHOD_ID}],
            "evidence": [
                {
                    "evidence_id": "E-MODEL-IL-001",
                    "statement": f"{SIM}: analysis scope supplied for contract validation only.",
                    "source": SIM,
                    "status": "ASSUMED",
                }
            ],
        },
    }


# ---------------------------------------------------------------------------
# state-machine event construction (contracts/state-machine.json shape)
# ---------------------------------------------------------------------------


def sm_state(stage: str, version: int, evidence_ids: list[str], question: str) -> dict:
    return {
        "project_id": PROJECT_ID,
        "stage": stage,
        "status": "ACTIVE",
        "version": version,
        "decision_question": question,
        "evidence": list(evidence_ids),
        "evidence_scope": "PHYSICAL",
    }


def sm_event(before: dict, after: dict, *, iteration: int | None = None,
             project_type: str = PROJECT_TYPE) -> dict:
    event = {"kind": "GO", "gate_status": "GO", "project_type": project_type, "before": before, "after": after}
    if iteration is not None:
        event["iteration"] = iteration
    return event


ROUND_1_DECISION_QUESTION = "Does round 1 separate the candidate grease from the reference?"


def ring_edge_event(validator, *, iteration: int | None, round_1_evidence: list[str],
                    appended: str = "ITER-2:batch.json", drop_round_1: bool = False,
                    version_before: int = 7, after_version: int | None = None):
    """The declared ring edge VARIANCE_ASSESSED -> BATCH_PRODUCED as a state-machine event.

    The before state's evidence list is the round-1 record set (one id per artifact the
    workspace actually produced), and the after state appends the new round's first
    record -- exactly the append-only shape the contract's ring-edge branch demands.
    ``after_version`` overrides the after state's version so the version-preservation rule
    can be exercised as a NEGATIVE (the validator's refusal), instead of being asserted
    on a pair this helper built to satisfy it.
    """
    after_evidence = [appended] if drop_round_1 else [*round_1_evidence, appended]
    before = sm_state("VARIANCE_ASSESSED", version_before, round_1_evidence, ROUND_1_DECISION_QUESTION)
    after = sm_state("BATCH_PRODUCED", version_before if after_version is None else after_version,
                     after_evidence, ROUND_1_DECISION_QUESTION)
    return validator.validate(sm_event(before, after, iteration=iteration)), before, after


# ---------------------------------------------------------------------------
# scenario E2E-2: one inner-loop round, the ring edge, iteration 1 -> 2
# ---------------------------------------------------------------------------


def stage_scripts() -> dict[str, Path]:
    return {
        "bench": SKILLS / "bench-registration" / "scripts",
        "campaign": SKILLS / "bench-registration" / "scripts",
        "batch": SKILLS / "grease-batch" / "scripts",
        "screening": SKILLS / "grease-screening" / "scripts",
        "bench_test": SKILLS / "experiment-import" / "scripts",
        "variance": SKILLS / "variance-assessment" / "scripts",
        "next_batch": SKILLS / "doe-design" / "scripts",
        "model": SKILLS / "statistical-analysis" / "scripts",
    }


def scenario_inner_loop_iteration(router, validator) -> dict:
    """E2E-2: full round -> ring edge ALLOW -> iteration increments, round 1 retained."""
    scripts = stage_scripts()
    result: dict = {}
    with tempfile.TemporaryDirectory() as temporary:
        ws = Path(temporary)

        # --- upstream scaffolding the inner loop consumes -------------------
        project_path = ws / "project.json"
        write_json(project_path, project_artifact())
        check_schema("project", project_path)
        design_space_path = ws / "design_space.json"
        write_json(design_space_path, design_space_artifact())
        check_schema("design_space", design_space_path)
        experiment_design_path = ws / "experiment_design.json"
        write_json(experiment_design_path, experiment_design_artifact())
        check_schema("experiment_design", experiment_design_path)
        naming = run(NAMING_SCRIPT, ws)
        assert naming.returncode == 0 and naming.stdout.strip().splitlines()[-1].startswith("PASS"), naming.stdout
        print("E2E-2 ok: upstream scaffolding (project/design_space/experiment_design) schema-valid, naming PASS")

        # --- BATCH_PRODUCED: the round's two samples (batch production) --------
        batch_paths: dict[str, Path] = {}
        sample_paths: dict[str, Path] = {}
        for index, (batch_id, sample_id, formula) in enumerate((BATCH_CANDIDATE, BATCH_REFERENCE)):
            request = ws / f"input-batch-{index}.json"
            write_json(request, batch_input(project_path, design_space_path, experiment_design_path,
                                            batch_id, sample_id, formula))
            artifact = ws / ("batch.json" if index == 0 else f"batch-{PROJECT_ID}-{batch_id}.json")
            run_ok(scripts["batch"] / "preflight_grease_batch.py", request)
            run_ok(scripts["batch"] / "build_batch_artifact.py", request, artifact)
            run_ok(scripts["batch"] / "validate_batch_artifact.py", artifact)
            record = check_schema("batch", artifact)
            assert record["decision"] == "GO", record
            # grease-batch writes the sample beside the batch record: the canonical
            # ``batch.json`` is paired with ``sample.json``, a suffixed batch record with
            # ``<stem>.sample.json`` (see build_batch_artifact.sample_output_path).
            sample_path = ws / "sample.json" if index == 0 else artifact.with_name(artifact.stem + ".sample.json")
            check_schema("sample", sample_path)
            batch_paths[sample_id] = artifact
            sample_paths[sample_id] = sample_path
        assert read_json(ws / "sample.json")["sample_id"] == BATCH_CANDIDATE[1]
        print("E2E-2 ok: BATCH_PRODUCED x2 (candidate + reference) built and validated by grease-batch")

        # --- SCREENING_PASSED: the candidate clears the screen ----------------
        screening_request = ws / "input-screening.json"
        write_json(screening_request, screening_input(
            project_path, batch_paths[BATCH_CANDIDATE[1]], sample_paths[BATCH_CANDIDATE[1]],
            "SCR-PGD-IL-001", BATCH_CANDIDATE[1], failing_index=None, bench_request=BATCH_CANDIDATE[1],
        ))
        screening_path = ws / "screening.json"
        run_ok(scripts["screening"] / "preflight_grease_screening.py", screening_request)
        run_ok(scripts["screening"] / "build_screening_artifact.py", screening_request, screening_path)
        run_ok(scripts["screening"] / "validate_screening_artifact.py", screening_path)
        screening = check_schema("screening", screening_path)
        assert screening["overall_verdict"] == "PASS", screening
        assert screening["gate_to_bench"] == "RELEASED" and screening["decision"] == "GO", screening
        # The reference arm is screened the same way: both samples of the paired round
        # must clear the screen, because the bench gate (E-3) releases a slot only for a
        # sample its own PASS/RELEASED screening record covers.
        reference_screening_request = ws / "input-screening-reference.json"
        write_json(reference_screening_request, screening_input(
            project_path, batch_paths[BATCH_REFERENCE[1]], sample_paths[BATCH_REFERENCE[1]],
            "SCR-PGD-IL-002", BATCH_REFERENCE[1], failing_index=None, bench_request=BATCH_REFERENCE[1],
        ))
        reference_screening_path = ws / "screening-002.json"
        run_ok(scripts["screening"] / "preflight_grease_screening.py", reference_screening_request)
        run_ok(scripts["screening"] / "build_screening_artifact.py", reference_screening_request, reference_screening_path)
        run_ok(scripts["screening"] / "validate_screening_artifact.py", reference_screening_path)
        reference_screening = check_schema("screening", reference_screening_path)
        assert reference_screening["overall_verdict"] == "PASS", reference_screening
        assert reference_screening["gate_to_bench"] == "RELEASED", reference_screening
        print("E2E-2 ok: SCREENING_PASSED built and validated for both arms; gate_to_bench RELEASED")

        # --- BENCH_TESTED: four bench runs of the round -----------------------
        screening_by_sample = {
            BATCH_CANDIDATE[1]: screening_path,
            BATCH_REFERENCE[1]: reference_screening_path,
        }
        bench_test_paths: list[Path] = []
        for index, (run_id, batch_id, sample_id, event_time) in enumerate(ROUND_1_RUNS):
            request = ws / f"input-bench-test-{index}.json"
            write_json(request, bench_test_input(project_path, run_id, batch_id, sample_id, 1, event_time,
                                                 [screening_by_sample[sample_id].name]))
            artifact = ws / ("bench_test.json" if index == 0 else f"bench_test-{PROJECT_ID}-{run_id}.json")
            preflight = run_ok(scripts["bench_test"] / "preflight_experiment_import.py", request)
            if index == 0:
                # E-3: the run that may spend a slot prints the release conclusion, naming
                # the screening record that released its sample.
                assert f"released by screening {screening['screening_id']}" in preflight.stdout, preflight.stdout
            run_ok(scripts["bench_test"] / "build_bench_test_artifact.py", request, artifact)
            run_ok(scripts["bench_test"] / "validate_bench_test_artifact.py", artifact)
            record = check_schema("bench_test", artifact)
            assert record["stage"] == "BENCH_TESTED" and record["campaign_iteration"] == 1, record
            bench_test_paths.append(artifact)
        found = bench_test_records(ws)
        assert len(found) == 4, found
        result["bench_test_records_in_round_1"] = found
        print(f"E2E-2 ok: BENCH_TESTED x{len(bench_test_paths)} built and validated by experiment-import (bench path)")
        # E-3: the field set is closed -- a bench request that omits screening_artifacts is
        # refused by name; the gate never assumes a screen it was not given.
        missing_screening = bench_test_input(project_path, "RUN-PGD-IL-NOSCR", BATCH_CANDIDATE[0],
                                             BATCH_CANDIDATE[1], 1, 2.5, [screening_path.name])
        del missing_screening["screening_artifacts"]
        missing_screening_path = ws / "input-bench-test-no-screening.json"
        write_json(missing_screening_path, missing_screening)
        missing_refused = run(scripts["bench_test"] / "preflight_experiment_import.py", missing_screening_path)
        assert missing_refused.returncode != 0 and "screening_artifacts" in missing_refused.stdout, missing_refused.stdout
        print("E2E-2 ok: a bench request without screening_artifacts is refused by name (E-3)")

        # --- VARIANCE_ASSESSED: the round's difference is real ----------------
        variance_request = ws / "input-variance.json"
        write_json(variance_request, variance_input(project_path, bench_test_paths))
        variance_path = ws / "variance.json"
        run_ok(scripts["variance"] / "preflight_variance_assessment.py", variance_request)
        run_ok(scripts["variance"] / "build_variance_artifact.py", variance_request, variance_path)
        run_ok(scripts["variance"] / "validate_variance_artifact.py", variance_path)
        variance = check_schema("variance", variance_path)
        assert variance["verdict"] == "CONSISTENT_DIFFERENCE", variance["verdict"]
        assert variance["decision"] == "GO" and variance["computed_by"] == "ENGINE", variance
        assert variance["iteration"] == 1 and variance["campaign_reference"] == CAMPAIGN_ID, variance
        print("E2E-2 ok: VARIANCE_ASSESSED = CONSISTENT_DIFFERENCE (engine-computed), iteration 1")

        # --- BENCH_RESOURCE_REGISTERED: the bench the campaign draws on --------
        # The campaign gate only accepts slots from a REGISTERED bench of the same
        # project and evidence scope, so the bench is produced by its skill as well.
        bench_request = ws / "input-bench.json"
        write_json(bench_request, bench_registration_input())
        bench_path = ws / "bench.json"
        run_ok(scripts["bench"] / "preflight_bench_registration.py", bench_request)
        run_ok(scripts["bench"] / "build_bench_artifact.py", bench_request, bench_path)
        run_ok(scripts["bench"] / "validate_bench_artifact.py", bench_path)
        bench = check_schema("bench", bench_path)
        assert bench["bench_id"] == BENCH_ID and bench["evidence_scope"] == "PHYSICAL", bench
        assert bench["available_bench_slots"] >= 2, bench
        print(f"E2E-2 ok: BENCH_RESOURCE_REGISTERED built and validated by bench-registration "
              f"({bench['available_bench_slots']} derived slots)")

        # --- CAMPAIGN_OPENED: the loop's carrier, produced by its skill --------
        # W0 (D-1): the campaign is OPENED before round 1 runs, so its ledger is
        # legitimately EMPTY here and current_iteration is 1. The round entries are
        # appended at each round boundary (below), never pre-written at open time.
        campaign_path = ws / "campaign.json"
        campaign_request_path = ws / "input-campaign-opened.json"
        write_json(campaign_request_path, campaign_request(1, []))
        run_ok(scripts["campaign"] / "preflight_campaign_registration.py", campaign_request_path)
        run_ok(scripts["campaign"] / "build_campaign_artifact.py", campaign_request_path, campaign_path)
        run_ok(scripts["campaign"] / "validate_campaign_artifact.py", campaign_path)
        campaign_1 = check_schema("campaign", campaign_path)
        assert campaign_1["campaign_id"] == CAMPAIGN_ID and campaign_1["current_iteration"] == 1, campaign_1
        assert campaign_1["decision"] == "GO", campaign_1
        assert campaign_1["iterations"] == [], campaign_1["iterations"]
        # The request omitted the cap: the artifact must carry the contract's own figure
        # and record where it came from (a cap this loop could see invented would be the
        # one thing the bound cannot be).
        assert campaign_1["max_iterations"] == read_json(CONTRACT)["max_iterations"], campaign_1
        assert any(item.get("source") == "contracts/state-machine.json" for item in campaign_1["evidence"]), campaign_1
        print("E2E-2 ok: CAMPAIGN_OPENED built and validated by bench-registration with an EMPTY ledger "
              "(W0: the campaign is opened before round 1 runs)")

        # --- the round-1 boundary: the ledger gains round 1 (W1) ---------------
        # The entry is composed from the records THIS workspace produced (the sample ids
        # the batches carry, the four bench-test run ids on disk, the screening and
        # variance ids of this round), so the campaign record can be checked against the
        # workspace instead of against another fixture. A round that looped back carries
        # null for the two exit-round references (E2=B).
        round_1_entry = round_entry(
            1,
            [BATCH_CANDIDATE[1], BATCH_REFERENCE[1]],
            screening=read_json(screening_path)["screening_id"],
            variance=read_json(variance_path)["variance_id"],
            bench_tests=[read_json(path)["run_id"] for path in bench_test_paths],
        )
        round_1_request_path = ws / "input-campaign-iteration-1.json"
        write_json(round_1_request_path, campaign_request(2, [round_1_entry]))
        run_ok(scripts["campaign"] / "preflight_campaign_registration.py", round_1_request_path)
        run_ok(scripts["campaign"] / "build_campaign_artifact.py", round_1_request_path, campaign_path)
        run_ok(scripts["campaign"] / "validate_campaign_artifact.py", campaign_path)
        campaign_1 = check_schema("campaign", campaign_path)
        assert campaign_1["current_iteration"] == 2, campaign_1
        assert campaign_1["decision"] == "GO", campaign_1
        # Round 1's entry, as the product stored it, names records that exist on disk.
        stored = campaign_1["iterations"][0]
        assert stored == round_1_entry, stored
        assert read_json(screening_path)["screening_id"] == stored["screening_reference"], stored
        assert read_json(variance_path)["variance_id"] == stored["variance_reference"], stored
        assert [read_json(path)["run_id"] for path in bench_test_paths] == stored["bench_test_references"], stored
        assert all((ws / name).is_file() for name in (screening_path.name, variance_path.name)), stored
        print("E2E-2 ok: the round-1 boundary appended round 1's entry; the ledger stands at iteration 2 "
              "(W1: a CONTINUE round opened the next one)")

        # --- MODEL_BUILT: the probe, on the W1-shape campaign -------------------
        # E-2: the modeling entry consumes the round's own ledger, and it runs after the
        # round boundary has recorded the round (W1 above: the counter stands at 2, the
        # newest entry is round 1 ending CONTINUE with both exit-round references null) --
        # exactly the shape step 14 sees in the real loop. The record below is a labelled
        # fixture (the workspace produces no model), and the probe asserts the skill's REAL
        # refusal: only the two oil-path upstreams this inner-loop-only workspace does not
        # carry. The challenge path (C-1) and the experiment path (E-2) are legal omissions
        # on the grease route, and the contract-UNDECIDED bench_test record must not be
        # refused (WP-14; E2E-1 drives the stage for real on the full route).
        write_json(ws / "model.json", read_json(FIXTURES / "model_round_1.json"))
        model = check_schema("model", ws / "model.json")
        assert model["stage"] == "MODEL_BUILT", model
        probe = run(scripts["model"] / "preflight_statistical_analysis.py",
                    _probe_path(ws, project_path, design_space_path, experiment_design_path,
                                batch_paths[BATCH_CANDIDATE[1]], screening_path, bench_test_paths[0],
                                variance_path, campaign_path))
        assert probe.returncode != 0, probe.stdout
        assert probe.stdout.startswith("HOLD: missing or invalid:"), probe.stdout
        for key in ("failure_ctq_artifact", "test_method_artifact"):
            assert f"{key} cannot be read" in probe.stdout, probe.stdout
        assert "challenge_artifact cannot be read" not in probe.stdout, probe.stdout
        assert "experiment_artifact cannot be read" not in probe.stdout, probe.stdout
        assert MODEL_BUILT_GAP not in probe.stdout, (
            "the contract-UNDECIDED bench_test record must not be refused (WP-14): " + probe.stdout
        )
        # The campaign ledger is supplied and read: no error names it, and none demands it.
        assert "campaign_artifact cannot be read" not in probe.stdout, probe.stdout
        assert "campaign_artifact is required" not in probe.stdout, probe.stdout
        print("E2E-2 ok: statistical-analysis's real refusal on this workspace names only the two oil "
              "upstreams it does not carry (failure_ctq / test_method); the challenge and experiment "
              "paths are legal omissions on the grease route, the contract-UNDECIDED bench_test record "
              "is accepted, and the campaign ledger is consumed (MODEL_BUILT itself is a fixture here, "
              "driven for real by E2E-1)")

        # --- NEXT_BATCH_DECIDED: round 2 proposed by its skill -----------------
        next_batch_request_path = ws / "input-next-batch.json"
        write_json(next_batch_request_path, next_batch_request(campaign_path.name, experiment_design_path.name,
                                                               variance_path.name))
        next_batch_path = ws / "next_batch.json"
        run_ok(scripts["next_batch"] / "preflight_next_batch.py", next_batch_request_path)
        run_ok(scripts["next_batch"] / "build_next_batch_artifact.py", next_batch_request_path, next_batch_path)
        run_ok(scripts["next_batch"] / "validate_next_batch_artifact.py", next_batch_path)
        next_batch = check_schema("next_batch", next_batch_path)
        assert next_batch["stage"] == "NEXT_BATCH_DECIDED", next_batch
        # The iteration pair is DERIVED from the campaign carrier (the request never
        # supplies it); the stop state must agree with the campaign's own round-1 entry,
        # which is what authorises this decision. The carrier's next_batch_reference is a
        # record kept for the reader (E2=B: written only on the exit round, null on a
        # CONTINUE round), so the self-comparison that used to sit here is gone.
        assert (next_batch["from_iteration"], next_batch["to_iteration"]) == (1, 2), next_batch
        assert next_batch["campaign_reference"] == campaign_1["campaign_id"], next_batch
        assert campaign_1["iterations"][0]["next_batch_reference"] is None, campaign_1["iterations"][0]
        assert next_batch["stop_state"] == campaign_1["iterations"][0]["stop_state"] == "CONTINUE", next_batch
        assert next_batch["bench_slots_required"] == len(next_batch["proposed_samples"]) == 2, next_batch
        assert next_batch["information_gain_basis"].strip(), next_batch
        # Every proposed sample's discrimination text is COMPOSED from the explanations
        # the request declared (statement text, joined by the schema's own " vs "
        # separator): the gate never invents a hypothesis, it spells out the declared ones.
        requested = read_json(next_batch_request_path)["next_batch"]
        statement_by_id = {item["explanation_id"]: item["statement"] for item in requested["competing_explanations"]}
        assert len(statement_by_id) >= 2, requested
        for sample, requested_sample in zip(next_batch["proposed_samples"], requested["proposed_samples"]):
            assert sample["sample_reference"] == requested_sample["sample_reference"], sample
            assert sample["hypothesis"] == statement_by_id[requested_sample["hypothesis"]], sample
            assert sample["discriminates"] == " vs ".join(
                statement_by_id[item] for item in requested_sample["separates"]
            ), sample
        print("E2E-2 ok: NEXT_BATCH_DECIDED built and validated by doe-design; round 2 proposed "
              "(from_iteration 1 -> to_iteration 2, CONTINUE) with its declared explanations")

        round_1_digests = artifact_digests(ws)
        # The round-1 record set the ring edge must carry forward, one evidence id per
        # artifact this workspace actually produced (the campaign counter record is the
        # iteration bookkeeping, not a round record).
        frozen_round_1 = sorted(name for name in round_1_digests if name != "campaign.json")
        round_1_evidence = [f"ITER-1:{name}" for name in frozen_round_1]

        # --- the ring edge: router ALLOW + state machine ALLOW ---------------
        router_ring = router.decide(
            {"stage": "VARIANCE_ASSESSED", "status": "ACTIVE", "evidence_scope": "PHYSICAL", "project_type": PROJECT_TYPE},
            "BATCH_PRODUCED",
        )
        assert router_ring["decision"] == "ALLOW", router_ring
        assert router_ring["reason"] == "declared inner-loop edge permitted", router_ring
        assert router_ring["skill"] == "grease-batch", router_ring
        # The ring is an ADDITION to the route, never a replacement: the ordinary next
        # step VARIANCE_ASSESSED -> MODEL_BUILT stays legal.
        router_normal = router.decide(
            {"stage": "VARIANCE_ASSESSED", "status": "ACTIVE", "evidence_scope": "PHYSICAL", "project_type": PROJECT_TYPE},
            "MODEL_BUILT",
        )
        assert router_normal["decision"] == "ALLOW" and router_normal["reason"] == "single-step advancement permitted", router_normal
        print("E2E-2 ok: router ALLOWs the ring edge VARIANCE_ASSESSED -> BATCH_PRODUCED "
              "and still ALLOWs the route step VARIANCE_ASSESSED -> MODEL_BUILT")

        # --- round 2: the ring edge leads to a materialised BATCH_PRODUCED ----
        # The router ALLOW above authorizes the advance to BATCH_PRODUCED; the round-2
        # batch record is what that stage now holds.
        round2_request = ws / "input-batch-round2.json"
        write_json(round2_request, batch_input(project_path, design_space_path, experiment_design_path, *BATCH_ROUND_2))
        round2_batch = ws / f"batch-{PROJECT_ID}-{BATCH_ROUND_2[0]}.json"
        run_ok(scripts["batch"] / "preflight_grease_batch.py", round2_request)
        run_ok(scripts["batch"] / "build_batch_artifact.py", round2_request, round2_batch)
        run_ok(scripts["batch"] / "validate_batch_artifact.py", round2_batch)
        round2_record = check_schema("batch", round2_batch)
        assert round2_record["stage"] == "BATCH_PRODUCED", round2_record
        assert round2_record["batch_id"] == BATCH_ROUND_2[0], round2_record
        print("E2E-2 ok: round 2's BATCH_PRODUCED record built and validated by grease-batch")

        # The ring event carries the incremented iteration; the round-1 record set is
        # carried forward and the round-2 batch record is appended. The pair itself is
        # assembled by this test (the validator takes an event, it does not advance a
        # stored state), so the pair is NOT asserted against itself: what is asserted is
        # (a) the validator's ALLOW verdict, (b) that every record the pair names exists
        # on disk, and (c) below, that the SAME rules refuse a version bump and a dropped
        # round -- the refusals are real product output.
        appended = f"ITER-2:{round2_batch.name}"
        # W1 has already advanced the counter (the round that ended CONTINUE opened the
        # next one), and the decision's pair is derived from the newest recorded entry.
        assert campaign_1["current_iteration"] == 2, campaign_1
        assert next_batch["to_iteration"] == campaign_1["current_iteration"], next_batch
        missing_round_1_records = [name for name in frozen_round_1 if not (ws / name).is_file()]
        assert missing_round_1_records == [], missing_round_1_records
        assert (ws / round2_batch.name).is_file(), round2_batch
        reason, before, after = ring_edge_event(
            validator, iteration=next_batch["to_iteration"], round_1_evidence=round_1_evidence, appended=appended
        )
        assert reason is None, f"ring edge must be ALLOWed by the state machine: {reason}"
        print("E2E-2 ok: state machine ALLOWs the ring edge at iteration "
              f"{next_batch['to_iteration']} over all {len(round_1_evidence)} round-1 records "
              f"(each named record exists on disk) with the round-2 batch appended")

        # Negative counterparts: the ALLOW above is a real gate, not a validator that
        # accepts everything. Each refusal below is the validator's OWN wording for the
        # rule the assembled ALLOW pair satisfies by construction, so a relaxed rule
        # fails here instead of passing silently.
        contract = read_json(CONTRACT)
        cap = contract["max_iterations"]
        drop_reason, _, _ = ring_edge_event(validator, iteration=2, round_1_evidence=round_1_evidence,
                                            appended=appended, drop_round_1=True)
        assert drop_reason == RING_DROP_REASON, drop_reason
        no_counter_reason, _, _ = ring_edge_event(validator, iteration=None, round_1_evidence=round_1_evidence,
                                                  appended=appended)
        assert no_counter_reason == RING_COUNTER_REASON, no_counter_reason
        over_cap_reason, _, _ = ring_edge_event(validator, iteration=cap + 1, round_1_evidence=round_1_evidence,
                                                appended=appended)
        assert over_cap_reason == f"iteration {cap + 1} exceeds max_iterations {cap}; stop the inner loop and record PIVOT or KILL", over_cap_reason
        version_bump_reason, _, _ = ring_edge_event(validator, iteration=2, round_1_evidence=round_1_evidence,
                                                    appended=appended, after_version=8)
        assert version_bump_reason == RING_VERSION_REASON, version_bump_reason
        print("E2E-2 ok: dropping round-1 evidence / omitting the iteration counter / exceeding "
              f"max_iterations={cap} / bumping the project version on the ring edge are each REFUSED")

        # campaign iteration 2 is produced by the SAME skill, and its round-1 entry is the
        # one the iteration-1 artifact recorded (read back from disk, never re-authored):
        # the iteration advance runs through the producer, and the producer must refuse a
        # record that drops round 1 or exceeds its own cap. Round 2 ends CONTINUE, so the
        # counter stands at the round that round opened (W1: 3).
        campaign_2_request_path = ws / "input-campaign-iteration-2.json"
        round_2_entry = round_entry(2, [BATCH_ROUND_2[1]], next_batch=None)
        write_json(campaign_2_request_path, campaign_request(3, [stored, round_2_entry]))
        run_ok(scripts["campaign"] / "preflight_campaign_registration.py", campaign_2_request_path)
        run_ok(scripts["campaign"] / "build_campaign_artifact.py", campaign_2_request_path, campaign_path)
        run_ok(scripts["campaign"] / "validate_campaign_artifact.py", campaign_path)
        campaign_2 = check_schema("campaign", campaign_path)
        assert campaign_2["current_iteration"] == 3, campaign_2
        assert campaign_2["decision"] == "GO", campaign_2
        assert campaign_2["iterations"][0] == stored, campaign_2["iterations"]
        assert [entry["iteration"] for entry in campaign_2["iterations"]] == [1, 2], campaign_2["iterations"]
        assert campaign_2["iterations"][1]["samples"] == [BATCH_ROUND_2[1]], campaign_2["iterations"][1]
        assert campaign_2["max_iterations"] == cap, campaign_2

        # (i) A campaign that records ONLY round 2 is refused: rounds are oldest first,
        # so the loop cannot drop the round it advanced past.
        dropped_request = ws / "input-campaign-dropped-round-1.json"
        write_json(dropped_request, campaign_request(3, [round_entry(2, [BATCH_ROUND_2[1]])]))
        dropped_probe = run(scripts["campaign"] / "preflight_campaign_registration.py", dropped_request)
        assert dropped_probe.returncode != 0 and CAMPAIGN_ROUND_ORDER_GAP in dropped_probe.stdout, dropped_probe.stdout
        # (ii) A campaign whose current_iteration exceeds its own cap is refused.
        over_cap_request = ws / "input-campaign-over-cap.json"
        over_cap_payload = campaign_request(2, [stored, round_2_entry])
        over_cap_payload["campaign"]["max_iterations"] = 1
        write_json(over_cap_request, over_cap_payload)
        over_cap_probe = run(scripts["campaign"] / "preflight_campaign_registration.py", over_cap_request)
        assert over_cap_probe.returncode != 0 and CAMPAIGN_CAP_GAP in over_cap_probe.stdout, over_cap_probe.stdout
        print("E2E-2 ok: campaign iteration 2 built and validated by bench-registration; dropping round 1 and "
              "exceeding the campaign's own cap are each REFUSED by its gate")

        # The round-1 records on disk are byte-identical after the ring advance.
        # campaign.json is the one record that legitimately moves: it is where
        # current_iteration lives, and its round-1 entry was asserted unchanged above.
        after_digests = artifact_digests(ws)
        changed = {
            name: (round_1_digests[name], after_digests[name])
            for name in round_1_digests
            if name != "campaign.json" and name in after_digests and round_1_digests[name] != after_digests[name]
        }
        assert changed == {}, changed
        missing = sorted(name for name in round_1_digests if name not in after_digests)
        assert missing == [], missing
        frozen_round_1 = [name for name in round_1_digests if name != "campaign.json"]
        print(f"E2E-2 ok: all {len(frozen_round_1)} round-1 artifacts other than the campaign counter record "
              "are byte-identical after the ring advance (nothing was voided)")

        result["workspace"] = str(ws)
        result["campaign_1_iteration"] = campaign_1["current_iteration"]
        result["campaign_2_iteration"] = campaign_2["current_iteration"]

    # The round 1 artifacts no longer exist once the temp workspace is gone; the
    # counts below are the recorded evidence of what was asserted above.
    return result


def _probe_path(ws: Path, project_path, design_space_path, experiment_design_path,
                batch_path, screening_path, bench_test_path, variance_path, campaign_path) -> Path:
    request = ws / "input-model-probe.json"
    write_json(request, model_probe_input(project_path, {
        "design_space": design_space_path.name,
        "experiment_design": experiment_design_path.name,
        "batch": batch_path.name,
        "screening": screening_path.name,
        "bench_test": bench_test_path.name,
        "variance": variance_path.name,
        "campaign": campaign_path.name,
    }))
    return request


# ---------------------------------------------------------------------------
# scenario E2E-3: the failed screen remakes the batch without a bench slot
# ---------------------------------------------------------------------------


def scenario_screening_rework(router, validator) -> dict:
    """E2E-3: screen FAIL -> rework edge ALLOW, batch remade, no bench_test record anywhere."""
    scripts = stage_scripts()
    with tempfile.TemporaryDirectory() as temporary:
        ws = Path(temporary)

        project_path = ws / "project.json"
        write_json(project_path, project_artifact())
        check_schema("project", project_path)
        design_space_path = ws / "design_space.json"
        write_json(design_space_path, design_space_artifact())
        check_schema("design_space", design_space_path)
        experiment_design_path = ws / "experiment_design.json"
        write_json(experiment_design_path, experiment_design_artifact())
        check_schema("experiment_design", experiment_design_path)

        # --- the batch the failed round produced -----------------------------
        batch_request = ws / "input-batch.json"
        write_json(batch_request, batch_input(project_path, design_space_path, experiment_design_path, *BATCH_CANDIDATE))
        batch_path = ws / "batch.json"
        run_ok(scripts["batch"] / "preflight_grease_batch.py", batch_request)
        run_ok(scripts["batch"] / "build_batch_artifact.py", batch_request, batch_path)
        run_ok(scripts["batch"] / "validate_batch_artifact.py", batch_path)
        batch = check_schema("batch", batch_path)
        assert batch["decision"] == "GO" and batch["batch_verdict"] == "VALID", batch
        sample_path = ws / "sample.json"
        check_schema("sample", sample_path)
        print("E2E-3 ok: the failed round's BATCH_PRODUCED record is released (batch_verdict VALID, decision GO)")

        # --- the physical screen FAILs ---------------------------------------
        screening_request = ws / "input-screening.json"
        write_json(screening_request, screening_input(
            project_path, batch_path, sample_path, "SCR-PGD-IL-001", BATCH_CANDIDATE[1],
            failing_index="DROPPING_POINT", bench_request=None,
        ))
        screening_path = ws / "screening.json"
        run_ok(scripts["screening"] / "preflight_grease_screening.py", screening_request)
        run_ok(scripts["screening"] / "build_screening_artifact.py", screening_request, screening_path)
        run_ok(scripts["screening"] / "validate_screening_artifact.py", screening_path)
        screening = check_schema("screening", screening_path)
        assert screening["overall_verdict"] == "FAIL", screening
        assert screening["gate_to_bench"] == "BLOCKED", screening
        assert screening["decision"] == "HOLD", screening
        # N14: a failed sample must not even be requested for a bench slot.
        n14_request = ws / "input-screening-bench-request.json"
        write_json(n14_request, screening_input(
            project_path, batch_path, sample_path, "SCR-PGD-IL-001", BATCH_CANDIDATE[1],
            failing_index="DROPPING_POINT", bench_request=BATCH_CANDIDATE[1],
        ))
        n14 = run(scripts["screening"] / "preflight_grease_screening.py", n14_request)
        assert n14.returncode != 0 and "must not consume a bench slot" in n14.stdout, n14.stdout
        print("E2E-3 ok: SCREENING_PASSED recorded FAIL -> gate_to_bench BLOCKED -> decision HOLD, "
              "and the bench request for the failed sample is refused (N14)")
        # E-3: the bench side now refuses the same sample on its OWN evidence. The bench
        # request names this round's FAIL/BLOCKED screening record and the bench gate
        # resolves it (instead of trusting the reference), so a sample the screen failed
        # cannot even be documented as having spent a slot. The refusal names the sample
        # AND the screening id.
        bench_refused_request = ws / "input-bench-refused.json"
        write_json(bench_refused_request, bench_test_input(
            project_path, "RUN-PGD-IL-RW-1", BATCH_CANDIDATE[0], BATCH_CANDIDATE[1], 1, 2.5,
            [screening_path.name],
        ))
        bench_refused = run(scripts["bench_test"] / "preflight_experiment_import.py", bench_refused_request)
        assert bench_refused.returncode != 0, bench_refused.stdout
        assert BATCH_CANDIDATE[1] in bench_refused.stdout, bench_refused.stdout
        assert "SCR-PGD-IL-001" in bench_refused.stdout, bench_refused.stdout
        print("E2E-3 ok: the bench gate refuses the failed screen's sample on its own evidence "
              "(the refusal names " + BATCH_CANDIDATE[1] + " and SCR-PGD-IL-001)")

        # --- the rework edge: the router ALLOWs SCREENING_PASSED -> BATCH_PRODUCED ---
        # The cap (`max_iterations`) is measured in bench rounds and governs the
        # LOOP_BACK edge only; a REWORK remakes the batch without consuming a bench
        # slot (contract `loop_edges[1].note`), so the rework edge stays ALLOWed even
        # at the cap. Asserted at the cap itself: that is the case the old
        # behaviour got wrong.
        assert router.MAX_ITERATIONS == 12, router.MAX_ITERATIONS
        router_rework = router.decide(
            {"stage": "SCREENING_PASSED", "status": "ACTIVE", "evidence_scope": "PHYSICAL",
             "project_type": PROJECT_TYPE, "current_iteration": router.MAX_ITERATIONS},
            "BATCH_PRODUCED",
        )
        assert router_rework["decision"] == "ALLOW", router_rework
        assert router_rework["reason"] == "declared inner-loop edge permitted", router_rework
        assert router_rework["skill"] == "grease-batch", router_rework
        # The normal next step SCREENING_PASSED -> BENCH_TESTED stays legal as well.
        router_normal = router.decide(
            {"stage": "SCREENING_PASSED", "status": "ACTIVE", "evidence_scope": "PHYSICAL", "project_type": PROJECT_TYPE},
            "BENCH_TESTED",
        )
        assert router_normal["decision"] == "ALLOW", router_normal
        print("E2E-3 ok: router ALLOWs the rework edge SCREENING_PASSED -> BATCH_PRODUCED "
              "and still ALLOWs the route step SCREENING_PASSED -> BENCH_TESTED")

        # --- the batch is remade at BATCH_PRODUCED ---------------------------
        rework_request = ws / "input-batch-rework.json"
        write_json(rework_request, batch_input(project_path, design_space_path, experiment_design_path, *BATCH_REWORK))
        rework_batch = ws / f"batch-{PROJECT_ID}-{BATCH_REWORK[0]}.json"
        run_ok(scripts["batch"] / "preflight_grease_batch.py", rework_request)
        run_ok(scripts["batch"] / "build_batch_artifact.py", rework_request, rework_batch)
        run_ok(scripts["batch"] / "validate_batch_artifact.py", rework_batch)
        rework = check_schema("batch", rework_batch)
        assert rework["batch_id"] == BATCH_REWORK[0] and rework["stage"] == "BATCH_PRODUCED", rework
        print("E2E-3 ok: the batch is remade (BATCH_PRODUCED) from the rework edge")

        # A rework consumes no bench round, so the counter stays at 1 (the contract's own
        # fixture go-precision-grease-ring-rework-remakes-the-batch uses iteration 1 too).
        # The event's evidence names the records this workspace actually produced, and the
        # rule the assembled ALLOW pair satisfies by construction -- version preserved,
        # prior evidence retained -- is locked below with the validator's OWN refusals
        # instead of being asserted on the pair itself.
        for name in (batch_path.name, screening_path.name, rework_batch.name):
            assert (ws / name).is_file(), name
        before = sm_state("SCREENING_PASSED", 6,
                          [f"ITER-1:{batch_path.name}", f"ITER-1:{screening_path.name}"],
                          "Can round 1 clear physical screening?")
        after = sm_state("BATCH_PRODUCED", 6,
                         [*before["evidence"], f"ITER-1:{rework_batch.name}"],
                         "Can round 1 clear physical screening?")
        reason = validator.validate(sm_event(before, after, iteration=1))
        assert reason is None, f"rework edge must be ALLOWed by the state machine: {reason}"
        dropped = sm_state("BATCH_PRODUCED", 6, [f"ITER-1:{rework_batch.name}"],
                           "Can round 1 clear physical screening?")
        dropped_reason = validator.validate(sm_event(before, dropped, iteration=1))
        assert dropped_reason == RING_DROP_REASON, dropped_reason
        bumped = sm_state("BATCH_PRODUCED", 7, after["evidence"], "Can round 1 clear physical screening?")
        bumped_reason = validator.validate(sm_event(before, bumped, iteration=1))
        assert bumped_reason == RING_VERSION_REASON, bumped_reason
        print("E2E-3 ok: state machine ALLOWs the rework edge at iteration 1 (the failed screen's record is "
              "retained, the remade batch is appended), and REFUSES dropping that record or bumping the version")

        # --- no bench_test record anywhere in this workspace -----------------
        found = bench_test_records(ws)
        assert found == [], f"a failed screen must not have occupied a bench slot: {found}"
        named = [str(path.relative_to(ws)) for path in sorted(ws.rglob("*")) if "bench_test" in path.name]
        assert named == [], f"no file may even be named after a bench_test record here: {named}"
        scanned = [str(path.relative_to(ws)) for path in sorted(ws.rglob("*.json"))]
        naming = run(NAMING_SCRIPT, ws)
        assert naming.returncode == 0 and naming.stdout.strip().splitlines()[-1].startswith("PASS"), naming.stdout
        print(f"E2E-3 ok: 0 bench_test records in the workspace ({len(scanned)} json files scanned, "
              "name and artifact_type both checked); naming PASS")


# ---------------------------------------------------------------------------
# decision-3 boundary: inter-ring backtracking stays DENIED
# ---------------------------------------------------------------------------


def scenario_ring_edge_fixture_shapes(validator) -> None:
    """The batch-4 ring-edge fixtures are the authoritative shapes this test mirrors.

    ``scripts/validate_state_machine.py`` already runs them in its suite; re-adjudicating
    them here binds this test's expectations (the exact ALLOW/REJECT reasons above) to the
    fixtures' own events, so ring-edge drift fails loudly at the fixture level too.
    """
    valid_by_name = {case["name"]: case for case in read_json(ROOT / "fixtures" / "state-machine" / "valid.json")}
    invalid_by_name = {case["name"]: case for case in read_json(ROOT / "fixtures" / "state-machine" / "invalid.json")}
    for name in (
        "go-precision-grease-ring-rework-remakes-the-batch",
        "go-precision-grease-ring-continues-into-the-next-round",
        "go-precision-grease-third-iteration-keeps-earlier-round-records",
    ):
        assert name in valid_by_name, sorted(valid_by_name)
        assert validator.validate(valid_by_name[name]["event"]) is None, name
        print(f"fixture ok: {name} is still ALLOWed by the state machine")
    for name in (
        "go-precision-grease-cannot-backtrack-across-the-ring",
        "go-cannot-backtrack-from-optimized-to-method-qualification",
        "go-precision-grease-iteration-exceeds-max-iterations",
        "go-precision-grease-ring-edge-cannot-drop-evidence",
        "go-precision-grease-ring-edge-cannot-void-an-earlier-round",
    ):
        assert name in invalid_by_name, sorted(invalid_by_name)
        case = invalid_by_name[name]
        reason = validator.validate(case["event"])
        assert reason == case["expected_reason"], (name, reason, case["expected_reason"])
        print(f"fixture ok: {name} is still REJECTED ({reason})")


def scenario_inter_ring_backtrack_denied(router, validator) -> None:
    """Inter-ring backtracking is not an inner-loop edge and must stay DENIED."""
    contract = read_json(CONTRACT)
    edges = {(edge["from"], edge["to"], edge["kind"]) for edge in contract["loop_edges"]}
    assert edges == {RING_EDGE, REWORK_EDGE}, edges
    assert "BACKTRACK" not in contract["actions"], sorted(contract["actions"])
    listed = run(ROUTE_SCRIPT, "--list-loop-edges", PROJECT_TYPE)
    assert listed.returncode == 0, listed.stdout
    assert listed.stdout.splitlines() == [
        f"{RING_EDGE[0]} -> {RING_EDGE[1]} ({RING_EDGE[2]})",
        f"{REWORK_EDGE[0]} -> {REWORK_EDGE[1]} ({REWORK_EDGE[2]})",
    ], listed.stdout
    # The exemption is route-local: an oil route declares neither endpoint, so it
    # publishes no ring edge at all.
    no_edges = run(ROUTE_SCRIPT, "--list-loop-edges", "NEW_PRODUCT")
    assert no_edges.returncode == 0 and no_edges.stdout.strip() == "", no_edges.stdout
    print("decision-3 lock: the contract publishes exactly the two ring edges (no BACKTRACK action), "
          "and NEW_PRODUCT publishes none")

    denied_router = (
        ("BENCH_TESTED", "TEST_METHODS_QUALIFIED", PROJECT_TYPE),
        ("VARIANCE_ASSESSED", "TEST_METHODS_QUALIFIED", PROJECT_TYPE),
        ("BENCH_TESTED", "BATCH_PRODUCED", PROJECT_TYPE),
        ("SCREENING_PASSED", "TEST_METHODS_QUALIFIED", PROJECT_TYPE),
        ("OPTIMIZED", "TEST_METHODS_QUALIFIED", "NEW_PRODUCT"),
        # Route locality: the ring edge itself must not leak into an oil route.
        ("VARIANCE_ASSESSED", "BATCH_PRODUCED", "NEW_PRODUCT"),
        ("SCREENING_PASSED", "BATCH_PRODUCED", "NEW_PRODUCT"),
    )
    for current, requested, project_type in denied_router:
        result = router.decide(
            {"stage": current, "status": "ACTIVE", "evidence_scope": "PHYSICAL", "project_type": project_type},
            requested,
        )
        assert result["decision"] == "DENY", (current, requested, project_type, result)
        assert result["reason"], result
        print(f"decision-3 ok: router DENYs {project_type} {current} -> {requested} ({result['reason']})")

    denied_state_machine = (
        ("BENCH_TESTED", "TEST_METHODS_QUALIFIED", PROJECT_TYPE, "GO must advance exactly one stage"),
        ("VARIANCE_ASSESSED", "BENCH_TESTED", PROJECT_TYPE, "GO must advance exactly one stage"),
        ("OPTIMIZED", "TEST_METHODS_QUALIFIED", "NEW_PRODUCT", "GO must advance exactly one stage"),
        # Route locality on the state-machine side too.
        ("VARIANCE_ASSESSED", "BATCH_PRODUCED", "NEW_PRODUCT", "GO must advance exactly one stage"),
    )
    for current, target, project_type, expected in denied_state_machine:
        before = sm_state(current, 9, ["ITER-2:bench_test.json"], "Is the bench method discriminating enough?")
        after = sm_state(target, 9, ["ITER-2:bench_test.json"], "Is the bench method discriminating enough?")
        reason = validator.validate(sm_event(before, after, iteration=2, project_type=project_type))
        assert reason == expected, (current, target, project_type, reason)
        print(f"decision-3 ok: state machine DENYs {project_type} {current} -> {target} ({reason})")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    contract = read_json(CONTRACT)
    cap = contract["max_iterations"]
    assert isinstance(cap, int) and cap >= 2, contract
    edges = {(edge["from"], edge["to"], edge["kind"]) for edge in contract["loop_edges"]}
    assert edges == {RING_EDGE, REWORK_EDGE}, edges
    print(f"contract ok: loop_edges = {sorted(edges)}; max_iterations = {cap}")

    # The pack's own state-machine suite must be green: it carries the batch-4 ring-edge
    # cases (valid + invalid) this acceptance test builds on.
    suite = run(STATE_MACHINE_SCRIPT)
    assert suite.returncode == 0, suite.stdout + suite.stderr
    assert "failures=0" in suite.stdout, suite.stdout
    tail = suite.stdout.strip().splitlines()[-1]
    print(f"state-machine fixture suite ok: {tail}")

    router = load_module(ROUTE_SCRIPT, "inner_loop_route_step")
    validator = load_module(STATE_MACHINE_SCRIPT, "inner_loop_state_machine")
    assert router.CONTRACT is not None, router.CONTRACT_ERRORS

    scenario_ring_edge_fixture_shapes(validator)
    inner_loop = scenario_inner_loop_iteration(router, validator)
    scenario_screening_rework(router, validator)
    scenario_inter_ring_backtrack_denied(router, validator)

    print(
        "PASS: E2E-2 inner-loop iteration (ring edge ALLOW, iteration "
        f"{inner_loop['campaign_1_iteration']} -> {inner_loop['campaign_2_iteration']} advanced by re-driving the "
        "bench-registration campaign producer, round-1 records retained on disk), "
        "E2E-3 screening rework (rework edge ALLOW, batch remade, 0 bench_test records), "
        "decision-3 boundary locked (inter-ring backtracking DENY)"
    )
    print(
        "NOT COVERED HERE: MODEL_BUILT is the one inline record (fixtures/inner-loop/model_round_1.json) because "
        "statistical-analysis's remaining oil-route upstreams (failure_ctq / test_method) are not carried by this "
        "inner-loop-only workspace; its real refusal names exactly those two -- the challenge path (C-1) and the "
        "experiment path (E-2) are legal grease-route omissions -- and it no longer demands a verdict from the "
        "contract-UNDECIDED bench_test record. E2E-1 (test_precision_grease_chain.py) drives MODEL_BUILT for real "
        "on the full route. The oil-route upstream stages themselves are not re-driven here."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
