"""Deterministic failure/CTQ policy gated on the project type.

Why this module exists
----------------------
``schemas/failure_ctq.schema.json`` is a shared contract, so ``criteria_layer`` was added
as an OPTIONAL string property rather than to ``required`` (pure-increment rule). The grease
route therefore gets its enforcement here, in the skill policy layer:

* ``PRECISION_GREASE_DEV`` -> every CTQ must declare ``criteria_layer`` in
  {``SCREENING``, ``BENCH``, ``MACHINE``}: the three-layer criteria chain of the refactor
  plan §3 step 3 (physicochemical screening criteria -> bench criteria -> whole-machine
  criteria). A CTQ whose layer is undeclared cannot be routed to the right gate.
* The diagnosis chain is enforced for that route: Failure Diagnosis -> Root-Cause
  Hypothesis -> Lubricant Contribution. A record may not jump from an observed symptom
  ("bearing wear") straight to a lubricant cause ("insufficient anti-wear additive"): the
  diagnosis step must describe the physical/tribological state, and the lubricant linkage
  belongs one link later, in the hypotheses and then the contribution.
* Failure modes must be harmonic-drive specific: micro-pitting, fretting wear, grease
  hardening and oil-bleed starvation. The policy requires at least one of those four mode
  families across ``failure_mode`` + ``mechanism``, so an oil-shaped mode set (foam,
  demulsibility, sump oxidation) cannot be carried into the grease route.
* any of the six oil project types -> no criteria-layer requirement, no harmonic-drive mode
  requirement, no extra chain grammar. Every oil code path is identical to before.
"""

from __future__ import annotations

PRECISION_GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"

LEGACY_PROJECT_TYPES = (
    "NEW_PRODUCT",
    "IMPROVEMENT",
    "COST_DOWN",
    "CUSTOMIZATION",
    "EXPLORATION",
    "PROCESS_ROBUSTNESS",
)

CRITERIA_LAYERS = ("SCREENING", "BENCH", "MACHINE")

# The harmonic-drive failure-mode families the plan names (§4.2.1 item 1-16).
GREASE_FAILURE_MODES = (
    "MICRO_PITTING",
    "FRETTING_WEAR",
    "GREASE_HARDENING",
    "OIL_BLEED_STARVATION",
)

# Wording each family may be recognised by; hyphen/space/case variants all normalize to the
# same token, so "micro-pitting", "Micro Pitting" and "MICROPITTING" all match.
GREASE_FAILURE_MODE_MARKERS = {
    "MICRO_PITTING": ("MICROPITTING", "MICRO PITTING", "MICRO-PITTING", "微点蚀"),
    "FRETTING_WEAR": ("FRETTING", "MICRO-MOTION WEAR", "微振磨损", "微动磨损"),
    "GREASE_HARDENING": ("GREASE HARDENING", "HARDENING", "硬化", "稠化剂老化"),
    "OIL_BLEED_STARVATION": ("OIL BLEED", "OIL-BLEED", "BLEED STARVATION", "析油", "基础油析出"),
}

# Phrases that name a LUBRICANT CAUSE. They belong after the hypotheses, in
# ``lubricant_contribution`` - never in ``failure_diagnosis``, which records the physical
# state. A diagnosis built from these is exactly the forbidden shortcut from "bearing wear"
# to "insufficient anti-wear additive". Matched case-insensitively.
LUBRICANT_CAUSE_MARKERS = (
    "anti-wear additive", "antiwear additive", "anti wear additive",
    "extreme pressure additive", "ep additive", "antioxidant",
    "additive package", "additive treat rate", "base oil viscosity",
    "thickener content", "thickener concentration",
    "抗磨剂", "极压剂", "抗氧化剂", "添加剂", "基础油粘度", "稠化剂含量",
)

UNCERTAINTY_MARKERS = (
    "may", "possible", "potential", "hypothesis", "pending", "to be verified",
    "可能", "待验证", "尚待", "假设", "潜在", "需验证", "未证实",
)


