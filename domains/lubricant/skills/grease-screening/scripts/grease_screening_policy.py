"""Deterministic grease-screening policy: the aggregate verdict and the bench gate.

Stage 10 (grease-screening) is the first rework point of the inner loop. The bench is the
bottleneck of the whole campaign - about 2 positions per round and roughly 30 days per
round - so cheap, fast physical/chemical tests exist for one purpose only: to stop
obviously-unqualified samples from ever consuming a bench slot. This module is the single
place where that judgement is made, and it is shared by the preflight, the builder and the
validator so the three scripts cannot disagree about the same input.

**The discrimination limit is part of the policy, not a footnote.** Physical/chemical
indices usually have LOW discrimination power between close candidate formulas: most
qualified greases pass all of them. This stage is therefore a GATE, never a SELECTION
criterion. A PASS means only "not obviously unqualified" - never "better", never "best".
Any code path that would let a screened index rank one candidate above another is a defect
against the purpose of this stage.

Four rules, all fail-closed:

1. THE AGGREGATE VERDICT IS DERIVED, NEVER SUPPLIED. ``overall_verdict`` is the worst
   per-test verdict: FAIL if any test failed, INCONCLUSIVE if none failed but at least one
   is undetermined, PASS only if every test passed. It is computed here and supplying it on
   the input is a hard reject, exactly like ``available_bench_slots`` in bench-registration
   and ``tier`` in reference-material. A hand-set aggregate is precisely the edit that would
   let a failed index disappear behind a favourable summary.

2. THE BENCH GATE MIRRORS THE SCHEMA AND IS DERIVED FROM IT.
   ``schemas/screening.schema.json`` carries the if/then rule ``overall_verdict: FAIL ->
   gate_to_bench: BLOCKED``, and the gate is derived from the verdict here rather than
   trusted from the caller, so the schema's rule can never be violated by an artifact this
   skill produces. The gate is the schema's field; the skill's own ``decision`` is stricter
   and is what actually holds a sample back (rule 3).

3. THE RELEASE RULE (放行判据) IS STRICTER THAN THE GATE FIELD, ON PURPOSE. The schema
   fixes what the gate *value* may be; the decision is this policy's. Only an all-PASS
   screen is a clearance: FAIL sends the sample back to Stage 9 (grease-batch) - the inner
   loop's first rework point - and INCONCLUSIVE holds it until the undetermined index is
   resolved, because a screen with an unmeasured index has not cleared anything either. The
   sample does not consume a bench slot in either case.

4. EVERY DECLARED INDEX MUST BE MEASURED, AND NO INDEX IS INVENTED. The screen is frozen per
   campaign, so a measurement that was not determined is recorded as verdict INCONCLUSIVE
   with its reason in the input-only ``note`` field; it is never silently omitted, and an
   omitted required index is a HOLD. An index nobody measured is reported as absent and is
   never filled in with an assumed value.
"""

from __future__ import annotations

import math

# Input: the two upstream artifact paths, the optional sample binding, the screening
# measurements, the optional bench request N14 governs, and the artifact-level evidence.
REQUIRED_INPUT_FIELDS = frozenset(
    {"project_artifact", "batch_artifact", "screening", "evidence_scope", "evidence"}
)
OPTIONAL_INPUT_FIELDS = frozenset({"sample_artifact", "bench_request"})
INPUT_FIELDS = REQUIRED_INPUT_FIELDS | OPTIONAL_INPUT_FIELDS

# The screening record the caller supplies. ``overall_verdict`` and ``gate_to_bench`` are
# NOT here: they are derived by this module and supplying either is a hard reject.
SCREENING_INPUT_FIELDS = {"screening_id", "sample_reference", "tests", "measurement_replicates"}
DERIVED_SCREENING_FIELDS = ("overall_verdict", "gate_to_bench")
# The artifact form, i.e. the input fields plus the two derived fields the contract requires.
SCREENING_ARTIFACT_FIELDS = (
    "screening_id",
    "sample_reference",
    "tests",
    "overall_verdict",
    "measurement_replicates",
    "gate_to_bench",
)
TEST_INPUT_FIELDS = {"test_id", "test_name", "value", "unit", "limit", "verdict", "note"}
TEST_ARTIFACT_FIELDS = ("test_id", "test_name", "value", "unit", "limit", "verdict")
EVIDENCE_FIELDS = {"evidence_id", "statement", "source", "status"}
EVIDENCE_STATUSES = ("OBSERVED", "ASSUMED", "GAP")
EVIDENCE_SCOPES = ("SYNTHETIC", "PHYSICAL")

