"""Deterministic Stage 4 design-space decision policy shared by builder and validator."""

from __future__ import annotations


def has_gap(design_space: dict) -> bool:
    evidence = design_space.get("evidence")
    return isinstance(evidence, list) and any(isinstance(item, dict) and item.get("status") == "GAP" for item in evidence)


def expected_decision_fields(design_space: dict) -> dict[str, str]:
    design_space_id = design_space.get("design_space_id", "")
    ready = not has_gap(design_space)
    return {
        "decision_question": f"Is the supplied input sufficient to define testable design space {design_space_id}?",
        "hypothesis": f"{design_space_id} records supplied variables, bounds, constraints, CTQ links, and qualified-method links sufficient for later testing.",
        "uncertainty": "Supplied bounds, constraints, sources, and provenance are not independently verified; recorded ASSUMED evidence remains assumed and this record does not establish formula, experiment, performance, cost, or optimization conclusions.",
        "decision_rule": "Define the design space only when upstream links, complete bound metadata, ordered same-unit bounds, constraints, and evidence without GAP are supplied.",
        "result": f"{design_space_id} is {'sufficient' if ready else 'not sufficient'} to define a testable design space from supplied input only.",
        "decision": "GO" if ready else "HOLD",
        "next_action": f"Retain {design_space_id} as the supplied design-space record." if ready else "Retain the supplied evidence and resolve the recorded GAP before defining a design space.",
    }
