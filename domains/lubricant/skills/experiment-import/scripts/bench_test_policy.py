"""Deterministic bench-test policy: the censoring discipline of the precision-grease inner loop.

Step 11 of the PRECISION_GREASE_DEV route (skill ``experiment-import``, stage
``BENCH_TESTED``) records ONE bench run. The bench is the only source of real performance
evidence for a grease and the scarcest resource of the campaign (about two positions per
round and roughly 30 days per round), so the quality of this record decides whether the
inner loop can converge at all. This module is the single place where that record is
judged, and it is shared by the preflight, the builder and the validator so the three
scripts cannot disagree about the same input.

**The censoring discipline is the point of this module, and it has real-case provenance.**
``WGO_001_S1_BENCH_METHOD_QUALIFICATION_PLAN.md`` states that "right-censored 10h
observations NEVER treated as event_time=10h". A run that reached the end of its window
without an event tells us only that no event happened *inside* the window; the window
length is a censoring time, not an end-point. Once such a value is written as an
end-point, the variance estimate is wrong and every downstream conclusion built on it is
void. This is red line 3 of the development guide (删失不得当终点).

Four rules for the run record, all fail-closed. The first two mirror the if/then rules of
``schemas/bench_test.schema.json``; the last two are stricter on purpose and say so:
1. A CENSORING TIME IS NEVER AN END-POINT (schema rule (i)). ``event_occurred: false``
   forces ``event_time: null``, whatever the ``censoring_type`` says. A right-censored
   10 h observation is refused, never reinterpreted as a completed run.

2. A CENSORED OBSERVATION MUST DECLARE WHY IT STOPPED (schema rule (ii)). Any
   ``censoring_type`` other than ``NONE`` requires a non-empty ``stop_reason``: an
   unexplained stop is not an observation, and administrative censoring must never be
   presented silently as a finished run.

3. A RUN THAT PRODUCED NO EVENT MUST ALSO DECLARE WHY IT STOPPED. Stricter than the
   schema, which only forces ``stop_reason`` for a non-NONE censoring type. A
   ``censoring_type: NONE`` record with ``event_occurred: false`` is a run that ended
   without an event and without declaring any censoring, so it must still say why it
   ended. Otherwise the record that looks most like a completed run is exactly the one
   carrying no explanation.

4. AN EVENT CLAIM MUST CARRY ITS TIME. ``event_occurred: true`` requires a numeric
   ``event_time`` >= 0, which is what the schema's own description states ("event time in
   hours when event_occurred is true"). An event without a time is not an end-point
   either, and it would be silently unusable by the variance assessment downstream.

5. A BENCH SLOT IS SPENT ONLY ON A SCREENED SAMPLE (E-3 / L5). The request names the
   screening artifacts of the round, and the run's ``sample_reference`` must fall on a
   supplied screening whose ``overall_verdict`` is ``PASS`` with
   ``gate_to_bench: RELEASED``. Until now the rule "a failed screen must not occupy a
   bench slot" was enforced only by the screening side refusing a ``bench_request`` for
   its own sample (N14 of grease-screening): the bench record itself never resolved its
   screening reference, so a sample recorded as FAIL/BLOCKED could still be documented
   as having consumed a slot. The bench is the scarcest resource of the loop, so this
   gate resolves the reference and refuses the run instead of trusting a path.

The modeling entry's observed-CTQ link is also carried here: since step 14
(statistical-analysis) consumes the round's bench records on the grease route, the run
records WHICH CTQ it observed in ``ctq_reference`` -- the artifact's ``response_references``
are checked against exactly that field. It is a plain structural field of the record.

Nothing is invented anywhere: the record is projected field by field into the artifact,
the canonical decision block is derived from the artifact's own fields, and the run's
``decision`` is UNDECIDED because one run is a record, not a verdict. Whether the round's
difference is real is decided at Step 12 (variance-assessment), never here.
"""

from __future__ import annotations

import math

# Input: the upstream charter, the bench-run record, the screening records that released
# the run's sample, and the artifact-level evidence. ``bench_test`` is the record; the
# artifact-level fields (schema_version, artifact_type, project_id, stage,
# decision_question, hypothesis, uncertainty, decision_rule, result, decision,
# next_action) are DERIVED by this module and supplying any of them is a hard reject,
# exactly like the aggregate verdict in grease-screening.
BENCH_INPUT_FIELDS = frozenset({"project_artifact", "bench_test", "screening_artifacts", "evidence_scope", "evidence"})

