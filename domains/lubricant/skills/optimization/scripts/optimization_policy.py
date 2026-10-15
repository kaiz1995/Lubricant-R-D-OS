"""Deterministic wording and route rules for a Phase 4 optimization handoff.

Two things live here, and both are pure functions of the artifact's own fields so
the builder and the validator can never disagree about the same input.

1. THE COST SEMANTICS OF THE OBJECTIVE (plan section 4.4.3 item 3-1, upstream
   redesign section 6.3). ``objective_type`` keeps both of its contract values, but
   on the precision-grease route it DEFAULTS to ``CONSTRAINT_SATISFACTION``: satisfy
   the performance criteria first and then stay under the cost ceiling. Putting cost
   and performance side by side as equal objectives (``MULTI_OBJECTIVE``) is the
   wrong trade for a performance-first product, and JSON Schema has no force behind
   a default, so the default is implemented here, in the skill policy layer, exactly
   as the plan requires. Cost is a constraint, never a criterion; it must never
   appear as a CTQ criterion.

2. THE STAGE AND THE TRUST REGION. The grease route's step 14 is
   ``NON_INFERIORITY_PASSED`` (added in batch 0 and deliberately chosen over reusing
   ``OPTIMIZED``), while the six oil routes stay on ``OPTIMIZED``. The grease route
   also carries the model's applicability boundary (trust region) into the engine,
   because a recommended point outside the region the model was fitted on is an
   extrapolation and may never be recommended silently.

Everything oil-side is unchanged: with ``grease=False`` the decision block below is
the original wording, string for string.
"""

from __future__ import annotations

import math


GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"
OIL_STAGE = "OPTIMIZED"
GREASE_STAGE = "NON_INFERIORITY_PASSED"
OBJECTIVE_TYPES = ("CONSTRAINT_SATISFACTION", "MULTI_OBJECTIVE")
GREASE_DEFAULT_OBJECTIVE_TYPE = "CONSTRAINT_SATISFACTION"

# The model-side field name (mirrors statistical_analysis_policy.TRUST_REGION_FIELD)
# and the artifact-side name the optimization record carries. The model artifact
# contract (schemas/model.schema.json, unevaluatedProperties: false) has no slot for
# the boundary, so the boundary travels input-side on the grease route: the request
# supplies ``model_trust_region`` and the builder writes it into the optimization
# artifact as ``trust_region``, where run_compute translates it for the engine.
MODEL_TRUST_REGION_FIELD = "applicability_boundary"
MODEL_TRUST_REGION_INPUT_FIELD = "model_trust_region"
TRUST_REGION_FIELD = "trust_region"
TRUST_REGION_REQUIRED_FIELDS = ("variable_references", "region_statement")
TRUST_REGION_OPTIONAL_FIELDS = ("lower_bounds", "upper_bounds", "unit", "basis", "source")
TRUST_REGION_FIELDS = set(TRUST_REGION_REQUIRED_FIELDS) | set(TRUST_REGION_OPTIONAL_FIELDS)
TRUST_REGION_MODES = ("EXCLUDE", "DEGRADE")
TRUST_REGION_DEFAULT_MODE = "EXCLUDE"

# The two variance verdicts that release a round to the optimizer. UNDERPOWERED is
# deliberately its own value and is never read as NO_DETECTABLE_DIFFERENCE.
ADMISSIBLE_VARIANCE_VERDICTS = ("CONSISTENT_DIFFERENCE", "NO_DETECTABLE_DIFFERENCE")
BLOCKING_VARIANCE_VERDICTS = ("UNDERPOWERED", "REPLICATE_INCONSISTENT")


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def has_gap(value: dict) -> bool:
    return any(isinstance(item, dict) and item.get("status") == "GAP" for item in value.get("evidence", []))


def grease_route(project: object) -> bool:
    """True when the supplied charter routes this request onto the grease inner loop."""
    return isinstance(project, dict) and project.get("project_type") == GREASE_PROJECT_TYPE