def has_text(value: object) -> bool:
    """True for a non-empty, non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def is_precision_grease(project_type: object) -> bool:
    """True only for the precision-gear grease route. An unknown type is not grease."""
    return project_type == PRECISION_GREASE_PROJECT_TYPE


def resolved_project_type(project_artifact: object, failure_ctq: object) -> object:
    """The project type to enforce for this input, or None when it is not determinable.

    An explicit upstream project charter wins. Without one, a failure record whose CTQs
    already declare ``criteria_layer`` is grease-shaped: only this policy writes that field,
    so its presence can only ever ADD enforcement over an input that already opted in. An
    oil record (no layer declared) resolves to None and keeps its previous behaviour.
    """
    if isinstance(project_artifact, dict) and has_text(project_artifact.get("project_type")):
        return project_artifact["project_type"]
    ctqs = failure_ctq.get("ctqs") if isinstance(failure_ctq, dict) else None
    if isinstance(ctqs, list) and any(
        isinstance(ctq, dict) and "criteria_layer" in ctq for ctq in ctqs
    ):
        return PRECISION_GREASE_PROJECT_TYPE
    return None


def criteria_layer_errors(ctqs: object, project_type: object) -> list[str]:
    """Every CTQ of the grease route must declare a valid ``criteria_layer``.

    Oil routes are untouched: no errors, so the field stays optional in the shared contract
    and oil fixtures keep validating.
    """
    if not is_precision_grease(project_type) or not isinstance(ctqs, list):
        return []
    errors: list[str] = []
    for index, ctq in enumerate(ctqs):
        if not isinstance(ctq, dict):
            continue
        label = f"failure_ctq.ctqs[{index}]"
        layer = ctq.get("criteria_layer")
        if not has_text(layer):
            errors.append(
                f"{label}.criteria_layer is required for {PRECISION_GREASE_PROJECT_TYPE}: "
                "every CTQ must declare which layer of the three-layer criteria chain "
                f"({', '.join(CRITERIA_LAYERS)}) it belongs to"
            )
        elif layer not in CRITERIA_LAYERS:
            errors.append(f"{label}.criteria_layer must be one of {', '.join(CRITERIA_LAYERS)}")
    return errors


def normalized(value: object) -> str:
    """Uppercase, collapse every non-alphanumeric run to one space (keeps CJK runs)."""
    if not isinstance(value, str):
        return ""
    out: list[str] = []
    for character in value.upper():
        if character.isalnum():
            out.append(character)
        elif out and out[-1] != " ":
            out.append(" ")
    return "".join(out).strip()


def named_failure_modes(failure_mode: object, mechanism: object) -> list[str]:
    """Which harmonic-drive mode families the recorded text names."""
    haystack = f"{normalized(failure_mode)} {normalized(mechanism)}"
    found: list[str] = []
    for family, markers in GREASE_FAILURE_MODE_MARKERS.items():
        for marker in markers:
            token = normalized(marker)
            if token and token in haystack:
                found.append(family)
                break
    return found


def failure_mode_errors(failure_mode: object, mechanism: object, project_type: object) -> list[str]:
    """The grease route requires a harmonic-drive-specific failure mode.

    Positive check only (one of the four named families must be present); it never
    blacklists a word, so a record may use any prose as long as it names a harmonic-drive
    gear-grease mechanism. Oil routes are untouched.
    """
    if not is_precision_grease(project_type):
        return []
    if named_failure_modes(failure_mode, mechanism):
        return []
    return [
        "failure_ctq.failure_mode must name a harmonic-drive grease failure mode "
        f"({', '.join(GREASE_FAILURE_MODES)}): micro-pitting, fretting wear, grease hardening, "
        "or oil-bleed starvation"
    ]


def diagnosis_chain_errors(failure_ctq: object, project_type: object) -> list[str]:
    """The no-shortcut diagnosis chain, enforced for the grease route only.

    Chain: Failure Diagnosis -> Root-Cause Hypothesis -> Lubricant Contribution. Three
    shortcuts are rejected:

    * no diagnosis step recorded at all;
    * the diagnosis is a verbatim restatement of ``failure_mode`` or ``mechanism``, i.e. the
      step was skipped rather than written;
    * the diagnosis names a lubricant cause (an additive, a base-oil property, a thickener
      quantity). That is the forbidden jump: the lubricant linkage belongs one link later,
      and a diagnosis that IS the lubricant cause leaves nothing for the hypotheses to test.

    Oil routes: no extra error, exactly the pre-existing grammar.
    """
    if not is_precision_grease(project_type) or not isinstance(failure_ctq, dict):
        return []
    errors: list[str] = []
    diagnosis = failure_ctq.get("failure_diagnosis")
    mechanism = failure_ctq.get("mechanism")
    failure_mode = failure_ctq.get("failure_mode")
    if not has_text(diagnosis):
        errors.append(
            "failure_ctq.failure_diagnosis must record the diagnosis step between the observed "
            "failure and its hypotheses; an observed symptom may not jump straight to a lubricant cause"
        )
    else:
        if normalized(diagnosis) in {normalized(failure_mode), normalized(mechanism)}:
            errors.append(
                "failure_ctq.failure_diagnosis must add the diagnosis step, not restate the failure "
                "mode or the mechanism; the chain is Failure Diagnosis -> Root-Cause Hypothesis -> "
                "Lubricant Contribution"
            )
        if any(marker in diagnosis.casefold() for marker in LUBRICANT_CAUSE_MARKERS):
            errors.append(
                "failure_ctq.failure_diagnosis must not name a lubricant cause: record the physical "
                "or tribological state here and keep the lubricant linkage in "
                "root_cause_hypotheses -> lubricant_contribution"
            )
    hypotheses = failure_ctq.get("root_cause_hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses or not all(has_text(item) for item in hypotheses):
        errors.append(
            "failure_ctq.root_cause_hypotheses must record at least one hypothesis between the "
            "diagnosis and the lubricant contribution"
        )
    contribution = failure_ctq.get("lubricant_contribution")
    if not has_text(contribution):
        errors.append("failure_ctq.lubricant_contribution must record the last link of the chain")
    elif not any(marker in contribution.casefold() for marker in UNCERTAINTY_MARKERS):
        errors.append(
            "failure_ctq.lubricant_contribution must stay a pending-verification statement, not a "
            "confirmed lubricant cause"
        )
    return errors


def policy_errors(failure_ctq: object, project_type: object) -> list[str]:
    """The full grease-route policy verdict for one failure/CTQ record."""
    if not is_precision_grease(project_type) or not isinstance(failure_ctq, dict):
        return []
    return (
        criteria_layer_errors(failure_ctq.get("ctqs"), project_type)
        + failure_mode_errors(failure_ctq.get("failure_mode"), failure_ctq.get("mechanism"), project_type)
        + diagnosis_chain_errors(failure_ctq, project_type)
    )