# The bench-run record, mirroring the field set of schemas/bench_test.schema.json.
# ``stop_reason`` may be absent from the INPUT (an uncensored run may carry no stop
# reason), but it is always written into the artifact (null when absent), so it is in the
# allowed set and not in the required set. ``ctq_reference`` is required: the modeling
# entry (step 14) links the round's response references to the CTQ its bench runs
# recorded, so a run that does not say which CTQ it observed cannot be modeled.
BENCH_RECORD_INPUT_FIELDS = frozenset(
    {
        "run_id",
        "bench_reference",
        "batch_reference",
        "sample_reference",
        "ctq_reference",
        "protocol_version",
        "setpoints",
        "environment",
        "raw_record_reference",
        "event_occurred",
        "event_time",
        "censoring_type",
        "stop_reason",
        "anomalies",
        "campaign_iteration",
    }
)
BENCH_RECORD_REQUIRED_INPUT_FIELDS = BENCH_RECORD_INPUT_FIELDS - {"stop_reason"}
DERIVED_ARTIFACT_FIELDS = (
    "schema_version",
    "artifact_type",
    "project_id",
    "stage",
    "evidence_scope",
    "decision_question",
    "hypothesis",
    "uncertainty",
    "evidence",
    "decision_rule",
    "result",
    "decision",
    "next_action",
)
# The run identity the step-11 release criterion names: every run must hang its bench, its
# batch, its sample, the frozen protocol version and the raw record it was distilled from.
IDENTITY_FIELDS = (
    "run_id",
    "bench_reference",
    "batch_reference",
    "sample_reference",
    "protocol_version",
    "raw_record_reference",
)
EVIDENCE_FIELDS = {"evidence_id", "statement", "source", "status"}
EVIDENCE_STATUSES = ("OBSERVED", "ASSUMED", "GAP")
EVIDENCE_SCOPES = ("SYNTHETIC", "PHYSICAL")
ENVIRONMENT_FIELDS = {"temperature_c", "humidity_percent"}
CENSORING_TYPES = ("RIGHT", "LEFT", "INTERVAL", "NONE")
BENCH_TEST_STAGE = "BENCH_TESTED"
BENCH_TEST_ARTIFACT_TYPE = "bench_test"

# The grease route gate. BENCH_TESTED sits on no oil route (contracts/state-machine.json
# declares it only under PRECISION_GREASE_DEV), so a bench run recorded against a charter
# that does not route as the precision-grease campaign would materialise a stage the route
# never had. Fail-closed: HOLD, and the message names the route.
ROUTED_PROJECT_TYPE = "PRECISION_GREASE_DEV"
REROUTE_HOLD = (
    "the bench run is the PRECISION_GREASE_DEV inner loop (step 11); BENCH_TESTED is on no oil route"
)

# The two schema rules, quoted so every reason this module gives is traceable to
# schemas/bench_test.schema.json's own if/then comments.
SCHEMA_PATH = "schemas/bench_test.schema.json"
CENSORING_CITATION = (
    f"{SCHEMA_PATH} if/then rule (i): censoring_type RIGHT forces event_occurred false and "
    "event_time null; a censoring time is never an end-point value"
)
STOP_REASON_CITATION = (
    f"{SCHEMA_PATH} if/then rule (ii): any censoring_type other than NONE requires a non-empty "
    "stop_reason"
)
DISCIPLINE_STATEMENT = (
    "a right-censored observation is recorded as event_occurred=false with event_time=null and a "
    "declared stop_reason, never as an end-point value; once a censoring time is mixed in as an "
    "end-point the variance estimate is wrong and every downstream conclusion is void"
)


def is_bench_request(data: object) -> bool:
    """True when the request is unambiguously a bench-run request.

    The skill serves two artifact kinds through one gate, so the entry point must be
    selected without ever re-routing a request the experiment path already judged. Every
    experiment request carries the ``experiment`` record (it is the path's required
    field), so a request that carries one stays on the experiment path even if it also
    carries a stray ``bench_test`` key -- that stray key then produces exactly the
    ``unexpected=['bench_test']`` HOLD it produced before this path existed.
    """
    return isinstance(data, dict) and "bench_test" in data and "experiment" not in data


