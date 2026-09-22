"""Validate one Failure/CTQ record against canonical or deployed contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from preflight_failure_ctq import contribution_errors, evidence_errors, failure_ctq_errors, schema_dir


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_failure_ctq_artifact.py <artifact.json>")
        return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        schemas = schema_dir()
        common = json.loads((schemas / "common.schema.json").read_text(encoding="utf-8"))
        project = json.loads((schemas / "project.schema.json").read_text(encoding="utf-8"))
        challenge = json.loads((schemas / "challenge.schema.json").read_text(encoding="utf-8"))
        failure_ctq = json.loads((schemas / "failure_ctq.schema.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    registry = registry.with_resource(project["$id"], Resource.from_contents(project))
    registry = registry.with_resource(challenge["$id"], Resource.from_contents(challenge))
    registry = registry.with_resource(failure_ctq["$id"], Resource.from_contents(failure_ctq))
    errors = [error.message for error in Draft202012Validator(failure_ctq, registry=registry).iter_errors(artifact)]
    if artifact.get("stage") != "FAILURE_CTQ_DEFINED":
        errors.append("stage must be FAILURE_CTQ_DEFINED")
    errors.extend(failure_ctq_errors(artifact, None))
    errors.extend(evidence_errors(artifact.get("evidence")))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: failure/CTQ artifact conforms to the Stage 2 contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
