"""Deterministic reference-material policy: the tier ladder and UNRESOLVED propagation.

A reference set is the discrimination ruler for a grease campaign: a Known Good that
must pass and a Known Bad that must fail. Method qualification (Stage 5) cannot prove
that a stand separates a good sample from a bad one unless both exist as PHYSICAL
objects, so this module decides - deterministically - which dossiers may be recorded
RESOLVED and what that means downstream. It is shared by preflight, builder and
validator so the three scripts cannot disagree about the same input.

Four rules, all fail-closed:

1. Resolution is DOWNGRADE-ONLY. A dossier is recorded RESOLVED only when the caller
   declares RESOLVED *and* the dossier's own records support it: material identity,
   formula identity, storage/preparation SOP and safety reference must all be present
   (an explicitly absent document stays absent, never filled in), a ladder rung must be
   claimed, and history_evidence must hold at least one well-formed item. A Known Bad
   must additionally bind at least one recorded failure to the mechanism it
   demonstrates. Anything short of that is recorded UNRESOLVED. An UNRESOLVED dossier
   is a legitimate record, not an error: better to admit there is no bad sample than to
   invent one.

2. A mechanism binding is STRUCTURAL, not prose. ``mechanism_reference`` must read
   ``<MECHANISM-ID>: <statement>`` with a concrete id. The no-mechanism markers
   (``MECHANISM-NONE`` and friends) are legitimate for a Known Good whose history
   records the *absence* of an event - there is no failure to bind - but they never
   establish a Known Bad: "high sulfur is generally bad" is a general statement, not
   evidence, and an unbound bad sample cannot discriminate a candidate.

3. The TIER LADDER. ``tier`` is the highest rung achieved by any RESOLVED dossier:
   ``DIRECT_HISTORY`` (a mature sample with a written bench/history record) over
   ``LONG_RUN_NO_EVENT`` (a sample with a 10 h no-event record) over ``UNRESOLVED``
   (nothing found). A set with no RESOLVED dossier is always UNRESOLVED.

4. UNRESOLVED PROPAGATES. ``downstream_flag`` carries the discrimination evidence:
   ``DISCRIMINATION_EVIDENCE_COMPLETE`` iff a Known Bad is RESOLVED, otherwise
   ``DISCRIMINATION_EVIDENCE_INCOMPLETE``. This mirrors the two ``if/then`` rules of
   ``schemas/reference.schema.json`` - the schema ties a RESOLVED Known Bad to COMPLETE
   and ``tier: UNRESOLVED`` to INCOMPLETE - and closes the remaining direction: this
   policy forces INCOMPLETE whenever no Known Bad is resolved, so the state cannot be
   papered over. Stage 5 reads the flag off this dossier and refuses to proceed when it
   is INCOMPLETE: a reference set with no RESOLVED Known Bad is exactly the
   no-Known-Bad case the discrimination ruler cannot be built from.

The release rule (放行判据): at least ONE side must be RESOLVED before Stage 5 may
proceed. ``decision`` is GO only when that rule is met and no artifact-level evidence
item carries status GAP; otherwise the artifact is still recorded, with decision HOLD,
because an UNRESOLVED reference set is a truthful record and the only remaining
recovery is more evidence - not a rewrite.
"""

from __future__ import annotations

import re

INPUT_FIELDS = {
    "project_artifact", "reference_id", "known_good", "known_bad",
    "evidence_scope", "evidence",
}
# Input-only dossier fields. `selection_rung` is the ladder rung the caller claims for
# that dossier; it is not an artifact field (schemas/reference.schema.json fixes the
# dossier shape), so the builder consumes it to derive `tier` and the achieved rung is
# reported in the deterministic decision block instead.
DOSSIER_INPUT_FIELDS = {
    "reference_id", "resolution", "selection_rung", "material_identity",
    "formula_identity", "history_evidence", "storage_sop", "safety_reference",
}
DOSSIER_ARTIFACT_FIELDS = (
    "reference_id", "resolution", "material_identity", "formula_identity",
    "history_evidence", "storage_sop", "safety_reference",
)
HISTORY_ITEM_FIELDS = {"evidence_reference", "mechanism_reference"}
EVIDENCE_FIELDS = {"evidence_id", "statement", "source", "status"}
EVIDENCE_STATUSES = {"OBSERVED", "ASSUMED", "GAP"}
EVIDENCE_SCOPES = {"SYNTHETIC", "PHYSICAL"}
SIDES = ("known_good", "known_bad")
RESOLVED = "RESOLVED"
UNRESOLVED = "UNRESOLVED"
RESOLUTIONS = (RESOLVED, UNRESOLVED)
# Ladder order, highest rung first: rung 1 (mature sample with a written record),
# rung 2 (10 h no-event record), rung 3 (nothing found -> tier UNRESOLVED).
RUNG_ORDER = ("DIRECT_HISTORY", "LONG_RUN_NO_EVENT")
TIERS = (*RUNG_ORDER, UNRESOLVED)
DOWNSTREAM_COMPLETE = "DISCRIMINATION_EVIDENCE_COMPLETE"
DOWNSTREAM_INCOMPLETE = "DISCRIMINATION_EVIDENCE_INCOMPLETE"
DOWNSTREAM_FLAGS = (DOWNSTREAM_COMPLETE, DOWNSTREAM_INCOMPLETE)

