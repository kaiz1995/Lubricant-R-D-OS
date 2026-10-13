"""End-to-end acceptance for the PRECISION_GREASE_DEV route (plan section 8.2 E2E-1).

Walks the contract's 20-stage route in order. For every stage the test first
asserts that ``route_step.decide()`` ALLOWs the single-step advance from the
previous stage and routes to the producing skill, then DRIVES the stage with that
skill: preflight -> build -> validate with exit code 0, followed by a schema
validation of the produced artifact against ``schemas/<type>.schema.json``
(jsonschema + referencing, the pack's existing usage) and a cross-check of the
fields the next stage consumes.

All 20 stages are drivable: the six break points this file used to record as open
product-code gaps were fixed (project-definition ships ``build_project_artifact.py``
and accepts PRECISION_GREASE_DEV; bench-registration produces campaigns;
doe-design produces next_batch records; statistical-analysis exempts the route's
contract-UNDECIDED bench_test record from its GO requirement; gate-review and
audit_chain accept the route's NON_INFERIORITY_PASSED optimization artifact).
The driven set is therefore asserted to EQUAL ``EXPECTED_ROUTE`` -- the coverage
floor is the full route, and a stage that silently drops out fails the run
instead of shrinking a printout.

  PROJECT_DEFINED -> DUTY_DEFINED -> FAILURE_MECHANISM_DEFINED ->
  REFERENCE_MATERIAL_RESOLVED -> TEST_METHODS_QUALIFIED -> DESIGN_SPACE_DEFINED ->
  BENCH_RESOURCE_REGISTERED -> CAMPAIGN_OPENED -> EXPERIMENT_DESIGNED ->
  BATCH_PRODUCED -> SCREENING_PASSED -> BENCH_TESTED -> VARIANCE_ASSESSED ->
  MODEL_BUILT -> NEXT_BATCH_DECIDED -> NON_INFERIORITY_PASSED ->
  PROCESS_SCALE_VALIDATED -> VERIFIED -> APPLIED -> KNOWLEDGE_ARCHIVED

Beyond the per-stage drives the chain closes what the records themselves claim:

  * ``audit_chain.py`` finds no violation over the workspace as built;
  * the knowledge_asset reaches ``CLOSED_KNOWLEDGE`` and each of its six asset
    references resolves to a real artifact this workspace produced, carrying the
    artifact type and stage the asset name implies (the six ``present`` flags are
    NOT taken as read-back of the test's own request);
  * E2E-10 retrieval closure: the route's own failure-mechanism query, run
    through the pack's retrieval consumer, finds the freshly archived asset --
    the consumer prints ``history_hits=N backend=local_bm25`` and the module
    search returns the asset's own file.

Negative checks lock the gates that make those drives meaningful: the router
denies a cross-stage jump; the campaign gate refuses a PHYSICAL campaign drawing
slots from a SYNTHETIC bench (NO Synthetic Closure); the next-batch gate refuses
a request that declares fewer than two competing explanations (it never composes
one); the bench-test gate refuses an event-free run with no declared stop reason;
and statistical-analysis refuses a PRECISION_GREASE_DEV request that omits the
four inner-loop artifacts -- its grease precondition is keyed on the charter's
project_type, not on the request shape.

Materials and censoring discipline are kept: the bench observation is recorded
with its censoring fields exactly as bench_test_policy requires, and the
variance assessment traces every observation back to a supplied bench record.
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
ROUTE_SCRIPT = SKILLS / "lubricant-rd-agent" / "scripts" / "route_step.py"
AUDIT_SCRIPT = ROOT / "scripts" / "audit_chain.py"

PROJECT_TYPE = "PRECISION_GREASE_DEV"
PROJECT_ID = "PGD-E2E-001"
SIM = "Synthetic test fixture / NOT_FOR_PHYSICAL_EXECUTION"
CTQ_ID = "CTQ-PGD-E2E-001"
METHOD_ID = "TM-PGD-E2E-001"
CHALLENGE_ID = "CH-PGD-E2E-001"
FAILURE_ID = "FM-PGD-E2E-001"
BENCH_ID = "BENCH-SZ-PGD-E2E-01"

EXPECTED_ROUTE = (
    "PROJECT_DEFINED",
    "DUTY_DEFINED",
    "FAILURE_MECHANISM_DEFINED",
    "REFERENCE_MATERIAL_RESOLVED",
    "TEST_METHODS_QUALIFIED",
    "DESIGN_SPACE_DEFINED",
    "BENCH_RESOURCE_REGISTERED",
    "CAMPAIGN_OPENED",
    "EXPERIMENT_DESIGNED",
    "BATCH_PRODUCED",
    "SCREENING_PASSED",
    "BENCH_TESTED",
    "VARIANCE_ASSESSED",
    "MODEL_BUILT",
    "NEXT_BATCH_DECIDED",
    "NON_INFERIORITY_PASSED",
    "PROCESS_SCALE_VALIDATED",
    "VERIFIED",
    "APPLIED",
    "KNOWLEDGE_ARCHIVED",
)

# stage -> the skill the router must route the request to (contract level fact).
STAGE_SKILL = {
    "PROJECT_DEFINED": "project-definition",
    "DUTY_DEFINED": "duty-definition",
    "FAILURE_MECHANISM_DEFINED": "failure-ctq-analysis",
    "REFERENCE_MATERIAL_RESOLVED": "reference-material",
    "TEST_METHODS_QUALIFIED": "test-method-qualification",
    "DESIGN_SPACE_DEFINED": "formulation-design",
    "BENCH_RESOURCE_REGISTERED": "bench-registration",
    "CAMPAIGN_OPENED": "bench-registration",
    "EXPERIMENT_DESIGNED": "doe-design",
    "BATCH_PRODUCED": "grease-batch",
    "SCREENING_PASSED": "grease-screening",
    "BENCH_TESTED": "experiment-import",
    "VARIANCE_ASSESSED": "variance-assessment",
    "MODEL_BUILT": "statistical-analysis",
    "NEXT_BATCH_DECIDED": "doe-design",
    "NON_INFERIORITY_PASSED": "optimization",
    "PROCESS_SCALE_VALIDATED": "process-scale-up",
    "VERIFIED": "gate-review",
    "APPLIED": "application-validation",
    "KNOWLEDGE_ARCHIVED": "knowledge-archive",
}

# The exact refusals the negative checks below pin. Each is the product's own
# wording, asserted against the observed output (never softened).
CAMPAIGN_SYNTHETIC_BENCH_GAP = "is SYNTHETIC and may not back a PHYSICAL campaign"
NEXT_BATCH_EXPLANATIONS_GAP = (
    "next_batch.competing_explanations must declare at least two competing explanations"
)
GREASE_PRECONDITION_GAP = "is required on the PRECISION_GREASE_DEV route"
# gate-review's stage constant for the oil routes (must survive the grease dispatch).
GATE_OIL_STAGE_GAP = "optimization_artifact must be stage OPTIMIZED"

# E2E-10: the printed retrieval summary line a knowledge-reuse consumer emits when
# its query hits a closed history corpus (see skills/duty-definition and
# skills/failure-ctq-analysis, both backed by scripts/knowledge_retrieval.py).
RETRIEVAL_BACKEND = "backend=local_bm25"
RETRIEVAL_LINE = "history_hits="


def audit_problem_lines(stdout: str) -> list[str]:
    """The audit's problem statements, without the 'FAIL' bullet prefix."""
    problems = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("FAIL "):
            problems.append(stripped[len("FAIL "):])
    return problems


