"""Deterministic decision wording for a supplied Phase 4 DOE-engine request."""

from __future__ import annotations


# WP-04a narrows the family vocabulary to the channels the Phase 4 DOE engine can
# actually solve. Mixture families route MIXTURE_CLOSED variables into the
# engine's ``components``; factor families route INDEPENDENT variables into
# ``factors``; MIXTURE_PROCESS accepts both. TAGUCHI_ROBUST and the pre-WP-04a
# screening/RSM families are not solvable and are deliberately not offered here.
# WP-04b upgrades the sequential family from a bare enum label to a runnable
# resource-constrained sequential path, so it joins the factor families.
MIXTURE_FAMILIES = ("MIXTURE", "CONSTRAINED_MIXTURE")
FACTOR_FAMILIES = ("FULL_FACTORIAL", "FRACTIONAL_FACTORIAL", "SPLIT_PLOT", "BAYESIAN_SEQUENTIAL")
COMBINED_FAMILIES = ("MIXTURE_PROCESS",)
SUPPORTED_FAMILIES = MIXTURE_FAMILIES + FACTOR_FAMILIES + COMBINED_FAMILIES

# Grease step 8 (purely additive): the sequential family's honest name.
#
# The engine implementation on this channel is "deterministic greedy selection
# from candidate lattice points", NOT model-driven sequential design -- there is no
# Gaussian process and no posterior sampling -- so the honest name is
# RESOURCE_CONSTRAINED_GREEDY_SEQUENTIAL. The legacy identifier keeps working as an
# alias, and both spellings are the SAME family: the alias never changes which
# channel a request routes to, and SUPPORTED_FAMILIES (and therefore the decision
# wording every pre-existing route receives) is left untouched.
SEQUENTIAL_FAMILY_HONEST = "RESOURCE_CONSTRAINED_GREEDY_SEQUENTIAL"
SEQUENTIAL_FAMILY_LEGACY = "BAYESIAN_SEQUENTIAL"
SEQUENTIAL_FAMILY_ALIASES = {SEQUENTIAL_FAMILY_HONEST: SEQUENTIAL_FAMILY_LEGACY}
SEQUENTIAL_FAMILIES = (SEQUENTIAL_FAMILY_HONEST, SEQUENTIAL_FAMILY_LEGACY)

# Grease route marker and its round-size constants. Only the exact project_type
# value activates the grease rules; the six oil routes declare other values (or
# none) and keep their existing wording and behaviour byte for byte.
GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"
# The bench is the bottleneck: about two concurrent positions per round and about
# 30 days per round, so one big fixed design is not feasible. A single 20-point
# design is roughly 7 months of bench time under that constraint, which a project
# can afford about once a year; the grease route therefore defaults to small
# sequential rounds instead.
GREASE_SMALL_BATCH_MIN = 3
GREASE_SMALL_BATCH_MAX = 6
GREASE_BENCH_POSITIONS_PER_ROUND = 2
GREASE_BENCH_ROUND_DAYS = 30


def has_gap(request: dict) -> bool:
    return any(isinstance(item, dict) and item.get("status") == "GAP" for item in request.get("evidence", []))


def canonical_family(family: object) -> object:
    """Map a family alias onto its canonical spelling (identity for everything else)."""
    return SEQUENTIAL_FAMILY_ALIASES.get(family, family)


def is_supported_family(family: object) -> bool:
    return canonical_family(family) in SUPPORTED_FAMILIES


def is_sequential_family(family: object) -> bool:
    return family in SEQUENTIAL_FAMILIES


def _request_shape(request: dict) -> tuple[str, dict, dict, str, object, bool]:
    design_id = request.get("experiment_design_id", "")
    design = request.get("design") if isinstance(request.get("design"), dict) else {}
    run_plan = request.get("run_plan") if isinstance(request.get("run_plan"), dict) else {}
    family = design.get("family", "")
    target_count = run_plan.get("target_count", "")
    return design_id, design, run_plan, family, target_count, is_supported_family(family) and not has_gap(request)