def has_text(value: object) -> bool:
    """True for a non-empty, non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_non_negative_number(value: object) -> bool:
    return is_finite_number(value) and value >= 0


def is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def scope_prefix(evidence_scope: object) -> str:
    return (
        "Synthetic test fixture / NOT_FOR_PHYSICAL_EXECUTION: this record cannot authorize stage advancement. "
        if evidence_scope == "SYNTHETIC"
        else ""
    )


def environment_errors(environment: object) -> list[str]:
    """Ambient conditions, mirroring the schema's required pair and additionalProperties: false."""
    label = "bench_test.environment"
    if not isinstance(environment, dict):
        return [f"{label} must be an object recording the ambient conditions of the run"]
    unknown = sorted(set(environment) - ENVIRONMENT_FIELDS)
    missing = sorted(ENVIRONMENT_FIELDS - set(environment))
    if unknown or missing:
        return [
            f"{label} must contain exactly temperature_c and humidity_percent; "
            f"unexpected={unknown or 'none'} missing={missing or 'none'}"
        ]
    errors: list[str] = []
    if not is_finite_number(environment.get("temperature_c")):
        errors.append(f"{label}.temperature_c must be a number in degC")
    humidity = environment.get("humidity_percent")
    if not is_finite_number(humidity) or not 0 <= float(humidity) <= 100:
        errors.append(f"{label}.humidity_percent must be a number between 0 and 100")
    return errors


def setpoints_errors(setpoints: object) -> list[str]:
    if not isinstance(setpoints, list) or not setpoints:
        return ["bench_test.setpoints must be a non-empty array of the run's fixed setpoints"]
    errors: list[str] = []
    for index, setpoint in enumerate(setpoints):
        if not has_text(setpoint):
            errors.append(f"bench_test.setpoints[{index}] must be a non-empty string")
    return errors


def anomalies_errors(anomalies: object) -> list[str]:
    if not isinstance(anomalies, list):
        return ["bench_test.anomalies must be an array (an empty array records 'none observed')"]
    errors: list[str] = []
    for index, item in enumerate(anomalies):
        if not has_text(item):
            errors.append(f"bench_test.anomalies[{index}] must be a non-empty string")
    return errors


def censoring_errors(record: object) -> list[str]:
    """The censoring discipline: rules 1-4 of the module docstring, all fail-closed.

    Applied to the input record and re-applied to the frozen artifact, so a hand-edited
    artifact cannot slip a censoring time in as an end-point after the gate has passed.
    """
    if not isinstance(record, dict):
        return ["bench_test must be an object"]
    errors: list[str] = []
    censoring_type = record.get("censoring_type")
    event_occurred = record.get("event_occurred")
    event_time = record.get("event_time")
    stop_reason = record.get("stop_reason")
    if censoring_type not in CENSORING_TYPES:
        errors.append(f"bench_test.censoring_type must be one of {', '.join(CENSORING_TYPES)}")
    if not isinstance(event_occurred, bool):
        errors.append(
            "bench_test.event_occurred must be a boolean (false means the run produced no event "
            "inside the observation window)"
        )
    if event_time is not None and not is_non_negative_number(event_time):
        errors.append(
            "bench_test.event_time must be a number of hours >= 0, or null when no event occurred"
        )
    # Rule 1: no event means no end-point, whatever the censoring label says.
    if event_occurred is False and event_time is not None:
        errors.append(
            f"bench_test: censored observation must not carry an event_time: recorded "
            f"event_occurred=false with event_time={event_time!r}; a censoring time is never an "
            f"end-point value ({CENSORING_CITATION})"
        )
    # Rule 4: an event claim must carry its time.
    if event_occurred is True and not is_non_negative_number(event_time):
        errors.append(
            "bench_test: event_occurred=true requires a numeric event_time >= 0 in hours; recorded "
            f"event_time={event_time!r}. An event without a time is not an end-point either"
        )
    if censoring_type in ("RIGHT", "LEFT", "INTERVAL"):
        # Rule 1, RIGHT-specific: the schema's own rule, quoted.
        if censoring_type == "RIGHT" and (event_occurred is not False or event_time is not None):
            errors.append(
                f"bench_test: censored observation must not carry an event_time: a RIGHT-censored run is "
                f"never recorded as an end-point value; recorded event_occurred={event_occurred!r} "
                f"event_time={event_time!r} ({CENSORING_CITATION})"
            )
        elif event_occurred is True:
            errors.append(
                f"bench_test is censored ({censoring_type}) but claims event_occurred=true: an event "
                "that occurred is not censored"
            )
        # Rule 2: a censored observation without a stop_reason is refused.
        if not has_text(stop_reason):
            errors.append(
                f"bench_test: censored observation without a stop_reason is refused: an unexplained stop "
                f"is not an observation; a {censoring_type}-censored run must declare why it stopped "
                f"({STOP_REASON_CITATION})"
            )
    elif censoring_type == "NONE" and event_occurred is False and not has_text(stop_reason):
        # Rule 3, stricter than the schema: no event and no censoring declared still needs a reason.
        errors.append(
            "bench_test: the run produced no event (event_occurred=false) and declares no censoring "
            "(censoring_type NONE) without a stop_reason: the record must state why the run ended "
            "(for example 'ran to the end of the protocol window without the defined event'); an "
            "unexplained stop is not an observation"
        )
    return errors