def has_producer(artifact_type: str) -> list[str]:
    """Scripts that assemble an artifact of this type (the type literal is the fingerprint)."""
    needles = (f'"artifact_type": "{artifact_type}"', f'"artifact_type":"{artifact_type}"')
    hits = []
    for path in sorted(SKILLS.glob("*/scripts/*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(needle in text for needle in needles):
            hits.append(str(path.relative_to(ROOT)))
    return hits


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: Path, *arguments: object, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", script.name, *map(str, arguments)],
        cwd=cwd or script.parent,
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


def measurement(value: float | int, unit: str, batch: str = "not_applicable", formula: str = "not_applicable") -> dict:
    return {
        "value": value,
        "unit": unit,
        "source": SIM,
        "method_version": "e2e-fixture-v1",
        "material_batch": batch,
        "formula_version": formula,
    }


def artifact_block(path: Path, stage: str) -> dict:
    """The canonical 7 decision fields shared by every stage artifact."""
    return {
        "schema_version": "0.1.0",
        "project_id": PROJECT_ID,
        "stage": stage,
        "decision_question": f"e2e fixture: can {path.name} be recorded?",
        "hypothesis": f"e2e fixture: {path.name} records supplied values only.",
        "uncertainty": f"{SIM}: supplied for contract validation only.",
        "evidence": [
            {
                "evidence_id": "E-E2E-BASE-001",
                "statement": f"{SIM}: base evidence for {path.name}.",
                "source": SIM,
                "status": "ASSUMED",
            }
        ],
        "decision_rule": "Record supplied values only.",
        "result": f"{path.name} recorded for contract validation only.",
        "decision": "GO",
        "next_action": "Retain the record.",
    }


# ---------------------------------------------------------------------------
# stage inputs (inline construction; values follow the pack's own fixture conventions)
# ---------------------------------------------------------------------------


def project_input() -> dict:
    return {
        "project_id": PROJECT_ID,
        "project_name": "Precision-gear grease E2E campaign",
        "project_type": PROJECT_TYPE,
        "product_family": "Precision-gear (harmonic drive) grease",
        "business_objective": "Qualify a precision-gear grease against the OEM reference grease.",
        "technical_objective": "Maintain the required CTQ and risk boundaries under the harmonic-drive duty.",
        "hard_constraints": [
            "Reference materials must exist as physical samples before method qualification.",
        ],
        "target_cost": {
            "value": 120,
            "unit": "CNY/kg",
            "source": SIM,
            "method_version": "cost-baseline-v1",
            "material_batch": "not_applicable",
            "formula_version": "baseline-v1",
        },
        "benchmark_products": ["Synthetic OEM precision-gear grease reference"],
        "success_criteria": ["Critical CTQs have evidence."],
        "risk_class": "STRATEGIC",
        "owner": "R&D owner",
        "source_evidence": [
            {
                "evidence_id": "E-PROJ-E2E-001",
                "statement": f"{SIM}: approved brief requests a precision-gear grease with an OEM grease as the performance benchmark.",
                "source": SIM,
                "status": "OBSERVED",
            }
        ],
    }


def project_ceiling_input() -> dict:
    """The same grease charter with cost as a CEILING instead of a reduction target.

    Cost is a constraint, never a criterion: on a grease project the cost is a limit
    to respect, so the schema accepts cost_ceiling + cost_basis_reason in place of
    target_cost. Keeping this reachable through the skill path is asserted in the
    PROJECT_DEFINED section.
    """
    data = project_input()
    data.pop("target_cost", None)
    data["cost_ceiling"] = {
        "value": 220,
        "unit": "CNY/kg",
        "source": SIM,
        "method_version": "cost-baseline-v1",
        "material_batch": "not_applicable",
        "formula_version": "baseline-v1",
    }
    data["cost_basis_reason"] = (
        f"{SIM}: a performance-first grease charter sets a cost ceiling to respect, not a reduction target."
    )
    return data


def duty_input(project_path: Path) -> dict:
    dimensions = {
        "equipment": ("Harmonic-drive precision reducer (cup type, flexspline + rigid wheel)", "E-PG-E2E-D-001"),
        "operating_conditions": ("Servo duty, frequent start/stop, bidirectional", "E-PG-E2E-D-002"),
        "maintenance": ("No replenishment opportunity over the reducer design life", "E-PG-E2E-D-003"),
        "temperature": ("-40 to 120 C", "E-PG-E2E-D-004"),
        "load": ("Rated output torque 40 Nm, peak 120 Nm", "E-PG-E2E-D-005"),
        "contamination": ("Sealed unit, no external media contact", "E-PG-E2E-D-006"),
        "life": ("Maintenance-free life target 20000 h", "E-PG-E2E-D-007"),
        "motion_regime": (
            "Oscillation amplitude +/-3 deg at 5 Hz, 10e6 cycles, bidirectional; continuous rotation between positioning moves",
            "E-PG-E2E-D-008",
        ),
        "contact_pair": (
            "Flexspline 40CrNiMoA / rigid wheel 40Cr, DLC coating present (a-C:H film system) on flexspline teeth, NBR seal, POM plastic part",
            "E-PG-E2E-D-009",
        ),
        "temperature_and_heat_source": ("-40 to 120 C window; servo temperature rise +35 K, continuous-duty rise +20 K", "E-PG-E2E-D-010"),
        "torque_requirement": (
            "Low-temperature start-up torque ceiling 0.15 Nm at -40 C, no-load breakaway torque 0.05 Nm, running torque 0.03 Nm",
            "E-PG-E2E-D-011",
        ),
        "fill_and_assembly": ("Fill mass 30 g, 70 percent of the free cavity; assembly by manual packing", "E-PG-E2E-D-012"),
        "life_and_maintenance": ("Maintenance-free whole-life target 20000 h with no replenishment", "E-PG-E2E-D-013"),
        "sealing_and_contamination": ("IP65 sealed unit, no external media contact", "E-PG-E2E-D-014"),
    }
    duty = {}
    for key, (value, evidence_id) in dimensions.items():
        duty[key] = {
            "value": value,
            "source": SIM,
            "evidence_id": evidence_id,
            "statement": f"{SIM}: {key.replace('_', ' ')} is supplied for contract testing only.",
            "status": "ASSUMED",
        }
    return {"project_artifact": project_path.name, "duty_id": "DP-PGD-E2E-001", "duty": duty}


def challenge_input(duty_path: Path, project_path: Path) -> dict:
    return {
        "duty_artifact": duty_path.name,
        "project_artifact": project_path.name,
        "challenge": {
            "duty_reference": "DP-PGD-E2E-001",
            "challenge_id": CHALLENGE_ID,
            "category": "FRETTING_WEAR",
            "description": (
                "Micro-oscillation under servo duty drives fretting wear on the flexspline tooth flank, "
                "the core harmonic-drive failure mode."
            ),
            "severity": "HIGH",
            "exposure": "HIGH",
            "lubricant_sensitivity": "HIGH",
            "evidence_gap": "No measured fretting-fatigue life data for this oscillation amplitude.",
            "priority": "HIGH",
        },
        "challenge_evidence": [
            {
                "evidence_id": "E-PG-E2E-C-001",
                "statement": f"{SIM}: the recorded grease duty profile states +/-3 deg oscillation at 5 Hz and 10e6 cycles for contract testing only.",
                "source": SIM,
                "status": "OBSERVED",
            }
        ],
    }


def failure_input(project_path: Path, challenge_path: Path) -> dict:
    return {
        "project_artifact": project_path.name,
        "challenge_artifact": challenge_path.name,
        "evidence": [
            {
                "evidence_id": "E-PG-E2E-F-001",
                "statement": f"{SIM}: the recorded fretting-wear challenge is carried forward for contract testing only.",
                "source": SIM,
                "status": "ASSUMED",
            }
        ],
        "failure_ctq": {
            "challenge_reference": CHALLENGE_ID,
            "failure_id": FAILURE_ID,
            "failure_mode": "Flexspline tooth-flank fretting wear with micro-pitting",
            "mechanism": (
                "Micro-oscillation keeps the contact in the boundary regime; the entrained film cannot "
                "reform between reversals, so asperity contact accumulates fretting damage (grease hardening)."
            ),
            "failure_diagnosis": (
                "The flexspline flank records material loss at the oscillation reversal zones while the "
                "bulk tooth form is intact: a boundary-regime contact-fatigue state, not a bulk load failure."
            ),
            "root_cause_hypotheses": [
                "Hypothesis: Grease base-oil bleed rate is too low to replenish the reversal zones between micro-oscillations.",
                "Hypothesis: Thickener soap-fiber structure is sheared out of the contact under sustained micro-oscillation.",
            ],
            "lubricant_contribution": "POSSIBLE - Pending SRV fretting bench verification of base-oil bleed rate and soap-fiber shear stability.",
            "ctqs": [
                {
                    "ctq_id": CTQ_ID,
                    "classification": "CTQ",
                    "criteria_layer": "BENCH",
                    "observable": "SRV fretting wear scar depth on flexspline material pair",
                    "specification_limit": {
                        "value": 15,
                        "unit": "um",
                        "source": SIM,
                        "method_version": "DIN-51834-2024",
                        "material_batch": "baseline-batch",
                        "formula_version": "baseline-v1",
                    },
                    "engineering_risk_limit": {
                        "value": 10,
                        "unit": "um",
                        "source": SIM,
                        "method_version": "risk-model-v1",
                        "material_batch": "baseline-batch",
                        "formula_version": "baseline-v1",
                    },
                    "test_references": [METHOD_ID],
                    "evidence_required": ["qualified SRV method", "reference grease comparison"],
                }
            ],
            "test_chain": [METHOD_ID],
        },
    }


def reference_input(project_path: Path) -> dict:
    return {
        "project_artifact": project_path.name,
        "reference_id": "REF-PGD-E2E-001",
        "evidence_scope": "SYNTHETIC",
        "known_good": [
            {
                "reference_id": "REF-PGD-E2E-001-G1",
                "resolution": "RESOLVED",
                "selection_rung": "DIRECT_HISTORY",
                "material_identity": f"{SIM}: synthetic precision-gear grease, trade name SYN-PG-GOOD, lot LOT-SYN-PG-E2E-0001",
                "formula_identity": "FORM-PG-E2E@v1",
                "history_evidence": [
                    {
                        "evidence_reference": f"{SIM}: synthetic history record SYN-PG-E2E-H-001, 24 months in the reference harmonic drive with no bearing event recorded.",
                        "mechanism_reference": "MECHANISM-NONE: no failure mechanism is demonstrated by this no-event history.",
                    }
                ],
                "storage_sop": "SOP-SYN-PG-E2E-STORE-001",
                "safety_reference": "SDS-SYN-PG-GOOD-2025",
            }
        ],
        "known_bad": [
            {
                "reference_id": "REF-PGD-E2E-001-B1",
                "resolution": "RESOLVED",
                "selection_rung": "DIRECT_HISTORY",
                "material_identity": f"{SIM}: synthetic precision-gear grease, trade name SYN-PG-BAD, lot LOT-SYN-PG-E2E-0002",
                "formula_identity": "FORM-PG-E2E@v0",
                "history_evidence": [
                    {
                        "evidence_reference": f"{SIM}: synthetic failure event SYN-PG-E2E-FE-001, grease hardening and torque rise after the synthetic bench run.",
                        "mechanism_reference": "MECHANISM-PG-GREASE-HARDENING-001: the recorded failure demonstrates hardening driven by an under-milled soap structure.",
                    }
                ],
                "storage_sop": "SOP-SYN-PG-E2E-STORE-002",
                "safety_reference": "SDS-SYN-PG-BAD-2025",
            }
        ],
        "evidence": [
            {
                "evidence_id": "E-REF-PG-E2E-001",
                "statement": f"{SIM}: the Known Good dossier cites a no-event service history.",
                "source": SIM,
                "status": "ASSUMED",
            },
            {
                "evidence_id": "E-REF-PG-E2E-002",
                "statement": f"{SIM}: the Known Bad dossier cites a failure event bound to the grease-hardening mechanism it demonstrates.",
                "source": SIM,
                "status": "ASSUMED",
            },
        ],
    }


def material_artifacts() -> list[dict]:
    base_oil = {
        **artifact_block(Path("material-base-oil.json"), "DESIGN_SPACE_DEFINED"),
        "artifact_type": "material",
        "evidence_scope": "SYNTHETIC",
        "evidence": [
            {
                "evidence_id": "E-MAT-PG-E2E-001",
                "statement": f"{SIM}: the supplier datasheet records the trade name, lot, and KV100 of the base oil.",
                "source": SIM,
                "status": "ASSUMED",
                "claim_class": "MANUFACTURER_DATASHEET",
            },
            {
                "evidence_id": "E-MAT-PG-E2E-002",
                "statement": f"{SIM}: the aniline point is not yet available from the supplier, so it is recorded as a GAP, not guessed.",
                "source": SIM,
                "status": "GAP",
            },
        ],
        "material_id": "MAT-PG-E2E-BO-001",
        "category": "BASE_OIL",
        "identity": {"supplier": "Synthetic supplier A", "trade_name": "Synthetic PAO-6", "lot": "LOT-SYN-PG-E2E-001"},
        "chemistry": {"base_oil_family": "PAO", "notes": f"{SIM}: non-polar polyalphaolefin."},
        "properties": [
            {"property_id": "kv40", "value": 31.0, "unit": "mm2/s", "source": SIM, "evidence_id": "E-MAT-PG-E2E-001", "status": "ASSUMED"},
            {"property_id": "kv100", "value": 6.0, "unit": "mm2/s", "source": SIM, "evidence_id": "E-MAT-PG-E2E-001", "status": "ASSUMED"},
            {"property_id": "vi", "value": 138, "unit": "dimensionless", "source": SIM, "evidence_id": "E-MAT-PG-E2E-001", "status": "ASSUMED"},
            {"property_id": "aniline_point", "value": "not supplied by the manufacturer", "unit": "degC", "source": SIM, "evidence_id": "E-MAT-PG-E2E-002", "status": "GAP"},
            {"property_id": "polarity", "value": "non-polar", "unit": "qualitative", "source": SIM, "evidence_id": "E-MAT-PG-E2E-001", "status": "ASSUMED"},
        ],
        "cost": {"value": 4.2, "unit": "CNY/kg", "price_timestamp": "2026-09-01"},
    }
    thickener = {
        **artifact_block(Path("material-thickener-raw.json"), "DESIGN_SPACE_DEFINED"),
        "artifact_type": "material",
        "evidence_scope": "SYNTHETIC",
        "evidence": [
            {
                "evidence_id": "E-MAT-PG-E2E-003",
                "statement": f"{SIM}: the supplier datasheet records the fatty acid trade name and lot.",
                "source": SIM,
                "status": "ASSUMED",
                "claim_class": "MANUFACTURER_DATASHEET",
            }
        ],
        "material_id": "MAT-PG-E2E-FA-001",
        "category": "THICKENER_RAW",
        "identity": {"supplier": "Synthetic supplier B", "trade_name": "Synthetic 12-hydroxystearic acid", "lot": "LOT-SYN-PG-E2E-002"},
        "chemistry": {
            "base_oil_family": "OTHER",
            "notes": f"{SIM}: fatty acid feedstock of the saponification reaction; the soap that determines the product is generated in situ from it.",
        },
        "properties": [
            {"property_id": "acid_value", "value": 178, "unit": "mg KOH/g", "source": SIM, "evidence_id": "E-MAT-PG-E2E-003", "status": "ASSUMED"},
            {"property_id": "melting_point", "value": 78, "unit": "degC", "source": SIM, "evidence_id": "E-MAT-PG-E2E-003", "status": "ASSUMED"},
        ],
        "cost": {"value": 22.0, "unit": "CNY/kg", "price_timestamp": "2026-09-01"},
    }
    return [base_oil, thickener]


def test_method_input(project_path: Path, challenge_path: Path, failure_path: Path, reference_path: Path) -> dict:
    return {
        "project_artifact": project_path.name,
        "challenge_artifact": challenge_path.name,
        "failure_ctq_artifact": failure_path.name,
        "reference_material_artifact": reference_path.name,
        "evidence_scope": "PHYSICAL",
        "evidence": [
            {
                "evidence_id": "E-TM-PG-E2E-STD",
                "statement": f"{SIM}: the SRV bench protocol identity is supplied.",
                "source": SIM,
                "status": "OBSERVED",
            },
            {
                "evidence_id": "E-TM-PG-E2E-REP",
                "statement": f"{SIM}: the same sample was measured many times and the engine computed the repeatability spread.",
                "source": SIM,
                "status": "OBSERVED",
            },
            {
                "evidence_id": "E-TM-PG-E2E-DIS",
                "statement": f"{SIM}: the engine computed the discrimination between the Known Good and Known Bad dossiers.",
                "source": SIM,
                "status": "OBSERVED",
            },
            {
                "evidence_id": "E-TM-PG-E2E-BATCH",
                "statement": f"{SIM}: both conclusions were re-verified on a fresh batch, not on the batch that produced them.",
                "source": SIM,
                "status": "OBSERVED",
            },
        ],
        "test_method": {
            "method_id": METHOD_ID,
            "name": "SRV fretting bench for flexspline material pair",
            "standard": "Synthetic SRV fretting protocol P-E2E-001",
            "challenge_reference": CHALLENGE_ID,
            "target_failure_reference": FAILURE_ID,
            "role": ["D", "P"],
            "qualification_metrics": [
                {
                    "metric": "REPEATABILITY",
                    "measurement": measurement(1.1, "um", "LOT-SYN-PG-E2E-001", "baseline-v1"),
                    "computed_by": "ENGINE",
                },
                {
                    "metric": "DISCRIMINATION",
                    "measurement": measurement(6.0, "um", "LOT-SYN-PG-E2E-001", "baseline-v1"),
                    "computed_by": "ENGINE",
                },
                {
                    "metric": "MECHANISM_RELEVANCE",
                    "measurement": measurement(1, "qualitative rank"),
                },
                {
                    "metric": "BENCHMARK_RANKING",
                    "measurement": measurement(2, "rank positions"),
                },
            ],
            "qualification_pipeline": {
                "repeatability": {"status": "PASS", "evidence_reference": "E-TM-PG-E2E-REP", "computed_by": "ENGINE"},
                "discrimination": {"status": "PASS", "evidence_reference": "E-TM-PG-E2E-DIS", "computed_by": "ENGINE"},
                "independent_batch": {"status": "PASS", "evidence_reference": "E-TM-PG-E2E-BATCH"},
            },
            "reference_material_reference": "REF-PGD-E2E-001",
            "qualification_basis": [
                "engine-computed repeatability",
                "engine-computed discrimination against the resolved reference dossiers",
                "independent new batch re-verification",
            ],
            "qualification_status": "QUALIFIED",
            "method_source_evidence_id": "E-TM-PG-E2E-STD",
            "qualification_evidence_ids": ["E-TM-PG-E2E-REP", "E-TM-PG-E2E-DIS", "E-TM-PG-E2E-BATCH"],
        },
    }


def design_space_input(project_path: Path, challenge_path: Path, failure_path: Path, method_path: Path) -> dict:
    def bound(value: float, unit: str, batch: str = "not_applicable", formula: str = "baseline-v1") -> dict:
        return measurement(value, unit, batch, formula)

    return {
        "project_artifact": project_path.name,
        "challenge_artifact": challenge_path.name,
        "failure_ctq_artifact": failure_path.name,
        "test_method_artifact": method_path.name,
        "material_artifacts": ["material-base-oil.json", "material-thickener-raw.json"],
        "design_space": {
            "design_space_id": "DS-PGD-E2E-001",
            "scope": f"{SIM}: precision-gear grease formulation and process window.",
            "variables": [
                {
                    "variable_id": "VAR-SOAP-CONCENTRATION",
                    "variable_type": "FORMULATION_VARIABLE",
                    "material_reference": "MAT-PG-E2E-FA-001",
                    "role": "REACTION_PRODUCT",
                    "constraint_role": "INDEPENDENT",
                    "lower_bound": bound(8.0, "mass percent"),
                    "upper_bound": bound(14.0, "mass percent"),
                    "constraint_rationale": f"{SIM}: below 8 percent the soap network does not form a stable grease; above 14 percent the low-temperature torque requirement is at risk.",
                },
                {
                    "variable_id": "VAR-BASE-OIL-FRACTION",
                    "variable_type": "MATERIAL_FAMILY",
                    "material_reference": "MAT-PG-E2E-BO-001",
                    "role": "INPUT_MATERIAL",
                    "lower_bound": bound(80.0, "mass percent", "LOT-SYN-PG-E2E-001"),
                    "upper_bound": bound(92.0, "mass percent", "LOT-SYN-PG-E2E-001"),
                    "constraint_rationale": f"{SIM}: charged base oil fraction; it is a real charge, so it closes the charge side.",
                },
                {
                    "variable_id": "VAR-SOAP-HOLD-TIME",
                    "variable_type": "PROCESS_VARIABLE",
                    "lower_bound": bound(20, "min", "not_applicable", "not_applicable"),
                    "upper_bound": bound(60, "min", "not_applicable", "not_applicable"),
                    "constraint_rationale": f"{SIM}: the saponification hold must complete before dehydration starts.",
                },
            ],
            "ctq_references": [CTQ_ID],
            "qualified_test_method_references": [METHOD_ID],
            "constraints": [
                {
                    "constraint_id": "CONS-PG-E2E-001",
                    "kind": "MIXTURE_CLOSURE_INPUTS",
                    "expression": "sum(inputs.mass_percent) == 100",
                    "rationale": f"{SIM}: this closes the CHARGE only; the soap is generated in situ, so it is not a charged input.",
                    "evidence_id": "E-DS-PG-E2E-001",
                },
                "Use only the supplied variable bounds.",
            ],
            "baseline_process_reference": "PROCESS-BASE-PGD-E2E-001",
            "feasibility_regions": [
                {
                    "region_id": "REG-PG-E2E-LOW-SOAP",
                    "expression": "soap_percent in [8, 11] and base_oil_family == PAO",
                    "convexity": "CONVEX",
                    "connected": True,
                    "rationale": f"{SIM}: the low-soap PAO corner forms a stable grease.",
                    "evidence_id": "E-DS-PG-E2E-001",
                },
                {
                    "region_id": "REG-PG-E2E-ESTER-ISLAND",
                    "expression": "soap_percent in [12, 14] and base_oil_family == ESTER",
                    "convexity": "CONVEX",
                    "connected": True,
                    "rationale": f"{SIM}: an ester island separated from the PAO region by a soap/oil combination that does not form a grease.",
                    "evidence_id": "E-DS-PG-E2E-001",
                },
            ],
            "evidence": [
                {
                    "evidence_id": "E-DS-PG-E2E-001",
                    "statement": f"{SIM}: bounds, charge-closure basis, structural feasibility limit, and the disconnected feasible islands are supplied for contract validation only.",
                    "source": SIM,
                    "status": "ASSUMED",
                }
            ],
        },
    }


def process_input(design_space_path: Path) -> dict:
    steps = [
        ("ST-001", "SAPONIFICATION", "P-PG-SAP-TEMP", "saponification temperature", 90, 110, "degC"),
        ("ST-002", "SOAP_HOLD", "P-PG-SOAP-HOLD", "soap hold time", 20, 60, "min"),
        ("ST-003", "DEHYDRATION", "P-PG-DEH-TEMP", "dehydration temperature", 100, 130, "degC"),
        ("ST-004", "PHASE_INVERSION", "P-PG-PHI-TEMP", "phase inversion temperature", 150, 180, "degC"),
        ("ST-005", "DILUTION_CURVE", "P-PG-DIL-RATE", "dilution rate along the curve", 1, 4, "kg/min"),
        ("ST-006", "DILUTION_COOLING", "P-PG-COOL-RATE", "cooling rate", 1, 5, "degC/min"),
        ("ST-007", "RIPENING", "P-PG-RIPEN-TIME", "ripening time", 4, 24, "h"),
        ("ST-008", "MILLING", "P-PG-MIL-GAP", "mill gap", 0.05, 0.3, "mm"),
        ("ST-009", "HOMOGENIZATION", "P-PG-HOM-PRES", "homogenization pressure", 5, 20, "MPa"),
        ("ST-010", "VACUUM_DEAERATION", "P-PG-VAC-PRES", "vacuum pressure", 1, 10, "kPa"),
        ("ST-011", "FILLING_TEMPERATURE", "P-PG-FILL-TEMP", "filling temperature", 70, 90, "degC"),
        ("ST-012", "FILLING", "P-PG-FILL-RATE", "filling rate", 0.5, 2.0, "kg/min"),
    ]
    process_step = []
    for index, (step_id, step_type, parameter_id, name, lower, upper, unit) in enumerate(steps, start=1):
        process_step.append(
            {
                "step_id": step_id,
                "step_type": step_type,
                "parameters": [
                    {
                        "parameter_id": parameter_id,
                        "parameter_name": name,
                        "lower_bound": lower,
                        "upper_bound": upper,
                        "unit": unit,
                        "source": SIM,
                        "evidence_id": f"EV-PG-E2E-PROC-{index:03d}",
                        "status": "ASSUMED",
                    }
                ],
            }
        )
    return {
        "design_space_artifact": design_space_path.name,
        "process": {
            "process_id": "PROC-PGD-E2E-BASE-001",
            "project_reference": PROJECT_ID,
            "process_step": process_step,
            "batch_scale": {"scale_class": "PILOT", "batch_size": measurement(50, "kg", "LOT-SYN-PG-E2E-001", "baseline-v1")},
            "amplification_factor": 20.0,
            "process_window": {
                "window_id": "PW-PG-E2E-001",
                "basis": f"{SIM}: pilot window supplied for contract validation only",
                "validated": False,
            },
            "control_points": [
                {
                    "control_point_id": "CP-PG-E2E-001",
                    "parameter_id": "P-PG-PHI-TEMP",
                    "control_type": "IN_PROCESS",
                    "criterion": "Hold phase inversion within the supplied window",
                    "source": SIM,
                    "evidence_id": "EV-PG-E2E-PROC-004",
                },
                {
                    "control_point_id": "CP-PG-E2E-002",
                    "parameter_id": "P-PG-SOAP-HOLD",
                    "control_type": "IN_PROCESS",
                    "criterion": "Complete the soap hold before dehydration starts",
                    "source": SIM,
                    "evidence_id": "EV-PG-E2E-PROC-002",
                },
            ],
            "cpk": {"value": 1.33, "ctq_reference": CTQ_ID, "sample_size": 30},
            "material_batch_reference": "LOT-SYN-PG-E2E-001",
            "factor_role": "SUB_PLOT",
            "evidence_scope": "SYNTHETIC",
            "evidence": [
                {
                    "evidence_id": "EV-PG-E2E-PROC-001",
                    "statement": f"{SIM}: process bounds supplied for contract validation only; not a qualified process window.",
                    "source": SIM,
                    "status": "ASSUMED",
                }
            ],
        },
    }


def bench_input() -> dict:
    return {
        "bench": {
            "bench_id": BENCH_ID,
            "project_reference": PROJECT_ID,
            "bench_name": "Precision-gear grease bench (E2E fixture)",
            "location": "Synthetic bench location",
            "availability_window": [
                {"window_id": "W-1", "start": "2026-11-01", "end": "2026-12-30"},
                {"window_id": "W-2", "start": "2027-01-01", "end": "2027-03-01"},
            ],
            "cycle_days": 30,
            "cost_per_run": {"value": 12000, "unit": "CNY/run", "source": SIM},
            "source": SIM,
            "evidence_id": "EV-BENCH-PGD-E2E-01",
            # This fixture chain declares PHYSICAL throughout (the SIM text above is
            # the provenance label on the content). The bench carries the same scope
            # as the rest of the chain because the campaign gate enforces the bench
            # skill's NO Synthetic Closure red line: a PHYSICAL campaign may not draw
            # its scarce slots from a SYNTHETIC bench record.
            "evidence_scope": "PHYSICAL",
            "evidence": [
                {
                    "evidence_id": "EV-BENCH-PGD-E2E-01",
                    "statement": f"{SIM}: bench availability supplied for contract validation only; not a booked or qualified capacity.",
                    "source": SIM,
                    "status": "ASSUMED",
                }
            ],
        }
    }


def campaign_input(project_path: Path, bench_path: Path) -> dict:
    """The CAMPAIGN_OPENED request for bench-registration's campaign producer.

    The request shape is the skill's own (preflight_campaign_registration ->
    build_campaign_artifact -> validate_campaign_artifact): the campaign record
    plus the two upstream artifacts it draws on, supplied by path so the gate can
    re-read them. ``max_iterations`` is deliberately OMITTED so this run exercises
    the skill's contract-default path (the cap is read from
    contracts/state-machine.json and the builder records that provenance), and the
    round-1 entry cites the ids the later stages of this chain actually produce,
    so the entry and the next_batch record it authorises agree by construction.
    """
    return {
        "project_artifact": project_path.name,
        "bench_artifacts": [bench_path.name],
        "campaign": {
            "campaign_id": "CMP-PGD-E2E-001",
            "project_reference": PROJECT_ID,
            "bench_references": [BENCH_ID],
            "current_iteration": 1,
            "iterations": [
                {
                    "iteration": 1,
                    "samples": ["SMP-PGD-E2E-001", "SMP-PGD-E2E-002"],
                    "stop_state": "CONTINUE",
                    "screening_reference": "SCR-PGD-E2E-001",
                    "variance_reference": "VAR-PGD-E2E-001",
                    "model_reference": "MODEL-PGD-E2E-001",
                    "next_batch_reference": "NEXT-PGD-E2E-001",
                    "bench_test_references": [
                        "RUN-PGD-E2E-001",
                        "RUN-PGD-E2E-002",
                        "RUN-PGD-E2E-003",
                        "RUN-PGD-E2E-004",
                    ],
                }
            ],
            "pairing_design": {
                "paired": True,
                "description": f"{SIM}: A/B pair runs in the same round; at a fixed sigma, pairing buys more resolution than measuring sigma precisely.",
            },
            "evidence_scope": "PHYSICAL",
            "source": SIM,
            "evidence_id": "E-CM-PGD-E2E-001",
            "evidence": [
                {
                    "evidence_id": "E-CM-PGD-E2E-001",
                    "statement": f"{SIM}: campaign record recorded for contract validation only; this is not product evidence.",
                    "source": SIM,
                    "status": "ASSUMED",
                }
            ],
        },
    }


def experiment_design_input(
    project_path: Path,
    challenge_path: Path,
    failure_path: Path,
    method_path: Path,
    design_space_path: Path,
    bench_path: Path,
) -> dict:
    return {
        "project_artifact": project_path.name,
        "challenge_artifact": challenge_path.name,
        "failure_ctq_artifact": failure_path.name,
        "test_method_artifact": method_path.name,
        "design_space_artifact": design_space_path.name,
        "bench_artifact": bench_path.name,
        "experiment_design": {
            "experiment_design_id": "ED-PGD-E2E-001",
            "factor_references": [
                "VAR-SOAP-CONCENTRATION",
                "VAR-BASE-OIL-FRACTION",
                "VAR-SOAP-HOLD-TIME",
            ],
            "design": {
                "family": "RESOURCE_CONSTRAINED_GREEDY_SEQUENTIAL",
                "rationale": f"{SIM}: the inner loop runs small sequential rounds, so the next batch is chosen from the previous round's result rather than from one large fixed design.",
                "effects_to_estimate": [
                    "soap concentration effect",
                    "base oil fraction effect",
                    "soap hold time effect",
                ],
            },
            "run_plan": {
                "target_count": 4,
                "replicate_count": 0,
                "center_point_count": 0,
                "randomized": True,
                "point_generation": "PHASE4_DETERMINISTIC_ENGINE",
            },
            "resource_envelope": {
                "bench_slots": 4,
                "lot_capacity": 8,
                "cycle_days": 30,
                "cost_cap": 60000,
                "external_test_lead_time": 14,
            },
            "responses": [
                {"ctq_reference": CTQ_ID, "test_method_reference": METHOD_ID, "role": "OPTIMIZATION_RESPONSE"}
            ],
            "guardrails": [
                "Remain within DS-PGD-E2E-001.",
                "Do not exceed the registered bench capacity per round.",
            ],
            "expected_information_value": {
                "classification": "RECOMMENDED",
                "decision_relevance": "Separates feasible precision-gear grease routes inside the frozen design space.",
                "expected_information_gain": "Can inform the next batch decision of the inner loop.",
                "cost": "Synthetic planning estimate only.",
                "duration": "Synthetic planning estimate only.",
                "redundancy": "No duplicate response is represented by this fixture.",
            },
            "evidence": [
                {
                    "evidence_id": "E-ED-PG-E2E-001",
                    "statement": f"{SIM}: this record references a bounded design space, a qualified method and the registered bench for contract validation only.",
                    "source": SIM,
                    "status": "ASSUMED",
                }
            ],
        },
    }


def doe_engine_input() -> dict:
    return {
        "evidence_scope": "PHYSICAL",
        "input_type": "FACTORIAL_DOE_DESIGN",
        "design_type": "RESOURCE_CONSTRAINED_GREEDY_SEQUENTIAL",
        "model_order": "LINEAR",
        "target_runs": 0,
        "design_space_reference": "DS-PGD-E2E-001",
        "project_type": PROJECT_TYPE,
        "factors": [
            {"factor_id": "VAR-SOAP-CONCENTRATION", "factor_type": "CONTINUOUS", "range": {"lower": 8.0, "upper": 14.0}, "unit": "mass percent", "role": "SUB_PLOT"},
            {"factor_id": "VAR-BASE-OIL-FRACTION", "factor_type": "CONTINUOUS", "range": {"lower": 80.0, "upper": 92.0}, "unit": "mass percent", "role": "SUB_PLOT"},
            {"factor_id": "VAR-SOAP-HOLD-TIME", "factor_type": "CONTINUOUS", "range": {"lower": 20.0, "upper": 60.0}, "unit": "min", "role": "SUB_PLOT"},
        ],
        "responses": [
            {"ctq_reference": CTQ_ID, "test_method_reference": METHOD_ID, "role": "OPTIMIZATION_RESPONSE"}
        ],
        "resource_envelope": {
            "bench_slots": 4,
            "lot_capacity": 8,
            "cycle_days": 30,
            "cost_cap": 60000,
            "external_test_lead_time": 14,
        },
        "experiment_card": {
            "decision_question": "Which four sample settings should the first inner-loop round run?",
            "hypothesis": "Soap concentration, base oil fraction and soap hold time separate feasible grease routes.",
            "variables_note": "Three independent factor references from the frozen design space.",
            "constraints_note": "Independent factor bounds; the registered bench bounds the round.",
            "responses_note": f"{CTQ_ID} SRV fretting response.",
            "doe_selection_reason": "Resource-constrained greedy sequential selection over the two-level candidate lattice.",
            "expected_information_value": "A deterministic batch of four runs maximises accumulated det(X'X) per bench slot.",
            "decision_rule": "Run the batch, then decide the next round from the variance assessment.",
        },
    }


def batch_input(project_path: Path, design_space_path: Path, experiment_design_path: Path) -> dict:
    trajectory = [
        ("SAPONIFICATION", 195, 196, "degC", 5400, 3),
        ("SOAP_HOLD", 40, 41, "min", 2400, 3),
        ("DEHYDRATION", 115, 116, "degC", 1800, 5),
        ("PHASE_INVERSION", "visual inversion point", "visual inversion point", "qualitative", 420, "operator confirms the inversion point on the sight glass"),
        ("DILUTION_CURVE", 2.5, 2.6, "kg/min", 900, 0.2),
        ("DILUTION_COOLING", 3.0, 3.1, "degC/min", 1800, 0.5),
        ("RIPENING", 12, 12, "h", 43200, 2),
        ("MILLING", 0.15, 0.16, "mm", 600, 0.02),
        ("HOMOGENIZATION", 12, 12.2, "MPa", 300, 0.5),
        ("VACUUM_DEAERATION", 5, 5.1, "kPa", 900, 0.5),
        ("FILLING_TEMPERATURE", 80, 80, "degC", 300, 2),
        ("FILLING", 1.2, 1.21, "kg/min", 600, 0.05),
    ]
    steps = []
    for index, (step_type, setpoint, actual, unit, duration_s, tolerance) in enumerate(trajectory, start=1):
        step = {
            "step_type": step_type,
            "setpoint": setpoint,
            "actual": actual,
            "unit": unit,
            "duration_s": duration_s,
            "deviation": (actual - setpoint) if isinstance(setpoint, (int, float)) else "none recorded",
            "deviation_verdict": "WITHIN",
            "tolerance": tolerance,
            "source": f"{SIM}: kettle log KL-E2E-001 line {index}",
            "evidence_id": "E-BAT-PG-E2E-001",
        }
        steps.append(step)
    if isinstance(steps[1]["deviation"], float):
        steps[1]["deviation"] = round(steps[1]["deviation"], 6)
    return {
        "project_artifact": project_path.name,
        "design_space_artifact": design_space_path.name,
        "experiment_design_artifact": experiment_design_path.name,
        "evidence_scope": "PHYSICAL",
        "evidence": [
            {
                "evidence_id": "E-BAT-PG-E2E-001",
                "statement": f"{SIM}: kettle log KL-E2E-001 records setpoint, actual, duration and a tolerance band for every executed step.",
                "source": f"{SIM}: kettle log KL-E2E-001",
                "status": "OBSERVED",
            }
        ],
        "batch": {
            "batch_id": "BAT-PGD-E2E-001",
            "formula_reference": "FORM-PG-E2E@v1",
            "scale_class": "LAB",
            "trajectory": steps,
            "raw_material_lots": ["LOT-SYN-PG-E2E-001", "LOT-SYN-PG-E2E-002"],
            "operator": "Operator OP-E2E-01",
            "equipment": "5 L pilot kettle K-E2E-01",
            "anomalies": [],
            "batch_verdict": "VALID",
        },
        "sample": {
            "sample_id": "SMP-PGD-E2E-001",
            "label": {
                "printed_text": "SMP-PGD-E2E-001 | BAT-PGD-E2E-001 | FORM-PG-E2E@v1 | 2026-12-05",
                "printed_at": "2026-12-05T09:40:00",
            },
            "prepared_at": "2026-12-05",
            "storage": "Sealed 1 kg drum at 25 degC, dry indoor cabinet, sample shelf S-03.",
            "chain_of_custody": [
                {
                    "from": "Kettle operator OP-E2E-01",
                    "to": "Sample store SS-E2E-01",
                    "at": "2026-12-05",
                    "purpose": "Store the freshly filled drum until the screening bench run is scheduled.",
                }
            ],
            "status": "IN_TRANSIT",
        },
    }


def screening_input(project_path: Path, batch_path: Path) -> dict:
    tests = [
        ("ST-PG-E2E-001", "PENETRATION", 265, "0.1 mm", 340, "PASS"),
        ("ST-PG-E2E-002", "WORKED_PENETRATION_CHANGE", 12, "0.1 mm", 30, "PASS"),
        ("ST-PG-E2E-003", "DROPPING_POINT", 185, "degC", "180 min", "PASS"),
        ("ST-PG-E2E-004", "OIL_SEPARATION", 1.2, "percent mass", 5, "PASS"),
        ("ST-PG-E2E-005", "EVAPORATION_LOSS", 2.5, "percent mass", 3, "PASS"),
        ("ST-PG-E2E-006", "SHEAR_STABILITY", 8, "percent change", 10, "PASS"),
        ("ST-PG-E2E-007", "APPEARANCE_UNIFORMITY", "uniform", "visual grade", "uniform", "PASS"),
    ]
    return {
        "project_artifact": project_path.name,
        "batch_artifact": batch_path.name,
        "sample_artifact": "sample.json",
        "evidence_scope": "PHYSICAL",
        "evidence": [
            {
                "evidence_id": "E-SC-PG-E2E-001",
                "statement": f"{SIM}: the screening lab worksheet supplied for this sample records value, unit, limit and verdict for each screened index.",
                "source": SIM,
                "status": "ASSUMED",
            }
        ],
        "screening": {
            "screening_id": "SCR-PGD-E2E-001",
            "sample_reference": "SMP-PGD-E2E-001",
            "tests": [
                {"test_id": test_id, "test_name": name, "value": value, "unit": unit, "limit": limit, "verdict": verdict}
                for test_id, name, value, unit, limit, verdict in tests
            ],
            "measurement_replicates": 3,
        },
        "bench_request": "SMP-PGD-E2E-001",
    }


def bench_test_input(project_path: Path, run_id: str, batch_reference: str, sample_reference: str,
                     iteration: int, event_time: float | None, event_occurred: bool,
                     stop_reason: str, censoring_type: str) -> dict:
    record = {
        "run_id": run_id,
        "bench_reference": BENCH_ID,
        "batch_reference": batch_reference,
        "sample_reference": sample_reference,
        "protocol_version": "BENCH_PROTOCOL_V2",
        "setpoints": ["load 1.5 kN", "speed 1200 rpm", "temperature 80 degC"],
        "environment": {"temperature_c": 23.5, "humidity_percent": 45.0},
        "raw_record_reference": f"RAW-{run_id}",
        "event_occurred": event_occurred,
        "event_time": event_time,
        "censoring_type": censoring_type,
        "stop_reason": stop_reason,
        "anomalies": [],
        "campaign_iteration": iteration,
    }
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
        "bench_test": record,
    }


def experiment_input(project_path: Path, method_path: Path, design_space_path: Path,
                     experiment_design_path: Path, doe_output_path: Path) -> tuple[dict, str]:
    digest = hashlib.sha256(doe_output_path.read_bytes()).hexdigest()
    doe = read_json(doe_output_path)
    runs = []
    values = [2.55, 2.60, 2.65, 2.58]
    for index, point in enumerate(doe["result"]["runs"], start=1):
        runs.append(
            {
                "run_id": f"EXP-RUN-PGD-E2E-{index:03d}",
                "material_batch": "BAT-PGD-E2E-001",
                "formula_reference": "FORM-PG-E2E@v1",
                "formula_version": "v1",
                "doe_point_reference": {"run_index": point["run_index"]},
                "execution_provenance": {
                    "executed_at": "2026-12-06T09:30:00+08:00",
                    "operator_reference": "Operator OP-E2E-01",
                    "instrument_reference": f"SRV rig SRV-E2E-{index:02d}",
                    "calibration_reference": "CAL-E2E-2026-12",
                    "raw_record_reference": f"RAW-EXP-PGD-E2E-{index:03d}",
                },
                "response_measurements": [
                    {
                        "ctq_reference": CTQ_ID,
                        "method_reference": {"method_id": METHOD_ID, "qualification_reference": "E-TM-PG-E2E-BATCH"},
                        "measurement": measurement(values[(index - 1) % len(values)], "um", "BAT-PGD-E2E-001", "v1"),
                    }
                ],
            }
        )
    data = {
        "project_artifact": project_path.name,
        "challenge_artifact": "challenge.json",
        "failure_ctq_artifact": "failure_ctq.json",
        "test_method_artifact": method_path.name,
        "design_space_artifact": design_space_path.name,
        "experiment_design_artifact": experiment_design_path.name,
        "doe_output_artifact": doe_output_path.name,
        "doe_output_digest": digest,
        "experiment": {
            "experiment_id": "EXP-PGD-E2E-001",
            "evidence": [
                {
                    "evidence_id": "E-X-PGD-E2E-001",
                    "statement": f"{SIM}: synthetic observed measurement.",
                    "source": SIM,
                    "status": "OBSERVED",
                }
            ],
            "runs": runs,
        },
    }
    return data, digest


def variance_input(project_path: Path, bench_test_paths: list[Path]) -> dict:
    observations = [
        ("OBS-PGD-E2E-001", "ARM-CANDIDATE", "SMP-PGD-E2E-001", "BAT-PGD-E2E-001", "RUN-PGD-E2E-001", 2.55),
        ("OBS-PGD-E2E-002", "ARM-CANDIDATE", "SMP-PGD-E2E-001", "BAT-PGD-E2E-001", "RUN-PGD-E2E-002", 2.60),
        ("OBS-PGD-E2E-003", "ARM-REFERENCE", "SMP-PGD-E2E-002", "BAT-PGD-E2E-002", "RUN-PGD-E2E-003", 4.40),
        ("OBS-PGD-E2E-004", "ARM-REFERENCE", "SMP-PGD-E2E-002", "BAT-PGD-E2E-002", "RUN-PGD-E2E-004", 4.45),
    ]
    return {
        "campaign_reference": "CMP-PGD-E2E-001",
        "variance_id": "VAR-PGD-E2E-001",
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
                {"level": "BATCH", "n": 2, "group_reference": "ARM-CANDIDATE", "batch_reference": "BAT-PGD-E2E-001", "sample_reference": "SMP-PGD-E2E-001"},
                {"level": "BATCH", "n": 2, "group_reference": "ARM-REFERENCE", "batch_reference": "BAT-PGD-E2E-002", "sample_reference": "SMP-PGD-E2E-002"},
                {"level": "BENCH", "n": 2, "group_reference": "RUN-PGD-E2E-001", "batch_reference": "BAT-PGD-E2E-001", "sample_reference": "SMP-PGD-E2E-001"},
                {"level": "BENCH", "n": 2, "group_reference": "RUN-PGD-E2E-002", "batch_reference": "BAT-PGD-E2E-001", "sample_reference": "SMP-PGD-E2E-001"},
                {"level": "BENCH", "n": 2, "group_reference": "RUN-PGD-E2E-003", "batch_reference": "BAT-PGD-E2E-002", "sample_reference": "SMP-PGD-E2E-002"},
                {"level": "BENCH", "n": 2, "group_reference": "RUN-PGD-E2E-004", "batch_reference": "BAT-PGD-E2E-002", "sample_reference": "SMP-PGD-E2E-002"},
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
                    "at": ("2026-12-10T09:00:00Z" if value < 3 else "2026-12-11T09:00:00Z"),
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
            # A recorded absence: no equipment intervention happened inside the
            # observation windows, so no observation is confounded.
            "intervention_events": [],
        },
        "evidence": [
            {
                "evidence_id": "E-VAR-PG-E2E-001",
                "statement": f"{SIM}: variance-assessment request VAR-PGD-E2E-001 is recorded for contract validation only; it is not product evidence.",
                "source": SIM,
                "status": "ASSUMED",
            }
        ],
    }


