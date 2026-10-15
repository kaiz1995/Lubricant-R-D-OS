"""Reject incomplete variance-assessment input before a VARIANCE_ASSESSED record is built.

Step 12 answers the question that decides whether the inner loop is meaningful: is
the observed difference real, or is it noise? Upstream is the step-11 bench-test
records, and this gate is fail-closed. A missing or schema-invalid bench-test
record, an observation with no upstream run, an upstream censored run presented as
a completed observation, a censored observation carrying an end-point, an
unexplained stop, a relaxed planning constant, or a request that admits an
artifact-level evidence GAP all stop the skill before anything is written.

Two deliberate boundaries, both stated rather than hidden:

* A bench-test record is a RUN record, so its ``decision`` is not required to be GO.
  Requiring GO here would forbid exactly the input this step exists to handle -- a
  round that ended in a censored observation. What is required is the stage
  ``BENCH_TESTED``, schema validity, one consistent ``project_id``, one consistent
  ``evidence_scope``, and agreement between the declared iteration and every run's
  ``campaign_iteration``.
* The preflight does not run the engine. It enforces the three data-quality rules
  and the provenance links itself, so the caller gets a reason without a round trip;
  the builder runs the engine and refuses to write when the engine rejects.

The engine's own contract (its input schema) is validated by the engine when the
builder calls it; this module checks the same structure independently so a defect is
reported before anything is built.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from variance_assessment_policy import (
    INPUT_FIELDS,
    REQUIRED_INPUT_FIELDS,
    EVIDENCE_SCOPES,
    ENGINE_ANALYSES,
    FROZEN_ALPHA,
    FROZEN_K_REQUIRED,
    FROZEN_TARGET_POWER,
    MODE_MEANING,
    engine_input_errors,
    evidence_errors,
    has_gap,
    has_text,
    input_notes,
    is_positive_number,
    mode_errors,
    prediction_interval_errors,
    provenance_errors,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "bench_test.schema.json", "variance.schema.json")
BENCH_TEST_SCHEMA = "bench_test.schema.json"
BENCH_TEST_STAGE = "BENCH_TESTED"
ABSENCE_HINT = "record an explicit absence marker such as MISSING when the upstream record does not exist"


def _ensure_naming_checker_importable() -> bool:
    """Probe the shared naming checker in both layouts (reference-material precedent).

    Repository layout: the module lives in the pack-level ``scripts/`` tree.
    Deployed layout: the installer copies it beside this skill's scripts
    (install_domain_skill.py maps variance-assessment -> check_artifact_naming.py).
    If neither candidate holds the file the preflight still runs; the naming
    contract is then unenforced here, exactly like knowledge_retrieval.
    """
    for candidate in (SKILL_ROOT / "scripts", SKILL_ROOT.parents[1] / "scripts"):
        if (candidate / "check_artifact_naming.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return True
    return False


_NAMING_AVAILABLE = _ensure_naming_checker_importable()

if _NAMING_AVAILABLE:
    import check_artifact_naming  # noqa: E402


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def workspace_naming_errors(input_path: Path) -> list[str]:
    """Enforce the canonical-name contract on the workspace holding the input.

    The request file lives in the workspace root, so ``input_path.parent`` is the
    workspace. A bare staging directory without ``project.json`` is not treated as a
    workspace (keeps ad-hoc preflight invocations working). A mangled artifact name
    is invisible to the stage-gate panel, so every violation here is a HOLD.
    """
    if not _NAMING_AVAILABLE:
        return []
    workspace = input_path.parent
    if not (workspace / "project.json").is_file():
        return []
    try:
        _, violations = check_artifact_naming.check_workspace(str(workspace))
    except OSError:
        return []
    return [f"workspace naming: {violation}" for violation in violations]


def loaded_schemas() -> tuple[dict[str, dict], Registry]:
    directory = schema_dir()
    schemas = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return schemas, registry


def bench_test_errors(records: list[dict]) -> list[str]:
    """One consistent project, one consistent scope, one consistent iteration.

    The declared iteration must be the iteration every supplied run belongs to: a
    record that quietly mixes two rounds into one variance estimate would pool runs
    that were never meant to be pooled.
    """
    errors: list[str] = []
    project_ids = {record.get("project_id") for record in records}
    if len(project_ids) != 1:
        errors.append(
            "bench_test records must all carry the same project_id; found "
            + ", ".join(sorted(str(value) for value in project_ids)))
    scopes = {record.get("evidence_scope") for record in records}
    if scopes - {"SYNTHETIC", "PHYSICAL"} or len(scopes) != 1:
        errors.append(
            "bench_test records must all carry one valid evidence_scope (SYNTHETIC or PHYSICAL); found "
            + ", ".join(sorted(str(value) for value in scopes)))
    return errors


def load_bench_records(data: dict, input_path: Path) -> tuple[list[str], list[dict]]:
    """Read and schema-validate every supplied bench-test record (step 11 upstream)."""
    errors: list[str] = []
    records: list[dict] = []
    value = data.get("bench_test_artifacts")
    if not isinstance(value, list) or not value:
        return ["bench_test_artifacts must be a non-empty array of step-11 bench_test record paths"], records
    try:
        schemas, registry = loaded_schemas()
    except (OSError, json.JSONDecodeError) as error:
        return [f"bench_test_artifacts cannot be read: schemas unavailable: {error}"], records
    seen_paths: set[str] = set()
    for index, item in enumerate(value):
        label = f"bench_test_artifacts[{index}]"
        path = resolved_path(item, input_path)
        if path is None:
            errors.append(f"{label} must be a non-empty path string; {ABSENCE_HINT}")
            continue
        if str(path) in seen_paths:
            errors.append(f"{label} {item} is supplied more than once")
            continue
        seen_paths.add(str(path))
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{label} cannot be read: {error}")
            continue
        if not isinstance(record, dict):
            errors.append(f"{label} must be a JSON object")
            continue
        schema_problems = [
            f"{label}: {error.message}"
            for error in Draft202012Validator(schemas[BENCH_TEST_SCHEMA], registry=registry).iter_errors(record)
        ]
        if schema_problems:
            errors.extend(schema_problems)
            continue
        if record.get("stage") != BENCH_TEST_STAGE:
            errors.append(f"{label} {record.get('run_id')} must be stage {BENCH_TEST_STAGE}")
            continue
        records.append(record)
    if not errors:
        errors.extend(bench_test_errors(records))
    return errors, records


def iteration_errors(data: dict, records: list[dict]) -> list[str]:
    """The declared iteration must be the iteration every supplied run belongs to."""
    iteration = data.get("iteration")
    errors: list[str] = []
    if not isinstance(iteration, int) or isinstance(iteration, bool) or iteration < 1:
        return ["iteration must be an integer >= 1"]
    mismatched = sorted({
        record.get("campaign_iteration") for record in records
        if record.get("campaign_iteration") != iteration
    }, key=str)
    if mismatched:
        errors.append(
            f"iteration {iteration} does not match the campaign_iteration of every supplied bench_test record; "
            "found " + ", ".join(str(value) for value in mismatched)
            + ": one variance assessment covers one round, never a pool of rounds")
    return errors


def scope_errors(data: dict, records: list[dict]) -> list[str]:
    """The artifact's evidence scope must be the scope of the runs it assesses."""
    scope = data.get("evidence_scope")
    if scope not in EVIDENCE_SCOPES:
        return ["evidence_scope must be SYNTHETIC or PHYSICAL"]
    mismatched = sorted({record.get("evidence_scope") for record in records if record.get("evidence_scope") != scope})
    if mismatched:
        return [
            f"evidence_scope {scope} does not match the supplied bench_test records' scope "
            + ", ".join(str(value) for value in mismatched)
        ]
    return []


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    extra = sorted(set(data) - INPUT_FIELDS)
    missing = sorted(REQUIRED_INPUT_FIELDS - set(data))
    if extra or missing:
        return [
            "input must contain only the variance-assessment input fields; "
            f"unexpected={extra or 'none'} missing={missing or 'none'}"
        ]
    errors: list[str] = []
    if not has_text(data.get("variance_id")):
        errors.append("variance_id must be a non-empty string")
    if not has_text(data.get("campaign_reference")):
        errors.append("campaign_reference must be a non-empty string; a variance assessment belongs to a campaign")
    errors.extend(evidence_errors(data.get("evidence")))
    if not errors and has_gap(data.get("evidence")):
        errors.append(
            "evidence contains GAP; an unanswerable question belongs on the record as the engine's verdict "
            "(UNDERPOWERED), not on the request as an open gap"
        )
    errors.extend(prediction_interval_errors(data.get("model_prediction_interval")))
    errors.extend(mode_errors(data.get("input_mode"), data.get("engine_input")))
    errors.extend(engine_input_errors(data.get("engine_input")))
    record_errors, records = load_bench_records(data, input_path)
    errors.extend(record_errors)
    if records and not record_errors:
        errors.extend(iteration_errors(data, records))
        errors.extend(scope_errors(data, records))
        errors.extend(provenance_errors(data.get("engine_input"), records))
    errors.extend(workspace_naming_errors(input_path))
    return errors


