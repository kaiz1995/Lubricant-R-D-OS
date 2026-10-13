"""Reject incomplete NEXT_BATCH_DECIDED requests before any next_batch artifact is built.

Step 13b of the precision-grease inner loop decides two things at once (
``schemas/next_batch.schema.json``): which samples the NEXT bench round runs, and whether
the loop continues at all. This gate exists because both halves are easy to fake:

* a proposed sample is only worth a bench slot if it separates two *competing*
  explanations, so every sample must cite a pair of explanations the input itself declares.
  This preflight never composes a hypothesis: an input that declares no competing
  explanations is held, never filled in with a plausible one.
* a stop is a decision like any other, so a ``stop_state`` other than CONTINUE must carry
  its non-empty reason - and, conversely, a reason is recorded only for a stop.
* the decision is taken at ONE campaign round boundary: the campaign carrier, the round's
  design and the round's variance assessment must agree on the project, the evidence scope
  and the iteration, and the campaign's own iteration entry must tell the same story as
  this record (same stop_state, same ``next_batch_reference``, same ``variance_reference``).
* the round is bounded by the availability the round's design declares, and a CONTINUE may
  not open an iteration beyond the campaign's ``max_iterations`` - the state machine
  refuses that advance, so this record must not authorize it.

Upstream artifacts are read for the fields this stage actually consumes, exactly like the
bench-capacity rule of the sibling ``preflight_doe_design.py``: their full contracts belong
to their owning skills (bench-registration / doe-design / variance-assessment), and loading
those schemas here would duplicate rules that already have one owner. The one authority
schema this stage owns - ``next_batch.schema.json`` - IS loaded and enforced, both on the
composed candidate and (by ``validate_next_batch_artifact.py``) on the committed record.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from next_batch_policy import (
    CONTINUE,
    STOP_STATES,
    VARIANCE_ROUTING_NOTES,
    VARIANCE_VERDICTS,
    composed_sample,
    expected_decision_fields,
    has_text,
    is_count,
    statement_map,
    stop_rationale_errors,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
NEXT_BATCH_STAGE = "NEXT_BATCH_DECIDED"
# This stage owns one authority schema (the record it writes) plus the common block that
# schema references. The sibling doe-design contract is not re-loaded here (its owner is
# preflight_doe_design.py), and neither are the campaign / variance contracts.
SCHEMA_NAMES = ("common.schema.json", "next_batch.schema.json")
INPUT_FIELDS = {"campaign_artifact", "experiment_design_artifact", "variance_artifact", "next_batch"}
RECORD_REQUIRED_FIELDS = {
    "next_batch_id",
    "stop_state",
    "bench_slots_required",
    "information_gain_basis",
    "competing_explanations",
    "proposed_samples",
    "evidence",
}
RECORD_OPTIONAL_FIELDS = {"stop_rationale", "next_round_budget"}
RECORD_ALLOWED_FIELDS = RECORD_REQUIRED_FIELDS | RECORD_OPTIONAL_FIELDS
SAMPLE_ALLOWED_FIELDS = {"sample_reference", "formula_reference", "hypothesis", "separates"}
EXPLANATION_FIELDS = {"explanation_id", "statement"}
EVIDENCE_FIELDS = {"evidence_id", "statement", "source", "status"}
EVIDENCE_STATUSES = {"OBSERVED", "ASSUMED", "GAP"}
BUDGET_FIELDS = {"bench_slots_remaining", "calendar_days_remaining"}
EVIDENCE_SCOPES = {"SYNTHETIC", "PHYSICAL"}


def schema_dir() -> Path:
    """Resolve the schema directory the way the sibling DOE preflight does.

    This stage loads only ``common.schema.json`` and ``next_batch.schema.json``, so it
    names only those two. The pack layout keeps every schema in ``../../schemas``; a
    deployed bundle keeps the copies it ships in the skill's own ``references/`` directory.
    """
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def load_schemas() -> tuple[dict[str, dict], Registry]:
    schemas = schema_dir()
    loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return loaded, registry


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def read_artifact(value: object, input_path: Path, label: str) -> tuple[list[str], dict | None]:
    """Read one upstream artifact, or report why it cannot be read. Never guesses a value."""
    path = resolved_path(value, input_path)
    if path is None:
        return [label], None
    try:
        return [], json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None


def campaign_errors(campaign: object) -> list[str]:
    """Structure of the inner-loop carrier, for the fields this stage reads."""
    if not isinstance(campaign, dict):
        return ["campaign_artifact must be a JSON object"]
    errors: list[str] = []
    if campaign.get("artifact_type") != "campaign":
        errors.append("campaign_artifact.artifact_type must be campaign")
    if campaign.get("stage") != "CAMPAIGN_OPENED":
        errors.append("campaign_artifact must be stage CAMPAIGN_OPENED")
    if not has_text(campaign.get("campaign_id")):
        errors.append("campaign_artifact.campaign_id must be a non-empty string")
    if not has_text(campaign.get("project_id")):
        errors.append("campaign_artifact.project_id must be a non-empty string")
    if campaign.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("campaign_artifact.evidence_scope must be SYNTHETIC or PHYSICAL")
    if not is_count(campaign.get("max_iterations"), 1):
        errors.append("campaign_artifact.max_iterations must be an integer >= 1")
    if not is_count(campaign.get("current_iteration"), 1):
        errors.append("campaign_artifact.current_iteration must be an integer >= 1")
    iterations = campaign.get("iterations")
    if not isinstance(iterations, list) or not iterations:
        errors.append("campaign_artifact.iterations must be a non-empty array of round entries")
    elif is_count(campaign.get("current_iteration"), 1):
        entry = campaign_entry(campaign)
        if entry is None:
            errors.append(
                f"campaign_artifact.iterations carries no entry for iteration {campaign['current_iteration']}: "
                "the next-batch decision is taken at the campaign's current round boundary")
        elif not has_text(entry.get("stop_state")):
            errors.append(
                f"campaign_artifact.iterations (iteration {campaign['current_iteration']}).stop_state must record "
                "how that round ended")
    return errors


def campaign_entry(campaign: object) -> dict | None:
    """The campaign's entry for its own current iteration, or None when it has none."""
    if not isinstance(campaign, dict):
        return None
    for entry in campaign.get("iterations", []) if isinstance(campaign.get("iterations"), list) else []:
        if isinstance(entry, dict) and entry.get("iteration") == campaign.get("current_iteration"):
            return entry
    return None


