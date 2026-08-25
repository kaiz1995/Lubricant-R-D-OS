"""Hold incomplete PHYSICAL experiment imports before any artifact is written."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json")
INPUT_FIELDS = {"project_artifact", "challenge_artifact", "failure_ctq_artifact", "test_method_artifact", "design_space_artifact", "experiment_design_artifact", "doe_output_artifact", "doe_output_digest", "experiment"}
UPSTREAM = (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"), ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"), ("experiment_design_artifact", "experiment_design.schema.json", "EXPERIMENT_DESIGNED"))


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


def candidate(data: dict, project: dict, method: dict, design_space: dict, design: dict, doe: dict, output_digest: str) -> dict:
    record = data.get("experiment", {})
    return {
        "schema_version": "0.1.0", "artifact_type": "experiment", "project_id": project["project_id"], "stage": "EXPERIMENT_RUNNING", "evidence_scope": design["evidence_scope"],
        "decision_question": "Does the supplied PHYSICAL execution record satisfy the import provenance contract?",
        "hypothesis": "The import records supplied execution provenance only.",
        "uncertainty": "No owner approval, method qualification, product-performance, or release conclusion is established by import.",
        "decision_rule": "Import only complete PHYSICAL records linked to one supplied DOE output and qualified method.",
        "result": "Physical execution record imported from supplied records only; not owner approval, method qualification, product performance, or release approval.",
        "decision": "GO", "next_action": "Retain the supplied raw records for existing downstream validation without inferring performance.",
        "experiment_id": record.get("experiment_id"), "experiment_design_reference": design["experiment_design_id"], "design_space_reference": design_space["design_space_id"], "test_method_references": [method["method_id"]],
        "doe_output_reference": {"engine_name": doe["engine_name"], "engine_version": doe["engine_version"], "input_digest": doe["input_digest"], "output_digest": output_digest},
        "runs": record.get("runs"), "evidence": record.get("evidence"),
    }


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors: list[str] = []
    if set(data) != INPUT_FIELDS:
        errors.append("input must contain only experiment-import fields")
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
    if design_space.get("qualified_test_method_references") != [method.get("method_id")]: errors.append("design_space_artifact qualified method link is invalid")
    if design.get("test_method_references") != [method.get("method_id")]: errors.append("experiment_design_artifact method link is invalid")
    doe_errors, doe, output_digest = doe_output(resolve(data.get("doe_output_artifact"), input_path)); errors.extend(doe_errors)
    if doe is None or output_digest is None: return errors
    if data.get("doe_output_digest") != output_digest:
        errors.append("doe_output_digest must equal the supplied DOE output bytes SHA-256")
    record = data.get("experiment")
    if not isinstance(record, dict) or set(record) != {"experiment_id", "runs", "evidence"}:
        return errors + ["experiment must contain only experiment_id, runs, and evidence"]
    if has_gap(record): errors.append("experiment evidence contains GAP")
    points = doe.get("result", {}).get("runs", []) if isinstance(doe.get("result"), dict) else []
    point_ids = {item.get("run_index") for item in points if isinstance(item, dict)}
    seen: set[object] = set()
    expected_ctqs = {item.get("ctq_reference") for item in design.get("responses", []) if isinstance(item, dict)}
    for index, run in enumerate(record.get("runs", []) if isinstance(record.get("runs"), list) else []):
        label = f"experiment.runs[{index}]"
        if not isinstance(run, dict): errors.append(label); continue
        if not all(has_text(run.get(field)) for field in ("run_id", "material_batch", "formula_reference", "formula_version")): errors.append(f"{label} formula/batch reference is incomplete")
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


def main() -> int:
    if len(sys.argv) != 2: print("Usage: python preflight_experiment_import.py <input.json>"); return 1
    path = Path(sys.argv[1]).resolve()
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, path)
    if errors: print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    print("READY: PHYSICAL execution record can be imported without approval or performance inference"); return 0


if __name__ == "__main__": raise SystemExit(main())