# The frozen screen of the precision-gear grease campaign, mirrored from
# schemas/screening.schema.json. A test_name outside this list is not a screened index.
SCREEN_TEST_NAMES = (
    "PENETRATION",
    "WORKED_PENETRATION_CHANGE",
    "DROPPING_POINT",
    "OIL_SEPARATION",
    "EVAPORATION_LOSS",
    "SHEAR_STABILITY",
    "APPEARANCE_UNIFORMITY",
)
# The CTQ-relevant pair of the campaign is mandatory; the rest are reported as NOTE lines
# when absent and are never invented to fill the screen out.
REQUIRED_TEST_NAMES = ("PENETRATION", "DROPPING_POINT")
TEST_VERDICTS = ("PASS", "FAIL", "INCONCLUSIVE")
OVERALL_VERDICTS = ("PASS", "FAIL", "INCONCLUSIVE")
GATE_VALUES = ("RELEASED", "BLOCKED")
VERDICT_ORDER = {"PASS": 0, "INCONCLUSIVE": 1, "FAIL": 2}

# The gate's own semantics, quoted in the messages so the citation is traceable to
# schemas/screening.schema.json's if/then rule.
SCHEMA_GATE_CITATION = "schemas/screening.schema.json: overall_verdict FAIL -> gate_to_bench BLOCKED"
LOW_DISCRIMINATION_STATEMENT = (
    "physical/chemical indices usually have LOW discrimination power between close candidate "
    "formulas: this screen is a GATE, never a SELECTION criterion, and PASS means only "
    "'not obviously unqualified', never 'better'"
)


