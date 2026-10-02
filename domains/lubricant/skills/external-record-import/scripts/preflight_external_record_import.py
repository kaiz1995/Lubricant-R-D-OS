"""Reject incomplete external-record input before an external record is imported.

The usage-rights anchor is fail-closed (plan WP-10 acceptance): an external
test record MUST carry a data_usage_rights_reference — a missing or empty
reference is rejected with the rule named, never defaulted, and no artifact is
generated.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from external_record_policy import (
    EVIDENCE_SCOPES,
    INPUT_FIELDS,
    RECORD_TYPES,
    evidence_errors,
    has_text,
    import_blockers,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "external_record.schema.json")


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def external_record_errors(value: object) -> list[str]:
    if not isinstance(value, dict) or set(value) != INPUT_FIELDS:
        if isinstance(value, dict):
            extra = sorted(set(value) - INPUT_FIELDS)
            missing = sorted(INPUT_FIELDS - set(value))
            return [f"external_record must contain only the external-record-import input fields; unexpected={extra or 'none'} missing={missing or 'none'}"]
        return ["external_record must contain only the external-record-import input fields"]
    errors: list[str] = []
    for field in ("external_id", "project_reference", "provider", "source", "evidence_id"):
        if not has_text(value.get(field)):
            errors.append(f"external_record.{field}")
    if value.get("record_type") not in RECORD_TYPES:
        errors.append("external_record.record_type must be EXTERNAL_TEST, EXTERNAL_SERVICE, or MANUFACTURER_DATASHEET")
    # Fail-closed (plan WP-10): the usage-rights anchor is checked as a plain
    # text field here and its absence is spelled out again by import_blockers.
    if not has_text(value.get("data_usage_rights_reference")):
        errors.append("external_record.data_usage_rights_reference is mandatory for external collaboration data")
    if value.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("external_record.evidence_scope must be SYNTHETIC or PHYSICAL")
    errors.extend(evidence_errors(value.get("evidence")))
    return errors


def errors_for(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != {"external_record"}:
        return ["input must contain only external_record"]
    return external_record_errors(data.get("external_record"))


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_external_record_import.py <input.json>")
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
    blockers = import_blockers(data["external_record"])
    if blockers:
        print(f"HOLD: missing or invalid: {', '.join(blockers)}; no artifact generated")
        return 1
    print("READY: input can form one external collaboration record only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
