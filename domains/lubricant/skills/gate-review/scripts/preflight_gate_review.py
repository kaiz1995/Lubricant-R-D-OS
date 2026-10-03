"""Reject incomplete Gate-review requests before a VERIFIED artifact is written."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from gate_review_policy import aggregate_scope, has_gap, process_window_synthetic


ROOT = Path(__file__).resolve().parents[1]


def _ensure_naming_checker_importable() -> bool:
    """Probe the shared naming checker in both layouts (knowledge_retrieval precedent).

    Repository layout: the module lives in the pack-level ``scripts/`` tree.
    Deployed layout: the installer copies it beside this skill's scripts
    (install_domain_skill.py maps gate-review -> check_artifact_naming.py).
    If neither candidate holds the file the preflight still runs; the naming
    contract is then unenforced here, exactly like knowledge_retrieval.
    """
    for candidate in (ROOT / "scripts", ROOT.parents[1] / "scripts"):
        if (candidate / "check_artifact_naming.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return True
    return False


_NAMING_AVAILABLE = _ensure_naming_checker_importable()

if _NAMING_AVAILABLE:
    import check_artifact_naming  # noqa: E402


def workspace_naming_errors(input_path: Path) -> list[str]:
    """Enforce the canonical-name contract on the workspace holding the input.

    The input request file lives in the workspace root, so ``input_path.parent``
    is the workspace. A bare staging directory without ``project.json`` is not
    treated as a workspace (keeps ad-hoc preflight invocations working). Every
    violation here is a HOLD: a mangled artifact name is invisible to the
    stage-gate panel, so a GO must not be issued over it.
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
SCHEMAS = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json", "optimization.schema.json", "gate.schema.json", "process.schema.json")
UPSTREAM = (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"), ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"), ("experiment_design_artifact", "experiment_design.schema.json", "EXPERIMENT_DESIGNED"), ("experiment_artifact", "experiment.schema.json", "EXPERIMENT_RUNNING"), ("model_artifact", "model.schema.json", "MODEL_BUILT"), ("optimization_artifact", "optimization.schema.json", "OPTIMIZED"))
INPUT_FIELDS = {key for key, _, _ in UPSTREAM} | {"gate"}
# Defect 4 (2026-10-03): the process pair used to be structurally unreachable
# from this gate. They are OPTIONAL here (a gate may review a non-process
# project), but when submitted they are validated and their evidence_scope is
# aggregated with the rest, so a SYNTHETIC process window can no longer slip
# through on an optimization artifact's PHYSICAL label.
PROCESS_UPSTREAM = (("process_artifact", "process.schema.json", "DESIGN_SPACE_DEFINED"), ("process_window_artifact", "process.schema.json", "PROCESS_WINDOW_DEFINED"))
OPTIONAL_INPUT_FIELDS = {key for key, _, _ in PROCESS_UPSTREAM}
REQUEST_FIELDS = {"gate_id", "scope", "gate_status", "satisfied_conditions", "unsatisfied_conditions", "evidence_gaps", "risks", "reason", "evidence"}
# WP-08: the request may also carry the optional signoff record. It stays a
# record only — no authority check happens here or downstream.
OPTIONAL_REQUEST_FIELDS = {"technical_reviewer", "reviewed_at", "approver", "approved_at", "dissent"}


def schema_dir() -> Path:
    canonical = ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMAS) else ROOT / "references"


def schemas() -> tuple[dict[str, dict], Registry]:
    directory = schema_dir(); loaded = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMAS}; registry = Registry()
    for schema in loaded.values(): registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return loaded, registry


def artifact(value: object, input_path: Path, schema_name: str, label: str) -> tuple[list[str], dict | None]:
    if not isinstance(value, str) or not value.strip(): return [label], None
    try:
        loaded, registry = schemas(); item = json.loads((input_path.parent / value).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: return [f"{label} cannot be read: {error}"], None
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(loaded[schema_name], registry=registry).iter_errors(item)]
    return errors, item if not errors else None


