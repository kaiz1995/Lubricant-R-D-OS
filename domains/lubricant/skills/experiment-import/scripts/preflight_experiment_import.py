"""Hold incomplete experiment imports before any artifact is written.

WP-07: the import is classified by `evidence_class`. A record without an
explicit `evidence_class` is treated as DOE_POINT (backward compatible: every
pre-existing record keeps its contract). Only DOE_POINT imports consume a DOE
output and its points; APPLICATION_FIELD and CONFIRMATORY_NON_DOE records are
held to their own declared minimal input sets (module docstring constants
below) and are still provenance-bound (test method + execution provenance).

ADDITIVE (step 11, PRECISION_GREASE_DEV): the same skill also produces the
``bench_test`` record of the precision-grease inner loop, so this gate serves
both artifact kinds. The bench path is a SECOND ENTRY POINT, selected only when
the request carries a ``bench_test`` record; every constant, function and message
of the experiment path is untouched, and an experiment request never reaches the
bench code. The bench entry is itself gated on the supplied charter routing as
``PRECISION_GREASE_DEV``, because ``BENCH_TESTED`` is on no oil route.

The censoring discipline of the bench path lives in ``bench_test_policy`` and is
enforced here, in the builder and in the validator through the one shared module:
a right-censored observation is never recorded as an end-point value, and a
censored or event-free run must declare why it stopped.

E-3/L5 (bench slot gate): the bench request also names the round's
``screening_artifacts``, and this gate resolves them instead of trusting the paths.
Each is schema-checked at stage ``SCREENING_PASSED``, and the run's
``sample_reference`` must fall on one whose ``overall_verdict`` is PASS with
``gate_to_bench`` RELEASED -- a sample the screen FAILed must not be documented as
having spent a bench slot. E-2: the record also carries ``ctq_reference``, the CTQ
the run observed, which is what the step-14 modeling entry links its response
references against on the grease route.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from bench_test_policy import (
    BENCH_INPUT_FIELDS,
    EVIDENCE_FIELDS,
    EVIDENCE_SCOPES,
    EVIDENCE_STATUSES,
    REROUTE_HOLD,
    ROUTED_PROJECT_TYPE,
    bench_test_artifact,
    censoring_notes,
    gate_lines,
    input_record_errors,
    is_bench_request,
    release_line,
    released_screening,
    screening_release_errors,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json")
# E-3 / L5: the bench path also carries the screening records that released the run's
# sample, so its own schema set gains ``screening.schema.json``. The experiment path's
# own list (SCHEMA_NAMES above) is untouched: it has no use for a screening record.
BENCH_SCHEMA_NAMES = ("common.schema.json", "project.schema.json", "bench_test.schema.json", "screening.schema.json")
UPSTREAM = (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"), ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"), ("experiment_design_artifact", "experiment_design.schema.json", "EXPERIMENT_DESIGNED"))
DOE_INPUT_FIELDS = {"doe_output_artifact", "doe_output_digest"}
INPUT_FIELDS = {key for key, _, _ in UPSTREAM} | {"experiment"} | DOE_INPUT_FIELDS
RECORD_FIELDS = {"experiment_id", "runs", "evidence"}
RECORD_OPTIONAL_FIELDS = {"evidence_class", "application_reference", "bench_reference"}
EVIDENCE_CLASSES = ("DOE_POINT", "APPLICATION_FIELD", "CONFIRMATORY_NON_DOE")
DEFAULT_EVIDENCE_CLASS = "DOE_POINT"


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def resolve(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def schema_dir() -> Path:
    return SKILL_ROOT.parents[1] / "schemas"


def schemas() -> tuple[dict[str, dict], Registry]:
    directory = schema_dir()
    loaded = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return loaded, registry


def artifact(path: Path | None, schema_name: str, label: str) -> tuple[list[str], dict | None]:
    if path is None:
        return [label], None
    try:
        value = json.loads(path.read_text(encoding="utf-8")); loaded, registry = schemas()
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(loaded[schema_name], registry=registry).iter_errors(value)]
    return errors, value if not errors else None


def has_gap(value: object) -> bool:
    return isinstance(value, dict) and any(isinstance(item, dict) and item.get("status") == "GAP" for item in value.get("evidence", []))


def timestamp_ok(value: object) -> bool:
    if not has_text(value):
        return False
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def doe_output(path: Path | None) -> tuple[list[str], dict | None, str | None]:
    if path is None:
        return ["doe_output_artifact"], None, None
    try:
        raw = path.read_bytes(); value = json.loads(raw.decode("utf-8"))
        schema = json.loads((SKILL_ROOT.parents[1] / "domains" / "lubricant" / "schemas" / "doe_result_schema.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"doe_output_artifact cannot be read: {error}"], None, None
    errors = [f"doe_output_artifact: {error.message}" for error in Draft202012Validator(schema).iter_errors(value)]
    if value.get("engine_name") != "doe" or value.get("status") != "OK":
        errors.append("doe_output_artifact must be an OK doe output")
    return errors, value if not errors else None, hashlib.sha256(raw).hexdigest()


def candidate(data: dict, project: dict, method: dict, design_space: dict, design: dict, doe: dict | None, output_digest: str | None) -> dict:
    record = data.get("experiment", {})
    evidence_class = record.get("evidence_class", DEFAULT_EVIDENCE_CLASS)
    artifact: dict = {
        "schema_version": "0.1.0", "artifact_type": "experiment", "project_id": project["project_id"], "stage": "EXPERIMENT_RUNNING", "evidence_scope": design["evidence_scope"],
        "decision_question": "Does the supplied PHYSICAL execution record satisfy the import provenance contract?",
        "hypothesis": "The import records supplied execution provenance only.",
        "uncertainty": "No owner approval, method qualification, product-performance, or release conclusion is established by import.",
        "decision_rule": "Import only complete PHYSICAL records linked to one supplied DOE output and qualified method." if evidence_class == "DOE_POINT" else "Import only complete PHYSICAL non-DOE records with qualified method, full execution provenance, and their declared non-DOE anchors; they never enter the modeling entry.",
        "result": "Physical execution record imported from supplied records only; not owner approval, method qualification, product performance, or release approval.",
        "decision": "GO", "next_action": "Retain the supplied raw records for existing downstream validation without inferring performance.",
        "experiment_id": record.get("experiment_id"), "evidence_class": evidence_class, "experiment_design_reference": design["experiment_design_id"], "design_space_reference": design_space["design_space_id"], "test_method_references": [method["method_id"]],
        "runs": record.get("runs"), "evidence": record.get("evidence"),
    }
    if evidence_class == "DOE_POINT":
        artifact["doe_output_reference"] = {"engine_name": doe["engine_name"], "engine_version": doe["engine_version"], "input_digest": doe["input_digest"], "output_digest": output_digest}
    for field in ("application_reference", "bench_reference"):
        if has_text(record.get(field)):
            artifact[field] = record[field]
    return artifact


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors: list[str] = []
    record = data.get("experiment")
    if not isinstance(record, dict) or not set(record) <= RECORD_FIELDS | RECORD_OPTIONAL_FIELDS or not RECORD_FIELDS <= set(record):
        if isinstance(record, dict):
            extra = sorted(set(record) - RECORD_FIELDS - RECORD_OPTIONAL_FIELDS)
            missing = sorted(RECORD_FIELDS - set(record))
            return ["experiment must contain only experiment_id, runs, evidence, and the optional WP-07 fields (evidence_class, application_reference, bench_reference)"
                    + f"; unexpected={extra or 'none'} missing={missing or 'none'}"]
        return ["experiment must contain only experiment_id, runs, evidence, and the optional WP-07 fields"]
    evidence_class = record.get("evidence_class", DEFAULT_EVIDENCE_CLASS)
    if evidence_class not in EVIDENCE_CLASSES:
        return [f"experiment.evidence_class must be one of {list(EVIDENCE_CLASSES)}; got {evidence_class!r}"]
    doe_required = evidence_class == DEFAULT_EVIDENCE_CLASS
    expected_input_fields = INPUT_FIELDS if doe_required else INPUT_FIELDS - DOE_INPUT_FIELDS
    if set(data) != expected_input_fields:
        extra = sorted(set(data) - expected_input_fields)
        missing = sorted(expected_input_fields - set(data))
        errors.append("input must contain only experiment-import fields"
                      + ("" if doe_required else " (non-DOE_POINT imports do not consume a DOE output)")
                      + f"; unexpected={extra or 'none'} missing={missing or 'none'}")
        return errors
    loaded: dict[str, dict | None] = {}
    for key, schema_name, stage in UPSTREAM:
        item_errors, value = artifact(resolve(data.get(key), input_path), schema_name, key)
        errors.extend(item_errors); loaded[key] = value
        if value is not None and (value.get("stage") != stage or value.get("decision") != "GO"):
            errors.append(f"{key} must be {stage} with decision GO")
        if has_gap(value): errors.append(f"{key} evidence contains GAP")
    project, challenge, failure, method, design_space, design = (loaded[key] for key, _, _ in UPSTREAM)
    if any(value is None for value in (project, challenge, failure, method, design_space, design)):
        return errors
    assert isinstance(project, dict) and isinstance(challenge, dict) and isinstance(failure, dict) and isinstance(method, dict) and isinstance(design_space, dict) and isinstance(design, dict)
    if len({value["project_id"] for value in (project, challenge, failure, method, design_space, design)}) != 1:
        errors.append("upstream project_id values must match")
    if project.get("status") != "ACTIVE": errors.append("project_artifact must be ACTIVE")
    if method.get("evidence_scope") != "PHYSICAL" or design.get("evidence_scope") != "PHYSICAL": errors.append("experiment import requires PHYSICAL test method and experiment design")
    if method.get("qualification_status") != "QUALIFIED": errors.append("test_method_artifact must be QUALIFIED")
    if failure.get("challenge_reference") != challenge.get("challenge_id"): errors.append("failure_ctq_artifact challenge link is invalid")
    if method.get("target_failure_reference") != failure.get("failure_id"): errors.append("test_method_artifact failure link is invalid")
    if design.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_design_artifact design-space link is invalid")
    # Defect 1 fix: membership replaces equality so a design space may declare
    # several qualified methods, one per CTQ. The per-CTQ cross-check below
    # still rejects a method that is not qualified or not linked to its CTQ.
    declared_methods = design_space.get("qualified_test_method_references")
    if method is not None and (not isinstance(declared_methods, list) or method.get("method_id") not in declared_methods): errors.append("design_space_artifact qualified method link is invalid")
    if method.get("method_id") not in (design.get("test_method_references") or []): errors.append("experiment_design_artifact method link is invalid")
    doe = None
    output_digest = None
    point_ids: set[object] = set()
    if doe_required:
        doe_errors, doe, output_digest = doe_output(resolve(data.get("doe_output_artifact"), input_path)); errors.extend(doe_errors)
        if doe is None or output_digest is None: return errors
        if data.get("doe_output_digest") != output_digest:
            errors.append("doe_output_digest must equal the supplied DOE output bytes SHA-256")
        points = doe.get("result", {}).get("runs", []) if isinstance(doe.get("result"), dict) else []
        point_ids = {item.get("run_index") for item in points if isinstance(item, dict)}
    if not doe_required and evidence_class == "CONFIRMATORY_NON_DOE" and not (has_text(record.get("application_reference")) or has_text(record.get("bench_reference"))):
        errors.append("CONFIRMATORY_NON_DOE records must cite an application_reference or bench_reference anchor")
    if has_gap(record): errors.append("experiment evidence contains GAP")
    seen: set[object] = set()
    expected_ctqs = {item.get("ctq_reference") for item in design.get("responses", []) if isinstance(item, dict)}
    for index, run in enumerate(record.get("runs", []) if isinstance(record.get("runs"), list) else []):
        label = f"experiment.runs[{index}]"
        if not isinstance(run, dict): errors.append(label); continue
        if not all(has_text(run.get(field)) for field in ("run_id", "material_batch", "formula_reference", "formula_version")): errors.append(f"{label} formula/batch reference is incomplete")
        if not doe_required:
            if "doe_point_reference" in run:
                errors.append(f"{label} carries doe_point_reference; only DOE_POINT records consume DOE points")
        else:
            point = run.get("doe_point_reference", {}).get("run_index") if isinstance(run.get("doe_point_reference"), dict) else None
            if point not in point_ids or point in seen: errors.append(f"{label} DOE point reference is missing, invalid, or duplicated")
            seen.add(point)
        execution = run.get("execution_provenance")
        if not isinstance(execution, dict) or not timestamp_ok(execution.get("executed_at")) or not all(has_text(execution.get(field)) for field in ("operator_reference", "instrument_reference", "calibration_reference", "raw_record_reference")):
            errors.append(f"{label} execution provenance is incomplete")
        for response in run.get("response_measurements", []) if isinstance(run.get("response_measurements"), list) else []:
            if not isinstance(response, dict): errors.append(f"{label}.response_measurements"); continue
            measurement, reference = response.get("measurement"), response.get("method_reference")
            if response.get("ctq_reference") not in expected_ctqs: errors.append(f"{label} CTQ is not in experiment design")
            if not isinstance(reference, dict) or reference.get("method_id") != method.get("method_id") or not has_text(reference.get("qualification_reference")): errors.append(f"{label} method qualification reference is invalid")
            if not isinstance(measurement, dict) or measurement.get("material_batch") != run.get("material_batch") or measurement.get("formula_version") != run.get("formula_version") or not has_text(measurement.get("method_version")):
                errors.append(f"{label} measurement batch/formula/method version is invalid")
    value = candidate(data, project, method, design_space, design, doe, output_digest)
    try:
        schemas_value, registry = schemas()
        errors.extend(f"experiment: {error.message}" for error in Draft202012Validator(schemas_value["experiment.schema.json"], registry=registry).iter_errors(value))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"experiment schema cannot be read: {error}")
    return errors


def bench_schema_dir() -> Path:
    """Resolve the bench entry's schema directory with the house-style layout probe.

    Repository layout: the canonical schemas live in the pack-level ``schemas/`` tree.
    Deployed layout: the installer copies them beside this skill as ``references/``
    (install_domain_skill.py maps the skill to its schema list). This probe is
    deliberately SEPARATE from :func:`schema_dir`, which the experiment path keeps
    using unchanged: the probe only ever selects a directory that actually holds the
    bench schema set, so it cannot alter what the experiment path resolves.
    """
    canonical = SKILL_ROOT.parents[1] / "schemas"
    if all((canonical / name).is_file() for name in BENCH_SCHEMA_NAMES):
        return canonical
    return SKILL_ROOT / "references"


def bench_schemas() -> tuple[dict[str, dict], Registry]:
    """Load the bench entry's own schema set (common + project + bench_test).

    Kept separate from :func:`schemas` on purpose: the experiment path must keep loading
    exactly the eight schemas it always loaded, and this list is a superset only by
    sharing common/project.
    """
    directory = bench_schema_dir()
    loaded = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in BENCH_SCHEMA_NAMES}
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return loaded, registry


def bench_screenings(data: object, input_path: Path) -> tuple[list[str], list[dict]]:
    """The request's screening artifacts: loaded, schema-checked and release-judged (E-3/L5).

    The bench path resolves the screening reference instead of trusting it. Every named
    artifact is read from the request's directory and validated against
    ``screening.schema.json`` (whose stage is the const SCREENING_PASSED, re-read
    explicitly); the run's ``sample_reference`` must then be released by one of them --
    ``overall_verdict`` PASS with ``gate_to_bench`` RELEASED. A sample the screen FAILed
    (which the screening contract forces to BLOCKED) must not be documented as having
    spent a bench slot: the slot is the scarcest resource of the inner loop.

    Returns ``(errors, screenings)``; every screening that passed loading is returned even
    when the release judgement fails, so the caller can still report what was examined.
    """
    screening_paths = data.get("screening_artifacts") if isinstance(data, dict) else None
    if not isinstance(screening_paths, list) or not screening_paths:
        return ["screening_artifacts must be a non-empty array of screening artifact paths"], []
    try:
        loaded, registry = bench_schemas()
    except (OSError, json.JSONDecodeError) as error:
        return [f"bench-test schemas cannot be read: {error}"], []
    errors: list[str] = []
    screenings: list[dict] = []
    for index, value in enumerate(screening_paths):
        path = resolve(value, input_path)
        if path is None:
            errors.append(f"screening_artifacts[{index}] must be a non-empty path")
            continue
        try:
            screening = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"screening_artifacts[{index}] cannot be read: {error}")
            continue
        item_errors = [
            f"screening_artifacts[{index}]: {error.message}"
            for error in Draft202012Validator(loaded["screening.schema.json"], registry=registry).iter_errors(screening)
        ]
        if item_errors:
            errors.extend(item_errors)
            continue
        # The schema fixes stage to the const SCREENING_PASSED; re-read it explicitly so
        # the gate's own requirement is visible in one place.
        if screening.get("stage") != "SCREENING_PASSED":
            errors.append(f"screening_artifacts[{index}] must be stage SCREENING_PASSED")
            continue
        screenings.append(screening)
    if not errors:
        errors.extend(screening_release_errors(data.get("bench_test"), screenings))
    return errors, screenings


def bench_evidence_errors(value: object) -> list[str]:
    """Artifact-level evidence, same shape rule the grease route's other skills use."""
    if not isinstance(value, list) or not value:
        return ["evidence"]
    errors: list[str] = []
    for index, item in enumerate(value):
        label = f"evidence[{index}]"
        if not isinstance(item, dict) or set(item) != EVIDENCE_FIELDS:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"{label}.status")
    return errors


