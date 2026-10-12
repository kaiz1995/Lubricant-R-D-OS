"""Deterministic variance-assessment policy: the four-verdict routing and the gate rules.

Step 12 asks the question that decides whether the whole inner loop is meaningful:
is the observed difference real, or is it noise? This module holds every judgement
that the preflight, the builder and the validator must agree on, so the three
scripts cannot disagree about the same input.

Five rules, all fail-closed:

1. THE FOUR VERDICTS PASS THROUGH UNCHANGED. The engine decides one of
   CONSISTENT_DIFFERENCE / NO_DETECTABLE_DIFFERENCE / UNDERPOWERED /
   REPLICATE_INCONSISTENT and this skill never rewrites it. UNDERPOWERED stays its
   own verdict and is NEVER collapsed into NO_DETECTABLE_DIFFERENCE: "we cannot
   measure it" is not "there is no difference", and conflating the two justifies a
   wrong product decision on a design that was never capable of answering the
   question. This is the most expensive error in grease R&D.

2. ONLY CONSISTENT_DIFFERENCE RELEASES THE MODEL. ``decision`` is GO exactly when
   the verdict is CONSISTENT_DIFFERENCE and no artifact-level evidence item carries
   status GAP. An UNDERPOWERED, REPLICATE_INCONSISTENT or NO_DETECTABLE_DIFFERENCE
   round is still recorded -- truthfully, with decision HOLD -- because the record
   of an unanswerable round is evidence too, and the only recovery is a better
   method, a better criterion or a repaired replicate structure.

3. THE THREE DATA-QUALITY RULES ARE CHECKED HERE, BEFORE ANYTHING IS WRITTEN.
   (a) Censoring is never an end-point: a censored observation must not carry an
   event_time, must not claim event_occurred=true, and must declare a stop_reason;
   a censored observation without one is refused fail-closed, because an
   unexplained stop is not an observation. (b) Material identity must be
   verifiable: every observation traces to sample_id + batch_id. (c) Confounding
   must be excludable: an observation without a parseable timestamp cannot be
   proven to sit outside a confounds=true intervention window. The engine enforces
   the same three, but a caller deserves the reason before anything is built.

4. EVERY ASSESSED OBSERVATION TRACES TO A BENCH-TEST RECORD. The runs come from
   step 11, so an observation whose run_reference resolves to no supplied
   bench_test artifact has no provenance and is refused; a supplied bench-test
   record that no observation references is an omission, not a silent drop; and
   the run's censoring discipline is cross-checked, so an upstream right-censored
   run can never be presented downstream as a completed observation. The value of
   an uncensored run's end-point must appear in the record it came from.

5. THE PACK'S PLANNING CONSTANTS ARE FROZEN. alpha = 0.05, target power = 0.80 and
   the separation factor k = 3 are fixed by the pack so that a sample-size question
   can never be answered by two different numbers in two different documents. A
   request that relaxes one of them is refused rather than silently honoured:
   SIGMA_MAX = delta / k, and below k = 3 the rule is to change the method or the
   criterion, not to relax the factor.

Two derived routings are recorded rather than asserted:

* SIGMA SOURCE. A frozen sigma imported from method characterisation is preferred
  over the sigma estimated from this design, because estimating sigma needs an
  order of magnitude more data than using a known one. Which one was used is
  reported, never inferred.
* STOP STATE. When the caller declares the model's prediction interval and the
  engine finds a real difference inside it, the difference is already predicted by
  the model, so another round adds no information: the inner loop stops with the
  existing evidence (stop_state NO_NEW_INFORMATION) instead of spending bench
  months to re-learn what is known. The comparison is between two declared numbers
  -- the engine's difference and the caller's interval half-width -- so no
  statistic is computed here.
"""

from __future__ import annotations

import datetime
import math

# --- Request contract --------------------------------------------------------
# The upstream of step 12 is the step-11 bench-test records, so the request names
# them and nothing else: the project identity is inherited from those records
# (the preflight proves they agree on exactly one project_id), and a variance
# assessment that could be pointed at a project its runs did not come from would
# be a provenance hole.
INPUT_FIELDS = {
    "campaign_reference", "variance_id", "iteration", "evidence_scope", "input_mode",
    "bench_test_artifacts", "engine_input", "model_prediction_interval", "evidence",
}
REQUIRED_INPUT_FIELDS = INPUT_FIELDS - {"model_prediction_interval"}
# The three accepted input shapes of step 12. A request declares which one it used
# so the reader never has to guess where the noise scale came from.
INPUT_MODES = ("FROZEN_SIGMA", "RUN_RECORDS", "PREREGISTERED_DELTA")
MODE_MEANING = {
    "FROZEN_SIGMA": "a frozen sigma imported from step-5 method characterisation drives the power question",
    "RUN_RECORDS": "this round's run records plus the declared replicate structure carry the question",
    "PREREGISTERED_DELTA": "a pre-registered delta from the step-3 criterion drives the power question",
}
EVIDENCE_SCOPES = {"SYNTHETIC", "PHYSICAL"}
EVIDENCE_FIELDS = {"evidence_id", "statement", "source", "status", "claim_class"}
EVIDENCE_STATUSES = {"OBSERVED", "ASSUMED", "GAP"}

# --- Engine contract (mirrors the frozen engine constants) -------------------
ENGINE_NAME = "statistics"
ENGINE_METHOD = "NESTED_VARIANCE_V1"
ENGINE_ANALYSES = ("VARIANCE_COMPONENTS", "POWER_ANALYSIS", "CONSISTENCY_CHECK")
VARIANCE_INPUT_TYPE = "VARIANCE_ANALYSIS"
ENGINE_EVIDENCE_SOURCE = "ENGINE:statistics"
FROZEN_K_REQUIRED = 3.0
FROZEN_ALPHA = 0.05
FROZEN_TARGET_POWER = 0.80
RESOLUTION_CONSTANT = 4.0
BENCH_ROUND_DAYS = 30
BENCH_POSITIONS_PER_ROUND = 2

