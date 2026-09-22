"""Direct-run DOE engine tests (no pytest) - Phase 4.2 constrained mixture DOE."""
from __future__ import annotations
import hashlib
import json
import math
import tempfile
from pathlib import Path
import sys
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

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def make_card():
    return {
        "decision_question": "What proportion maximizes KV40?",
        "hypothesis": "Quadratic effect exists.",
        "variables_note": "Mixture vars.",
        "constraints_note": "Bounds.",
        "responses_note": "KV40/TAN.",
        "doe_selection_reason": "Scheffe.",
        "expected_information_value": "det precision.",
        "decision_rule": "Pick best."
    }

def make_input(components, design_type, model_order, target_runs, mixture_total=1.0, responses=None):
    if responses is None:
        responses=[{"ctq_reference":"KV40","test_method_reference":"ASTM D445","role":"OPTIMIZATION_RESPONSE"}]
    return {
        "input_type": "MIXTURE_DOE_DESIGN",
        "components": components,
        "mixture_total": mixture_total,
        "design_type": design_type,
        "model_order": model_order,
        "target_runs": target_runs,
        "responses": responses,
        "experiment_card": make_card()
    }

def comps_uniform(q, low, high):
    return [{"component_id": f"C{i}", "lower_bound": low, "upper_bound": high} for i in range(q)]

def comps_named(bounds_dict):
    # bounds_dict {id: (low, high)} sorted by id
    return [{"component_id": k, "lower_bound": v[0], "upper_bound": v[1]} for k,v in sorted(bounds_dict.items())]