def model_input(project_path: Path, method_path: Path, design_space_path: Path,
                experiment_design_path: Path, experiment_path: Path,
                batch_path: Path, screening_path: Path, bench_test_path: Path, variance_path: Path) -> dict:
    return {
        "project_artifact": project_path.name,
        "challenge_artifact": "challenge.json",
        "failure_ctq_artifact": "failure_ctq.json",
        "test_method_artifact": method_path.name,
        "design_space_artifact": design_space_path.name,
        "experiment_design_artifact": experiment_design_path.name,
        "experiment_artifact": experiment_path.name,
        "batch_artifact": batch_path.name,
        "screening_artifact": screening_path.name,
        "bench_test_artifact": bench_test_path.name,
        "variance_artifact": variance_path.name,
        "analysis": {
            "model_id": "MODEL-PGD-E2E-001",
            "requested_analyses": ["ANOVA", "REGRESSION", "RESIDUAL"],
            "response_references": [{"ctq_reference": CTQ_ID, "test_method_reference": METHOD_ID}],
            "evidence": [
                {
                    "evidence_id": "E-M-PG-E2E-001",
                    "statement": f"{SIM}: analysis scope supplied for contract validation only.",
                    "source": SIM,
                    "status": "ASSUMED",
                }
            ],
        },
    }