def design_errors(design: object) -> list[str]:
    """Structure of the round's design, for the availability this stage consumes."""
    if not isinstance(design, dict):
        return ["experiment_design_artifact must be a JSON object"]
    errors: list[str] = []
    if design.get("artifact_type") != "experiment_design":
        errors.append("experiment_design_artifact.artifact_type must be experiment_design")
    if design.get("stage") != "EXPERIMENT_DESIGNED":
        errors.append("experiment_design_artifact must be stage EXPERIMENT_DESIGNED")
    if not has_text(design.get("project_id")):
        errors.append("experiment_design_artifact.project_id must be a non-empty string")
    if design.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("experiment_design_artifact.evidence_scope must be SYNTHETIC or PHYSICAL")
    envelope = design.get("resource_envelope")
    if envelope is not None and (not isinstance(envelope, dict) or not is_count(envelope.get("bench_slots"), 1)):
        errors.append(
            "experiment_design_artifact.resource_envelope.bench_slots must be an integer >= 1 when the envelope "
            "is present: it is the number of concurrent bench positions available for the next round")
    if "available_bench_slots" in design and not is_count(design.get("available_bench_slots"), 0):
        errors.append(
            "experiment_design_artifact.available_bench_slots must be the integer >= 0 derived by "
            "bench-registration (it is never hand-set)")
    return errors