def stage_for(grease: bool) -> str:
    return GREASE_STAGE if grease else OIL_STAGE


def resolve_objective_type(request: object, grease: bool) -> str | None:
    """The objective type the artifact records.

    An explicitly supplied value always wins (both contract values stay legal on both
    routes). When it is absent the grease route fills CONSTRAINT_SATISFACTION; the oil
    routes keep demanding it explicitly, so no oil request changes behaviour.
    """
    if not isinstance(request, dict):
        return None
    supplied = request.get("objective_type")
    if has_text(supplied):
        return supplied
    return GREASE_DEFAULT_OBJECTIVE_TYPE if grease else None


def default_note(grease: bool, supplied: object) -> list[str]:
    """A NOTE line whenever the grease default was applied, so it is never silent."""
    if not grease or has_text(supplied):
        return []
    return [
        f"NOTE: objective_type was not supplied; the {GREASE_PROJECT_TYPE} route defaults to "
        f"{GREASE_DEFAULT_OBJECTIVE_TYPE} (satisfy performance first, then stay under the cost ceiling) "
        "rather than MULTI_OBJECTIVE, which would weigh cost and performance as equal objectives"
    ]


def trust_region_errors(value: object) -> list[str]:
    """Structural errors of a declared applicability boundary (model side).

    Mirrors the statistical-analysis rule: the boundary must name the variables it is
    stated over and carry a region statement; optional numeric bounds must be finite
    and ordered. A boundary that names no variable would let the model predict
    anywhere while claiming a region.
    """
    if not isinstance(value, dict):
        return [f"{MODEL_TRUST_REGION_FIELD} must be an object"]
    errors: list[str] = []
    unknown = sorted(set(value) - TRUST_REGION_FIELDS)
    missing = sorted(set(TRUST_REGION_REQUIRED_FIELDS) - set(value))
    if unknown or missing:
        return [f"{MODEL_TRUST_REGION_FIELD}: unexpected={unknown or 'none'} missing={missing or 'none'}"]
    variables = value.get("variable_references")
    if not isinstance(variables, list) or not variables or not all(has_text(item) for item in variables):
        errors.append(f"{MODEL_TRUST_REGION_FIELD}.variable_references must be a non-empty array of non-empty strings")
    if not has_text(value.get("region_statement")):
        errors.append(f"{MODEL_TRUST_REGION_FIELD}.region_statement must be a non-empty string")
    for field in ("lower_bounds", "upper_bounds"):
        bounds = value.get(field)
        if bounds is None:
            continue
        if not isinstance(bounds, dict) or not bounds:
            errors.append(f"{MODEL_TRUST_REGION_FIELD}.{field} must be a non-empty object when supplied")
            continue
        for key, bound in sorted(bounds.items()):
            if not has_text(key) or not is_number(bound):
                errors.append(f"{MODEL_TRUST_REGION_FIELD}.{field}.{key} must be a finite number")
    if not errors:
        variables = value["variable_references"]
        lower = value.get("lower_bounds") or {}
        upper = value.get("upper_bounds") or {}
        for name in variables:
            if name in lower and name in upper and float(lower[name]) > float(upper[name]):
                errors.append(
                    f"{MODEL_TRUST_REGION_FIELD}: lower bound of {name} exceeds its upper bound, so the region is empty"
                )
        extra = sorted((set(lower) | set(upper)) - set(variables))
        if extra:
            errors.append(
                f"{MODEL_TRUST_REGION_FIELD} bounds must belong to a declared variable_reference; found "
                + ", ".join(extra)
            )
    return errors