def main():
    sys.path.insert(0, str(ROOT))
    from domains.lubricant.compute.doe.engine import generate_doe
    # 1. q=3 unconstrained LINEAR simplex -> 3 vertices literature anchor
    inp1 = make_input(comps_uniform(3, 0, 1), "SIMPLEX_MIXTURE", "LINEAR", 0)
    raw1 = json.dumps(inp1, ensure_ascii=False, sort_keys=True).encode()
    env1 = generate_doe(inp1, raw1)
    assert env1["status"] == "OK", env1
    assert env1["method"] == "SIMPLEX_LATTICE_V1"
    assert env1["result"]["run_count"] == 3, env1["result"]
    # vertices order lex sorted by sorted_ids (C0,C1,C2) -> (0,0,1),(0,1,0),(1,0,0) ??? need check engine sorts lex
    props1 = [r["proportions"] for r in env1["result"]["runs"]]
    # verify each run has exactly one 1.0
    for pr in props1:
        vals = sorted(pr.values(), reverse=True)
        assert vals[0]==1.0 and vals[1]==0.0 and vals[2]==0.0, pr
    # deterministic order: sorted lex tuple
    tuples1 = [tuple(pr[c] for c in sorted(pr.keys())) for pr in props1]
    assert tuples1 == sorted(tuples1), "lex order"
    print("PASS: q=3 LINEAR simplex 3 vertices")

    # 2. q=3 unconstrained QUADRATIC simplex -> 6 points (3 vertices + 3 edge mids)
    inp2 = make_input(comps_uniform(3, 0, 1), "SIMPLEX_MIXTURE", "QUADRATIC", 0)
    env2 = generate_doe(inp2, json.dumps(inp2, ensure_ascii=False, sort_keys=True).encode())
    assert env2["status"]=="OK"
    assert env2["result"]["run_count"]==6
    tuples2 = sorted([tuple(r["proportions"][c] for c in sorted(r["proportions"])) for r in env2["result"]["runs"]])
    # expect classic Scheffe: vertices + (0,0.5,0.5) perms
    expected = {(1,0,0),(0,1,0),(0,0,1),(0.5,0.5,0),(0.5,0,0.5),(0,0.5,0.5)}
    got = set(tuple(round(v,10) for v in t) for t in tuples2)
    assert got==expected, f"got {got}"
    print("PASS: q=3 QUADRATIC 6 points")

    # 3. centroid negative -> m<=2 must NOT contain (1/3,1/3,1/3) for SIMPLEX
    for mo in ["LINEAR","QUADRATIC"]:
        inp = make_input(comps_uniform(3, 0, 1), "SIMPLEX_MIXTURE", mo, 0)
        env = generate_doe(inp, json.dumps(inp, ensure_ascii=False, sort_keys=True).encode())
        assert env["status"]=="OK"
        for r in env["result"]["runs"]:
            pr=r["proportions"]
            is_centroid = all(abs(pr[c]-1/3)<1e-9 for c in pr)
            assert not is_centroid, f"centroid should not appear for m<=2 {mo} {pr}"
    print("PASS: centroid negative")

    # 4. bounded filtering: use [0,0.8]^3 so vertices filtered but edge mids remain (engine candidate test analogue)
    # For simplex with bounds [0,0.8], vertices (1,0,0) infeasible since 1>0.8 => filtered. Edge mids (0.5,0.5,0) feasible (0.5 within). So filtered count must be 3 edge mids, not 6.
    inp4 = make_input(comps_uniform(3, 0, 0.8), "SIMPLEX_MIXTURE", "QUADRATIC", 0)
    env4 = generate_doe(inp4, json.dumps(inp4, ensure_ascii=False, sort_keys=True).encode())
    assert env4["status"]=="OK", env4
    assert env4["result"]["run_count"]==3, f"expected 3 edge mids after vertex filter {env4['result']}"
    for r in env4["result"]["runs"]:
        pr=r["proportions"]
        for v in pr.values():
            assert v <= 0.8+1e-12
        # all runs should be edge mids (0.5,0.5,0)
        vals=sorted(pr.values(), reverse=True)
        assert vals==[0.5,0.5,0.0], pr
    print("PASS: bounded filtering vertex removed edge retained")

    # 5a. infeasible sum lowers > total
    inp5a = make_input([{"component_id":"A","lower_bound":0.6,"upper_bound":0.8},{"component_id":"B","lower_bound":0.6,"upper_bound":0.8},{"component_id":"C","lower_bound":0.6,"upper_bound":0.8}], "SIMPLEX_MIXTURE","LINEAR",0, mixture_total=1.0)
    env5a = generate_doe(inp5a, json.dumps(inp5a, ensure_ascii=False, sort_keys=True).encode())
    assert env5a["status"]=="REJECTED" and env5a["result"]=={}, env5a
    assert any("exceeds" in r or "infeasible" in r for r in env5a["rejection_reasons"])
    print("PASS: infeasible sum lowers > total")
    # 5b. infeasible sum uppers < total
    inp5b = make_input([{"component_id":"A","lower_bound":0,"upper_bound":0.2},{"component_id":"B","lower_bound":0,"upper_bound":0.2},{"component_id":"C","lower_bound":0,"upper_bound":0.2}], "SIMPLEX_MIXTURE","LINEAR",0, mixture_total=1.0)
    env5b = generate_doe(inp5b, json.dumps(inp5b, ensure_ascii=False, sort_keys=True).encode())
    assert env5b["status"]=="REJECTED" and env5b["result"]=={}
    print("PASS: infeasible sum uppers < total")
    # 5c. infeasible after lattice filtering (all points filtered) - must pass business validation but fail lattice
    # LINEAR q=3 [0,0.8] -> vertices (1,0,0) filtered (1>0.8) -> empty, yet sum lowers 0<=1<=2.4 passes
    inp5c = make_input(comps_uniform(3, 0, 0.8), "SIMPLEX_MIXTURE","LINEAR",0)
    env5c = generate_doe(inp5c, json.dumps(inp5c, ensure_ascii=False, sort_keys=True).encode())
    assert env5c["status"]=="REJECTED"
    assert any("infeasible after lattice" in r for r in env5c["rejection_reasons"]), env5c["rejection_reasons"]
    print("PASS: infeasible after lattice filtering")

    # 6. missing experiment_card field -> REJECTED via schema
    inp6 = make_input(comps_uniform(3,0,1), "SIMPLEX_MIXTURE","LINEAR",0)
    del inp6["experiment_card"]["hypothesis"]
    env6 = generate_doe(inp6, json.dumps(inp6, ensure_ascii=False, sort_keys=True).encode())
    assert env6["status"]=="REJECTED", env6
    print("PASS: missing card field rejected")

    # 7. SIMPLEX + target>0 rejected
    inp7 = make_input(comps_uniform(3,0,1), "SIMPLEX_MIXTURE","LINEAR",2)
    env7 = generate_doe(inp7, json.dumps(inp7, ensure_ascii=False, sort_keys=True).encode())
    assert env7["status"]=="REJECTED"
    assert any("target_runs" in r for r in env7["rejection_reasons"])
    print("PASS: SIMPLEX target>0 rejected")

    # 8a duplicate component_id
    inp8a = make_input([{"component_id":"A","lower_bound":0,"upper_bound":1},{"component_id":"A","lower_bound":0,"upper_bound":1},{"component_id":"B","lower_bound":0,"upper_bound":1}], "SIMPLEX_MIXTURE","LINEAR",0)
    env8a = generate_doe(inp8a, json.dumps(inp8a, ensure_ascii=False, sort_keys=True).encode())
    assert env8a["status"]=="REJECTED" and "duplicate" in " ".join(env8a["rejection_reasons"]).lower()
    print("PASS: duplicate id rejected")
    # 8b bounds inverted
    inp8b = make_input([{"component_id":"A","lower_bound":0.8,"upper_bound":0.2},{"component_id":"B","lower_bound":0,"upper_bound":1},{"component_id":"C","lower_bound":0,"upper_bound":1}], "SIMPLEX_MIXTURE","LINEAR",0)
    env8b = generate_doe(inp8b, json.dumps(inp8b, ensure_ascii=False, sort_keys=True).encode())
    assert env8b["status"]=="REJECTED"
    print("PASS: bounds inverted rejected")

    # 9. D-optimal candidate==p full selection: find a feasible narrow case where candidates==p, otherwise use unconstrained full set as proxy (with target==candidates the greedy exchange still keeps estimable set)
    # Probe engine directly to find any input where candidates==p; search small grid
    from domains.lubricant.compute.doe.engine import _build_doe_candidates
    found=False
    for q in [3,4]:
        p_quad=q+q*(q-1)//2
        p_lin=q
        for model_order, p in [("LINEAR",p_lin),("QUADRATIC",p_quad)]:
            for low, high in [(0,1),(0,0.8),(0.2,0.8),(0.1,0.6)]:
                comps=[{"component_id":f"C{i}","lower_bound":low,"upper_bound":high} for i in range(q)]
                sorted_ids=sorted([c["component_id"] for c in comps])
                lowers=[low]*q
                uppers=[high]*q
                cands=_build_doe_candidates({"mixture_total":1.0}, sorted_ids, lowers, uppers, q)
                if len(cands)==p:
                    inp9=make_input(comps, "D_OPTIMAL_MIXTURE", model_order, p)
                    env9=generate_doe(inp9, json.dumps(inp9, ensure_ascii=False, sort_keys=True).encode())
                    assert env9["status"]=="OK", f"expected OK for p==cand {q} {model_order} {low} {high} {env9}"
                    assert env9["result"]["run_count"]==p
                    assert env9["result"]["candidates_considered"]==p
                    # all candidates must be selected (sorted order determinism)
                    found=True
                    break
            if found:
                break
        if found:
            break
    if not found:
        # fallback: use unconstrained q=3 linear with target 3 where candidates=10 > p but we set target == candidates to force all selected? Actually target max is caps at candidates, so we test with target == candidates that output size == candidates
        inp9 = make_input(comps_uniform(3,0,1), "D_OPTIMAL_MIXTURE","LINEAR",10)
        raw9=json.dumps(inp9, ensure_ascii=False, sort_keys=True).encode()
        env9=generate_doe(inp9, raw9)
        assert env9["status"]=="OK"
        assert env9["result"]["candidates_considered"]==10
        assert env9["result"]["run_count"]==10
        print("PASS: D-optimal full selection fallback (10 candidates)")
    else:
        print("PASS: D-optimal candidate==p full selection")

    # 10. D-optimal convergence + audit candidates_considered
    inp10 = make_input(comps_uniform(4,0,1), "D_OPTIMAL_MIXTURE","QUADRATIC",12)
    env10 = generate_doe(inp10, json.dumps(inp10, ensure_ascii=False, sort_keys=True).encode())
    assert env10["status"]=="OK", env10
    assert env10["result"]["candidates_considered"]==15
    assert env10["method"]=="D_OPTIMAL_GREEDY_DET_V1"
    assert env10["parameters"]["convergence_threshold"]==1e-12
    # selection_reason contains candidate count
    assert "candidates=15" in env10["result"]["selection_reason"]
    # evidence OBSERVED
    assert any(e["status"]=="OBSERVED" for e in env10["evidence"])
    print("PASS: D-optimal convergence and audit")

    # 11. proportions sum ==1.0 exact for all runs across both design types
    for inp in [make_input(comps_uniform(3,0,1),"SIMPLEX_MIXTURE","QUADRATIC",0), make_input(comps_uniform(4,0,1),"D_OPTIMAL_MIXTURE","QUADRATIC",12)]:
        env=generate_doe(inp, json.dumps(inp, ensure_ascii=False, sort_keys=True).encode())
        assert env["status"]=="OK"
        for r in env["result"]["runs"]:
            s=math.fsum(r["proportions"].values())
            assert s==1.0, f"sum !=1.0 exact {s} {r}"
    print("PASS: proportions sum ==1.0 exact")

    # 12. deterministic double run byte equal via CLI or direct (here direct + CLI)
    inp12 = make_input(comps_uniform(3,0,1), "D_OPTIMAL_MIXTURE","QUADRATIC",8)
    raw12=json.dumps(inp12, ensure_ascii=False, sort_keys=True).encode()
    env_a=generate_doe(inp12, raw12)
    env_b=generate_doe(inp12, raw12)
    b_a=json.dumps(env_a, ensure_ascii=False, indent=2, sort_keys=False).encode()+b"\n"
    b_b=json.dumps(env_b, ensure_ascii=False, indent=2, sort_keys=False).encode()+b"\n"
    assert b_a==b_b, "double run bytes differ"
    # also via CLI
    with tempfile.TemporaryDirectory() as td:
        p_in=Path(td)/"in.json"
        p_out1=Path(td)/"out1.json"
        p_out2=Path(td)/"out2.json"
        p_in.write_bytes(raw12)
        import subprocess
        for po in [p_out1, p_out2]:
            r=subprocess.run([sys.executable, "-m", "domains.lubricant.compute.doe.engine", str(p_in), str(po)], cwd=str(ROOT), capture_output=True)
            assert r.returncode==0, r.stderr.decode()[:500]
        assert p_out1.read_bytes()==p_out2.read_bytes()
    print("PASS: deterministic double run byte equal")

    # 13. gold fixture reproduction hash locked
    gold_in_path=ROOT/"fixtures/compute/doe-gold-input.json"
    gold_out_path=ROOT/"fixtures/compute/doe-gold-output.json"
    gold_data=json.loads(gold_in_path.read_text(encoding="utf-8"))
    raw_gold=gold_in_path.read_bytes()
    env_gold=generate_doe(gold_data, raw_gold)
    disk=json.loads(gold_out_path.read_text(encoding="utf-8"))
    # status OK and result matches
    assert disk["status"]=="OK", disk
    assert env_gold["status"]=="OK"
    assert hashlib.sha256(json.dumps(env_gold, ensure_ascii=False, indent=2).encode()+b"\n").hexdigest()==hashlib.sha256(gold_out_path.read_bytes()).hexdigest(), "gold output bytes differ"
    # also validate schemas
    assert not validate("doe_input.schema.json", gold_data), "gold input schema fail"
    errs_gold=validate("doe_result_schema.json", env_gold)
    assert not errs_gold, f"gold output schema fail {[e.message for e in errs_gold]}"
    print("PASS: gold fixture reproduction")

    # additional: envelope CLI REJECTED cases land as file exit 0 (simplex target>0)
    with tempfile.TemporaryDirectory() as td:
        bad=make_input(comps_uniform(3,0,1),"SIMPLEX_MIXTURE","LINEAR",1)
        p_in=Path(td)/"bad_in.json"
        p_out=Path(td)/"bad_out.json"
        p_in.write_text(json.dumps(bad, ensure_ascii=False, indent=2), encoding="utf-8")
        import subprocess as sp
        r=sp.run([sys.executable,"-m","domains.lubricant.compute.doe.engine", str(p_in), str(p_out)], cwd=str(ROOT), capture_output=True, text=True)
        assert r.returncode==0
        env=json.loads(p_out.read_text(encoding="utf-8"))
        assert env["status"]=="REJECTED" and env["result"]=={}
        assert env["evidence"]==[]
    print("PASS: CLI REJECTED envelope")

    # OK envelope evidence OBSERVED minimal
    inp_ok=make_input(comps_uniform(3,0,1),"SIMPLEX_MIXTURE","LINEAR",0)
    env_ok=generate_doe(inp_ok, json.dumps(inp_ok, ensure_ascii=False, sort_keys=True).encode())
    assert env_ok["evidence"] and env_ok["evidence"][0]["status"]=="OBSERVED"
    assert not validate("doe_result_schema.json", env_ok), f"ok envelope invalid {[e.message for e in validate('doe_result_schema.json', env_ok)]}"
    print("PASS: OK envelope OBSERVED")

    print("ALL DOE TESTS PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
