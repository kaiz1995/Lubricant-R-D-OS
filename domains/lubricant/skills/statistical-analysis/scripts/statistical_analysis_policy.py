"""Deterministic wording for a Phase 4 statistical-analysis handoff, plus the grease gate.

Two layers, deliberately separated so the six oil routes are untouched:

1. The ORIGINAL Phase 3 policy. ``expected_decision_fields`` and ``has_gap`` are
   unchanged in meaning and in output: every oil request produces exactly the decision
   block it produced before. ``expected_decision_fields`` is now a thin wrapper over a
   route-aware function, and with the default route it returns the original strings
   verbatim.

2. The PRECISION_GREASE_DEV additions, all gated on the supplied project charter
   routing as ``PRECISION_GREASE_DEV``. Two rules, both from the step-12/step-13 plan:

   * **THE MODEL ONLY ACCEPTS DATA THAT PASSED THE VARIANCE CHECK.** A round whose
     engine verdict is ``UNDERPOWERED`` or ``REPLICATE_INCONSISTENT`` must not enter
     the model. An ``UNDERPOWERED`` design could not answer the question it was asked,
     so fitting a model to it fits noise and then presents the fit as knowledge; a
     ``REPLICATE_INCONSISTENT`` round has same-arm replicates that contradict, so
     there is no mean worth fitting at all. ``NO_DETECTABLE_DIFFERENCE`` is admissible
     but recorded as such, because "a capable design found nothing" is information,
     while "we could not measure it" is not.
   * **THE MODEL CARRIES ITS APPLICABILITY BOUNDARY (TRUST REGION).** Step 13's rule is
     that a model may only predict inside the region it was fitted on. The boundary is
     optional in the REQUEST -- an oil request that omits it stays valid exactly as
     before -- and when it is supplied the preflight validates it, the builder persists it
     onto the record, and step 16 checks its requested region against what was recorded.
     ``schemas/model.schema.json`` carries the slot since P-2 (2026-10-14) lifted the
     earlier "this skill must not change that" constraint; the decision block's grease
     branch still waits on a variance-reference slot this contract does not have.

Both rules are implemented in this module so the preflight, the builder and the
validator cannot disagree about the same input.
"""

from __future__ import annotations

import math

ROUTED_PROJECT_TYPE = "PRECISION_GREASE_DEV"

# --- Step-12 verdicts (mirrors the engine's four frozen values) ---------------
VERDICT_CONSISTENT_DIFFERENCE = "CONSISTENT_DIFFERENCE"
VERDICT_NO_DETECTABLE_DIFFERENCE = "NO_DETECTABLE_DIFFERENCE"
VERDICT_UNDERPOWERED = "UNDERPOWERED"
VERDICT_REPLICATE_INCONSISTENT = "REPLICATE_INCONSISTENT"
VARIANCE_VERDICTS = (
    VERDICT_CONSISTENT_DIFFERENCE,
    VERDICT_NO_DETECTABLE_DIFFERENCE,
    VERDICT_UNDERPOWERED,
    VERDICT_REPLICATE_INCONSISTENT,
)
# Verdicts that BLOCK the model. UNDERPOWERED is its own value on purpose: collapsing
# it into NO_DETECTABLE_DIFFERENCE is the most expensive error in grease R&D, and the
# same distinction decides here whether a model may be fitted at all.
BLOCKING_VERDICTS = (VERDICT_UNDERPOWERED, VERDICT_REPLICATE_INCONSISTENT)
ADMISSIBLE_VERDICTS = (VERDICT_CONSISTENT_DIFFERENCE, VERDICT_NO_DETECTABLE_DIFFERENCE)

# --- Applicability boundary (trust region) -----------------------------------
# The artifact contract has no field for the boundary, so the input declares it and the
# builder writes it as an extra property. It is enforced on the grease route only.
TRUST_REGION_FIELD = "applicability_boundary"
TRUST_REGION_REQUIRED_FIELDS = ("variable_references", "region_statement")
TRUST_REGION_OPTIONAL_FIELDS = ("lower_bounds", "upper_bounds", "unit", "basis", "source")
TRUST_REGION_FIELDS = set(TRUST_REGION_REQUIRED_FIELDS) | set(TRUST_REGION_OPTIONAL_FIELDS)

# --- Frozen evidence id prefix for the variance-gate evidence item ------------
VARIANCE_GATE_EVIDENCE_PREFIX = "E-VARIANCE-GATE-"