# --- Verdicts ----------------------------------------------------------------
VERDICT_CONSISTENT_DIFFERENCE = "CONSISTENT_DIFFERENCE"
VERDICT_NO_DETECTABLE_DIFFERENCE = "NO_DETECTABLE_DIFFERENCE"
VERDICT_UNDERPOWERED = "UNDERPOWERED"
VERDICT_REPLICATE_INCONSISTENT = "REPLICATE_INCONSISTENT"
VERDICTS = (
    VERDICT_CONSISTENT_DIFFERENCE,
    VERDICT_NO_DETECTABLE_DIFFERENCE,
    VERDICT_UNDERPOWERED,
    VERDICT_REPLICATE_INCONSISTENT,
)
# The one verdict that releases the step-13 model update.
RELEASING_VERDICT = VERDICT_CONSISTENT_DIFFERENCE

# --- Stop routing ------------------------------------------------------------
STOP_CONTINUE = "CONTINUE"
STOP_NO_NEW_INFORMATION = "NO_NEW_INFORMATION"
STOP_STATES = (STOP_CONTINUE, STOP_NO_NEW_INFORMATION)

# --- Censoring discipline ----------------------------------------------------
CENSORING_TYPES = ("RIGHT", "LEFT", "INTERVAL", "NONE")
OBSERVATION_LEVELS = ("MEASUREMENT", "BENCH", "BATCH")
OBSERVATION_REQUIRED_FIELDS = (
    "observation_reference", "level", "group_reference", "sample_id", "batch_id",
    "run_reference", "value", "event_occurred", "event_time",
)
CENSORING_REQUIRED_FIELDS = (
    "observation_reference", "event_occurred", "event_time", "censoring_type", "stop_reason",
)


def has_text(value: object) -> bool:
    """True for a non-empty, non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def is_number(value: object) -> bool:
    """True for a finite real number (booleans are not numbers here)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_positive_number(value: object) -> bool:
    return is_number(value) and value > 0.0


def format_number(value: object) -> str:
    """Deterministic text for one engine number, identical in builder and validator."""
    if value is None:
        return "null"
    return format(float(value), ".6g")


def has_gap(evidence: object) -> bool:
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("status") == "GAP" for item in evidence
    )


def _instant_key(text: object) -> float | None:
    """ISO-8601 instant -> comparable float (UTC seconds), or None if unparseable."""
    if not has_text(text):
        return None
    value = text.strip()
    if value.endswith("Z") or value.endswith("z"):
        value = value[:-1] + "+00:00"
    try:
        moment = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment.timestamp()


# --- Request-level validation -------------------------------------------------

def evidence_errors(value: object) -> list[str]:
    """Artifact-level evidence must be a non-empty list of well-formed items."""
    if not isinstance(value, list) or not value:
        return ["evidence must be a non-empty array"]
    errors: list[str] = []
    for index, item in enumerate(value):
        label = f"evidence[{index}]"
        if not isinstance(item, dict) or not set(item) <= EVIDENCE_FIELDS:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"{label}.status")
    return errors


def prediction_interval_errors(value: object) -> list[str]:
    """The optional model prediction interval: a declared half-width, not a computed one."""
    if value is None:
        return []
    if not isinstance(value, dict):
        return ["model_prediction_interval must be an object"]
    unknown = sorted(set(value) - {"model_reference", "half_width", "unit"})
    missing = sorted({"model_reference", "half_width", "unit"} - set(value))
    if unknown or missing:
        return [f"model_prediction_interval: unexpected={unknown or 'none'} missing={missing or 'none'}"]
    errors: list[str] = []
    for field in ("model_reference", "unit"):
        if not has_text(value.get(field)):
            errors.append(f"model_prediction_interval.{field} must be a non-empty string")
    if not is_positive_number(value.get("half_width")):
        errors.append("model_prediction_interval.half_width must be a positive number")
    return errors


def mode_errors(mode: object, engine_input: object) -> list[str]:
    """The declared input shape must actually carry the input it claims."""
    if mode not in INPUT_MODES:
        return [f"input_mode must be one of {', '.join(INPUT_MODES)}"]
    if not isinstance(engine_input, dict):
        return ["engine_input must be an object"]
    errors: list[str] = []
    if mode == "FROZEN_SIGMA":
        if not is_positive_number(engine_input.get("frozen_sigma")):
            errors.append(
                "input_mode FROZEN_SIGMA requires engine_input.frozen_sigma > 0 "
                "(the noise baseline imported from step-5 method characterisation)")
        if not has_text(engine_input.get("frozen_sigma_reference")):
            errors.append(
                "input_mode FROZEN_SIGMA requires engine_input.frozen_sigma_reference: "
                "a sigma without the record it was frozen in is not a frozen baseline")
    if mode == "RUN_RECORDS":
        structure = engine_input.get("replicate_structure")
        levels = {entry.get("level") for entry in structure if isinstance(entry, dict)} \
            if isinstance(structure, list) else set()
        if not levels & {"BENCH", "BATCH"}:
            errors.append(
                "input_mode RUN_RECORDS requires a declared replicate structure with a BENCH or "
                "BATCH level: the round's repeats are what the question rests on")
    if mode == "PREREGISTERED_DELTA":
        if not is_positive_number(engine_input.get("preregistered_delta")):
            errors.append(
                "input_mode PREREGISTERED_DELTA requires engine_input.preregistered_delta > 0 "
                "(the smallest difference worth detecting, registered at step 3 before the runs)")
    return errors


