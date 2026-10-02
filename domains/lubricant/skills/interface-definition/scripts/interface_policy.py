"""Deterministic interface-definition policy: the fail-closed compatibility rules.

One interface record binds two counterparts (optionally with a coating system)
to per-condition compatibility observations and a controlled verdict
(PASS / FAIL / INCONCLUSIVE / GAP). The verdict is fail-closed, mirroring
application_policy: a PASS is only admissible when the compatibility evidence
is non-empty, every observation is OBSERVED with a PASS result, and the record
evidence carries no GAP. An empty evidence list forces `verdict = "GAP"`; a
verdict of FAIL / INCONCLUSIVE is a legitimate recorded outcome and is never
upgraded here. The external dependency (DLC coating parameters, supplier
batches) is handled by declaration: the optional `coating` object is either
fully present with provenance or omitted entirely.

This module also owns the COMPATIBILITY_PASSED link (WP-09): a design_freeze
freeze condition `COMPATIBILITY_PASSED` must cite the interface artifact as
`INTERFACE:<interface_id>`, the cited artifact must exist, and its verdict
must be PASS — no compatibility evidence, no satisfied freeze condition.
"""

from __future__ import annotations

import math

INPUT_FIELDS = {
    "interface_id", "project_reference", "interface_type",
    "counterpart_a", "counterpart_b", "coating",
    "compatibility_evidence", "verdict", "source", "evidence_id",
    "evidence_scope", "evidence",
}
ARTIFACT_FIELDS = (
    "interface_id", "project_reference", "interface_type",
    "counterpart_a", "counterpart_b", "coating",
    "compatibility_evidence", "verdict",
)
ALLOWED_FIELDS = INPUT_FIELDS | {"interface_reference"}
VERDICTS = ("PASS", "FAIL", "INCONCLUSIVE", "GAP")
EVIDENCE_SCOPES = ("SYNTHETIC", "PHYSICAL")
INTERFACE_TYPES = ("COATING_SUBSTRATE", "LUBRICANT_SURFACE", "MATERIAL_PAIR")
ROLES = ("COATING", "SUBSTRATE", "LUBRICANT", "COUNTERFACE", "SEAL", "OTHER")
COMPATIBILITY_REFERENCE_PREFIX = "INTERFACE:"
COMPATIBILITY_CONDITION_ID = "COMPATIBILITY_PASSED"


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def has_gap(record: dict) -> bool:
    evidence = record.get("evidence")
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("status") == "GAP" for item in evidence
    )


def counterpart_errors(counterpart: object, label: str) -> list[str]:
    if not isinstance(counterpart, dict) or not set(counterpart) <= {"role", "designation", "material_reference", "supplier", "supplier_batch_reference", "source"}:
        return [label]
    errors: list[str] = []
    if counterpart.get("role") not in ROLES:
        errors.append(f"{label}.role")
    if not has_text(counterpart.get("designation")):
        errors.append(f"{label}.designation")
    if not has_text(counterpart.get("source")):
        errors.append(f"{label}.source")
    return errors


def coating_errors(coating: object) -> list[str]:
    if coating is None:
        return []
    if not isinstance(coating, dict) or not set(coating) <= {"coating_system", "coating_reference", "deposition_process", "supplier", "supplier_batch_reference", "thickness_um", "surface_hardness", "hardness_unit", "source"}:
        return ["interface.coating"]
    errors: list[str] = []
    for field in ("coating_system", "coating_reference", "supplier", "supplier_batch_reference", "source"):
        if not has_text(coating.get(field)):
            errors.append(f"interface.coating.{field}")
    for field in ("thickness_um", "surface_hardness"):
        if field in coating and not is_finite_number(coating.get(field)):
            errors.append(f"interface.coating.{field} must be a positive number")
    if "surface_hardness" in coating and not has_text(coating.get("hardness_unit")):
        errors.append("interface.coating.hardness_unit must accompany surface_hardness")
    return errors


