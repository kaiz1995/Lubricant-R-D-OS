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


def reference_dossier_errors(reference_id: object, project_type: object, dossier_path: Path | None) -> list[str]:
    """Grease-route presence and resolution of the Stage 4 reference dossier.

    ``reference_id`` is the id recorded on the method; ``dossier_path`` is the
    optional top-level ``reference_material_artifact`` path. The dossier is read
    structurally rather than schema-validated: the reference contract is not part
    of this skill's deployment list, and naming a schema the bundle does not ship
    would make the deployed preflight crash at runtime (the double-list guard
    exists for exactly that). The fields checked here are the ones this policy
    actually consumes - identity, stage, decision, and the downstream
    discrimination flag - and they are checked, not assumed.
    """
    if not is_grease_route(project_type):
        return []
    if not has_text(reference_id):
        return [
            f"test_method.reference_material_reference is required on the {GREASE_PROJECT_TYPE} route: "
            "discrimination cannot be proved without the physical Known Good / Known Bad dossiers"
        ]
    if dossier_path is None:
        # A bare id with no dossier beside the input: the requirement above is
        # met, and there is nothing further this layer can read.
        return []
    if not dossier_path.is_file():
        return [f"reference_material_artifact cannot be read: {dossier_path} is not a file"]
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
        # The flag is the discrimination evidence state Stage 5 must carry to the
        # final gate (E2E-7): an incomplete flag is reported, never silently used.
        errors.append(
            "reference_material_artifact.downstream_flag is DISCRIMINATION_EVIDENCE_INCOMPLETE: "
            "the Known Bad is not RESOLVED, so discrimination evidence is incomplete and this state "
            "must be carried to the final gate"
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
        # still checked structurally rather than accepted unchecked.
        errors.extend(pipeline_errors(value))
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    errors, artifacts = [], {}
    evidence_scope = data.get("evidence_scope")
    if evidence_scope not in {"SYNTHETIC", "PHYSICAL"}:
        errors.append("evidence_scope must be SYNTHETIC or PHYSICAL")
    for key, schema, stage in (("project_artifact", "project.schema.json", "PROJECT_DEFINED"), ("challenge_artifact", "challenge.schema.json", "CHALLENGES_DEFINED"), ("failure_ctq_artifact", "failure_ctq.schema.json", "FAILURE_CTQ_DEFINED")):
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
    project, challenge, failure = artifacts["project_artifact"], artifacts["challenge_artifact"], artifacts["failure_ctq_artifact"]
    if project is not None and project.get("status") != "ACTIVE":
        errors.append("project_artifact must have status ACTIVE")
    if project and challenge and failure and len({project.get("project_id"), challenge.get("project_id"), failure.get("project_id")}) != 1:
        errors.append("project, challenge, and failure_ctq project_id values must match")
    project_type = project.get("project_type") if isinstance(project, dict) else None
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