def application_input(process_window_reference: str | None) -> dict:
    criteria = [
        ("C-STARTUP", "Start-up torque at -40 degC below the OEM ceiling.", 0.35, "<=", "Nm"),
        ("C-BACKLASH", "Backlash drift after the duty cycle below the limit.", 3.0, "<=", "arcmin"),
        ("C-TEMPRISE", "Steady-state temperature rise below the limit.", 45.0, "<=", "K"),
        ("C-LIFE", "No torque-rise event within the validated life condition.", 6000.0, ">=", "h"),
    ]
    application = {
        "application_id": "APP-PGD-E2E-001",
        "project_reference": PROJECT_ID,
        "formula_reference": "FORM-PG-E2E@v1",
        "bench_references": [BENCH_ID],
        "acceptance_criteria": [
            {
                "criterion_id": criterion_id,
                "statement": statement,
                "threshold": threshold,
                "operator": operator,
                "unit": unit,
                "source": SIM,
                "evidence_id": "EV-APP-PGD-E2E-001",
                "status": "OBSERVED",
            }
            for criterion_id, statement, threshold, operator, unit in criteria
        ],
        "result": "PASS",
        "counterexamples": [],
        "life_claim_boundary": {
            "claim_scope": "10-year service life at the rated duty",
            "status": "OBSERVED",
            "validated_conditions": [
                {"condition_id": "LC-1", "parameter": "temperature", "lower_bound": 40, "upper_bound": 100, "unit": "degC"}
            ],
            "extrapolation_basis": "Synthetic bench extrapolation",
            "evidence_reference": "EV-APP-PGD-E2E-001",
        },
        "source": SIM,
        "evidence_id": "EV-APP-PGD-E2E-001",
        "evidence_scope": "PHYSICAL",
        "evidence": [
            {
                "evidence_id": "EV-APP-PGD-E2E-001",
                "statement": f"{SIM}: machine protocol run supplied for contract validation only; not product evidence.",
                "source": SIM,
                "status": "ASSUMED",
            }
        ],
    }
    # process_window_reference is permitted but never demanded; the window
    # artifact cannot be produced on this route, so the record omits the citation
    # rather than pointing at a record that does not exist.
    if process_window_reference is not None:
        application["process_window_reference"] = process_window_reference
    return {"application": application}