def design_availability(design: object) -> tuple[int | None, str]:
    """The tightest bench availability the round's design declares, and where it came from.

    ``available_bench_slots`` is the registered bench capacity copied by doe-design when a
    bench artifact was supplied; ``resource_envelope.bench_slots`` is the hand-filled
    declaration that path keeps otherwise. When both are present the smaller one binds.
    When neither is present the round declares no bound and there is nothing to check -
    that is reported as a NOTE, not silently treated as unlimited.
    """
    if not isinstance(design, dict):
        return None, "none"
    candidates: list[tuple[int, str]] = []
    envelope = design.get("resource_envelope")
    if isinstance(envelope, dict) and is_count(envelope.get("bench_slots"), 1):
        candidates.append((envelope["bench_slots"], "experiment_design_artifact.resource_envelope.bench_slots"))
    if is_count(design.get("available_bench_slots"), 0):
        candidates.append((design["available_bench_slots"], "experiment_design_artifact.available_bench_slots"))
    if not candidates:
        return None, "none"
    return min(candidates)


def variance_errors(variance: object) -> list[str]:
    """Structure of the round's variance record, for the fields this stage reads."""
    if not isinstance(variance, dict):
        return ["variance_artifact must be a JSON object"]
    errors: list[str] = []
    if variance.get("artifact_type") != "variance":
        errors.append("variance_artifact.artifact_type must be variance")
    if variance.get("stage") != "VARIANCE_ASSESSED":
        errors.append("variance_artifact must be stage VARIANCE_ASSESSED")
    if not has_text(variance.get("variance_id")):
        errors.append("variance_artifact.variance_id must be a non-empty string")
    if not has_text(variance.get("campaign_reference")):
        errors.append("variance_artifact.campaign_reference must be a non-empty string")
    if not is_count(variance.get("iteration"), 1):
        errors.append("variance_artifact.iteration must be an integer >= 1")
    if variance.get("verdict") not in VARIANCE_VERDICTS:
        errors.append(f"variance_artifact.verdict must be one of {list(VARIANCE_VERDICTS)}")
    if not has_text(variance.get("project_id")):
        errors.append("variance_artifact.project_id must be a non-empty string")
    if variance.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("variance_artifact.evidence_scope must be SYNTHETIC or PHYSICAL")
    return errors


def record_errors(record: object, design: object) -> list[str]:
    """The request block itself: stop-state rule, declared explanations, proposed samples."""
    if not isinstance(record, dict):
        return ["next_batch must be a JSON object"]
    errors: list[str] = []
    if not RECORD_REQUIRED_FIELDS <= set(record) or not set(record) <= RECORD_ALLOWED_FIELDS:
        # Reported, but not returned early: the per-field checks below name what is actually
        # missing or malformed (in particular the declared-explanation rule, whose refusal
        # must read as its own reason rather than as a generic shape error).
        errors.append(
            "next_batch must contain only the required fields "
            f"{sorted(RECORD_REQUIRED_FIELDS)} plus the optional {sorted(RECORD_OPTIONAL_FIELDS)}")
    if not has_text(record.get("next_batch_id")):
        errors.append("next_batch.next_batch_id must be a non-empty string")
    if record.get("stop_state") not in STOP_STATES:
        errors.append(f"next_batch.stop_state must be one of {list(STOP_STATES)}")
    errors.extend(stop_rationale_errors(record))
    if not is_count(record.get("bench_slots_required"), 1):
        errors.append("next_batch.bench_slots_required must be an integer >= 1")
    if not has_text(record.get("information_gain_basis")):
        errors.append(
            "next_batch.information_gain_basis must be a non-empty statement of why these are the informative "
            "samples rather than the alternatives considered")
    errors.extend(explanation_errors(record))
    errors.extend(sample_errors(record))
    budget = record.get("next_round_budget")
    if budget is not None:
        if not isinstance(budget, dict) or set(budget) != BUDGET_FIELDS:
            errors.append(f"next_batch.next_round_budget must contain exactly {sorted(BUDGET_FIELDS)}")
        elif any(not is_count(budget.get(field), 0) for field in BUDGET_FIELDS):
            errors.append("next_batch.next_round_budget figures must be integers >= 0")
    errors.extend(evidence_errors(record.get("evidence")))
    availability, source = design_availability(design)
    slots = record.get("bench_slots_required")
    if is_count(slots, 1) and isinstance(availability, int) and slots > availability:
        errors.append(
            f"next_batch.bench_slots_required={slots} exceeds the round's declared bench availability "
            f"{availability} ({source}): a round may not plan more positions than it has")
    samples = record.get("proposed_samples")
    if isinstance(samples, list) and is_count(slots, 1) and len(samples) > slots:
        errors.append(
            f"next_batch proposes {len(samples)} sample(s) but requires only {slots} bench slot(s): every "
            "proposed sample would run in the next round and therefore needs a slot")
    return errors