def record_field_errors(record: object) -> list[str]:
    """Shape checks on the bench-run record, shared by the input gate and the validator."""
    if not isinstance(record, dict):
        return ["bench_test must be an object"]
    errors: list[str] = []
    for field in IDENTITY_FIELDS:
        if not has_text(record.get(field)):
            errors.append(
                f"bench_test.{field} is required: every bench run must hang its run id, its bench, its "
                "batch, its sample, the frozen protocol version and the raw record it was distilled from"
            )
    if not has_text(record.get("ctq_reference")):
        errors.append(
            "bench_test.ctq_reference is required: the run must record which CTQ it observed, because the "
            "modeling entry (step 14) links its response references to the CTQs the round's bench runs "
            "actually recorded"
        )
    errors.extend(setpoints_errors(record.get("setpoints")))
    errors.extend(environment_errors(record.get("environment")))
    errors.extend(anomalies_errors(record.get("anomalies")))
    if not is_positive_int(record.get("campaign_iteration")):
        errors.append(
            "bench_test.campaign_iteration must be a strictly positive integer: which inner-loop round "
            "this run belongs to is part of the record, not an inference"
        )
    errors.extend(censoring_errors(record))
    return errors


def bench_record_errors(record: object) -> list[str]:
    """Everything wrong with a bench-run record that is already known to be a record."""
    if not isinstance(record, dict):
        return ["bench_test must be an object"]
    return record_field_errors(record)


def input_record_errors(record: object) -> list[str]:
    """The input-side gate: derived fields, field set, then the record's own rules."""
    if not isinstance(record, dict):
        return ["bench_test must be an object"]
    supplied = derived_field_errors(record)
    if supplied:
        return supplied
    unknown = sorted(set(record) - BENCH_RECORD_INPUT_FIELDS)
    missing = sorted(BENCH_RECORD_REQUIRED_INPUT_FIELDS - set(record))
    if unknown or missing:
        return [
            "bench_test must contain only the bench-run input fields; "
            f"unexpected={unknown or 'none'} missing={missing or 'none'}"
        ]
    return record_field_errors(record)


def derived_field_errors(record: object) -> list[str]:
    """The artifact-level fields are derived and must never be supplied."""
    if not isinstance(record, dict):
        return []
    supplied = sorted(set(record) & set(DERIVED_ARTIFACT_FIELDS))
    if not supplied:
        return []
    return [
        "bench_test."
        + " and bench_test.".join(supplied)
        + " are derived by bench_test_policy and must not be supplied; the run's decision block is "
        "computed from the recorded observation"
    ]


def record_projection(record: object) -> dict:
    """Project the input record into its artifact form, field by field, inventing nothing.

    ``stop_reason`` is written as null when the run did not carry one, so the artifact
    states "no reason recorded" explicitly instead of leaving the field to guesswork.
    """
    if not isinstance(record, dict):
        return {}
    return {
        field: record.get(field)
        for field in (
            "run_id",
            "bench_reference",
            "batch_reference",
            "sample_reference",
            "ctq_reference",
            "protocol_version",
            "setpoints",
            "environment",
            "raw_record_reference",
            "event_occurred",
            "event_time",
            "censoring_type",
            "stop_reason",
            "anomalies",
            "campaign_iteration",
        )
    }


