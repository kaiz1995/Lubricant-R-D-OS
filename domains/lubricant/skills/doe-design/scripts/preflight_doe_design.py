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
    GREASE_PROJECT_TYPE,
    GREASE_SMALL_BATCH_MAX,
    GREASE_SMALL_BATCH_MIN,
    MIXTURE_FAMILIES,
    SEQUENTIAL_FAMILIES,
    SUPPORTED_FAMILIES,
    canonical_family,
    has_gap,
    is_sequential_family,
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

from constraint_role import (  # noqa: E402
    CONSTRAINT_ROLES,
    ConstraintRoleError,
    resolve_variable_constraint_role,
)


SCHEMA_NAMES = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json")
INPUT_FIELDS = {"project_artifact", "challenge_artifact", "failure_ctq_artifact", "test_method_artifact", "design_space_artifact", "experiment_design"}
# Grease step 8: the registered bench artifact is an OPTIONAL extra upstream path.
# It is optional on purpose: when it is absent the design keeps the hand-filled
# resource_envelope.bench_slots path it always had, so every pre-existing oil-route
# input is unaffected. When it IS supplied the bench's derived capacity becomes the
# authority for the round size and the design size.
OPTIONAL_INPUT_FIELDS = {"bench_artifact"}
REQUIRED_INPUT_FIELDS = INPUT_FIELDS
INPUT_FIELDS = REQUIRED_INPUT_FIELDS | OPTIONAL_INPUT_FIELDS
# The grease route's own input shape: CHALLENGES_DEFINED is on no type_route, so that
# route may legally omit the challenge artifact and records the Challenge Map link as
# UNROUTED:<project_id> on the failure record instead. Only the shape differs; every
# other route keeps validating against REQUIRED_INPUT_FIELDS verbatim.
CHALLENGE_KEY = "challenge_artifact"
GREASE_NO_CHALLENGE_FIELDS = REQUIRED_INPUT_FIELDS - {CHALLENGE_KEY}
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
    **{family: CHANNEL_FACTOR for family in SEQUENTIAL_FAMILIES},
    **{family: CHANNEL_BOTH for family in COMBINED_FAMILIES},
}


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_grease_route(project_type: object) -> bool:
    """True when the supplied route marker carries the grease rules.

    An absent or unknown project type is NOT the grease route, so every caller that
    cannot determine the route keeps exactly the pre-change behaviour.
    """
    return project_type == GREASE_PROJECT_TYPE


def challenge_note(project_id: object) -> str:
    """The one audible line a grease run without a challenge artifact prints."""
    return "NOTE: " + unrouted_statement(project_id)


def unrouted_statement(project_id: object) -> str:
    """The recorded-gap sentence. The preflight prints it, the artifact's evidence carries it."""
    return (
        f"challenge_artifact not supplied on the {GREASE_PROJECT_TYPE} route "
        f"(CHALLENGES_DEFINED is on no type_route); the Challenge Map link is recorded as "
        f"{UNROUTED_PREFIX}{project_id}"
    )


def unrouted_evidence(project_id: object) -> dict:
    """The ASSUMED evidence item that records the missing challenge as a route property.

    Never GAP: several preflights refuse a GAP-status item outright, and this is not an
    unresolved gap in the record - it is a recorded property of the route.
    """
    return {
        "evidence_id": f"EV-UNROUTED-{project_id}",
        "statement": unrouted_statement(project_id),
        "source": ROUTE_CONTRACT_SOURCE,
        "status": "ASSUMED",
    }


def grease_without_challenge(data: object, project: object) -> bool:
    """True for the grease route's legal no-challenge shape, and nothing else."""
    return (
        isinstance(data, dict)
        and CHALLENGE_KEY not in data
        and is_grease_route(project.get("project_type") if isinstance(project, dict) else None)
    )


UNROUTED_PREFIX = "UNROUTED:"
# Provenance of the recorded gap: the route contract is what says the stage is on no
# type_route, so it is what the recorded evidence cites.
ROUTE_CONTRACT_SOURCE = "contracts/state-machine.json"


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


