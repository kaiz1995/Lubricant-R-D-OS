import math
from .common import check


def validate_cost(data, _context):
    result = data.get("result", {})
    if data.get("status") != "OK":
        return [check("cost.status", "NUMERICAL", "ERROR", "rejected cost artifact is not eligible")]
    components = result.get("components", [])
    out = [check("cost.total_positive", "NUMERICAL", "INFO" if result.get("total_cost", 0) > 0 else "ERROR", "total_cost must be positive")]
    pct = math.fsum(x.get("cost_percentage", 0) for x in components)
    out.append(check("cost.contribution_sum", "NUMERICAL", "INFO" if abs(pct - 100.0) <= 1e-9 else "ERROR", "cost percentages must sum to 100"))
    ranking = result.get("sensitivity", {}).get("ranking", [])
    expected = sorted(components, key=lambda x: (-x.get("cost_percentage", 0), x.get("component_id", "")))
    consistent = [(x.get("component_id"), x.get("cost_percentage")) for x in expected] == [(x.get("component_id"), x.get("percentage")) for x in ranking]
    out.append(check("cost.sensitivity_ranking", "NUMERICAL", "INFO" if consistent else "ERROR", "sensitivity ranking must match components"))
    return out