def censoring_rule_errors(engine_input: dict) -> list[str]:
    """Rule (a): censoring is never an end-point, and a stop must be explained.

    Applied before the engine is called so the caller gets the reason without a
    round trip. A right-censored value recorded as an end-point silently poisons
    every variance estimate downstream: the observation looks like a finished run
    while it only means "we stopped watching".
    """
    errors: list[str] = []
    entries = engine_input.get("censoring")
    if not isinstance(entries, list):
        return ["engine_input.censoring must be an array (an empty array is a complete record of no censoring)"]
    known = {
        observation.get("observation_reference")
        for observation in engine_input.get("observations", [])
        if isinstance(observation, dict)
    }
    seen: set[object] = set()
    for index, entry in enumerate(entries):
        label = f"engine_input.censoring[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        reference = entry.get("observation_reference")
        if not has_text(reference):
            errors.append(f"{label}.observation_reference must be a non-empty string")
        elif reference not in known:
            errors.append(f"{label} references unknown observation_reference {reference}")
        if reference in seen:
            errors.append(f"{label} duplicates the censoring entry for {reference}")
        seen.add(reference)
        if entry.get("censoring_type") not in CENSORING_TYPES:
            errors.append(f"{label}.censoring_type must be one of {', '.join(CENSORING_TYPES)}")
            continue
        stop_reason = str(entry.get("stop_reason") or "").strip()
        if entry["censoring_type"] != "NONE":
            if entry.get("event_occurred") is not False:
                errors.append(
                    f"{label} is censored ({entry['censoring_type']}) but claims event_occurred="
                    f"{entry.get('event_occurred')}: an event that occurred is not censored")
            if entry.get("event_time") is not None:
                errors.append(
                    f"{label} is censored but carries event_time={entry.get('event_time')}: "
                    "a censoring time must never be recorded as an end-point")
            if not stop_reason:
                errors.append(
                    f"{label} is censored without a stop_reason: refused fail-closed, an unexplained "
                    "stop is not an observation")
        elif not stop_reason:
            # The engine tolerates a NONE entry without a reason; this artifact contract does
            # not, because every recorded censoring entry must carry why the run stopped.
            errors.append(
                f"{label} has censoring_type NONE and no stop_reason: the record must state why the "
                "run stopped (for example 'event observed inside the protocol window')")
    return errors


def identity_rule_errors(engine_input: dict) -> list[str]:
    """Rule (b): material identity must be verifiable on every observation.

    WGO_001 discarded its only clean replicate pair because the photo said ASA#2
    while the worksheet said ASA#4. An observation that cannot be traced to a
    sample from a batch cannot be used as a replicate at all. The conflict itself
    (one sample_id under two batch_ids) is the engine's REPLICATE_INCONSISTENT
    verdict, not a refusal: the numbers are irrelevant to it, so it must reach the
    engine and come back as a verdict.
    """
    errors: list[str] = []
    for index, observation in enumerate(engine_input.get("observations", [])):
        label = f"engine_input.observations[{index}]"
        if not isinstance(observation, dict):
            errors.append(f"{label} must be an object")
            continue
        for field in ("sample_id", "batch_id"):
            if not has_text(observation.get(field)):
                errors.append(
                    f"{label}.{field} must be a non-empty string: material identity must be "
                    "verifiable before an observation can count as a replicate")
    return errors


def confounding_rule_errors(engine_input: dict) -> list[str]:
    """Rule (c): a confounder that cannot be excluded must be refused, not assumed away.

    An unparseable window would silently hide a confounder, and an observation
    without a timestamp cannot be proven to sit outside an open window.
    """
    errors: list[str] = []
    events = engine_input.get("intervention_events")
    if not isinstance(events, list):
        return ["engine_input.intervention_events must be an array (an empty array records no intervention)"]
    confounds_any = False
    for index, event in enumerate(events):
        label = f"engine_input.intervention_events[{index}]"
        if not isinstance(event, dict):
            errors.append(f"{label} must be an object")
            continue
        if not has_text(event.get("event_id")) or not has_text(event.get("description")):
            errors.append(f"{label} needs a non-empty event_id and description")
        if _instant_key(event.get("at")) is None:
            errors.append(f"{label} has an unparseable at: an unreadable window would silently hide a confounder")
        if event.get("until") is not None and _instant_key(event.get("until")) is None:
            errors.append(f"{label} has an unparseable until")
        if not isinstance(event.get("confounds"), bool):
            errors.append(f"{label}.confounds must be a boolean")
        confounds_any = confounds_any or event.get("confounds") is True
    if confounds_any:
        for index, observation in enumerate(engine_input.get("observations", [])):
            if not isinstance(observation, dict):
                continue
            if _instant_key(observation.get("at")) is None:
                errors.append(
                    f"engine_input.observations[{index}] has no parseable at while a confounds=true "
                    "intervention exists: the engine cannot prove it is outside the window")
    return errors


