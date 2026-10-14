"""Deterministic merged bench policy: the capacity conversion + the round plan's judgement.

Contract v1.0.0 merged the former pair of stages (bench registration and the
campaign opening) into ONE stage and ONE artifact, ``bench.json``: the record
registers a shared test-stand resource AND carries the inner-loop round plan that
resource is spent on. This module holds the judgement the preflight, the builder
and the validator must agree on, so the three scripts cannot disagree about the
same input. Two rule families live here:

A. THE CAPACITY CONVERSION. `available_bench_slots` is the single conversion of a
bench's availability into capacity, and it is the anchor the DOE resource envelope
must reconcile against:

    available_bench_slots = sum over availability_window of
        floor(usable_days(window) / cycle_days)

where usable_days(window) = (end - start).days + 1 - reserved_days, clamped at 0.

WP-04b adds `resource_envelope.bench_slots` to the nested DOE input schema
(`domains/lubricant/schemas/doe_input.schema.json`). That value MUST be reconciled
with this function (end-to-end cross-check recorded as a TODO in
`tests/lubricant_e2e/test_application_bench.py`; the two are in separate
worktrees and are joined only after merge).

B. THE ROUND PLAN AND ITS ONE DECISION. The plan's ledger is the list of rounds
already run, each ending in one ``stop_state``, plus the paired design the rounds
follow and the cap that bounds them. Four rules, all fail-closed:

1. THE CAP IS THE CONTRACT'S OR THE CALLER'S, NEVER INVENTED. ``max_iterations``
   may be supplied in the campaign block of the request; when it is absent the
   value is read from ``contracts/state-machine.json`` (``max_iterations``, 12:
   "about 12 bench rounds in one year") and the built artifact records that
   provenance in one appended evidence item. A request that omits the cap while
   the contract cannot be read is refused: a plan whose cap is unknown cannot be
   bounded, and no other number is guessed.

2. ONLY CONTINUE AUTHORIZES ANOTHER ROUND (schema ``bench.schema.json``, the
   ``iterations`` description). Every round older than the newest must have ended
   CONTINUE; a plan whose newest round ended GOAL_MET / NO_NEW_INFORMATION /
   RESOURCE_EXHAUSTED / PIVOT / KILL is still recorded truthfully, but no round may
   follow it. A ledger that records NO round yet (W0: the plan is opened before
   round 1 runs) does authorize the first round.

3. THE CAP IS A REAL BOUND, AND current_iteration IS THE ROUND THE LEDGER STANDS
   AT. ``current_iteration`` must not exceed ``max_iterations`` and the plan may
   not record more rounds than the cap allows (both stated by the schema). With an
   empty ledger it is 1; with a newest round that ended CONTINUE it is
   ``len(iterations) + 1`` (that round opened the next one, W1); with a newest
   round that ended otherwise it is ``len(iterations)`` (the ledger closed at that
   round, W2). A plan cannot be "at" round 1 while holding three completed rounds.

3b. THE MODEL AND NEXT-BATCH REFERENCES ARE EXIT-ROUND ONLY (E2=B).
   ``model_reference`` and ``next_batch_reference`` are written only on the round
   that exits the inner loop; every round that looped back (``stop_state ==
   CONTINUE``) must carry null for both. ``screening_reference`` and
   ``variance_reference`` are per-round and carry no such rule.

The former per-block rules 4 and 5 of the campaign policy (bench references resolve
to supplied registered benches; a SYNTHETIC bench never backs a PHYSICAL campaign)
are subsumed by the merge and gone: the artifact IS the bench registration, so
there is no ``bench_references`` list left to resolve, and the two halves must
declare the same ``evidence_scope`` (preflight cross-block rule), so a
SYNTHETIC/PHYSICAL mismatch cannot be represented.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

# ---- the bench half: availability -> usable slots ------------------------------
INPUT_FIELDS = {
    "bench_id", "project_reference", "bench_name", "location",
    "availability_window", "cycle_days", "cost_per_run",
    "source", "evidence_id", "evidence_scope", "evidence",
}
# The bench-owned fields of a built artifact, projected verbatim from the block.
BENCH_ARTIFACT_FIELDS = (
    "bench_id", "project_reference", "bench_name", "location",
    "availability_window", "cycle_days", "cost_per_run",
)
# The request shape minus evidence: what the artifact validator checks through the
# bench block's field rules (the artifact's evidence array is the merged one).
BENCH_FIELD_FIELDS = INPUT_FIELDS - {"evidence"}
ALLOWED_FIELDS = INPUT_FIELDS | {"available_bench_slots"}
WINDOW_FIELDS = {"window_id", "start", "end", "reserved_days"}
EVIDENCE_SCOPES = {"SYNTHETIC", "PHYSICAL"}
ISO_DATE_LENGTH = 10

SKILL_ROOT = Path(__file__).resolve().parents[1]

# The one stage this skill materialises (contract v1.0.0). The registration and
# the campaign opening are now a single stage, and the router hands it here on
# the PRECISION_GREASE_DEV route only.
BENCH_STAGE = "BENCH_RESOURCE_REGISTERED"

# ---- the round-plan half: the campaign block and the merged artifact -------------
# The campaign block of the request. `max_iterations` is optional (rule 1) and so is
# `project_reference` (after the merge it shares its source with
# bench.project_reference; a supplied value must equal it, checked by the preflight).
# Every other field is mandatory: a plan with no identity, no rounds, no pairing
# design or no evidence is not a plan.
CAMPAIGN_REQUEST_FIELDS = {
    "campaign_id", "project_reference", "max_iterations",
    "current_iteration", "iterations", "pairing_design", "evidence_scope",
    "source", "evidence_id", "evidence",
}
REQUIRED_CAMPAIGN_REQUEST_FIELDS = CAMPAIGN_REQUEST_FIELDS - {"max_iterations", "project_reference"}

# The campaign-owned fields of a built artifact: the record the validator
# re-derives every ledger judgement from. evidence_scope is shared with the bench
# block (the preflight requires the halves to agree); evidence is artifact-level.
CAMPAIGN_RECORD_FIELDS = {
    "campaign_id", "pairing_design", "current_iteration", "max_iterations", "iterations",
}

# The full field set of the merged artifact (bench.schema.json,
# unevaluatedProperties false): the shared artifact block + the bench half + the
# round-plan half. The artifact-level source/evidence_id/evidence_scope are the
# bench block's (it is the main record the plan hangs off).
ARTIFACT_FIELDS = {
    "schema_version", "artifact_type", "project_id", "stage",
    "decision_question", "hypothesis", "uncertainty", "evidence",
    "decision_rule", "result", "decision", "next_action",
    "bench_id", "project_reference", "bench_name", "location",
    "availability_window", "cycle_days", "cost_per_run", "available_bench_slots",
    "source", "evidence_id", "evidence_scope",
    "campaign_id", "pairing_design", "current_iteration", "max_iterations", "iterations",
}

ITERATION_FIELDS = {
    "iteration", "samples", "stop_state", "screening_reference",
    "variance_reference", "model_reference", "next_batch_reference",
    "bench_test_references",
}
REQUIRED_ITERATION_FIELDS = {"iteration", "samples", "stop_state"}
# screening_reference / variance_reference are PER-ROUND: a round that ran records what was
# screened and what was assessed, whether it looped back or exited the loop.
PER_ROUND_REFERENCE_FIELDS = ("screening_reference", "variance_reference")
# model_reference / next_batch_reference are EXIT-ROUND ONLY (E2=B): the model update and the
# sequential decision happen only on the round that exits the inner loop, so a round that
# ended CONTINUE (it looped back) must leave both null. Enforced in iteration_errors.
EXIT_ROUND_REFERENCE_FIELDS = ("model_reference", "next_batch_reference")
STOP_STATES = ("CONTINUE", "GOAL_MET", "NO_NEW_INFORMATION", "RESOURCE_EXHAUSTED", "PIVOT", "KILL")
CONTINUE = "CONTINUE"
PAIRING_FIELDS = {"paired", "description"}

# Evidence items: the shared common.schema.json shape, claim_class optional
# (WP-12), exactly as external-record-import and variance-assessment accept it.
EVIDENCE_FIELDS = {"evidence_id", "statement", "source", "status", "claim_class"}
EVIDENCE_STATUSES = {"OBSERVED", "ASSUMED", "GAP"}
CLAIM_CLASSES = {
    "MANUFACTURER_DATASHEET", "THIRD_PARTY_LAB", "INTERNAL_TEST", "REGULATORY_OR_STANDARD",
}

# The one evidence item this skill appends, when and only when it defaulted the
# cap: the reserved id may not be supplied by the caller (the preflight refuses
# it), so its presence on a built artifact is a trustworthy provenance marker.
MAX_ITERATIONS_EVIDENCE_ID = "E-CONTRACT-CAMPAIGN-MAX-ITERATIONS"
CONTRACT_SOURCE = "contracts/state-machine.json"


# ---- shared scalar predicates ---------------------------------------------------
def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_positive_int(value: object) -> bool:
    return is_int(value) and value >= 1


def parse_iso_date(value: object) -> date | None:
    if not has_text(value) or len(value) != ISO_DATE_LENGTH:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# ---- the capacity conversion ----------------------------------------------------
def window_usable_days(window: object) -> int | None:
    """Inclusive usable days in one availability window, or None if malformed."""
    if not isinstance(window, dict):
        return None
    start, end = parse_iso_date(window.get("start")), parse_iso_date(window.get("end"))
    if start is None or end is None:
        return None
    reserved = window.get("reserved_days", 0)
    if not is_non_negative_int(reserved):
        return None
    return max((end - start).days + 1 - reserved, 0)


def available_bench_slots(bench: object) -> int:
    """Convert availability_window + cycle_days into usable slots. Raises on malformed input."""
    if not isinstance(bench, dict):
        raise ValueError("bench must be a JSON object")
    cycle = bench.get("cycle_days")
    if not is_finite_number(cycle) or cycle <= 0:
        raise ValueError("cycle_days must be a positive number")
    windows = bench.get("availability_window")
    if not isinstance(windows, list) or not windows:
        raise ValueError("availability_window must be a non-empty array")
    total = 0
    for window in windows:
        days = window_usable_days(window)
        if days is None:
            label = window.get("window_id", "?") if isinstance(window, dict) else "?"
            raise ValueError(f"availability_window {label} has invalid dates or reserved_days")
        total += max(0, math.floor(days / cycle))
    return total


def has_gap(record: object) -> bool:
    evidence = record.get("evidence") if isinstance(record, dict) else None
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("status") == "GAP" for item in evidence
    )


# ---- the cap: the contract's or the caller's, never invented ---------------------
def contract_path() -> Path | None:
    """The shared state-machine contract, from the pack or the deployed skill."""
    for candidate in (SKILL_ROOT.parents[1] / "contracts", SKILL_ROOT / "references"):
        path = candidate / "state-machine.json"
        if path.is_file():
            return path
    return None


def contract_max_iterations() -> tuple[int | None, list[str]]:
    """The contract's published inner-loop cap, or the reason it cannot be read."""
    path = contract_path()
    if path is None:
        return None, [
            f"max_iterations is absent and {CONTRACT_SOURCE} is absent from the pack contracts/ "
            "and the deployed references/ directories"
        ]
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, [f"max_iterations is absent and {CONTRACT_SOURCE} cannot be read: {error}"]
    value = contract.get("max_iterations") if isinstance(contract, dict) else None
    if not is_positive_int(value):
        return None, [f"max_iterations is absent and {CONTRACT_SOURCE} publishes no positive integer max_iterations"]
    return value, []


