
from __future__ import annotations
import hashlib
import json
import math
import sys
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ENGINE_NAME = "cost"
ENGINE_VERSION = "0.1.0"
METHOD = "COST_SUM_V1"
SUM_TOL = 1e-09

def _load_schemas():
    schema_dir = Path(__file__).resolve().parents[2] / "schemas"
    schemas = {}
    for p in schema_dir.glob("*.json"):
        schemas[p.name] = json.loads(p.read_text(encoding="utf-8"))
    registry = Registry()
    for s in schemas.values():
        if "$id" in s:
            registry = registry.with_resource(s["$id"], Resource.from_contents(s))
    return schemas, registry

def _validate_input_schema(data):
    schemas, registry = _load_schemas()
    schema = schemas.get("cost_input.schema.json")
    if schema is None:
        return ["cost_input.schema.json not found"]
    v = Draft202012Validator(schema, registry=registry)
    errs = sorted(v.iter_errors(data), key=lambda e: list(e.path))
    return [e.message for e in errs]

def _digest_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def calculate_cost(input_dict, input_bytes=None):
    # schema validation
    schema_errors = _validate_input_schema(input_dict)
    if schema_errors:
        reason = f"input schema validation failed: {schema_errors[0]}"
        return _build_rejected(input_dict, input_bytes, [reason])
    # business checks
    reasons = []
    formula = input_dict.get("formula", {})
    components = formula.get("components", [])
    materials = input_dict.get("materials", [])
    # duplicate material_id in materials
    mat_ids = [m.get("material_id") for m in materials]
    if len(mat_ids) != len(set(mat_ids)):
        reasons.append("duplicate material_id in materials")
    # duplicate in components
    comp_ids = [c.get("material_id") for c in components]
    if len(comp_ids) != len(set(comp_ids)):
        reasons.append("duplicate material_id in formula.components")
    # price map
    price_map = {m["material_id"]: m["price"] for m in materials if "material_id" in m and "price" in m}
    missing = [cid for cid in comp_ids if cid not in price_map]
    if missing:
        reasons.append(f"material_id not found in materials: {missing[0]}")
    # fraction sum
    fracs = [c.get("fraction", 0) for c in components]
    total_frac = math.fsum(fracs)
    if abs(total_frac - 1.0) > 1e-9:
        reasons.append(f"sum of fractions {total_frac} deviates from 1.0 beyond 1e-9")
    if reasons:
        return _build_rejected(input_dict, input_bytes, reasons)
    # compute
    contributions = []
    for c in components:
        cid = c["material_id"]
        x = c["fraction"]
        p = price_map[cid]
        contributions.append((cid, x * p))
    total = math.fsum(v for _, v in contributions)
    # components sorted by percentage desc then id asc (and same for sensitivity)
    comps = []
    sens_rank = []
    for cid, contrib in contributions:
        pct = (contrib / total * 100.0) if total != 0 else 0.0
        comps.append((cid, contrib, pct))
        sens_rank.append((cid, contrib, pct))
    comps.sort(key=lambda x: (-x[2], x[0]))
    sens_rank.sort(key=lambda x: (-x[2], x[0]))
    highest = comps[0][0] if comps else ""
    price_ts = input_dict.get("price_timestamp", "")
    digest = _digest_bytes(input_bytes) if input_bytes is not None else _digest_bytes(json.dumps(input_dict, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    result = {
        "total_cost": total,
        "currency": "CNY",
        "components": [{"component_id": cid, "cost_contribution": contrib, "cost_percentage": pct} for cid, contrib, pct in comps],
        "highest_cost_component": highest,
        "sensitivity": {
            "ranking": [{"component_id": cid, "contribution": contrib, "percentage": pct} for cid, contrib, pct in sens_rank],
            "method_note": "CONTRIBUTION_RATIO_V1"
        }
    }
    evidence = [{
        "evidence_id": "cost-price-source",
        "statement": f"cost calculated from materials price table at price_timestamp {price_ts}; price table is the single source of price truth",
        "source": "materials table in cost_input",
        "status": "OBSERVED"
    }]
    envelope = {
        "schema_version": "0.1.0",
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "method": METHOD,
        "parameters": {"sum_tolerance": 1e-09},
        "input_digest": digest,
        "status": "OK",
        "rejection_reasons": [],
        "result": result,
        "evidence": evidence
    }
    return envelope

def _build_rejected(input_dict, input_bytes, reasons):
    digest = _digest_bytes(input_bytes) if input_bytes is not None else _digest_bytes(json.dumps(input_dict, ensure_ascii=False, sort_keys=True).encode("utf-8") if isinstance(input_dict, dict) else b"")
    return {
        "schema_version": "0.1.0",
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "method": METHOD,
        "parameters": {"sum_tolerance": 1e-09},
        "input_digest": digest,
        "status": "REJECTED",
        "rejection_reasons": reasons,
        "result": {},
        "evidence": []
    }

def _write_output(path, envelope):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def main():
    if len(sys.argv) != 3:
        print(f"Usage: python -m domains.lubricant.compute.cost.engine <input.json> <output.json>", file=sys.stderr)
        return 2
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2])
    try:
        raw = inp.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        env = _build_rejected({}, raw if "raw" in locals() else b"", [f"input read/parse failed: {e}"])
        _write_output(out, env)
        return 0
    # schema validation: CLI must also envelope REJECTED to file
    schema_errors = _validate_input_schema(data)
    if schema_errors:
        env = _build_rejected(data, raw, [f"input schema validation failed: {schema_errors[0]}"])
        _write_output(out, env)
        return 0
    env = calculate_cost(data, raw)
    _write_output(out, env)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
