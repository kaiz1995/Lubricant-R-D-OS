"""Reject incomplete merged bench-registration input before the artifact is built.

One request registers ONE bench AND opens ITS round plan (contract v1.0.0 merged
the former two-step bench-registration / campaign-opening pair into one stage and
one artifact). Registration is fail-closed on both halves:

* the bench half needs availability windows, a strictly positive cycle time,
  per-run cost with a source, provenance, and evidence without GAP; the usable
  slot count is DERIVED (never hand-supplied) by bench_policy.available_bench_slots;
* the round-plan half needs a bounded cap (supplied, or read from
  ``contracts/state-machine.json`` when the campaign block omits it -- the
  contract's published figure, never an invented one), a legal ledger (W0/W1/W2
  position, only CONTINUE authorizes another round, exit-round-only
  model/next-batch references), a pairing design, and evidence without GAP;
* the two halves share ONE project and ONE evidence_scope: a supplied
  campaign.project_reference must equal bench.project_reference, and
  campaign.evidence_scope must equal bench.evidence_scope.

The request carries exactly two keys, ``bench`` and ``campaign``. There are no
upstream artifact paths: after the merge the bench block IS the registration, so
``project_reference`` inside it is the single project source -- the former
``project_artifact`` / ``bench_artifacts`` keys and the campaign's
``bench_references`` list are gone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bench_policy import (
    ALLOWED_FIELDS,
    BENCH_STAGE,
    CAMPAIGN_REQUEST_FIELDS,
    EVIDENCE_SCOPES,
    INPUT_FIELDS,
    REQUIRED_CAMPAIGN_REQUEST_FIELDS,
    WINDOW_FIELDS,
    available_bench_slots,
    expected_decision_fields,
    has_gap,
    has_text,
    is_finite_number,
    is_non_negative_int,
    parse_iso_date,
    record_errors,
    resolve_cap,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
# The schemas this preflight loads: the shared contract and the merged bench
# contract the built artifact must satisfy. No upstream artifact contracts are
# loaded: the bench block IS the registration after the merge.
SCHEMA_NAMES = ("common.schema.json", "bench.schema.json")
EVIDENCE_FIELDS = {"evidence_id", "statement", "source", "status"}
COST_FIELDS = {"value", "unit", "source"}
INPUT_BLOCKS = {"bench", "campaign"}


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def window_errors(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["bench.availability_window"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, window in enumerate(value):
        label = f"bench.availability_window[{index}]"
        if not isinstance(window, dict) or not set(window) <= WINDOW_FIELDS or not {"window_id", "start", "end"} <= set(window):
            errors.append(label)
            continue
        window_id = window.get("window_id")
        if not has_text(window_id):
            errors.append(f"{label}.window_id")
        elif window_id in seen:
            errors.append(f"{label}.window_id {window_id} is duplicated")
        else:
            seen.add(window_id)
        start, end = parse_iso_date(window.get("start")), parse_iso_date(window.get("end"))
        if start is None:
            errors.append(f"{label}.start must be an ISO date YYYY-MM-DD")
        if end is None:
            errors.append(f"{label}.end must be an ISO date YYYY-MM-DD")
        if start is not None and end is not None and start > end:
            errors.append(f"{label}.start must be <= end")
        if "reserved_days" in window and not is_non_negative_int(window.get("reserved_days")):
            errors.append(f"{label}.reserved_days must be a non-negative integer")
    return errors


def cost_errors(value: object) -> list[str]:
    if not isinstance(value, dict) or set(value) != COST_FIELDS:
        return ["bench.cost_per_run"]
    errors: list[str] = []
    amount = value.get("value")
    if not is_finite_number(amount) or amount < 0:
        errors.append("bench.cost_per_run.value must be a non-negative number")
    for field in ("unit", "source"):
        if not has_text(value.get(field)):
            errors.append(f"bench.cost_per_run.{field}")
    return errors


def evidence_errors(value: object) -> list[str]:
    """The bench block's evidence rule: the strict four-field shape, no claim_class.

    The campaign block and the merged artifact accept the optional ``claim_class``
    grade (bench_policy.evidence_errors); the bench block has always been stricter
    and stays that way -- its evidence is plain supplied parameters.
    """
    if not isinstance(value, list) or not value:
        return ["bench.evidence"]
    errors: list[str] = []
    for index, item in enumerate(value):
        label = f"bench.evidence[{index}]"
        if not isinstance(item, dict) or set(item) != EVIDENCE_FIELDS:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in {"OBSERVED", "ASSUMED", "GAP"}:
            errors.append(f"{label}.status")
    return errors


def bench_field_errors(value: object) -> list[str]:
    """The bench block's field rules, WITHOUT its evidence array.

    Split out from :func:`bench_errors` because the built artifact's evidence
    array is the two blocks' evidence merged (bench first), so the artifact
    validator checks the bench fields here and that merged array separately through
    bench_policy.policy_errors.
    """
    if not isinstance(value, dict):
        return ["bench must contain only the bench-registration input fields"]
    errors: list[str] = []
    for field in ("bench_id", "project_reference", "bench_name", "location", "source", "evidence_id"):
        if not has_text(value.get(field)):
            errors.append(f"bench.{field}")
    errors.extend(window_errors(value.get("availability_window")))
    cycle = value.get("cycle_days")
    if not is_finite_number(cycle) or cycle <= 0:
        errors.append("bench.cycle_days must be a positive number")
    errors.extend(cost_errors(value.get("cost_per_run")))
    if value.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("bench.evidence_scope must be SYNTHETIC or PHYSICAL")
    return errors


def bench_errors(value: object) -> list[str]:
    """The bench block's full rules: shape, fields, evidence, GAP."""
    if not isinstance(value, dict) or set(value) != INPUT_FIELDS:
        derived = ""
        if isinstance(value, dict) and "available_bench_slots" in value:
            derived = "; available_bench_slots is derived by bench_policy and must not be supplied"
        elif isinstance(value, dict):
            extra = sorted(set(value) - ALLOWED_FIELDS)
            missing = sorted(INPUT_FIELDS - set(value))
            derived = f"; unexpected={extra or 'none'} missing={missing or 'none'}"
        return [f"bench must contain only the bench-registration input fields{derived}"]
    errors = bench_field_errors(value)
    errors.extend(evidence_errors(value.get("evidence")))
    if not errors and has_gap(value):
        errors.append("bench.evidence contains GAP; current input is insufficient")
    return errors


