from __future__ import annotations
# Note: jsonschema/referencing are established project dev-deps used by all Phase 4 engines; not a new dependency.
import hashlib, itertools, json, math, sys
from pathlib import Path
from domains.lubricant.compute.cost.engine import calculate_cost

ENGINE_NAME, ENGINE_VERSION, METHOD = "optimization", "0.1.0", "GRID_SEARCH_V1"
TOL, DOMAIN_TOL, MAX_POINTS = 1e-12, 1e-9, 10000

def _digest(raw): return hashlib.sha256(raw).hexdigest()
def _canonical(data): return json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")

def _schema_errors(data):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    root = Path(__file__).resolve().parents[2] / "schemas"
    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in root.glob("*.json")]
    registry = Registry()
    for schema in schemas:
        if "$id" in schema: registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    schema = next(s for s in schemas if s.get("$id", "").endswith("optimization_input.schema.json"))
    return [e.message for e in sorted(Draft202012Validator(schema, registry=registry).iter_errors(data), key=lambda e: list(e.path))]

def _rejected(data, raw, reasons):
    return {"schema_version":"0.1.0","engine_name":ENGINE_NAME,"engine_version":ENGINE_VERSION,"method":METHOD,"parameters":{"comparison_tolerance":TOL,"domain_check_method":"BOUNDING_BOX_APPROX_V1"},"input_digest":_digest(raw if raw is not None else _canonical(data)),"status":"REJECTED","rejection_reasons":reasons,"result":{},"evidence":[]}

def _compositions(total, n, prefix=()):
    if n == 1:
        yield prefix + (total,); return
    for value in range(total + 1): yield from _compositions(total-value, n-1, prefix+(value,))

def _terms(ids, order):
    out = ["x_"+x for x in ids]
    if order == "QUADRATIC": out += ["x_"+a+"*x_"+b for i,a in enumerate(ids) for b in ids[i+1:]]
    return out

def _business_errors(data):
    reasons=[]; ids=data["candidate_space"]["component_ids"]
    if ids != sorted(ids) or len(ids) != len(set(ids)): reasons.append("component_ids must be unique and lexicographically sorted")
    bounds=data["candidate_space"]["bounds"]; bm={x["component_id"]:x for x in bounds}
    if set(bm)!=set(ids) or len(bounds)!=len(ids): reasons.append("bounds component_ids must exactly match component_ids")
    if any(x["lower"] >= x["upper"] for x in bounds): reasons.append("bounds.lower must be less than bounds.upper")
    if math.fsum(x["lower"] for x in bounds)>1+DOMAIN_TOL or math.fsum(x["upper"] for x in bounds)<1-DOMAIN_TOL: reasons.append("candidate bounds have no simplex intersection")
    expected={tuple(_terms(ids,m["model_order"])) for m in data["statistical_models"]}
    if len(expected)!=1 or any(tuple(m["term_order"]) not in expected for m in data["statistical_models"]): reasons.append("component_ids do not match statistical model term_order")
    if any([c["term"] for c in m["coefficients"]] != m["term_order"] for m in data["statistical_models"]): reasons.append("coefficient terms do not match term_order")
    ctqs={m["ctq_reference"] for m in data["statistical_models"]}
    if len(ctqs)!=len(data["statistical_models"]): reasons.append("duplicate statistical model ctq_reference")
    if any(g["ctq_reference"] not in ctqs for g in data["guardrails"]): reasons.append("guardrail ctq_reference not found in statistical_models")
    if any(g["ctq_reference"] not in ctqs for g in data["non_inferiority"]): reasons.append("non-inferiority ctq_reference not found in statistical_models")
    if abs(math.fsum(data["baseline"]["proportions"].values())-1)>DOMAIN_TOL: reasons.append("baseline proportions must sum to 1.0")
    if set(data["baseline"]["proportions"])!=set(ids): reasons.append("baseline proportions must exactly match component_ids")
    for g in data["guardrails"]+data["non_inferiority"]:
        if g.get("tolerance_mode","RELATIVE_PERCENT")=="RELATIVE_PERCENT" and data["baseline"]["ctq_values"].get(g["ctq_reference"])==0: reasons.append("relative guardrail baseline_ref must not be zero")
    if any(c["reference_id"] not in ctqs|{"COST"} for c in data["hard_constraints"]): reasons.append("hard constraint reference_id not found")
    if data["ranking_method"]=="WEIGHTED_OBJECTIVE":
        weights=data.get("weights",[])
        if abs(math.fsum(w["weight"] for w in weights)-1)>DOMAIN_TOL: reasons.append("weighted objective weights must sum to 1.0")
        if any(w["objective_ref"] not in ctqs|{"COST"} for w in weights): reasons.append("weight objective_ref not found")
    elif data.get("weights"): reasons.append("weights are only allowed for WEIGHTED_OBJECTIVE")
    n=math.comb(data["candidate_space"]["grid_resolution"]+len(ids)-2,len(ids)-1)
    if n>MAX_POINTS: reasons.append("candidate grid exceeds 10000 points")
    dps=data["source_doe_design_points"]
    if any(set(p["proportions"])!=set(ids) for p in dps): reasons.append("source DOE proportions must exactly match component_ids")
    if not reasons:
        dm={i:(min(p["proportions"][i] for p in dps),max(p["proportions"][i] for p in dps)) for i in ids}
        lowers=[max(bm[i]["lower"],dm[i][0]) for i in ids]; uppers=[min(bm[i]["upper"],dm[i][1]) for i in ids]
        if any(lo>hi+DOMAIN_TOL for lo,hi in zip(lowers,uppers)) or math.fsum(lowers)>1+DOMAIN_TOL or math.fsum(uppers)<1-DOMAIN_TOL: reasons.append("no candidates within source DOE design space")
    return reasons

