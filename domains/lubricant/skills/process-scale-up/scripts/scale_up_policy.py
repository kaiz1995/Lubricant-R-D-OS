"""Deterministic process-window scale-up decision policy shared by builder and validator.

Two contracts live here.

1. THE ON-DEMAND WINDOW (frozen). ``PROCESS_WINDOW_DEFINED`` fixes a manufacturing window
   from a DESIGN_SPACE_DEFINED process record and an OPTIMIZED conclusion. Its semantics are
   frozen: nothing in this module changes them, and a request that does not declare the
   precision-grease route keeps exactly the behaviour it had.

2. ``validated: true`` MEANS "THE WINDOW HAS BEEN FIXED" - NOT "A SCALE-UP EXPERIMENT
   VERIFIED IT" (handoff doc section 5.2 item 6). The field is set by the builder and can
   never be claimed by the caller: it records that the window is the fixed conclusion this
   artifact hands downstream. On the precision-grease route the skill therefore also
   requires at least one OBSERVED evidence item before it will fix a window, because a
   window claim with nothing but assumed evidence is exactly the ambiguity this note
   exists to prevent. The stage on that route is ``PROCESS_SCALE_VALIDATED`` (the route's
   own step-15 stage); the on-demand ``PROCESS_WINDOW_DEFINED`` stage is untouched.
"""

from __future__ import annotations


# LAB -> PILOT -> PRODUCTION: a scale-up step must move strictly forward.
SCALE_ORDER = {"LAB": 0, "PILOT": 1, "PRODUCTION": 2}

GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"
ON_DEMAND_STAGE = "PROCESS_WINDOW_DEFINED"
GREASE_STAGE = "PROCESS_SCALE_VALIDATED"

# The grease route's own process items, mirrored from schemas/process.schema.json.
# SAPONIFICATION is the step that generates the soap in situ, so a fixed grease window
# that never covers it is not a fixed grease window; the other grease-specific steps are
# reported as NOTE lines when absent and are never invented.
GREASE_STEP_TYPES = (
    "SAPONIFICATION",
    "DEHYDRATION",
    "PHASE_INVERSION",
    "DILUTION_COOLING",
    "MILLING",
    "HOMOGENIZATION",
    "VACUUM_DEAERATION",
    "FILLING",
    "SOAP_HOLD",
    "DILUTION_CURVE",
    "RIPENING",
    "FILLING_TEMPERATURE",
)
GREASE_SPECIFIC_STEP_TYPES = ("SOAP_HOLD", "DILUTION_CURVE", "RIPENING", "FILLING_TEMPERATURE")
REQUIRED_GREASE_STEP_TYPES = ("SAPONIFICATION",)


def grease_route(project: object) -> bool:
    """True when the supplied charter routes this request onto the precision-grease route."""
    return isinstance(project, dict) and project.get("project_type") == GREASE_PROJECT_TYPE


def window_stage(grease: bool) -> str:
    """The stage the fixed window lands at: the route's own stage on grease, the frozen one otherwise."""
    return GREASE_STAGE if grease else ON_DEMAND_STAGE


def window_evidence_reference(window_id: str) -> str:
    """The reference a design_freeze MANUFACTURABILITY_ACCEPTABLE condition must cite.

    The citation is the link between the freeze and the fixed window: the condition must
    read exactly ``PROCESS-WINDOW:<window_id>``, never a free-form record.
    """
    return f"PROCESS-WINDOW:{window_id}"


def has_gap(container: dict) -> bool:
    evidence = container.get("evidence")
    return isinstance(evidence, list) and any(isinstance(item, dict) and item.get("status") == "GAP" for item in evidence)


def has_observed_evidence(container: dict) -> bool:
    evidence = container.get("evidence")
    return isinstance(evidence, list) and any(isinstance(item, dict) and item.get("status") == "OBSERVED" for item in evidence)


def grease_step_notes(process: object) -> list[str]:
    """Audible NOTE lines for grease-specific steps the fixed window does not cover."""
    if not isinstance(process, dict):
        return []
    steps = process.get("process_step")
    if not isinstance(steps, list):
        return []
    recorded = {step.get("step_type") for step in steps if isinstance(step, dict)}
    absent = [step_type for step_type in GREASE_SPECIFIC_STEP_TYPES if step_type not in recorded]
    if not absent:
        return []
    return [
        "NOTE: the fixed window does not cover "
        + ", ".join(absent)
        + "; an uncovered step stays uncovered and is never invented into the window"
    ]


def expected_decision_fields(process_id: str, window_id: str, ready: bool, grease: bool = False) -> dict[str, str]:
    fields = {
        "decision_question": f"Is process {process_id} window {window_id} fixed from the OPTIMIZED conclusion?",
        "hypothesis": f"{window_id} fixes the manufacturing window of {process_id} at the amplified batch scale, carrying the OPTIMIZED conclusion into a validated process window.",
        "uncertainty": "The fixed window rests on the supplied scale-up evidence only; it does not by itself establish capability, release approval, or product performance.",
        "decision_rule": "Fix the process window only when the DESIGN_SPACE_DEFINED process record and the OPTIMIZED conclusion share a project, the scale step advances to a later scale class, and evidence without GAP is supplied.",
        "result": f"{window_id} is {'fixed' if ready else 'not fixed'} for {process_id} from supplied input only.",
        "decision": "GO" if ready else "HOLD",
        "next_action": f"Retain {window_id} as the fixed process window and cite it from the design freeze." if ready else "Retain the supplied evidence and resolve the recorded GAP before fixing a process window.",
    }
    if not grease:
        return fields
    # Stated explicitly, because the field name is ambiguous on its own: validated=true
    # means the window has been FIXED, not that a scale-up experiment verified it.
    return {
        **fields,
        "decision_question": f"Is process {process_id} window {window_id} fixed at the {GREASE_STAGE} stage?",
        "hypothesis": f"{window_id} fixes the manufacturing window of {process_id} at the amplified batch scale; validated=true records that the window has been FIXED, not that a scale-up experiment verified it.",
        "uncertainty": "The fixed window rests on the supplied scale-up evidence only; it does not by itself establish capability, release approval, or product performance, and validated=true is a fixing statement rather than an experiment-verification statement.",
        "decision_rule": "Fix the process window only when the DESIGN_SPACE_DEFINED process record and the NON_INFERIORITY_PASSED conclusion share a project, the scale step advances to a later scale class, the process record covers the grease route's structure-setting steps, at least one OBSERVED evidence item is supplied, and no GAP remains.",
        "result": f"{window_id} is {'fixed' if ready else 'not fixed'} for {process_id} from supplied input only; validated=true is carried as a fixed-window marker.",
        "next_action": f"Retain {window_id} as the fixed process window at {GREASE_STAGE} and cite it from the design freeze as {window_evidence_reference(window_id)}." if ready else "Retain the supplied evidence and resolve the recorded blockers before fixing a process window.",
    }
