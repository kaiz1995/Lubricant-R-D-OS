"""Direct-run compute schema tests (no pytest)."""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "domains" / "lubricant" / "schemas"

def load_schemas():
    schemas = {}
    for p in SCHEMA_DIR.glob("*.json"):
        schemas[p.name] = json.loads(p.read_text(encoding="utf-8"))
    registry = Registry()
    for s in schemas.values():
        if "$id" in s:
            registry = registry.with_resource(s["$id"], Resource.from_contents(s))
    return schemas, registry

def validate(schema_name, doc):
    schemas, registry = load_schemas()
    v = Draft202012Validator(schemas[schema_name], registry=registry)
    return list(v.iter_errors(doc))

def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    # 1. valid envelope
    valid = json.loads((ROOT / "fixtures/compute/envelope-valid.json").read_text(encoding="utf-8"))
    errs = validate("compute_envelope.schema.json", valid)
    assert not errs, f"valid envelope should pass { [e.message for e in errs]}"
    print("PASS: valid envelope")
    # 2. REJECTED without reasons -> FAIL
    invalid_rejected = json.loads((ROOT / "fixtures/compute/envelope-invalid-rejected-no-reasons.json").read_text(encoding="utf-8"))
    errs = validate("compute_envelope.schema.json", invalid_rejected)
    assert errs, "REJECTED without reasons must fail"
    print("PASS: REJECTED without reasons correctly fails")
    # 3. OK with reasons -> FAIL
    ok_with = dict(valid)
    ok_with["rejection_reasons"] = ["unexpected"]
    errs = validate("compute_envelope.schema.json", ok_with)
    assert errs, "OK with reasons must fail"
    print("PASS: OK with reasons correctly fails")
    # 4. bad digest
    bad = dict(valid)
    bad["input_digest"] = "not-a-sha256"
    errs = validate("compute_envelope.schema.json", bad)
    assert errs, "bad digest must fail"
    print("PASS: bad digest correctly fails")
    # 5. cost missing highest_cost_component
    cost_doc = {
        "schema_version": "0.1.0",
        "engine_name": "cost",
        "engine_version": "0.1.0",
        "method": "COST_SUM",
        "parameters": {},
        "input_digest": "c"*64,
        "status": "OK",
        "rejection_reasons": [],
        "result": {"total_cost": 123.4, "currency": "CNY", "components": [{"component_id": "PAO6", "cost_contribution": 80.0, "cost_percentage": 64.8}]},
        "evidence": []
    }
    errs = validate("cost_result_schema.json", cost_doc)
    assert errs, "cost missing highest_cost_component must fail"
    print("PASS: cost missing highest_cost_component correctly fails")
    # 6. Phase 3 frozen
    for name in ["model.schema.json", "optimization.schema.json"]:
        ws = ROOT / "schemas" / name
        ws_hash = sha256_file(ws)
        proc = subprocess.run(["git", "show", f"HEAD:schemas/{name}"], cwd=ROOT, capture_output=True)
        assert proc.returncode == 0, f"git show failed {proc.stderr.decode()}"
        head_hash = hashlib.sha256(proc.stdout).hexdigest()
        assert ws_hash == head_hash, f"{name} modified {ws_hash} != {head_hash}"
        print(f"PASS: {name} frozen ({ws_hash[:8]})")
    # positive cost (1.1.0: sensitivity required)
    good_cost = {
        "schema_version": "0.1.0",
        "engine_name": "cost",
        "engine_version": "0.1.0",
        "method": "COST_SUM",
        "parameters": {"price_date": "2026-01-01"},
        "input_digest": "d"*64,
        "status": "OK",
        "rejection_reasons": [],
        "result": {"total_cost": 100.0, "currency": "CNY", "components": [{"component_id": "PAO6", "cost_contribution": 60.0, "cost_percentage": 60.0}, {"component_id": "AN", "cost_contribution": 40.0, "cost_percentage": 40.0}], "highest_cost_component": "PAO6", "sensitivity": {"ranking": [{"component_id": "PAO6", "contribution": 60.0, "percentage": 60.0}, {"component_id": "AN", "contribution": 40.0, "percentage": 40.0}], "method_note": "CONTRIBUTION_RATIO_V1"}},
        "evidence": [{"evidence_id": "E1", "statement": "price from supplier", "source": "supplier sheet", "status": "OBSERVED"}]
    }
    errs = validate("cost_result_schema.json", good_cost)
    assert not errs, f"good cost should pass {[e.message for e in errs]}"
    print("PASS: valid cost result")
    print("ALL PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