def has_text(value: object) -> bool:
    """True for a non-empty, non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def test_value_present(value: object) -> bool:
    """A measured value is a finite number or a non-empty string."""
    return is_finite_number(value) or has_text(value)


def test_errors(test: object, index: int, require_reason: bool = True) -> list[str]:
    """Shape checks shared by the input gate and the artifact validator.

    ``require_reason`` is True at the gate, where the input-only ``note`` field exists and
    an undetermined index must state why. It is False when judging a stored artifact: the
    frozen screening contract has no slot for ``note`` (``additionalProperties: false``), so
    the reason cannot survive into the artifact and the requirement is unenforceable there.
    The boundary is stated rather than hidden: a stored artifact whose INCONCLUSIVE index
    carries no traceable reason is not detectable by this validator.
    """
    label = f"screening.tests[{index}]"
    if not isinstance(test, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    if not has_text(test.get("test_id")):
        errors.append(f"{label}.test_id")
    if test.get("test_name") not in SCREEN_TEST_NAMES:
        errors.append(f"{label}.test_name is not one of the frozen screen indices")
    verdict = test.get("verdict")
    if verdict not in TEST_VERDICTS:
        errors.append(f"{label}.verdict must be PASS, FAIL, or INCONCLUSIVE")
        return errors
    if verdict == "INCONCLUSIVE":
        # A not-determined index is recorded honestly, with its reason; never omitted.
        if not test_value_present(test.get("value")):
            errors.append(
                f"{label}.value must record what was observed (use an explicit marker such as "
                "'not determined'): a screened index is never silently omitted"
            )
        if not has_text(test.get("unit")):
            errors.append(f"{label}.unit must state the unit or the qualitative scale")
        if require_reason and not has_text(test.get("note")):
            errors.append(f"{label}.note must state why this index is INCONCLUSIVE")
        return errors
    if not test_value_present(test.get("value")):
        errors.append(f"{label}.value must be a number or a non-empty string")
    if not has_text(test.get("unit")):
        errors.append(f"{label}.unit")
    limit = test.get("limit")
    if limit is not None and not test_value_present(limit):
        errors.append(f"{label}.limit must be a number, a non-empty string, or null")
    return errors


def tests_errors(tests: object, require_reason: bool = True) -> list[str]:
    if not isinstance(tests, list) or not tests:
        return ["screening.tests must be a non-empty array of screened indices"]
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for index, test in enumerate(tests):
        errors.extend(test_errors(test, index, require_reason))
        if not isinstance(test, dict):
            continue
        test_id = test.get("test_id")
        if has_text(test_id):
            if test_id in seen_ids:
                errors.append(f"screening.tests[{index}].test_id {test_id} is duplicated")
            seen_ids.add(test_id)
        test_name = test.get("test_name")
        if test_name in SCREEN_TEST_NAMES:
            if test_name in seen_names:
                errors.append(
                    f"screening.tests[{index}].test_name {test_name} is measured twice in one screen; "
                    "one entry per screened index"
                )
            seen_names.add(test_name)
    for required in REQUIRED_TEST_NAMES:
        if required not in seen_names:
            errors.append(
                f"screening.tests must contain the {required} index: the frozen screen of this campaign "
                "is not complete without it"
            )
    return errors


def derived_overall_verdict(tests: object) -> str | None:
    """The verdict the recorded tests support: the worst per-test verdict.

    None when the tests are not judgeable at all (missing, empty, or malformed verdicts),
    so the caller can distinguish "no tests to judge" from a judged verdict.
    """
    if not isinstance(tests, list) or not tests:
        return None
    verdicts = [test.get("verdict") for test in tests if isinstance(test, dict)]
    if len(verdicts) != len(tests) or any(verdict not in TEST_VERDICTS for verdict in verdicts):
        return None
    return max(verdicts, key=lambda verdict: VERDICT_ORDER[verdict])


def derived_gate(overall_verdict: object) -> str:
    """The bench gate the aggregate verdict implies.

    This mirrors ``schemas/screening.schema.json`` exactly and does not tighten it: the
    schema states that RELEASED is only legal when ``overall_verdict`` is not FAIL. An
    INCONCLUSIVE screen therefore leaves the gate RELEASED, and the honest "this screen is
    not resolved" state is carried by this skill's own ``decision`` field (rule 3), which
    holds the sample until every screened index has passed. Tightening the gate here would
    make the validator reject artifacts the frozen schema declares legal, which this skill
    must not do.
    """
    return "BLOCKED" if overall_verdict == "FAIL" else "RELEASED"


def derived_screening(tests: object) -> dict[str, str | None]:
    """The two derived screening fields, computed together so builder and validator agree."""
    verdict = derived_overall_verdict(tests)
    return {"overall_verdict": verdict, "gate_to_bench": derived_gate(verdict) if verdict else None}


def derived_field_errors(screening: object) -> list[str]:
    """``overall_verdict`` and ``gate_to_bench`` are derived and must not be supplied."""
    if not isinstance(screening, dict):
        return []
    supplied = [field for field in DERIVED_SCREENING_FIELDS if field in screening]
    if not supplied:
        return []
    return [
        "screening."
        + " and screening.".join(supplied)
        + " are derived by grease_screening_policy and must not be supplied; "
        "the aggregate verdict is the worst per-test verdict and the bench gate follows it "
        f"({SCHEMA_GATE_CITATION})"
    ]


def verdict_errors(overall_verdict: object, tests: object) -> list[str]:
    """A stored verdict must equal the worst per-test verdict, exactly."""
    derived = derived_overall_verdict(tests)
    if overall_verdict not in OVERALL_VERDICTS:
        return ["screening.overall_verdict must be PASS, FAIL, or INCONCLUSIVE"]
    if derived is None:
        return []
    if overall_verdict != derived:
        return [
            f"screening.overall_verdict {overall_verdict} does not equal the worst per-test verdict "
            f"{derived}: the aggregate verdict is computed from the recorded tests, never declared over them"
        ]
    return []


def gate_errors(gate_to_bench: object, overall_verdict: object) -> list[str]:
    """The bench gate must equal the gate the aggregate verdict implies."""
    if gate_to_bench not in GATE_VALUES:
        return ["screening.gate_to_bench must be RELEASED or BLOCKED"]
    if overall_verdict == "FAIL" and gate_to_bench == "RELEASED":
        return [
            "screening.gate_to_bench RELEASED is illegal over overall_verdict FAIL: a failed screen must "
            f"never reach the bench ({SCHEMA_GATE_CITATION})"
        ]
    expected = derived_gate(overall_verdict)
    if gate_to_bench != expected:
        return [
            f"screening.gate_to_bench must be {expected} for overall_verdict {overall_verdict}: the gate is "
            "derived from the aggregate verdict, not declared over it"
        ]
    return []


def screening_errors(screening: object) -> list[str]:
    """Structural checks on the screening INPUT record (derived fields must be absent)."""
    if not isinstance(screening, dict):
        return ["screening must be an object"]
    unknown = sorted(set(screening) - SCREENING_INPUT_FIELDS - set(DERIVED_SCREENING_FIELDS))
    missing = sorted(SCREENING_INPUT_FIELDS - set(screening))
    if unknown or missing:
        return [
            "screening must contain only the screening-measurement input fields; "
            f"unexpected={unknown or 'none'} missing={missing or 'none'}"
        ]
    errors = derived_field_errors(screening)
    if not has_text(screening.get("screening_id")):
        errors.append("screening.screening_id")
    if not has_text(screening.get("sample_reference")):
        errors.append("screening.sample_reference")
    errors.extend(tests_errors(screening.get("tests"), require_reason=True))
    replicates = screening.get("measurement_replicates")
    if not isinstance(replicates, int) or isinstance(replicates, bool) or replicates < 1:
        errors.append("screening.measurement_replicates must be a strictly positive integer")
    return errors


def artifact_screening_errors(screening: object) -> list[str]:
    """Structural checks on a STORED screening artifact, including its derived fields."""
    if not isinstance(screening, dict):
        return ["screening must be an object"]
    unknown = sorted(set(screening) - set(SCREENING_ARTIFACT_FIELDS))
    missing = sorted(set(SCREENING_ARTIFACT_FIELDS) - set(screening))
    if unknown or missing:
        return [
            "the stored screening record must contain exactly the screening contract fields; "
            f"unexpected={unknown or 'none'} missing={missing or 'none'}"
        ]
    errors: list[str] = []
    if not has_text(screening.get("screening_id")):
        errors.append("screening.screening_id")
    if not has_text(screening.get("sample_reference")):
        errors.append("screening.sample_reference")
    # require_reason is False: the frozen screening contract carries no ``note`` slot, so
    # the reason an index is undetermined cannot survive into a stored artifact.
    errors.extend(tests_errors(screening.get("tests"), require_reason=False))
    replicates = screening.get("measurement_replicates")
    if not isinstance(replicates, int) or isinstance(replicates, bool) or replicates < 1:
        errors.append("screening.measurement_replicates must be a strictly positive integer")
    errors.extend(verdict_errors(screening.get("overall_verdict"), screening.get("tests")))
    errors.extend(gate_errors(screening.get("gate_to_bench"), screening.get("overall_verdict")))
    return errors


def recorded_screening(screening: object) -> dict:
    """Project a STORED screening artifact back to the fields the policy judges."""
    if not isinstance(screening, dict):
        return {}
    return {field: screening.get(field) for field in SCREENING_ARTIFACT_FIELDS}


def screen_coverage_notes(screening: object) -> list[str]:
    """Audible NOTE lines for frozen indices the screen does not measure.

    An unmeasured index stays unmeasured: this never invents a test to fill the screen out.
    """
    if not isinstance(screening, dict):
        return []
    tests = screening.get("tests")
    if not isinstance(tests, list):
        return []
    measured = {test.get("test_name") for test in tests if isinstance(test, dict)}
    absent = [name for name in SCREEN_TEST_NAMES if name not in measured]
    if not absent:
        return []
    return [
        "NOTE: screen does not measure "
        + ", ".join(absent)
        + "; an unmeasured index is reported as absent, never invented"
    ]


def test_notes(screening: object) -> list[str]:
    """One line per screened index so the run is never silent about what was judged."""
    if not isinstance(screening, dict):
        return []
    tests = screening.get("tests")
    if not isinstance(tests, list):
        return []
    notes: list[str] = []
    for index, test in enumerate(tests):
        if not isinstance(test, dict):
            continue
        note = (
            f"NOTE: tests[{index}] {test.get('test_name')} value={test.get('value')} {test.get('unit')} "
            f"limit={test.get('limit')} verdict={test.get('verdict')}"
        )
        if has_text(test.get("note")):
            note = f"{note} reason={test.get('note')}"
        notes.append(note)
    return notes


def test_names_with_verdict(screening: object, verdict: str) -> list[str]:
    if not isinstance(screening, dict):
        return []
    tests = screening.get("tests")
    if not isinstance(tests, list):
        return []
    return [
        str(test.get("test_name"))
        for test in tests
        if isinstance(test, dict) and test.get("verdict") == verdict
    ]


def gate_blockers(screening: object) -> list[str]:
    """The skill's release rule: only an all-PASS screen is a clearance for the bench.

    Stricter than the schema's gate field on purpose, and the difference is deliberate: the
    schema fixes what the gate value may be, while this decides the record's ``decision``.
    FAIL goes back to Stage 9 (the inner loop's first rework point); INCONCLUSIVE holds the
    sample until the undetermined index is resolved.
    """
    if not isinstance(screening, dict):
        return ["screening must be an object"]
    verdict = screening.get("overall_verdict")
    if verdict == "FAIL":
        failed = test_names_with_verdict(screening, "FAIL")
        return [
            "the screen FAILED ("
            + (", ".join(failed) if failed else "a recorded index failed")
            + "): the sample does not go to the bench, it goes back to Stage 9 (grease-batch)"
        ]
    if verdict == "INCONCLUSIVE":
        undetermined = test_names_with_verdict(screening, "INCONCLUSIVE")
        return [
            "the screen is INCONCLUSIVE ("
            + (", ".join(undetermined) if undetermined else "a recorded index is undetermined")
            + "): the sample is not obviously unqualified but is not cleared either, so it does not "
            "consume a bench slot until that index is resolved"
        ]
    if verdict not in OVERALL_VERDICTS:
        return ["overall_verdict is not a recorded verdict"]
    return []


def scope_prefix(evidence_scope: object) -> str:
    return (
        "Synthetic test fixture / NOT_FOR_PHYSICAL_EXECUTION: this record cannot authorize stage advancement. "
        if evidence_scope == "SYNTHETIC"
        else ""
    )


def expected_decision_fields(screening: object, evidence_scope: object) -> dict[str, str]:
    """The canonical screening decision block, recomputed identically by builder and validator.

    A pure function of the artifact's own fields, so the validator needs nothing else.
    """
    if not isinstance(screening, dict):
        screening = {}
    verdict = screening.get("overall_verdict")
    gate = screening.get("gate_to_bench")
    screening_id = screening.get("screening_id")
    sample_reference = screening.get("sample_reference")
    failed = test_names_with_verdict(screening, "FAIL")
    inconclusive = test_names_with_verdict(screening, "INCONCLUSIVE")
    passed = test_names_with_verdict(screening, "PASS")
    blockers = gate_blockers(screening)
    decision = "GO" if not blockers else "HOLD"
    if verdict == "FAIL":
        next_action = (
            f"Stay at Stage 9: screen {screening_id} failed, so sample {sample_reference} does not consume a "
            "bench slot. Remake the batch and screen the new sample."
        )
    elif verdict == "INCONCLUSIVE":
        next_action = (
            f"Resolve the undetermined index of screen {screening_id} before sample {sample_reference} is "
            "counted as screened; the sample is not obviously unqualified but is not cleared either."
        )
    elif verdict == "PASS":
        next_action = (
            f"Queue sample {sample_reference} for the next bench round: screen {screening_id} found nothing "
            "obviously unqualified, so the bench slot may be spent on it."
        )
    else:
        next_action = f"Stay at Stage 9: screen {screening_id} carries no legal overall_verdict."
    return {
        "decision_question": (
            f"Does sample {sample_reference} clear the cheap physical/chemical screen before it may occupy a "
            "bench slot?"
        ),
        "hypothesis": (
            "No screened index is out of limit, so the sample is not obviously unqualified for the bench; "
            "the screen is a gate and not a claim that this candidate is better than another."
        ),
        "uncertainty": (
            f"{scope_prefix(evidence_scope)}{LOW_DISCRIMINATION_STATEMENT}. The recorded values are supplied "
            "screen results, not independently verified, and a PASS does not establish bench or product "
            f"performance. overall_verdict={verdict}."
        ),
        "decision_rule": (
            "Release the sample to the bench only when no screened index fails: overall_verdict FAIL forces "
            f"gate_to_bench BLOCKED ({SCHEMA_GATE_CITATION}), because the bench is the scarcest resource of "
            "the inner loop and a failed screen must go back to Stage 9 instead."
        ),
        "result": (
            f"screen {screening_id}: {len(passed)} PASS, {len(failed)} FAIL"
            + (f" ({', '.join(failed)})" if failed else "")
            + f", {len(inconclusive)} INCONCLUSIVE"
            + (f" ({', '.join(inconclusive)})" if inconclusive else "")
            + f"; overall_verdict={verdict}; gate_to_bench={gate}."
        ),
        "decision": decision,
        "next_action": next_action,
    }


def low_discrimination_notes() -> list[str]:
    """The standing limitation, printed on every run so it cannot be forgotten."""
    return [f"NOTE: {LOW_DISCRIMINATION_STATEMENT}"]