def gate_request_errors(request: object, project_id: str, experiment_id: str, evidence_scope: str | None = None) -> list[str]:
    if not isinstance(request, dict) or not REQUEST_FIELDS <= set(request) or set(request) - REQUEST_FIELDS - OPTIONAL_REQUEST_FIELDS: return ["gate must contain only the required review fields"]
    candidate = {"schema_version": "0.1.0", "artifact_type": "gate", "project_id": project_id or "input-project", "stage": "VERIFIED", "evidence_scope": evidence_scope, "decision_question": "input", "hypothesis": "input", "uncertainty": "input", "decision_rule": "input", "result": "input", "decision": request.get("gate_status"), "next_action": "input", "experiment_reference": experiment_id or "input-experiment", **{key: value for key, value in request.items() if key != "reason"}}
    loaded, registry = schemas()
    return [f"gate: {error.message}" for error in Draft202012Validator(loaded["gate.schema.json"], registry=registry).iter_errors(candidate)]


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict): return ["input must be a JSON object"]
    errors, items = [], {}
    unexpected = set(data) - INPUT_FIELDS - OPTIONAL_INPUT_FIELDS
    missing = INPUT_FIELDS - set(data)
    if unexpected or missing:
        errors.append("input must contain only required upstream artifact paths and gate (process artifacts optional but permitted)")
    for key, schema, stage in UPSTREAM:
        item_errors, value = artifact(data.get(key), input_path, schema, key); errors.extend(item_errors); items[key] = value
        if value and value.get("stage") != stage: errors.append(f"{key} must be stage {stage}")
        if value and value.get("decision") != "GO": errors.append(f"{key} must have decision GO")
    for key, schema, stage in PROCESS_UPSTREAM:
        if key not in data: continue
        item_errors, value = artifact(data.get(key), input_path, schema, key); errors.extend(item_errors); items[key] = value
        if value and value.get("stage") != stage: errors.append(f"{key} must be stage {stage}")
        if value and value.get("decision") != "GO": errors.append(f"{key} must have decision GO")
    if ("process_artifact" in data) != ("process_window_artifact" in data):
        errors.append("process_artifact and process_window_artifact must be submitted together")
    project, challenge, failure, method, design_space, experiment_design, experiment, model, optimization = (items[key] for key, _, _ in UPSTREAM)
    process, process_window = items.get("process_artifact"), items.get("process_window_artifact")
    if process and project and process.get("project_reference") != project.get("project_id"):
        errors.append("process_artifact project link is invalid")
    if process_window and process and process_window.get("process_id") != process.get("process_id"):
        errors.append("process_window_artifact process link is invalid")
    present = [value for value in (project, challenge, failure, method, design_space, experiment_design, experiment, model, optimization) if value]
    scopes = {value.get("evidence_scope") for value in (method, experiment_design, experiment, model, optimization) if value is not None}
    if scopes - {"SYNTHETIC", "PHYSICAL"} or len(scopes) != 1:
        errors.append("test_method, experiment_design, experiment, model, and optimization evidence_scope values must exist and match")
    if project and project.get("status") != "ACTIVE": errors.append("project_artifact must have status ACTIVE")
    if len(present) == 9 and len({value.get("project_id") for value in present}) != 1: errors.append("all upstream artifact project_id values must match")
    if failure and challenge and failure.get("challenge_reference") != challenge.get("challenge_id"): errors.append("failure_ctq_artifact challenge link is invalid")
    if method and failure and (method.get("target_failure_reference") != failure.get("failure_id") or method.get("qualification_status") != "QUALIFIED"): errors.append("test_method_artifact must be linked and qualified")
    if design_space and method and method.get("method_id") not in (design_space.get("qualified_test_method_references") or []): errors.append("design_space_artifact method link is invalid")
    if experiment_design and design_space and experiment_design.get("design_space_reference") != design_space.get("design_space_id"): errors.append("experiment_design_artifact design-space link is invalid")
    if experiment and experiment_design and experiment.get("experiment_design_reference") != experiment_design.get("experiment_design_id"): errors.append("experiment_artifact design link is invalid")
    if model and experiment and model.get("experiment_reference") != experiment.get("experiment_id"): errors.append("model_artifact experiment link is invalid")
    if optimization and model and optimization.get("model_reference") != model.get("model_id"): errors.append("optimization_artifact model link is invalid")
    # Defect 4 fix: the weakest declared scope across every submitted upstream
    # governs the disposition, so a SYNTHETIC process window cannot inherit
    # PHYSICAL from the optimization artifact.
    scope_values = [value.get("evidence_scope") for value in (method, experiment_design, experiment, model, optimization) if value is not None]
    scope_values += [value.get("evidence_scope") for value in (process, process_window) if value is not None]
    effective_scope = aggregate_scope(scope_values)
    if process is not None and process_window is not None:
        nested = process_window.get("process_window") if isinstance(process_window.get("process_window"), dict) else {}
        if aggregate_scope(scope_values) == "SYNTHETIC" or process_window_synthetic(nested) or process_window_synthetic(process_window):
            errors.append("SYNTHETIC process evidence_scope permits Gate HOLD workflow validation only; a validated window declared SYNTHETIC cannot authorize a state transition")
    request = data.get("gate"); errors.extend(gate_request_errors(request, project.get("project_id", "") if project else "", experiment.get("experiment_id") if experiment else "", effective_scope))
    if not isinstance(request, dict): return errors
    status = request.get("gate_status")
    if effective_scope == "SYNTHETIC" and status != "HOLD": errors.append("SYNTHETIC evidence_scope permits Gate HOLD workflow validation only")
    if status == "GO" and has_gap(request): errors.append("GO cannot use GAP evidence")
    if status in {"PIVOT", "KILL", "FREEZE"} and (not isinstance(request.get("reason"), str) or not request["reason"].strip() or has_gap(request)): errors.append(f"{status} requires explicit reason and evidence without GAP")
    return errors


def main() -> int:
    if len(sys.argv) != 2: print("Usage: python preflight_gate_review.py <input.json>"); return 1
    path = Path(sys.argv[1]).resolve()
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, path)
    errors.extend(workspace_naming_errors(path))
    if errors: print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    print("READY: input can form one VERIFIED Gate artifact only"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
