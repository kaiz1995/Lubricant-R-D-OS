"""Reject incomplete or overclaimed Failure/CTQ input before an artifact is written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SKILL_ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_FIELDS = ("value", "unit", "source", "method_version", "material_batch", "formula_version")
CTQ_CLASSES = {"CTQ", "DEGRADATION_INDICATOR", "FUNCTIONAL_SYMPTOM"}
EVIDENCE_STATUSES = {"OBSERVED", "ASSUMED", "GAP"}
UNCERTAINTY_MARKERS = ("may", "possible", "potential", "hypothesis", "pending", "to be verified", "可能", "待验证", "尚待", "假设", "潜在", "需验证", "未证实")
CONFIRMED_CAUSE_MARKERS = ("confirmed root cause", "confirmed cause", "proven cause", "direct cause", "已确认根因", "已证实为原因", "确定由")
CONFIRMED_ROOT_CAUSE_MARKERS = ("confirmed root cause", "proven", "established", "direct cause", "root cause is", "已确认", "已证实", "已证明", "根因是", "确定为")


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    names = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json")
    return canonical if all((canonical / name).is_file() for name in names) else SKILL_ROOT / "references"


def schema_errors(path: Path, schema_name: str, label: str) -> tuple[list[str], dict | None]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
        schemas = schema_dir()
        common = json.loads((schemas / "common.schema.json").read_text(encoding="utf-8"))
        project = json.loads((schemas / "project.schema.json").read_text(encoding="utf-8"))
        challenge = json.loads((schemas / "challenge.schema.json").read_text(encoding="utf-8"))
        schema = {"project.schema.json": project, "challenge.schema.json": challenge}[schema_name]
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    registry = registry.with_resource(project["$id"], Resource.from_contents(project))
    registry = registry.with_resource(challenge["$id"], Resource.from_contents(challenge))
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(schema, registry=registry).iter_errors(artifact)]
    return errors, artifact if not errors else None


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def measurement_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [label]
    errors: list[str] = []
    for field in MEASUREMENT_FIELDS:
        item = value.get(field)
        if field == "value":
            if not isinstance(item, (int, float)) or isinstance(item, bool):
                errors.append(f"{label}.value")
        elif not has_text(item):
            errors.append(f"{label}.{field}")
    return errors


def text_list_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(has_text(item) for item in value):
        return [label]
    return []


def contribution_errors(value: object) -> list[str]:
    if not has_text(value):
        return ["failure_ctq.lubricant_contribution"]
    lowered = value.casefold()
    if any(marker in lowered for marker in CONFIRMED_CAUSE_MARKERS):
        return ["failure_ctq.lubricant_contribution must not claim a confirmed cause"]
    if not any(marker in lowered for marker in UNCERTAINTY_MARKERS):
        return ["failure_ctq.lubricant_contribution must state possible or pending verification"]
    return []


def root_cause_errors(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["failure_ctq.root_cause_hypotheses"]
    errors: list[str] = []
    for index, item in enumerate(value):
        label = f"failure_ctq.root_cause_hypotheses[{index}]"
        if not has_text(item):
            errors.append(label)
            continue
        if item.startswith("Hypothesis:"):
            statement = item.removeprefix("Hypothesis:").strip()
        elif item.startswith("假设:"):
            statement = item.removeprefix("假设:").strip()
        else:
            errors.append(f"{label} must start with Hypothesis: or 假设:")
            continue
        if not statement:
            errors.append(f"{label} must contain a hypothesis after its prefix")
        if any(marker in statement.casefold() for marker in CONFIRMED_ROOT_CAUSE_MARKERS):
            errors.append(f"{label} must not state a confirmed root cause")
    return errors


def evidence_errors(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["evidence"]
    errors: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"evidence[{index}]")
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"evidence[{index}].{field}")
        if item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"evidence[{index}].status is invalid")
    return errors


def failure_ctq_errors(value: object, challenge: dict | None) -> list[str]:
    if not isinstance(value, dict):
        return ["failure_ctq"]
    errors: list[str] = []
    for field in ("challenge_reference", "failure_id", "failure_mode", "mechanism", "failure_diagnosis"):
        if not has_text(value.get(field)):
            errors.append(f"failure_ctq.{field}")
    if challenge is not None and value.get("challenge_reference") != challenge.get("challenge_id"):
        errors.append("failure_ctq.challenge_reference must equal challenge_artifact.challenge_id")
    errors.extend(root_cause_errors(value.get("root_cause_hypotheses")))
    errors.extend(contribution_errors(value.get("lubricant_contribution")))
    ctqs = value.get("ctqs")
    if not isinstance(ctqs, list) or not ctqs:
        errors.append("failure_ctq.ctqs")
    else:
        for index, ctq in enumerate(ctqs):
            label = f"failure_ctq.ctqs[{index}]"
            if not isinstance(ctq, dict):
                errors.append(label)
                continue
            for field in ("ctq_id", "observable"):
                if not has_text(ctq.get(field)):
                    errors.append(f"{label}.{field}")
            if ctq.get("classification") not in CTQ_CLASSES:
                errors.append(f"{label}.classification is invalid")
            errors.extend(measurement_errors(ctq.get("specification_limit"), f"{label}.specification_limit"))
            errors.extend(measurement_errors(ctq.get("engineering_risk_limit"), f"{label}.engineering_risk_limit"))
            if ctq.get("specification_limit") == ctq.get("engineering_risk_limit"):
                errors.append(f"{label} limits must be separately recorded as compliance and engineering-risk boundaries")
            errors.extend(text_list_errors(ctq.get("test_references"), f"{label}.test_references"))
            errors.extend(text_list_errors(ctq.get("evidence_required"), f"{label}.evidence_required"))
    errors.extend(text_list_errors(value.get("test_chain"), "failure_ctq.test_chain"))
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors: list[str] = []
    project_path = resolved_path(data.get("project_artifact"), input_path)
    if project_path is None:
        errors.append("project_artifact")
        project = None
    else:
        project_errors, project = schema_errors(project_path, "project.schema.json", "project_artifact")
        errors.extend(project_errors)
        if project is not None and (project.get("stage") != "PROJECT_DEFINED" or project.get("status") != "ACTIVE"):
            errors.append("project_artifact must be stage PROJECT_DEFINED and status ACTIVE")
    challenge_path = resolved_path(data.get("challenge_artifact"), input_path)
    if challenge_path is None:
        errors.append("challenge_artifact")
        challenge = None
    else:
        challenge_errors, challenge = schema_errors(challenge_path, "challenge.schema.json", "challenge_artifact")
        errors.extend(challenge_errors)
        if challenge is not None and challenge.get("stage") != "CHALLENGES_DEFINED":
            errors.append("challenge_artifact must be stage CHALLENGES_DEFINED")
    if project is not None and challenge is not None and project.get("project_id") != challenge.get("project_id"):
        errors.append("project_artifact.project_id must equal challenge_artifact.project_id")
    errors.extend(failure_ctq_errors(data.get("failure_ctq"), challenge))
    errors.extend(evidence_errors(data.get("evidence")))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_failure_ctq.py <input.json>")
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
    print("READY: input can form one FAILURE_CTQ_DEFINED record only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