def resolve_cap(record: object) -> tuple[int | None, bool, list[str]]:
    """The plan's iteration cap: the supplied value, or the contract's.

    Returns (cap, defaulted, errors). ``defaulted`` is True only when the request
    omitted ``max_iterations`` and the value came from the contract.
    """
    if not isinstance(record, dict):
        return None, False, ["campaign must be a JSON object"]
    if "max_iterations" in record:
        supplied = record.get("max_iterations")
        if not is_positive_int(supplied):
            return None, False, ["campaign.max_iterations must be a positive integer (bench rounds)"]
        return supplied, False, []
    default, errors = contract_max_iterations()
    return default, True, errors


def max_iterations_evidence_item(cap: int) -> dict:
    """The canonical provenance item for a contract-defaulted cap."""
    return {
        "evidence_id": MAX_ITERATIONS_EVIDENCE_ID,
        "statement": (
            f"max_iterations={cap} was defaulted from {CONTRACT_SOURCE} (max_iterations); no explicit cap was "
            "supplied in the campaign block, so the plan is bounded by the contract's published figure "
            "rather than by an invented one."
        ),
        "source": CONTRACT_SOURCE,
        "status": "OBSERVED",
    }


def defaulted_from_evidence(evidence: object) -> bool:
    """True when the artifact carries the contract-default provenance item."""
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("evidence_id") == MAX_ITERATIONS_EVIDENCE_ID for item in evidence
    )


