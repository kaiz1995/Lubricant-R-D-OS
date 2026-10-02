"""Reject incomplete interface-definition input before an interface artifact is built.

The compatibility verdict is fail-closed: a PASS is only admissible with
non-empty, all-OBSERVED, all-PASS compatibility evidence and no GAP evidence;
an empty compatibility_evidence list forces verdict GAP. The external blocker
(DLC coating parameters / supplier batches have no owner yet) is handled by
declaration, not guessing: the optional coating object is either fully present
with provenance or omitted entirely, and unsupported verdicts stay
FAIL / INCONCLUSIVE / GAP — a fabricated PASS is the one thing this skill must
never produce.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from interface_policy import (
    EVIDENCE_SCOPES,
    INPUT_FIELDS,
    INTERFACE_TYPES,
    VERDICTS,
    coating_errors,
    compatibility_errors,
    counterpart_errors,
    has_text,
    pass_blockers,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "interface.schema.json")
EVIDENCE_FIELDS = {"evidence_id", "statement", "source", "status"}


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def evidence_errors(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["interface.evidence"]
    errors: list[str] = []
    for index, item in enumerate(value):
        label = f"interface.evidence[{index}]"
        if not isinstance(item, dict) or set(item) != EVIDENCE_FIELDS:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in {"OBSERVED", "ASSUMED", "GAP"}:
            errors.append(f"{label}.status")
    return errors


def interface_errors(value: object) -> list[str]:
    if not isinstance(value, dict) or set(value) != INPUT_FIELDS:
        if isinstance(value, dict):
            extra = sorted(set(value) - INPUT_FIELDS)
            missing = sorted(INPUT_FIELDS - set(value))
            return [f"interface must contain only the interface-definition input fields; unexpected={extra or 'none'} missing={missing or 'none'}"]
        return ["interface must contain only the interface-definition input fields"]
    errors: list[str] = []
    for field in ("interface_id", "project_reference", "source", "evidence_id"):
        if not has_text(value.get(field)):
            errors.append(f"interface.{field}")
    if value.get("interface_type") not in INTERFACE_TYPES:
        errors.append("interface.interface_type must be COATING_SUBSTRATE, LUBRICANT_SURFACE, or MATERIAL_PAIR")
    errors.extend(counterpart_errors(value.get("counterpart_a"), "interface.counterpart_a"))
    errors.extend(counterpart_errors(value.get("counterpart_b"), "interface.counterpart_b"))
    errors.extend(coating_errors(value.get("coating")))
    errors.extend(compatibility_errors(value.get("compatibility_evidence")))
    verdict = value.get("verdict")
    if verdict not in VERDICTS:
        errors.append("interface.verdict must be PASS, FAIL, INCONCLUSIVE, or GAP")
    compat = value.get("compatibility_evidence")
    if isinstance(compat, list) and not compat and verdict != "GAP":
        errors.append("interface.verdict must be GAP when compatibility_evidence is empty")
    if verdict == "PASS":
        # pass_blockers already covers GAP evidence, empty evidence, and non-PASS/non-OBSERVED items.
        errors.extend(pass_blockers(value))
    if value.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("interface.evidence_scope must be SYNTHETIC or PHYSICAL")
    errors.extend(evidence_errors(value.get("evidence")))
    return errors


def errors_for(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != {"interface"}:
        return ["input must contain only interface"]
    return interface_errors(data.get("interface"))


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_interface_definition.py <input.json>")
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
    print("READY: input can form one interface record only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