def explanation_errors(record: dict) -> list[str]:
    """The declared competing explanations the proposed samples must separate."""
    explanations = record.get("competing_explanations")
    if not isinstance(explanations, list) or len(explanations) < 2:
        return [
            "next_batch.competing_explanations must declare at least two competing explanations for this round "
            "boundary; the discrimination a sample buys is what the input declares it to be, never a guess"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(explanations):
        label = f"next_batch.competing_explanations[{index}]"
        if not isinstance(item, dict) or set(item) != EXPLANATION_FIELDS:
            errors.append(f"{label} must contain exactly {sorted(EXPLANATION_FIELDS)}")
            continue
        if not has_text(item.get("explanation_id")):
            errors.append(f"{label}.explanation_id must be a non-empty string")
            continue
        if not has_text(item.get("statement")):
            errors.append(f"{label}.statement must be a non-empty string")
        if item["explanation_id"] in seen:
            errors.append(f"{label}.explanation_id={item['explanation_id']} is declared more than once")
        seen.add(item["explanation_id"])
    return errors


def sample_errors(record: dict) -> list[str]:
    """Every proposed sample must quote its discriminating pair from the declarations."""
    samples = record.get("proposed_samples")
    if not isinstance(samples, list) or not samples:
        return ["next_batch.proposed_samples must be a non-empty array of the samples the next round would run"]
    declared = statement_map(record.get("competing_explanations"))
    errors: list[str] = []
    for index, sample in enumerate(samples):
        label = f"next_batch.proposed_samples[{index}]"
        if not isinstance(sample, dict) or not set(sample) <= SAMPLE_ALLOWED_FIELDS:
            errors.append(f"{label} must contain only {sorted(SAMPLE_ALLOWED_FIELDS)}")
            continue
        if not (has_text(sample.get("sample_reference")) or has_text(sample.get("formula_reference"))):
            errors.append(
                f"{label}: a sample that exists already is named by sample_reference, a formula the next round "
                "has yet to produce by formula_reference - at least one of the two must be supplied")
        hypothesis, separates = sample.get("hypothesis"), sample.get("separates")
        if not has_text(hypothesis) or hypothesis not in declared:
            errors.append(
                f"{label}.hypothesis={hypothesis!r} is not a declared explanation_id in "
                "next_batch.competing_explanations")
        if not isinstance(separates, list) or len(separates) != 2 or not all(isinstance(item, str) for item in separates):
            errors.append(f"{label}.separates must cite exactly two competing explanations (two explanation_ids)")
        elif separates[0] == separates[1]:
            errors.append(
                f"{label}.separates cites {separates[0]} twice: a sample that cannot separate two competing "
                "explanations is not worth a bench slot")
        else:
            undeclared = [item for item in separates if item not in declared]
            if undeclared:
                errors.append(
                    f"{label}.separates cites {undeclared} which next_batch.competing_explanations does not "
                    "declare")
    return errors


def evidence_errors(evidence: object) -> list[str]:
    if not isinstance(evidence, list) or not evidence:
        return ["next_batch.evidence must be a non-empty array of evidence items"]
    errors: list[str] = []
    for index, item in enumerate(evidence):
        label = f"next_batch.evidence[{index}]"
        if not isinstance(item, dict) or set(item) != EVIDENCE_FIELDS:
            errors.append(f"{label} must contain exactly {sorted(EVIDENCE_FIELDS)}")
            continue
        if item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"{label}.status must be OBSERVED, ASSUMED or GAP")
        elif item.get("status") == "GAP":
            errors.append(f"{label} contains GAP; current input is insufficient")
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field} must be a non-empty string")
    return errors


