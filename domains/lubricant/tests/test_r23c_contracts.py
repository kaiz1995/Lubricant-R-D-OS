"""Runnable contract checks for R2.3c: benchmark / evidence qualification / NI limits."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


def load_registry() -> Registry:
    registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


def validator_for(kind: str, registry: Registry) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / f"{kind}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=registry)


def errors(validator: Draft202012Validator, instance: dict) -> list[str]:
    return [error.message for error in validator.iter_errors(instance)]


def artifact(**overrides: object) -> dict:
    base = {
        "schema_version": "0.1.0",
        "project_id": "WGO-001",
        "stage": "TEST_METHODS_QUALIFIED",
        "evidence_scope": "PHYSICAL",
        "decision_question": "Sample decision question?",
        "hypothesis": "Sample hypothesis.",
        "uncertainty": "Sample uncertainty.",
        "evidence": [{"evidence_id": "E-1", "statement": "Sample statement.", "source": "sample", "status": "OBSERVED"}],
        "decision_rule": "Sample rule.",
        "result": "Sample result.",
        "decision": "HOLD",
        "next_action": "Sample action.",
    }
    base.update(overrides)
    return base


def benchmark(**overrides: object) -> dict:
    base = artifact(
        artifact_type="benchmark",
        product_id="BK-001",
        product_type="EXTERNAL_COMPETITOR",
        source="competitor datasheet",
        batch_reference="BATCH-BK-001",
        test_data_references=["TD-001"],
        applicable_scenarios=["hydraulic oil comparison"],
        usage_role="COMPARISON_VALIDATION",
        evidence_status="OBSERVED",
    )
    base.update(overrides)
    return base


def qualification(**overrides: object) -> dict:
    base = artifact(
        artifact_type="evidence_qualification",
        qualification_id="EQ-001",
        qualification="PROVISIONAL",
        evidence_chain=[
            {"artifact_reference": "SYNTH-RUN-001", "evidence_scope": "SYNTHETIC", "evidence_status": "ASSUMED"}
        ],
        rule_reference="RULE-EVIDENCE-QUALIFICATION-V1",
        decided_by="Demo",
        decided_on="2026-08-25",
        synthetic_marker="SYNTHETIC_DEMO_ONLY",
    )
    base.update(overrides)
    return base


def optimization(**overrides: object) -> dict:
    base = artifact(
        artifact_type="optimization",
        stage="OPTIMIZED",
        optimization_id="OPT-001",
        model_reference="MODEL-001",
        objective_type="CONSTRAINT_SATISFACTION",
        objectives=[
            {"response_reference": "CTQ-001", "direction": "MINIMIZE", "criterion": "Meet the CTQ boundary."}
        ],
        methods=["NON_INFERIORITY"],
        engine_handoff="PHASE4_DETERMINISTIC_ENGINE",
    )
    base.update(overrides)
    return base


def main() -> int:
    registry = load_registry()
    benchmark_validator = validator_for("benchmark", registry)
    qualification_validator = validator_for("evidence_qualification", registry)
    optimization_validator = validator_for("optimization", registry)

    # Benchmark: COMPARISON_VALIDATION is legal.
    assert errors(benchmark_validator, benchmark()) == [], errors(benchmark_validator, benchmark())

    # Benchmark: FORMULA_COPY_SOURCE is rejected.
    copy_source = benchmark(usage_role="FORMULA_COPY_SOURCE")
    assert errors(benchmark_validator, copy_source), "FORMULA_COPY_SOURCE must be rejected"

    # Evidence qualification: SYNTHETIC + QUALIFIED is rejected.
    synthetic_qualified = qualification(qualification="QUALIFIED")
    assert errors(qualification_validator, synthetic_qualified), "SYNTHETIC+QUALIFIED must be rejected"

    # Evidence qualification: SYNTHETIC + PROVISIONAL with demo marker is legal.
    provisional = qualification(evidence_scope="SYNTHETIC")
    assert errors(qualification_validator, provisional) == [], errors(qualification_validator, provisional)

    # Evidence qualification: PHYSICAL + QUALIFIED is legal.
    physical_qualified = qualification(
        qualification="QUALIFIED",
        evidence_chain=[
            {"artifact_reference": "TM-001", "evidence_scope": "PHYSICAL", "evidence_status": "OBSERVED"}
        ],
    )
    assert errors(qualification_validator, physical_qualified) == [], errors(qualification_validator, physical_qualified)

    # Evidence qualification: SYNTHETIC cannot drop the demo marker.
    missing_marker = qualification(evidence_scope="SYNTHETIC")
    del missing_marker["synthetic_marker"]
    assert errors(qualification_validator, missing_marker), "SYNTHETIC evidence must carry the demo marker"

    # Optimization NI limits: legal when the margin is positive.
    ni_legal = optimization(
        objectives=[
            {
                "response_reference": "CTQ-001",
                "direction": "MINIMIZE",
                "criterion": "Meet the CTQ boundary.",
                "ni_limits": {
                    "baseline": 50.0,
                    "minimum_acceptable": 45.0,
                    "non_inferiority_margin": 2.0,
                    "preferred_target": 40.0,
                },
            }
        ]
    )
    assert errors(optimization_validator, ni_legal) == [], errors(optimization_validator, ni_legal)

    # Optimization NI limits: margin <= 0 is rejected; non-numeric limits are rejected.
    ni_bad_margin = optimization(
        objectives=[
            {
                "response_reference": "CTQ-001",
                "direction": "MINIMIZE",
                "criterion": "Meet the CTQ boundary.",
                "ni_limits": {"baseline": 50.0, "minimum_acceptable": 45.0, "non_inferiority_margin": 0.0},
            }
        ]
    )
    assert errors(optimization_validator, ni_bad_margin), "margin=0 must be rejected"

    ni_non_numeric = optimization(
        objectives=[
            {
                "response_reference": "CTQ-001",
                "direction": "MINIMIZE",
                "criterion": "Meet the CTQ boundary.",
                "ni_limits": {"baseline": "high"},
            }
        ]
    )
    assert errors(optimization_validator, ni_non_numeric), "non-numeric NI limit must be rejected"

    print("PASS: benchmark / evidence_qualification / NI-limit contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