# A mechanism reference is a binding only when it names a concrete mechanism id.
# These markers deliberately mean "no mechanism is demonstrated": honest for a no-event
# Known Good history, useless for a Known Bad.
NO_MECHANISM_TOKENS = frozenset({
    "MECHANISM_NONE", "NONE", "NA", "NOT_APPLICABLE", "GENERAL", "GENERIC",
    "UNBOUND", "UNKNOWN", "TBD", "NO_MECHANISM",
})
# An explicitly absent document is recorded as absent; it is never a value that can
# support a RESOLVED claim. The caller writes one of these markers instead of a
# fabricated SOP number or safety sheet.
ABSENT_MARKERS = frozenset({
    "NOT_SUPPLIED", "NOT_AVAILABLE", "MISSING", "ABSENT", "UNKNOWN", "TBD",
    "NONE", "NA", "NOT_APPLICABLE", "UNVERIFIED", "NO_DOCUMENT",
})
MECHANISM_BINDING_RE = re.compile(r"^(?P<token>[A-Z][A-Z0-9_-]*)\s*:\s*(?P<statement>\S.*)$")
_NON_TOKEN_RE = re.compile(r"[^A-Z0-9]+")


def has_text(value: object) -> bool:
    """True for a non-empty, non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def _normalize(value: str) -> str:
    return _NON_TOKEN_RE.sub("_", value.strip().upper()).strip("_")


def is_absent(value: object) -> bool:
    """True when a document reference is explicitly recorded as not supplied.

    Matches when the whole record, or the portion after its last colon, is an absence
    marker (optionally with a trailing qualifier, e.g. ``MISSING_LOT``). Prose that
    merely quotes a real document does not match.
    """
    if not has_text(value):
        return True
    text = value.strip()
    candidates = [text]
    if ":" in text:
        tail = text.rsplit(":", 1)[1].strip()
        if tail:
            candidates.append(tail)
    for candidate in candidates:
        normalized = _normalize(candidate)
        if not normalized:
            continue
        if normalized in ABSENT_MARKERS or any(normalized.startswith(f"{marker}_") for marker in ABSENT_MARKERS):
            return True
    return False


def mechanism_token(value: object) -> str | None:
    """The mechanism id of a ``<MECHANISM-ID>: <statement>`` reference, or None."""
    if not has_text(value):
        return None
    match = MECHANISM_BINDING_RE.match(value.strip())
    return match.group("token") if match else None


def item_is_well_formed(item: object) -> bool:
    """True when a history item is a recordable ``evidence_reference`` + binding pair."""
    if not isinstance(item, dict) or set(item) != HISTORY_ITEM_FIELDS:
        return False
    if not has_text(item.get("evidence_reference")) or is_absent(item.get("evidence_reference")):
        return False
    return mechanism_token(item.get("mechanism_reference")) is not None


def item_is_bound(item: object) -> bool:
    """True when a history item binds a recorded event to a CONCRETE mechanism."""
    if not item_is_well_formed(item):
        return False
    return _normalize(mechanism_token(item.get("mechanism_reference"))) not in NO_MECHANISM_TOKENS


def admitted_history(dossier: dict) -> list[dict]:
    """History items that may be written: well-formed pairs only.

    An item that is not a well-formed pair cannot be written at all
    (``mechanism_reference`` is required by the reference contract), so it is kept out
    of the artifact and reported as a NOTE by the caller instead of being invented.
    """
    items = dossier.get("history_evidence")
    if not isinstance(items, list):
        return []
    return [
        {"evidence_reference": item["evidence_reference"], "mechanism_reference": item["mechanism_reference"]}
        for item in items
        if item_is_well_formed(item)
    ]


def dropped_history(dossier: dict) -> list[object]:
    """History items that cannot be written (unbound or malformed)."""
    items = dossier.get("history_evidence")
    if not isinstance(items, list):
        return []
    return [item for item in items if not item_is_well_formed(item)]


def dossier_defects(dossier: object, side: str) -> list[str]:
    """Every reason this dossier cannot be recorded RESOLVED. Empty list = it can.

    An UNRESOLVED claim needs no support and returns no defects.
    """
    if not isinstance(dossier, dict):
        return ["dossier must be an object"]
    if dossier.get("resolution") != RESOLVED:
        return []
    defects: list[str] = []
    for field in ("reference_id", "material_identity", "formula_identity", "storage_sop", "safety_reference"):
        if not has_text(dossier.get(field)):
            defects.append(f"{field} is missing")
        elif is_absent(dossier.get(field)):
            defects.append(f"{field} is recorded as absent")
    if dossier.get("selection_rung") not in RUNG_ORDER:
        defects.append(
            "selection_rung must be DIRECT_HISTORY or LONG_RUN_NO_EVENT to record RESOLVED "
            "(the ladder ends at UNRESOLVED, never at an invented rung)"
        )
    admitted = admitted_history(dossier)
    if not admitted:
        defects.append("history_evidence must hold at least one well-formed evidence item")
    if side == "known_bad" and not any(item_is_bound(item) for item in admitted):
        defects.append(
            "known_bad history_evidence must bind at least one recorded failure to the mechanism "
            "it demonstrates; a general statement about a contaminant is not evidence"
        )
    return defects


def recorded_resolution(dossier: object, side: str) -> str:
    """The only resolution a dossier may be recorded at: RESOLVED or a downgrade.

    Downgrade-only, in both directions: a dossier that declares UNRESOLVED is never
    upgraded, and a dossier that declares RESOLVED but lacks its own supporting records
    is stored as UNRESOLVED rather than believed.
    """
    if not isinstance(dossier, dict) or dossier.get("resolution") != RESOLVED:
        return UNRESOLVED
    return UNRESOLVED if dossier_defects(dossier, side) else RESOLVED


def recorded_dossier(dossier: dict, side: str) -> dict:
    """Project one input dossier into its recordable artifact form (downgrade-only)."""
    return {
        "reference_id": dossier.get("reference_id"),
        "resolution": recorded_resolution(dossier, side),
        "material_identity": dossier.get("material_identity"),
        "formula_identity": dossier.get("formula_identity"),
        "history_evidence": admitted_history(dossier),
        "storage_sop": dossier.get("storage_sop"),
        "safety_reference": dossier.get("safety_reference"),
    }


def recorded_side(dossiers: object, side: str) -> list[dict]:
    """Project one whole side (known_good / known_bad) into recorded dossiers."""
    if not isinstance(dossiers, list):
        return []
    return [recorded_dossier(dossier, side) for dossier in dossiers if isinstance(dossier, dict)]


def resolved_count(dossiers: object) -> tuple[int, int]:
    """(resolved, total) for one recorded side."""
    if not isinstance(dossiers, list):
        return 0, 0
    return (
        sum(1 for dossier in dossiers if isinstance(dossier, dict) and dossier.get("resolution") == RESOLVED),
        len(dossiers),
    )


def tier_from_input(known_good: object, known_bad: object) -> str:
    """Ladder rung achieved by any RESOLVED dossier of the INPUT (rungs are input-side)."""
    rungs = {
        dossier.get("selection_rung")
        for side, source in (("known_good", known_good), ("known_bad", known_bad))
        if isinstance(source, list)
        for dossier in source
        if isinstance(dossier, dict) and recorded_resolution(dossier, side) == RESOLVED
    }
    for rung in RUNG_ORDER:
        if rung in rungs:
            return rung
    return UNRESOLVED


def tier_errors(tier: object, known_good: object, known_bad: object) -> list[str]:
    """A stored ``tier`` must agree with the recorded dossiers it stands over.

    Scope, stated honestly: ``schemas/reference.schema.json`` fixes the dossier shape
    and carries no ladder-rung field, so the rung a dossier achieved is INPUT-side
    information. The validator therefore checks the resolved/UNRESOLVED direction
    exactly (no tier above UNRESOLVED without a RESOLVED dossier, and no UNRESOLVED over
    one) but cannot distinguish rung 1 from rung 2 in a hand-edited artifact whose
    dossiers are all legitimately RESOLVED. The builder derives ``tier`` from the
    claimed rung directly, so the normal path is exact; the dangerous direction - a
    resolution or a COMPLETE flag justified by nothing - is closed by
    ``dossier_evidence_errors`` and ``downstream_errors``.
    """
    errors: list[str] = []
    if tier not in TIERS:
        errors.append(f"tier must be one of {', '.join(TIERS)}")
        return errors
    any_resolved = bool(resolved_count(known_good)[0] or resolved_count(known_bad)[0])
    if not any_resolved and tier != UNRESOLVED:
        errors.append(f"tier must be {UNRESOLVED} when no dossier is RESOLVED")
    if any_resolved and tier == UNRESOLVED:
        errors.append(f"tier {UNRESOLVED} cannot stand over a RESOLVED dossier")
    return errors


def derive_downstream_flag(known_bad: object) -> str:
    """Discrimination evidence carried downstream: COMPLETE only with a RESOLVED Known Bad."""
    return DOWNSTREAM_COMPLETE if resolved_count(known_bad)[0] else DOWNSTREAM_INCOMPLETE


def downstream_errors(tier: object, downstream_flag: object, known_bad: object) -> list[str]:
    """The schema's two if/then rules at the skill layer, both directions enforced."""
    errors: list[str] = []
    if downstream_flag not in DOWNSTREAM_FLAGS:
        errors.append(f"downstream_flag must be one of {', '.join(DOWNSTREAM_FLAGS)}")
        return errors
    expected = derive_downstream_flag(known_bad)
    if downstream_flag != expected:
        errors.append(
            f"downstream_flag must be {expected}: a RESOLVED Known Bad carries the discrimination "
            "evidence and a set without one stays DISCRIMINATION_EVIDENCE_INCOMPLETE"
        )
    if tier == UNRESOLVED and downstream_flag != DOWNSTREAM_INCOMPLETE:
        errors.append(
            f"tier {UNRESOLVED} requires downstream_flag {DOWNSTREAM_INCOMPLETE} "
            "(mirrors the tier if/then rule of schemas/reference.schema.json)"
        )
    return errors


