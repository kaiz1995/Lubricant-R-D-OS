from .common import check


def validate_optimization(data, _context):
    if data.get("status") != "OK":
        return [check("optimization.status", "NUMERICAL", "ERROR", "rejected optimization artifact is not eligible")]
    result = data.get("result", {}); candidates = result.get("recommended_candidates", [])
    ranks = [x.get("rank") for x in candidates]
    guardrails = all(all(m.get("passes") for m in x.get("margin_report", [])) for x in candidates)
    pareto = all(not x.get("in_pareto_front") or x.get("rank", 0) <= result.get("pareto_front_size", 0) for x in candidates)
    proportions = all(abs(sum(x.get("proportions", {}).values()) - 1.0) <= 1e-9 and all(0 <= v <= 1 for v in x.get("proportions", {}).values()) for x in candidates)
    return [check("optimization.guardrails", "NUMERICAL", "INFO" if guardrails else "ERROR", "recommended candidates must pass every guardrail"),
            check("optimization.ranks", "NUMERICAL", "INFO" if ranks == list(range(1, len(ranks) + 1)) else "ERROR", "ranks must be contiguous from 1"),
            check("optimization.pareto", "NUMERICAL", "INFO" if pareto else "ERROR", "Pareto flags must agree with pareto_front_size"),
            check("optimization.domain", "NUMERICAL", "INFO" if proportions else "ERROR", "candidate proportions must remain in the mixture domain")]
