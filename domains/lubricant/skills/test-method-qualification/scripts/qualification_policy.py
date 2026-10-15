"""Deterministic Stage 3 qualification decision policy shared by builder and validator.

The grease route (PRECISION_GREASE_DEV, outer-loop step 5) adds three rules that
the six oil routes do not have today. They are gated on the upstream
``project_type`` so the oil routes keep their current behaviour byte-for-byte:

1. ``REPEATABILITY`` is required for EVERY role, not only D and P. A method whose
   repeatability was never established cannot support any claim: you do not know
   whether a difference you measured is a difference in the sample or in the
   stand.

2. The three qualification sub-steps are SERIAL, not parallel. Order is enforced
   as a state machine: discrimination may not be recorded while repeatability has
   not passed, and the independent new batch check may not be recorded while
   discrimination has not passed. Verification on the same batch that built the
   result is not verification.

3. Repeatability and discrimination values must be ENGINE-computed, and the
   independent new batch check must be PASS. Before a method can predict the
   bench, any optimisation algorithm only optimises the wrong target faster: a
   hand-entered discrimination figure is a declaration, not a measurement.
"""

from __future__ import annotations


ROLES = {"C", "D", "P"}
METRICS = {"REPEATABILITY", "DISCRIMINATION", "SENSITIVITY", "MECHANISM_RELEVANCE", "BENCHMARK_RANKING", "FIELD_RELEVANCE", "COST", "DURATION"}
QUALIFICATION_STATUSES = {"PENDING", "QUALIFIED", "NOT_QUALIFIED"}

# The project type whose route carries the new mandatory qualification rules.
GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"

# The three qualification sub-steps, in their required order. Each element is
# (pipeline key, the metric it computes, the human name used in error text).
PIPELINE_STEPS = (
    ("repeatability", "REPEATABILITY", "repeatability"),
    ("discrimination", "DISCRIMINATION", "discrimination"),
    ("independent_batch", None, "independent new batch check"),
)

# Sub-statuses that mean "this sub-step has not passed".
PIPELINE_PASS = "PASS"


def is_grease_route(project_type: object) -> bool:
    """True when the supplied upstream project type carries the grease rules.

    An absent or unknown project type is NOT the grease route, so every caller
    that cannot determine the route keeps exactly the pre-change behaviour.
    """
    return project_type == GREASE_PROJECT_TYPE


def metric_names(method: dict) -> set[str]:
    metrics = method.get("qualification_metrics")
    return {item.get("metric") for item in metrics if isinstance(item, dict) and isinstance(item.get("metric"), str)} if isinstance(metrics, list) else set()


def metric_entries(method: dict) -> dict[str, dict]:
    """Map each declared metric name to its entry (first entry wins on duplicates)."""
    metrics = method.get("qualification_metrics")
    entries: dict[str, dict] = {}
    if not isinstance(metrics, list):
        return entries
    for item in metrics:
        if isinstance(item, dict) and isinstance(item.get("metric"), str):
            entries.setdefault(item["metric"], item)
    return entries


def role_metric_errors(method: dict, project_type: object = None) -> list[str]:
    """Role/metric completeness errors.

    With ``project_type`` absent or non-grease this is exactly the pre-change
    rule: role D requires DISCRIMINATION and role P requires MECHANISM_RELEVANCE
    plus FIELD_RELEVANCE or BENCHMARK_RANKING. On the grease route it
    additionally requires REPEATABILITY for every declared role.
    """
    roles, metrics = method.get("role"), metric_names(method)
    if not isinstance(roles, list) or any(role not in ROLES for role in roles):
        return ["role is invalid"]
    errors = []
    if "D" in roles and "DISCRIMINATION" not in metrics:
        errors.append("role D requires DISCRIMINATION")
    if "P" in roles:
        if "MECHANISM_RELEVANCE" not in metrics:
            errors.append("role P requires MECHANISM_RELEVANCE")
        if not ({"FIELD_RELEVANCE", "BENCHMARK_RANKING"} & metrics):
            errors.append("role P requires FIELD_RELEVANCE or BENCHMARK_RANKING")
    if is_grease_route(project_type) and "REPEATABILITY" not in metrics:
        # Every role, not just D and P: without repeatability a measured
        # difference cannot be attributed to the sample rather than the stand.
        for role in sorted(roles):
            errors.append(f"role {role} requires REPEATABILITY")
    return errors


def _substep(method: dict, key: str) -> dict | None:
    pipeline = method.get("qualification_pipeline")
    if not isinstance(pipeline, dict):
        return None
    step = pipeline.get(key)
    return step if isinstance(step, dict) else None


def _substep_status(method: dict, key: str) -> object:
    step = _substep(method, key)
    return step.get("status") if isinstance(step, dict) else None


def _substep_computed_by(method: dict, key: str) -> object:
    step = _substep(method, key)
    return step.get("computed_by") if isinstance(step, dict) else None