# ---- evidence rules -------------------------------------------------------------
def evidence_errors(evidence: object, *, forbid_provenance_item: bool) -> list[str]:
    if not isinstance(evidence, list) or not evidence:
        return ["campaign.evidence must be a non-empty array"]
    errors: list[str] = []
    for index, item in enumerate(evidence):
        label = f"campaign.evidence[{index}]"
        if not isinstance(item, dict) or not set(item) <= EVIDENCE_FIELDS or not {"evidence_id", "statement", "source", "status"} <= set(item):
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"{label}.status")
        if "claim_class" in item and item.get("claim_class") not in CLAIM_CLASSES:
            errors.append(f"{label}.claim_class")
        if forbid_provenance_item and item.get("evidence_id") == MAX_ITERATIONS_EVIDENCE_ID:
            errors.append(
                f"{label}.evidence_id {MAX_ITERATIONS_EVIDENCE_ID} is reserved for the contract-default "
                "provenance item this skill appends"
            )
    return errors


# ---- ledger rules ---------------------------------------------------------------
def iteration_errors(iterations: object, cap: object) -> list[str]:
    if not isinstance(iterations, list):
        return ["campaign.iterations must be an array of round entries (empty until round 1's boundary is recorded)"]
    errors: list[str] = []
    for index, entry in enumerate(iterations):
        label = f"campaign.iterations[{index}]"
        if not isinstance(entry, dict) or not set(entry) <= ITERATION_FIELDS or not REQUIRED_ITERATION_FIELDS <= set(entry):
            extras = sorted(set(entry) - ITERATION_FIELDS) if isinstance(entry, dict) else []
            missing = sorted(REQUIRED_ITERATION_FIELDS - set(entry)) if isinstance(entry, dict) else []
            errors.append(f"{label} must contain {sorted(REQUIRED_ITERATION_FIELDS)}; unexpected={extras or 'none'} missing={missing or 'none'}")
            continue
        if entry.get("iteration") != index + 1:
            errors.append(f"{label}.iteration must be {index + 1}: rounds are recorded oldest first and 1-based")
        samples = entry.get("samples")
        if not isinstance(samples, list) or not samples or not all(has_text(sample) for sample in samples):
            errors.append(f"{label}.samples must be a non-empty array of sample references")
        if entry.get("stop_state") not in STOP_STATES:
            errors.append(f"{label}.stop_state must be one of {sorted(STOP_STATES)}")
        elif index < len(iterations) - 1 and entry.get("stop_state") != CONTINUE:
            errors.append(
                f"{label}.stop_state must be {CONTINUE}: only {CONTINUE} authorizes another round, so no round "
                "may follow one that ended otherwise"
            )
        for field in (*PER_ROUND_REFERENCE_FIELDS, *EXIT_ROUND_REFERENCE_FIELDS):
            if field in entry and entry.get(field) is not None and not has_text(entry.get(field)):
                errors.append(f"{label}.{field} must be a non-empty string or null")
        # E2=B exit-round-only references: a round that ended CONTINUE looped back, and the
        # model update / next-batch decision are taken only on the round that exits the loop.
        if entry.get("stop_state") == CONTINUE:
            for field in EXIT_ROUND_REFERENCE_FIELDS:
                if entry.get(field) is not None:
                    errors.append(
                        f"{label}.{field} must be null while this round ended {CONTINUE}: the model update and "
                        "the next-batch decision are written only on the round that exits the inner loop"
                    )
        if "bench_test_references" in entry:
            references = entry.get("bench_test_references")
            if not isinstance(references, list) or not all(has_text(item) for item in references):
                errors.append(f"{label}.bench_test_references must be an array of bench-test references")
    if is_positive_int(cap) and len(iterations) > cap:
        errors.append(f"campaign.iterations records {len(iterations)} rounds, more than max_iterations {cap}")
    return errors


