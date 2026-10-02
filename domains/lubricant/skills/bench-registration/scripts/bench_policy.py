"""Deterministic bench-registration policy: availability -> usable bench slots.

`available_bench_slots` is the single conversion of a bench's availability into
capacity, and it is the anchor the DOE resource envelope must reconcile against:

    available_bench_slots = sum over availability_window of
        floor(usable_days(window) / cycle_days)

where usable_days(window) = (end - start).days + 1 - reserved_days, clamped at 0.

WP-04b adds `resource_envelope.bench_slots` to the nested DOE input schema
(`domains/lubricant/schemas/doe_input.schema.json`). That value MUST be reconciled
with this function (end-to-end cross-check recorded as a TODO in
`tests/lubricant_e2e/test_application_bench.py`; the two are in separate
worktrees and are joined only after merge).
"""

from __future__ import annotations

import math
from datetime import date

INPUT_FIELDS = {
    "bench_id", "project_reference", "bench_name", "location",
    "availability_window", "cycle_days", "cost_per_run",
    "source", "evidence_id", "evidence_scope", "evidence",
}
ARTIFACT_FIELDS = (
    "bench_id", "project_reference", "bench_name", "location",
    "availability_window", "cycle_days", "cost_per_run",
)
ALLOWED_FIELDS = INPUT_FIELDS | {"available_bench_slots"}
WINDOW_FIELDS = {"window_id", "start", "end", "reserved_days"}
EVIDENCE_SCOPES = {"SYNTHETIC", "PHYSICAL"}
ISO_DATE_LENGTH = 10


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def parse_iso_date(value: object) -> date | None:
    if not has_text(value) or len(value) != ISO_DATE_LENGTH:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


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


def has_gap(bench: dict) -> bool:
    evidence = bench.get("evidence")
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("status") == "GAP" for item in evidence
    )


def expected_decision_fields(bench: dict, slots: int) -> dict[str, str]:
    bench_id = bench.get("bench_id", "")
    ready = not has_gap(bench)
    return {
        "decision_question": f"Is the supplied input sufficient to register bench {bench_id}?",
        "hypothesis": f"{bench_id} records its availability windows, cycle time and per-run cost sufficient for later slot planning.",
        "uncertainty": "Supplied availability, cycle time and cost are not independently verified; recorded ASSUMED evidence remains assumed and this record does not reserve capacity, book a run, or establish a capability conclusion.",
        "decision_rule": "Register the bench only when availability windows, a positive cycle time, per-run cost with source, and evidence without GAP are supplied.",
        "result": f"{bench_id} is {'sufficient' if ready else 'not sufficient'} to register a bench record; available_bench_slots={slots}.",
        "decision": "GO" if ready else "HOLD",
        "next_action": f"Retain {bench_id} as a registered bench with {slots} usable slots." if ready else "Retain the supplied evidence and resolve the recorded GAP before registering the bench.",
    }