def bench_errors_for(data: object, input_path: Path) -> list[str]:
    """Every reason a bench-run request is not recordable. Empty list = it is.

    Fail-closed: the charter and the record are both validated against their own schemas,
    the charter must route as ``PRECISION_GREASE_DEV`` (BENCH_TESTED is on no oil route),
    and the censoring discipline is applied by the shared ``bench_test_policy``. The
    record's own reasons are always collected, so a censored observation carrying an
    end-point is reported even when the charter is also wrong.
    """
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != BENCH_INPUT_FIELDS:
        extra = sorted(set(data) - BENCH_INPUT_FIELDS)
        missing = sorted(BENCH_INPUT_FIELDS - set(data))
        return [
            "input must contain only the bench-test import fields; "
            f"unexpected={extra or 'none'} missing={missing or 'none'}"
        ]
    try:
        loaded, registry = bench_schemas()
    except (OSError, json.JSONDecodeError) as error:
        return [f"bench-test schemas cannot be read: {error}"]
    errors: list[str] = []
    project = None
    project_path = resolve(data.get("project_artifact"), input_path)
    if project_path is None:
        errors.append("project_artifact")
    else:
        try:
            project = json.loads(project_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"project_artifact cannot be read: {error}")
        else:
            errors.extend(
                f"project_artifact: {error.message}"
                for error in Draft202012Validator(loaded["project.schema.json"], registry=registry).iter_errors(project)
            )
    if isinstance(project, dict):
        if project.get("status") != "ACTIVE":
            errors.append("project_artifact must have status ACTIVE")
        if project.get("stage") != "PROJECT_DEFINED":
            errors.append("project_artifact must be stage PROJECT_DEFINED")
        if project.get("decision") != "GO":
            errors.append("project_artifact must have decision GO")
        if project.get("project_type") != ROUTED_PROJECT_TYPE:
            errors.append(
                f"project_artifact.project_type is {project.get('project_type')!r}: {REROUTE_HOLD}"
            )
    if data.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("evidence_scope must be SYNTHETIC or PHYSICAL")
    errors.extend(bench_evidence_errors(data.get("evidence")))
    errors.extend(input_record_errors(data.get("bench_test")))
    # E-3/L5: the bench slot is spent only on a sample a PASS/RELEASED screen released.
    # Collected beside the record's own reasons so a censoring violation and an unreleased
    # sample are both reported in one refusal.
    screening_errors, _screenings = bench_screenings(data, input_path)
    errors.extend(screening_errors)
    if errors:
        return errors
    artifact = bench_test_artifact(data["bench_test"], project, data["evidence_scope"], data["evidence"])
    errors.extend(
        f"bench_test: {error.message}"
        for error in Draft202012Validator(loaded["bench_test.schema.json"], registry=registry).iter_errors(artifact)
    )
    return errors


def bench_main(data: dict, input_path: Path) -> int:
    """The bench-test entry point: NOTE lines, then the GATE line, then the verdict."""
    errors = bench_errors_for(data, input_path)
    record = data.get("bench_test") if isinstance(data, dict) else None
    for note in censoring_notes(record):
        print(note)
    for line in gate_lines(data):
        print(line)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    # The release conclusion is printed only when it holds: the run may spend a bench slot
    # because a supplied screening released its sample (E-3/L5).
    _, screenings = bench_screenings(data, input_path)
    released = released_screening(data.get("bench_test"), screenings)
    if released is not None:
        print(release_line(data["bench_test"], released))
    print("READY: bench run can be recorded as one BENCH_TESTED observation, censoring included")
    return 0


def main() -> int:
    if len(sys.argv) != 2: print("Usage: python preflight_experiment_import.py <input.json>"); return 1
    path = Path(sys.argv[1]).resolve()
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    if is_bench_request(data):
        return bench_main(data, path)
    errors = errors_for(data, path)
    if errors: print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    print("READY: execution record can be imported without approval or performance inference"); return 0


if __name__ == "__main__": raise SystemExit(main())