def expected_decision_fields(request: dict, project_type: str | None = None) -> dict[str, str]:
    """Canonical decision fields for one request.

    ``project_type`` is the route marker read from the validated project artifact.
    Omitted (or any value other than the grease route) returns exactly the
    pre-grease wording, so the six oil routes are unaffected; the grease route gets
    wording that names its small sequential round and the bench hard constraint.
    """
    if project_type == GREASE_PROJECT_TYPE:
        return expected_grease_decision_fields(request)
    design_id = request.get("experiment_design_id", "")
    design = request.get("design") if isinstance(request.get("design"), dict) else {}
    run_plan = request.get("run_plan") if isinstance(request.get("run_plan"), dict) else {}
    family = design.get("family", "")
    target_count = run_plan.get("target_count", "")
    ready = is_supported_family(family) and not has_gap(request)
    supported = "/".join(SUPPORTED_FAMILIES)
    return {
        "decision_question": f"Can supplied {family} request {design_id} be handed to the Phase 4 deterministic engine?",
        "hypothesis": f"{design_id} records supplied {family} planning inputs for later deterministic point generation.",
        "uncertainty": "Supplied design family, factors, target count, replicates, center points, randomization, response roles, guardrails, total, and information-value statements are not independently verified; statistical sufficiency is not verified and no DOE point, formula, measurement, result, cost, performance, optimization, or downstream conclusion is established.",
        "decision_rule": f"Hand off only a supplied {supported} request with linked qualified D/P method, feasible same-unit bounds, complete responses and guardrails, role-consistent design-space variables, and evidence without GAP.",
        "result": f"{design_id} is {'eligible' if ready else 'not eligible'} for Phase 4 deterministic point generation; family {family} and target count {target_count} are supplied planning inputs, not generated DOE points or a statistical-sufficiency conclusion.",
        "decision": "GO" if ready else "HOLD",
        "next_action": f"Hand {design_id} to the Phase 4 deterministic engine without adding DOE points." if ready else "Retain supplied evidence and resolve the recorded design-request gap before any Phase 4 handoff.",
    }


def expected_grease_decision_fields(request: dict) -> dict[str, str]:
    """Decision fields for one PRECISION_GREASE_DEV design request.

    Same field set and the same GO/HOLD rule as the shared wording; what changes is
    that the record states the route's own design policy: a small sequential round
    (3-6 samples per round) rather than one big DOE, and a round that fits the
    registered bench capacity.
    """
    design_id, _design, run_plan, family, target_count, ready = _request_shape(request)
    envelope = request.get("resource_envelope") if isinstance(request.get("resource_envelope"), dict) else {}
    bench_slots = envelope.get("bench_slots", "not declared")
    supported = "/".join(SUPPORTED_FAMILIES)
    return {
        "decision_question": f"Can supplied {family} request {design_id} be handed to the Phase 4 deterministic engine as one small sequential round?",
        "hypothesis": (
            f"{design_id} records supplied {family} planning inputs for one small sequential round of "
            f"{GREASE_SMALL_BATCH_MIN}-{GREASE_SMALL_BATCH_MAX} samples per round, decided from the previous "
            "round's result rather than from one large fixed design."),
        "uncertainty": (
            "Supplied design family, factors, target count, replicates, center points, randomization, response "
            "roles, guardrails, total, and information-value statements are not independently verified; statistical "
            "sufficiency is not verified and no DOE point, formula, measurement, result, cost, performance, "
            "optimization, or downstream conclusion is established. The declared bench capacity is a planning input "
            "and reserves no capacity."),
        "decision_rule": (
            f"Hand off only a supplied {supported} request with linked qualified D/P method, feasible same-unit "
            "bounds, complete responses and guardrails, role-consistent design-space variables, evidence without "
            f"GAP, a round of {GREASE_SMALL_BATCH_MIN}-{GREASE_SMALL_BATCH_MAX} samples per round, and a design "
            "size within the registered bench capacity."),
        "result": (
            f"{design_id} is {'eligible' if ready else 'not eligible'} for Phase 4 deterministic point generation as "
            f"one small sequential round; family {family} and target count {target_count} are supplied planning "
            f"inputs, the round is bounded by the declared bench capacity ({bench_slots} position(s) for the next "
            "round), and no DOE point or statistical-sufficiency conclusion is established."),
        "decision": "GO" if ready else "HOLD",
        "next_action": (
            f"Hand {design_id} to the Phase 4 deterministic engine for one small sequential round without adding "
            "DOE points; size the round to the registered bench capacity."
            if ready else
            "Retain supplied evidence and resolve the recorded design-request gap before any Phase 4 handoff."),
    }
