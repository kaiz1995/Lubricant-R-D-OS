"""Reject incomplete design-space input before an artifact is built.

The PRECISION_GREASE_DEV route (outer-loop step 6) carries four extra mandatory
elements, enforced here in the POLICY LAYER rather than in the shared contract so
the six oil routes keep their current behaviour exactly:

  * every material-bearing variable must reference a ``material`` object and the
    referenced ``material_id`` must resolve to a readable material record - a bare
    name string carries no supplier, lot, chemistry, or property list;
  * ``baseline_process_reference`` is required, because comparing formulae across
    a changed process is invalid;
  * every variable must declare its material-side ``role``;
  * the in-situ reaction semantics: grease soap is generated during saponification,
    so a thickener percentage is a PRODUCT of the batch, and a variable over an
    in-situ feedstock may not be declared as a charged input.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from design_space_policy import (
    CONSTRAINT_KINDS,
    IN_SITU_PRODUCT_MATERIAL_CATEGORIES,
    INPUT_MATERIAL,
    MATERIAL_BEARING_VARIABLE_TYPES,
    MATERIAL_ROLES,
    REACTION_PRODUCT,
    derive_material_role,
    effective_route_is_grease,
    feasibility_region_errors,
    grease_notes,
    has_gap,
    has_text,
    is_grease_route,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]

# The Challenge Map link of a route that carries no CHALLENGES_DEFINED step. The route
# marker (the charter's project_type) is the authority: a design space that merely uses
# grease-shaped fields is not evidence that the stage is off the route, and gating on the
# marker is what keeps every non-grease request byte-identical to what it was.
UNROUTED_PREFIX = "UNROUTED:"
# Provenance of the recorded gap: the route contract is what says the stage is on no
# type_route, so it is what the recorded evidence cites.
ROUTE_CONTRACT_SOURCE = "contracts/state-machine.json"


def unrouted_statement(project_id: object) -> str:
    """The recorded-gap sentence. The preflight prints it, the artifact's evidence carries it."""
    return (
        "challenge_artifact not supplied on the PRECISION_GREASE_DEV route "
        f"(CHALLENGES_DEFINED is on no type_route); the Challenge Map link is recorded as "
        f"{UNROUTED_PREFIX}{project_id}"
    )


def challenge_note(project_id: object) -> str:
    """The one audible line a grease run without a challenge artifact prints."""
    return "NOTE: " + unrouted_statement(project_id)


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
    """True for the grease route's legal no-challenge shape, and nothing else.

    Strictly gated: a non-grease charter, or a grease request that did supply a challenge
    artifact, returns False and every caller keeps the output it had.
    """
    return (
        isinstance(data, dict)
        and CHALLENGE_KEY not in data
        and is_grease_route(project.get("project_type") if isinstance(project, dict) else None)
    )