def application_validation_input(application_path: Path, campaign_path: Path, bench_test_path: Path) -> dict:
    return {
        "application_validation": {
            "project_reference": PROJECT_ID,
            "current_stage": "VERIFIED",
            "application": read_json(application_path),
            "project_type": PROJECT_TYPE,
            "campaign_artifact": campaign_path.name,
            "bench_test_artifact": bench_test_path.name,
            "machine_indicators": [
                {"indicator": "START_UP_TORQUE", "criterion_reference": "C-STARTUP"},
                {"indicator": "BACKLASH", "criterion_reference": "C-BACKLASH"},
                {"indicator": "TEMPERATURE_RISE", "criterion_reference": "C-TEMPRISE"},
                {"indicator": "LIFE", "criterion_reference": "C-LIFE"},
            ],
        }
    }


def knowledge_input(project_path: Path) -> dict:
    """The KNOWLEDGE_ARCHIVED request, with each asset reference bound to a real record.

    ``knowledge_assets.<key>.artifact_reference`` is a free-text reference, so this
    request points every one of the six assets at the artifact of this workspace
    that actually carries it (the workspace root is the request's own directory,
    exactly as the other artifact references in this chain resolve). main() then
    asserts each reference RESOLVES -- the file exists and carries the artifact
    type / stage the asset names -- so the six ``present`` flags are a claim the
    chain can check, not the test reading its own request back.
    """
    return {
        "project_artifact": project_path.name,
        "asset_status": "CLOSED_KNOWLEDGE",
        "knowledge_assets": {
            # The stage-16 optimization artifact records the recommended formula
            # (its objectives and methods are what the closed loop recommends).
            "recommended_formula": {"artifact_reference": "optimization.json", "present": True},
            "feasible_design_space": {"artifact_reference": "design_space.json", "present": True},
            "critical_failure_boundaries": {"artifact_reference": "failure_ctq.json", "present": True},
            # The evidence package is the applied/validated record; its
            # qualification reference is the gate review that verified the chain.
            "evidence_package": {
                "artifact_reference": "application.json",
                "present": True,
                "qualification_reference": "gate.json",
                "qualification": "QUALIFIED",
            },
            "material_knowledge": {"artifact_reference": "material-base-oil.json", "present": True},
            "model": {"artifact_reference": "model.json", "present": True},
        },
        "evidence_scope": "PHYSICAL",
        "evidence": [
            {
                "evidence_id": "E-KA-PGD-E2E-001",
                "statement": f"{SIM}: the closure evidence package is qualified.",
                "source": SIM,
                "status": "OBSERVED",
            }
        ],
    }


# ---------------------------------------------------------------------------
# the chain
# ---------------------------------------------------------------------------


def optimization_input(project_path: Path, method_path: Path, design_space_path: Path,
                       experiment_design_path: Path, experiment_path: Path, model_path: Path,
                       variance_path: Path) -> dict:
    return {
        "project_artifact": project_path.name,
        "challenge_artifact": "challenge.json",
        "failure_ctq_artifact": "failure_ctq.json",
        "test_method_artifact": method_path.name,
        "design_space_artifact": design_space_path.name,
        "experiment_design_artifact": experiment_design_path.name,
        "experiment_artifact": experiment_path.name,
        "model_artifact": model_path.name,
        "variance_artifact": variance_path.name,
        "model_trust_region": {
            "variable_references": ["VAR-SOAP-CONCENTRATION", "VAR-BASE-OIL-FRACTION", "VAR-SOAP-HOLD-TIME"],
            "region_statement": f"{SIM}: the model was fitted over the bounded factor box used by the recorded design points.",
            "lower_bounds": {"VAR-SOAP-CONCENTRATION": 8.0, "VAR-BASE-OIL-FRACTION": 80.0, "VAR-SOAP-HOLD-TIME": 20.0},
            "upper_bounds": {"VAR-SOAP-CONCENTRATION": 14.0, "VAR-BASE-OIL-FRACTION": 92.0, "VAR-SOAP-HOLD-TIME": 60.0},
            "basis": SIM,
            "source": SIM,
        },
        "optimization": {
            "optimization_id": "OPT-PGD-E2E-001",
            "objectives": [
                {
                    "response_reference": CTQ_ID,
                    "direction": "MINIMIZE",
                    "criterion": "Meet the supplied CTQ boundary.",
                }
            ],
            "methods": ["NON_INFERIORITY"],
            "evidence": [
                {
                    "evidence_id": "E-OPT-PGD-E2E-001",
                    "statement": f"{SIM}: optimization scope supplied for the precision-grease route.",
                    "source": SIM,
                    "status": "ASSUMED",
                }
            ],
        },
    }


def scale_up_input(process_path: Path, optimization_path: Path) -> dict:
    return {
        "process_artifact": process_path.name,
        "optimization_artifact": optimization_path.name,
        "scale_up": {
            "window_id": "PW-PGD-E2E-001-PROD",
            "basis": f"{SIM}: pilot-to-production amplification basis for the grease route.",
            "amplification_factor": 200.0,
            "batch_scale": {
                "scale_class": "PRODUCTION",
                "batch_size": measurement(500, "kg", "BATCH-PGD-E2E-PROD-001", "v0.2"),
            },
            "evidence_scope": "SYNTHETIC",
            "evidence": [
                {
                    "evidence_id": "EV-PGD-E2E-SCALE-001",
                    "statement": f"{SIM}: amplification run reproduced the window at production scale.",
                    "source": f"{SIM} + OPT-PGD-E2E-001",
                    "status": "OBSERVED",
                }
            ],
        },
    }


def gate_request(project_path: Path, challenge_path: Path, failure_path: Path, method_path: Path,
                 design_space_path: Path, experiment_design_path: Path, experiment_path: Path,
                 model_path: Path, optimization_path: Path) -> dict:
    return {
        "project_artifact": project_path.name,
        "challenge_artifact": challenge_path.name,
        "failure_ctq_artifact": failure_path.name,
        "test_method_artifact": method_path.name,
        "design_space_artifact": design_space_path.name,
        "experiment_design_artifact": experiment_design_path.name,
        "experiment_artifact": experiment_path.name,
        "model_artifact": model_path.name,
        "optimization_artifact": optimization_path.name,
        "gate": {
            "gate_id": "GATE-PGD-E2E-001",
            "scope": f"{SIM}: precision-gear grease chain review.",
            "gate_status": "GO",
            "satisfied_conditions": ["Linked experiment, model, variance and optimization records are present."],
            "unsatisfied_conditions": [],
            "evidence_gaps": [],
            "risks": ["Synthetic fixtures do not establish product performance."],
            "reason": "All supplied synthetic review conditions are satisfied.",
            "evidence": [
                {
                    "evidence_id": "E-G-PGD-E2E-001",
                    "statement": f"{SIM}: synthetic review evidence supplied.",
                    "source": SIM,
                    "status": "OBSERVED",
                }
            ],
        },
    }


def next_batch_input(campaign_path: Path, experiment_design_path: Path, variance_path: Path) -> dict:
    """The NEXT_BATCH_DECIDED request for doe-design's next_batch producer.

    Shape is the skill's own (preflight_next_batch -> build_next_batch_artifact ->
    validate_next_batch_artifact): the three upstream records the decision is
    taken at, plus the record's own fields. The two competing explanations are
    DECLARED here because the gate refuses to compose one, and every proposed
    sample quotes its discriminating pair from those declarations. The iteration
    pair (from_iteration/to_iteration) is not supplied at all: the builder derives
    it from the campaign carrier, so the record cannot claim a round boundary the
    campaign does not have.
    """
    return {
        "campaign_artifact": campaign_path.name,
        "experiment_design_artifact": experiment_design_path.name,
        "variance_artifact": variance_path.name,
        "next_batch": {
            "next_batch_id": "NEXT-PGD-E2E-001",
            "stop_state": "CONTINUE",
            "bench_slots_required": 2,
            "information_gain_basis": (
                f"{SIM}: the two proposed samples are the swapped halves of the round 1 pair, so the round 2 "
                "contrast cancels bench drift instead of measuring it, which no single-arm sample can do."
            ),
            "competing_explanations": [
                {
                    "explanation_id": "EXPL-FORMULATION-EFFECT",
                    "statement": "The round 1 arm difference is a formulation effect that travels with the formula.",
                },
                {
                    "explanation_id": "EXPL-BENCH-DRIFT",
                    "statement": "The round 1 arm difference is bench-to-bench drift that follows the run order.",
                },
            ],
            "proposed_samples": [
                {
                    "sample_reference": "SMP-PGD-E2E-003",
                    "hypothesis": "EXPL-FORMULATION-EFFECT",
                    "separates": ["EXPL-FORMULATION-EFFECT", "EXPL-BENCH-DRIFT"],
                },
                {
                    "sample_reference": "SMP-PGD-E2E-004",
                    "hypothesis": "EXPL-BENCH-DRIFT",
                    "separates": ["EXPL-FORMULATION-EFFECT", "EXPL-BENCH-DRIFT"],
                },
            ],
            "next_round_budget": {"bench_slots_remaining": 4, "calendar_days_remaining": 60},
            "evidence": [
                {
                    "evidence_id": "E-NB-PGD-E2E-001",
                    "statement": f"{SIM}: the round 1 variance assessment reports a consistent arm difference.",
                    "source": SIM,
                    "status": "ASSUMED",
                },
                {
                    "evidence_id": "E-NB-PGD-E2E-002",
                    "statement": f"{SIM}: the campaign record still has bench slots left before max_iterations.",
                    "source": SIM,
                    "status": "ASSUMED",
                },
            ],
        },
    }