def gate_lines(data: dict) -> list[str]:
    """The routing decision, computed deterministically so the caller sees it up front."""
    engine_input = data.get("engine_input") if isinstance(data.get("engine_input"), dict) else {}
    analyses = engine_input.get("analyses") or []
    arms = engine_input.get("comparison_arms")
    lines = [
        "GATE: this record carries engine output only; the four verdicts pass through unchanged and "
        "UNDERPOWERED is never collapsed into NO_DETECTABLE_DIFFERENCE",
        f"GATE: analyses={', '.join(analyses)}; frozen constants alpha={FROZEN_ALPHA:g} "
        f"target_power={FROZEN_TARGET_POWER:g} k_required={FROZEN_K_REQUIRED:g} (SIGMA_MAX = delta / k)",
    ]
    if arms is None:
        lines.append(
            "GATE: no comparison_arms declared, so no difference is claimed: the engine's verdict can never be "
            "CONSISTENT_DIFFERENCE or NO_DETECTABLE_DIFFERENCE from this record")
    if "POWER_ANALYSIS" in analyses and not is_positive_number(engine_input.get("preregistered_delta")):
        lines.append(
            "GATE: POWER_ANALYSIS is requested without a pre-registered delta, so the engine will report power "
            "NOT_COMPUTABLE and the verdict will be UNDERPOWERED -- which is the honest answer, not a missing "
            "value to be filled in. Without a pre-registered delta no design can be declared free of a difference")
    return lines


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_variance_assessment.py <input.json>")
        return 1
    input_path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, input_path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    _, records = load_bench_records(data, input_path)
    print("READY: input can form one VARIANCE_ASSESSED record")
    for line in gate_lines(data):
        print(line)
    print(f"NOTE: {len(records)} bench_test run(s) supplied for iteration {data.get('iteration')}")
    for line in input_notes(data):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