def cross_errors(campaign: dict, design: dict, variance: dict, record: dict) -> list[str]:
    """The three upstream artifacts and the campaign carrier must tell one story."""
    errors: list[str] = []
    upstreams = (
        ("campaign_artifact", campaign),
        ("experiment_design_artifact", design),
        ("variance_artifact", variance),
    )
    project_ids = {item.get("project_id") for _, item in upstreams}
    if len(project_ids) != 1:
        errors.append("all upstream artifact project_id values must match")
    scopes = {item.get("evidence_scope") for _, item in upstreams}
    if len(scopes) != 1:
        errors.append(
            "all upstream artifacts must declare one evidence_scope: this record is taken at one round boundary "
            "of one campaign and cannot inherit two")
    from_iteration = campaign.get("current_iteration")
    if is_count(from_iteration, 1):
        to_iteration = from_iteration + 1
        entry = campaign_entry(campaign)
        if isinstance(entry, dict):
            if entry.get("stop_state") != record.get("stop_state"):
                errors.append(
                    f"campaign_artifact.iterations (iteration {from_iteration}).stop_state="
                    f"{entry.get('stop_state')} contradicts the supplied next_batch.stop_state="
                    f"{record.get('stop_state')}: the carrier's round history and this decision must tell the "
                    "same story")
            reference = entry.get("next_batch_reference")
            if reference is not None and reference != record.get("next_batch_id"):
                errors.append(
                    f"campaign_artifact.iterations (iteration {from_iteration}).next_batch_reference={reference} "
                    f"is not the supplied next_batch.next_batch_id={record.get('next_batch_id')}")
            variance_reference = entry.get("variance_reference")
            if variance_reference is not None and variance_reference != variance.get("variance_id"):
                errors.append(
                    f"campaign_artifact.iterations (iteration {from_iteration}).variance_reference="
                    f"{variance_reference} is not the supplied variance_artifact.variance_id="
                    f"{variance.get('variance_id')}")
        if record.get("stop_state") == CONTINUE:
            cap = campaign.get("max_iterations")
            if is_count(cap, 1) and to_iteration > cap:
                errors.append(
                    f"next_batch.stop_state=CONTINUE would open iteration {to_iteration} beyond "
                    f"campaign_artifact.max_iterations={cap}; stop the inner loop and record PIVOT or KILL")
    if variance.get("campaign_reference") != campaign.get("campaign_id"):
        errors.append(
            f"variance_artifact.campaign_reference={variance.get('campaign_reference')} must equal "
            f"campaign_artifact.campaign_id={campaign.get('campaign_id')}")
    if variance.get("iteration") != from_iteration:
        errors.append(
            f"variance_artifact.iteration={variance.get('iteration')} must equal the campaign's current iteration "
            f"{from_iteration}: one variance assessment covers one round, and this decision is taken at that round "
            "boundary")
    return errors


def composed_artifact(data: dict, campaign: dict, design: dict) -> dict:
    """The artifact the builder writes: a pure function of the validated request + carrier.

    The iteration pair is derived from the carrier, never asserted by the caller, so the
    record cannot claim a round boundary the campaign does not have. Every string in the
    proposed samples comes from the declared explanations (see ``composed_sample``).
    """
    record = data["next_batch"]
    statements = statement_map(record.get("competing_explanations"))
    from_iteration = campaign.get("current_iteration") if is_count(campaign.get("current_iteration"), 1) else 0
    samples = record.get("proposed_samples")
    artifact = {
        "schema_version": "0.1.0",
        "artifact_type": "next_batch",
        "project_id": campaign.get("project_id"),
        "stage": NEXT_BATCH_STAGE,
        "evidence_scope": campaign.get("evidence_scope"),
        "next_batch_id": record.get("next_batch_id"),
        "campaign_reference": campaign.get("campaign_id"),
        "from_iteration": from_iteration,
        "to_iteration": from_iteration + 1,
        "proposed_samples": [
            composed_sample(sample, statements) for sample in samples if isinstance(sample, dict)
        ] if isinstance(samples, list) else [],
        "information_gain_basis": record.get("information_gain_basis"),
        "bench_slots_required": record.get("bench_slots_required"),
        "stop_state": record.get("stop_state"),
        "evidence": record.get("evidence"),
    }
    if record.get("stop_rationale") is not None:
        artifact["stop_rationale"] = record.get("stop_rationale")
    if isinstance(record.get("next_round_budget"), dict):
        artifact["next_round_budget"] = record.get("next_round_budget")
    # The decision block is derived from the record's own fields, so the validator can
    # re-derive it and a hand-edited artifact fails.
    return {**artifact, **expected_decision_fields(artifact, artifact["campaign_reference"])}


