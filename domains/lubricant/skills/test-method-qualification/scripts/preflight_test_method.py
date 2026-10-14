"""Reject incomplete test-method qualification input before an artifact is built.

The PRECISION_GREASE_DEV route (outer-loop step 5) carries three extra mandatory
rules, enforced in this POLICY LAYER rather than in the shared contract so the six
oil routes keep their current behaviour exactly:

  * ``REPEATABILITY`` is required for EVERY role, not only D and P;
  * the repeatability -> discrimination -> independent new batch pipeline is
    SERIAL: a later sub-step without its predecessor passing is a pipeline gap;
  * repeatability and discrimination must be ENGINE-computed and the independent
    new batch check must be PASS - before a method can predict the bench, any
    optimisation algorithm only optimises the wrong target faster.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from qualification_policy import (
    GREASE_PROJECT_TYPE,
    METRICS,
    QUALIFICATION_STATUSES,
    ROLES,
    grease_qualification_errors,
    is_grease_route,
    role_metric_errors,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_FIELDS = ("value", "unit", "source", "method_version", "material_batch", "formula_version")
# The one upstream key the grease route may legally omit: CHALLENGES_DEFINED is on no
# type_route, so the grease route records the Challenge Map link as UNROUTED:<project_id>
# instead of producing an out-of-route artifact. Named once, used by the take-item loop
# and by the recorded-gap evidence the builder writes.
CHALLENGE_KEY = "challenge_artifact"
UNROUTED_PREFIX = "UNROUTED:"
# Provenance of the recorded gap: the route contract is what says the stage is on no
# type_route, so it is what the recorded evidence cites.
ROUTE_CONTRACT_SOURCE = "contracts/state-machine.json"


def unrouted_statement(project_id: object) -> str:
    """The recorded-gap sentence. The preflight prints it, the artifact's evidence carries it."""
    return (
        f"challenge_artifact not supplied on the {GREASE_PROJECT_TYPE} route "
        f"(CHALLENGES_DEFINED is on no type_route); the Challenge Map link is recorded as "
        f"{UNROUTED_PREFIX}{project_id}"
    )


def unrouted_note(project_id: object) -> str:
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
        and is_grease_route(charter_project_type(project))
    )


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    names = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json")
    return canonical if all((canonical / name).is_file() for name in names) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def charter_project_type(project: object) -> object:
    """The route marker off a validated charter, or None when there is not one.

    An unreadable or absent charter yields None, which ``is_grease_route`` reads as "not
    the grease route": every caller that cannot determine the route keeps the exact
    pre-change behaviour.
    """
    return project.get("project_type") if isinstance(project, dict) else None


def schema_artifact(path: Path, name: str, label: str) -> tuple[list[str], dict | None]:
    try:
        schemas = schema_dir()
        names = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json")
        loaded = {item: json.loads((schemas / item).read_text(encoding="utf-8")) for item in names}
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(loaded[name], registry=registry).iter_errors(artifact)]
    return errors, artifact if not errors else None