def pairing_errors(pairing: object) -> list[str]:
    if not isinstance(pairing, dict) or set(pairing) != PAIRING_FIELDS:
        return [f"campaign.pairing_design must contain exactly {sorted(PAIRING_FIELDS)}"]
    errors: list[str] = []
    if not isinstance(pairing.get("paired"), bool):
        errors.append("campaign.pairing_design.paired must be a boolean")
    if not has_text(pairing.get("description")):
        errors.append("campaign.pairing_design.description")
    return errors


def cross_field_errors(record: object, cap: object) -> list[str]:
    """The rules the schema cannot express, enforced here and reported by name.

    bench.schema.json says so itself: pure JSON Schema has no keyword that
    compares two instance values, so these are validator-enforced rather than
    structural (top-level description, the `$comment` on max_iterations, and the
    schema's own `$comment`):

    * ``current_iteration`` must not exceed ``max_iterations``;
    * ``current_iteration`` IS the round the ledger stands at: 1 while no round is
      recorded (the ledger is opened before round 1 runs, W0), ``len(iterations) + 1``
      when the newest recorded round ended CONTINUE (that round opened the next one, W1),
      and ``len(iterations)`` when it ended otherwise (the ledger closed at that round, W2).
    """
    errors: list[str] = []
    current = record.get("current_iteration") if isinstance(record, dict) else None
    if is_positive_int(current) and is_positive_int(cap) and current > cap:
        errors.append(f"campaign.current_iteration {current} must not exceed max_iterations {cap}")
    iterations = record.get("iterations") if isinstance(record, dict) else None
    if not isinstance(iterations, list) or not is_positive_int(current):
        return errors
    if not iterations:
        if current != 1:
            errors.append(
                f"campaign.current_iteration {current} must be 1 while no round is recorded: the ledger is opened "
                "before round 1's boundary is reached"
            )
        return errors
    newest = iterations[-1]
    newest_state = newest.get("stop_state") if isinstance(newest, dict) else None
    if newest_state == CONTINUE:
        expected = len(iterations) + 1
        if current != expected:
            errors.append(
                f"campaign.current_iteration {current} must be {expected}: the newest recorded round ended "
                f"{CONTINUE}, so the ledger stands at the round that round opened"
            )
    elif current != len(iterations):
        errors.append(
            f"campaign.current_iteration {current} must be {len(iterations)}: the newest recorded round ended "
            f"{newest_state!r}, so the ledger stands at the round it closed at"
        )
    return errors