def engine_input_errors(engine_input: object) -> list[str]:
    """Structural contract of the engine input, checked before the engine is called."""
    if not isinstance(engine_input, dict):
        return ["engine_input must be an object"]
    errors: list[str] = []
    if engine_input.get("input_type") != VARIANCE_INPUT_TYPE:
        errors.append(f"engine_input.input_type must be {VARIANCE_INPUT_TYPE}")
    analyses = engine_input.get("analyses")
    if not isinstance(analyses, list) or not analyses:
        errors.append("engine_input.analyses must be a non-empty array")
    else:
        unknown = [name for name in analyses if name not in ENGINE_ANALYSES]
        if unknown:
            errors.append(f"engine_input.analyses contains an unknown analysis: {unknown[0]}")
    structure = engine_input.get("replicate_structure")
    if not isinstance(structure, list) or not structure:
        errors.append("engine_input.replicate_structure must be a non-empty array")
    else:
        for index, entry in enumerate(structure):
            label = f"engine_input.replicate_structure[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{label} must be an object")
                continue
            if entry.get("level") not in OBSERVATION_LEVELS:
                errors.append(f"{label}.level must be one of {', '.join(OBSERVATION_LEVELS)}")
            if not isinstance(entry.get("n"), int) or isinstance(entry.get("n"), bool) or entry["n"] < 1:
                errors.append(f"{label}.n must be an integer >= 1")
            if not has_text(entry.get("group_reference")):
                errors.append(f"{label}.group_reference must be a non-empty string")
    observations = engine_input.get("observations")
    if not isinstance(observations, list) or not observations:
        errors.append("engine_input.observations must be a non-empty array")
    else:
        seen: set[object] = set()
        for index, observation in enumerate(observations):
            label = f"engine_input.observations[{index}]"
            if not isinstance(observation, dict):
                errors.append(f"{label} must be an object")
                continue
            for field in OBSERVATION_REQUIRED_FIELDS:
                if field not in observation:
                    errors.append(f"{label}.{field} is required")
            if observation.get("level") not in OBSERVATION_LEVELS:
                errors.append(f"{label}.level must be one of {', '.join(OBSERVATION_LEVELS)}")
            if not is_number(observation.get("value")):
                errors.append(f"{label}.value must be a finite number")
            if not isinstance(observation.get("event_occurred"), bool):
                errors.append(f"{label}.event_occurred must be a boolean")
            if observation.get("event_time") is not None and not is_number(observation.get("event_time")):
                errors.append(f"{label}.event_time must be a number or null")
            reference = observation.get("observation_reference")
            if reference in seen:
                errors.append(f"{label}.observation_reference {reference} is duplicated")
            seen.add(reference)
    arms = engine_input.get("comparison_arms")
    if arms is not None:
        if not isinstance(arms, dict) or set(arms) != {"arm_a_group_reference", "arm_b_group_reference"}:
            errors.append("engine_input.comparison_arms must contain exactly arm_a_group_reference and arm_b_group_reference")
        else:
            group_references = {
                observation.get("group_reference") for observation in observations
                if isinstance(observation, dict)
            } if isinstance(observations, list) else set()
            for key in ("arm_a_group_reference", "arm_b_group_reference"):
                if arms.get(key) not in group_references:
                    errors.append(
                        f"engine_input.comparison_arms.{key} {arms.get(key)} does not match any "
                        "observation group_reference")
            if arms.get("arm_a_group_reference") == arms.get("arm_b_group_reference"):
                errors.append("engine_input.comparison_arms names the same group twice: there is nothing to compare")
    for field in ("frozen_sigma", "control_band", "preregistered_delta"):
        if engine_input.get(field) is not None and not is_positive_number(engine_input.get(field)):
            errors.append(f"engine_input.{field} must be a positive number when supplied")
    if engine_input.get("frozen_sigma") is not None and not has_text(engine_input.get("frozen_sigma_reference")):
        errors.append(
            "engine_input.frozen_sigma_reference is required with engine_input.frozen_sigma: "
            "the frozen baseline must name the record it came from")
    if engine_input.get("k_required") is not None and engine_input.get("k_required") != FROZEN_K_REQUIRED:
        errors.append(
            f"engine_input.k_required is frozen at {FROZEN_K_REQUIRED:g} by the pack (SIGMA_MAX = delta / k); "
            "below k = 3 the rule is to change the method or the criterion, never to relax the separation factor")
    if engine_input.get("alpha") is not None and engine_input.get("alpha") != FROZEN_ALPHA:
        errors.append(
            f"engine_input.alpha is frozen at {FROZEN_ALPHA:g} by the pack so a sample-size question cannot be "
            "answered by two different numbers in two different documents")
    if engine_input.get("target_power") is not None and engine_input.get("target_power") != FROZEN_TARGET_POWER:
        errors.append(
            f"engine_input.target_power is frozen at {FROZEN_TARGET_POWER:g} by the pack so a sample-size question "
            "cannot be answered by two different numbers in two different documents")
    n_values = engine_input.get("resolution_n_values")
    if n_values is not None and (
        not isinstance(n_values, list) or not n_values
        or not all(isinstance(value, int) and not isinstance(value, bool) and value >= 1 for value in n_values)
    ):
        errors.append("engine_input.resolution_n_values must be an array of integers >= 1")
    errors.extend(censoring_rule_errors(engine_input))
    errors.extend(identity_rule_errors(engine_input))
    errors.extend(confounding_rule_errors(engine_input))
    return errors


