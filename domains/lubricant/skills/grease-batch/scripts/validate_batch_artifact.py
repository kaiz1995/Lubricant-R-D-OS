"""Validate one deterministic batch artifact and its sample artifact.

Two independent checks, both fail-closed:

1. Structural: each artifact validates against ``schemas/batch.schema.json`` /
   ``schemas/sample.schema.json`` with the common contract in the registry. Schema
   errors are reported with their instance path so the citation is traceable.
2. Semantic: the artifact equals what ``grease_batch_policy`` deterministically derives
   from its own fields - the trajectory trace and tolerance boundary, the legality of the
   declared batch verdict, the release rule, and the canonical decision block. This
   catches a hand-edited artifact that is schema-legal but not policy-legal (for example
   a batch recorded VALID over a DEVIATED step, or a step edited after the batch was
   recorded so that it no longer matches its own derived trace).

The sample artifact is validated against the batch record when it is found beside it
(``_tmp_batch.json`` -> ``_tmp_sample.json``, or the canonical ``batch.json`` ->
``sample.json``), because a sample's decision is derived from its batch's verdict.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from grease_batch_policy import (
    BATCH_ARTIFACT_FIELDS,
    batch_errors,
    batch_verdict_errors,
    expected_decision_fields,
    expected_sample_decision_fields,
    recorded_sample,
    sample_binding_errors,
    sample_errors,
    trajectory_trace_errors,
)
from preflight_grease_batch import SCHEMA_NAMES, schema_dir


def schema_errors(artifact: object, schema_name: str) -> list[str]:
    schemas = schema_dir()
    loaded = {name: json.loads((schemas / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator(loaded[schema_name], registry=registry)
    return [
        f"{schema_name}: {error.message} (path {list(error.absolute_path) or ['<root>']})"
        for error in validator.iter_errors(artifact)
    ]


def semantic_errors(artifact: object) -> list[str]:
    """Batch-side policy checks: shape, trace boundary, verdict legality, decision block."""
    if not isinstance(artifact, dict):
        return []
    batch = {field: artifact.get(field) for field in BATCH_ARTIFACT_FIELDS}
    errors = batch_errors(batch)
    errors.extend(trajectory_trace_errors(artifact))
    errors.extend(batch_verdict_errors(batch))
    for field, value in expected_decision_fields(batch, artifact.get("evidence_scope")).items():
        if artifact.get(field) != value:
            errors.append(f"{field} must equal the deterministic grease-batch policy")
    return errors


def sample_semantic_errors(sample: object, batch: object) -> list[str]:
    """The gate rule, the batch binding, and the canonical sample decision block."""
    errors = sample_errors(recorded_sample(sample), batch if isinstance(batch, dict) else {})
    errors.extend(sample_binding_errors(sample, batch))
    if isinstance(sample, dict) and isinstance(batch, dict):
        for field, value in expected_sample_decision_fields(
            sample, sample.get("batch_reference"), batch.get("batch_verdict"), sample.get("evidence_scope")
        ).items():
            if sample.get(field) != value:
                errors.append(f"sample {field} must equal the deterministic grease-batch policy")
    return errors


def sample_path_for(artifact_path: Path) -> Path | None:
    """The sample record that accompanies this batch record, or None if absent.

    ``_tmp_batch.json`` -> ``_tmp_sample.json`` and the canonical ``batch.json`` ->
    ``sample.json`` mirror the builder's naming; ``<stem>.sample.json`` is accepted too so
    a suffixed record (``batch-PGD-001-BAT-1.json``) can carry its sample.
    """
    candidates = [artifact_path.with_name(artifact_path.stem + ".sample.json")]
    if artifact_path.stem.endswith("batch"):
        candidates.append(
            artifact_path.with_name(artifact_path.stem[: -len("batch")] + "sample.json")
        )
    candidates.append(artifact_path.parent / "sample.json")
    for candidate in candidates:
        if candidate.is_file() and candidate.resolve() != artifact_path.resolve():
            return candidate
    return None


def batch_path_for(sample_path: Path) -> Path | None:
    """The batch record a stored sample belongs to, or None if it is not in this workspace.

    This is what lets ``sample.json`` be validated directly (``validate_workspace.py``
    dispatches per filename): a sample cannot be judged without the batch whose verdict
    decides it, so a sample with no batch record beside it is a FAIL rather than a pass.
    """
    candidates = [
        sample_path.with_name(sample_path.stem + ".batch.json"),
        sample_path.parent / "batch.json",
    ]
    if sample_path.stem.endswith("sample"):
        candidates.insert(
            0,
            sample_path.with_name(sample_path.stem[: -len("sample")] + "batch.json"),
        )
    return first_existing(candidates, exclude=sample_path)


def first_existing(candidates: list[Path], exclude: Path) -> Path | None:
    for candidate in candidates:
        if candidate.is_file() and candidate.resolve() != exclude.resolve():
            return candidate
    return None


def expected_batch_names(sample_path: Path) -> str:
    """The batch filenames this sample could be paired with, for the failure message."""
    names: list[str] = []
    for candidate in (
        sample_path.parent / "batch.json",
        sample_path.with_name(sample_path.stem[: -len("sample")] + "batch.json")
        if sample_path.stem.endswith("sample")
        else sample_path.with_name(sample_path.stem + ".batch.json"),
    ):
        if candidate.name not in names:
            names.append(candidate.name)
    return " or ".join(names)


def validate_sample_entry(sample_path: Path, sample: dict) -> list[str]:
    """Validate a stored sample record as the entry artifact, against its own batch."""
    errors = schema_errors(sample, "sample.schema.json")
    batch_path = batch_path_for(sample_path)
    if batch_path is None:
        errors.append(
            "no batch record found beside this sample (expected "
            f"{expected_batch_names(sample_path)}): a sample cannot be judged without the batch "
            "whose verdict decides it"
        )
        return errors
    try:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{batch_path.name} cannot be read: {error}")
        return errors
    if not isinstance(batch, dict) or batch.get("artifact_type") != "batch":
        errors.append(f"{batch_path.name} is not a batch artifact")
        return errors
    errors.extend(sample_semantic_errors(sample, batch))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_batch_artifact.py <artifact.json>")
        return 1
    artifact_path = Path(sys.argv[1]).resolve()
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    if isinstance(artifact, dict) and artifact.get("artifact_type") == "sample":
        # Entry-point dispatch: the sample record is the second artifact this skill owns,
        # and the workspace validator addresses files one by one.
        try:
            errors = validate_sample_entry(artifact_path, artifact)
        except (OSError, json.JSONDecodeError) as error:
            print(f"FAIL: cannot read artifact or schemas: {error}")
            return 1
        if errors:
            for error in errors:
                print(f"FAIL: {error}")
            return 1
        print("PASS: deterministic sample record conforms to the sample contract")
        return 0
    try:
        errors = schema_errors(artifact, "batch.schema.json")
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    if not isinstance(artifact, dict):
        errors.append("artifact must be a JSON object")
    else:
        errors.extend(semantic_errors(artifact))
    sample_path = sample_path_for(artifact_path)
    sample: dict | None = None
    if sample_path is not None:
        try:
            loaded_sample = json.loads(sample_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{sample_path.name} cannot be read: {error}")
            loaded_sample = None
        if isinstance(loaded_sample, dict):
            sample = loaded_sample
            try:
                errors.extend(schema_errors(sample, "sample.schema.json"))
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"cannot read artifact or schemas: {error}")
            errors.extend(sample_semantic_errors(sample, artifact))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    if sample is not None:
        print(
            "PASS: deterministic batch artifact and its sample record conform to the batch contract "
            f"({sample_path.name})"
        )
    else:
        print("PASS: deterministic batch artifact conforms to the batch contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