def campaign_request_errors(record: object) -> list[str]:
    """The campaign block's shape, optional fields, reserved marker, then the shared ledger rules."""
    if not isinstance(record, dict):
        return ["campaign must be a JSON object"]
    extra = sorted(set(record) - CAMPAIGN_REQUEST_FIELDS)
    missing = sorted(REQUIRED_CAMPAIGN_REQUEST_FIELDS - set(record))
    if extra or missing:
        return [
            "campaign must contain the campaign-registration request fields"
            f" ({sorted(REQUIRED_CAMPAIGN_REQUEST_FIELDS)} plus optional max_iterations and project_reference)"
            f"; unexpected={extra or 'none'} missing={missing or 'none'}"
        ]
    cap, _, cap_errors = resolve_cap(record)
    errors: list[str] = list(cap_errors)
    if "project_reference" in record and not has_text(record.get("project_reference")):
        errors.append("campaign.project_reference must be a non-empty string when supplied")
    for field in ("source", "evidence_id"):
        if not has_text(record.get(field)):
            errors.append(f"campaign.{field}")
    errors.extend(record_errors(record, cap=cap, forbid_provenance_item=True))
    return errors


def cross_block_errors(bench: object, campaign: object) -> list[str]:
    """The two rules the merged record's halves must agree on.

    (1) project: the campaign block may omit ``project_reference`` (the merged
    record has exactly one project source, ``bench.project_reference``); when
    supplied it must be the same value -- a second, divergent project id inside one
    record is a provenance hole, not a second opinion.
    (2) evidence_scope: the artifact carries ONE scope, taken from the bench block,
    so a campaign block declaring the other scope must be refused rather than
    silently overwritten.
    """
    if not isinstance(bench, dict) or not isinstance(campaign, dict):
        return []  # the block-level checks already refuse malformed halves
    errors: list[str] = []
    if "project_reference" in campaign and campaign.get("project_reference") != bench.get("project_reference"):
        errors.append(
            f"campaign.project_reference {campaign.get('project_reference')!r} must equal bench.project_reference "
            f"{bench.get('project_reference')!r}: the merged record has one project"
        )
    if campaign.get("evidence_scope") != bench.get("evidence_scope"):
        errors.append(
            f"campaign.evidence_scope {campaign.get('evidence_scope')!r} must equal bench.evidence_scope "
            f"{bench.get('evidence_scope')!r}: the artifact carries one scope"
        )
    return errors


def errors_for(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != INPUT_BLOCKS:
        extra = sorted(set(data) - INPUT_BLOCKS)
        missing = sorted(INPUT_BLOCKS - set(data))
        return [f"input must contain only {sorted(INPUT_BLOCKS)}; unexpected={extra or 'none'} missing={missing or 'none'}"]
    bench, campaign = data.get("bench"), data.get("campaign")
    errors = bench_errors(bench)
    errors.extend(campaign_request_errors(campaign))
    errors.extend(cross_block_errors(bench, campaign))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_bench_registration.py <input.json>")
        return 1
    path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    bench, record = data["bench"], data["campaign"]
    slots = available_bench_slots(bench)
    cap, defaulted, _ = resolve_cap(record)
    # The preflight shares the one decision function with the builder and the
    # validator (bench_policy.expected_decision_fields): the verdict a caller sees
    # here is the exact verdict the built artifact will carry, so the three stages
    # of the pipeline can never disagree about the same input.
    preview = expected_decision_fields(bench, {**record, "max_iterations": cap}, slots, defaulted=defaulted)
    print(f"READY: input can register one bench record and open its round plan at stage {BENCH_STAGE}")
    print(f"DECISION: {preview['decision']} (the builder will record exactly this verdict)")
    print(f"DERIVED: available_bench_slots={slots}")
    if defaulted:
        print(f"NOTE: max_iterations={cap} defaulted from contracts/state-machine.json")
    if isinstance(cap, int) and not isinstance(cap, bool) and cap > slots:
        print(
            f"NOTE: max_iterations={cap} exceeds the {slots} available_bench_slots this registration records; a "
            "registration records only the availability it was given, so this is reported and not rejected"
        )
    iterations = record.get("iterations") if isinstance(record.get("iterations"), list) else []
    print(
        f"NOTE: campaign {record.get('campaign_id')} carries {len(iterations)} recorded round(s), "
        f"standing at round {record.get('current_iteration')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