def has_gap(value: dict) -> bool:
    """True when an artifact-level evidence item records an unresolved gap."""
    return any(isinstance(item, dict) and item.get("status") == "GAP" for item in value.get("evidence", []))


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def grease_route(project: object) -> bool:
    """True when the supplied charter routes this request onto the grease inner loop.

    The gate is read from the project charter the request already supplies, so no
    shared contract changes and no oil route is touched. A missing or non-grease
    project_type means the grease rules do not apply.
    """
    return isinstance(project, dict) and project.get("project_type") == ROUTED_PROJECT_TYPE


def variance_blockers(verdict: object, variance_id: object = None) -> list[str]:
    """Reasons this verdict may not enter the model (empty list = it may)."""
    if verdict not in VARIANCE_VERDICTS:
        return [
            f"variance verdict {verdict!r} is not one of the four frozen values "
            + ", ".join(VARIANCE_VERDICTS)
        ]
    if verdict in BLOCKING_VERDICTS:
        label = f"variance assessment {variance_id}" if has_text(variance_id) else "the variance assessment"
        if verdict == VERDICT_UNDERPOWERED:
            return [
                f"{label} is UNDERPOWERED: the design could not resolve the pre-registered difference, so "
                "fitting a model to this round fits noise and presents the fit as knowledge. UNDERPOWERED is "
                "never a synonym for NO_DETECTABLE_DIFFERENCE; change the method or the criterion "
                "(SIGMA_MAX = delta / k) before modeling"
            ]
        return [
            f"{label} is REPLICATE_INCONSISTENT: same-arm replicates contradict (or share a sample_id across "
            "batch_ids), so there is no mean worth fitting. Repair the replicate structure before modeling"
        ]
    return []


def variance_admissible(verdict: object) -> bool:
    return not variance_blockers(verdict)


def trust_region_errors(value: object) -> list[str]:
    """Structural errors of the declared applicability boundary (trust region).

    The boundary must name the variables it is stated over and carry a region
    statement; optional numeric bounds must be finite and ordered. A boundary that
    names no variable would let the model predict anywhere while claiming a region.
    """
    if not isinstance(value, dict):
        return ["applicability_boundary must be an object"]
    errors: list[str] = []
    unknown = sorted(set(value) - TRUST_REGION_FIELDS)
    missing = sorted(set(TRUST_REGION_REQUIRED_FIELDS) - set(value))
    if unknown or missing:
        return [f"applicability_boundary: unexpected={unknown or 'none'} missing={missing or 'none'}"]
    variables = value.get("variable_references")
    if not isinstance(variables, list) or not variables or not all(has_text(item) for item in variables):
        errors.append("applicability_boundary.variable_references must be a non-empty array of non-empty strings")
    if not has_text(value.get("region_statement")):
        errors.append("applicability_boundary.region_statement must be a non-empty string")
    for field in ("lower_bounds", "upper_bounds"):
        if field not in value:
            continue
        bounds = value[field]
        if not isinstance(bounds, dict) or not bounds:
            errors.append(f"applicability_boundary.{field} must be a non-empty object when supplied")
            continue
        for key, bound in sorted(bounds.items()):
            if not has_text(key) or not is_number(bound):
                errors.append(f"applicability_boundary.{field}.{key} must be a finite number")
    if not errors:
        variables = value["variable_references"]
        lower = value.get("lower_bounds") or {}
        upper = value.get("upper_bounds") or {}
        for name in variables:
            if name in lower and name in upper and float(lower[name]) > float(upper[name]):
                errors.append(
                    f"applicability_boundary: lower bound of {name} exceeds its upper bound, so the region is empty"
                )
        extra = sorted((set(lower) | set(upper)) - set(variables))
        if extra:
            errors.append(
                "applicability_boundary bounds must belong to a declared variable_reference; found "
                + ", ".join(extra)
            )
    return errors


def variance_gate_evidence_item(variance_id: object, verdict: object) -> dict:
    """The one evidence item the grease route appends: which variance record released this round."""
    return {
        "evidence_id": f"{VARIANCE_GATE_EVIDENCE_PREFIX}{variance_id}",
        "statement": (
            f"Variance assessment {variance_id} returned verdict {verdict}, so this round is admissible to the "
            "model. A verdict of UNDERPOWERED or REPLICATE_INCONSISTENT blocks the model on the grease route; "
            "UNDERPOWERED is never read as NO_DETECTABLE_DIFFERENCE."
        ),
        "source": f"variance-assessment:{variance_id}",
        "status": "OBSERVED",
    }


