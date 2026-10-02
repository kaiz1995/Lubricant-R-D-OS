"""Reject incomplete duty-definition input before an artifact is written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


SKILL_ROOT = Path(__file__).resolve().parents[1]
DUTY_FIELDS = ("equipment", "operating_conditions", "maintenance", "temperature", "load", "contamination", "life")


def _ensure_knowledge_retrieval_importable() -> bool:
    """Probe the shared retrieval module in both layouts (constraint_role precedent).

    Repository layout: the module lives in the pack-level ``scripts/`` tree.
    Deployed layout: the installer copies it beside this skill's scripts. If
    neither candidate holds the file the preflight still runs; retrieval is
    advisory and its absence must not block the gate.
    """
    for candidate in (SKILL_ROOT / "scripts", SKILL_ROOT.parents[1] / "scripts"):
        if (candidate / "knowledge_retrieval.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return True
    return False


_RETRIEVAL_AVAILABLE = _ensure_knowledge_retrieval_importable()

if _RETRIEVAL_AVAILABLE:
    import knowledge_retrieval  # noqa: E402


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def has_value(value: object) -> bool:
    return has_text(value) or isinstance(value, (int, float)) and not isinstance(value, bool)


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    names = ("common.schema.json", "project.schema.json", "duty.schema.json")
    return canonical if all((canonical / name).is_file() for name in names) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def project_errors(path: Path) -> tuple[list[str], dict | None]:
    try:
        schemas = schema_dir()
        common = json.loads((schemas / "common.schema.json").read_text(encoding="utf-8"))
        project = json.loads((schemas / "project.schema.json").read_text(encoding="utf-8"))
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"project_artifact cannot be read: {error}"], None
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    registry = registry.with_resource(project["$id"], Resource.from_contents(project))
    errors = [f"project_artifact: {error.message}" for error in Draft202012Validator(project, registry=registry).iter_errors(artifact)]
    if not errors and (artifact.get("stage") != "PROJECT_DEFINED" or artifact.get("status") != "ACTIVE" or artifact.get("decision") != "GO"):
        errors.append("project_artifact must be PROJECT_DEFINED, ACTIVE, and GO")
    return errors, artifact if not errors else None


def duty_errors(duty: object) -> list[str]:
    if not isinstance(duty, dict):
        return ["duty"]
    errors: list[str] = []
    for name in DUTY_FIELDS:
        item = duty.get(name)
        label = f"duty.{name}"
        if not isinstance(item, dict):
            errors.append(label)
            continue
        if not has_value(item.get("value")):
            errors.append(f"{label}.value")
        for field in ("source", "evidence_id", "statement"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") == "GAP":
            errors.append(f"{label}.status GAP requires resolution")
        elif item.get("status") not in {"OBSERVED", "ASSUMED"}:
            errors.append(f"{label}.status must be OBSERVED or ASSUMED")
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors: list[str] = []
    project_path = resolved_path(data.get("project_artifact"), input_path)
    if project_path is None:
        errors.append("project_artifact")
    else:
        project_errors_found, _ = project_errors(project_path)
        errors.extend(project_errors_found)
    if not has_text(data.get("duty_id")):
        errors.append("duty_id")
    errors.extend(duty_errors(data.get("duty")))
    return errors


def duty_query(data: object) -> str:
    """Free-text query for reuse retrieval: duty values and their statements."""
    if not isinstance(data, dict) or not isinstance(data.get("duty"), dict):
        return ""
    parts: list[str] = []
    for item in data["duty"].values():
        if not isinstance(item, dict):
            continue
        for field in ("value", "statement"):
            value = item.get(field)
            if isinstance(value, str) and value.strip() and "NOT_FOR_PHYSICAL_EXECUTION" not in value:
                parts.append(value.strip())
    return " ".join(parts)


def history_lines(data: object, input_path: Path) -> list[str]:
    """WP-11 historical hits. Empty index (the normal state) stays silent.

    Fail-open boundary: retrieval problems or an empty corpus return no lines
    and never block the preflight; a non-empty hit list is summarized.
    """
    if not _RETRIEVAL_AVAILABLE:
        return []
    query = duty_query(data)
    if not query:
        return []
    roots = knowledge_retrieval.history_roots(data.get("history_roots") if isinstance(data, dict) else None, input_path)
    roots = roots or knowledge_retrieval.history_roots_from_env()
    if not roots:
        return []
    hits = knowledge_retrieval.search_history(query, roots, top_k=knowledge_retrieval.TOP_K_DEFAULT)
    if not hits:
        return []
    lines = [f"history_hits={len(hits)} backend={knowledge_retrieval.describe_backend()}"]
    for index, hit in enumerate(hits, start=1):
        lines.append(
            f"HISTORY_HIT[{index}] score={hit['score']:.3f} artifact_type={hit['artifact_type']} "
            f"project_id={hit['project_id']} source={hit['source']} snippet={hit['snippet']}"
        )
    return lines


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_duty_definition.py <input.json>")
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
    print("READY: input can form one DUTY_DEFINED artifact only")
    for line in history_lines(data, input_path):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