def record_field_errors(record: object, cap: object) -> list[str]:
    """Every field-level ledger rule, shared by the campaign block and the artifact.

    The evidence array is deliberately NOT checked here: on the request it is the
    block's own array, on the artifact it is the two blocks' array merged, and each
    caller checks the array it actually owns.
    """
    if not isinstance(record, dict):
        return ["campaign must be a JSON object"]
    errors: list[str] = []
    if not has_text(record.get("campaign_id")):
        errors.append("campaign.campaign_id")
    if not is_positive_int(record.get("current_iteration")):
        errors.append("campaign.current_iteration must be a positive integer (bench round, 1-based)")
    errors.extend(iteration_errors(record.get("iterations"), cap))
    errors.extend(pairing_errors(record.get("pairing_design")))
    if record.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("campaign.evidence_scope must be SYNTHETIC or PHYSICAL")
    errors.extend(cross_field_errors(record, cap))
    return errors


def record_errors(record: object, *, cap: object, forbid_provenance_item: bool) -> list[str]:
    """Every campaign-block-level rule, in one place for the request block.

    ``forbid_provenance_item`` is True for the request (the caller may not forge
    the reserved contract-default marker); a built artifact carries it legitimately
    and is checked by :func:`policy_errors` instead.
    """
    if not isinstance(record, dict):
        return ["campaign must be a JSON object"]
    errors = record_field_errors(record, cap)
    errors.extend(evidence_errors(record.get("evidence"), forbid_provenance_item=forbid_provenance_item))
    if not errors and has_gap(record):
        errors.append("campaign.evidence contains GAP; current input is insufficient")
    return errors


