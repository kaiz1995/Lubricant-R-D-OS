"""Reject incomplete DOE-design requests before any EXPERIMENT_DESIGNED artifact is built."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from doe_design_policy import (
    COMBINED_FAMILIES,
    FACTOR_FAMILIES,
    MIXTURE_FAMILIES,
    SUPPORTED_FAMILIES,
    has_gap,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]


def _ensure_constraint_role_importable() -> None:
    """Make the shared role resolver importable in both layouts.

    Repository layout: the module lives in the pack-level ``scripts/`` tree.
    Deployed layout: the installer copies it beside the skill's own scripts, so
    it is already on the script directory's path. Probe both candidates and pin
    the first that actually contains the file; never inline a second copy — the
    plan forbids recreating the double-list drift of the role mapping.
    """
    for candidate in (SKILL_ROOT / "scripts", SKILL_ROOT.parents[1] / "scripts"):
        if (candidate / "constraint_role.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return
    raise ImportError(
        "constraint_role.py not found beside the skill scripts or in the pack scripts/ directory"
    )


_ensure_constraint_role_importable()

from constraint_role import CONSTRAINT_ROLES, ConstraintRoleError, resolve_constraint_role  # noqa: E402


SCHEMA_NAMES = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json")
INPUT_FIELDS = {"project_artifact", "challenge_artifact", "failure_ctq_artifact", "test_method_artifact", "design_space_artifact", "experiment_design"}
# mixture_total is only meaningful for the mixture channels, so it is optional at
# the envelope level and required/forbidden per family by the bridge below.
# resource_envelope (WP-04b) is the same: optional in the request shape, required on
# the factor channels and forbidden on the mixture-only channels.
REQUEST_REQUIRED_FIELDS = {"experiment_design_id", "factor_references", "design", "run_plan", "responses", "guardrails", "expected_information_value", "evidence"}
REQUEST_OPTIONAL_FIELDS = {"mixture_total", "resource_envelope"}
REQUEST_ALLOWED_FIELDS = REQUEST_REQUIRED_FIELDS | REQUEST_OPTIONAL_FIELDS
MEASUREMENT_FIELDS = {"value", "unit", "source", "method_version", "material_batch", "formula_version"}
RESOURCE_ENVELOPE_FIELDS = ("bench_slots", "lot_capacity", "cycle_days", "cost_cap", "external_test_lead_time")

# WP-04a bridge: which constraint role each channel routes where. MIXTURE_CLOSED
# variables feed the engine's ``components`` (mixture_total applies); INDEPENDENT
# variables feed ``factors`` (no mixture_total). MIXTURE_PROCESS carries both.
CHANNEL_MIXTURE = "MIXTURE"
CHANNEL_FACTOR = "FACTOR"
CHANNEL_BOTH = "BOTH"
FAMILY_CHANNEL = {
    **{family: CHANNEL_MIXTURE for family in MIXTURE_FAMILIES},
    **{family: CHANNEL_FACTOR for family in FACTOR_FAMILIES},
    **{family: CHANNEL_BOTH for family in COMBINED_FAMILIES},
}


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def load_schemas() -> tuple[dict[str, dict], Registry]:
    schemas = schema_dir()
    loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return loaded, registry


def schema_artifact(path: Path, name: str, label: str) -> tuple[list[str], dict | None]:
    try:
        loaded, registry = load_schemas()
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(loaded[name], registry=registry).iter_errors(artifact)]
    return errors, artifact if not errors else None


def measurement_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, dict) or set(value) != MEASUREMENT_FIELDS:
        return [label]
    errors = []
    number = value.get("value")
    if not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(number):
        errors.append(f"{label}.value")
    for field in MEASUREMENT_FIELDS - {"value"}:
        if not has_text(value.get(field)):
            errors.append(f"{label}.{field}")
    return errors


def resource_envelope_errors(value: object) -> list[str]:
    """Structural + semantic checks for the WP-04b resource envelope."""
    label = "experiment_design.resource_envelope"
    if not isinstance(value, dict) or set(value) != set(RESOURCE_ENVELOPE_FIELDS):
        return [f"{label} must contain exactly {list(RESOURCE_ENVELOPE_FIELDS)}"]
    errors = []
    for field in RESOURCE_ENVELOPE_FIELDS:
        number = value.get(field)
        if not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(number):
            errors.append(f"{label}.{field}")
    if errors:
        return errors
    if value["bench_slots"] < 1:
        errors.append(f"{label}.bench_slots must be >= 1, got {value['bench_slots']}")
    if value["lot_capacity"] < 1:
        errors.append(f"{label}.lot_capacity must be >= 1, got {value['lot_capacity']}")
    if value["cycle_days"] <= 0:
        errors.append(f"{label}.cycle_days must be > 0, got {value['cycle_days']}")
    if value["cost_cap"] < 0:
        errors.append(f"{label}.cost_cap must be >= 0, got {value['cost_cap']}")
    if value["external_test_lead_time"] < 0:
        errors.append(f"{label}.external_test_lead_time must be >= 0, got {value['external_test_lead_time']}")
    return errors


def request_schema_errors(request: object, project_id: str, evidence_scope: str | None = None) -> list[str]:
    if not isinstance(request, dict) or not REQUEST_REQUIRED_FIELDS <= set(request) or not set(request) <= REQUEST_ALLOWED_FIELDS:
        return ["experiment_design must contain only the required request fields"]
    candidate = {
        "schema_version": "0.1.0", "artifact_type": "experiment_design", "project_id": project_id or "input-project", "stage": "EXPERIMENT_DESIGNED", "evidence_scope": evidence_scope,
        "decision_question": "input", "hypothesis": "input", "uncertainty": "input", "decision_rule": "input", "result": "input", "decision": "GO", "next_action": "input",
        "design_space_reference": "input-design-space", "test_method_references": ["input-method"], **request,
    }
    try:
        loaded, registry = load_schemas()
    except (OSError, json.JSONDecodeError) as error:
        return [f"experiment_design schemas cannot be read: {error}"]
    return [f"experiment_design: {error.message}" for error in Draft202012Validator(loaded["experiment_design.schema.json"], registry=registry).iter_errors(candidate)]


def resolved_variable_roles(design_space: dict | None) -> tuple[dict[str, str], list[str]]:
    """Resolve every design-space variable to its WP-01 constraint role.

    ``roles`` maps ``variable_id`` to the role returned by the shared
    ``constraint_role`` module (declared value when consistent, otherwise the
    ``variable_type``-derived value). A declared ``constraint_role`` that
    contradicts the derived role is reported, never silently coerced — exactly the
    Stage 4 formulation-preflight rule, because this is the same implementation.
    """
    roles: dict[str, str] = {}
    errors: list[str] = []
    for item in design_space.get("variables", []) if isinstance(design_space, dict) else []:
        if not isinstance(item, dict):
            continue
        variable_id = item.get("variable_id")
        try:
            roles[variable_id] = resolve_constraint_role(item.get("variable_type"), item.get("constraint_role"))
        except ConstraintRoleError as error:
            errors.append(f"design_space_artifact.variables[{variable_id}].constraint_role: {error}")
    return roles, errors


def request_errors(request: object, design_space: dict | None, failure: dict | None, method: dict | None, project_id: str) -> list[str]:
    errors = request_schema_errors(request, project_id, method.get("evidence_scope") if method else None)
    if not isinstance(request, dict):
        return errors
    design = request.get("design") if isinstance(request.get("design"), dict) else {}
    family = design.get("family")
    channel = FAMILY_CHANNEL.get(family)
    if channel is None:
        errors.append(f"experiment_design.design.family is not supported for GO; supported families are {list(SUPPORTED_FAMILIES)}")
    if has_gap(request):
        errors.append("experiment_design.evidence contains GAP; current input is insufficient")
    variables = {item.get("variable_id"): item for item in design_space.get("variables", []) if isinstance(item, dict)} if design_space else {}
    roles, role_errors = resolved_variable_roles(design_space)
    errors.extend(role_errors)
    # WP-04a bridge: MIXTURE_CLOSED variables belong in the engine's ``components``
    # (mixture_total applies); INDEPENDENT variables belong in ``factors``. A
    # variable placed on the wrong side of the declared family's channel is
    # rejected by name instead of being silently re-routed.
    mixture_channel = channel in (CHANNEL_MIXTURE, CHANNEL_BOTH)
    factor_channel = channel in (CHANNEL_FACTOR, CHANNEL_BOTH)
    factors = request.get("factor_references")
    factor_list = factors if isinstance(factors, list) else []
    if isinstance(factors, list) and len(factors) < 2:
        errors.append("experiment_design.factor_references requires at least two factors")
    units, lower_sum, upper_sum, mixture_factors = set(), 0.0, 0.0, 0
    for factor in factor_list:
        variable = variables.get(factor) if isinstance(factor, str) else None
        if variable is None:
            errors.append(f"experiment_design.factor_references: {factor} does not exist in design_space_artifact")
            continue
        role = roles.get(factor)
        if channel is not None and role in CONSTRAINT_ROLES:
            if role == "MIXTURE_CLOSED" and not mixture_channel:
                errors.append(f"experiment_design.factor_references: {factor} resolves to MIXTURE_CLOSED and belongs in DOE components, but family {family} routes INDEPENDENT variables into DOE factors")
                continue
            if role == "INDEPENDENT" and not factor_channel:
                errors.append(f"experiment_design.factor_references: {factor} resolves to INDEPENDENT and belongs in DOE factors, but family {family} routes MIXTURE_CLOSED variables into DOE components")
                continue
        label = f"design_space_artifact.variables[{factor}]"
        lower, upper = variable.get("lower_bound"), variable.get("upper_bound")
        errors.extend(measurement_errors(lower, f"{label}.lower_bound"))
        errors.extend(measurement_errors(upper, f"{label}.upper_bound"))
        if measurement_errors(lower, "") or measurement_errors(upper, ""):
            continue
        if lower["value"] > upper["value"]:
            errors.append(f"{label}.lower_bound.value must be <= upper_bound.value")
        if role == "MIXTURE_CLOSED" or channel is None:
            units.update((lower["unit"], upper["unit"]))
            lower_sum += lower["value"]
            upper_sum += upper["value"]
            mixture_factors += 1
    total = request.get("mixture_total")
    if mixture_channel:
        if len(units) > 1:
            errors.append("selected factor bounds must use the same unit")
        errors.extend(measurement_errors(total, "experiment_design.mixture_total"))
        if not measurement_errors(total, ""):
            if total["value"] <= 0:
                errors.append("experiment_design.mixture_total.value must be > 0")
            if units and total["unit"] not in units:
                errors.append("experiment_design.mixture_total.unit must equal selected factor bounds")
            if mixture_factors and not (lower_sum <= total["value"] <= upper_sum):
                errors.append("experiment_design.mixture_total must be within the sum of selected factor bounds")
    elif channel is not None and total is not None:
        errors.append("experiment_design.mixture_total must be absent for a factor-only family")
    # WP-04b: the resource envelope is required exactly where the engine consumes it
    # (the factor / process channels) and forbidden on the mixture-only channels.
    envelope = request.get("resource_envelope")
    if channel == CHANNEL_MIXTURE:
        if envelope is not None:
            errors.append("experiment_design.resource_envelope must be absent for a mixture family")
    elif channel in (CHANNEL_FACTOR, CHANNEL_BOTH):
        if envelope is None:
            errors.append(
                f"experiment_design.resource_envelope is required for family {family}: "
                "the next round is bounded by bench_slots, lot_capacity and cycle_days")
        else:
            errors.extend(resource_envelope_errors(envelope))
    ctqs = {item.get("ctq_id"): item for item in failure.get("ctqs", []) if isinstance(item, dict)} if failure else {}
    allowed_ctqs = set(design_space.get("ctq_references", [])) if design_space else set()
    method_id = method.get("method_id") if method else None
    for response in request.get("responses", []) if isinstance(request.get("responses"), list) else []:
        if not isinstance(response, dict):
            continue
        ctq = response.get("ctq_reference")
        if ctq not in ctqs or ctq not in allowed_ctqs:
            errors.append(f"experiment_design.responses: {ctq} must exist in failure_ctq and design_space")
        if response.get("test_method_reference") != method_id:
            errors.append("experiment_design.responses.test_method_reference must equal the supplied qualified method_id")
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors, artifacts = [], {}
    if set(data) != INPUT_FIELDS:
        errors.append("input must contain only required upstream artifact paths and experiment_design")
    requirements = (
        ("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"),
        ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"),
        ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"),
    )
    for key, schema, stage in requirements:
        path = resolved_path(data.get(key), input_path)
        if path is None:
            errors.append(key)
            artifacts[key] = None
            continue
        item_errors, artifact = schema_artifact(path, schema, key)
        errors.extend(item_errors)
        artifacts[key] = artifact
        if artifact is not None and artifact.get("stage") != stage:
            errors.append(f"{key} must be stage {stage}")
        if artifact is not None and artifact.get("decision") != "GO":
            errors.append(f"{key} must have decision GO")
    project, challenge, failure, method, design_space = (artifacts[key] for key, _, _ in requirements)
    present = [item for item in (project, challenge, failure, method, design_space) if item is not None]
    if method is not None and method.get("evidence_scope") not in {"SYNTHETIC", "PHYSICAL"}:
        errors.append("test_method_artifact must declare evidence_scope")
    if project is not None and project.get("status") != "ACTIVE":
        errors.append("project_artifact must have status ACTIVE")
    if len(present) == 5 and len({item.get("project_id") for item in present}) != 1:
        errors.append("all upstream artifact project_id values must match")
    if challenge is not None and failure is not None and failure.get("challenge_reference") != challenge.get("challenge_id"):
        errors.append("failure_ctq_artifact.challenge_reference must equal challenge_artifact.challenge_id")
    if failure is not None and method is not None and method.get("target_failure_reference") != failure.get("failure_id"):
        errors.append("test_method_artifact.target_failure_reference must equal failure_ctq_artifact.failure_id")
    if method is not None and method.get("qualification_status") != "QUALIFIED":
        errors.append("test_method_artifact must have qualification_status QUALIFIED")
    if method is not None and not ({"D", "P"} & set(method.get("role", []))):
        errors.append("test_method_artifact must have role D or P")
    if design_space is not None and method is not None:
        # Defect 1 fix: membership, not single-element equality, so a multi-CTQ
        # design space can declare one qualified method per CTQ.
        if method.get("method_id") not in (design_space.get("qualified_test_method_references") or []):
            errors.append("design_space_artifact qualified method references must contain the supplied method_id")
        ctqs = {item.get("ctq_id"): item for item in failure.get("ctqs", []) if isinstance(item, dict)} if failure else {}
        for ctq_id in design_space.get("ctq_references", []):
            ctq = ctqs.get(ctq_id)
            if ctq is None:
                errors.append(f"design_space_artifact.ctq_references: {ctq_id} does not exist in failure_ctq_artifact")
            elif method["method_id"] not in ctq.get("test_references", []) and method["method_id"] not in failure.get("test_chain", []):
                errors.append(f"design_space_artifact.ctq_references: {ctq_id} is not linked to the supplied qualified method")
    errors.extend(request_errors(data.get("experiment_design"), design_space, failure, method, project.get("project_id", "") if project else ""))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_doe_design.py <input.json>")
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
    print("READY: input can form one EXPERIMENT_DESIGNED request only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
