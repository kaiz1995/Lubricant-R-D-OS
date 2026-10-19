"""Deterministic grease-batch policy: the trajectory judgement and the release rule.

Stage 9 (grease-batch) is where "recipe + process = product" lands. A formula fixes
intent; a trajectory records what the equipment actually did. The same formula through
a different kettle may not be the same product, because the soap-fibre skeleton is set
by saponification, phase inversion, cooling rate and milling. This module is the single
place where that trajectory is judged, and it is shared by the preflight, the builder
and the validator so the three scripts cannot disagree about the same input.

Four rules, all fail-closed:

1. PROVENANCE IS STRUCTURAL. Every executed step must carry its own ``source`` and
   ``evidence_id``, and that ``evidence_id`` must resolve to an evidence item whose
   status is not GAP. A process parameter without provenance is a hard reject, not a
   warning (red line NO Provenance-Free Parameters).

2. THE DEVIATION IS RECORDED, NOT ASSERTED. For a numeric step the recorded
   ``deviation`` must equal ``actual - setpoint``, the step must declare a numeric
   ``tolerance``, and a step whose ``|deviation|`` exceeds that tolerance must be
   recorded DEVIATED. The cautious direction - recording DEVIATED while the value is
   inside tolerance, for example because the hold time ran long - is allowed, because a
   stricter per-step judgement can never make a batch look better than it was.

3. THE BATCH VERDICT IS POLICED, NOT DERIVED AWAY. The caller declares
   ``batch_verdict`` in {VALID, DEVIATED, VOID} and this policy refuses the illegal
   combinations: VALID is illegal over a DEVIATED step, DEVIATED must be justified by
   a DEVIATED step or a recorded anomaly, and VOID must state why. Whether a batch is
   voided is a production decision the record must carry, so it is not inferred.

4. THE DERIVED TRAJECTORY TRACE. ``schemas/batch.schema.json`` fixes seven fields per
   step and forbids extras, so the input-side ``tolerance`` and ``source`` cannot be
   written into the trajectory. The builder therefore emits one canonical evidence item
   per step (``TRAJ {...}`` with a fixed JSON payload, id ``E-TRAJ-<batch_id>-<n>``)
   and the validator re-derives that line from the artifact's own trajectory. The
   tolerance boundary is therefore re-checked on the frozen artifact, not only at the
   gate. Stated boundary: an editor who rewrites both a step and its trace line can
   still forge a consistent artifact - the trace makes the edit visible, it does not
   make forgery impossible, and no code path accepts a hand-edited trajectory silently.

The release rule (放行判据): only a batch whose every step is within its declared
tolerance (``batch_verdict: VALID``) is released to Stage 10 (grease-screening). A
DEVIATED batch holds at Stage 9 until the deviation is dispositioned, and a VOID batch
is never released. The sample record produced beside the batch carries the same
decision, because an unreleased batch has no releasable sample.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime

INPUT_FIELDS = {
    "project_artifact",
    "design_space_artifact",
    "experiment_design_artifact",
    "batch",
    "sample",
    "evidence_scope",
    "evidence",
}
# Input-only trajectory fields: ``tolerance``, ``source`` and ``evidence_id`` are
# consumed by this policy and by the derived trace, but the frozen batch contract has
# no slot for them (additionalProperties: false), so the builder strips them.
BATCH_INPUT_FIELDS = {
    "batch_id",
    "formula_reference",
    "scale_class",
    "trajectory",
    "raw_material_lots",
    "operator",
    "equipment",
    "anomalies",
    "batch_verdict",
}
BATCH_ARTIFACT_FIELDS = (
    "batch_id",
    "formula_reference",
    "scale_class",
    "trajectory",
    "raw_material_lots",
    "operator",
    "equipment",
    "anomalies",
    "batch_verdict",
)
TRAJECTORY_STEP_INPUT_FIELDS = {
    "step_type",
    "setpoint",
    "actual",
    "unit",
    "duration_s",
    "deviation",
    "deviation_verdict",
    "tolerance",
    "source",
    "evidence_id",
}
TRAJECTORY_STEP_ARTIFACT_FIELDS = (
    "step_type",
    "setpoint",
    "actual",
    "unit",
    "duration_s",
    "deviation",
    "deviation_verdict",
)
# ``batch_reference`` and ``formula_reference`` are NOT sample inputs: they are bound
# to the batch record this sample was taken from, so supplying them is a hard reject.
SAMPLE_INPUT_FIELDS = {
    "sample_id",
    "label",
    "prepared_at",
    "storage",
    "chain_of_custody",
    "status",
}
SAMPLE_ARTIFACT_FIELDS = (
    "sample_id",
    "label",
    "prepared_at",
    "storage",
    "chain_of_custody",
    "status",
)
LABEL_FIELDS = {"printed_text", "printed_at"}
CUSTODY_FIELDS = {"from", "to", "at", "purpose"}
EVIDENCE_FIELDS = {"evidence_id", "statement", "source", "status"}
EVIDENCE_STATUSES = ("OBSERVED", "ASSUMED", "GAP")
EVIDENCE_SCOPES = ("SYNTHETIC", "PHYSICAL")

# The grease route, mirrored from schemas/batch.schema.json. SAPONIFICATION is the
# step that generates the soap in situ, so a grease batch record without it is not a
# recorded grease batch; the other route steps are reported as NOTE lines when absent
# and are never invented to fill the trajectory out.
ROUTE_STEP_TYPES = (
    "SAPONIFICATION",
    "DEHYDRATION",
    "PHASE_INVERSION",
    "DILUTION_COOLING",
    "MILLING",
    "HOMOGENIZATION",
    "VACUUM_DEAERATION",
    "FILLING",
    "SOAP_HOLD",
    "DILUTION_CURVE",
    "RIPENING",
    "FILLING_TEMPERATURE",
)
REQUIRED_ROUTE_STEP_TYPES = ("SAPONIFICATION",)
STEP_VERDICTS = ("WITHIN", "DEVIATED")
BATCH_VERDICTS = ("VALID", "DEVIATED", "VOID")
SCALE_CLASSES = ("LAB", "PILOT", "PRODUCTION")
SAMPLE_STATUSES = ("PREPARED", "IN_TRANSIT", "CONSUMED", "ARCHIVED", "VOID")

# Canonical derived-trajectory trace. The prefix is reserved: a caller evidence item
# may not claim it, because the validator must be able to find the derived line.
TRACE_EVIDENCE_PREFIX = "E-TRAJ-"
TRACE_STATEMENT_PREFIX = "TRAJ "
# A reported deviation is accepted when it agrees with actual - setpoint to within
# half of a last-digit rounding step, so a log rounded to one decimal still passes.
DEVIATION_ABS_TOLERANCE = 0.05
ISO_DATE_LENGTH = 10
# Mirrors the label.printed_at pattern of schemas/sample.schema.json.
ISO_DATE_OR_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?$"
)


def has_text(value: object) -> bool:
    """True for a non-empty, non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_non_negative_number(value: object) -> bool:
    return is_finite_number(value) and value >= 0