def provenance_errors(evidence: object, cap: object) -> list[str]:
    """The appended contract-default item, when present, must be canonical and true."""
    if not isinstance(evidence, list):
        return []
    items = [item for item in evidence if isinstance(item, dict) and item.get("evidence_id") == MAX_ITERATIONS_EVIDENCE_ID]
    if not items:
        return []
    errors: list[str] = []
    if len(items) > 1:
        errors.append(f"evidence must carry at most one {MAX_ITERATIONS_EVIDENCE_ID} item")
    default, contract_errors = contract_max_iterations()
    if contract_errors:
        errors.extend(contract_errors)
        return errors
    if cap != default:
        errors.append(
            f"campaign.max_iterations {cap} carries the {MAX_ITERATIONS_EVIDENCE_ID} provenance, but "
            f"{CONTRACT_SOURCE} publishes {default}"
        )
    elif items[0] != max_iterations_evidence_item(default):
        errors.append(f"{MAX_ITERATIONS_EVIDENCE_ID} must be the canonical contract-default provenance item")
    return errors


# ---- the merged decision block --------------------------------------------------
def expected_decision_fields(bench: dict, campaign: dict, slots: int, *, defaulted: bool) -> dict[str, str]:
    """The canonical merged decision block. Pure function of the record's own fields.

    The merged record answers one question -- whether the supplied input is
    sufficient to register the bench AND open its round plan -- so the decision
    follows that reading: GO when no supplied evidence item is GAP, HOLD
    otherwise. The ledger's own legality (cap, W0/W1/W2 position, E2=B exit-round
    references) is enforced fail-closed by the cross-field validators, never
    softened into this block; ``result`` reports the ledger state it stands at so
    both readings are visible on the artifact.

    ``defaulted`` is passed in rather than re-derived so the builder (which
    defaulted the cap) and the validator (which re-derives it from the appended
    provenance item) compute the same text deterministically.
    """
    bench = bench if isinstance(bench, dict) else {}
    campaign = campaign if isinstance(campaign, dict) else {}
    bench_id = bench.get("bench_id", "")
    campaign_id = campaign.get("campaign_id", "")
    iterations = campaign.get("iterations") if isinstance(campaign.get("iterations"), list) else []
    rounds = len(iterations)
    newest = iterations[-1].get("stop_state") if rounds and isinstance(iterations[-1], dict) else None
    current = campaign.get("current_iteration")
    cap = campaign.get("max_iterations")
    gap = has_gap(bench) or has_gap(campaign)
    cap_source = f"defaulted from {CONTRACT_SOURCE}" if defaulted else "supplied in the request"
    if not rounds:
        ledger = (
            f"no round recorded yet (the ledger stands at round {current} of {cap}, max_iterations={cap}, {cap_source})"
        )
    elif newest == CONTINUE:
        ledger = (
            f"{rounds} round(s) recorded, standing at round {current} of {cap} (max_iterations={cap}, {cap_source})"
        )
    else:
        ledger = (
            f"{rounds} round(s) recorded, the ledger closed at round {current} of {cap} "
            f"(max_iterations={cap}, {cap_source})"
        )
    if gap:
        next_action = "Retain the supplied evidence and resolve the recorded GAP before registering the bench or opening its round plan."
    elif not rounds or newest == CONTINUE:
        next_action = f"Open bench round {current} of {cap} with the pairing design recorded above."
    else:
        next_action = (
            f"Retain {bench_id} as a registered bench with {slots} usable slots; the newest recorded round ended "
            f"{newest}, so this record opens no further round."
        )
    return {
        "decision_question": f"Is the supplied input sufficient to register bench {bench_id} and open its round plan?",
        "hypothesis": (
            f"{bench_id} records its availability windows, cycle time and per-run cost sufficient for later slot "
            f"planning, and {campaign_id} records its rounds, their stop states and its paired design, so the inner "
            f"loop can run up to {cap} bench rounds."
        ),
        "uncertainty": (
            "Supplied availability, cycle time and cost are not independently verified; recorded ASSUMED evidence "
            "remains assumed and this record does not reserve capacity, book a run, or establish a capability "
            "conclusion. The plan's rounds are recorded as they happened, and a later round's outcome is not known "
            "before it runs."
        ),
        "decision_rule": (
            "Register the bench and open its round plan only when availability windows, a positive cycle time, "
            "per-run cost with source, a recorded pairing design, and evidence without GAP are supplied; the "
            "cross-field ledger rules (current_iteration within max_iterations, only CONTINUE authorizes another "
            "round, exit-round-only model/next-batch references) are enforced by the validator."
        ),
        "result": (
            f"{bench_id} is {'sufficient' if not gap else 'not sufficient'} to register a bench record; "
            f"available_bench_slots={slots}; {ledger}."
        ),
        "decision": "GO" if not gap else "HOLD",
        "next_action": next_action,
    }