def compatibility_errors(items: object) -> list[str]:
    if not isinstance(items, list):
        return ["interface.compatibility_evidence"]
    errors: list[str] = []
    for index, item in enumerate(items):
        label = f"interface.compatibility_evidence[{index}]"
        if not isinstance(item, dict) or not set(item) <= {"compatibility_id", "method_reference", "condition", "result", "evidence_id", "status"}:
            errors.append(label)
            continue
        for field in ("compatibility_id", "method_reference", "condition", "evidence_id"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("result") not in VERDICTS:
            errors.append(f"{label}.result")
        if item.get("status") not in {"OBSERVED", "ASSUMED", "GAP"}:
            errors.append(f"{label}.status")
    return errors


def pass_blockers(interface: dict) -> list[str]:
    """Every reason a PASS verdict is not yet justified. Empty list = PASS allowed."""
    reasons: list[str] = []
    items = interface.get("compatibility_evidence")
    if not isinstance(items, list) or not items:
        reasons.append("compatibility_evidence must be a non-empty array to claim PASS")
    else:
        for index, item in enumerate(items):
            label = f"compatibility_evidence[{index}]"
            if not isinstance(item, dict):
                reasons.append(f"{label} is not an object")
                continue
            if item.get("result") != "PASS":
                reasons.append(f"{label}.result must be PASS to claim PASS (a FAIL/INCONCLUSIVE/GAP observation blocks PASS)")
            if item.get("status") != "OBSERVED":
                reasons.append(f"{label}.status must be OBSERVED to claim PASS (ASSUMED/GAP observations block PASS)")
    if has_gap(interface):
        reasons.append("interface.evidence contains GAP; a PASS verdict is not allowed")
    return reasons


def expected_decision_fields(interface: dict) -> dict[str, str]:
    interface_id = interface.get("interface_id", "")
    passed = interface.get("verdict") == "PASS"
    return {
        "decision_question": f"Does the supplied evidence justify compatibility for interface {interface_id}?",
        "hypothesis": f"{interface_id} records its counterparts, optional coating system, and per-condition compatibility observations.",
        "uncertainty": "Supplied observations are not independently verified; recorded ASSUMED evidence remains assumed and this record does not by itself establish a release or life conclusion.",
        "decision_rule": "Record the supplied verdict as-is; a PASS is only admissible with non-empty all-OBSERVED all-PASS compatibility evidence and no GAP evidence. design_freeze may cite this record as COMPATIBILITY_PASSED evidence only when the verdict is PASS.",
        "result": f"{interface_id} is {'supported' if passed else 'not supported'} by the supplied compatibility evidence.",
        "decision": "GO" if passed else "HOLD",
        "next_action": f"Retain {interface_id} as an interface record with verdict {interface.get('verdict')}." if passed else "Retain the supplied evidence and resolve the recorded blockers before citing this interface in a design freeze.",
    }


def interface_reference(interface_id: object) -> str:
    """The canonical design_freeze citation form for one interface artifact."""
    return f"{COMPATIBILITY_REFERENCE_PREFIX}{interface_id}"


def freeze_compatibility_errors(condition: object, interfaces: dict[str, dict]) -> list[str]:
    """Validate one design_freeze freeze condition against the interface contract.

    Only the COMPATIBILITY_PASSED condition is governed here; every other
    condition is returned clean. `interfaces` maps interface_id -> built
    interface artifact (or an empty dict to express "no interfaces supplied").
    """
    if not isinstance(condition, dict) or condition.get("condition_id") != COMPATIBILITY_CONDITION_ID:
        return []
    reference = condition.get("evidence_reference")
    if not has_text(reference) or not reference.startswith(COMPATIBILITY_REFERENCE_PREFIX):
        return [f"{COMPATIBILITY_CONDITION_ID} must cite an interface artifact as {COMPATIBILITY_REFERENCE_PREFIX}<interface_id>; got {reference!r}"]
    interface_id = reference[len(COMPATIBILITY_REFERENCE_PREFIX):]
    interface = interfaces.get(interface_id)
    if interface is None:
        return [f"{COMPATIBILITY_CONDITION_ID} cites unknown interface {interface_id}; the interface artifact must exist and be supplied"]
    verdict = interface.get("verdict")
    if verdict != "PASS":
        blockers = pass_blockers(interface) if isinstance(interface, dict) else ["the record is not an interface artifact"]
        return [
            f"{COMPATIBILITY_CONDITION_ID} cites interface {interface_id} whose verdict is {verdict!r}; "
            "compatibility evidence must support PASS before the freeze condition can be satisfied"
        ] + [f"interface {interface_id}: {blocker}" for blocker in blockers]
    return []