def provenance_errors(engine_input: object, bench_records: list[dict]) -> list[str]:
    """Every assessed observation traces to a step-11 record, and the discipline matches.

    Three directions, all fail-closed: an observation with no upstream run has no
    provenance; a supplied upstream record that no observation references was
    dropped without being said out loud; and a run recorded as censored upstream
    may never reappear downstream as a completed observation. The end-point of an
    uncensored run must be traceable to the value the record actually holds, so a
    hand-entered figure cannot slip in as the assessed value.
    """
    if not isinstance(engine_input, dict):
        return ["engine_input must be an object"]
    errors: list[str] = []
    observations = engine_input.get("observations")
    if not isinstance(observations, list):
        return ["engine_input.observations must be an array"]
    by_run: dict[str, dict] = {}
    for record in bench_records:
        run_id = record.get("run_id")
        if run_id in by_run:
            errors.append(f"bench_test run_id {run_id} is supplied more than once")
        by_run[run_id] = record
    censoring_index = {
        entry.get("observation_reference"): entry
        for entry in engine_input.get("censoring", [])
        if isinstance(entry, dict)
    }
    referenced: dict[str, list[dict]] = {}
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            continue
        run_reference = observation.get("run_reference")
        if run_reference not in by_run:
            errors.append(
                f"engine_input.observations[{index}] run_reference {run_reference} resolves to no supplied "
                "bench_test record: an observation without a step-11 record has no provenance")
            continue
        referenced.setdefault(run_reference, []).append(observation)
    for run_id in sorted(key for key in by_run if key not in referenced):
        errors.append(
            f"bench_test run {run_id} is supplied but no observation references it: a supplied run that is "
            "not assessed is an omission, not a silent drop")
    for run_id in sorted(referenced):
        record = by_run[run_id]
        run_observations = referenced[run_id]
        for observation in run_observations:
            if observation.get("sample_id") != record.get("sample_reference"):
                errors.append(
                    f"bench_test run {run_id} tests sample_reference {record.get('sample_reference')} but "
                    f"observation {observation.get('observation_reference')} claims sample_id "
                    f"{observation.get('sample_id')}: material identity must be verifiable end to end")
            if observation.get("batch_id") != record.get("batch_reference"):
                errors.append(
                    f"bench_test run {run_id} belongs to batch_reference {record.get('batch_reference')} but "
                    f"observation {observation.get('observation_reference')} claims batch_id "
                    f"{observation.get('batch_id')}: a run is not a replicate of a batch it did not come from")
        censoring_type = record.get("censoring_type")
        if censoring_type != "NONE":
            matching = [
                observation for observation in run_observations
                if (censoring_index.get(observation.get("observation_reference")) or {}).get("censoring_type")
                == censoring_type
            ]
            if not matching:
                errors.append(
                    f"bench_test run {run_id} is recorded as censored ({censoring_type}) but no observation of "
                    "that run carries a matching censoring entry: an upstream censored run must not reappear "
                    "downstream as a completed observation")
            continue
        for observation in run_observations:
            entry = censoring_index.get(observation.get("observation_reference"))
            if isinstance(entry, dict) and entry.get("censoring_type") != "NONE":
                errors.append(
                    f"bench_test run {run_id} is an uncensored completed run but observation "
                    f"{observation.get('observation_reference')} is marked {entry.get('censoring_type')}-censored: "
                    "the two records disagree about whether the run ended in an event")
        endpoint = record.get("event_time")
        if endpoint is not None and not any(
            is_number(observation.get("value")) and float(observation["value"]) == float(endpoint)
            for observation in run_observations
        ):
            errors.append(
                f"bench_test run {run_id} records end-point {endpoint} but no observation of that run carries "
                "that value: the assessed value is not traceable to the record it came from")
    return errors


def stop_state(engine_input: dict, engine_result: dict, prediction_interval: object) -> str:
    """CONTINUE, or NO_NEW_INFORMATION when the model already predicts this difference.

    A real difference inside the model's own prediction interval confirms what the
    model already says, so another round buys no information and the inner loop
    stops with the existing evidence. Both numbers are declared: the engine's
    difference and the caller's interval half-width. Nothing is computed here.
    """
    if not isinstance(prediction_interval, dict):
        return STOP_CONTINUE
    comparison = engine_result.get("comparison") or {}
    difference = comparison.get("difference")
    if engine_result.get("verdict") != RELEASING_VERDICT or not is_number(difference):
        return STOP_CONTINUE
    if abs(float(difference)) <= float(prediction_interval["half_width"]):
        return STOP_NO_NEW_INFORMATION
    return STOP_CONTINUE


# --- Artifact projection ------------------------------------------------------

def _finite_or_none(value: object) -> float | None:
    return float(value) if is_number(value) else None


def project_components(engine_result: dict) -> tuple[dict, list[str]]:
    """Engine variance components -> the artifact's flat <component>_ci_low shape.

    A component the layout cannot separate stays null, never zero. A null
    confidence bound is omitted rather than written as null: the artifact contract
    allows an absent bound but not a null one, and a bound the engine could not
    compute must not look like a bound of zero.
    """
    source = engine_result.get("variance_components")
    if not isinstance(source, dict):
        return {}, ["engine result carries no variance_components block"]
    components: dict = {}
    for name in ("sigma_meas", "sigma_bench", "sigma_batch", "sigma_total"):
        components[name] = _finite_or_none(source.get(name))
    for name in ("sigma_meas", "sigma_bench", "sigma_batch", "sigma_total"):
        low = _finite_or_none(source.get(name + "_ci_low"))
        high = _finite_or_none(source.get(name + "_ci_high"))
        if low is not None:
            components[name + "_ci_low"] = low
        if high is not None:
            components[name + "_ci_high"] = high
    return components, []


def project_resolution_table(engine_result: dict) -> tuple[list[dict], list[str]]:
    """Engine resolution rows -> artifact rows, keeping the sqrt(n) message intact."""
    rows = engine_result.get("resolution_table")
    if not isinstance(rows, list):
        return [], ["engine result carries no resolution_table block"]
    projected: list[dict] = []
    errors: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"resolution_table[{index}] is not an object")
            continue
        if not isinstance(row.get("detectable"), bool):
            errors.append(
                f"resolution_table[{index}].detectable is {row.get('detectable')!r}: the artifact contract "
                "requires a boolean, so the engine must have compared the row against a frozen criterion")
            continue
        entry = {
            "replicates_per_group": row.get("replicates_per_group"),
            "detectable_difference": _finite_or_none(row.get("detectable_difference")),
            "detectable": row.get("detectable"),
        }
        if has_text(row.get("note")):
            entry["note"] = row["note"]
        projected.append(entry)
    return projected, errors


