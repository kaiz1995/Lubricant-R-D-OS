"""Deterministic campaign policy: the inner-loop carrier and its one decision.

CAMPAIGN_OPENED is the second stage the router hands to this skill
(`skills/lubricant-rd-agent/scripts/route_step.py`, PRECISION_GREASE_DEV only,
where a bench is the bottleneck). A campaign is the carrier of the inner loop:
it records the bench rounds already run, how each one ended (``stop_state``),
the paired design the rounds follow, and the iteration cap that bounds them.

This module holds the judgement the preflight, the builder and the validator must
agree on, so the three scripts cannot disagree about the same input. Five rules,
all fail-closed:

1. THE CAP IS THE CONTRACT'S OR THE CALLER'S, NEVER INVENTED. ``max_iterations``
   may be supplied in the request; when it is absent the value is read from
   ``contracts/state-machine.json`` (``max_iterations``, 12: "about 12 bench
   rounds in one year") and the built artifact records that provenance in both
   its ``result`` text and one appended evidence item. A request that omits the
   cap while the contract cannot be read is refused: a campaign whose cap is
   unknown cannot be bounded, and no other number is guessed.

2. ONLY CONTINUE AUTHORIZES ANOTHER ROUND (schema ``campaign.schema.json``, the
   ``iterations`` description). Every round older than the newest must have ended
   CONTINUE; a campaign whose newest round ended GOAL_MET / NO_NEW_INFORMATION /
   RESOURCE_EXHAUSTED / PIVOT / KILL is still recorded truthfully, but its
   decision is HOLD -- the record does not authorize another bench round, and the
   inner loop is not something this record may silently extend.

3. THE CAP IS A REAL BOUND. ``current_iteration`` must not exceed
   ``max_iterations`` and the campaign may not record more rounds than the cap
   allows (both stated by the schema). ``current_iteration`` also may not sit
   before the rounds the record already lists: a campaign cannot be "at" round 1
   while holding three completed rounds.

4. THE BENCH REFERENCES COME FROM REGISTERED BENCHES. Every
   ``bench_references`` entry must resolve to a supplied, schema-valid bench
   artifact of the same project, and a supplied bench artifact that no reference
   cites is an omission, not a silent drop: the campaign draws its scarce slots
   from benches someone registered, and a reference that does not resolve is a
   provenance hole (the same shape as application-validation's upstream
   contract).

5. A SYNTHETIC BENCH NEVER BACKS A PHYSICAL CAMPAIGN. The bench skill's red line
   "NO Synthetic Closure" forbids presenting a SYNTHETIC bench record as physical
   capacity, so a PHYSICAL campaign citing a SYNTHETIC bench artifact is refused
   here rather than promoted downstream.

The derived ``available_bench_slots`` of each supplied bench is *called* from
``bench_policy`` (single source of truth) and reported by the preflight; it is
never recomputed here and never stored on the campaign artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

from bench_policy import EVIDENCE_SCOPES, has_text

SKILL_ROOT = Path(__file__).resolve().parents[1]

CAMPAIGN_STAGE = "CAMPAIGN_OPENED"

# The request record. `max_iterations` is optional (rule 1); every other field is
# mandatory, which is exactly what the fail-closed contract needs: a campaign
# with no identity, no bench, no rounds, no pairing design or no evidence is not
# a campaign. `project_reference`, `source` and `evidence_id` are request-level
# provenance -- campaign.schema.json carries none of the three.
REQUEST_FIELDS = {
    "campaign_id", "project_reference", "bench_references", "max_iterations",
    "current_iteration", "iterations", "pairing_design", "evidence_scope",
    "source", "evidence_id", "evidence",
}
REQUIRED_REQUEST_FIELDS = REQUEST_FIELDS - {"max_iterations"}

# The fields a built artifact carries (campaign.schema.json, unevaluatedProperties
# false): the record the validator can re-derive every judgement from.
RECORD_FIELDS = {
    "campaign_id", "bench_references", "max_iterations", "current_iteration",
    "iterations", "pairing_design", "evidence_scope", "evidence",
}
ARTIFACT_FIELDS = {
    "schema_version", "artifact_type", "project_id", "stage",
    "decision_question", "hypothesis", "uncertainty", "evidence",
    "decision_rule", "result", "decision", "next_action",
    *RECORD_FIELDS,
}

ITERATION_FIELDS = {
    "iteration", "samples", "stop_state", "screening_reference",
    "variance_reference", "model_reference", "next_batch_reference",
    "bench_test_references",
}
REQUIRED_ITERATION_FIELDS = {"iteration", "samples", "stop_state"}
REFERENCE_FIELDS = ("screening_reference", "variance_reference", "model_reference", "next_batch_reference")
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


def is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_positive_int(value: object) -> bool:
    return is_int(value) and value >= 1


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
    """The campaign's iteration cap: the supplied value, or the contract's.

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
            "supplied in the campaign request, so the campaign is bounded by the contract's published figure "
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