def trust_region_from_boundary(boundary: object) -> dict | None:
    """Translate the model's applicability boundary into the engine's trust region.

    The engine enforces a box: every variable it is given needs a numeric lower and
    upper bound. A boundary that declares no numeric box cannot be enforced, so it
    yields ``None`` here and the caller must refuse rather than quietly optimize
    without a boundary.
    """
    if not isinstance(boundary, dict) or trust_region_errors(boundary):
        return None
    lower = boundary.get("lower_bounds") or {}
    upper = boundary.get("upper_bounds") or {}
    bounds = [
        {"component_id": name, "lower": float(lower[name]), "upper": float(upper[name])}
        for name in boundary.get("variable_references", [])
        if name in lower and name in upper
    ]
    if not bounds:
        return None
    region = {
        "region_statement": boundary.get("region_statement"),
        "mode": TRUST_REGION_DEFAULT_MODE,
        "variable_bounds": bounds,
    }
    if boundary.get("basis") is not None:
        region["basis"] = boundary["basis"]
    return region


def trust_region_summary(trust_region: object) -> str | None:
    """One readable line for the decision block, or None when no region is recorded."""
    if not isinstance(trust_region, dict):
        return None
    bounds = trust_region.get("variable_bounds")
    if not isinstance(bounds, list) or not bounds:
        return None
    box = ", ".join(f"{item.get('component_id')}=[{item.get('lower')}, {item.get('upper')}]" for item in bounds)
    mode = trust_region.get("mode") or "EXCLUDE"
    return f"{trust_region.get('region_statement')} ({box}; mode {mode})"


def expected_decision_fields(value: dict, grease: bool = False, trust_region: object = None, variance_reference: object = None) -> dict[str, str]:
    """The canonical decision block.

    With ``grease=False`` (the default, and every oil route) this returns exactly the
    original Phase 3 wording, string for string. With ``grease=True`` the block adds
    the cost-semantics default, the variance gate, and the trust region, because on
    that route the handoff has three more preconditions the reader must see.
    """
    optimization_id = value.get("optimization_id", "")
    methods = ", ".join(value.get("methods", []))
    fields = {
        "decision_question": f"Can supplied optimization request {optimization_id} be handed to the Phase 4 deterministic engine?",
        "hypothesis": f"{optimization_id} records supplied objectives and methods without calculating an optimum.",
        "uncertainty": "No candidate, Pareto front, desirability, non-inferiority result, constraint evaluation, trade-off, formulation recommendation, performance conclusion, or verification result is established by this Phase 3 artifact.",
        "decision_rule": "Hand off only a linked MODEL_BUILT request with supplied objectives, supported Phase 3 methods, and evidence without GAP.",
        "result": f"{optimization_id} records supplied methods {methods}; no optimization calculation or recommendation has been produced.",
        "decision": "GO",
        "next_action": f"Hand {optimization_id} to the Phase 4 deterministic engine without adding candidates or recommendations.",
    }
    if not grease:
        return fields
    objective_type = value.get("objective_type", "")
    variance_id = variance_reference if variance_reference is not None else value.get("variance_reference", "")
    summary = trust_region_summary(trust_region if trust_region is not None else value.get(TRUST_REGION_FIELD))
    region = summary if summary else "none recorded"
    return {
        **fields,
        "decision_rule": (
            "Hand off only a linked MODEL_BUILT request with supplied objectives, supported Phase 3 methods, and "
            "evidence without GAP. On the precision-grease route the round must ALSO have passed the variance check "
            "(UNDERPOWERED or REPLICATE_INCONSISTENT blocks the optimization), the objective_type defaults to "
            "CONSTRAINT_SATISFACTION because cost is a constraint and never an objective weighed against "
            "performance, and every recommendation must fall inside the model's applicability boundary."
        ),
        "result": (
            f"{optimization_id} records supplied methods {methods} with objective_type {objective_type}; no "
            f"optimization calculation or recommendation has been produced. Variance gate: {variance_id}. "
            f"Model applicability boundary: {region}."
        ),
        "next_action": (
            f"Hand {optimization_id} to the Phase 4 deterministic engine with the model's trust region "
            f"({region}): a recommended point outside it must be removed or explicitly degraded, never "
            "recommended silently."
        ),
    }
