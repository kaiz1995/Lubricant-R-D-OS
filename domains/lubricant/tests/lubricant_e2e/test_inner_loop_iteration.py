"""End-to-end acceptance for the PRECISION_GREASE_DEV inner loop (plan section 8.2 E2E-2 / E2E-3).

Two scenarios plus one locked counter-example, driven over real workspaces with the
pack's own skill scripts (preflight -> build -> validate) and the pack's own decision points
(``skills/lubricant-rd-agent/scripts/route_step.py`` and
``scripts/validate_state_machine.py``):

  E2E-2 inner-loop iteration (``scenario_inner_loop_iteration``)
    One full bench round: batch production (grease-batch) -> screening PASS
    (grease-screening) -> bench runs (experiment-import bench path) -> variance
    CONSISTENT_DIFFERENCE (variance-assessment) -> model update -> next_batch
    (round 2 proposed with its reason).
    Then the declared ring edge VARIANCE_ASSESSED -> BATCH_PRODUCED must be ALLOWed by
    BOTH the router and the state machine, the iteration must advance 1 -> 2, and every
    round-1 record must survive (evidence append-only; the ring is an edge, not a
    ROLLBACK that voids the rounds it passes).

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
    past max_iterations, the exemption leaking into an oil route) are locked here too,
    so the ALLOW assertions above cannot pass against a validator that allows
    everything.

Records with no producing script in the pack (campaign / model / next_batch) are
assembled inline against their schemas from ``fixtures/inner-loop/`` -- the same
treatment ``tests/lubricant_e2e/test_precision_grease_chain.py`` gives campaign.json --
and each such record says so in its own ``uncertainty`` text. The workspace's upstream
scaffolding (project.json / design_space.json / experiment_design.json) is inline
constructed too, because this acceptance test is about the inner loop and not about
re-driving the six upstream oil stages. This file modifies no product code.

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

# The recorded product-code gap that keeps MODEL_BUILT from being driven here.
MODEL_BUILT_GAP = "bench_test_artifact must have decision GO"


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
                     iteration: int, event_time: float) -> dict:
    return {
        "project_artifact": project_path.name,
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


def model_probe_input(project_path: Path, artifact_names: dict[str, str]) -> dict:
    """The grease-route statistical-analysis request, used only to locate the MODEL_BUILT gap."""
    return {
        "project_artifact": project_path.name,
        "challenge_artifact": "challenge.json",
        "failure_ctq_artifact": "failure_ctq.json",
        "test_method_artifact": "test_method.json",
        "design_space_artifact": artifact_names["design_space"],
        "experiment_design_artifact": artifact_names["experiment_design"],
        "experiment_artifact": "experiment.json",
        "batch_artifact": artifact_names["batch"],
        "screening_artifact": artifact_names["screening"],
        "bench_test_artifact": artifact_names["bench_test"],
        "variance_artifact": artifact_names["variance"],
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
                    version_before: int = 7):
    """The declared ring edge VARIANCE_ASSESSED -> BATCH_PRODUCED as a state-machine event.

    The before state's evidence list is the round-1 record set (one id per artifact the
    workspace actually produced), and the after state appends the new round's first
    record -- exactly the append-only shape the contract's ring-edge branch demands.
    """
    after_evidence = [appended] if drop_round_1 else [*round_1_evidence, appended]
    before = sm_state("VARIANCE_ASSESSED", version_before, round_1_evidence, ROUND_1_DECISION_QUESTION)
    after = sm_state("BATCH_PRODUCED", version_before, after_evidence, ROUND_1_DECISION_QUESTION)
    return validator.validate(sm_event(before, after, iteration=iteration)), before, after


# ---------------------------------------------------------------------------
# scenario E2E-2: one inner-loop round, the ring edge, iteration 1 -> 2
# ---------------------------------------------------------------------------


def stage_scripts() -> dict[str, Path]:
    return {
        "batch": SKILLS / "grease-batch" / "scripts",
        "screening": SKILLS / "grease-screening" / "scripts",
        "bench_test": SKILLS / "experiment-import" / "scripts",
        "variance": SKILLS / "variance-assessment" / "scripts",
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
        print("E2E-2 ok: SCREENING_PASSED built and validated; gate_to_bench RELEASED")

        # --- BENCH_TESTED: four bench runs of the round -----------------------
        bench_test_paths: list[Path] = []
        for index, (run_id, batch_id, sample_id, event_time) in enumerate(ROUND_1_RUNS):
            request = ws / f"input-bench-test-{index}.json"
            write_json(request, bench_test_input(project_path, run_id, batch_id, sample_id, 1, event_time))
            artifact = ws / ("bench_test.json" if index == 0 else f"bench_test-{PROJECT_ID}-{run_id}.json")
            run_ok(scripts["bench_test"] / "preflight_experiment_import.py", request)
            run_ok(scripts["bench_test"] / "build_bench_test_artifact.py", request, artifact)
            run_ok(scripts["bench_test"] / "validate_bench_test_artifact.py", artifact)
            record = check_schema("bench_test", artifact)
            assert record["stage"] == "BENCH_TESTED" and record["campaign_iteration"] == 1, record
            bench_test_paths.append(artifact)
        found = bench_test_records(ws)
        assert len(found) == 4, found
        result["bench_test_records_in_round_1"] = found
        print(f"E2E-2 ok: BENCH_TESTED x{len(bench_test_paths)} built and validated by experiment-import (bench path)")

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

        # --- MODEL_BUILT / NEXT_BATCH_DECIDED: records with no pack producer --
        for fixture_name, target in (("model_round_1.json", "model.json"), ("next_batch_round_1.json", "next_batch.json")):
            write_json(ws / target, read_json(FIXTURES / fixture_name))
            check_schema(target[: -len(".json")], ws / target)
        model = read_json(ws / "model.json")
        next_batch = read_json(ws / "next_batch.json")
        assert model["stage"] == "MODEL_BUILT", model
        assert next_batch["from_iteration"] == 1 and next_batch["to_iteration"] == 2, next_batch
        assert next_batch["stop_state"] == "CONTINUE", next_batch
        assert next_batch["information_gain_basis"].strip(), next_batch
        assert all(item["hypothesis"].strip() and item["discriminates"].strip()
                   for item in next_batch["proposed_samples"]), next_batch
        assert next_batch["bench_slots_required"] >= 1, next_batch
        print("E2E-2 ok: MODEL_BUILT and NEXT_BATCH_DECIDED records present and schema-valid")
        print("E2E-2 ok: next_batch proposes round 2 (from_iteration 1 -> to_iteration 2, CONTINUE) with its reason")

        # The MODEL_BUILT producer cannot consume this route's own chain today: the
        # refusal is located with the skill's real preflight so the inline record above
        # is an accounted-for gap, not a silent substitution.
        probe = run(scripts["model"] / "preflight_statistical_analysis.py",
                    _probe_path(ws, project_path, design_space_path, experiment_design_path,
                                batch_paths[BATCH_CANDIDATE[1]], screening_path, bench_test_paths[0],
                                variance_path))
        if MODEL_BUILT_GAP in probe.stdout:
            print(f"E2E-2 KNOWN GAP (product code): statistical-analysis refuses the route's own chain: {MODEL_BUILT_GAP}")
            result["model_built_gap"] = MODEL_BUILT_GAP
        else:
            print("E2E-2 NOTE: statistical-analysis no longer reports the bench_test decision gap "
                  "(gap closed upstream); the MODEL_BUILT record above is still the inline fixture")

        # --- campaign iteration 1: current_iteration lives in campaign.json --
        campaign_path = ws / "campaign.json"
        write_json(campaign_path, read_json(FIXTURES / "campaign_iteration_1.json"))
        campaign_1 = check_schema("campaign", campaign_path)
        assert campaign_1["current_iteration"] == 1, campaign_1
        assert campaign_1["iterations"][0]["stop_state"] == "CONTINUE", campaign_1["iterations"][0]
        assert campaign_1["iterations"][0]["next_batch_reference"] == next_batch["next_batch_id"], campaign_1
        assert campaign_1["iterations"][0]["variance_reference"] == variance["variance_id"], campaign_1
        print("E2E-2 ok: campaign.json carries current_iteration=1 with round 1's own references")

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

        # The ring event carries the incremented iteration; the whole round-1 record set
        # is retained verbatim and the round-2 batch record is appended (append-only).
        appended = f"ITER-2:{round2_batch.name}"
        assert campaign_1["current_iteration"] == 1
        assert next_batch["to_iteration"] == campaign_1["current_iteration"] + 1, next_batch
        reason, before, after = ring_edge_event(
            validator, iteration=next_batch["to_iteration"], round_1_evidence=round_1_evidence, appended=appended
        )
        assert reason is None, f"ring edge must be ALLOWed by the state machine: {reason}"
        assert before["version"] == after["version"], (before, after)
        assert all(item in after["evidence"] for item in before["evidence"]), after["evidence"]
        assert len(after["evidence"]) == len(before["evidence"]) + 1, after["evidence"]
        assert after["evidence"][-1] == appended
        assert len(round_1_evidence) == len(frozen_round_1)
        assert next_batch["to_iteration"] == 2 == campaign_1["current_iteration"] + 1
        print("E2E-2 ok: state machine ALLOWs the ring edge at iteration "
              f"{next_batch['to_iteration']} with all {len(round_1_evidence)} round-1 records retained "
              "verbatim (version preserved, exactly the round-2 batch appended)")

        # Negative counterparts: the ALLOW above is a real gate, not a validator that
        # accepts everything, and the ring is not a ROLLBACK (it may not void a round).
        drop_reason, _, _ = ring_edge_event(validator, iteration=2, round_1_evidence=round_1_evidence,
                                            appended=appended, drop_round_1=True)
        assert drop_reason == "GO ring-edge advance must retain prior evidence", drop_reason
        no_counter_reason, _, _ = ring_edge_event(validator, iteration=None, round_1_evidence=round_1_evidence,
                                                  appended=appended)
        assert no_counter_reason == "GO ring-edge advance must carry the inner-loop iteration counter", no_counter_reason
        contract = read_json(CONTRACT)
        cap = contract["max_iterations"]
        over_cap_reason, _, _ = ring_edge_event(validator, iteration=cap + 1, round_1_evidence=round_1_evidence,
                                                appended=appended)
        assert over_cap_reason == f"iteration {cap + 1} exceeds max_iterations {cap}; stop the inner loop and record PIVOT or KILL", over_cap_reason
        print("E2E-2 ok: dropping round-1 evidence / omitting the iteration counter / exceeding "
              f"max_iterations={cap} are each REFUSED")

        # campaign.json now carries iteration 2 with round 1 appended-to, never voided.
        write_json(campaign_path, read_json(FIXTURES / "campaign_iteration_2.json"))
        campaign_2 = check_schema("campaign", campaign_path)
        assert campaign_2["current_iteration"] == 2 == campaign_1["current_iteration"] + 1, campaign_2
        assert campaign_2["iterations"][: len(campaign_1["iterations"])] == campaign_1["iterations"], campaign_2["iterations"]
        assert [entry["iteration"] for entry in campaign_2["iterations"]] == [1, 2], campaign_2["iterations"]
        assert campaign_2["iterations"][1]["samples"] == [BATCH_ROUND_2[1]], campaign_2["iterations"][1]
        assert campaign_2["max_iterations"] == cap, campaign_2
        print("E2E-2 ok: campaign.json current_iteration incremented to 2; iteration 1's entry is carried over verbatim")

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
                batch_path, screening_path, bench_test_path, variance_path) -> Path:
    request = ws / "input-model-probe.json"
    write_json(request, model_probe_input(project_path, {
        "design_space": design_space_path.name,
        "experiment_design": experiment_design_path.name,
        "batch": batch_path.name,
        "screening": screening_path.name,
        "bench_test": bench_test_path.name,
        "variance": variance_path.name,
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

        # --- the rework edge: the router ALLOWs SCREENING_PASSED -> BATCH_PRODUCED ---
        router_rework = router.decide(
            {"stage": "SCREENING_PASSED", "status": "ACTIVE", "evidence_scope": "PHYSICAL", "project_type": PROJECT_TYPE},
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
        # The event's evidence names the records this workspace actually produced.
        before = sm_state("SCREENING_PASSED", 6,
                          [f"ITER-1:{batch_path.name}", f"ITER-1:{screening_path.name}"],
                          "Can round 1 clear physical screening?")
        after = sm_state("BATCH_PRODUCED", 6,
                         [*before["evidence"], f"ITER-1:{rework_batch.name}"],
                         "Can round 1 clear physical screening?")
        reason = validator.validate(sm_event(before, after, iteration=1))
        assert reason is None, f"rework edge must be ALLOWed by the state machine: {reason}"
        assert before["version"] == after["version"], (before, after)
        assert all(item in after["evidence"] for item in before["evidence"]), after["evidence"]
        assert len(after["evidence"]) == len(before["evidence"]) + 1, after["evidence"]
        print("E2E-3 ok: state machine ALLOWs the rework edge at iteration 1 "
              "(the failed screen's record is retained, the remade batch is appended)")

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
        f"{inner_loop['campaign_1_iteration']} -> {inner_loop['campaign_2_iteration']}, round-1 records retained), "
        "E2E-3 screening rework (rework edge ALLOW, batch remade, 0 bench_test records), "
        "decision-3 boundary locked (inter-ring backtracking DENY)"
    )
    print(
        "NOT COVERED: MODEL_BUILT is inline-assembled here because statistical-analysis refuses this route's own "
        f"bench_test record ({inner_loop.get('model_built_gap', 'the gap was reported closed')}); NEXT_BATCH_DECIDED "
        "and CAMPAIGN_OPENED have no producing script in the pack (both records are inline fixtures, schema-checked); "
        "the oil-route upstream stages are not re-driven"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