def project_engine_result(engine_input: dict, engine_result: dict) -> tuple[dict, list[str]]:
    """Project the engine envelope into the artifact's own fields.

    Everything numeric is copied from the engine; nothing is recomputed here. The
    only transformation is shape: the artifact records the replicate levels it was
    assessed over, the censoring entries, the intervention windows and the
    components in their flat form.
    """
    errors: list[str] = []
    components, component_errors = project_components(engine_result)
    errors.extend(component_errors)
    resolution, resolution_errors = project_resolution_table(engine_result)
    errors.extend(resolution_errors)
    comparison = engine_result.get("comparison") or {}
    effect = comparison.get("effect_size")
    projected = {
        "replicate_structure": [
            {
                "level": entry.get("level"),
                "n": entry.get("n"),
                "group_reference": entry.get("group_reference"),
            }
            for entry in engine_input.get("replicate_structure", [])
            if isinstance(entry, dict)
        ],
        "censoring": [
            {
                "observation_reference": entry.get("observation_reference"),
                "event_occurred": entry.get("event_occurred"),
                "event_time": entry.get("event_time"),
                "censoring_type": entry.get("censoring_type"),
                "stop_reason": entry.get("stop_reason"),
            }
            for entry in engine_input.get("censoring", [])
            if isinstance(entry, dict)
        ],
        # The artifact's intervention_event contract carries no window end, so
        # `until` is dropped here; the engine evaluated the full window and the
        # description is carried verbatim.
        "intervention_events": [
            {
                "event_id": entry.get("event_id"),
                "description": entry.get("description"),
                "at": entry.get("at"),
                "confounds": entry.get("confounds"),
            }
            for entry in engine_input.get("intervention_events", [])
            if isinstance(entry, dict)
        ],
        "components": components,
        "effect_size": _finite_or_none(effect.get("cohens_d")) if isinstance(effect, dict) else None,
        "power": _finite_or_none((engine_result.get("power") or {}).get("power")),
        "k_ratio": _finite_or_none(comparison.get("k_ratio")),
        "sigma_max_requirement": _finite_or_none(comparison.get("sigma_max_requirement")),
        "resolution_table": resolution,
        "verdict": engine_result.get("verdict"),
    }
    if engine_input.get("frozen_sigma_reference") is not None:
        projected["frozen_sigma_reference"] = engine_input.get("frozen_sigma_reference")
    if engine_input.get("preregistered_delta") is not None:
        projected["preregistered_delta"] = engine_input.get("preregistered_delta")
    if projected["verdict"] not in VERDICTS:
        errors.append(f"engine returned verdict {projected['verdict']!r}, which is not one of the four frozen values")
    return projected, errors


def engine_evidence_item(engine_envelope: dict, variance_id: object) -> dict:
    """The one evidence item this skill appends: the engine run, verbatim where it matters.

    The digest is the engine's own SHA256 of the canonical input bytes, so the
    artifact points back at exactly the bytes that produced its numbers.
    """
    result = engine_envelope.get("result") or {}
    basis = result.get("verdict_basis")
    digest = engine_envelope.get("input_digest")
    statement = (
        f"Engine verdict {result.get('verdict')}"
        + (f" ({basis})" if has_text(basis) else "")
        + f". All statistics in this record were produced by the deterministic {ENGINE_NAME} engine "
        + f"(method {ENGINE_METHOD}, engine input digest {digest}); no number here was computed or "
        + "entered by hand."
    )
    return {
        "evidence_id": f"E-ENGINE-{variance_id}",
        "statement": statement,
        "source": ENGINE_EVIDENCE_SOURCE,
        "status": "OBSERVED",
    }


def engine_evidence_errors(evidence: object) -> list[str]:
    """The engine-run evidence item must be present, OBSERVED and named as the engine's."""
    if not isinstance(evidence, list):
        return ["evidence must be an array"]
    for item in evidence:
        if isinstance(item, dict) and item.get("source") == ENGINE_EVIDENCE_SOURCE:
            if item.get("status") != "OBSERVED":
                return [f"the {ENGINE_EVIDENCE_SOURCE} evidence item must have status OBSERVED"]
            if not has_text(item.get("statement")):
                return [f"the {ENGINE_EVIDENCE_SOURCE} evidence item needs a statement"]
            return []
    return [
        "evidence must carry the engine-run item (source "
        f"{ENGINE_EVIDENCE_SOURCE}): this artifact records engine output, so the engine run must be "
        "traceable in the record"
    ]


# --- Decision block -----------------------------------------------------------

def decision_for(verdict: object, evidence: object) -> str:
    """GO exactly for a releasing verdict with no artifact-level GAP."""
    if has_gap(evidence):
        return "HOLD"
    return "GO" if verdict == RELEASING_VERDICT else "HOLD"


