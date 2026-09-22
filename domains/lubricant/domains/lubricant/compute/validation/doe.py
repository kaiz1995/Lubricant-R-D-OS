import math
from .common import check


def _bounds(data, context):
    supplied = data.get("parameters", {}).get("design_space_bounds")
    if isinstance(supplied, dict):
        return {key: (value["lower"], value["upper"]) for key, value in supplied.items()
                if isinstance(value, dict) and "lower" in value and "upper" in value}
    for item in context:
        source = item.get("data", {})
        supplied = source.get("parameters", {}).get("design_space_bounds")
        if isinstance(supplied, dict):
            return {key: (value["lower"], value["upper"]) for key, value in supplied.items()
                    if isinstance(value, dict) and "lower" in value and "upper" in value}
        if item.get("artifact_type") == "doe_input" and isinstance(source.get("components"), list):
            return {x["component_id"]: (x["lower_bound"], x["upper_bound"]) for x in source["components"]
                    if all(key in x for key in ("component_id", "lower_bound", "upper_bound"))}
    return {}


def validate_doe(data, context):
    if data.get("status") != "OK":
        return [check("doe.status", "NUMERICAL", "ERROR", "rejected DOE artifact is not eligible")]
    result = data.get("result", {}); runs = result.get("runs", [])
    out = [check("doe.run_count", "NUMERICAL", "INFO" if result.get("run_count") == len(runs) else "ERROR", "run_count must match runs")]
    sums_ok = all(abs(math.fsum(r.get("proportions", {}).values()) - 1.0) <= 1e-9 for r in runs)
    bounds = _bounds(data, context)
    component_ids = set(runs[0].get("proportions", {})) if runs else set()
    evidence_ok = bool(bounds) and set(bounds) == component_ids
    bounds_ok = evidence_ok and all(all(key in bounds and bounds[key][0] - 1e-9 <= value <= bounds[key][1] + 1e-9
                                        for key, value in r.get("proportions", {}).items()) for r in runs)
    keys = [set(r.get("proportions", {})) for r in runs]
    components_ok = bool(keys) and all(x == keys[0] for x in keys)
    out += [check("doe.proportion_sum", "NUMERICAL", "INFO" if sums_ok else "ERROR", "run proportions must sum to mixture_total 1.0"),
            check("doe.bounds_evidence", "PROVENANCE", "INFO" if evidence_ok else "FATAL", "actual DOE design-space bounds must be available"),
            check("doe.bounds", "NUMERICAL", "INFO" if bounds_ok else "ERROR", "proportions must satisfy supplied design-space bounds"),
            check("doe.components", "NUMERICAL", "INFO" if components_ok else "ERROR", "all runs must use the same components")]
    return out