def main() -> int:
    contract = read_json(CONTRACT)
    route = tuple(contract["type_routes"][PROJECT_TYPE])
    assert route == EXPECTED_ROUTE, route
    listed = run(ROUTE_SCRIPT, "--list-stages", PROJECT_TYPE)
    assert listed.returncode == 0 and tuple(listed.stdout.splitlines()) == EXPECTED_ROUTE, listed.stdout

    router = load_module(ROUTE_SCRIPT, "e2e_route_step")

    def route_allow(previous: str, requested: str) -> str:
        result = router.decide(
            {
                "stage": previous,
                "status": "ACTIVE",
                "evidence_scope": "PHYSICAL",
                "project_type": PROJECT_TYPE,
            },
            requested,
        )
        assert result["decision"] == "ALLOW", (previous, requested, result)
        assert result["skill"] == STAGE_SKILL[requested], (requested, result)
        return result["skill"]

    # A cross-stage jump must be denied: without this the ALLOW assertions above
    # could pass against a router that allows everything.
    denied = router.decide(
        {"stage": "DUTY_DEFINED", "status": "ACTIVE", "evidence_scope": "PHYSICAL", "project_type": PROJECT_TYPE},
        "REFERENCE_MATERIAL_RESOLVED",
    )
    assert denied["decision"] == "DENY" and "cross-stage jump rejected" in denied["reason"], denied

    stage_script = {
        name: SKILLS / skill / "scripts"
        for name, skill in STAGE_SKILL.items()
    }

    with tempfile.TemporaryDirectory() as temporary:
        ws = Path(temporary)
        # Request files and artifacts live in the same workspace root: the skills
        # resolve upstream paths relative to the request file's parent, and
        # grease-batch/gate-review/knowledge-archive additionally police the
        # workspace's canonical artifact names. Request files carry an
        # ``input-`` prefix so the naming checker reads them as unrelated.

        # Stages that ARE driven by their skill are appended to ``driven_stages`` at
        # the point of the drive; ``stage_gaps`` exists only as the safety net for a
        # stage that has to be skipped, and the coverage assertion at the end of main
        # requires it to be EMPTY and the driven list to equal the whole route. A
        # skip therefore has to be recorded here on purpose -- it can never hide
        # behind a printout.
        stage_gaps: dict[str, str] = {}
        driven_stages: list[str] = []

        def write_input(name: str, payload: object) -> Path:
            path = ws / name
            write_json(path, payload)
            return path

        def drive(preflight: Path, builder: Path | None, validator: Path | None, request: Path, artifact: str) -> Path:
            run_ok(preflight, request)
            path = ws / artifact
            if builder is not None:
                run_ok(builder, request, path)
            if validator is not None:
                run_ok(validator, path)
            return path

        # --- 1. PROJECT_DEFINED (project-definition) ---------------------------
        # The builder this stage is driven with is asserted to exist first: a skill
        # that silently loses its writer is a coverage regression, not a skip.
        project_builder = stage_script["PROJECT_DEFINED"] / "build_project_artifact.py"
        assert project_builder.is_file(), (
            "project-definition ships no build_project_artifact.py: the route's own charter can no longer be "
            "produced by the skill, so PROJECT_DEFINED cannot be driven (update this test only with the drive "
            "replaced by a real producer)"
        )
        route_allow("DRAFT", "PROJECT_DEFINED")
        project_request = write_input("input-project.json", project_input())
        project_path = drive(
            stage_script["PROJECT_DEFINED"] / "preflight_project_definition.py",
            project_builder,
            stage_script["PROJECT_DEFINED"] / "validate_project_artifact.py",
            project_request,
            "project.json",
        )
        project_record = check_schema("project", project_path)
        assert project_record["project_type"] == PROJECT_TYPE, project_record
        assert project_record["stage"] == "PROJECT_DEFINED", project_record["stage"]
        assert project_record["decision"] == "GO" and project_record["status"] == "ACTIVE", project_record
        driven_stages.append("PROJECT_DEFINED")

        # The route's own cost semantics must stay reachable: on a grease charter the
        # cost is a ceiling to respect, not a reduction target, so the schema allows
        # cost_ceiling + cost_basis_reason instead of target_cost. A preflight that
        # out-requires the schema would make that branch dead and force every grease
        # charter to declare a target it does not have -- this asserts it does not.
        # (Built into its own probe directory: the chain workspace keeps exactly one
        # charter, and a second one there is itself a finding.)
        ceiling_request = write_input("input-project-ceiling.json", project_ceiling_input())
        ceiling_dir = ws / "cost-ceiling-probe"
        ceiling_dir.mkdir(parents=True, exist_ok=True)
        ceiling_path = ceiling_dir / "project.json"
        run_ok(stage_script["PROJECT_DEFINED"] / "preflight_project_definition.py", ceiling_request)
        run_ok(project_builder, ceiling_request, ceiling_path)
        run_ok(stage_script["PROJECT_DEFINED"] / "validate_project_artifact.py", ceiling_path)
        ceiling_record = check_schema("project", ceiling_path)
        assert "target_cost" not in ceiling_record, ceiling_record
        assert ceiling_record["cost_ceiling"]["value"] == 220, ceiling_record["cost_ceiling"]

        # --- 2. DUTY_DEFINED (duty-definition) ---------------------------------
        route_allow("PROJECT_DEFINED", "DUTY_DEFINED")
        duty_request = write_input("input-duty.json", duty_input(project_path))
        duty_path = drive(
            stage_script["DUTY_DEFINED"] / "preflight_duty_definition.py",
            stage_script["DUTY_DEFINED"] / "build_duty_artifact.py",
            stage_script["DUTY_DEFINED"] / "validate_duty_artifact.py",
            duty_request,
            "duty.json",
        )
        check_schema("duty", duty_path)
        driven_stages.append("DUTY_DEFINED")

        # Supporting material for the next stage: the Challenge Map member. It is
        # produced by duty-challenge-analysis (a stage this route does not carry)
        # and is consumed as an upstream artifact by failure-ctq-analysis.
        challenge_request = write_input("input-challenge.json", challenge_input(duty_path, project_path))
        challenge_path = drive(
            SKILLS / "duty-challenge-analysis" / "scripts" / "preflight_duty_challenge.py",
            SKILLS / "duty-challenge-analysis" / "scripts" / "build_duty_challenge_artifact.py",
            SKILLS / "duty-challenge-analysis" / "scripts" / "validate_duty_challenge_artifact.py",
            challenge_request,
            "challenge.json",
        )
        check_schema("challenge", challenge_path)

        # --- 3. FAILURE_MECHANISM_DEFINED (failure-ctq-analysis) ---------------
        route_allow("DUTY_DEFINED", "FAILURE_MECHANISM_DEFINED")
        failure_request = write_input("input-failure.json", failure_input(project_path, challenge_path))
        failure_path = drive(
            stage_script["FAILURE_MECHANISM_DEFINED"] / "preflight_failure_ctq.py",
            stage_script["FAILURE_MECHANISM_DEFINED"] / "build_failure_ctq_artifact.py",
            stage_script["FAILURE_MECHANISM_DEFINED"] / "validate_failure_ctq_artifact.py",
            failure_request,
            "failure_ctq.json",
        )
        failure_artifact = check_schema("failure_ctq", failure_path)
        assert failure_artifact["stage"] == "FAILURE_CTQ_DEFINED", failure_artifact["stage"]
        driven_stages.append("FAILURE_MECHANISM_DEFINED")

        # --- 4. REFERENCE_MATERIAL_RESOLVED (reference-material) ---------------
        route_allow("FAILURE_MECHANISM_DEFINED", "REFERENCE_MATERIAL_RESOLVED")
        reference_request = write_input("input-reference.json", reference_input(project_path))
        reference_path = drive(
            stage_script["REFERENCE_MATERIAL_RESOLVED"] / "preflight_reference_material.py",
            stage_script["REFERENCE_MATERIAL_RESOLVED"] / "build_reference_artifact.py",
            stage_script["REFERENCE_MATERIAL_RESOLVED"] / "validate_reference_artifact.py",
            reference_request,
            "reference.json",
        )
        reference_artifact = check_schema("reference", reference_path)
        assert reference_artifact["downstream_flag"] == "DISCRIMINATION_EVIDENCE_COMPLETE", reference_artifact
        driven_stages.append("REFERENCE_MATERIAL_RESOLVED")

        # --- 5. TEST_METHODS_QUALIFIED (test-method-qualification) -------------
        route_allow("REFERENCE_MATERIAL_RESOLVED", "TEST_METHODS_QUALIFIED")
        method_request = write_input("input-test-method.json", test_method_input(project_path, challenge_path, failure_path, reference_path))
        method_path = drive(
            stage_script["TEST_METHODS_QUALIFIED"] / "preflight_test_method.py",
            stage_script["TEST_METHODS_QUALIFIED"] / "build_test_method_artifact.py",
            stage_script["TEST_METHODS_QUALIFIED"] / "validate_test_method_artifact.py",
            method_request,
            "test_method.json",
        )
        check_schema("test_method", method_path)
        driven_stages.append("TEST_METHODS_QUALIFIED")

        # --- 6. DESIGN_SPACE_DEFINED (formulation-design) ----------------------
        route_allow("TEST_METHODS_QUALIFIED", "DESIGN_SPACE_DEFINED")
        for index, material in enumerate(material_artifacts(), start=1):
            path = ws / ("material-base-oil.json" if index == 1 else "material-thickener-raw.json")
            write_json(path, material)
            check_schema("material", path)
        design_space_request = write_input(
            "input-design-space.json", design_space_input(project_path, challenge_path, failure_path, method_path)
        )
        design_space_path = drive(
            stage_script["DESIGN_SPACE_DEFINED"] / "preflight_formulation_design.py",
            stage_script["DESIGN_SPACE_DEFINED"] / "build_design_space_artifact.py",
            stage_script["DESIGN_SPACE_DEFINED"] / "validate_design_space_artifact.py",
            design_space_request,
            "design_space.json",
        )
        check_schema("design_space", design_space_path)
        # Companion artifact of this step: the fixed process baseline.
        process_request = write_input("input-process-baseline.json", process_input(design_space_path))
        process_baseline_path = drive(
            SKILLS / "process-definition" / "scripts" / "preflight_process_definition.py",
            SKILLS / "process-definition" / "scripts" / "build_process_artifact.py",
            SKILLS / "process-definition" / "scripts" / "validate_process_artifact.py",
            process_request,
            "process-baseline.json",
        )
        baseline_artifact = check_schema("process", process_baseline_path)
        assert baseline_artifact["stage"] == "DESIGN_SPACE_DEFINED", baseline_artifact["stage"]
        driven_stages.append("DESIGN_SPACE_DEFINED")

        # --- 7. BENCH_RESOURCE_REGISTERED (bench-registration) -----------------
        route_allow("DESIGN_SPACE_DEFINED", "BENCH_RESOURCE_REGISTERED")
        bench_request = write_input("input-bench.json", bench_input())
        bench_path = drive(
            stage_script["BENCH_RESOURCE_REGISTERED"] / "preflight_bench_registration.py",
            stage_script["BENCH_RESOURCE_REGISTERED"] / "build_bench_artifact.py",
            stage_script["BENCH_RESOURCE_REGISTERED"] / "validate_bench_artifact.py",
            bench_request,
            "bench.json",
        )
        bench_artifact = check_schema("bench", bench_path)
        assert bench_artifact["available_bench_slots"] == 4, bench_artifact["available_bench_slots"]
        assert bench_artifact["evidence_scope"] == "PHYSICAL", bench_artifact["evidence_scope"]
        driven_stages.append("BENCH_RESOURCE_REGISTERED")

        # --- 8. CAMPAIGN_OPENED (bench-registration) ---------------------------
        route_allow("BENCH_RESOURCE_REGISTERED", "CAMPAIGN_OPENED")
        # The router maps this stage to bench-registration, and the skill now ships
        # the campaign producer. Both facts are asserted BEFORE the drive: the
        # producer must exist (a silent removal would make this stage undrivable)
        # and must live in the skill the contract routes the stage to.
        campaign_producers = has_producer("campaign")
        assert campaign_producers, (
            "no script in the pack assembles a campaign artifact: CAMPAIGN_OPENED cannot be driven "
            "(the drive below needs a real campaign producer under the routed skill)"
        )
        assert any(Path(hit).parts[:2] == ("skills", STAGE_SKILL["CAMPAIGN_OPENED"]) for hit in campaign_producers), (
            "the campaign producer exists but does not live under the routed skill: " + repr(campaign_producers)
        )
        campaign_request = write_input("input-campaign.json", campaign_input(project_path, bench_path))
        campaign_path = drive(
            stage_script["CAMPAIGN_OPENED"] / "preflight_campaign_registration.py",
            stage_script["CAMPAIGN_OPENED"] / "build_campaign_artifact.py",
            stage_script["CAMPAIGN_OPENED"] / "validate_campaign_artifact.py",
            campaign_request,
            "campaign.json",
        )
        campaign_record = check_schema("campaign", campaign_path)
        assert campaign_record["stage"] == "CAMPAIGN_OPENED", campaign_record["stage"]
        assert campaign_record["decision"] == "GO", campaign_record["decision"]
        assert campaign_record["current_iteration"] == 1, campaign_record["current_iteration"]
        # The request omits the cap on purpose, so the artifact must carry the
        # contract's published figure and say where it came from -- a cap this
        # chain could see invented would be worse than no cap at all.
        assert "max_iterations" not in read_json(campaign_request)["campaign"], "the contract-default path is the one under test"
        assert campaign_record["max_iterations"] == contract["max_iterations"], (
            campaign_record["max_iterations"], contract["max_iterations"]
        )
        assert any(item.get("source") == "contracts/state-machine.json" for item in campaign_record["evidence"]), (
            "the contract-derived cap must record its provenance on the artifact: " + repr(campaign_record["evidence"])
        )
        driven_stages.append("CAMPAIGN_OPENED")

        # The stage's NO Synthetic Closure gate is real: the same campaign on the
        # same bench, but with the bench record downgraded to SYNTHETIC, is refused.
        synthetic_bench = read_json(bench_path)
        synthetic_bench["evidence_scope"] = "SYNTHETIC"
        synthetic_bench_path = write_input("input-bench-synthetic.json", synthetic_bench)
        synthetic_campaign_request = write_input(
            "input-campaign-synthetic-bench.json",
            campaign_input(project_path, synthetic_bench_path),
        )
        synthetic_refusal = run(
            stage_script["CAMPAIGN_OPENED"] / "preflight_campaign_registration.py", synthetic_campaign_request
        )
        assert synthetic_refusal.returncode != 0 and CAMPAIGN_SYNTHETIC_BENCH_GAP in synthetic_refusal.stdout, (
            synthetic_refusal.stdout
        )
        print("gate ok: the campaign preflight refuses a PHYSICAL campaign drawing slots from a SYNTHETIC bench")

        # --- 9. EXPERIMENT_DESIGNED (doe-design) -------------------------------
        route_allow("CAMPAIGN_OPENED", "EXPERIMENT_DESIGNED")
        doe_request = write_input(
            "input-experiment-design.json",
            experiment_design_input(project_path, challenge_path, failure_path, method_path, design_space_path, bench_path),
        )
        experiment_design_path = drive(
            stage_script["EXPERIMENT_DESIGNED"] / "preflight_doe_design.py",
            stage_script["EXPERIMENT_DESIGNED"] / "build_experiment_design_artifact.py",
            stage_script["EXPERIMENT_DESIGNED"] / "validate_experiment_design_artifact.py",
            doe_request,
            "experiment_design.json",
        )
        design_artifact = check_schema("experiment_design", experiment_design_path)
        assert design_artifact["available_bench_slots"] == 4, design_artifact
        # The design is handed to the deterministic engine: the round the engine
        # draws is the DOE output the experiment import later consumes.
        engine_input = write_input("input-doe-engine-input.json", doe_engine_input())
        compute = subprocess.run(
            [sys.executable, "-B", "run_compute.py"],
            cwd=stage_script["EXPERIMENT_DESIGNED"],
            # The request handed to the engine is the file this test wrote, so the
            # record on disk is the one the engine actually consumed (never a
            # re-rendered copy of it).
            input=engine_input.read_text(encoding="utf-8"),
            capture_output=True,
            text=True,
        )
        assert compute.returncode == 0, compute.stdout + compute.stderr
        envelope = json.loads(compute.stdout)["result"]
        assert envelope["status"] == "OK", envelope.get("rejection_reasons")
        assert envelope["result"]["run_count"] == 4, envelope["result"]
        # The engine's own points are checked against the factor box the request
        # declared, and against each other: a run outside its declared bounds, or a
        # repeated corner, would make the batch (and the experiment import that
        # consumes this output) meaningless.
        declared = {factor["factor_id"]: factor["range"] for factor in doe_engine_input()["factors"]}
        points = envelope["result"]["runs"]
        assert len(points) == 4, points
        for point in points:
            for factor_id, value in point["settings"].items():
                lower, upper = declared[factor_id]["lower"], declared[factor_id]["upper"]
                assert lower <= value <= upper, (point, factor_id, lower, upper)
        assert len({tuple(sorted(point["settings"].items())) for point in points}) == 4, points
        doe_output_path = ws / "doe-output.json"
        write_json(doe_output_path, envelope)
        driven_stages.append("EXPERIMENT_DESIGNED")

        # --- 10. BATCH_PRODUCED (grease-batch) ---------------------------------
        route_allow("EXPERIMENT_DESIGNED", "BATCH_PRODUCED")
        batch_request = write_input("input-batch.json", batch_input(project_path, design_space_path, experiment_design_path))
        batch_path = drive(
            stage_script["BATCH_PRODUCED"] / "preflight_grease_batch.py",
            stage_script["BATCH_PRODUCED"] / "build_batch_artifact.py",
            stage_script["BATCH_PRODUCED"] / "validate_batch_artifact.py",
            batch_request,
            "batch.json",
        )
        batch_artifact = check_schema("batch", batch_path)
        assert batch_artifact["decision"] == "GO", batch_artifact["decision"]
        sample_path = ws / "sample.json"
        check_schema("sample", sample_path)
        assert read_json(sample_path)["sample_id"] == "SMP-PGD-E2E-001", read_json(sample_path)
        driven_stages.append("BATCH_PRODUCED")

        # --- 11. SCREENING_PASSED (grease-screening) ---------------------------
        route_allow("BATCH_PRODUCED", "SCREENING_PASSED")
        screening_request = write_input("input-screening.json", screening_input(project_path, batch_path))
        screening_path = drive(
            stage_script["SCREENING_PASSED"] / "preflight_grease_screening.py",
            stage_script["SCREENING_PASSED"] / "build_screening_artifact.py",
            stage_script["SCREENING_PASSED"] / "validate_screening_artifact.py",
            screening_request,
            "screening.json",
        )
        screening_artifact = check_schema("screening", screening_path)
        assert screening_artifact["decision"] == "GO", screening_artifact["decision"]
        driven_stages.append("SCREENING_PASSED")

        # --- 12. BENCH_TESTED (experiment-import, bench path) ------------------
        route_allow("SCREENING_PASSED", "BENCH_TESTED")
        bench_runs = [
            ("RUN-PGD-E2E-001", "BAT-PGD-E2E-001", "SMP-PGD-E2E-001", 2.55, True, "event observed inside the protocol window", "NONE"),
            ("RUN-PGD-E2E-002", "BAT-PGD-E2E-001", "SMP-PGD-E2E-001", 2.60, True, "event observed inside the protocol window", "NONE"),
            ("RUN-PGD-E2E-003", "BAT-PGD-E2E-002", "SMP-PGD-E2E-002", 4.40, True, "event observed inside the protocol window", "NONE"),
            ("RUN-PGD-E2E-004", "BAT-PGD-E2E-002", "SMP-PGD-E2E-002", 4.45, True, "event observed inside the protocol window", "NONE"),
        ]
        bench_test_paths = []
        for index, (run_id, batch_reference, sample_reference, event_time, occurred, stop_reason, censoring) in enumerate(bench_runs):
            request = write_input(
                f"input-bench-test-{run_id}.json",
                bench_test_input(project_path, run_id, batch_reference, sample_reference, 1, event_time, occurred, stop_reason, censoring),
            )
            artifact_name = "bench_test.json" if index == 0 else f"bench_test-{PROJECT_ID}-{run_id}.json"
            path = drive(
                stage_script["BENCH_TESTED"] / "preflight_experiment_import.py",
                stage_script["BENCH_TESTED"] / "build_bench_test_artifact.py",
                stage_script["BENCH_TESTED"] / "validate_bench_test_artifact.py",
                request,
                artifact_name,
            )
            artifact = check_schema("bench_test", path)
            assert artifact["stage"] == "BENCH_TESTED", artifact["stage"]
            bench_test_paths.append(path)
        # The censoring discipline is real: an event-free run without a declared
        # reason is refused (never silently recorded as an end-point).
        bad_censoring = write_input(
            "input-bench-test-invalid-censoring.json",
            bench_test_input(project_path, "RUN-PGD-E2E-BAD", "BAT-PGD-E2E-001", "SMP-PGD-E2E-001", 1, None, False, "", "NONE"),
        )
        refused = run(stage_script["BENCH_TESTED"] / "preflight_experiment_import.py", bad_censoring)
        assert refused.returncode != 0 and "stop_reason" in refused.stdout, refused.stdout

        # Supporting material: one DOE_POINT experiment import beside the bench
        # runs. MODEL_BUILT (statistical-analysis) still requires the
        # EXPERIMENT_RUNNING artifact on this route.
        experiment_request = write_input(
            "input-experiment.json",
            experiment_input(project_path, method_path, design_space_path, experiment_design_path, doe_output_path)[0],
        )
        experiment_path = drive(
            stage_script["BENCH_TESTED"] / "preflight_experiment_import.py",
            stage_script["BENCH_TESTED"] / "build_experiment_artifact.py",
            stage_script["BENCH_TESTED"] / "validate_experiment_artifact.py",
            experiment_request,
            "experiment.json",
        )
        experiment_artifact = check_schema("experiment", experiment_path)
        assert experiment_artifact["stage"] == "EXPERIMENT_RUNNING", experiment_artifact["stage"]
        driven_stages.append("BENCH_TESTED")

        # --- 13. VARIANCE_ASSESSED (variance-assessment) -----------------------
        route_allow("BENCH_TESTED", "VARIANCE_ASSESSED")
        variance_request = write_input("input-variance.json", variance_input(project_path, bench_test_paths))
        variance_path = drive(
            stage_script["VARIANCE_ASSESSED"] / "preflight_variance_assessment.py",
            stage_script["VARIANCE_ASSESSED"] / "build_variance_artifact.py",
            stage_script["VARIANCE_ASSESSED"] / "validate_variance_artifact.py",
            variance_request,
            "variance.json",
        )
        variance_artifact = check_schema("variance", variance_path)
        assert variance_artifact["verdict"] == "CONSISTENT_DIFFERENCE", variance_artifact["verdict"]
        assert variance_artifact["decision"] == "GO", variance_artifact["decision"]
        assert variance_artifact["computed_by"] == "ENGINE", variance_artifact["computed_by"]
        driven_stages.append("VARIANCE_ASSESSED")

        # --- 14. MODEL_BUILT (statistical-analysis) ----------------------------
        route_allow("VARIANCE_ASSESSED", "MODEL_BUILT")
        model_request = write_input(
            "input-model.json",
            model_input(project_path, method_path, design_space_path, experiment_design_path,
                        experiment_path, batch_path, screening_path, bench_test_paths[0], variance_path),
        )
        model_path = drive(
            stage_script["MODEL_BUILT"] / "preflight_statistical_analysis.py",
            stage_script["MODEL_BUILT"] / "build_model_artifact.py",
            stage_script["MODEL_BUILT"] / "validate_model_artifact.py",
            model_request,
            "model.json",
        )
        model_artifact = check_schema("model", model_path)
        assert model_artifact["stage"] == "MODEL_BUILT", model_artifact["stage"]
        assert model_artifact["decision"] == "GO", model_artifact["decision"]
        # The route's bench_test record is UNDECIDED by contract (one bench run is a
        # record, not a verdict) and is still the upstream the model consumes: the
        # gate exempts it instead of demanding a verdict it must never carry. The
        # artifact's own links, derived by the builder rather than copied from the
        # request, are what bind the model to this chain.
        assert read_json(bench_test_paths[0])["decision"] == "UNDECIDED", read_json(bench_test_paths[0])["decision"]
        assert model_artifact["experiment_reference"] == experiment_artifact["experiment_id"], model_artifact
        assert model_artifact["design_space_reference"] == read_json(design_space_path)["design_space_id"], model_artifact
        assert METHOD_ID in model_artifact["test_method_references"], model_artifact
        driven_stages.append("MODEL_BUILT")

        # The grease precondition is keyed on the supplied charter's project_type,
        # not on the request shape: the same PRECISION_GREASE_DEV analysis with the
        # four inner-loop artifacts omitted is REFUSED. (The fail-open hole this
        # chain used to record is closed; the refusal wording is the gate's own.)
        oil_shaped_payload = model_input(project_path, method_path, design_space_path, experiment_design_path,
                                         experiment_path, batch_path, screening_path, bench_test_paths[0], variance_path)
        for key in ("batch_artifact", "screening_artifact", "bench_test_artifact", "variance_artifact"):
            del oil_shaped_payload[key]
        oil_shaped_request = write_input("input-model-oil-shaped.json", oil_shaped_payload)
        oil_shaped_probe = run(
            stage_script["MODEL_BUILT"] / "preflight_statistical_analysis.py", oil_shaped_request
        )
        assert oil_shaped_probe.returncode != 0 and GREASE_PRECONDITION_GAP in oil_shaped_probe.stdout, (
            oil_shaped_probe.stdout
        )
        print("gate ok: statistical-analysis refuses a PRECISION_GREASE_DEV request that omits the four inner-loop artifacts")

        # --- 15. NEXT_BATCH_DECIDED (doe-design) --------------------------------
        route_allow("MODEL_BUILT", "NEXT_BATCH_DECIDED")
        next_batch_producers = has_producer("next_batch")
        assert next_batch_producers, (
            "no script in the pack assembles a next_batch artifact: NEXT_BATCH_DECIDED cannot be driven "
            "(the drive below needs a real next_batch producer under the routed skill)"
        )
        assert any(Path(hit).parts[:2] == ("skills", STAGE_SKILL["NEXT_BATCH_DECIDED"]) for hit in next_batch_producers), (
            "the next_batch producer exists but does not live under the routed skill: " + repr(next_batch_producers)
        )
        next_batch_request = write_input(
            "input-next-batch.json",
            next_batch_input(campaign_path, experiment_design_path, variance_path),
        )
        next_batch_path = drive(
            stage_script["NEXT_BATCH_DECIDED"] / "preflight_next_batch.py",
            stage_script["NEXT_BATCH_DECIDED"] / "build_next_batch_artifact.py",
            stage_script["NEXT_BATCH_DECIDED"] / "validate_next_batch_artifact.py",
            next_batch_request,
            "next_batch.json",
        )
        next_batch_record = check_schema("next_batch", next_batch_path)
        assert next_batch_record["stage"] == "NEXT_BATCH_DECIDED", next_batch_record["stage"]
        # The iteration pair is DERIVED from the campaign carrier (the request never
        # supplies it), so the record cannot claim a round boundary the campaign does
        # not have; the ids and the stop state must agree with the campaign's own
        # round-1 entry, which is what authorises this decision.
        assert (next_batch_record["from_iteration"], next_batch_record["to_iteration"]) == (1, 2), next_batch_record
        assert next_batch_record["campaign_reference"] == campaign_record["campaign_id"], next_batch_record
        assert next_batch_record["next_batch_id"] == campaign_record["iterations"][0]["next_batch_reference"], next_batch_record
        assert next_batch_record["stop_state"] == campaign_record["iterations"][0]["stop_state"] == "CONTINUE", next_batch_record
        assert next_batch_record["bench_slots_required"] == len(next_batch_record["proposed_samples"]) == 2, next_batch_record
        driven_stages.append("NEXT_BATCH_DECIDED")

        # The gate refuses to compose a hypothesis: a request that declares fewer
        # than two competing explanations is held, never filled in with a plausible one.
        singular_payload = next_batch_input(campaign_path, experiment_design_path, variance_path)
        singular_payload["next_batch"]["competing_explanations"] = singular_payload["next_batch"]["competing_explanations"][:1]
        singular_request = write_input("input-next-batch-single-explanation.json", singular_payload)
        singular_probe = run(stage_script["NEXT_BATCH_DECIDED"] / "preflight_next_batch.py", singular_request)
        assert singular_probe.returncode != 0 and NEXT_BATCH_EXPLANATIONS_GAP in singular_probe.stdout, (
            singular_probe.stdout
        )
        print("gate ok: the next-batch preflight refuses a request with fewer than two competing explanations")

        # --- 16. NON_INFERIORITY_PASSED (optimization) -------------------------
        route_allow("NEXT_BATCH_DECIDED", "NON_INFERIORITY_PASSED")
        optimization_request = write_input(
            "input-optimization.json",
            optimization_input(project_path, method_path, design_space_path, experiment_design_path,
                               experiment_path, model_path, variance_path),
        )
        optimization_path = drive(
            stage_script["NON_INFERIORITY_PASSED"] / "preflight_optimization.py",
            stage_script["NON_INFERIORITY_PASSED"] / "build_optimization_artifact.py",
            stage_script["NON_INFERIORITY_PASSED"] / "validate_optimization_artifact.py",
            optimization_request,
            "optimization.json",
        )
        optimization_artifact = check_schema("optimization", optimization_path)
        assert optimization_artifact["stage"] == "NON_INFERIORITY_PASSED", optimization_artifact["stage"]
        assert optimization_artifact["decision"] == "GO", optimization_artifact["decision"]
        # The links and the grease trust region are the builder's own derivations:
        # the artifact must cite the model and the round's variance record it was
        # optimized against, and carry the applicability boundary the grease route
        # requires, not a boundary the caller wrote.
        assert optimization_artifact["model_reference"] == model_artifact["model_id"], optimization_artifact
        assert optimization_artifact["variance_reference"] == variance_artifact["variance_id"], optimization_artifact
        assert optimization_artifact["objectives"][0]["response_reference"] == CTQ_ID, optimization_artifact
        assert optimization_artifact["engine_handoff"] == "PHASE4_DETERMINISTIC_ENGINE", optimization_artifact
        driven_stages.append("NON_INFERIORITY_PASSED")

        # --- 17. PROCESS_SCALE_VALIDATED (process-scale-up) --------------------
        route_allow("NON_INFERIORITY_PASSED", "PROCESS_SCALE_VALIDATED")
        scale_up_request = write_input("input-scale-up.json", scale_up_input(process_baseline_path, optimization_path))
        window_path = drive(
            stage_script["PROCESS_SCALE_VALIDATED"] / "preflight_process_scale_up.py",
            stage_script["PROCESS_SCALE_VALIDATED"] / "build_process_window_artifact.py",
            stage_script["PROCESS_SCALE_VALIDATED"] / "validate_process_window_artifact.py",
            scale_up_request,
            "process.json",
        )
        window_artifact = check_schema("process", window_path)
        # The stage constant is itself evidence: the builder derives it from the
        # UPSTREAM optimization artifact's stage, so getting PROCESS_SCALE_VALIDATED
        # (rather than the oil window stage) proves the grease dispatch saw this
        # route's NON_INFERIORITY_PASSED artifact.
        assert window_artifact["stage"] == "PROCESS_SCALE_VALIDATED", window_artifact["stage"]
        assert window_artifact["process_window"]["validated"] is True, window_artifact["process_window"]
        assert window_artifact["process_window"]["evidence_reference"] == "PROCESS-WINDOW:PW-PGD-E2E-001-PROD", window_artifact
        driven_stages.append("PROCESS_SCALE_VALIDATED")

        # --- 18. VERIFIED (gate-review) ----------------------------------------
        route_allow("PROCESS_SCALE_VALIDATED", "VERIFIED")
        # The gate consumes the route's own optimization artifact at its own stage:
        # the preflight dispatches the expected stage on the charter's project_type
        # (the WP-14 fix this chain used to record as open), and the drive must land
        # the gate artifact -- there is no "if it happened to exist" branch here.
        gate_request_path = write_input(
            "input-gate.json",
            gate_request(project_path, challenge_path, failure_path, method_path, design_space_path,
                         experiment_design_path, experiment_path, model_path, optimization_path),
        )
        gate_path = drive(
            stage_script["VERIFIED"] / "preflight_gate_review.py",
            stage_script["VERIFIED"] / "build_gate_artifact.py",
            stage_script["VERIFIED"] / "validate_gate_artifact.py",
            gate_request_path,
            "gate.json",
        )
        gate_artifact = check_schema("gate", gate_path)
        assert gate_artifact["stage"] == "VERIFIED", gate_artifact["stage"]
        assert gate_artifact["gate_status"] == "GO", gate_artifact["gate_status"]
        assert gate_artifact["experiment_reference"] == experiment_artifact["experiment_id"], gate_artifact
        driven_stages.append("VERIFIED")

        # The stage dispatch is route-local, and this is where that is locked: the
        # SAME request with an oil charter (NEW_PRODUCT) makes the gate expect the
        # oil constant again and the route's NON_INFERIORITY_PASSED artifact is
        # refused. The grease allowance cannot leak into the six oil routes.
        #
        # The oil charter copy lives in its own directory on purpose: the chain audit
        # dispatches the grease stage expectation from the first project-typed record
        # it reads in the workspace ROOT, so a second charter there would shadow the
        # real one (it would flip the audit itself onto the oil constants).
        oil_check_dir = ws / "oil-charter-check"
        oil_check_dir.mkdir()
        oil_charter = read_json(project_path)
        oil_charter["project_type"] = "NEW_PRODUCT"
        oil_charter_path = oil_check_dir / "project.json"
        write_json(oil_charter_path, oil_charter)
        oil_gate_payload = gate_request(project_path, challenge_path, failure_path, method_path, design_space_path,
                                        experiment_design_path, experiment_path, model_path, optimization_path)
        oil_gate_payload["project_artifact"] = str(oil_charter_path)
        # Every other reference is made absolute so the request resolves from the
        # directory the copy lives in.
        for key in sorted(key for key in oil_gate_payload if key.endswith("_artifact")):
            oil_gate_payload[key] = str(ws / oil_gate_payload[key])
        oil_gate_request = oil_check_dir / "input-gate-oil-charter.json"
        write_json(oil_gate_request, oil_gate_payload)
        oil_gate_probe = run(stage_script["VERIFIED"] / "preflight_gate_review.py", oil_gate_request)
        assert oil_gate_probe.returncode != 0 and GATE_OIL_STAGE_GAP in oil_gate_probe.stdout, oil_gate_probe.stdout
        print("gate ok: the same optimization artifact is refused under an oil charter (the stage expectation "
              "stays OPTIMIZED for the six oil routes)")

        # --- 19. APPLIED (application-definition + application-validation) ------
        route_allow("VERIFIED", "APPLIED")
        application_request = write_input("input-application.json", application_input(None))
        application_path = drive(
            SKILLS / "application-definition" / "scripts" / "preflight_application_definition.py",
            SKILLS / "application-definition" / "scripts" / "build_application_artifact.py",
            SKILLS / "application-definition" / "scripts" / "validate_application_artifact.py",
            application_request,
            "application.json",
        )
        application_artifact = check_schema("application", application_path)
        assert application_artifact["stage"] == "APPLIED", application_artifact["stage"]
        assert application_artifact["decision"] == "GO", application_artifact["decision"]
        gate_entry_request = write_input(
            "input-application-validation.json",
            application_validation_input(application_path, campaign_path, bench_test_paths[0]),
        )
        ready = run_ok(
            stage_script["APPLIED"] / "preflight_application_validation.py", gate_entry_request
        )
        assert ready.stdout.startswith("READY:") and "APPLIED" in ready.stdout, ready.stdout
        driven_stages.append("APPLIED")

        # --- 20. KNOWLEDGE_ARCHIVED (knowledge-archive) -------------------------
        route_allow("APPLIED", "KNOWLEDGE_ARCHIVED")
        knowledge_request = write_input("input-knowledge.json", knowledge_input(project_path))
        knowledge_path = drive(
            stage_script["KNOWLEDGE_ARCHIVED"] / "preflight_knowledge_archive.py",
            stage_script["KNOWLEDGE_ARCHIVED"] / "build_knowledge_asset_artifact.py",
            stage_script["KNOWLEDGE_ARCHIVED"] / "validate_knowledge_asset_artifact.py",
            knowledge_request,
            "knowledge_asset.json",
        )
        knowledge_artifact = check_schema("knowledge_asset", knowledge_path)
        assert knowledge_artifact["stage"] == "KNOWLEDGE_ARCHIVED", knowledge_artifact["stage"]
        assets = knowledge_artifact["knowledge_assets"]
        expected_assets = {
            "recommended_formula",
            "feasible_design_space",
            "critical_failure_boundaries",
            "evidence_package",
            "material_knowledge",
            "model",
        }
        assert set(assets) == expected_assets, sorted(assets)
        assert all(entry.get("present") is True for entry in assets.values()), assets
        assert knowledge_artifact["asset_status"] == "CLOSED_KNOWLEDGE", knowledge_artifact["asset_status"]
        # The six present flags are a claim, not a read-back: every asset reference
        # must RESOLVE to a record this workspace actually produced, and that record
        # must carry the artifact type / stage the asset name implies. A reference
        # that dangles -- or one pointing at the wrong kind of record -- fails here.
        asset_resolution = {
            "recommended_formula": ("optimization.json", "optimization", "NON_INFERIORITY_PASSED"),
            "feasible_design_space": ("design_space.json", "design_space", "DESIGN_SPACE_DEFINED"),
            "critical_failure_boundaries": ("failure_ctq.json", "failure_ctq", "FAILURE_CTQ_DEFINED"),
            "evidence_package": ("application.json", "application", "APPLIED"),
            "material_knowledge": ("material-base-oil.json", "material", "DESIGN_SPACE_DEFINED"),
            "model": ("model.json", "model", "MODEL_BUILT"),
        }
        for key, (reference, artifact_type, stage) in asset_resolution.items():
            entry = assets[key]
            assert entry["artifact_reference"] == reference, (key, entry)
            referenced = ws / reference
            assert referenced.is_file(), f"{key} points at {reference}, which does not exist in the workspace"
            target = check_schema(artifact_type, referenced)
            assert target["stage"] == stage, (key, reference, target["stage"], stage)
        qualification_path = ws / assets["evidence_package"]["qualification_reference"]
        assert qualification_path.is_file(), assets["evidence_package"]
        assert read_json(qualification_path)["stage"] == "VERIFIED", assets["evidence_package"]
        driven_stages.append("KNOWLEDGE_ARCHIVED")

        # --- E2E-10 retrieval closure ------------------------------------------
        # A closed knowledge asset that no later project can find would close the
        # chain on paper only. The route's own failure-mechanism query is run
        # through the pack's retrieval consumer (the failure-ctq preflight drives
        # scripts/knowledge_retrieval.py over history_roots), and then through the
        # module directly, so both the consumer's printed summary and the module's
        # own return value are asserted -- not the test's assumption about them.
        retrieval_request = write_input(
            "input-failure-retrieval.json",
            {**failure_input(project_path, challenge_path), "history_roots": [str(ws)]},
        )
        retrieval = run_ok(
            stage_script["FAILURE_MECHANISM_DEFINED"] / "preflight_failure_ctq.py", retrieval_request
        )
        summary = next((line for line in retrieval.stdout.splitlines() if line.startswith(RETRIEVAL_LINE)), None)
        assert summary is not None, "the retrieval consumer printed no history summary: " + retrieval.stdout
        assert RETRIEVAL_BACKEND in summary, summary
        assert int(summary.split()[0].split("=")[1]) > 0, summary
        assert any("artifact_type=knowledge_asset" in line and f"project_id={PROJECT_ID}" in line
                   for line in retrieval.stdout.splitlines()), retrieval.stdout
        print("E2E-10 ok: retrieval consumer reports " + summary)

        retrieval_module = load_module(ROOT / "scripts" / "knowledge_retrieval.py", "e2e_knowledge_retrieval")
        assert retrieval_module.describe_backend() == "local_bm25", retrieval_module.describe_backend()
        hits = retrieval_module.search_history(
            "Flexspline tooth-flank fretting wear with micro-pitting: asperity contact accumulates "
            "fretting damage and grease hardening",
            ws,
        )
        assert hits, "the archived knowledge_asset is not retrievable from the workspace that produced it"
        assert all(hit["artifact_type"] == "knowledge_asset" for hit in hits), hits
        assert any(Path(hit["source"]).resolve() == knowledge_path.resolve() for hit in hits), hits
        print(f"E2E-10 ok: knowledge_retrieval.py backend={retrieval_module.describe_backend()} "
              f"returns the archived asset as hit[0] (score={hits[0]['score']})")

        # --- chain audit over the workspace as built ---------------------------
        audit = run(AUDIT_SCRIPT, ws)
        assert "chain audit over" in audit.stdout, audit.stdout + audit.stderr
        audit_problems = audit_problem_lines(audit.stdout)
        assert audit_problems == [], audit.stdout
        ok_lines = [line for line in audit.stdout.splitlines() if line.strip().startswith("ok")]
        assert ok_lines, audit.stdout
        print("audit_chain: no violation over the built workspace (" + str(len(ok_lines)) + " internal checks passed)")

        # The scratch copies this test needed along the way (the oil-charter copy,
        # the SYNTHETIC-bench copy, the refused requests) all carry the ``input-``
        # prefix, so the audit above reads them as scratch input rather than as
        # chain records -- and the audit runs over the workspace AS BUILT, with
        # every one of the 20 stage artifacts in it.

    # Coverage is an assertion, never just a print: all 20 stages must have been
    # driven by the skill the router names, in route order, and ``stage_gaps`` (the
    # escape hatch for a stage that had to be skipped) must be empty. A stage that
    # silently drops out of the chain -- for any reason -- fails here.
    assert stage_gaps == {}, f"stages were skipped instead of driven: {stage_gaps}"
    assert driven_stages == list(EXPECTED_ROUTE), (
        "the driven stages do not match the route exactly: "
        f"driven={driven_stages} missing={sorted(set(EXPECTED_ROUTE) - set(driven_stages))}"
    )
    assert len(driven_stages) == len(EXPECTED_ROUTE) == 20, driven_stages
    for stage in driven_stages:
        print(f"DRIVEN: {stage} <- {STAGE_SKILL[stage]}")
    print(
        f"PASS: PRECISION_GREASE_DEV route verified stage by stage; {len(driven_stages)} of {len(EXPECTED_ROUTE)} "
        "stages driven end to end (preflight -> build -> validate -> schema) and asserted as the coverage floor; "
        "chain audit clean over the built workspace; knowledge asset CLOSED_KNOWLEDGE with all six asset "
        "references resolving to real records; E2E-10 retrieval closure verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