def artifact_schema_errors(artifact: object) -> list[str]:
    try:
        loaded, registry = load_schemas()
    except (OSError, json.JSONDecodeError) as error:
        return [f"the next_batch schemas cannot be read: {error}"]
    return [
        f"next_batch: {error.message}"
        for error in Draft202012Validator(loaded["next_batch.schema.json"], registry=registry).iter_errors(artifact)
    ]


def vocabulary_errors() -> list[str]:
    """The mirrored stop-state vocabulary must equal the contract's own enum.

    One list, two readers: this module's mirror and the schema. If the contract widens and
    the mirror is not widened with it, the run fails here instead of refusing a legal value
    (or accepting an illegal one) somewhere downstream.
    """
    try:
        loaded, _ = load_schemas()
        enum = loaded["next_batch.schema.json"]["properties"]["stop_state"]["enum"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        return [f"the next_batch schemas cannot be read: {error}"]
    if set(enum) != set(STOP_STATES):
        return [
            f"the mirrored stop-state vocabulary {list(STOP_STATES)} drifted from next_batch.schema.json's enum "
            f"{enum}; update next_batch_policy.STOP_STATES"]
    return []


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != INPUT_FIELDS:
        return [f"input must contain exactly {sorted(INPUT_FIELDS)}"]
    errors, artifacts = [], {}
    for key, checker in (
        ("campaign_artifact", campaign_errors),
        ("experiment_design_artifact", design_errors),
        ("variance_artifact", variance_errors),
    ):
        item_errors, artifact = read_artifact(data.get(key), input_path, key)
        errors.extend(item_errors)
        if artifact is not None:
            errors.extend(checker(artifact))
        artifacts[key] = artifact
    errors.extend(vocabulary_errors())
    campaign, design, variance = (artifacts[key] for key in ("campaign_artifact", "experiment_design_artifact", "variance_artifact"))
    if campaign is not None and design is not None and variance is not None:
        record_errors_ = record_errors(data.get("next_batch"), design)
        errors.extend(record_errors_)
        if isinstance(data.get("next_batch"), dict):
            errors.extend(cross_errors(campaign, design, variance, data["next_batch"]))
        if not errors:
            # Only composed and schema-checked once the structure is clean, so a broken
            # request reports named, actionable refusals instead of a schema error storm.
            errors.extend(artifact_schema_errors(composed_artifact(data, campaign, design)))
    return errors


def notes_for(data: object, input_path: Path) -> list[str]:
    """Declared-boundary notes. Printed, never written into the artifact.

    The record's own contract has no slot for them, and they report what the input does
    NOT declare (an unbounded round) or what the round's variance verdict routes to - both
    are readings of supplied fields, not new claims.
    """
    notes: list[str] = []
    _, design = read_artifact(data.get("experiment_design_artifact"), input_path, "experiment_design_artifact")
    availability, _ = design_availability(design)
    if availability is None:
        notes.append(
            "the round's design declares no bench availability (resource_envelope.bench_slots or "
            "available_bench_slots), so bench_slots_required is recorded without a declared bound")
    _, variance = read_artifact(data.get("variance_artifact"), input_path, "variance_artifact")
    verdict = variance.get("verdict") if isinstance(variance, dict) else None
    if verdict in VARIANCE_ROUTING_NOTES:
        notes.append(f"round verdict {verdict}: {VARIANCE_ROUTING_NOTES[verdict]}")
    return notes


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_next_batch.py <input.json>")
        return 1
    path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    record = data["next_batch"]
    print("READY: input can form one NEXT_BATCH_DECIDED record only")
    print(
        f"GATE: stop_state={record['stop_state']} bench_slots_required={record['bench_slots_required']} "
        f"proposed_samples={len(record['proposed_samples'])} "
        f"declared_explanations={len(record['competing_explanations'])}")
    for note in notes_for(data, path):
        print(f"NOTE: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
