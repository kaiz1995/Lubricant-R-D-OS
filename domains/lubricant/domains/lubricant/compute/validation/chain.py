from .common import canonical_digest, check


def _components(data):
    engine = data.get("engine_name")
    if engine == "doe":
        runs = data.get("result", {}).get("runs", [])
        return set(runs[0].get("proportions", {})) if runs else set()
    if engine == "statistics":
        terms = data.get("parameters", {}).get("term_order", [])
        return {part[2:] for term in terms for part in term.split("*") if part.startswith("x_")}
    if engine == "optimization":
        rows = data.get("result", {}).get("recommended_candidates", [])
        return set(rows[0].get("proportions", {})) if rows else set()
    return {x.get("component_id") for x in data.get("result", {}).get("components", [])}


def validate_chain(primary, artifact_type, context):
    by_type = {x.get("artifact_type"): x for x in context}
    state = {"doe_to_statistics": "NOT_CHECKED", "statistics_to_optimization": "NOT_CHECKED", "cost_basis": "NOT_CHECKED", "design_space_domain": "NOT_CHECKED"}
    out = []
    if artifact_type == "statistics_result" and "doe_result" in by_type:
        ok = _components(primary) == _components(by_type["doe_result"]["data"])
        state["doe_to_statistics"] = "CONSISTENT" if ok else "MISMATCH"
        state["design_space_domain"] = state["doe_to_statistics"]
        out.append(check("chain.doe_statistics.components", "CROSS_STAGE", "INFO" if ok else "ERROR", "DOE and Statistics component sets must match"))
    if artifact_type == "optimization_result":
        params = primary.get("parameters", {})
        if "statistics_result" in by_type:
            actual = canonical_digest(by_type["statistics_result"]["data"])
            declared = params.get("source_statistics_digest", actual)
            ok = actual == declared and _components(primary) == _components(by_type["statistics_result"]["data"])
            state["statistics_to_optimization"] = "CONSISTENT" if ok else "MISMATCH"
            state["design_space_domain"] = state["statistics_to_optimization"]
            out.append(check("chain.statistics_optimization", "CROSS_STAGE", "INFO" if ok else "ERROR", "Statistics model digest and components must match Optimization references"))
        if "cost_result" in by_type:
            actual = canonical_digest(by_type["cost_result"]["data"])
            ok = params.get("source_cost_digest", actual) == actual
            state["cost_basis"] = "CONSISTENT" if ok else "MISMATCH"
            out.append(check("chain.cost_basis", "CROSS_STAGE", "INFO" if ok else "ERROR", "Cost artifact digest must match Optimization cost basis"))
    return out, state
