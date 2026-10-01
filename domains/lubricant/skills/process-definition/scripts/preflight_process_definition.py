"""Reject incomplete process-definition input before a process artifact is built.

Upstream artifact: one DESIGN_SPACE_DEFINED design space. The process record
must not be created from an absent, non-GO, or different-project design space.
Every process parameter must carry both `source` and `evidence_id`; a parameter
without provenance is rejected rather than defaulted.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from process_policy import has_gap


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "design_space.schema.json", "process.schema.json")
MEASUREMENT_FIELDS = ("value", "unit", "source", "method_version", "material_batch", "formula_version")
INPUT_FIELDS = {"design_space_artifact", "process"}
PROCESS_FIELDS = {
    "process_id", "project_reference", "process_step", "batch_scale", "amplification_factor",
    "process_window", "control_points", "cpk", "material_batch_reference", "factor_role",
    "evidence_scope", "evidence",
}
STEP_TYPES = {
    "SAPONIFICATION", "DEHYDRATION", "PHASE_INVERSION", "DILUTION_COOLING",
    "MILLING", "HOMOGENIZATION", "VACUUM_DEAERATION", "FILLING",
}
EVIDENCE_SCOPES = {"SYNTHETIC", "PHYSICAL"}
CONTROL_TYPES = {"INCOMING", "IN_PROCESS", "FINAL"}
FACTOR_ROLES = {"WHOLE_PLOT", "SUB_PLOT"}
SCALE_CLASSES = {"LAB", "PILOT", "PRODUCTION"}
PARAMETER_STATUSES = {"OBSERVED", "ASSUMED"}


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def schema_artifact(path: Path, name: str, label: str) -> tuple[list[str], dict | None]:
    try:
        schemas = schema_dir()
        loaded = {item: json.loads((schemas / item).read_text(encoding="utf-8")) for item in SCHEMA_NAMES}
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(loaded[name], registry=registry).iter_errors(artifact)]
    return errors, artifact if not errors else None


def measurement_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, dict) or set(value) != set(MEASUREMENT_FIELDS):
        return [label]
    errors = []
    for field in MEASUREMENT_FIELDS:
        item = value.get(field)
        if field == "value":
            if not is_finite_number(item):
                errors.append(f"{label}.value")
        elif not has_text(item):
            errors.append(f"{label}.{field}")
    return errors


def evidence_errors(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["process.evidence"]
    errors = []
    for index, item in enumerate(value):
        label = f"process.evidence[{index}]"
        if not isinstance(item, dict) or set(item) != {"evidence_id", "statement", "source", "status"}:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in {"OBSERVED", "ASSUMED", "GAP"}:
            errors.append(f"{label}.status")
    return errors


def parameter_errors(value: object, label: str) -> list[str]:
    permitted = {"parameter_id", "parameter_name", "lower_bound", "upper_bound", "unit", "source", "evidence_id", "status"}
    if not isinstance(value, dict):
        return [label]
    errors = []
    for field in sorted(set(value) - permitted):
        errors.append(f"{label}.{field} is not a permitted process parameter field")
    for field in ("parameter_id", "parameter_name", "unit"):
        if not has_text(value.get(field)):
            errors.append(f"{label}.{field}")
    # source / evidence_id are the load-bearing provenance fields: a parameter
    # without them is rejected explicitly, never silently accepted.
    for field in ("source", "evidence_id"):
        if not has_text(value.get(field)):
            errors.append(f"{label}.{field} is required for every process parameter")
    lower, upper = value.get("lower_bound"), value.get("upper_bound")
    if not is_finite_number(lower):
        errors.append(f"{label}.lower_bound")
    if not is_finite_number(upper):
        errors.append(f"{label}.upper_bound")
    if is_finite_number(lower) and is_finite_number(upper) and lower > upper:
        errors.append(f"{label}.lower_bound must be <= upper_bound")
    if value.get("status") not in PARAMETER_STATUSES:
        errors.append(f"{label}.status")
    return errors


def process_step_errors(value: object) -> tuple[list[str], set[str]]:
    if not isinstance(value, list) or not value:
        return ["process.process_step"], set()
    errors: list[str] = []
    parameter_ids: set[str] = set()
    for index, step in enumerate(value):
        label = f"process.process_step[{index}]"
        if not isinstance(step, dict) or set(step) != {"step_id", "step_type", "parameters"}:
            errors.append(label)
            continue
        if not has_text(step.get("step_id")):
            errors.append(f"{label}.step_id")
        if step.get("step_type") not in STEP_TYPES:
            errors.append(f"{label}.step_type")
        parameters = step.get("parameters")
        if not isinstance(parameters, list) or not parameters:
            errors.append(f"{label}.parameters")
            continue
        for parameter_index, parameter in enumerate(parameters):
            parameter_label = f"{label}.parameters[{parameter_index}]"
            errors.extend(parameter_errors(parameter, parameter_label))
            if isinstance(parameter, dict) and has_text(parameter.get("parameter_id")):
                parameter_ids.add(parameter["parameter_id"])
    return errors, parameter_ids


def control_point_errors(value: object, parameter_ids: set[str]) -> list[str]:
    required = {"control_point_id", "parameter_id", "control_type", "criterion", "source", "evidence_id"}
    if not isinstance(value, list) or not value:
        return ["process.control_points"]
    errors = []
    for index, item in enumerate(value):
        label = f"process.control_points[{index}]"
        if not isinstance(item, dict) or set(item) != required:
            errors.append(label)
            continue
        for field in ("control_point_id", "parameter_id", "criterion", "source", "evidence_id"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("control_type") not in CONTROL_TYPES:
            errors.append(f"{label}.control_type")
        parameter_id = item.get("parameter_id")
        if has_text(parameter_id) and parameter_ids and parameter_id not in parameter_ids:
            errors.append(f"{label}.parameter_id {parameter_id} does not exist in process_step parameters")
    return errors


def process_errors(value: object, design_space: dict | None) -> list[str]:
    if not isinstance(value, dict) or set(value) != PROCESS_FIELDS:
        return ["process must contain only the process-definition input fields"]
    errors: list[str] = []
    for field in ("process_id", "material_batch_reference"):
        if not has_text(value.get(field)):
            errors.append(f"process.{field}")
    project_reference = value.get("project_reference")
    if not has_text(project_reference):
        errors.append("process.project_reference")
    elif design_space is not None and project_reference != design_space.get("project_id"):
        errors.append("process.project_reference must equal the upstream design_space project_id")
    step_errors, parameter_ids = process_step_errors(value.get("process_step"))
    errors.extend(step_errors)
    batch_scale = value.get("batch_scale")
    if not isinstance(batch_scale, dict) or set(batch_scale) != {"scale_class", "batch_size"}:
        errors.append("process.batch_scale")
    else:
        if batch_scale.get("scale_class") not in SCALE_CLASSES:
            errors.append("process.batch_scale.scale_class")
        errors.extend(measurement_errors(batch_scale.get("batch_size"), "process.batch_scale.batch_size"))
    if not is_finite_number(value.get("amplification_factor")) or value.get("amplification_factor") <= 0:
        errors.append("process.amplification_factor must be a positive number")
    process_window = value.get("process_window")
    if not isinstance(process_window, dict) or set(process_window) != {"window_id", "basis", "validated"}:
        errors.append("process.process_window")
    else:
        for field in ("window_id", "basis"):
            if not has_text(process_window.get(field)):
                errors.append(f"process.process_window.{field}")
        if not isinstance(process_window.get("validated"), bool):
            errors.append("process.process_window.validated")
    errors.extend(control_point_errors(value.get("control_points"), parameter_ids))
    cpk = value.get("cpk")
    if not isinstance(cpk, dict) or set(cpk) != {"value", "ctq_reference", "sample_size"}:
        errors.append("process.cpk")
    else:
        if not is_finite_number(cpk.get("value")):
            errors.append("process.cpk.value")
        if not has_text(cpk.get("ctq_reference")):
            errors.append("process.cpk.ctq_reference")
        sample_size = cpk.get("sample_size")
        if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 1:
            errors.append("process.cpk.sample_size")
    if value.get("factor_role") not in FACTOR_ROLES:
        errors.append("process.factor_role")
    if value.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("process.evidence_scope must be SYNTHETIC or PHYSICAL")
    errors.extend(evidence_errors(value.get("evidence")))
    if not errors and has_gap(value):
        errors.append("process.evidence contains GAP; current input is insufficient")
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors = []
    if set(data) != INPUT_FIELDS:
        errors.append("input must contain only the design space artifact path and process")
    design_space: dict | None = None
    path = resolved_path(data.get("design_space_artifact"), input_path)
    if path is None:
        errors.append("design_space_artifact")
    else:
        item_errors, design_space = schema_artifact(path, "design_space.schema.json", "design_space_artifact")
        errors.extend(item_errors)
        if design_space is not None and design_space.get("stage") != "DESIGN_SPACE_DEFINED":
            errors.append("design_space_artifact must be stage DESIGN_SPACE_DEFINED")
        if design_space is not None and design_space.get("decision") != "GO":
            errors.append("design_space_artifact must have decision GO")
    errors.extend(process_errors(data.get("process"), design_space))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_process_definition.py <input.json>")
        return 1
    path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    print("READY: input can form one process record only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
