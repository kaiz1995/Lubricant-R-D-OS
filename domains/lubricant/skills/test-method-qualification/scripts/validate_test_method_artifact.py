"""Validate one deterministic test-method qualification artifact.

The validator sees the artifact without its upstream charter, so it detects the
grease extension from the artifact itself: a record that carries the
``qualification_pipeline`` or a ``reference_material_reference`` is held to the
whole grease rule set (serial pipeline, ENGINE-computed repeatability and
discrimination, PASS on the independent new batch check). A record that carries
neither keeps exactly the pre-change rule set, which is what the six oil routes
produce.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from preflight_test_method import METRICS, QUALIFICATION_STATUSES, ROLES, evidence_errors, has_text, measurement_errors, pipeline_errors, schema_dir
from qualification_policy import GREASE_PROJECT_TYPE, expected_decision_fields, go_qualification_errors, role_metric_errors


# Presence of any of these fields marks the artifact as using the grease extension.
GREASE_EXTENSION_FIELDS = ("qualification_pipeline", "reference_material_reference")


def artifact_route(artifact: dict) -> str | None:
    """Return the grease project type when the artifact uses the extension, else None."""
    if any(field in artifact for field in GREASE_EXTENSION_FIELDS):
        return GREASE_PROJECT_TYPE
    return None


def semantic_errors(artifact: dict) -> list[str]:
    errors = []
    if artifact.get("evidence_scope") not in {"SYNTHETIC", "PHYSICAL"}:
        errors.append("evidence_scope")
    for field in ("method_id", "name", "standard", "target_failure_reference"):
        if not has_text(artifact.get(field)):
            errors.append(field)
    roles = artifact.get("role")
    if not isinstance(roles, list) or not roles or len(roles) != len(set(roles)) or any(role not in ROLES for role in roles):
        errors.append("role")
    metrics = artifact.get("qualification_metrics")
    if not isinstance(metrics, list) or not metrics:
        errors.append("qualification_metrics")
    else:
        seen = set()
        for index, item in enumerate(metrics):
            label = f"qualification_metrics[{index}]"
            if not isinstance(item, dict) or item.get("metric") not in METRICS:
                errors.append(f"{label}.metric")
                continue
            if item["metric"] in seen:
                errors.append(f"{label}.metric is duplicated")
            seen.add(item["metric"])
            errors.extend(measurement_errors(item.get("measurement"), f"{label}.measurement"))
            if "computed_by" in item and item.get("computed_by") not in {"ENGINE", "MANUAL"}:
                errors.append(f"{label}.computed_by")
    basis = artifact.get("qualification_basis")
    if not isinstance(basis, list) or not basis or not all(has_text(item) for item in basis):
        errors.append("qualification_basis")
    evidence_problems, _ = evidence_errors(artifact.get("evidence"))
    errors.extend(evidence_problems)
    if artifact.get("qualification_status") not in QUALIFICATION_STATUSES:
        errors.append("qualification_status")
    project_type = artifact_route(artifact)
    if "qualification_pipeline" in artifact:
        errors.extend(pipeline_errors(artifact.get("qualification_pipeline"), project_type))
    if project_type is not None and not has_text(artifact.get("reference_material_reference")):
        # The dossier id is the ruler the qualification claims to have used; a
        # grease record without it cannot say what the discrimination was against.
        errors.append("reference_material_reference is required when the qualification pipeline is recorded")
    errors.extend(role_metric_errors(artifact, project_type))
    if artifact.get("qualification_status") == "QUALIFIED":
        errors.extend(go_qualification_errors(artifact, project_type))
    for field, value in expected_decision_fields(artifact, project_type).items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic qualification policy")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_test_method_artifact.py <artifact.json>")
        return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        schemas = schema_dir()
        names = ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json")
        loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in names}
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [error.message for error in Draft202012Validator(loaded["test_method.schema.json"], registry=registry).iter_errors(artifact)]
    if artifact.get("stage") != "TEST_METHODS_QUALIFIED":
        errors.append("stage must be TEST_METHODS_QUALIFIED")
    errors.extend(semantic_errors(artifact))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: deterministic test-method qualification artifact conforms to the Stage 3 contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
