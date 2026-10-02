"""Deterministic application-validation policy: the APPLIED entry gate.

WP-06 Stage 13 (`APPLIED`): this policy decides whether one verified project
may enter the application-and-machine-validation stage. The headline rule is
fail-closed and asymmetric:

    **INCONCLUSIVE 不得进入 APPLIED** — an undetermined verdict is not a
    validation pass, so it can never gate entry into `APPLIED`. Only a
    `PASS` application record may, and a `PASS` is only admissible under the
    exact fail-closed conditions of the producing skill
    (`application_policy.pass_blockers`): every acceptance criterion
    OBSERVED with a determined threshold, a non-empty OBSERVED
    life-claim boundary, no counterexamples, and no GAP evidence.

The PASS semantics are NOT re-implemented here: this module imports the single
source of truth (`skills/application-definition/scripts/application_policy.py`,
deployed beside this skill's scripts by the pack installer) so the two skills
cannot drift apart. This module only adds the stage-entry rules on top.

Missing criteria are rejected the same way: an application record with an
empty criteria list can only carry `result = GAP`, and a GAP record never
enters `APPLIED`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Single source of truth for the PASS rule: the producing skill's policy.
# In the pack tree it lives in the sibling skill; in a deployed bundle the
# pack installer copies it beside this skill's scripts.
_HERE = Path(__file__).resolve().parent
for _candidate in (
    _HERE,
    _HERE.parent / "application-definition" / "scripts",
    _HERE.parents[1] / "application-definition" / "scripts",
):
    if (_candidate / "application_policy.py").is_file() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))
from application_policy import pass_blockers  # noqa: E402

RECORD_FIELDS = {"project_reference", "current_stage", "application"}
STAGES_ALLOWED_BEFORE_APPLIED = {"VERIFIED"}
RESULTS = ("PASS", "FAIL", "INCONCLUSIVE", "GAP")


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def applied_entry_blockers(record: dict) -> list[str]:
    """Every reason the record cannot gate entry into APPLIED. Empty = allowed."""
    reasons: list[str] = []
    stage = record.get("current_stage")
    if stage not in STAGES_ALLOWED_BEFORE_APPLIED:
        reasons.append(
            "current_stage must be VERIFIED to enter APPLIED "
            f"(got {stage!r}); only a verified project can be applied"
        )
    application = record.get("application")
    if not isinstance(application, dict):
        return reasons + ["application must be the built application artifact object"]
    if application.get("project_reference") != record.get("project_reference"):
        reasons.append(
            "application.project_reference must match the gated project_reference "
            f"(record {record.get('project_reference')!r} vs application {application.get('project_reference')!r})"
        )
    result = application.get("result")
    if result not in RESULTS:
        reasons.append("application.result must be PASS, FAIL, INCONCLUSIVE, or GAP")
    elif result == "INCONCLUSIVE":
        # The headline fail-closed rule: an undetermined verdict never advances.
        reasons.append(
            "INCONCLUSIVE cannot enter APPLIED: the application verdict is "
            "undetermined; resolve the criteria or record GAP instead"
        )
    elif result != "PASS":
        reasons.append(
            f"application result must be PASS to enter APPLIED (got {result}); "
            "a FAIL or GAP verdict blocks the stage"
        )
    else:
        reasons.extend(f"application.{blocker}" for blocker in pass_blockers(application))
    benches = application.get("bench_references")
    if not isinstance(benches, list) or not benches or not all(has_text(item) for item in benches):
        reasons.append("application.bench_references must list at least one registered bench")
    return reasons


def expected_decision_fields(record: dict, blockers: list[str]) -> dict[str, str]:
    application = record.get("application") if isinstance(record, dict) else None
    application_id = application.get("application_id", "") if isinstance(application, dict) else ""
    allowed = not blockers
    return {
        "decision_question": f"May application {application_id} gate project entry into APPLIED?",
        "hypothesis": f"{application_id} records a PASS application verdict with determined criteria, a non-empty life-claim boundary, and bench linkage.",
        "uncertainty": "This gate records the supplied application verdict only; it does not create new experiment, model, or release evidence and does not by itself freeze the design.",
        "decision_rule": "Enter APPLIED only when the record is at stage VERIFIED, the application verdict is PASS (INCONCLUSIVE, FAIL, and GAP are all blocked), the PASS is fail-closed admissible, and at least one registered bench is cited.",
        "result": "The supplied application record satisfies the APPLIED entry gate." if allowed else f"The supplied application record is blocked from APPLIED: {'; '.join(blockers)}.",
        "decision": "GO" if allowed else "HOLD",
        "next_action": "Advance to APPLIED under a state-machine GO with this record as evidence." if allowed else "Retain the project at VERIFIED and resolve the recorded blockers; never fabricate a PASS.",
    }