def decision_errors(artifact: dict, slots: int) -> list[str]:
    """Re-derive the decision block from the artifact and require an exact match."""
    bench = {field: artifact.get(field) for field in INPUT_FIELDS}
    campaign = {field: artifact.get(field) for field in CAMPAIGN_RECORD_FIELDS}
    campaign = {**campaign, "evidence": artifact.get("evidence")}
    defaulted = defaulted_from_evidence(artifact.get("evidence"))
    return [
        f"{field} must equal the deterministic bench policy"
        for field, value in expected_decision_fields(bench, campaign, slots, defaulted=defaulted).items()
        if artifact.get(field) != value
    ]


def policy_errors(artifact: object) -> list[str]:
    """Everything the validator re-derives from a built merged artifact."""
    if not isinstance(artifact, dict):
        return ["artifact must be a JSON object"]
    errors: list[str] = []
    if set(artifact) != ARTIFACT_FIELDS:
        extra = sorted(set(artifact) - ARTIFACT_FIELDS)
        missing = sorted(ARTIFACT_FIELDS - set(artifact))
        errors.append(
            f"artifact must contain exactly the merged bench fields; unexpected={extra or 'none'} missing={missing or 'none'}"
        )
        return errors
    cap = artifact.get("max_iterations")
    record = {field: artifact.get(field) for field in CAMPAIGN_RECORD_FIELDS | {"evidence_scope"}}
    errors.extend(record_field_errors(record, cap))
    errors.extend(evidence_errors(artifact.get("evidence"), forbid_provenance_item=False))
    if not errors and has_gap(artifact):
        errors.append("evidence contains GAP; the current input is insufficient")
    errors.extend(provenance_errors(artifact.get("evidence"), cap))
    try:
        slots = available_bench_slots(artifact)
    except ValueError as error:
        errors.append(f"available_bench_slots cannot be re-derived: {error}")
        return errors
    if artifact.get("available_bench_slots") != slots:
        errors.append(f"available_bench_slots must equal the derived {slots}")
    errors.extend(decision_errors(artifact, slots))
    return errors