def bench_capacity_errors(bench: object, label: str = "bench_artifact") -> list[str]:
    """The bench artifact must carry the derived capacity this stage consumes.

    Only the field this skill actually reads is checked here: the bench artifact's
    full contract (availability windows, cycle time, cost, provenance, and the
    derived-vs-declared assertion) belongs to ``bench-registration``, which owns
    ``bench.schema.json``. Re-validating the whole object here would take a second
    cross-skill schema dependency and duplicate a rule that already has one owner.

    ``available_bench_slots`` is DERIVED by bench-registration
    (``bench_policy.available_bench_slots``); this preflight never recomputes it and
    never accepts a hand-set substitute. What it requires is that the field is
    present as an integer >= 0, because that is the number the round is bounded by.
    """
    if not isinstance(bench, dict):
        return [f"{label} must be a JSON object"]
    capacity = bench.get("available_bench_slots")
    if isinstance(capacity, bool) or not isinstance(capacity, int):
        return [
            f"{label}.available_bench_slots must be the integer derived by bench-registration "
            "(it is never hand-set)"]
    if capacity < 0:
        return [f"{label}.available_bench_slots must be >= 0, got {capacity}"]
    if bench.get("artifact_type") != "bench":
        return [f"{label}.artifact_type must be bench"]
    return []


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

    Grease step 8 (purely additive): the material-side ``role`` is passed through
    too, so a design space whose variable ranges over an in-situ reaction product
    (grease soap: ``role: REACTION_PRODUCT``) resolves to INDEPENDENT instead of
    being rejected against its FORMULATION_VARIABLE type. Omitting ``role`` — every
    oil-route design space — returns exactly the pre-extension result, because
    ``resolve_variable_constraint_role`` falls back to ``resolve_constraint_role``
    when ``material_role`` is None.
    """
    roles: dict[str, str] = {}
    errors: list[str] = []
    for item in design_space.get("variables", []) if isinstance(design_space, dict) else []:
        if not isinstance(item, dict):
            continue
        variable_id = item.get("variable_id")
        try:
            roles[variable_id] = resolve_variable_constraint_role(
                item.get("variable_type"), item.get("constraint_role"), item.get("role"))
        except ConstraintRoleError as error:
            errors.append(f"design_space_artifact.variables[{variable_id}].constraint_role: {error}")
    return roles, errors


def request_errors(request: object, design_space: dict | None, failure: dict | None, method: dict | None, project_id: str) -> list[str]:
    errors = request_schema_errors(request, project_id, method.get("evidence_scope") if method else None)
    if not isinstance(request, dict):
        return errors
    design = request.get("design") if isinstance(request.get("design"), dict) else {}
    family = design.get("family")
    # Grease step 8: the honest sequential name is an alias of the legacy one, so it
    # routes through the same channel and every check below sees the canonical value.
    channel = FAMILY_CHANNEL.get(canonical_family(family))
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


def bench_capacity_errors(bench: object, label: str = "bench_artifact") -> list[str]:
    """The bench artifact must carry a derived capacity, and that capacity is the authority.

    ``available_bench_slots`` is DERIVED by bench-registration
    (``bench_policy.available_bench_slots``) and asserted by its validator; this
    preflight never recomputes it and never accepts a hand-set value as a
    substitute. What it checks is the field the DOE round actually consumes: an
    integer >= 0. A bench that does not carry it cannot bound the design.
    """
    if not isinstance(bench, dict):
        return [f"{label} must be a JSON object"]
    capacity = bench.get("available_bench_slots")
    if isinstance(capacity, bool) or not isinstance(capacity, int):
        return [
            f"{label}.available_bench_slots must be the integer derived by bench-registration "
            "(it is never hand-set)"]
    if capacity < 0:
        return [f"{label}.available_bench_slots must be >= 0, got {capacity}"]
    return []


def grease_request_errors(request: object, bench: object, project_type: str | None) -> list[str]:
    """Grease-route rules (step 8): small sequential round, and bench capacity as the cap.

    Returns [] for every other route, so the six oil routes keep their existing
    behaviour byte for byte. Two rules are enforced here at the skill layer:

    * The declared round size (``run_plan.target_count``) must not exceed the
      small-batch window's top -- that is the route's DEFAULT design policy, and one
      big fixed design is what the plan rejects (a single 20-point design is about
      7 months of bench time at the registered capacity). The window's floor is a
      preference, not a refusal: the registered bench may legitimately pull a round
      below it, which is exactly the paired round the plan asks for when the bench
      is tight.
    * The design size must not exceed the bench's available positions. That is the
      step-8 release criterion, and it is read from the bench artifact when one is
      supplied. Without a bench artifact the hand-filled envelope stays the only
      declaration (the pre-existing path), and the capacity rule has nothing to
      check against.
    """
    if project_type != GREASE_PROJECT_TYPE or not isinstance(request, dict):
        return []
    errors: list[str] = []
    design = request.get("design") if isinstance(request.get("design"), dict) else {}
    family = design.get("family")
    run_plan = request.get("run_plan") if isinstance(request.get("run_plan"), dict) else {}
    target_count = run_plan.get("target_count")
    numeric_target = isinstance(target_count, int) and not isinstance(target_count, bool)
    if is_sequential_family(family) and numeric_target and target_count > GREASE_SMALL_BATCH_MAX:
        errors.append(
            f"experiment_design.run_plan.target_count must not exceed {GREASE_SMALL_BATCH_MAX} for a {family} "
            "round on the grease route: the route defaults to small sequential rounds of "
            f"{GREASE_SMALL_BATCH_MIN}-{GREASE_SMALL_BATCH_MAX} samples per round, not one big fixed design")
    if bench is None:
        return errors
    capacity = bench.get("available_bench_slots") if isinstance(bench, dict) else None
    if not isinstance(capacity, int) or isinstance(capacity, bool):
        return errors
    envelope = request.get("resource_envelope") if isinstance(request.get("resource_envelope"), dict) else {}
    declared = envelope.get("bench_slots")
    if isinstance(declared, int) and not isinstance(declared, bool) and declared != capacity:
        errors.append(
            f"experiment_design.resource_envelope.bench_slots={declared} contradicts the supplied bench "
            f"artifact's derived available_bench_slots={capacity}: on the grease route the registered bench "
            "schedule is the authority and the hand-filled slot count must equal its derived capacity")
    if numeric_target and target_count > capacity:
        errors.append(
            f"experiment_design.run_plan.target_count={target_count} exceeds the bench's available positions "
            f"{capacity} (bench_artifact.available_bench_slots): the design size must not exceed the bench capacity")
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors, artifacts = [], {}
    requirements = (
        ("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"),
        ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"), ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"),
        ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"),
    )
    # The charter is read BEFORE the key-set verdict: whether the challenge key may be
    # absent at all is a property of the route (CHALLENGES_DEFINED is on no type_route).
    # Any other input shape, and a grease shape whose charter is not the grease route,
    # gets the pre-existing verdict word for word.
    project_path = resolved_path(data.get("project_artifact"), input_path)
    charter = None
    if project_path is not None and project_path.is_file():
        try:
            charter = json.loads(project_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            charter = None
    grease = is_grease_route(charter.get("project_type") if isinstance(charter, dict) else None)
    no_challenge_shape = CHALLENGE_KEY not in set(data)
    key_shape_ok = (
        GREASE_NO_CHALLENGE_FIELDS <= set(data) <= INPUT_FIELDS - {CHALLENGE_KEY}
        if no_challenge_shape and grease
        else REQUIRED_INPUT_FIELDS <= set(data) <= INPUT_FIELDS
    )
    if not key_shape_ok:
        errors.append("input must contain only required upstream artifact paths and experiment_design")
    for key, schema, stage in requirements:
        path = resolved_path(data.get(key), input_path)
        if path is None:
            # The grease route's legal no-challenge state; the link lives on the failure
            # record as UNROUTED:<project_id> instead of being consumable here.
            if key != CHALLENGE_KEY or not grease:
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
    # Grease step 8: the optional bench artifact. Only the derived capacity this
    # stage consumes is read here; the object's own contract is owned by
    # bench-registration. When absent, nothing changes for any route.
    bench = None
    bench_path = resolved_path(data.get("bench_artifact"), input_path)
    if data.get("bench_artifact") is not None and bench_path is None:
        errors.append("bench_artifact")
    elif bench_path is not None:
        try:
            bench = json.loads(bench_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"bench_artifact cannot be read: {error}")
        else:
            errors.extend(bench_capacity_errors(bench))
    project, challenge, failure, method, design_space = (artifacts[key] for key, _, _ in requirements)
    if method is not None and method.get("evidence_scope") not in {"SYNTHETIC", "PHYSICAL"}:
        errors.append("test_method_artifact must declare evidence_scope")
    if project is not None and project.get("status") != "ACTIVE":
        errors.append("project_artifact must have status ACTIVE")
    if challenge is not None:
        present = [item for item in (project, challenge, failure, method, design_space) if item is not None]
        if len(present) == 5 and len({item.get("project_id") for item in present}) != 1:
            errors.append("all upstream artifact project_id values must match")
    elif grease:
        # The no-challenge shape's own uniformity rule, over the four artifacts that
        # exist. Unreachable on any route that requires a challenge.
        present = [item for item in (project, failure, method, design_space) if item is not None]
        if len(present) == 4 and len({item.get("project_id") for item in present}) != 1:
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
    errors.extend(grease_request_errors(
        data.get("experiment_design"), bench, project.get("project_type") if project else None))
    return errors


def route_notes(data: object, input_path: Path) -> list[str]:
    """The audible NOTE for the grease route's recorded CHALLENGES_DEFINED gap.

    Empty on every other shape: an oil request, and a grease request that supplied a
    challenge artifact, print exactly what they printed before.
    """
    if not isinstance(data, dict):
        return []
    project_path = resolved_path(data.get("project_artifact"), input_path)
    if project_path is None or not project_path.is_file():
        return []
    try:
        project = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not is_grease_route(project.get("project_type") if isinstance(project, dict) else None):
        return []
    if resolved_path(data.get("challenge_artifact"), input_path) is not None:
        return []
    return [challenge_note(project.get("project_id"))]


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
    for note in route_notes(data, path):
        print(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