def optimize(data, input_bytes=None):
    errors=_schema_errors(data)
    if errors: return _rejected(data,input_bytes,["input schema validation failed: "+errors[0]])
    errors=_business_errors(data)
    if errors: return _rejected(data,input_bytes,errors)
    ids=data["candidate_space"]["component_ids"]; res=data["candidate_space"]["grid_resolution"]; bm={x["component_id"]:x for x in data["candidate_space"]["bounds"]}
    dps=data["source_doe_design_points"]; dm={i:(min(p["proportions"][i] for p in dps),max(p["proportions"][i] for p in dps)) for i in ids}
    models=data["statistical_models"]; candidates=[]
    for nums in _compositions(res-1,len(ids)):
        props={ids[i]:nums[i]/(res-1) for i in range(len(ids))}
        if any(props[i]<bm[i]["lower"]-TOL or props[i]>bm[i]["upper"]+TOL for i in ids): continue
        candidates.append(props)
    hard=[]
    for props in candidates:
        if any(props[i]<dm[i][0]-DOMAIN_TOL or props[i]>dm[i][1]+DOMAIN_TOL for i in ids): continue
        predicted={}
        for m in models:
            values=[]
            for term in m["term_order"]:
                factors=term.split("*"); values.append(math.prod(props[x[2:]] for x in factors))
            predicted[m["ctq_reference"]]=math.fsum(c["estimate"]*values[i] for i,c in enumerate(m["coefficients"]))
        template=data["cost_input"]["formula_template"]
        cost_data={"input_type":"COST_CALCULATION","formula":{"formula_id":template["formula_id"],"version":template["version"],"components":[{"material_id":x["component_id"],"fraction":props[x["component_id"]]} for x in template["components"] if props[x["component_id"]]>0]},"materials":data["cost_input"]["materials"],"price_timestamp":data["cost_input"]["price_timestamp"]}
        cost=calculate_cost(cost_data,_canonical(cost_data))
        if cost["status"]!="OK": continue
        row={"proportions":props,"predicted_ctq":predicted,"total_cost":cost["result"]["total_cost"],"currency":cost["result"]["currency"],"cost_evaluation":{"engine_name":cost["engine_name"],"engine_version":cost["engine_version"],"input_digest":cost["input_digest"],"total_cost":cost["result"]["total_cost"]}}
        ok=True
        for c in data["hard_constraints"]:
            value=row["total_cost"] if c["reference_id"]=="COST" else predicted[c["reference_id"]]
            ok &= value <= c["threshold"]+TOL if c["direction"]=="MINIMIZE" else value >= c["threshold"]-TOL
        if ok: hard.append(row)
    guardrail_passed=[]
    for row in hard:
        reports=[]
        for g in data["guardrails"]:
            base=data["baseline"]["ctq_values"][g["ctq_reference"]]; value=row["predicted_ctq"][g["ctq_reference"]]
            delta=(value-base) if g["direction"]=="HIGHER_IS_BETTER" else (base-value)
            margin=delta if g.get("tolerance_mode","RELATIVE_PERCENT")=="ABSOLUTE" else delta/base*100
            reports.append({"guardrail_id":g["guardrail_id"],"margin_value":margin,"passes":margin>=g["minimum_margin"]-TOL})
        row["margin_report"]=reports
        if all(x["passes"] for x in reports): guardrail_passed.append(row)
    feasible=[]
    for row in guardrail_passed:
        passes=True
        for criterion in data["non_inferiority"]:
            base=data["baseline"]["ctq_values"][criterion["ctq_reference"]]; value=row["predicted_ctq"][criterion["ctq_reference"]]
            delta=(value-base) if criterion["direction"]=="HIGHER_IS_BETTER" else (base-value)
            margin=delta if criterion.get("tolerance_mode","RELATIVE_PERCENT")=="ABSOLUTE" else delta/base*100
            passes &= margin>=criterion["minimum_margin"]-TOL
        if passes: feasible.append(row)
    dirs={g["ctq_reference"]:g["direction"] for g in data["guardrails"]}
    def key(row): return tuple(row["proportions"][i] for i in ids)
    def dominates(a,b):
        vals=[]
        for ref,direction in dirs.items():
            av,bv=a["predicted_ctq"][ref],b["predicted_ctq"][ref]
            vals.append((av>=bv-TOL,av>bv+TOL) if direction=="HIGHER_IS_BETTER" else (av<=bv+TOL,av<bv-TOL))
        return bool(vals) and all(v[0] for v in vals) and any(v[1] for v in vals)
    front=sorted([a for a in feasible if not any(dominates(b,a) for b in feasible if b is not a)],key=key)
    if data["ranking_method"]=="PARETO": ranked=front; role="PARETO_FRONT"
    else:
        weights=data["weights"]; ranges={}
        for w in weights:
            ref=w["objective_ref"]; vals=[r["total_cost"] if ref=="COST" else r["predicted_ctq"][ref] for r in feasible]; ranges[ref]=(min(vals),max(vals)) if vals else (0,0)
        for row in feasible:
            score=0.0
            for w in weights:
                ref=w["objective_ref"]; value=row["total_cost"] if ref=="COST" else row["predicted_ctq"][ref]; lo,hi=ranges[ref]
                norm=1.0 if hi==lo else ((hi-value)/(hi-lo) if ref=="COST" or dirs.get(ref)=="LOWER_IS_BETTER" else (value-lo)/(hi-lo))
                score += w["weight"]*norm
            row["weighted_score"]=score
        ranked=sorted(feasible,key=lambda r:(-r["weighted_score"],key(r))); role="WEIGHTED_RANK_TOP"
    selected=ranked[:data.get("max_recommendations",10)]
    for i,row in enumerate(selected,1): row.update(rank=i,candidate_role=role,in_pareto_front=row in front,weighted_score=row.get("weighted_score"))
    bounds_note="BOUNDING_BOX_APPROX_V1: "+", ".join(f"{i}=[{dm[i][0]}, {dm[i][1]}]" for i in ids)+"; DOMAIN_SCREENED_APPROX"
    result={"total_candidates_evaluated":len(candidates),"hard_constraint_passed":len(hard),"guardrail_passed":len(feasible),"pareto_front_size":len(front) if data["ranking_method"]=="PARETO" else 0,"recommended_candidates":selected,"method_summary":{"ranking_method":data["ranking_method"],"grid_resolution":res,"effective_domain_note":bounds_note,"normalization_method":"FEASIBLE_SET_MINMAX_V1" if data["ranking_method"]=="WEIGHTED_OBJECTIVE" else None}}
    raw=input_bytes if input_bytes is not None else _canonical(data)
    return {"schema_version":"0.1.0","engine_name":ENGINE_NAME,"engine_version":ENGINE_VERSION,"method":METHOD,"parameters":{"comparison_tolerance":TOL,"domain_tolerance":DOMAIN_TOL,"domain_check_method":"BOUNDING_BOX_APPROX_V1"},"input_digest":_digest(raw),"status":"OK","rejection_reasons":[],"result":result,"evidence":[{"evidence_id":"optimization-grid-search","statement":"deterministic grid search; candidates are DOMAIN_SCREENED_APPROX before hard constraints, guardrails, and non-inferiority filtering","source":"engine internal deterministic algorithm","status":"OBSERVED"},{"evidence_id":"pareto-comparison-tolerance","statement":"Pareto dominance uses comparison_tolerance=1e-12","source":"engine constant COMPARISON_TOLERANCE_V1","status":"OBSERVED"}]}

def _write(path, env):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes((json.dumps(env,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))
def main():
    if len(sys.argv)!=3: print("Usage: python -m domains.lubricant.compute.optimization.engine <input.json> <output.json>",file=sys.stderr); return 2
    try: raw=Path(sys.argv[1]).read_bytes(); data=json.loads(raw.decode("utf-8")); env=optimize(data,raw)
    except Exception as exc: env=_rejected({},raw if "raw" in locals() else b"",["input read/parse failed: "+str(exc)])
    _write(sys.argv[2],env); return 0
if __name__=="__main__": raise SystemExit(main())
