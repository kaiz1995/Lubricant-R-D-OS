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

This stage produces no artifact and no decision block: the gate only answers
"READY / HOLD" for the `VERIFIED -> APPLIED` transition. A decision-block builder
(deleted 2026-10-14, batch H / M4) had no caller anywhere in the pack and was removed
rather than wired up -- the `application.json` decision block is produced by the
producing skill (`application-definition/scripts/application_policy.py`). If a gate
summary is ever needed here, emit a NOTE line, never a decision block.
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
from application_policy import boundary_is_empty, pass_blockers  # noqa: E402

RECORD_FIELDS = {"project_reference", "current_stage", "application"}
STAGES_ALLOWED_BEFORE_APPLIED = {"VERIFIED"}
RESULTS = ("PASS", "FAIL", "INCONCLUSIVE", "GAP")
EVIDENCE_SCOPES = ("SYNTHETIC", "PHYSICAL")

# --- Precision-grease route: acceptance criteria must reach the whole machine --------
# ADDITIVE (step 16b, plan section 4.4.3 item 3-6). On the oil routes the application
# record is unchanged; on PRECISION_GREASE_DEV the criteria chain must land on the four
# whole-machine indicators the redesign names (start-up torque / backlash / temperature
# rise / life), because a bench criterion that never reaches the machine is not an
# application verdict. The requirement is gated on the route, so no oil record changes.
GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"
MACHINE_INDICATORS = ("START_UP_TORQUE", "BACKLASH", "TEMPERATURE_RISE", "LIFE")
MACHINE_INDICATOR_ENTRY_FIELDS = {"indicator", "criterion_reference"}
# M6 (2026-10-14): the grease record also names the BUILT application artifact it
# gates. The inline `application` object is kept (the field-level semantics in
# `applied_entry_blockers` depend on it), but it alone let a record gate over a
# copy edited after the fact: the path is what the preflight reads back and
# compares field by field, so the two cannot drift apart silently.
APPLICATION_REFERENCE_FIELD = "application_artifact"
GREASE_RECORD_FIELDS = {"project_type", "campaign_artifact", "bench_test_artifact", "machine_indicators", APPLICATION_REFERENCE_FIELD}


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def grease_route(record: dict) -> bool:
    """True when the record declares the precision-grease route."""
    return isinstance(record, dict) and record.get("project_type") == GREASE_PROJECT_TYPE


def machine_indicator_blockers(record: dict, application: dict) -> list[str]:
    """Every reason the whole-machine criteria chain is not complete. Empty = complete.

    Each of the four machine indicators must be declared once and must resolve to an
    acceptance criterion that is OBSERVED with a determined numeric threshold when the
    verdict is PASS. A cited criterion that does not exist is a broken chain, not a gap:
    the record claims a machine-level criterion the application record does not carry.
    """
    reasons: list[str] = []
    indicators = record.get("machine_indicators")
    if not isinstance(indicators, list) or not indicators:
        return [
            "machine_indicators must declare the whole-machine criteria chain on the "
            f"{GREASE_PROJECT_TYPE} route ({', '.join(MACHINE_INDICATORS)})"
        ]
    declared: dict[str, str] = {}
    for index, entry in enumerate(indicators):
        label = f"machine_indicators[{index}]"
        if not isinstance(entry, dict) or set(entry) != MACHINE_INDICATOR_ENTRY_FIELDS:
            reasons.append(f"{label} must contain exactly indicator and criterion_reference")
            continue
        indicator = entry.get("indicator")
        reference = entry.get("criterion_reference")
        if indicator not in MACHINE_INDICATORS:
            reasons.append(f"{label}.indicator must be one of {', '.join(MACHINE_INDICATORS)}")
            continue
        if not has_text(reference):
            reasons.append(f"{label}.criterion_reference must be a non-empty criterion id")
            continue
        if indicator in declared:
            reasons.append(f"{label}.indicator {indicator} is declared more than once")
            continue
        declared[indicator] = reference
    missing = [indicator for indicator in MACHINE_INDICATORS if indicator not in declared]
    if missing:
        reasons.append(
            "machine_indicators must cover every whole-machine indicator; missing "
            + ", ".join(missing)
            + " (a machine-level criterion the record never names cannot gate APPLIED)"
        )
    criteria = application.get("acceptance_criteria")
    criteria = criteria if isinstance(criteria, list) else []
    by_id = {
        item.get("criterion_id"): item
        for item in criteria
        if isinstance(item, dict) and has_text(item.get("criterion_id"))
    }
    for indicator in MACHINE_INDICATORS:
        reference = declared.get(indicator)
        if reference is None:
            continue
        criterion = by_id.get(reference)
        if criterion is None:
            reasons.append(
                f"machine_indicators.{indicator} cites criterion {reference!r}, which is not present in "
                "application.acceptance_criteria"
            )
            continue
        if application.get("result") == "PASS":
            if criterion.get("status") != "OBSERVED":
                reasons.append(
                    f"machine_indicators.{indicator} cites criterion {reference} with status "
                    f"{criterion.get('status')!r}: a PASS requires every whole-machine criterion to be OBSERVED"
                )
            if not is_number(criterion.get("threshold")):
                reasons.append(
                    f"machine_indicators.{indicator} cites criterion {reference} without a determined numeric "
                    "threshold: a PASS requires a numeric threshold per whole-machine indicator"
                )
    if "LIFE" in declared and boundary_is_empty(application.get("life_claim_boundary")):
        reasons.append(
            "machine_indicators.LIFE requires a non-empty OBSERVED life_claim_boundary: "
            "a life indicator with no validated condition cannot gate APPLIED"
        )
    return reasons


def evidence_scope_blockers(record: dict, application: dict) -> list[str]:
    """Refuse a SYNTHETIC application record on the precision-grease route.

    The pack has one rule for synthetic evidence: it validates the workflow, it
    never authorizes a state transition. The router enforces it on every
    advancement, the gate review refuses anything but HOLD, and knowledge-archive
    caps a synthetic project at DRAFT_KNOWLEDGE. This gate used to be the one
    admission that let a SYNTHETIC application record through to APPLIED, so the
    same chain could be refused at step 17 and admitted at step 18.

    Gated on the grease route deliberately: the oil records carry no
    ``project_type`` and are validated exactly as before (pure-increment rule).
    """
    if not grease_route(record):
        return []
    scope = application.get("evidence_scope")
    if scope not in EVIDENCE_SCOPES:
        return [
            "application.evidence_scope must be SYNTHETIC or PHYSICAL on the "
            f"{GREASE_PROJECT_TYPE} route"
        ]
    if scope == "SYNTHETIC":
        return [
            "SYNTHETIC application evidence cannot enter APPLIED: synthetic evidence "
            "validates the workflow only and never authorizes a state transition"
        ]
    return []


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
    # ADDITIVE: the whole-machine criteria chain, required only on the grease route.
    if grease_route(record):
        reasons.extend(machine_indicator_blockers(record, application))
        reasons.extend(evidence_scope_blockers(record, application))
    return reasons
