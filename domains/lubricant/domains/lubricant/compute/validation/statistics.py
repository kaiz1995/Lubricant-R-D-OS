from .common import check


def validate_statistics(data, _context):
    if data.get("status") != "OK":
        return [check("statistics.status", "NUMERICAL", "ERROR", "statistics status must be OK")]
    result = data.get("result", {}); terms = data.get("parameters", {}).get("term_order", [])
    coefficients = result.get("coefficients", [])
    aligned = terms == [x.get("term") for x in coefficients]
    metadata = bool(result.get("anova_table")) and bool(result.get("fit_statistics"))
    components = {part[2:] for term in terms for part in term.split("*") if part.startswith("x_")}
    out = [check("statistics.term_alignment", "NUMERICAL", "INFO" if aligned else "ERROR", "coefficients must align with term_order"),
           check("statistics.metadata", "NUMERICAL", "INFO" if metadata else "ERROR", "ANOVA and fit metadata must exist"),
           check("statistics.model_domain", "NUMERICAL", "INFO" if components else "ERROR", "model component domain must be declared by term_order")]
    return out
