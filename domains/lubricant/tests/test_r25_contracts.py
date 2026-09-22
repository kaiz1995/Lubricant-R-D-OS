"""Runnable contract checks for R2.5: Stage 7 design freeze / Stage 8 knowledge assets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
FIXTURES = ROOT / "fixtures"

FREEZE_CONDITIONS = {
    "CRITICAL_CTQ_SATISFIED",
    "CRITICAL_RISK_EVIDENCE_SUFFICIENT",
    "COST_TARGET_MET",
    "RAW_MATERIAL_SUPPLY_ACCEPTABLE",
    "MANUFACTURABILITY_ACCEPTABLE",
    "CRITICAL_BENCHMARK_NO_DEGRADATION",
    "COMPATIBILITY_PASSED",
    "RISK_REVIEW_PASSED",
}

KNOWLEDGE_ASSETS = {
    "recommended_formula",
    "feasible_design_space",
    "critical_failure_boundaries",
    "evidence_package",
    "material_knowledge",
    "model",
}


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
        "stage": "VERIFIED",
        "evidence_scope": "PHYSICAL",
        "decision_question": "Sample closure question?",
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


def freeze_conditions() -> list[dict]:
    return [
        {"condition_id": condition, "satisfied": True, "evidence_reference": f"VR-{condition}-001"}
        for condition in sorted(FREEZE_CONDITIONS)
    ]


def freeze_record(**overrides: object) -> dict:
    base = {
        "reason": "All stage-7 conditions are satisfied.",
        "evidence_package": "EQ-001",
        "evidence_scope": "PHYSICAL",
        "evidence_status": "OBSERVED",
        "freeze_conditions": freeze_conditions(),
    }
    base.update(overrides)
    return base


def design_freeze(**overrides: object) -> dict:
    base = artifact(
        artifact_type="design_freeze",
        stage="FROZEN",
        decision="FREEZE",
        freeze_record=freeze_record(),
    )
    base.update(overrides)
    return base


def knowledge_assets(**overrides: object) -> dict:
    base = {
        "recommended_formula": {"artifact_reference": "FORMULA-REC-001", "present": True},
        "feasible_design_space": {"artifact_reference": "DS-FEASIBLE-001", "present": True},
        "critical_failure_boundaries": {"artifact_reference": "CFB-001", "present": True},
        "evidence_package": {
            "artifact_reference": "EP-001",
            "present": True,
            "qualification_reference": "EQ-001",
            "qualification": "QUALIFIED",
        },
        "material_knowledge": {"artifact_reference": "MAT-KNOW-001", "present": True},
        "model": {"artifact_reference": "MODEL-001", "present": True},
    }
    base.update(overrides)
    return base


def knowledge(**overrides: object) -> dict:
    base = artifact(
        artifact_type="knowledge_asset",
        stage="CLOSED",
        decision="FREEZE",
        asset_status="CLOSED_KNOWLEDGE",
        knowledge_assets=knowledge_assets(),
    )
    base.update(overrides)
    return base


def fixture(kind: str, name: str) -> dict:
    return json.loads((FIXTURES / "valid" / f"{kind}--{name}.json").read_text(encoding="utf-8")) if name else json.loads(
        (FIXTURES / "valid" / f"{kind}.json").read_text(encoding="utf-8")
    )


def main() -> int:
    registry = load_registry()
    freeze_validator = validator_for("design_freeze", registry)
    knowledge_validator = validator_for("knowledge_asset", registry)

    # Schema intent: the eight stage-7 freeze conditions are frozen by name.
    freeze_schema = json.loads((SCHEMAS / "design_freeze.schema.json").read_text(encoding="utf-8"))
    condition_ids = set(freeze_schema["properties"]["freeze_record"]["properties"]["freeze_conditions"]["items"]["properties"]["condition_id"]["enum"])
    assert condition_ids == FREEZE_CONDITIONS, condition_ids

    knowledge_schema = json.loads((SCHEMAS / "knowledge_asset.schema.json").read_text(encoding="utf-8"))
    assert set(knowledge_schema["properties"]["knowledge_assets"]["properties"]) == KNOWLEDGE_ASSETS

    # Valid fixtures: full freeze, closed knowledge package, draft knowledge package.
    valid_freezes = [design_freeze(), fixture("design_freeze", "")]
    for instance in valid_freezes:
        assert errors(freeze_validator, instance) == [], errors(freeze_validator, instance)

    valid_knowledge = [knowledge(), fixture("knowledge_asset", "")]
    for instance in valid_knowledge:
        assert instance["asset_status"] == "CLOSED_KNOWLEDGE"
        assert errors(knowledge_validator, instance) == [], errors(knowledge_validator, instance)

    draft = fixture("knowledge_asset", "draft-incomplete")
    assert draft["asset_status"] == "DRAFT_KNOWLEDGE"
    assert errors(knowledge_validator, draft) == [], errors(knowledge_validator, draft)

    # Invalid fixtures: each must be rejected with the expected message fragment.
    invalid_cases = [
        ("design_freeze", "unsatisfied-condition", "True was expected"),
        ("design_freeze", "synthetic", "'PHYSICAL' was expected"),
        ("knowledge_asset", "missing-model", "True was expected"),
        ("knowledge_asset", "synthetic-closed", "'DRAFT_KNOWLEDGE' was expected"),
    ]
    for kind, name, expected in invalid_cases:
        instance = json.loads((FIXTURES / "invalid" / f"{kind}--{name}.json").read_text(encoding="utf-8"))
        validator = freeze_validator if kind == "design_freeze" else knowledge_validator
        found = errors(validator, instance)
        assert found, f"{kind}--{name} was unexpectedly accepted"
        assert any(expected in message for message in found), f"{kind}--{name}: expected {expected!r}, got {found!r}"

    # A freeze with ANY unsatisfied condition is rejected end-to-end.
    failed_freezes = []
    for condition in FREEZE_CONDITIONS:
        record = freeze_record()
        for item in record["freeze_conditions"]:
            if item["condition_id"] == condition:
                item["satisfied"] = False
        failed = design_freeze(freeze_record=record)
        assert errors(freeze_validator, failed), f"freeze must reject unsatisfied {condition}"
        failed_freezes.append(condition)
    assert len(failed_freezes) == 8

    # SYNTHETIC evidence: freeze is impossible; knowledge caps at DRAFT with the demo marker.
    synthetic_freeze = design_freeze(evidence_scope="SYNTHETIC")
    assert errors(freeze_validator, synthetic_freeze), "SYNTHETIC freeze must be rejected"

    synthetic_draft = knowledge(
        evidence_scope="SYNTHETIC",
        stage="VERIFIED",
        decision="HOLD",
        asset_status="DRAFT_KNOWLEDGE",
        synthetic_marker="SYNTHETIC_DEMO_ONLY",
        knowledge_assets=knowledge_assets(),
    )
    assert errors(knowledge_validator, synthetic_draft) == [], errors(knowledge_validator, synthetic_draft)

    # CLOSED_KNOWLEDGE without a QUALIFIED evidence package is rejected.
    unqualified = knowledge()
    unqualified["knowledge_assets"]["evidence_package"]["qualification"] = "PROVISIONAL"
    assert errors(knowledge_validator, unqualified), "CLOSED_KNOWLEDGE without QUALIFIED must be rejected"

    print("PASS: design_freeze / knowledge_asset contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