def parse_iso_date(value: object) -> date | None:
    """ISO date (YYYY-MM-DD) or None."""
    if not has_text(value) or len(value) != ISO_DATE_LENGTH:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_iso_date_or_datetime(value: object) -> datetime | None:
    """ISO date or date-time accepted by the sample label contract, or None."""
    if not has_text(value) or not ISO_DATE_OR_DATETIME_RE.match(value.strip()):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def numeric_step(step: object) -> bool:
    """True when both setpoint and actual are numbers (the deviation is arithmetic)."""
    if not isinstance(step, dict):
        return False
    return is_finite_number(step.get("setpoint")) and is_finite_number(step.get("actual"))


def expected_deviation(step: object) -> float | None:
    """actual - setpoint for a numeric step, else None."""
    if not numeric_step(step):
        return None
    return float(step["actual"]) - float(step["setpoint"])


def trajectory_trace_id(batch_id: object, index: int) -> str:
    return f"{TRACE_EVIDENCE_PREFIX}{batch_id}-{index + 1:02d}"


def trajectory_trace_line(index: int, step: object, tolerance: object) -> str:
    """The canonical derived trace of one executed step (builder writes, validator re-derives)."""
    payload = {
        "step_index": index,
        "step_type": step.get("step_type") if isinstance(step, dict) else None,
        "setpoint": step.get("setpoint") if isinstance(step, dict) else None,
        "actual": step.get("actual") if isinstance(step, dict) else None,
        "unit": step.get("unit") if isinstance(step, dict) else None,
        "duration_s": step.get("duration_s") if isinstance(step, dict) else None,
        "deviation": step.get("deviation") if isinstance(step, dict) else None,
        "tolerance": tolerance,
        "deviation_verdict": step.get("deviation_verdict") if isinstance(step, dict) else None,
    }
    return TRACE_STATEMENT_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def parse_trajectory_trace(statement: object) -> dict | None:
    """The payload of a canonical ``TRAJ {...}`` statement, or None if malformed."""
    if not has_text(statement) or not statement.startswith(TRACE_STATEMENT_PREFIX):
        return None
    try:
        payload = json.loads(statement[len(TRACE_STATEMENT_PREFIX) :])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def step_field_errors(step: object, label: str) -> list[str]:
    """Shape checks shared by the input gate and the artifact validator."""
    if not isinstance(step, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    if step.get("step_type") not in ROUTE_STEP_TYPES:
        errors.append(f"{label}.step_type is not one of the grease route step types")
    for field in ("setpoint", "actual"):
        value = step.get(field)
        if not is_finite_number(value) and not has_text(value):
            errors.append(f"{label}.{field} must be a number or a non-empty string")
    if not has_text(step.get("unit")):
        errors.append(f"{label}.unit")
    if not is_non_negative_number(step.get("duration_s")):
        errors.append(f"{label}.duration_s must be a non-negative number")
    if not is_finite_number(step.get("deviation")) and not has_text(step.get("deviation")):
        errors.append(f"{label}.deviation must be a number or a non-empty string")
    if step.get("deviation_verdict") not in STEP_VERDICTS:
        errors.append(f"{label}.deviation_verdict must be WITHIN or DEVIATED")
    return errors


def deviation_verdict_errors(index: int, step: object, tolerance: object) -> list[str]:
    """The tolerance boundary and the deviation arithmetic for one step.

    ``tolerance`` is the input-side tolerance band for this step: a non-negative number
    for a numeric step, a non-empty string for a qualitative step. The same check runs
    at the gate (on the input) and on the frozen artifact (on the tolerance recovered
    from the derived trace).
    """
    label = f"trajectory[{index}]"
    if not isinstance(step, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    verdict = step.get("deviation_verdict")
    deviation = step.get("deviation")
    if numeric_step(step):
        if not is_non_negative_number(tolerance):
            errors.append(f"{label}.tolerance must be a non-negative number for a numeric step")
            return errors
        if not is_finite_number(deviation):
            errors.append(f"{label}.deviation must be numeric when setpoint and actual are numeric")
            return errors
        computed = expected_deviation(step)
        if computed is not None and abs(float(deviation) - computed) > DEVIATION_ABS_TOLERANCE:
            errors.append(
                f"{label}.deviation must equal actual - setpoint: recorded {deviation}, computed {round(computed, 6)}"
            )
        if abs(float(deviation)) > float(tolerance) and verdict != "DEVIATED":
            errors.append(
                f"{label}: deviation {deviation} exceeds the declared tolerance {tolerance} "
                f"but the step is recorded {verdict or 'without a verdict'}"
            )
        return errors
    if not has_text(tolerance):
        errors.append(f"{label}.tolerance must be a non-empty string for a qualitative step")
    if not has_text(deviation) and not is_finite_number(deviation):
        errors.append(f"{label}.deviation must be recorded for every step")
    return errors


def trajectory_trace_errors(artifact: object) -> list[str]:
    """Every trajectory step must be accompanied by its canonical derived trace.

    This is what lets the frozen contract still be re-checked: the artifact's
    ``evidence`` list carries the tolerance and the verdict of every step, so a
    hand-edited trajectory that does not match its own trace is a FAIL.
    """
    if not isinstance(artifact, dict):
        return ["artifact must be a JSON object"]
    trajectory = artifact.get("trajectory")
    evidence = artifact.get("evidence")
    if not isinstance(trajectory, list) or not isinstance(evidence, list):
        return []
    batch_id = artifact.get("batch_id")
    by_id = {
        item.get("evidence_id"): item
        for item in evidence
        if isinstance(item, dict) and has_text(item.get("evidence_id"))
    }
    errors: list[str] = []
    for index, step in enumerate(trajectory):
        label = f"trajectory[{index}]"
        if not isinstance(step, dict):
            continue
        trace_id = trajectory_trace_id(batch_id, index)
        item = by_id.get(trace_id)
        if item is None:
            errors.append(
                f"{label}: the derived trajectory trace {trace_id} is missing from evidence; "
                "a trajectory without its derived trace cannot be judged"
            )
            continue
        if not has_text(item.get("source")):
            errors.append(f"{trace_id}.source is required: a derived trace must keep the step's source")
        payload = parse_trajectory_trace(item.get("statement"))
        if payload is None:
            errors.append(f"{trace_id} is not a canonical TRAJ trace line")
            continue
        tolerance = payload.get("tolerance")
        if trajectory_trace_line(index, step, tolerance) != item.get("statement"):
            errors.append(
                f"{label}: the recorded trajectory does not match its derived trace {trace_id} "
                "(a step was edited after the batch was recorded)"
            )
            continue
        errors.extend(deviation_verdict_errors(index, step, tolerance))
    return errors


def batch_verdict_errors(batch: object) -> list[str]:
    """The declared batch verdict must be legal over its own trajectory."""
    if not isinstance(batch, dict):
        return ["batch must be an object"]
    trajectory = batch.get("trajectory")
    anomalies = batch.get("anomalies")
    verdict = batch.get("batch_verdict")
    errors: list[str] = []
    if verdict not in BATCH_VERDICTS:
        errors.append("batch.batch_verdict must be VALID, DEVIATED, or VOID")
        return errors
    steps = [step for step in trajectory if isinstance(step, dict)] if isinstance(trajectory, list) else []
    deviated = [
        index for index, step in enumerate(steps) if step.get("deviation_verdict") == "DEVIATED"
    ]
    recorded_anomaly = isinstance(anomalies, list) and any(has_text(item) for item in anomalies)
    if verdict == "VALID" and deviated:
        errors.append(
            "batch.batch_verdict VALID is illegal while "
            + ", ".join(f"trajectory[{index}]" for index in deviated)
            + " is recorded DEVIATED"
        )
    if verdict == "DEVIATED" and not deviated and not recorded_anomaly:
        errors.append(
            "batch.batch_verdict DEVIATED must be justified: no trajectory step is DEVIATED "
            "and no anomaly is recorded"
        )
    if verdict == "VOID" and not recorded_anomaly:
        errors.append("batch.batch_verdict VOID must state why: batch.anomalies is empty")
    return errors


def trajectory_errors(trajectory: object, evidence_ids: set[str]) -> list[str]:
    """Input-side trajectory checks: shape, provenance, tolerance boundary, coverage."""
    if not isinstance(trajectory, list) or not trajectory:
        return ["batch.trajectory must be a non-empty array of executed process steps"]
    errors: list[str] = []
    for index, step in enumerate(trajectory):
        label = f"batch.trajectory[{index}]"
        if not isinstance(step, dict):
            errors.append(label)
            continue
        unknown = sorted(set(step) - TRAJECTORY_STEP_INPUT_FIELDS)
        missing = sorted(TRAJECTORY_STEP_INPUT_FIELDS - set(step))
        if unknown or missing:
            errors.append(f"{label}: unexpected={unknown or 'none'} missing={missing or 'none'}")
            continue
        errors.extend(step_field_errors(step, label))
        for field in ("source", "evidence_id"):
            if not has_text(step.get(field)):
                errors.append(f"{label}.{field} is required: a process parameter without provenance is a hard reject")
        evidence_id = step.get("evidence_id")
        if has_text(evidence_id) and evidence_id not in evidence_ids:
            errors.append(f"{label}.evidence_id {evidence_id} does not resolve to an evidence item")
        errors.extend(deviation_verdict_errors(index, step, step.get("tolerance")))
    step_types = [step.get("step_type") for step in trajectory if isinstance(step, dict)]
    for required in REQUIRED_ROUTE_STEP_TYPES:
        if required not in step_types:
            errors.append(
                f"batch.trajectory must contain at least one {required} step: the soap is generated "
                "in situ, so a grease batch without it is not a recorded grease batch"
            )
    return errors


def batch_errors(batch: object) -> list[str]:
    """Structural batch-record checks that do not depend on the evidence list."""
    if not isinstance(batch, dict):
        return ["batch must be an object"]
    unknown = sorted(set(batch) - BATCH_INPUT_FIELDS)
    missing = sorted(BATCH_INPUT_FIELDS - set(batch))
    if unknown or missing:
        return [f"batch must contain only the batch-record input fields; unexpected={unknown or 'none'} missing={missing or 'none'}"]
    errors: list[str] = []
    for field in ("batch_id", "formula_reference", "operator", "equipment"):
        if not has_text(batch.get(field)):
            errors.append(f"batch.{field}")
    if batch.get("scale_class") not in SCALE_CLASSES:
        errors.append("batch.scale_class must be LAB, PILOT, or PRODUCTION")
    lots = batch.get("raw_material_lots")
    if not isinstance(lots, list) or not lots:
        errors.append("batch.raw_material_lots must be a non-empty array of lot identifiers")
    else:
        for index, lot in enumerate(lots):
            if not has_text(lot):
                errors.append(f"batch.raw_material_lots[{index}] must be a non-empty string")
        if len({lot for lot in lots if has_text(lot)}) != len(lots):
            errors.append("batch.raw_material_lots must be distinct: a duplicated lot is not two lots")
    anomalies = batch.get("anomalies")
    if not isinstance(anomalies, list):
        errors.append("batch.anomalies must be an array (an empty array records 'none observed')")
    else:
        for index, item in enumerate(anomalies):
            if not has_text(item):
                errors.append(f"batch.anomalies[{index}] must be a non-empty string")
    return errors


def sample_errors(sample: object, batch: object) -> list[str]:
    """Sample checks: label-printer convention, preparation date, custody chain."""
    if not isinstance(sample, dict):
        return ["sample must be an object"]
    unknown = sorted(set(sample) - SAMPLE_INPUT_FIELDS)
    missing = sorted(SAMPLE_INPUT_FIELDS - set(sample))
    if unknown or missing:
        return [
            "sample must contain only the sample-record input fields; "
            f"unexpected={unknown or 'none'} missing={missing or 'none'} "
            "(batch_reference and formula_reference are bound to the batch record and must not be supplied)"
        ]
    batch_id = batch.get("batch_id") if isinstance(batch, dict) else None
    formula_reference = batch.get("formula_reference") if isinstance(batch, dict) else None
    errors: list[str] = []
    sample_id = sample.get("sample_id")
    if not has_text(sample_id):
        errors.append("sample.sample_id")
    elif re.search(r"\s", sample_id) or "|" in sample_id:
        errors.append(
            "sample.sample_id must be a single printable token: the label printer cannot print "
            "an id containing whitespace or '|'"
        )
    label = sample.get("label")
    if not isinstance(label, dict) or set(label) != LABEL_FIELDS:
        errors.append("sample.label must contain printed_text and printed_at")
    else:
        printed_text = label.get("printed_text")
        if not has_text(printed_text):
            errors.append("sample.label.printed_text")
        else:
            for token, description in (
                (sample_id, f"the sample_id {sample_id}"),
                (batch_id, f"the batch reference {batch_id}"),
                (formula_reference, f"the formula reference {formula_reference}"),
            ):
                if has_text(token) and token not in printed_text:
                    errors.append(
                        f"sample.label.printed_text must contain {description}: the id on the record "
                        "must be the id the label printer printed"
                    )
        if parse_iso_date_or_datetime(label.get("printed_at")) is None:
            errors.append("sample.label.printed_at must be an ISO date or date-time")
    prepared_at = parse_iso_date(sample.get("prepared_at"))
    if prepared_at is None:
        errors.append("sample.prepared_at must be an ISO date YYYY-MM-DD")
    printed_at = parse_iso_date_or_datetime(label.get("printed_at")) if isinstance(label, dict) else None
    if prepared_at is not None and printed_at is not None and printed_at.date() < prepared_at:
        errors.append("sample.label.printed_at must not predate sample.prepared_at")
    if not has_text(sample.get("storage")):
        errors.append("sample.storage")
    custody = sample.get("chain_of_custody")
    if not isinstance(custody, list) or not custody:
        errors.append(
            "sample.chain_of_custody must be a non-empty array: a sample with no recorded custody "
            "cannot support a downstream measurement"
        )
    else:
        previous: date | None = None
        for index, entry in enumerate(custody):
            label_text = f"sample.chain_of_custody[{index}]"
            if not isinstance(entry, dict):
                errors.append(label_text)
                continue
            unknown = sorted(set(entry) - CUSTODY_FIELDS)
            missing = sorted(CUSTODY_FIELDS - set(entry))
            if unknown or missing:
                errors.append(f"{label_text}: unexpected={unknown or 'none'} missing={missing or 'none'}")
                continue
            for field in ("from", "to", "purpose"):
                if not has_text(entry.get(field)):
                    errors.append(f"{label_text}.{field}")
            at = parse_iso_date(entry.get("at"))
            if at is None:
                errors.append(f"{label_text}.at must be an ISO date YYYY-MM-DD")
                continue
            if prepared_at is not None and at < prepared_at:
                errors.append(f"{label_text}.at must not predate sample.prepared_at")
            if previous is not None and at < previous:
                errors.append("sample.chain_of_custody must be in non-decreasing time order")
            previous = at
    if sample.get("status") not in SAMPLE_STATUSES:
        errors.append("sample.status must be PREPARED, IN_TRANSIT, CONSUMED, ARCHIVED, or VOID")
    return errors


def recorded_sample(sample: object) -> dict:
    """Project a stored sample ARTIFACT back to its recordable input form.

    The artifact carries the common contract block plus the batch/formula binding; only
    the six sample fields are judged by :func:`sample_errors`, so the validator can reuse
    exactly the gate rule instead of keeping a second copy of it.
    """
    if not isinstance(sample, dict):
        return {}
    return {field: sample.get(field) for field in SAMPLE_INPUT_FIELDS}


def sample_binding_errors(sample: object, batch: object) -> list[str]:
    """A stored sample must be bound to the batch record it was taken from."""
    if not isinstance(sample, dict) or not isinstance(batch, dict):
        return []
    errors: list[str] = []
    if sample.get("batch_reference") != batch.get("batch_id"):
        errors.append(
            f"sample.batch_reference {sample.get('batch_reference')!r} must equal the batch record's "
            f"batch_id {batch.get('batch_id')!r}"
        )
    if sample.get("formula_reference") != batch.get("formula_reference"):
        errors.append(
            "sample.formula_reference must equal the batch record's formula_reference: a measurement "
            "must stay bound to the formulation even if the batch record is revised"
        )
    return errors


def recorded_batch(batch: dict) -> dict:
    """Project the batch record into its artifact form.

    ``tolerance``, ``source`` and ``evidence_id`` are input-only: the frozen batch
    contract fixes seven trajectory fields and forbids extras, so they are consumed by
    the policy (and preserved in the derived trace) instead of being written into the
    trajectory itself.
    """
    artifact = {field: batch.get(field) for field in BATCH_ARTIFACT_FIELDS}
    trajectory = batch.get("trajectory")
    if isinstance(trajectory, list):
        artifact["trajectory"] = [
            {field: step.get(field) for field in TRAJECTORY_STEP_ARTIFACT_FIELDS}
            if isinstance(step, dict)
            else step
            for step in trajectory
        ]
    return artifact


def route_coverage_notes(batch: object) -> list[str]:
    """Audible NOTE lines for route steps the trajectory does not record.

    An unrecorded step stays unrecorded: this never invents a step to fill the
    trajectory out, it only makes the absence visible.
    """
    if not isinstance(batch, dict):
        return []
    trajectory = batch.get("trajectory")
    if not isinstance(trajectory, list):
        return []
    recorded = {step.get("step_type") for step in trajectory if isinstance(step, dict)}
    absent = [step_type for step_type in ROUTE_STEP_TYPES if step_type not in recorded]
    if not absent:
        return []
    return [
        "NOTE: trajectory does not record "
        + ", ".join(absent)
        + "; an unrecorded route step stays unrecorded and is never invented"
    ]


def step_notes(batch: object) -> list[str]:
    """One line per step so the run is never silent about what was judged."""
    if not isinstance(batch, dict):
        return []
    trajectory = batch.get("trajectory")
    if not isinstance(trajectory, list):
        return []
    notes: list[str] = []
    for index, step in enumerate(trajectory):
        if not isinstance(step, dict):
            continue
        tolerance = step.get("tolerance")
        notes.append(
            f"NOTE: trajectory[{index}] {step.get('step_type')} deviation={step.get('deviation')} "
            f"tolerance={tolerance} verdict={step.get('deviation_verdict')}"
        )
    return notes


def gate_blockers(batch: object) -> list[str]:
    """The release rule: only a VALID batch may be released to Stage 10."""
    if not isinstance(batch, dict):
        return ["batch must be an object"]
    verdict = batch.get("batch_verdict")
    if verdict == "VALID":
        return []
    if verdict == "DEVIATED":
        return ["the batch carries a recorded out-of-tolerance deviation (batch_verdict DEVIATED)"]
    if verdict == "VOID":
        return ["the batch is voided (batch_verdict VOID)"]
    return ["batch_verdict is not a recorded verdict"]


def scope_prefix(evidence_scope: object) -> str:
    return (
        "Synthetic test fixture / NOT_FOR_PHYSICAL_EXECUTION: this record cannot authorize stage advancement. "
        if evidence_scope == "SYNTHETIC"
        else ""
    )


def expected_decision_fields(batch: object, evidence_scope: object) -> dict[str, str]:
    """The canonical batch decision block, recomputed identically by builder and validator.

    A pure function of the artifact's own fields, so the validator needs nothing else.
    """
    if not isinstance(batch, dict):
        batch = {}
    trajectory = batch.get("trajectory")
    steps = [step for step in trajectory if isinstance(step, dict)] if isinstance(trajectory, list) else []
    deviated = [index for index, step in enumerate(steps) if step.get("deviation_verdict") == "DEVIATED"]
    verdict = batch.get("batch_verdict")
    blockers = gate_blockers(batch)
    decision = "GO" if not blockers else "HOLD"
    batch_id = batch.get("batch_id")
    if verdict == "VALID":
        next_action = (
            f"Route the sample taken from {batch_id} to Stage 10 (grease-screening) before it may "
            "consume a bench slot."
        )
    elif verdict == "DEVIATED":
        next_action = (
            f"Stay at Stage 9: disposition the recorded deviation on {batch_id} before its sample is "
            "screened or sent to the bench."
        )
    elif verdict == "VOID":
        next_action = (
            f"Stay at Stage 9: {batch_id} is voided and its sample must not be released; make a "
            "replacement batch against the same baseline."
        )
    else:
        next_action = f"Stay at Stage 9: {batch_id} carries no legal batch_verdict."
    return {
        "decision_question": (
            f"Was batch {batch_id} produced from {batch.get('formula_reference')} against the declared "
            "process baseline, step by step, from the recorded lots?"
        ),
        "hypothesis": (
            "A batch whose trajectory records setpoint, actual, duration, and an explicit per-step "
            "deviation verdict against the baseline is the landing point where recipe plus process "
            "becomes a traceable product."
        ),
        "uncertainty": (
            f"{scope_prefix(evidence_scope)}The trajectory records what the equipment actually did; it is "
            "not independently verified, and recording a within-tolerance trajectory does not establish "
            f"product performance or that the sample will clear screening. batch_verdict={verdict}."
        ),
        "decision_rule": (
            "A batch is released to Stage 10 only when every trajectory step is within its declared "
            "tolerance (batch_verdict VALID); a DEVIATED batch holds until the deviation is dispositioned, "
            "and a VOID batch is never released."
        ),
        "result": (
            f"batch {batch_id}: {len(steps)} step(s) recorded, {len(deviated)} DEVIATED, "
            f"{len(steps) - len(deviated)} WITHIN; batch_verdict={verdict}."
        ),
        "decision": decision,
        "next_action": next_action,
    }


def expected_sample_decision_fields(
    sample: object, batch_reference: object, batch_verdict: object, evidence_scope: object
) -> dict[str, str]:
    """The canonical sample decision block.

    ``batch_reference`` is passed explicitly rather than parsed back out of the printed
    label: the builder binds it from the batch record and the validator reads the stored
    ``batch_reference`` field, so both sides compute the same block from the same value.
    """
    if not isinstance(sample, dict):
        sample = {}
    sample_id = sample.get("sample_id")
    decision = "GO" if batch_verdict == "VALID" else "HOLD"
    if batch_verdict == "VALID":
        next_action = (
            f"Hand sample {sample_id} to Stage 10 (grease-screening) under the recorded custody chain."
        )
    elif batch_verdict == "DEVIATED":
        next_action = (
            f"Hold sample {sample_id}: its batch is DEVIATED, so the deviation must be dispositioned "
            "before the sample leaves Stage 9."
        )
    else:
        next_action = (
            f"Void sample {sample_id}: its batch is voided and must not reach the bench."
        )
    return {
        "decision_question": (
            f"Can sample {sample_id} taken from batch {batch_reference} be traced to the bench under a "
            "complete chain of custody?"
        ),
        "hypothesis": (
            f"{sample_id} carries the printed label, the preparation date, the storage condition, and "
            "every handover, so a downstream measurement can be bound to it."
        ),
        "uncertainty": (
            f"{scope_prefix(evidence_scope)}The label text, custody names, and dates are recorded as "
            "supplied; a sample record does not establish that its batch is within tolerance. "
            f"batch_verdict={batch_verdict}."
        ),
        "decision_rule": (
            "A sample may be handed to the bench only when its batch record is released "
            "(batch_verdict VALID); a sample from a DEVIATED or VOID batch is held at Stage 9."
        ),
        "result": (
            f"sample {sample_id} recorded at status {sample.get('status')} against batch "
            f"{batch_reference} (batch_verdict={batch_verdict})."
        ),
        "decision": decision,
        "next_action": next_action,
    }
