"""Reject incomplete process-window scale-up input before a window artifact is built.

Upstream artifacts: one DESIGN_SPACE_DEFINED process record (from
process-definition) and one OPTIMIZED optimization artifact with `decision: GO`.
A process window is fixed only from both, at a strictly later scale class, on
evidence without GAP. Every rule is fail-closed: an unmet condition yields HOLD,
never a default.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from scale_up_policy import SCALE_ORDER, has_gap


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = ("common.schema.json", "process.schema.json", "optimization.schema.json")
MEASUREMENT_FIELDS = ("value", "unit", "source", "method_version", "material_batch", "formula_version")
INPUT_FIELDS = {"process_artifact", "optimization_artifact", "scale_up"}
SCALE_UP_FIELDS = {"window_id", "basis", "amplification_factor", "batch_scale", "evidence_scope", "evidence"}
EVIDENCE_SCOPES = {"SYNTHETIC", "PHYSICAL"}
SCALE_CLASSES = set(SCALE_ORDER)


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
        return ["scale_up.evidence"]
    errors = []
    for index, item in enumerate(value):
        label = f"scale_up.evidence[{index}]"
        if not isinstance(item, dict) or set(item) != {"evidence_id", "statement", "source", "status"}:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in {"OBSERVED", "ASSUMED", "GAP"}:
            errors.append(f"{label}.status")
    return errors


def scale_up_errors(value: object, process: dict | None) -> list[str]:
    if not isinstance(value, dict) or set(value) != SCALE_UP_FIELDS:
        return ["scale_up must contain only the scale-up input fields"]
    errors: list[str] = []
    for field in ("window_id", "basis"):
        if not has_text(value.get(field)):
            errors.append(f"scale_up.{field}")
    factor = value.get("amplification_factor")
    if not is_finite_number(factor) or factor <= 0:
        errors.append("scale_up.amplification_factor must be a positive number")
    elif process is not None and is_finite_number(process.get("amplification_factor")) and factor <= process["amplification_factor"]:
        errors.append("scale_up.amplification_factor must exceed the process record amplification_factor")
    batch_scale = value.get("batch_scale")
    if not isinstance(batch_scale, dict) or set(batch_scale) != {"scale_class", "batch_size"}:
        errors.append("scale_up.batch_scale")
    else:
        scale_class = batch_scale.get("scale_class")
        if scale_class not in SCALE_CLASSES:
            errors.append("scale_up.batch_scale.scale_class")
        elif process is not None:
            current = (process.get("batch_scale") or {}).get("scale_class")
            if current in SCALE_ORDER and SCALE_ORDER[scale_class] <= SCALE_ORDER[current]:
                errors.append("scale_up.batch_scale.scale_class must advance beyond the process record scale class")
        errors.extend(measurement_errors(batch_scale.get("batch_size"), "scale_up.batch_scale.batch_size"))
    scope = value.get("evidence_scope")
    if scope not in EVIDENCE_SCOPES:
        errors.append("scale_up.evidence_scope must be SYNTHETIC or PHYSICAL")
    elif process is not None and scope != process.get("evidence_scope"):
        errors.append("scale_up.evidence_scope must retain the process record evidence_scope")
    errors.extend(evidence_errors(value.get("evidence")))
    if not errors and has_gap(value):
        errors.append("scale_up.evidence contains GAP; current input is insufficient")
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors: list[str] = []
    if set(data) != INPUT_FIELDS:
        errors.append("input must contain only the process artifact, the optimization artifact, and scale_up")
    process: dict | None = None
    process_path = resolved_path(data.get("process_artifact"), input_path)
    if process_path is None:
        errors.append("process_artifact")
    else:
        item_errors, process = schema_artifact(process_path, "process.schema.json", "process_artifact")
        errors.extend(item_errors)
        if process is not None and process.get("stage") != "DESIGN_SPACE_DEFINED":
            errors.append("process_artifact must be stage DESIGN_SPACE_DEFINED")
    optimization: dict | None = None
    optimization_path = resolved_path(data.get("optimization_artifact"), input_path)
    if optimization_path is None:
        errors.append("optimization_artifact")
    else:
        item_errors, optimization = schema_artifact(optimization_path, "optimization.schema.json", "optimization_artifact")
        errors.extend(item_errors)
        if optimization is not None and optimization.get("decision") != "GO":
            errors.append("optimization_artifact must have decision GO")
    if process is not None and optimization is not None and process.get("project_id") != optimization.get("project_id"):
        errors.append("process_artifact and optimization_artifact must belong to the same project_id")
    errors.extend(scale_up_errors(data.get("scale_up"), process))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_process_scale_up.py <input.json>")
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
    print("READY: input can fix one PROCESS_WINDOW_DEFINED process record only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
