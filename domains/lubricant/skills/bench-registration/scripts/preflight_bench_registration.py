"""Reject incomplete bench-registration input before a bench artifact is built.

A bench is shared test-stand capacity. Registration is fail-closed: availability
windows, a strictly positive cycle time, per-run cost with a source, provenance,
and evidence without GAP are all required, and the usable slot count is DERIVED
(never hand-supplied) by bench_policy.available_bench_slots.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bench_policy import (
    ALLOWED_FIELDS,
    EVIDENCE_SCOPES,
    INPUT_FIELDS,
    WINDOW_FIELDS,
    available_bench_slots,
    has_gap,
    has_text,
    is_finite_number,
    is_non_negative_int,
    parse_iso_date,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "bench.schema.json")
EVIDENCE_FIELDS = {"evidence_id", "statement", "source", "status"}
COST_FIELDS = {"value", "unit", "source"}


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


def bench_errors(value: object) -> list[str]:
    if not isinstance(value, dict) or set(value) != INPUT_FIELDS:
        derived = ""
        if isinstance(value, dict) and "available_bench_slots" in value:
            derived = "; available_bench_slots is derived by bench_policy and must not be supplied"
        elif isinstance(value, dict):
            extra = sorted(set(value) - ALLOWED_FIELDS)
            missing = sorted(INPUT_FIELDS - set(value))
            derived = f"; unexpected={extra or 'none'} missing={missing or 'none'}"
        return [f"bench must contain only the bench-registration input fields{derived}"]
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
    errors.extend(evidence_errors(value.get("evidence")))
    if not errors and has_gap(value):
        errors.append("bench.evidence contains GAP; current input is insufficient")
    return errors


def errors_for(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != {"bench"}:
        return ["input must contain only bench"]
    return bench_errors(data.get("bench"))


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
    slots = available_bench_slots(data["bench"])
    print("READY: input can register one bench record only")
    print(f"DERIVED: available_bench_slots={slots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