def measurement_errors(value: object, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [label]
    errors = []
    for field in MEASUREMENT_FIELDS:
        item = value.get(field)
        if field == "value":
            if not isinstance(item, (int, float)) or isinstance(item, bool):
                errors.append(f"{label}.value")
        elif not has_text(item):
            errors.append(f"{label}.{field}")
    return errors


def evidence_errors(value: object) -> tuple[list[str], dict[str, dict]]:
    if not isinstance(value, list) or not value:
        return ["evidence"], {}
    errors, indexed = [], {}
    for index, item in enumerate(value):
        label = f"evidence[{index}]"
        if not isinstance(item, dict):
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in {"OBSERVED", "ASSUMED", "GAP"}:
            errors.append(f"{label}.status")
        elif has_text(item.get("evidence_id")):
            indexed[item["evidence_id"]] = item
    return errors, indexed


def observed_id_errors(value: object, label: str, evidence: dict[str, dict]) -> list[str]:
    if not isinstance(value, list) or not value or not all(has_text(item) for item in value):
        return [label]
    return [f"{label}: {item} must reference OBSERVED evidence" for item in value if item not in evidence or evidence[item].get("status") != "OBSERVED"]


def pipeline_errors(value: object, project_type: object) -> list[str]:
    """Structural checks for the optional pipeline object, plus grease presence.

    The shared schema states the shape; this layer states the meaning. On the
    grease route the whole pipeline is mandatory and every sub-status must be a
    recognised value.
    """
    if not isinstance(value, dict):
        return ["test_method.qualification_pipeline"]
    errors = []
    permitted = {"repeatability", "discrimination", "independent_batch"}
    errors.extend(f"test_method.qualification_pipeline.{field} is not a permitted sub-step" for field in sorted(set(value) - permitted))
    for key in ("repeatability", "discrimination", "independent_batch"):
        step = value.get(key)
        if step is None:
            continue
        if not isinstance(step, dict):
            errors.append(f"test_method.qualification_pipeline.{key}")
            continue
        errors.extend(
            f"test_method.qualification_pipeline.{key}.{field} is not a permitted sub-step field"
            for field in sorted(set(step) - {"status", "evidence_reference", "computed_by"})
        )
        if step.get("status") not in {"PASS", "FAIL", "NOT_RUN"}:
            errors.append(f"test_method.qualification_pipeline.{key}.status")
        if "computed_by" in step and step.get("computed_by") not in {"ENGINE", "MANUAL"}:
            errors.append(f"test_method.qualification_pipeline.{key}.computed_by")
        if "evidence_reference" in step and not has_text(step.get("evidence_reference")):
            errors.append(f"test_method.qualification_pipeline.{key}.evidence_reference")
    if is_grease_route(project_type):
        for key in ("repeatability", "discrimination"):
            step = value.get(key)
            if isinstance(step, dict) and not has_text(step.get("evidence_reference")):
                errors.append(
                    f"test_method.qualification_pipeline.{key}.evidence_reference is required on the "
                    f"{GREASE_PROJECT_TYPE} route: a sub-step outcome without its record is not evidence"
                )
    return errors


DOSSIER_REQUIRED = (
    "test_method.reference_material_artifact is required on the PRECISION_GREASE_DEV route: "
    "a reference id with no dossier beside the input cannot be read, and an unreadable dossier is "
    "exactly the no-Known-Bad case this step must refuse"
)


def reference_dossier_errors(reference_id: object, project_type: object, dossier_path: Path | None) -> list[str]:
    """Grease-route presence and resolution of the Stage 4 reference dossier.

    ``reference_id`` is the id recorded on the method; ``dossier_path`` is the
    top-level ``reference_material_artifact`` path, which is REQUIRED on this
    route: a reference id with no readable dossier beside the input cannot be
    read, and an unreadable dossier is exactly the no-Known-Bad case this step
    must refuse. The dossier is read structurally rather than schema-validated:
    the reference contract is not part of this skill's deployment list, and
    naming a schema the bundle does not ship would make the deployed preflight
    crash at runtime (the double-list guard exists for exactly that). The fields
    checked here are the ones this policy actually consumes - identity, stage,
    decision, and the downstream discrimination flag - and they are checked, not
    assumed.
    """
    if not is_grease_route(project_type):
        return []
    if not has_text(reference_id):
        return [
            f"test_method.reference_material_reference is required on the {GREASE_PROJECT_TYPE} route: "
            "discrimination cannot be proved without the physical Known Good / Known Bad dossiers"
        ]
    if dossier_path is None:
        return [DOSSIER_REQUIRED]
    if not dossier_path.is_file():
        return [f"{DOSSIER_REQUIRED} ({dossier_path} is not a file)"]
    try:
        dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"reference_material_artifact cannot be read: {error}"]
    if not isinstance(dossier, dict):
        return ["reference_material_artifact must be a JSON object"]
    errors: list[str] = []
    recorded = dossier.get("reference_id")
    if has_text(recorded) and recorded != reference_id:
        errors.append(
            f"test_method.reference_material_reference {reference_id} does not match "
            f"reference_material_artifact.reference_id {recorded}"
        )
    if dossier.get("stage") != "REFERENCE_MATERIAL_RESOLVED":
        errors.append("reference_material_artifact must be stage REFERENCE_MATERIAL_RESOLVED")
    if dossier.get("decision") != "GO":
        errors.append(
            "reference_material_artifact must have decision GO: no side is RESOLVED, so this reference "
            "set cannot serve as the discrimination ruler"
        )
    if dossier.get("downstream_flag") == "DISCRIMINATION_EVIDENCE_INCOMPLETE":
        # NOT a carried state (E3=B): the flag is a hard refusal here. A set with
        # no RESOLVED Known Bad is exactly the no-Known-Bad case this step must
        # refuse, so an incomplete flag is reported and Step 5 stops; it is never
        # silently used as a discrimination ruler.
        errors.append(
            "reference_material_artifact.downstream_flag is DISCRIMINATION_EVIDENCE_INCOMPLETE: "
            "the Known Bad is not RESOLVED, so this reference set cannot serve as the discrimination "
            "ruler and Step 5 must not proceed"
        )
    return errors