def recorded_record(artifact: object) -> dict:
    """Project a STORED bench_test artifact back to the record form the policy judges.

    The validator sees only the artifact, so this is what lets it re-run exactly the gate
    rules (including the censoring discipline) instead of keeping a second copy of them.
    """
    if not isinstance(artifact, dict):
        return {}
    return {field: artifact.get(field) for field in BENCH_RECORD_INPUT_FIELDS}


def censoring_notes(record: object) -> list[str]:
    """One audible line stating the observation exactly as recorded, plus the discipline."""
    if not isinstance(record, dict):
        return []
    lines = [
        f"NOTE: bench run {record.get('run_id')} censoring_type={record.get('censoring_type')} "
        f"event_occurred={record.get('event_occurred')} event_time={record.get('event_time')} "
        f"stop_reason={record.get('stop_reason')}"
    ]
    if record.get("censoring_type") in ("RIGHT", "LEFT", "INTERVAL") or record.get("event_occurred") is False:
        lines.append(f"NOTE: {DISCIPLINE_STATEMENT}")
    return lines


def expected_decision_fields(record: object, evidence_scope: object) -> dict[str, str]:
    """The canonical bench-run decision block, recomputed identically by builder and validator.

    A pure function of the artifact's own fields, so the validator needs nothing else. The
    decision is UNDECIDED on purpose: a single bench run is a record, and whether the
    round's difference is real is decided at Step 12 (variance-assessment).
    """
    if not isinstance(record, dict):
        record = {}
    run_id = record.get("run_id")
    censoring_type = record.get("censoring_type")
    event_occurred = record.get("event_occurred")
    event_time = record.get("event_time")
    stop_reason = record.get("stop_reason")
    protocol_version = record.get("protocol_version")
    iteration = record.get("campaign_iteration")
    if event_occurred is True:
        result = (
            f"run {run_id}: the defined event occurred at {event_time} h inside the observation window "
            f"under protocol {protocol_version}; recorded as an end-point observation."
        )
    elif censoring_type in ("RIGHT", "LEFT", "INTERVAL"):
        result = (
            f"run {run_id}: {censoring_type}-censored, no event inside the observation window; "
            f"event_time is null and the stop is recorded ({stop_reason}). The window length is not an "
            "end-point."
        )
    else:
        result = (
            f"run {run_id}: no event inside the observation window and no censoring declared; "
            f"event_time is null and the stop is recorded ({stop_reason})."
        )
    return {
        "decision_question": (
            f"Did bench run {run_id} produce the defined event inside the observation window under "
            f"protocol {protocol_version}?"
        ),
        "hypothesis": (
            "The run either produces the defined event inside the window or ends without it, in which case "
            "the observation is recorded as censored rather than as an end-point value."
        ),
        "uncertainty": (
            f"{scope_prefix(evidence_scope)}A single bench run records what the bench actually did; it does "
            "not by itself separate bench-to-bench drift from a formulation effect, and it is not a product "
            f"performance conclusion. censoring_type={censoring_type}."
        ),
        "decision_rule": (
            "Record the observation exactly as it happened: a right-censored run is never recorded or used "
            f"as an end-point value, and every censored or event-free run declares why it stopped "
            f"({CENSORING_CITATION}; {STOP_REASON_CITATION})."
        ),
        "result": result,
        "decision": "UNDECIDED",
        "next_action": (
            f"Hand run {run_id} to the variance assessment of campaign iteration {iteration} (Step 12) "
            "exactly as recorded; do not use the observation window length as an event time."
        ),
    }


def bench_test_artifact(record: object, project: dict, evidence_scope: object, evidence: object) -> dict:
    """Assemble the BENCH_TESTED artifact. Deterministic assembly only."""
    artifact = {
        "schema_version": "0.1.0",
        "artifact_type": BENCH_TEST_ARTIFACT_TYPE,
        "project_id": project["project_id"],
        "stage": BENCH_TEST_STAGE,
        "evidence_scope": evidence_scope,
        **expected_decision_fields(record, evidence_scope),
        "evidence": evidence,
    }
    artifact.update(record_projection(record))
    return artifact