def _ensure_constraint_role_importable() -> None:
    """Make the shared role resolver importable in both layouts.

    Repository layout: the module lives in the pack-level ``scripts/`` tree.
    Deployed layout: the installer copies it beside the skill's own scripts, so
    it is already on the script directory's path. Probe both candidates and pin
    the first that actually contains the file; never inline a second copy.
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
    ConstraintRoleError,
    describe_constraint_role,
    describe_variable_constraint_role,
    resolve_variable_constraint_role,
)


SCHEMA_NAMES = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json")
MEASUREMENT_FIELDS = ("value", "unit", "source", "method_version", "material_batch", "formula_version")
VARIABLE_REQUIRED_FIELDS = {"variable_id", "variable_type", "lower_bound", "upper_bound", "constraint_rationale"}
VARIABLE_OPTIONAL_FIELDS = {"constraint_role", "material_reference", "role"}
VARIABLE_ALLOWED_FIELDS = VARIABLE_REQUIRED_FIELDS | VARIABLE_OPTIONAL_FIELDS
REQUIRED_INPUT_FIELDS = {"project_artifact", "challenge_artifact", "failure_ctq_artifact", "test_method_artifact", "design_space"}
# Additive: material records may be supplied beside the input instead of being
# scanned out of the workspace. Optional for every route, so the six oil routes
# keep their exact input shape.
OPTIONAL_INPUT_FIELDS = {"material_artifacts"}
INPUT_FIELDS = REQUIRED_INPUT_FIELDS | OPTIONAL_INPUT_FIELDS
# The grease route's own input shape: CHALLENGES_DEFINED is on no type_route, so that
# route may legally omit the challenge artifact and records the Challenge Map link as
# UNROUTED:<project_id> instead. This constant is the only shape difference; the six oil
# routes keep validating against REQUIRED_INPUT_FIELDS verbatim.
CHALLENGE_KEY = "challenge_artifact"
GREASE_NO_CHALLENGE_FIELDS = REQUIRED_INPUT_FIELDS - {CHALLENGE_KEY}
VARIABLE_TYPES = {"MATERIAL_FAMILY", "FORMULATION_VARIABLE", "PROCESS_VARIABLE"}
DESIGN_SPACE_REQUIRED_FIELDS = {"design_space_id", "scope", "variables", "ctq_references", "qualified_test_method_references", "constraints", "evidence"}
DESIGN_SPACE_OPTIONAL_FIELDS = {"process_reference", "baseline_process_reference", "feasibility_regions"}


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


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


def material_paths(data: dict, input_path: Path) -> list[Path]:
    """Every material record reachable for this run.

    Explicit ``material_artifacts`` entries win; the workspace holding the input
    is also scanned for the canonical names ``material.json`` and
    ``material-<id>.json``. A material the caller did not supply is simply not
    resolvable - the policy reports it and never invents one.
    """
    paths: list[Path] = []
    declared = data.get("material_artifacts")
    if isinstance(declared, str):
        declared = [declared]
    for value in declared if isinstance(declared, list) else []:
        path = resolved_path(value, input_path)
        if path is not None:
            paths.append(path)
    for directory in (input_path.parent, input_path.parent.parent):
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.glob("material*.json")):
            if candidate.is_file():
                paths.append(candidate)
    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def load_materials(data: dict, input_path: Path) -> list[dict]:
    """Read every readable material record. An unreadable record is skipped here
    and reported by :func:`material_reference_errors` as an unresolved id."""
    materials: list[dict] = []
    for path in material_paths(data, input_path):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and has_text(record.get("material_id")):
            materials.append(record)
    return materials


def baseline_process_records(input_path: Path) -> list[dict]:
    """Every process record sitting in the input's OWN directory.

    Only the input directory itself is scanned (never its parent): the reference
    is a forward reference by construction - the design space is written before
    its step-6 companion ``process-baseline.json`` exists - and scanning upward
    would make an unrelated parent-level process record turn a legal pending
    reference into an incidental failure. A file counts as a record only when it
    parses to an object carrying a non-empty top-level ``process_id``: the
    request files (``input-process-baseline.json``) and every other shape are
    ignored.
    """
    records: list[dict] = []
    directory = input_path.parent
    if not directory.is_dir():
        return records
    for candidate in sorted(directory.glob("process*.json")):
        if not candidate.is_file():
            continue
        try:
            record = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and has_text(record.get("process_id")):
            records.append(record)
    return records


def baseline_process_errors(value: object, project_type: object, input_path: Path) -> list[str]:
    """Grease-route closure of ``baseline_process_reference``, consumer side.

    The design space names the fixed process its formula comparison is valid
    under, and that record is written later in the same step - so an absent
    record is the legal PENDING state (the NOTE in :func:`main`), never a HOLD.
    Once the directory holds at least one process record, the reference must
    resolve to one of them: a reference that names nothing is a dangling link.
    """
    if not isinstance(value, dict) or not effective_route_is_grease(project_type, value):
        return []
    reference = value.get("baseline_process_reference")
    if not has_text(reference):
        return []
    records = baseline_process_records(input_path)
    if not records:
        return []
    if any(record.get("process_id") == reference for record in records):
        return []
    return [
        f"design_space.baseline_process_reference: {reference} does not resolve to a readable process record "
        f"beside the input (found process_ids {sorted(record.get('process_id') for record in records)})"
    ]


def baseline_process_note(value: object, project_type: object, input_path: Path) -> list[str]:
    """The audible PENDING marker: the fixed process is declared, not yet written."""
    if not isinstance(value, dict) or not effective_route_is_grease(project_type, value):
        return []
    reference = value.get("baseline_process_reference")
    if not has_text(reference):
        return []
    if baseline_process_records(input_path):
        return []
    return [
        f"NOTE: design_space.baseline_process_reference {reference} is PENDING: no process record beside the "
        "input carries that process_id yet; the reference must resolve once the step-6 companion fix is written"
    ]


def measurement_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, dict) or set(value) != set(MEASUREMENT_FIELDS):
        return [label]
    errors = []
    for field in MEASUREMENT_FIELDS:
        item = value.get(field)
        if field == "value":
            if not isinstance(item, (int, float)) or isinstance(item, bool) or not math.isfinite(item):
                errors.append(f"{label}.value")
        elif not has_text(item):
            errors.append(f"{label}.{field}")
    return errors


def evidence_errors(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["design_space.evidence"]
    errors = []
    for index, item in enumerate(value):
        label = f"design_space.evidence[{index}]"
        if not isinstance(item, dict) or set(item) != {"evidence_id", "statement", "source", "status"}:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in {"OBSERVED", "ASSUMED", "GAP"}:
            errors.append(f"{label}.status")
    return errors


def constraint_errors(value: object) -> list[str]:
    """Constraints accept BOTH the legacy free-text form and the object form.

    The string form stays exactly as before, so every existing design space keeps
    validating. The object form is validated here because the shared contract can
    only state the shape, not the meaning of each declared kind.
    """
    if not isinstance(value, list) or not value:
        return ["design_space.constraints"]
    errors: list[str] = []
    for index, item in enumerate(value):
        label = f"design_space.constraints[{index}]"
        if has_text(item):
            continue
        if not isinstance(item, dict):
            errors.append(label)
            continue
        permitted = {"constraint_id", "kind", "expression", "rationale", "evidence_id"}
        errors.extend(f"{label}.{field} is not a permitted constraint field" for field in sorted(set(item) - permitted))
        for field in ("constraint_id", "expression", "rationale"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("kind") not in CONSTRAINT_KINDS:
            errors.append(f"{label}.kind must be one of {list(CONSTRAINT_KINDS)}")
    return errors


def material_reference_errors(variables: list, materials: list[dict], project_type: object, design_space: dict) -> list[str]:
    """Grease-route material reference resolution and the in-situ role semantics.

    Returns nothing for a non-grease route: the oil routes keep today's behaviour.
    ``role`` is the optional artifact field added by the grease step; when it is
    present the shared resolver is always used, so a reaction product can never be
    classified MIXTURE_CLOSED on any route.
    """
    by_id = {record["material_id"]: record for record in materials if has_text(record.get("material_id"))}
    grease = effective_route_is_grease(project_type, design_space)
    errors: list[str] = []
    for index, variable in enumerate(variables):
        if not isinstance(variable, dict):
            continue
        label = f"design_space.variables[{index}]"
        variable_id = variable.get("variable_id", f"variables[{index}]")
        reference = variable.get("material_reference")
        declared_role = variable.get("role")
        material_bearing = variable.get("variable_type") in MATERIAL_BEARING_VARIABLE_TYPES
        if grease and material_bearing and not has_text(reference):
            errors.append(
                f"{label}.material_reference is required on the PRECISION_GREASE_DEV route: "
                "a bare name string is not a material record"
            )
            continue
        if not has_text(reference):
            if declared_role is not None and declared_role not in MATERIAL_ROLES:
                errors.append(f"{label}.role must be one of {list(MATERIAL_ROLES)}")
            continue
        record = by_id.get(reference)
        if grease and record is None:
            errors.append(
                f"{label}.material_reference: {reference} does not resolve to a readable material record "
                f"(searched {len(by_id)} material object(s))"
            )
            continue
        category = record.get("category") if isinstance(record, dict) else None
        if declared_role is not None and declared_role not in MATERIAL_ROLES:
            errors.append(f"{label}.role must be one of {list(MATERIAL_ROLES)}")
            continue
        if grease and material_bearing and declared_role is None:
            errors.append(f"{label}.role is required on the PRECISION_GREASE_DEV route: state whether this variable is a charge or a reaction product")
            continue
        implied = derive_material_role(category)
        if grease and implied == REACTION_PRODUCT and declared_role != REACTION_PRODUCT:
            # N6: the thickener feed is consumed by saponification and the soap is
            # generated in situ, so the percentage that matters is a product.
            errors.append(
                f"{label}.role: {variable_id} ranges over material {reference} "
                f"({category}); its content is generated in situ by saponification, so it is a "
                f"{REACTION_PRODUCT} and must not be declared {declared_role or INPUT_MATERIAL}. "
                f"In-situ feedstocks: {list(IN_SITU_PRODUCT_MATERIAL_CATEGORIES)}"
            )
    return errors


def design_space_errors(value: object, failure: dict | None, method: dict | None, project_type: object = None, materials: list[dict] | None = None) -> list[str]:
    materials = materials or []
    if not isinstance(value, dict) or not DESIGN_SPACE_REQUIRED_FIELDS <= set(value) <= DESIGN_SPACE_REQUIRED_FIELDS | DESIGN_SPACE_OPTIONAL_FIELDS:
        return ["design_space must contain only the Stage 4 input fields"]
    errors = []
    for field in ("design_space_id", "scope"):
        if not has_text(value.get(field)):
            errors.append(f"design_space.{field}")
    if "process_reference" in value and not has_text(value.get("process_reference")):
        errors.append("design_space.process_reference")
    grease = effective_route_is_grease(project_type, value)
    if grease and not has_text(value.get("baseline_process_reference")):
        errors.append(
            "design_space.baseline_process_reference is required on the PRECISION_GREASE_DEV route: "
            "if the process changed, comparing formulae is invalid"
        )
    if "baseline_process_reference" in value and not has_text(value.get("baseline_process_reference")):
        errors.append("design_space.baseline_process_reference")
    feasibility = value.get("feasibility_regions")
    if feasibility is not None:
        if not isinstance(feasibility, list) or not feasibility:
            errors.append("design_space.feasibility_regions")
        else:
            for index, region in enumerate(feasibility):
                errors.extend(feasibility_region_errors(region, f"design_space.feasibility_regions[{index}]"))
    variables = value.get("variables")
    if not isinstance(variables, list) or not variables:
        errors.append("design_space.variables")
    else:
        variable_ids = set()
        for index, variable in enumerate(variables):
            label = f"design_space.variables[{index}]"
            if not isinstance(variable, dict) or not VARIABLE_REQUIRED_FIELDS <= set(variable) <= VARIABLE_ALLOWED_FIELDS:
                errors.append(label)
                continue
            variable_id = variable.get("variable_id")
            if not has_text(variable_id):
                errors.append(f"{label}.variable_id")
            elif variable_id in variable_ids:
                errors.append(f"{label}.variable_id is duplicated")
            else:
                variable_ids.add(variable_id)
            variable_type = variable.get("variable_type")
            if variable_type not in VARIABLE_TYPES:
                errors.append(f"{label}.variable_type")
            elif "constraint_role" in variable or "role" in variable:
                try:
                    resolve_variable_constraint_role(variable_type, variable.get("constraint_role"), variable.get("role"))
                except ConstraintRoleError as error:
                    errors.append(f"{label}.constraint_role: {error}")
            errors.extend(measurement_errors(variable.get("lower_bound"), f"{label}.lower_bound"))
            errors.extend(measurement_errors(variable.get("upper_bound"), f"{label}.upper_bound"))
            if not has_text(variable.get("constraint_rationale")):
                errors.append(f"{label}.constraint_rationale")
            lower, upper = variable.get("lower_bound"), variable.get("upper_bound")
            if isinstance(lower, dict) and isinstance(upper, dict) and not measurement_errors(lower, "") and not measurement_errors(upper, ""):
                if lower["unit"] != upper["unit"]:
                    errors.append(f"{label} bounds must use the same unit")
                if lower["value"] > upper["value"]:
                    errors.append(f"{label}.lower_bound.value must be <= upper_bound.value")
        if isinstance(variables, list):
            errors.extend(material_reference_errors(variables, materials, project_type, value))
    ctq_references = value.get("ctq_references")
    if not isinstance(ctq_references, list) or not ctq_references or not all(has_text(item) for item in ctq_references):
        errors.append("design_space.ctq_references")
    elif len(ctq_references) != len(set(ctq_references)):
        errors.append("design_space.ctq_references are duplicated")
    method_references = value.get("qualified_test_method_references")
    if not isinstance(method_references, list) or not method_references or not all(has_text(item) for item in method_references):
        errors.append("design_space.qualified_test_method_references")
    elif method is not None and method.get("method_id") not in method_references:
        # Defect 1 fix: membership instead of single-element equality.
        errors.append("design_space.qualified_test_method_references must contain the supplied qualified method_id")
    errors.extend(constraint_errors(value.get("constraints")))
    errors.extend(evidence_errors(value.get("evidence")))
    if not errors and has_gap(value):
        errors.append("design_space.evidence contains GAP; current input is insufficient")
    if failure is not None and method is not None and isinstance(ctq_references, list) and all(has_text(item) for item in ctq_references):
        ctqs = {item.get("ctq_id"): item for item in failure.get("ctqs", []) if isinstance(item, dict)}
        method_id = method.get("method_id")
        for ctq_id in ctq_references:
            ctq = ctqs.get(ctq_id)
            if ctq is None:
                errors.append(f"design_space.ctq_references: {ctq_id} does not exist")
            elif method_id not in ctq.get("test_references", []) and method_id not in failure.get("test_chain", []):
                # The step-3 CTQ may legally carry PENDING:<method_id> while the method
                # does not exist yet; by this step it IS qualified, so a CTQ that still
                # carries the marker must be backfilled with the bare id.
                references = ctq.get("test_references")
                pending_form = f"PENDING:{method_id}"
                hint = (
                    f"; this CTQ still marks the method as {pending_form}, so backfill the bare id "
                    f"{method_id} now that the method is QUALIFIED"
                    if isinstance(references, list) and pending_form in references
                    else ""
                )
                errors.append(
                    f"design_space.ctq_references: {ctq_id} is not linked to the supplied qualified method{hint}"
                )
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors = []
    artifacts: dict[str, dict | None] = {}
    requirements = (
        ("project_artifact", "project.schema.json", "PROJECT_DEFINED"),
        ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"),
        ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED"),
        ("test_method_artifact", "test_method.schema.json", "TEST_METHODS_QUALIFIED"),
    )
    # The charter is read BEFORE the key-set verdict, because whether the challenge key
    # may be absent at all is a property of the route: CHALLENGES_DEFINED is on no
    # type_route, so only the grease route may drop it. An input of any other shape, or a
    # grease shape whose charter is not the grease route, gets the pre-existing verdict
    # word for word.
    project_path = resolved_path(data.get("project_artifact"), input_path)
    charter = None
    if project_path is not None and project_path.is_file():
        try:
            charter = json.loads(project_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            charter = None
    grease = is_grease_route(charter.get("project_type") if isinstance(charter, dict) else None)
    no_challenge_shape = isinstance(data, dict) and CHALLENGE_KEY not in data
    key_shape_ok = (
        GREASE_NO_CHALLENGE_FIELDS <= set(data) <= INPUT_FIELDS - {CHALLENGE_KEY}
        if no_challenge_shape and grease
        else REQUIRED_INPUT_FIELDS <= set(data) <= INPUT_FIELDS
    )
    if not key_shape_ok:
        errors.append("input must contain only required Stage 4 artifact paths and design_space")
    for key, schema, stage in requirements:
        path = resolved_path(data.get(key), input_path)
        if path is None:
            # The grease route's legal no-challenge state: the link is recorded as
            # UNROUTED:<project_id> on the failure record instead of being consumable here.
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
    project = artifacts["project_artifact"]
    challenge = artifacts[CHALLENGE_KEY]
    failure = artifacts["failure_ctq_artifact"]
    method = artifacts["test_method_artifact"]
    if project is not None and project.get("status") != "ACTIVE":
        errors.append("project_artifact must have status ACTIVE")
    if challenge is not None and failure is not None and failure.get("challenge_reference") != challenge.get("challenge_id"):
        errors.append("failure_ctq_artifact.challenge_reference must equal challenge_artifact.challenge_id")
    if grease and challenge is None and failure is not None:
        # The no-challenge shape's own uniformity rule, over the three artifacts that
        # exist. Unreachable on any route that requires a challenge.
        present = [item for item in (project, failure, method) if item is not None]
        if len(present) == 3 and len({item.get("project_id") for item in present}) != 1:
            errors.append("project, failure_ctq, and test_method project_id values must match")
    elif challenge is not None:
        present = [item for item in (project, challenge, failure, method) if item is not None]
        if len(present) == 4 and len({item.get("project_id") for item in present}) != 1:
            errors.append("project, challenge, failure_ctq, and test_method project_id values must match")
    if failure is not None and method is not None and method.get("target_failure_reference") != failure.get("failure_id"):
        errors.append("test_method_artifact.target_failure_reference must equal failure_ctq_artifact.failure_id")
    if method is not None and method.get("qualification_status") != "QUALIFIED":
        errors.append("test_method_artifact must have qualification_status QUALIFIED")
    project_type = project.get("project_type") if isinstance(project, dict) else None
    errors.extend(design_space_errors(data.get("design_space"), failure, method, project_type, load_materials(data, input_path)))
    errors.extend(baseline_process_errors(data.get("design_space"), project_type, input_path))
    return errors


def constraint_role_notes(value: object) -> list[str]:
    """One explicit resolution line per variable so the run is never silent.

    Declared roles and type-derived roles are both reported; unresolved
    variables (unknown type, contradictory or invalid declaration) are reported
    as unresolved rather than omitted. A variable that declares the grease
    material-side ``role`` also reports the derived product side, so an in-situ
    product can never be silently classified as a charge.
    """
    if not isinstance(value, dict):
        return []
    variables = value.get("variables")
    if not isinstance(variables, list):
        return []
    notes = []
    for index, variable in enumerate(variables):
        if not isinstance(variable, dict):
            continue
        variable_id = variable.get("variable_id", f"variables[{index}]")
        try:
            if "role" in variable:
                note = describe_variable_constraint_role(
                    variable.get("variable_type"), variable.get("constraint_role"), variable.get("role")
                )
            else:
                note = describe_constraint_role(variable.get("variable_type"), variable.get("constraint_role"))
        except ConstraintRoleError as error:
            notes.append(f"{variable_id}: CONSTRAINT_ROLE unresolved: {error}")
            continue
        notes.append(f"{variable_id}: {note}")
    return notes


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_formulation_design.py <input.json>")
        return 1
    path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, path)
    design_space = data.get("design_space") if isinstance(data, dict) else None
    for note in constraint_role_notes(design_space):
        print(note)
    # The closure-basis note is grease-only: on the six oil routes the run output
    # must stay exactly what it was, so nothing new is printed there.
    project_path = resolved_path(data.get("project_artifact"), path) if isinstance(data, dict) else None
    project = None
    if project_path is not None and project_path.is_file():
        try:
            project = json.loads(project_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            project = None
    if effective_route_is_grease(project.get("project_type") if isinstance(project, dict) else None, design_space):
        for note in grease_notes(design_space):
            print(note)
        # The fixed-process reference is a forward reference by construction (the
        # companion process record is written later in this same step), so its
        # PENDING state is said out loud rather than silently assumed.
        for note in baseline_process_note(
            design_space, project.get("project_type") if isinstance(project, dict) else None, path
        ):
            print(note)
    # The recorded CHALLENGES_DEFINED gap is a property of the ROUTE, so it is gated on
    # the charter's own project_type rather than on effective_route_is_grease: a design
    # space that merely uses grease-shaped fields did not thereby drop a route stage.
    if isinstance(data, dict) and is_grease_route(project.get("project_type") if isinstance(project, dict) else None):
        if resolved_path(data.get("challenge_artifact"), path) is None:
            print(challenge_note(project.get("project_id")))
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    print("READY: input can form one DESIGN_SPACE_DEFINED record only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