def method_errors(value: object, challenge: dict | None, failure: dict | None, evidence: dict[str, dict], evidence_scope: object, project_type: object = None, input_path: Path | None = None, reference_dossier_path: object = None) -> list[str]:
    if not isinstance(value, dict):
        return ["test_method"]
    errors = []
    for field in ("method_id", "name", "standard", "challenge_reference", "target_failure_reference"):
        if not has_text(value.get(field)):
            errors.append(f"test_method.{field}")
    if challenge and value.get("challenge_reference") != challenge.get("challenge_id"):
        errors.append("test_method.challenge_reference must equal challenge_artifact.challenge_id")
    if failure and value.get("target_failure_reference") != failure.get("failure_id"):
        errors.append("test_method.target_failure_reference must equal failure_ctq_artifact.failure_id")
    if failure and value.get("challenge_reference") != failure.get("challenge_reference"):
        errors.append("test_method.challenge_reference must equal failure_ctq_artifact.challenge_reference")
    roles = value.get("role")
    if not isinstance(roles, list) or not roles or len(roles) != len(set(roles)) or any(role not in ROLES for role in roles):
        errors.append("test_method.role")
    metrics = value.get("qualification_metrics")
    if not isinstance(metrics, list) or not metrics:
        errors.append("test_method.qualification_metrics")
    else:
        names = set()
        for index, item in enumerate(metrics):
            label = f"test_method.qualification_metrics[{index}]"
            if not isinstance(item, dict) or item.get("metric") not in METRICS:
                errors.append(f"{label}.metric")
                continue
            if item["metric"] in names:
                errors.append(f"{label}.metric is duplicated")
            names.add(item["metric"])
            errors.extend(measurement_errors(item.get("measurement"), f"{label}.measurement"))
            if "computed_by" in item and item.get("computed_by") not in {"ENGINE", "MANUAL"}:
                errors.append(f"{label}.computed_by")
    basis = value.get("qualification_basis")
    if not isinstance(basis, list) or not basis or not all(has_text(item) for item in basis):
        errors.append("test_method.qualification_basis")
    if value.get("qualification_status") not in QUALIFICATION_STATUSES:
        errors.append("test_method.qualification_status")
    if evidence_scope == "SYNTHETIC" and value.get("qualification_status") == "QUALIFIED":
        errors.append("SYNTHETIC evidence_scope cannot form qualification_status QUALIFIED")
    source_id = value.get("method_source_evidence_id")
    if not has_text(source_id) or source_id not in evidence or evidence[source_id].get("status") != "OBSERVED":
        errors.append("test_method.method_source_evidence_id must reference OBSERVED evidence")
    errors.extend(observed_id_errors(value.get("qualification_evidence_ids"), "test_method.qualification_evidence_ids", evidence))
    if "qualification_pipeline" in value:
        errors.extend(pipeline_errors(value.get("qualification_pipeline"), project_type))
    errors.extend(role_metric_errors(value, project_type))
    if is_grease_route(project_type):
        # The serial-order and ENGINE-computation rules run on every grease input,
        # not only on a QUALIFIED claim: an unpassed or hand-entered sub-step is a
        # gap in the submission itself, and letting it through would let a
        # PENDING record hide a hand-entered discrimination figure. The pipeline
        # presence rule is part of this call (pipeline_errors reports an absent
        # pipeline), so it is not reported twice.
        errors.extend(grease_qualification_errors(value))
        errors.extend(
            reference_dossier_errors(
                value.get("reference_material_reference"),
                project_type,
                resolved_path(reference_dossier_path, input_path) if input_path is not None else None,
            )
        )
    elif "qualification_pipeline" in value:
        # Oil routes keep today's behaviour, but a pipeline they do supply is
        # still checked structurally rather than accepted unchecked. The route is
        # passed through, and the pipeline object (not the method) is what this
        # checker reads: dropping the argument raised a TypeError on any
        # non-grease input that carries a pipeline.
        errors.extend(pipeline_errors(value.get("qualification_pipeline"), project_type))
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors, artifacts = [], {}
    evidence_scope = data.get("evidence_scope")
    if evidence_scope not in {"SYNTHETIC", "PHYSICAL"}:
        errors.append("evidence_scope must be SYNTHETIC or PHYSICAL")
    # The three upstream artifacts are read in order, so the charter is available by the
    # time the challenge entry is reached: CHALLENGES_DEFINED is on no type_route, so on
    # the grease route a missing challenge_artifact is a legal state (recorded downstream
    # as UNROUTED:<project_id>) rather than a missing input. Every other route, and every
    # grease request that DOES supply one, keeps the pre-existing requirement word for word.
    for key, schema, stage in (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED")):
        path = resolved_path(data.get(key), input_path)
        if path is None:
            # The charter is read first, so ``grease`` is already knowable here.
            if key != CHALLENGE_KEY or not is_grease_route(charter_project_type(artifacts.get("project_artifact"))):
                errors.append(key)
            artifacts[key] = None
            continue
        item_errors, artifact = schema_artifact(path, schema, key)
        errors.extend(item_errors)
        artifacts[key] = artifact
        if artifact is not None and artifact.get("stage") != stage:
            errors.append(f"{key} must be stage {stage}")
    project = artifacts.get("project_artifact")
    challenge = artifacts.get(CHALLENGE_KEY)
    failure = artifacts.get("failure_ctq_artifact")
    grease = is_grease_route(charter_project_type(project))
    if project is not None and project.get("status") != "ACTIVE":
        errors.append("project_artifact must have status ACTIVE")
    if project and challenge and failure and len({project.get("project_id"), challenge.get("project_id"), failure.get("project_id")}) != 1:
        errors.append("project, challenge, and failure_ctq project_id values must match")
    if grease and challenge is None and project and failure and project.get("project_id") != failure.get("project_id"):
        # The grease route's no-challenge shape: the same uniformity rule, over the two
        # artifacts that do exist. Unreachable on any route that requires a challenge, so
        # the oil output is untouched.
        errors.append("project and failure_ctq project_id values must match")
    project_type = charter_project_type(project)
    evidence_problems, evidence = evidence_errors(data.get("evidence"))
    errors.extend(evidence_problems)
    errors.extend(
        method_errors(
            data.get("test_method"), challenge, failure, evidence, evidence_scope, project_type,
            input_path, data.get("reference_material_artifact"),
        )
    )
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_test_method.py <input.json>")
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
    print("READY: input can form one TEST_METHODS_QUALIFIED record only")
    # The recorded CHALLENGES_DEFINED gap is a property of the ROUTE, so it is gated on
    # the charter's own project_type and on the challenge key being absent: an oil request,
    # and a grease request that supplied a challenge artifact, print exactly what they
    # printed before. The line is printed AFTER the READY verdict so the verdict stays the
    # first line, matching the sibling preflights.
    project_path = resolved_path(data.get("project_artifact"), path)
    project = None
    if project_path is not None and project_path.is_file():
        try:
            project = json.loads(project_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            project = None
    if resolved_path(data.get("challenge_artifact"), path) is None and is_grease_route(charter_project_type(project)):
        print(unrouted_note(project.get("project_id")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