def has_gap(record: object) -> bool:
    evidence = record.get("evidence") if isinstance(record, dict) else None
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("status") == "GAP" for item in evidence
    )


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


def iteration_errors(iterations: object, cap: object) -> list[str]:
    if not isinstance(iterations, list) or not iterations:
        return ["campaign.iterations must be a non-empty array"]
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
        for field in REFERENCE_FIELDS:
            if field in entry and entry.get(field) is not None and not has_text(entry.get(field)):
                errors.append(f"{label}.{field} must be a non-empty string or null")
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


def bench_reference_errors(references: object) -> list[str]:
    if not isinstance(references, list) or not references:
        return ["campaign.bench_references must be a non-empty array of bench ids"]
    errors: list[str] = []
    if not all(has_text(item) for item in references):
        errors.append("campaign.bench_references must be a non-empty array of bench ids")
    elif len(set(references)) != len(references):
        errors.append("campaign.bench_references must not repeat a bench id")
    return errors


def record_errors(record: object, *, cap: object, forbid_provenance_item: bool) -> list[str]:
    """Every record-level rule, in one place for the request and the artifact.

    ``forbid_provenance_item`` is True for the request (the caller may not forge
    the reserved contract-default marker) and False for a built artifact (which
    is where that item legitimately appears).
    """
    if not isinstance(record, dict):
        return ["campaign must be a JSON object"]
    errors: list[str] = []
    if not has_text(record.get("campaign_id")):
        errors.append("campaign.campaign_id")
    errors.extend(bench_reference_errors(record.get("bench_references")))
    if not is_positive_int(record.get("current_iteration")):
        errors.append("campaign.current_iteration must be a positive integer (bench round, 1-based)")
    errors.extend(iteration_errors(record.get("iterations"), cap))
    errors.extend(pairing_errors(record.get("pairing_design")))
    if record.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("campaign.evidence_scope must be SYNTHETIC or PHYSICAL")
    errors.extend(evidence_errors(record.get("evidence"), forbid_provenance_item=forbid_provenance_item))
    errors.extend(cross_field_errors(record, cap))
    if not errors and has_gap(record):
        errors.append("campaign.evidence contains GAP; current input is insufficient")
    return errors


def cross_field_errors(record: object, cap: object) -> list[str]:
    """The rules the schema cannot express, enforced here and reported by name.

    campaign.schema.json says so itself: pure JSON Schema has no keyword that
    compares two instance numbers, so `current_iteration <= max_iterations` is
    validator-enforced rather than structural (top-level description, the
    `$comment` on max_iterations, and the schema's own `$comment`).
    """
    errors: list[str] = []
    current = record.get("current_iteration") if isinstance(record, dict) else None
    if is_positive_int(current) and is_positive_int(cap) and current > cap:
        errors.append(f"campaign.current_iteration {current} must not exceed max_iterations {cap}")
    iterations = record.get("iterations") if isinstance(record, dict) else None
    if isinstance(iterations, list) and is_positive_int(current) and len(iterations) > current:
        errors.append(
            f"campaign.current_iteration {current} is before the {len(iterations)} round(s) this campaign "
            "already records"
        )
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
        errors.append(f"campaign.evidence must carry at most one {MAX_ITERATIONS_EVIDENCE_ID} item")
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


