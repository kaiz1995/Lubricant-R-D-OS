"""Direct-run tests for Phase 4.4 deterministic optimization."""
from __future__ import annotations
import copy, hashlib, json, subprocess, sys, tempfile
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from domains.lubricant.compute.optimization.engine import optimize

FIX=ROOT/"fixtures"/"compute"; GOLD=FIX/"optimization-gold-input.json"
def base(): return json.loads(GOLD.read_text(encoding="utf-8"))
def run(data):
    raw=(json.dumps(data,ensure_ascii=False,sort_keys=True)+"\n").encode("utf-8")
    return optimize(data,raw)
def rejected(data):
    env=run(data)
    assert env["status"]=="REJECTED" and len(env["rejection_reasons"])>0, env
    return env

def main():
    # 1 Happy PARETO
    p=run(base()); assert p["status"]=="OK" and p["result"]["pareto_front_size"]>0
    assert p["parameters"]["comparison_tolerance"]==1e-12
    assert any(x["statement"]=="Pareto dominance uses comparison_tolerance=1e-12" and x["source"]=="engine constant COMPARISON_TOLERANCE_V1" for x in p["evidence"])
    assert [x["rank"] for x in p["result"]["recommended_candidates"]]==list(range(1,len(p["result"]["recommended_candidates"])+1))
    schemas=[json.loads(x.read_text(encoding="utf-8")) for x in (ROOT/"domains/lubricant/schemas").glob("*.json")]
    registry=Registry()
    for schema in schemas:
        if "$id" in schema: registry=registry.with_resource(schema["$id"],Resource.from_contents(schema))
    result_schema=next(x for x in schemas if x.get("$id","").endswith("optimization_result_schema.json"))
    assert not list(Draft202012Validator(result_schema,registry=registry).iter_errors(p))
    # 2 Happy weighted
    w=base(); w["ranking_method"]="WEIGHTED_OBJECTIVE"; w["weights"]=[{"objective_ref":"VI","weight":.4},{"objective_ref":"ACID","weight":.3},{"objective_ref":"COST","weight":.3}]
    we=run(w); scores=[x["weighted_score"] for x in we["result"]["recommended_candidates"]]
    assert we["status"]=="OK" and scores and scores==sorted(scores,reverse=True)
    # 3 Hard constraints eliminate all
    h=base(); h["hard_constraints"][0]["threshold"]=1
    he=run(h); assert he["result"]["hard_constraint_passed"]==0 and he["result"]["recommended_candidates"]==[]
    # 4 Guardrail filtering
    g=base(); g["guardrails"][0]["minimum_margin"]=5
    ge=run(g); assert ge["result"]["guardrail_passed"] < ge["result"]["hard_constraint_passed"]
    # 5 Non-inferiority is independent: permissive guardrails pass all hard survivors, NI removes some.
    n=base()
    for guardrail in n["guardrails"]: guardrail["minimum_margin"]=-1000
    without_ni=run(n); assert without_ni["result"]["guardrail_passed"]==without_ni["result"]["hard_constraint_passed"]
    n["non_inferiority"]=[{"non_inferiority_id":"NI-ACID","ctq_reference":"ACID","direction":"LOWER_IS_BETTER","minimum_margin":0,"tolerance_mode":"ABSOLUTE"}]
    ne=run(n); assert ne["result"]["guardrail_passed"] < ne["result"]["hard_constraint_passed"]
    # 6 Domain guard excludes points while retaining evaluated count
    d=base(); d["source_doe_design_points"]=[{"proportions":{"A":.5,"B":.5,"C":0}},{"proportions":{"A":.5,"B":0,"C":.5}},{"proportions":{"A":0,"B":.5,"C":.5}}]
    de=run(d); assert de["result"]["total_candidates_evaluated"]==15 and de["result"]["hard_constraint_passed"]<15
    # 7 Cost engine reuse and theoretical cost
    for c in p["result"]["recommended_candidates"]:
        theory=sum(c["proportions"][i]*{"A":30,"B":20,"C":10}[i] for i in "ABC")
        assert abs(c["total_cost"]-theory)<1e-12 and c["cost_evaluation"]["engine_name"]=="cost"
    # 8 Cheap but inferior candidate cannot rank
    cheap=base(); cheap["guardrails"][0]["minimum_margin"]=0
    ce=run(cheap); assert all(x["predicted_ctq"]["VI"]>=90-TOL for x in ce["result"]["recommended_candidates"])
    # 9 Empty feasible is OK
    empty=base(); empty["guardrails"][0]["minimum_margin"]=1000
    ee=run(empty); assert ee["status"]=="OK" and ee["result"]["recommended_candidates"]==[]
    # REJECTED envelopes always carry reasons.
    bad=base(); bad["candidate_space"]["component_ids"]=["B","A","C"]; rejected(bad)
    bad=base(); bad["baseline"]["ctq_values"]["VI"]=0; rejected(bad)
    bad=base(); bad["ranking_method"]="WEIGHTED_OBJECTIVE"; bad["weights"]=[{"objective_ref":"COST","weight":.5}]; rejected(bad)
    # 10 CLI double run is byte-identical
    with tempfile.TemporaryDirectory() as td:
        a,b=Path(td)/"a.json",Path(td)/"b.json"; cmd=[sys.executable,"-m","domains.lubricant.compute.optimization.engine",str(GOLD)]
        subprocess.run(cmd+[str(a)],cwd=ROOT,check=True); subprocess.run(cmd+[str(b)],cwd=ROOT,check=True); assert a.read_bytes()==b.read_bytes()
    # 11 golden bytes locked
    expected={"optimization-gold-input.json":"a89afb4c001fef9d6b1d6a7213290c7882acc22c84bfe7aff1bc72901b21e018", "optimization-gold-output.json":"2ba0a953ebf81379409b5650e617752e9e767699ab2f785ddb6de10b019f69f5"}
    for name,digest in expected.items(): assert hashlib.sha256((FIX/name).read_bytes()).hexdigest()==digest
    print("PASS: optimization engine 11 scenarios, determinism, golden hashes")

TOL=1e-12
if __name__=="__main__": main()
