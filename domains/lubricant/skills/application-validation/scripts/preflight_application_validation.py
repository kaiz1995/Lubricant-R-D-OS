"""Reject input that cannot gate entry into the WP-06 APPLIED stage.

Fail-closed and asymmetric: the headline rule is that an INCONCLUSIVE
application verdict can never enter APPLIED (an undetermined verdict is not a
validation pass). A FAIL or GAP verdict is likewise blocked; only a PASS that
is admissible under the producing skill's fail-closed rules (determined
OBSERVED criteria, non-empty OBSERVED life-claim boundary, no counterexamples,
no GAP evidence) and that cites at least one registered bench may advance a
VERIFIED project into APPLIED. Missing criteria are rejected the same way —
an empty criteria list can only carry result GAP, and GAP never advances.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from application_validation_policy import RECORD_FIELDS, applied_entry_blockers, has_text


def errors_for(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != {"application_validation"}:
        return ["input must contain only application_validation"]
    record = data["application_validation"]
    if not isinstance(record, dict) or set(record) != RECORD_FIELDS:
        if isinstance(record, dict):
            extra = sorted(set(record) - RECORD_FIELDS)
            missing = sorted(RECORD_FIELDS - set(record))
            return [f"application_validation must contain exactly {sorted(RECORD_FIELDS)}; unexpected={extra or 'none'} missing={missing or 'none'}"]
        return [f"application_validation must contain exactly {sorted(RECORD_FIELDS)}"]
    errors: list[str] = []
    if not has_text(record.get("project_reference")):
        errors.append("application_validation.project_reference")
    errors.extend(applied_entry_blockers(record))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_application_validation.py <input.json>")
        return 1
    path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no APPLIED entry")
        return 1
    errors = errors_for(data)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no APPLIED entry")
        return 1
    print("READY: the application record gates entry into APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