def has_variance_gate_evidence(evidence: object, variance_id: object) -> bool:
    if not isinstance(evidence, list):
        return False
    wanted = f"{VARIANCE_GATE_EVIDENCE_PREFIX}{variance_id}"
    return any(isinstance(item, dict) and item.get("evidence_id") == wanted for item in evidence)


# --- Decision block -----------------------------------------------------------

def expected_decision_fields(value: dict, grease: bool = False) -> dict[str, str]:
    """The canonical decision block.

    With ``grease=False`` (the default, and every oil route) this returns exactly the
    original Phase 3 wording, string for string. With ``grease=True`` the block adds the
    variance gate and the applicability boundary, because on that route the handoff has
    two more preconditions that the reader must see.
    """
    model_id = value.get("model_id", "")
    analyses = ", ".join(value.get("requested_analyses", []))
    fields = {
        "decision_question": f"Can supplied analysis request {model_id} be handed to the Phase 4 deterministic engine?",
        "hypothesis": f"{model_id} records supplied analysis requests without calculating a statistical model.",
        "uncertainty": "No coefficients, fit statistics, residual diagnosis, lack-of-fit result, interval, sensitivity result, adequacy conclusion, formulation, performance conclusion, or optimization is established by this Phase 3 artifact.",
        "decision_rule": "Hand off only linked observed-experiment response CTQs with a qualified method and evidence without GAP.",
        "result": f"{model_id} records supplied requests for {analyses}; no statistical calculation or model conclusion has been produced.",
        "decision": "GO",
        "next_action": f"Hand {model_id} to the Phase 4 deterministic engine without adding model results.",
    }
    if not grease:
        return fields
    # NOTE (E-2): this grease branch is currently dispatched by NOBODY, and that is
    # deliberate. Wiring it into build_model_artifact / validate_model_artifact was
    # reviewed and rejected: the builder computes the block from the REQUEST while the
    # validator recomputes it from the ARTIFACT, and this branch reads material
    # (variance_reference, the verdict, the applicability boundary) that the closed
    # schemas/model.schema.json (unevaluatedProperties: false) gives the artifact no slot
    # for -- the validator would then disagree with the builder and FAIL every build. It
    # stays here as the recorded contract of what the grease handoff would have to say,
    # ready for the day the model contract carries those fields; do not wire it before
    # that.
    variance_id = value.get("variance_reference", "")
    verdict = value.get("variance_verdict", "")
    boundary = value.get(TRUST_REGION_FIELD)
    region_statement = boundary.get("region_statement") if isinstance(boundary, dict) else None
    variables = boundary.get("variable_references") if isinstance(boundary, dict) else None
    region = ", ".join(variables) if isinstance(variables, list) else "none declared"
    return {
        **fields,
        "decision_rule": (
            "Hand off only linked observed-experiment response CTQs with a qualified method and evidence without "
            "GAP. On the precision-grease route the round must ALSO have passed the variance check: a verdict of "
            "UNDERPOWERED or REPLICATE_INCONSISTENT blocks the model, and the model must carry the applicability "
            "boundary (trust region) it was fitted on, because it may only predict inside that region."
        ),
        "result": (
            f"{model_id} records supplied requests for {analyses}; no statistical calculation or model conclusion "
            f"has been produced. Variance gate: {variance_id} returned {verdict}. Applicability boundary: "
            f"{region_statement} (variables: {region})."
        ),
        "next_action": (
            f"Hand {model_id} to the Phase 4 deterministic engine, then constrain every prediction to the "
            f"applicability boundary recorded here ({region}). A prediction outside it is an extrapolation and "
            "must be refused, not reported."
        ),
    }


def input_notes(verdict: object, variance_id: object) -> list[str]:
    """Audible NOTE lines for the grease route."""
    notes = [f"NOTE: variance gate {variance_id}: verdict {verdict} admits this round to the model"]
    if verdict == VERDICT_NO_DETECTABLE_DIFFERENCE:
        notes.append(
            "NOTE: the verdict is NO_DETECTABLE_DIFFERENCE, which is admissible but is not a difference: the "
            "model records the direction as excluded rather than supported")
    return notes