def expected_decision_fields(
    variance_id: object,
    campaign_reference: object,
    iteration: object,
    evidence_scope: object,
    verdict: object,
    sigma_total: object,
    power: object,
    k_ratio: object,
    sigma_max_requirement: object,
    preregistered_delta: object,
    effect_size: object,
    evidence: object,
    stop: str = STOP_CONTINUE,
) -> dict[str, str]:
    """The canonical decision block, recomputed identically by builder and validator.

    Every number quoted here is a field of the artifact itself, so the validator can
    recompute the whole block from the artifact alone.
    """
    scope_prefix = (
        "Synthetic test fixture / NOT_FOR_PHYSICAL_EXECUTION: this record cannot authorize stage "
        "advancement. " if evidence_scope == "SYNTHETIC" else ""
    )
    uncertainty = (
        f"{scope_prefix}verdict={verdict}; sigma_total={format_number(sigma_total)}; "
        f"power={format_number(power)} against the pre-registered delta "
        f"{format_number(preregistered_delta)}; k_ratio={format_number(k_ratio)}; "
        f"sigma_max_requirement={format_number(sigma_max_requirement)}; "
        f"effect_size={format_number(effect_size)}. UNDERPOWERED is never a synonym for "
        "NO_DETECTABLE_DIFFERENCE: 'we cannot measure it' is not 'there is no difference'. The verdict is "
        "the engine's; this record reports it and decides nothing about the product."
    )
    if verdict == VERDICT_UNDERPOWERED:
        uncertainty += (
            " The recovery is a better method or a different criterion, NOT more replicates: at "
            f"{BENCH_POSITIONS_PER_ROUND} bench positions per round and {BENCH_ROUND_DAYS} days per round a "
            "k < 3 question costs months, so the requirement belongs on the method's own repeatability "
            "(SIGMA_MAX = delta / k)."
        )
    result = (
        f"variance assessment {variance_id} for campaign {campaign_reference} iteration {iteration}: "
        f"verdict={verdict}; sigma_total={format_number(sigma_total)}; power={format_number(power)}; "
        f"k_ratio={format_number(k_ratio)}; sigma_max_requirement={format_number(sigma_max_requirement)}; "
        f"effect_size={format_number(effect_size)}."
    )
    if stop == STOP_NO_NEW_INFORMATION:
        result += (
            " The difference is real and lies inside the declared model prediction interval, so the model "
            "already predicts it and another round adds no information."
        )
    if verdict == VERDICT_CONSISTENT_DIFFERENCE and stop == STOP_NO_NEW_INFORMATION:
        next_action = (
            f"Stop the inner loop with the existing evidence: carry variance assessment {variance_id} into "
            "close-out with stop_state NO_NEW_INFORMATION, and update the model once from this round before "
            "closing. Do not spend another bench round re-measuring a difference the model already predicts."
        )
    elif verdict == VERDICT_CONSISTENT_DIFFERENCE:
        next_action = (
            f"Update the model (step 13) from the observations that passed this check and carry variance "
            f"assessment {variance_id} forward with the model's applicability boundary (trust region)."
        )
    elif verdict == VERDICT_NO_DETECTABLE_DIFFERENCE:
        next_action = (
            "Do not update the model from this round: the design was capable of resolving the pre-registered "
            "delta and found no difference exceeding the k = 3 separation. Record the direction as excluded "
            "and return to step 9 with a different candidate or a different criterion."
        )
    elif verdict == VERDICT_UNDERPOWERED:
        next_action = (
            "Do not update the model and do NOT add replicates: change the method or the criterion. The design "
            "could not resolve the pre-registered difference, so the requirement moves onto the method "
            "(SIGMA_MAX = delta / k, k = 3) and the method is unqualified until its own repeatability sigma "
            "meets it; return to step 5 (method qualification) or step 3 (criterion)."
        )
    else:
        next_action = (
            "Do not update the model: no difference claim is admissible from this round. Repair the replicate "
            "structure first (verifiable material identity, same-arm outcome agreement), then re-run the "
            "variance assessment."
        )
    return {
        "decision_question": (
            f"Is the difference assessed by variance record {variance_id} real, or could this design not "
            "answer the question at its resolution?"
        ),
        "hypothesis": (
            f"{variance_id} records an engine-computed nested variance decomposition, an effect size, the "
            "power against the pre-registered delta and exactly one of the four frozen verdicts."
        ),
        "uncertainty": uncertainty,
        "decision_rule": (
            "The engine decides one of four verdicts and this record reports it unchanged. Only "
            "CONSISTENT_DIFFERENCE releases the step-13 model update; UNDERPOWERED means the question cannot "
            "be answered at this design's resolution and is never read as 'no difference'; "
            "REPLICATE_INCONSISTENT blocks every difference claim until the replicate structure is repaired; "
            "NO_DETECTABLE_DIFFERENCE asserts only that a capable design found nothing exceeding the k = 3 "
            "separation."
        ),
        "result": result,
        "decision": decision_for(verdict, evidence),
        "next_action": next_action,
    }


# --- Validation ---------------------------------------------------------------

def _close(first: object, second: object, tolerance: float = 1e-12) -> bool:
    return is_number(first) and is_number(second) and abs(float(first) - float(second)) <= tolerance


def resolution_errors(artifact: dict) -> list[str]:
    """The resolution rows must be the engine's own 4 * sigma / sqrt(n) rows.

    Recomputed from the artifact's fields, so a hand-edited row cannot pass. The
    frozen criterion is the pre-registered delta when one exists, otherwise the
    measured sigma_total; that is the same choice the engine makes.
    """
    rows = artifact.get("resolution_table")
    if not isinstance(rows, list):
        return ["resolution_table must be an array"]
    sigma = artifact.get("preregistered_delta")
    delta = artifact.get("preregistered_delta")
    if sigma is None:
        sigma = (artifact.get("components") or {}).get("sigma_total")
    errors: list[str] = []
    if not is_number(sigma):
        return errors
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not is_number(row.get("replicates_per_group")) \
                or not is_number(row.get("detectable_difference")):
            errors.append(f"resolution_table[{index}] is malformed")
            continue
        expected = RESOLUTION_CONSTANT * float(sigma) / math.sqrt(float(row["replicates_per_group"]))
        if not _close(row["detectable_difference"], expected):
            errors.append(
                f"resolution_table[{index}].detectable_difference must equal 4 * sigma / sqrt(n) = "
                f"{expected!r}: the row must be the engine's own")
            continue
        if is_number(delta):
            expected_detectable = float(row["detectable_difference"]) <= float(delta)
        else:
            expected_detectable = float(row["detectable_difference"]) <= float(sigma) / FROZEN_K_REQUIRED
        if row.get("detectable") is not expected_detectable:
            errors.append(
                f"resolution_table[{index}].detectable must be {expected_detectable}: the row compares the "
                "detectable difference against the frozen criterion")
    return errors


