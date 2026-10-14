"""Deterministic projection and decision wording for one NEXT_BATCH_DECIDED record.

Step 13b of the precision-grease inner loop decides *which samples the next round runs*
and *whether the loop continues at all* (schemas/next_batch.schema.json). Everything
deterministic about that record lives here so the builder, the preflight and the validator
cannot disagree:

* the stop-state vocabulary and the variance-verdict vocabulary are mirrored here as one
  list each -- the preflight asserts the stop-state mirror against the enum in
  ``next_batch.schema.json``, so a widened contract cannot drift away from this module
  silently;
* ``composed_sample`` turns a *declared* explanation into the artifact's sample entry.
  This is the anti-fabrication rule of this stage: the artifact's ``hypothesis`` is the
  statement of a declared explanation and ``discriminates`` is two declared statements
  joined by the separator the schema's own example uses ("... vs ..."). No word of the
  discrimination is invented here -- an input that declares no competing explanations is
  held, never filled in;
* ``expected_decision_fields`` derives the canonical decision block from the record's own
  fields, so the validator can re-derive it and a hand-edited artifact fails.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence


# The six values shared by the merged bench artifact's iteration stop_state
# (bench.schema.json, whose iteration_entry carries the inner-loop round ledger) and
# next_batch.schema.json's stop_state. Only CONTINUE authorizes another round, so only
# CONTINUE makes this record a GO; every other value stops the loop and must carry its
# reason in stop_rationale.
CONTINUE = "CONTINUE"
STOP_STATES = (
    "CONTINUE",
    "GOAL_MET",
    "NO_NEW_INFORMATION",
    "RESOURCE_EXHAUSTED",
    "PIVOT",
    "KILL",
)

# The three fields that make up the next round's proposal. They exist only while the loop
# continues (next_batch.schema.json's second if/then rule, E2=B): a stop opens no round,
# proposes no sample and spends no bench slot, so it carries none of them and records its
# cause in stop_rationale instead. Enforced in both directions by proposal_field_errors.
PROPOSAL_FIELDS = ("proposed_samples", "information_gain_basis", "bench_slots_required")

# The pair separator: next_batch.schema.json's own example of the ``discriminates`` field
# is "'A explains the result' vs 'B explains the result'", so the composed form uses the
# same spelling. Every word but this separator is text the input declared.
DISCRIMINATION_SEPARATOR = " vs "

# The four frozen verdicts of a variance record (variance.schema.json, owned by
# variance-assessment). Read here only to print the routing note the variance skill
# itself publishes; this module never re-derives a statistic and never softens a verdict.
VARIANCE_VERDICTS = (
    "CONSISTENT_DIFFERENCE",
    "NO_DETECTABLE_DIFFERENCE",
    "UNDERPOWERED",
    "REPLICATE_INCONSISTENT",
)
VARIANCE_ROUTING_NOTES = {
    "CONSISTENT_DIFFERENCE": (
        "the round's difference is real and the same-arm replicates agree; the next round may build on it "
        "(and the campaign stops with NO_NEW_INFORMATION if the difference already sits inside the model's "
        "prediction interval, so another round would re-learn it)"
    ),
    "NO_DETECTABLE_DIFFERENCE": (
        "the design was capable and found nothing; the direction is excluded, so the next round must change "
        "the candidate or the criterion instead of repeating this one"
    ),
    "UNDERPOWERED": (
        "the design could not have answered the question at this resolution; the recovery is to change the "
        "METHOD or the criterion (SIGMA_MAX = delta / k), never to add samples -- 'we cannot measure it' is "
        "not 'there is no difference'"
    ),
    "REPLICATE_INCONSISTENT": (
        "same-arm replicates contradict or share a sample identity across batches, so no difference claim is "
        "admissible from this round; repair the replicate structure before deciding another round"
    ),
}


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_count(value: object, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def statement_map(explanations: object) -> dict[str, str]:
    """Map every declared explanation_id onto its statement text.

    Only entries that are well-formed objects with a non-empty id and statement are
    admitted; the preflight reports the malformed ones separately, so this map is used
    for composition, never as the validator of the input.
    """
    statements: dict[str, str] = {}
    for item in explanations if isinstance(explanations, Sequence) and not isinstance(explanations, str) else []:
        if not isinstance(item, Mapping):
            continue
        explanation_id, statement = item.get("explanation_id"), item.get("statement")
        if has_text(explanation_id) and has_text(statement):
            statements[explanation_id] = statement
    return statements


def composed_sample(sample: Mapping[str, object], statements: Mapping[str, str]) -> dict:
    """The artifact form of one proposed sample, with no invented discrimination text.

    ``hypothesis`` is the declared statement of the one hypothesis the sample is run to
    discriminate; ``discriminates`` is the sample's declared pair, spelled out as the two
    declared statements joined by the schema's own separator. A citation that does not
    resolve to a declared explanation resolves to an empty string here -- the preflight
    refuses that input long before the builder runs, and the empty string would fail the
    schema's minLength 1 rather than pass quietly.
    """
    separates = sample.get("separates")
    pair = [item for item in separates if isinstance(item, str)] if isinstance(separates, Sequence) and not isinstance(separates, str) else []
    entry: dict = {}
    for field in ("sample_reference", "formula_reference"):
        if has_text(sample.get(field)):
            entry[field] = sample[field]
    entry["hypothesis"] = statements.get(sample.get("hypothesis"), "")
    entry["discriminates"] = DISCRIMINATION_SEPARATOR.join(
        statements.get(item, "") for item in pair[:2]
    )
    return entry


def stop_rationale_errors(record: Mapping[str, object], label: str = "next_batch") -> list[str]:
    """Both directions of the contract's stop-reason rule.

    The schema's if/then enforces one direction (a stop needs a reason). The schema's own
    description states the other one -- ``stop_rationale`` is "omitted when the loop
    continues" -- so a record that both continues and explains why it would stop is
    refused here: a record says one thing per state.
    """
    stop_state = record.get("stop_state")
    rationale = record.get("stop_rationale")
    if stop_state not in STOP_STATES:
        # A missing or unknown stop_state is reported by the vocabulary check; this rule
        # only speaks about a value the contract defines.
        return []
    if stop_state == CONTINUE:
        if rationale is not None:
            return [
                f"{label}.stop_rationale must be omitted while stop_state is CONTINUE: the contract records a "
                "reason only for a stop"]
        return []
    if has_text(rationale):
        return []
    return [
        f"{label}.stop_rationale is required when stop_state is {stop_state}: stopping the loop is a decision "
        "like any other and must record why it stopped"]


def proposal_field_errors(record: Mapping[str, object], label: str = "next_batch") -> list[str]:
    """Both directions of the CONTINUE-only proposal rule (E2=B), as readable refusals.

    The schema's second if/then rule enforces the same thing structurally; this function is
    the wording layer for the request (which never reaches the artifact schema) and for the
    committed record (which the validator re-derives): while the loop continues the record
    must carry ``proposed_samples`` / ``information_gain_basis`` / ``bench_slots_required``;
    on any stop it must carry none of the three, because a stop opens no round, proposes no
    sample and spends no bench slot. A stop records its cause in ``stop_rationale`` instead --
    the two rules are mirror images of one another.
    """
    stop_state = record.get("stop_state")
    if stop_state not in STOP_STATES:
        # An unknown stop_state is reported by the vocabulary check; this rule only speaks
        # about a value the contract defines.
        return []
    if stop_state == CONTINUE:
        missing = [field for field in PROPOSAL_FIELDS if field not in record]
        if not missing:
            return []
        return [
            f"{label}.{', '.join(missing)} must be recorded while stop_state is CONTINUE: the round is opened by "
            "this decision and cannot be opened without the samples it would run, why they are informative and "
            "what they cost"
        ]
    present = [field for field in PROPOSAL_FIELDS if field in record]
    if not present:
        return []
    return [
        f"{label}.{', '.join(present)} must be omitted while stop_state is {stop_state}: a stop opens no round, "
        "proposes no sample and spends no bench slot; it records its cause in stop_rationale instead"
    ]


def expected_decision_fields(record: Mapping[str, object], campaign_id: str) -> dict[str, str]:
    """Canonical decision fields for one next-batch record (pure function of the record).

    Derived, never asserted: only CONTINUE authorizes another round, so only CONTINUE
    makes this record a GO. Every stop value is a HOLD -- a truthful record that no
    further bench round is authorized -- exactly as a variance record with an incapable
    design is a truthful HOLD rather than a failure.
    """
    batch_id = record.get("next_batch_id", "")
    stop_state = record.get("stop_state", "")
    from_iteration = record.get("from_iteration", "")
    to_iteration = record.get("to_iteration", "")
    samples = record.get("proposed_samples")
    sample_count = len(samples) if isinstance(samples, Sequence) and not isinstance(samples, str) else 0
    slots = record.get("bench_slots_required", "")
    continuing = stop_state == CONTINUE
    return {
        "decision_question": (
            f"Which samples should inner-loop round {to_iteration} run next, and does the campaign continue "
            f"past round {from_iteration}?"),
        "hypothesis": (
            f"{batch_id} records the supplied round-{to_iteration} proposal for campaign {campaign_id}: "
            f"{sample_count} proposed sample(s) at {slots} bench slot(s), each separating a declared pair of "
            "competing explanations."
            if continuing else
            f"{batch_id} records the supplied stop for campaign {campaign_id} at the round-{from_iteration} "
            f"boundary: the loop closes with stop_state {stop_state} and its recorded reason, so no round "
            "follows and no bench slot is proposed."),
        "uncertainty": (
            "The supplied proposed samples, competing explanations, information-gain basis, bench-slot "
            "requirement and stop state are planning statements that are not independently verified; this "
            "record establishes no sample, formula, measurement, result, cost, statistical sufficiency or "
            "bench capacity, and the declared bench slots reserve no capacity."),
        "decision_rule": (
            "Open the next round only while stop_state is CONTINUE, the campaign's own iteration entry agrees "
            "with this decision, and every proposed sample separates two declared competing explanations; any "
            "other stop_state records its reason in stop_rationale."
            if continuing else
            "The loop stays open only while stop_state is CONTINUE, the campaign's own iteration entry agrees "
            "with this decision, and every proposed sample separates two declared competing explanations; this "
            "record's stop_state is not CONTINUE, so it carries no proposal and records its reason in "
            "stop_rationale."),
        "result": (
            f"Round {to_iteration} is opened with {sample_count} proposed sample(s) requiring {slots} bench "
            f"slot(s); the round boundary ends with stop_state {stop_state}."
            if continuing else
            f"No round follows the round-{from_iteration} boundary: the loop closes with stop_state {stop_state} "
            "and its recorded reason."),
        "decision": "GO" if continuing else "HOLD",
        "next_action": (
            f"Hand the {sample_count} proposed sample(s) to the doe-design step as the round-{to_iteration} "
            "request without adding samples, and size the round to the registered bench capacity."
            if continuing else
            f"Stop the inner loop at round {from_iteration} with stop_state {stop_state} and retain the recorded "
            "reason; no further bench round is opened."),
    }
