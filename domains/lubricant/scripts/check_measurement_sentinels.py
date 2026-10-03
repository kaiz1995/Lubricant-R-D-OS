"""Detect sentinel markers and contradictory measurements (report-only).

Contract fix background: common.schema.json#/$defs/measurement now allows
value=null + status="DEFERRED"/"PENDING_CLIENT" to express "not set". JSON
Schema cannot inspect string content, so this script reports marker-based
sentinels that bypass the schema's null channel.

Rules (one violation per measurement-shaped object):
  R1: status in {"DEFERRED", "PENDING_CLIENT"} and value is a number
      -> contradiction: a value is given while claiming not set.
  R2: "SENTINEL" or "UNSET" appears in unit or source (case-insensitive)
      -> sentinel marker detected, regardless of value or status.
  Numeric value with NO status is OK (backward compatible, same as schema).

Legacy artifacts like value=-1 with a plain unit are NOT flagged: bare
numbers cannot be distinguished from legitimate physical quantities
(0 as a lower bound, -1 as a temperature) — no hardcoded numeric list.

A measurement-shaped object is any JSON object containing all six keys:
value, unit, source, method_version, material_batch, formula_version.
Note: value=null without status is rejected by the schema itself (allOf
if/then), so it is not this script's job to flag it.

The script only reports; it never rewrites artifacts.

Exit codes: 0 = PASS, 1 = HOLD (violations found or unreadable JSON present).
Usage: python check_measurement_sentinels.py <workspace-dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MEASUREMENT_KEYS = (
    "value",
    "unit",
    "source",
    "method_version",
    "material_batch",
    "formula_version",
)

SENTINEL_MARKERS = ("SENTINEL", "UNSET")
CONTRADICTORY_STATUSES = ("DEFERRED", "PENDING_CLIENT")


def find_measurements(node, path, found):
    """Recursively collect (json_path, obj) for every measurement-shaped object."""
    if isinstance(node, dict):
        if all(key in node for key in MEASUREMENT_KEYS):
            found.append((path, node))
        for key, child in node.items():
            find_measurements(child, f"{path}.{key}" if path else str(key), found)
    elif isinstance(node, list):
        for index, child in enumerate(node):
            find_measurements(child, f"{path}[{index}]", found)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_object(obj):
    """Return a violation reason string, or None if the object is acceptable."""
    unit = obj["unit"]
    source = obj["source"]
    value = obj["value"]
    status = obj.get("status")

    # R2: sentinel marker in unit/source is the strongest signal.
    hit_fields = [
        field
        for field, text in (("unit", unit), ("source", source))
        for marker in SENTINEL_MARKERS
        if marker in text.upper()
    ]
    if hit_fields:
        marker_text = unit if "unit" in hit_fields else source
        markers = [m for m in SENTINEL_MARKERS if m in marker_text.upper()]
        return (
            f"sentinel marker {sorted(set(hit_fields))} ({'+'.join(markers)}) "
            f"in {sorted(set(hit_fields))}: {marker_text[:80]!r}"
        )

    # R1: a value is given while status explicitly claims not set.
    if status in CONTRADICTORY_STATUSES and is_number(value):
        return f"value={value} is numeric but status={status!r}"

    # Otherwise OK: numeric + no status is backward compatible; null is the
    # legal not-set form (or a schema violation caught by allOf if/then).
    return None


def scan_workspace(workspace: Path):
    """Yield report lines for one workspace scan. Last line starts PASS:/HOLD:."""
    lines = []
    violations = 0
    unreadable = 0
    json_files = sorted(workspace.rglob("*.json"))

    for path in json_files:
        rel = path.relative_to(workspace).as_posix()
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            unreadable += 1
            lines.append(f"WARN: {rel}: unreadable JSON ({exc})")
            continue

        found = []
        find_measurements(data, "", found)
        for json_path, obj in found:
            location = f"{rel}#{json_path}" if json_path else rel
            reason = check_object(obj)
            if reason:
                violations += 1
                lines.append(f"VIOLATION: {location}: {reason}")
            else:
                lines.append(f"OK: {location}: value={obj['value']!r}, status={obj.get('status', 'absent')!r}")

    summary = (
        f"{violations} violation(s) in {len(json_files)} JSON file(s)"
        + (f", {unreadable} unreadable" if unreadable else "")
    )
    if violations or unreadable:
        lines.append(f"HOLD: {summary}")
    else:
        lines.append(f"PASS: {summary}")
    return lines


def main(argv):
    if len(argv) != 2:
        print("usage: check_measurement_sentinels.py <workspace-dir>", file=sys.stderr)
        return 2
    workspace = Path(argv[1])
    if not workspace.is_dir():
        print(f"error: not a directory: {workspace}", file=sys.stderr)
        return 2
    lines = scan_workspace(workspace)
    for line in lines:
        print(line)
    return 1 if lines and lines[-1].startswith("HOLD:") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