def gate_blockers(known_good: object, known_bad: object) -> list[str]:
    """The release rule: at least ONE side must be RESOLVED before Stage 5."""
    if resolved_count(known_good)[0] or resolved_count(known_bad)[0]:
        return []
    return [
        "at least one of Known Good / Known Bad must be RESOLVED before Stage 5 "
        "(frozen release rule for Stage 4)"
    ]


def identity_errors(known_good: object, known_bad: object) -> list[str]:
    """A dossier reference_id must identify exactly one dossier across the whole set."""
    errors: list[str] = []
    seen: dict[str, int] = {}
    for dossiers in (known_good, known_bad):
        if not isinstance(dossiers, list):
            continue
        for dossier in dossiers:
            if not isinstance(dossier, dict) or not has_text(dossier.get("reference_id")):
                continue
            reference_id = dossier["reference_id"]
            seen[reference_id] = seen.get(reference_id, 0) + 1
    for reference_id, count in sorted(seen.items()):
        if count > 1:
            errors.append(f"reference_id {reference_id} is used by {count} dossiers; a dossier id must identify one dossier")
    return errors


def dossier_evidence_errors(known_good: object, known_bad: object) -> list[str]:
    """No recorded dossier may claim more support than its own written records hold."""
    errors: list[str] = []
    for side, dossiers in (("known_good", known_good), ("known_bad", known_bad)):
        if not isinstance(dossiers, list):
            continue
        for index, dossier in enumerate(dossiers):
            if not isinstance(dossier, dict) or dossier.get("resolution") != RESOLVED:
                continue
            label = f"{side}[{index}] {dossier.get('reference_id')}"
            for field in ("reference_id", "material_identity", "formula_identity", "storage_sop", "safety_reference"):
                if not has_text(dossier.get(field)):
                    errors.append(f"{label}: {field} is required to record RESOLVED")
                elif is_absent(dossier.get(field)):
                    errors.append(f"{label}: {field} is recorded as absent, so the dossier cannot be RESOLVED")
            admitted = dossier.get("history_evidence")
            if not isinstance(admitted, list) or not admitted or not all(item_is_well_formed(item) for item in admitted):
                errors.append(f"{label}: RESOLVED requires well-formed history_evidence")
            elif side == "known_bad" and not any(item_is_bound(item) for item in admitted):
                errors.append(f"{label}: RESOLVED known_bad requires a failure bound to the mechanism it demonstrates")
    return errors


