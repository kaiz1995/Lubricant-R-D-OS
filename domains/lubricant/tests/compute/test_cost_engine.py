
"""Direct-run cost engine tests (no pytest)."""
from __future__ import annotations
import hashlib
import json
import math
import subprocess
import sys
import tempfile
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

def make_input(components, materials, price_timestamp="2026-01-15", formula_id="F1", version="1.0"):
    return {
        "input_type": "COST_CALCULATION",
        "formula": {"formula_id": formula_id, "version": version, "components": components},
        "materials": materials,
        "price_timestamp": price_timestamp,
    }

def mat(mid, price, name="M", category="BASE_OIL", supplier=None):
    m = {"material_id": mid, "name": name, "category": category, "unit": "CNY_PER_KG", "price": price, "currency": "CNY", "effective_date": "2026-01-01"}
    if supplier:
        m["supplier"] = supplier
    return m

def main():
    sys.path.insert(0, str(ROOT))
    from domains.lubricant.compute.cost.engine import calculate_cost

    # 1 single component 100%
    inp = make_input([{"material_id": "PAO6", "fraction": 1.0}], [mat("PAO6", 50.0)])
    raw = json.dumps(inp, ensure_ascii=False, sort_keys=True).encode("utf-8")
    env = calculate_cost(inp, raw)
    assert env["status"] == "OK", env
    assert env["result"]["total_cost"] == 50.0
    assert env["result"]["components"][0]["cost_percentage"] == 100.0
    assert env["result"]["sensitivity"]["ranking"][0]["percentage"] == 100.0
    assert env["result"]["sensitivity"]["method_note"] == "CONTRIBUTION_RATIO_V1"
    print("PASS: single component 100%")

    # 2 three-component anchor hand calc: 0.5*10 + 0.3*20 + 0.2*30 = 5+6+6=17
    inp2 = make_input(
        [{"material_id": "A", "fraction": 0.5}, {"material_id": "B", "fraction": 0.3}, {"material_id": "C", "fraction": 0.2}],
        [mat("A", 10.0), mat("B", 20.0), mat("C", 30.0)]
    )
    raw2 = json.dumps(inp2, ensure_ascii=False, sort_keys=True).encode("utf-8")
    env2 = calculate_cost(inp2, raw2)
    assert env2["status"] == "OK"
    assert math.isclose(env2["result"]["total_cost"], 17.0, rel_tol=1e-12)
    # contributions: A 5, B 6, C 6 -> ranking B,C tied then A; C before B? lexicographic B<C so B first
    comps = {c["component_id"]: c for c in env2["result"]["components"]}
    assert math.isclose(comps["A"]["cost_contribution"], 5.0)
    assert math.isclose(comps["B"]["cost_contribution"], 6.0)
    assert math.isclose(comps["C"]["cost_contribution"], 6.0)
    # ranking tie: B and C same pct, lexicographic -> B before C
    ranking = env2["result"]["sensitivity"]["ranking"]
    assert ranking[0]["component_id"] == "B"
    assert ranking[1]["component_id"] == "C"
    assert ranking[2]["component_id"] == "A"
    print("PASS: three component anchor")

    # 3 sum !=1 rejected
    inp3 = make_input([{"material_id": "A", "fraction": 0.5}, {"material_id": "B", "fraction": 0.3}], [mat("A", 10), mat("B", 20)])
    env3 = calculate_cost(inp3, json.dumps(inp3, ensure_ascii=False, sort_keys=True).encode())
    assert env3["status"] == "REJECTED" and env3["rejection_reasons"] and env3["result"] == {}
    print("PASS: sum !=1 rejected")

    # 4 missing price (reference not in table) rejected
    inp4 = make_input([{"material_id": "A", "fraction": 0.5}, {"material_id": "MISSING", "fraction": 0.5}], [mat("A", 10)])
    env4 = calculate_cost(inp4, json.dumps(inp4, ensure_ascii=False, sort_keys=True).encode())
    assert env4["status"] == "REJECTED" and env4["result"] == {}
    print("PASS: missing price rejected")

    # 5 price=0 schema rejected -> via calculate_cost schema path REJECTED
    inp5 = make_input([{"material_id": "A", "fraction": 1.0}], [mat("A", 0)])
    env5 = calculate_cost(inp5, json.dumps(inp5, ensure_ascii=False, sort_keys=True).encode())
    assert env5["status"] == "REJECTED"
    print("PASS: zero price rejected")

    # 6 negative price schema rejected
    inp6 = make_input([{"material_id": "A", "fraction": 1.0}], [mat("A", -5)])
    env6 = calculate_cost(inp6, json.dumps(inp6, ensure_ascii=False, sort_keys=True).encode())
    assert env6["status"] == "REJECTED"
    print("PASS: negative price rejected")

    # 7 duplicate material_id rejected
    inp7 = make_input([{"material_id": "A", "fraction": 0.5}, {"material_id": "A", "fraction": 0.5}], [mat("A", 10)])
    env7 = calculate_cost(inp7, json.dumps(inp7, ensure_ascii=False, sort_keys=True).encode())
    assert env7["status"] == "REJECTED"
    # also duplicate in materials table
    inp7b = make_input([{"material_id": "A", "fraction": 0.5}, {"material_id": "B", "fraction": 0.5}], [mat("A", 10), mat("A", 20), mat("B", 30)])
    env7b = calculate_cost(inp7b, json.dumps(inp7b, ensure_ascii=False, sort_keys=True).encode())
    assert env7b["status"] == "REJECTED"
    print("PASS: duplicate id rejected")

    # 8 extreme: fraction 1e-12 + price 1e6, no overflow, fsum consistent
    inp8 = make_input(
        [{"material_id": "A", "fraction": 1 - 1e-12}, {"material_id": "B", "fraction": 1e-12}],
        [mat("A", 1e6), mat("B", 1e6)]
    )
    raw8 = json.dumps(inp8, ensure_ascii=False, sort_keys=True).encode()
    env8 = calculate_cost(inp8, raw8)
    assert env8["status"] == "OK"
    assert math.isfinite(env8["result"]["total_cost"])
    assert math.isclose(env8["result"]["total_cost"], math.fsum([(1-1e-12)*1e6, 1e-12*1e6]), rel_tol=1e-12)
    print("PASS: extreme input no overflow fsum")

    # 9 sensitivity stable tie sort (already partly in 2, explicit equality case)
    inp9 = make_input(
        [{"material_id": "X", "fraction": 0.5}, {"material_id": "Y", "fraction": 0.5}],
        [mat("X", 10), mat("Y", 10)]
    )
    env9 = calculate_cost(inp9, json.dumps(inp9, ensure_ascii=False, sort_keys=True).encode())
    assert env9["status"] == "OK"
    assert env9["result"]["sensitivity"]["ranking"][0]["component_id"] == "X"
    assert env9["result"]["sensitivity"]["ranking"][1]["component_id"] == "Y"
    assert env9["result"]["components"][0]["component_id"] == "X"
    print("PASS: tie stable sort")

    # 10 deterministic double run byte equal
    inp10 = make_input([{"material_id": "A", "fraction": 0.4}, {"material_id": "B", "fraction": 0.6}], [mat("A", 12.3), mat("B", 45.6)])
    raw10 = (ROOT / "fixtures" / "compute" / "cost-gold-input.json").read_bytes() if False else json.dumps(inp10, ensure_ascii=False, sort_keys=True).encode()
    # use a fixed raw for digest determinism
    raw10a = json.dumps(inp10, ensure_ascii=False, sort_keys=True).encode()
    env10a = calculate_cost(inp10, raw10a)
    env10b = calculate_cost(inp10, raw10a)
    b10a = json.dumps(env10a, ensure_ascii=False, indent=2) + "\n"
    b10b = json.dumps(env10b, ensure_ascii=False, indent=2) + "\n"
    assert b10a == b10b
    print("PASS: deterministic double run")

    # 11 gold fixture reproduce byte equal
    gold_in = ROOT / "fixtures" / "compute" / "cost-gold-input.json"
    gold_out = ROOT / "fixtures" / "compute" / "cost-gold-output.json"
    raw_gold = gold_in.read_bytes()
    data_gold = json.loads(raw_gold.decode("utf-8"))
    env_gold = calculate_cost(data_gold, raw_gold)
    written = json.dumps(env_gold, ensure_ascii=False, indent=2) + "\n"
    expected = gold_out.read_text(encoding="utf-8")
    assert written == expected, f"gold mismatch: {written[:500]} vs {expected[:500]}"
    # also validate gold output against schema
    errs = validate("cost_result_schema.json", env_gold)
    assert not errs, [e.message for e in errs]
    # envelope invariants: method, engine_version, sum_tolerance, evidence OBSERVED mentions price_timestamp and materials
    assert env_gold["method"] == "COST_SUM_V1"
    assert env_gold["engine_version"] == "0.1.0"
    assert env_gold["parameters"]["sum_tolerance"] == 1e-09
    assert json.dumps(env_gold, ensure_ascii=False).count("sum_tolerance") >= 1
    ev = env_gold["evidence"]
    assert len(ev) >= 1 and any(e["status"] == "OBSERVED" for e in ev)
    assert any("price_timestamp" in e["statement"] and "materials" in e["statement"] for e in ev)
    assert env_gold["input_digest"] == hashlib.sha256(raw_gold).hexdigest()
    print("PASS: gold fixture reproduce")

    # bonus: CLI schema fail also envelopes REJECTED to file
    with tempfile.TemporaryDirectory() as td:
        bad_in = Path(td) / "bad.json"
        bad_out = Path(td) / "out.json"
        bad = {"input_type": "COST_CALCULATION", "formula": {"formula_id": "F", "version": "1", "components": []}, "materials": [], "price_timestamp": "2026-01-01"}
        bad_in.write_text(json.dumps(bad), encoding="utf-8")
        proc = subprocess.run([sys.executable, "-m", "domains.lubricant.compute.cost.engine", str(bad_in), str(bad_out)], cwd=str(ROOT), capture_output=True, text=True)
        assert proc.returncode == 0
        out_env = json.loads(bad_out.read_text(encoding="utf-8"))
        assert out_env["status"] == "REJECTED" and out_env["rejection_reasons"]
        assert out_env["result"] == {}
        # OK CLI roundtrip
        gi = ROOT / "fixtures" / "compute" / "cost-gold-input.json"
        go = Path(td) / "gold_out.json"
        proc2 = subprocess.run([sys.executable, "-m", "domains.lubricant.compute.cost.engine", str(gi), str(go)], cwd=str(ROOT), capture_output=True, text=True)
        assert proc2.returncode == 0
        assert go.read_text(encoding="utf-8") == (ROOT / "fixtures" / "compute" / "cost-gold-output.json").read_text(encoding="utf-8")
    print("PASS: CLI envelope")

    print("ALL PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