def expected_decision_fields(record: dict, cap: int, defaulted: bool) -> dict[str, str]:
    """The canonical decision block. Pure function of the artifact's own fields."""
    campaign_id = record.get("campaign_id", "")
    iterations = record.get("iterations") if isinstance(record.get("iterations"), list) else []
    rounds = len(iterations)
    newest = iterations[-1].get("stop_state") if rounds and isinstance(iterations[-1], dict) else None
    benches = record.get("bench_references") if isinstance(record.get("bench_references"), list) else []
    current = record.get("current_iteration")
    within_cap = is_positive_int(current) and is_positive_int(cap) and current <= cap
    open_loop = newest == CONTINUE
    gap = has_gap(record)
    ready = (not gap) and within_cap and open_loop
    cap_source = f"defaulted from {CONTRACT_SOURCE}" if defaulted else "supplied in the request"
    if gap:
        reason = "an evidence item is GAP"
    elif not within_cap:
        reason = f"current_iteration {current} exceeds max_iterations {cap}"
    else:
        reason = f"the newest recorded round ended {newest}, and only {CONTINUE} authorizes another round"
    return {
        "decision_question": f"May campaign {campaign_id} keep the inner bench loop open for another bench round?",
        "hypothesis": (
            f"{campaign_id} records its rounds, their stop states and its paired design, so the inner loop can "
            f"run up to {cap} bench rounds over bench {', '.join(benches)}."
        ),
        "uncertainty": (
            "The registered bench availability is supplied, not booked or qualified, and this record reserves no "
            "capacity; the campaign's rounds are recorded as they happened, and a later round's outcome is not "
            "known before it runs."
        ),
        "decision_rule": (
            f"Keep the loop open (GO) only when the newest recorded round ended {CONTINUE}, current_iteration is "
            "within max_iterations, and no evidence item is GAP."
        ),
        "result": (
            f"Campaign {campaign_id} holds {rounds} recorded round(s) and stands at iteration {current} of {cap} "
            f"(max_iterations={cap}, {cap_source}); the newest recorded round ended {newest}."
        ),
        "decision": "GO" if ready else "HOLD",
        "next_action": (
            f"Open bench round {current} of {cap} with the pairing design recorded above."
            if ready
            else f"Do not open another bench round: {reason}."
        ),
    }


def decision_errors(artifact: dict) -> list[str]:
    """Re-derive the decision block from the artifact and require an exact match."""
    cap = artifact.get("max_iterations")
    record = {field: artifact.get(field) for field in RECORD_FIELDS}
    defaulted = defaulted_from_evidence(artifact.get("evidence"))
    return [
        f"{field} must equal the deterministic campaign policy"
        for field, value in expected_decision_fields(record, cap, defaulted).items()
        if artifact.get(field) != value
    ]


def policy_errors(artifact: object) -> list[str]:
    """Everything the validator re-derives from a built campaign artifact."""
    if not isinstance(artifact, dict):
        return ["artifact must be a JSON object"]
    errors: list[str] = []
    if set(artifact) != ARTIFACT_FIELDS:
        extra = sorted(set(artifact) - ARTIFACT_FIELDS)
        missing = sorted(ARTIFACT_FIELDS - set(artifact))
        errors.append(f"artifact must contain exactly the campaign fields; unexpected={extra or 'none'} missing={missing or 'none'}")
        return errors
    cap = artifact.get("max_iterations")
    record = {field: artifact.get(field) for field in RECORD_FIELDS}
    errors.extend(record_errors(record, cap=cap, forbid_provenance_item=False))
    errors.extend(provenance_errors(artifact.get("evidence"), cap))
    errors.extend(decision_errors(artifact))
    return errors