def gate_lines(data: dict) -> list[str]:
    """The step-11 outcome, computed deterministically so the caller sees it up front.

    The line states the observation exactly as the record holds it. When the record
    contradicts the censoring discipline it says so instead of describing the legal
    shape the record was supposed to have, so the GATE line can never be read as an
    endorsement of a censoring time written as an end-point.
    """
    record = data.get("bench_test") if isinstance(data, dict) else None
    if not isinstance(record, dict):
        return []
    run_id = record.get("run_id")
    censoring_type = record.get("censoring_type")
    iteration = record.get("campaign_iteration")
    observed = (
        f"censoring_type={censoring_type} event_occurred={record.get('event_occurred')} "
        f"event_time={record.get('event_time')}"
    )
    handoff = (
        f"hand it to the variance assessment of campaign iteration {iteration} exactly as recorded"
    )
    if record.get("event_occurred") is False and record.get("event_time") is not None:
        return [
            f"GATE: bench run {run_id} recorded with no event but an end-point ({observed}) -> HOLD; a "
            "censoring time is never recorded as an end-point value and this run is not handed on as an "
            "observation"
        ]
    if censoring_type in ("RIGHT", "LEFT", "INTERVAL") and record.get("event_occurred") is True:
        return [
            f"GATE: bench run {run_id} recorded as {censoring_type}-censored but claiming an event "
            f"({observed}) -> HOLD; an event that occurred is not censored and this run is not handed on "
            "as an observation"
        ]
    if censoring_type == "NONE" and record.get("event_occurred") is True:
        return [
            f"GATE: bench run {run_id} recorded as an observed event at {record.get('event_time')} h "
            f"({observed}) -> decision UNDECIDED; {handoff}"
        ]
    if censoring_type == "NONE":
        return [
            f"GATE: bench run {run_id} recorded with no event and no censoring declared ({observed}) "
            f"-> decision UNDECIDED; {handoff}"
        ]
    return [
        f"GATE: bench run {run_id} recorded as a {censoring_type} observation with no end-point "
        f"({observed}) -> decision UNDECIDED; {handoff}, never as the observation window length"
    ]


# --- The screened-sample release gate (E-3 / L5) -------------------------------


def released_screening(record: object, screenings: object) -> dict | None:
    """The one supplied screening artifact that released this run's sample, or None.

    The single verifiable rule of the bench-side screen gate: the run's
    ``sample_reference`` must fall on a supplied screening artifact whose
    ``overall_verdict`` is PASS with ``gate_to_bench`` RELEASED. A screen that FAILed
    (which the schema forces to BLOCKED) or one that never released the sample cannot
    authorize a bench slot. Pure lookup over records judged on their own fields; the
    records' schema validity is checked by the caller that loaded them.
    """
    if not isinstance(record, dict) or not isinstance(screenings, list):
        return None
    sample = record.get("sample_reference")
    if not has_text(sample):
        return None
    for screening in screenings:
        if not isinstance(screening, dict):
            continue
        if screening.get("sample_reference") != sample:
            continue
        if screening.get("overall_verdict") == "PASS" and screening.get("gate_to_bench") == "RELEASED":
            return screening
    return None


def screening_release_errors(record: object, screenings: object) -> list[str]:
    """Reasons this run's sample is not released by any supplied screening artifact.

    The message names the sample AND every supplied screening (id, sample, verdict,
    gate), so a refusal is never silent about which screen failed to release which
    sample. Empty list = the sample was released and the bench slot may be spent.
    """
    if released_screening(record, screenings) is not None:
        return []
    sample = record.get("sample_reference") if isinstance(record, dict) else None
    listed = []
    for screening in screenings if isinstance(screenings, list) else []:
        if not isinstance(screening, dict):
            continue
        listed.append(
            f"{screening.get('screening_id')} (sample {screening.get('sample_reference')}, "
            f"overall_verdict {screening.get('overall_verdict')}, gate_to_bench {screening.get('gate_to_bench')})"
        )
    return [
        f"bench_test.sample_reference {sample} is not released by any supplied screening artifact: "
        + ("; ".join(listed) if listed else "none supplied")
        + ". A bench slot is spent only on a sample whose screening shows overall_verdict PASS with "
        "gate_to_bench RELEASED; a failed or unreleased screen must not occupy one"
    ]


def release_line(record: object, screening: dict) -> str:
    """The one-line release conclusion printed when the run may spend a bench slot."""
    return (
        f"GATE: run {record.get('run_id')} sample {record.get('sample_reference')} released by screening "
        f"{screening.get('screening_id')} (overall_verdict PASS, gate_to_bench RELEASED); "
        "the bench slot may be spent"
    )