def pipeline_errors(method: dict) -> list[str]:
    """Serial-order and engine-computation errors for the three sub-steps.

    Enforced on the grease route only (the caller gates it). The order is a
    state machine: a later sub-step without its predecessor passing is a
    pipeline gap, not a stronger submission.
    """
    errors: list[str] = []
    pipeline = method.get("qualification_pipeline")
    if not isinstance(pipeline, dict) or not pipeline:
        return [
            "qualification_pipeline is required on the PRECISION_GREASE_DEV route: "
            "repeatability, discrimination and the independent new batch check are serial, not parallel"
        ]
    repeatability = _substep_status(method, "repeatability")
    discrimination = _substep_status(method, "discrimination")
    independent_batch = _substep_status(method, "independent_batch")

    if repeatability is None:
        errors.append("qualification_pipeline.repeatability.status is required: repeatability comes first")
    if "discrimination" in pipeline and repeatability != PIPELINE_PASS:
        # N3: a discrimination result recorded on top of an unpassed repeatability
        # step has no established measurement noise behind it.
        errors.append("repeatability must pass before discrimination")
    if "independent_batch" in pipeline and discrimination is None:
        errors.append("discrimination must be recorded before an independent new batch check")
    elif "independent_batch" in pipeline and discrimination != PIPELINE_PASS:
        errors.append("discrimination must pass before the independent new batch check")
    if "independent_batch" in pipeline and independent_batch != PIPELINE_PASS:
        # Re-verification on a fresh batch is the only check that a result is not
        # an artefact of the batch that produced it, so it may not be skipped.
        errors.append("independent_batch must be PASS: a result verified on the batch that produced it is not verified")
    return errors


def engine_computation_errors(method: dict) -> list[str]:
    """Engine-computation errors for the computable metrics and sub-steps.

    Enforced on the grease route only (the caller gates it). Repeatability and
    discrimination are the two metrics an optimisation later relies on, so a
    hand-entered value for either is refused: before a method can predict the
    bench, any optimisation algorithm only optimises the wrong target faster.
    """
    errors: list[str] = []
    entries = metric_entries(method)
    for key, metric, name in PIPELINE_STEPS:
        if metric is None or metric not in entries:
            continue
        # N4: a MANUAL discrimination figure is a declaration, not a measurement.
        # The metric entry and the pipeline sub-step are two records of the same
        # computation, so a value that is not ENGINE-computed is reported once.
        if entries[metric].get("computed_by") != "ENGINE" or _substep_computed_by(method, key) not in (None, "ENGINE"):
            errors.append(f"{name} must be computed by the engine")
    return errors


def grease_qualification_errors(method: dict) -> list[str]:
    """Every grease-only mandatory qualification check, in one place."""
    return [*pipeline_errors(method), *engine_computation_errors(method)]


def go_qualification_errors(method: dict, project_type: object = None) -> list[str]:
    errors = role_metric_errors(method, project_type)
    if is_grease_route(project_type):
        errors.extend(grease_qualification_errors(method))
    if method.get("qualification_status") != "QUALIFIED":
        errors.append("qualification_status is not QUALIFIED")
    if method.get("evidence_scope") != "PHYSICAL":
        errors.append("qualification requires PHYSICAL evidence_scope; source declaration alone is not approval")
    if not isinstance(method.get("qualification_basis"), list) or not method["qualification_basis"]:
        errors.append("qualification_basis is empty")
    evidence = method.get("evidence")
    if not isinstance(evidence, list) or not any(isinstance(item, dict) and item.get("status") == "OBSERVED" for item in evidence):
        errors.append("OBSERVED qualification evidence is missing")
    return errors


def required_fields_for(project_type: object) -> tuple[str, ...]:
    """Fields a grease-route input must supply beyond the shared contract."""
    if is_grease_route(project_type):
        return ("qualification_pipeline", "reference_material_reference")
    return ()


def expected_decision_fields(method: dict, project_type: object = None) -> dict[str, str]:
    method_id, name = method.get("method_id", ""), method.get("name", "")
    role_text = "/".join(method.get("role", [])) if isinstance(method.get("role"), list) else ""
    qualified = not go_qualification_errors(method, project_type)
    if is_grease_route(project_type):
        rule = (
            "Qualify only when every role carries REPEATABILITY and DISCRIMINATION, the "
            "repeatability -> discrimination -> independent new batch pipeline is serial and passed, "
            "repeatability and discrimination are ENGINE-computed, and OBSERVED evidence, "
            "qualification basis, and PHYSICAL evidence scope are complete; PHYSICAL is a source "
            "declaration, not approval."
        )
    else:
        rule = f"Qualify only when {role_text} role metrics, OBSERVED evidence, qualification basis, and PHYSICAL evidence scope are complete; PHYSICAL is a source declaration, not approval."
    return {
        "decision_question": f"Is {method_id} ({name}) qualified to measure the target failure/CTQ?",
        "hypothesis": f"{method_id} can provide role-bound measurement evidence for the target failure/CTQ.",
        "uncertainty": "This qualification uses supplied standard/method provenance; its authenticity and validity are not independently verified, and it does not prove product risk, field prediction, or product performance.",
        "decision_rule": rule,
        "result": f"{method_id} is {'qualified' if qualified else 'not qualified'} for its recorded roles to measure the target failure/CTQ from supplied provenance and evidence only.",
        "decision": "GO" if qualified else "HOLD",
        "next_action": f"Register {method_id} as an eligible response for later design and retain the Evidence Stack." if qualified else "Retain the Evidence Stack and close the recorded qualification gaps.",
    }
