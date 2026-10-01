"""Deterministic process-definition decision policy shared by builder and validator."""

from __future__ import annotations


def has_gap(process: dict) -> bool:
    evidence = process.get("evidence")
    return isinstance(evidence, list) and any(isinstance(item, dict) and item.get("status") == "GAP" for item in evidence)


def expected_decision_fields(process: dict) -> dict[str, str]:
    process_id = process.get("process_id", "")
    ready = not has_gap(process)
    return {
        "decision_question": f"Is the supplied input sufficient to define process {process_id}?",
        "hypothesis": f"{process_id} records process steps, parameter bounds with provenance, scale, window, and control points sufficient for later process testing.",
        "uncertainty": "Supplied process bounds, sources, and provenance are not independently verified; recorded ASSUMED evidence remains assumed and this record does not establish a validated process window, capability, scale-up, or performance conclusion.",
        "decision_rule": "Define the process only when upstream design space, step parameters with source and evidence_id, scale, window, control points, and evidence without GAP are supplied.",
        "result": f"{process_id} is {'sufficient' if ready else 'not sufficient'} to define a process record from supplied input only.",
        "decision": "GO" if ready else "HOLD",
        "next_action": f"Retain {process_id} as the supplied process record." if ready else "Retain the supplied evidence and resolve the recorded GAP before defining a process.",
    }