def has_gap(evidence: object) -> bool:
    """True when an artifact-level evidence item records an unresolved gap."""
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("status") == "GAP" for item in evidence
    )


def expected_decision_fields(
    reference_id: object,
    evidence_scope: object,
    known_good: object,
    known_bad: object,
    tier: object,
    downstream_flag: object,
    evidence: object,
) -> dict[str, str]:
    """The canonical decision block, recomputed identically by builder and validator."""
    resolved_good, total_good = resolved_count(known_good)
    resolved_bad, total_bad = resolved_count(known_bad)
    blockers = gate_blockers(known_good, known_bad)
    if has_gap(evidence):
        blockers = [*blockers, "an artifact-level evidence item carries status GAP"]
    decision = "GO" if not blockers else "HOLD"
    scope_prefix = (
        "Synthetic test fixture / NOT_FOR_PHYSICAL_EXECUTION: this record cannot authorize stage advancement. "
        if evidence_scope == "SYNTHETIC"
        else ""
    )
    return {
        "decision_question": (
            f"Does reference set {reference_id} own at least one RESOLVED side usable as the "
            "discrimination ruler for the bench campaign?"
        ),
        "hypothesis": (
            f"Reference set {reference_id} records material identity, formula identity, mechanism-bound "
            "history, storage SOP and safety reference for a Known Good and a Known Bad."
        ),
        "uncertainty": (
            f"{scope_prefix}Supplied dossiers record material history; they are not independently verified "
            "evidence, so recording a dossier does not qualify a test method and does not by itself prove "
            f"that any stand can discriminate. downstream_flag={downstream_flag} is read by Stage 5, which "
            "refuses to proceed when it is DISCRIMINATION_EVIDENCE_INCOMPLETE: a Stage 4 GO is necessary but "
            "not sufficient for Stage 5."
        ),
        "decision_rule": (
            "A reference set may advance to Stage 5 only when at least one of its Known Good and Known Bad "
            "sides is RESOLVED; a Known Bad is RESOLVED only when at least one recorded failure is bound to "
            "the mechanism it demonstrates, and Stage 5 hard-rejects a dossier whose downstream_flag is "
            "DISCRIMINATION_EVIDENCE_INCOMPLETE (a Stage 4 GO is necessary but not sufficient)."
        ),
        "result": (
            f"reference set {reference_id}: known_good {resolved_good}/{total_good} RESOLVED, "
            f"known_bad {resolved_bad}/{total_bad} RESOLVED; tier={tier}; downstream_flag={downstream_flag}."
        ),
        "decision": decision,
        "next_action": (
            f"Route reference set {reference_id} to Stage 5 (test-method-qualification) as its discrimination "
            f"ruler and carry downstream_flag={downstream_flag} forward."
            if decision == "GO"
            else f"Stay at Stage 4: reference set {reference_id} has no RESOLVED side. Retain the recorded "
            f"dossiers (tier={tier}) and obtain a mechanism-bound Known Bad or a resolved Known Good; "
            f"downstream_flag={downstream_flag} stays incomplete."
        ),
    }


def input_notes(data: object) -> list[str]:
    """Audible NOTE lines: per-dossier rung achieved, and history items not admitted."""
    if not isinstance(data, dict):
        return []
    notes: list[str] = []
    for side in SIDES:
        dossiers = data.get(side)
        if not isinstance(dossiers, list):
            continue
        for index, dossier in enumerate(dossiers):
            if not isinstance(dossier, dict):
                continue
            label = f"{side}[{index}] {dossier.get('reference_id')}"
            for item_index, _ in enumerate(dropped_history(dossier)):
                notes.append(
                    f"NOTE: {label} history_evidence[{item_index}] is not a mechanism binding and is not "
                    "admitted as evidence; the dossier cannot be recorded RESOLVED"
                )
            defects = dossier_defects(dossier, side)
            if defects:
                notes.append(f"NOTE: {label} recorded {UNRESOLVED}: {'; '.join(defects)}")
            elif dossier.get("resolution") != RESOLVED:
                notes.append(
                    f"NOTE: {label} recorded {UNRESOLVED}: the caller declared {UNRESOLVED}; no side is "
                    "upgraded by this skill"
                )
            else:
                notes.append(f"NOTE: {label} recorded {RESOLVED} at rung {dossier.get('selection_rung')}")
    return notes