def policy_errors(artifact: dict) -> list[str]:
    """Every semantic check the validator applies to a stored artifact.

    Two kinds: the frozen-constant identities that prove the numbers are the
    engine's (k_ratio = delta / (sigma_total * k), SIGMA_MAX = delta / k, the
    resolution rows), and the decision block recomputed from the artifact's own
    fields.
    """
    errors: list[str] = []
    verdict = artifact.get("verdict")
    if verdict not in VERDICTS:
        errors.append(f"verdict must be one of {', '.join(VERDICTS)}")
    if artifact.get("computed_by") != "ENGINE":
        errors.append("computed_by must be ENGINE: this pack forbids hand-entered computed statistics")
    errors.extend(engine_evidence_errors(artifact.get("evidence")))
    components = artifact.get("components") or {}
    delta = artifact.get("preregistered_delta")
    if delta is not None:
        if not is_positive_number(delta):
            errors.append("preregistered_delta must be a positive number when present")
        else:
            expected_k_ratio = float(delta) / float(components.get("sigma_total") or 0.0) / FROZEN_K_REQUIRED \
                if is_positive_number(components.get("sigma_total")) else None
            if expected_k_ratio is not None and artifact.get("k_ratio") is not None \
                    and not _close(artifact.get("k_ratio"), expected_k_ratio):
                errors.append(
                    f"k_ratio must equal delta / (sigma_total * {FROZEN_K_REQUIRED:g}) = {expected_k_ratio!r}: "
                    "the ratio must be the engine's own")
            expected_sigma_max = float(delta) / FROZEN_K_REQUIRED
            if artifact.get("sigma_max_requirement") is not None \
                    and not _close(artifact.get("sigma_max_requirement"), expected_sigma_max):
                errors.append(
                    f"sigma_max_requirement must equal delta / {FROZEN_K_REQUIRED:g} = {expected_sigma_max!r}: "
                    "the requirement is frozen by the pack")
    else:
        if artifact.get("k_ratio") is not None:
            errors.append("k_ratio must be null when no pre-registered delta was recorded")
        if artifact.get("sigma_max_requirement") is not None:
            errors.append("sigma_max_requirement must be null when no pre-registered delta was recorded")
    errors.extend(resolution_errors(artifact))
    variants = [
        expected_decision_fields(
            artifact.get("variance_id"), artifact.get("campaign_reference"), artifact.get("iteration"),
            artifact.get("evidence_scope"), verdict, components.get("sigma_total"),
            artifact.get("power"), artifact.get("k_ratio"), artifact.get("sigma_max_requirement"),
            delta, artifact.get("effect_size"), artifact.get("evidence"), STOP_CONTINUE,
        )
    ]
    # Stated boundary: the artifact contract carries no field for the stop routing,
    # so the validator cannot see whether the model prediction interval contained
    # the difference. It enforces the direction that matters instead: the
    # NO_NEW_INFORMATION routing is only legal on a releasing verdict.
    if verdict == RELEASING_VERDICT:
        variants.append(
            expected_decision_fields(
                artifact.get("variance_id"), artifact.get("campaign_reference"), artifact.get("iteration"),
                artifact.get("evidence_scope"), verdict, components.get("sigma_total"),
                artifact.get("power"), artifact.get("k_ratio"), artifact.get("sigma_max_requirement"),
                delta, artifact.get("effect_size"), artifact.get("evidence"), STOP_NO_NEW_INFORMATION,
            )
        )
    mismatched = []
    for field in ("decision_question", "hypothesis", "uncertainty", "decision_rule", "result",
                  "decision", "next_action"):
        if any(variant[field] == artifact.get(field) for variant in variants):
            continue
        mismatched.append(field)
    if mismatched:
        errors.append(
            "the artifact must equal the deterministic variance-assessment policy for "
            + ", ".join(mismatched)
        )
    return errors


# --- Audible notes ------------------------------------------------------------

def input_notes(data: dict) -> list[str]:
    """NOTE lines: which input shape was used, and what it rests on."""
    notes: list[str] = []
    mode = data.get("input_mode")
    if mode in MODE_MEANING:
        notes.append(f"NOTE: input shape {mode}: {MODE_MEANING[mode]}")
    engine_input = data.get("engine_input") if isinstance(data.get("engine_input"), dict) else {}
    if is_positive_number(engine_input.get("frozen_sigma")):
        notes.append(
            "NOTE: sigma source FROZEN_METHOD_CHARACTERIZATION "
            f"({engine_input.get('frozen_sigma_reference')}): step 12 compares against the frozen noise "
            "baseline and does not re-estimate it; sigma accumulates from the blank reference sample that "
            "goes onto the bench every round at no extra bench position")
    else:
        notes.append(
            "NOTE: sigma source ESTIMATED_FROM_THIS_DESIGN: no frozen sigma was supplied, so the noise scale "
            "comes from this round's own replicates and is weaker than a frozen baseline")
    if is_positive_number(engine_input.get("preregistered_delta")):
        sigma = engine_input.get("frozen_sigma") or engine_input.get("control_band")
        if is_positive_number(sigma):
            k = float(engine_input["preregistered_delta"]) / float(sigma)
            notes.append(
                f"NOTE: k = delta / sigma = {k:.6g}; "
                + ("k >= 3, the pack planning rule n ~ 16/k^2 applies"
                   if k >= FROZEN_K_REQUIRED else
                   "k < 3: do NOT add samples -- change the method or the criterion "
                   "(SIGMA_MAX = delta / k)"))
    interval = data.get("model_prediction_interval")
    if isinstance(interval, dict) and is_positive_number(interval.get("half_width")):
        notes.append(
            "NOTE: a model prediction interval is declared; a real difference inside it routes the record to "
            "stop_state NO_NEW_INFORMATION (the model already predicts it, so another round buys nothing)")
    return notes
