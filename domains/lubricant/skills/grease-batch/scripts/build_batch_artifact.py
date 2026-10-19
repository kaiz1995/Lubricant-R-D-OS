"""Build the only permitted BATCH_PRODUCED artifacts (the batch record and its sample).

Deterministic assembly only. Every judgement - the per-step tolerance boundary, the
legality of the declared batch verdict, the release rule, and the canonical decision
blocks - lives in ``grease_batch_policy`` so this builder and the validator cannot
disagree.

Two artifacts are written from one request, because a sample is a physical portion of
the batch and cannot be identified without it:

1. ``<output_path>`` - the batch record. The input-side trajectory fields ``tolerance``,
   ``source`` and ``evidence_id`` have no slot in the frozen batch contract
   (``additionalProperties: false``), so the builder strips them and emits, for each
   executed step, one canonical derived evidence item ``TRAJ {...}`` with the id
   ``E-TRAJ-<batch_id>-<n>``. That trace is what keeps the tolerance boundary
   re-checkable on the frozen artifact.

2. ``<output_path with batch -> sample>`` - the sample record, carrying the label the
   printer actually produced and the custody chain from preparation onward.

The builder never invents a step, a lot, an operator, a deviation, or a label. Values
the caller did not supply stay unsupplied.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from grease_batch_policy import (
    SAMPLE_ARTIFACT_FIELDS,
    expected_decision_fields,
    expected_sample_decision_fields,
    recorded_batch,
    trajectory_trace_id,
    trajectory_trace_line,
)
from preflight_grease_batch import errors_for, resolved_path, schema_artifact


def derived_trace_evidence(batch: dict) -> list[dict]:
    """One canonical evidence item per executed step: the tolerance and verdict trace."""
    evidence: list[dict] = []
    trajectory = batch.get("trajectory")
    steps = trajectory if isinstance(trajectory, list) else []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        evidence.append(
            {
                "evidence_id": trajectory_trace_id(batch.get("batch_id"), index),
                "statement": trajectory_trace_line(index, step, step.get("tolerance")),
                "source": step.get("source"),
                "status": "OBSERVED",
            }
        )
    return evidence


def build_batch_artifact(data: dict, project: dict) -> dict:
    """Assemble the batch artifact. Pure function of validated input + charter."""
    batch = data["batch"]
    evidence_scope = data["evidence_scope"]
    recorded = recorded_batch(batch)
    return {
        "schema_version": "0.1.0",
        "artifact_type": "batch",
        "project_id": project["project_id"],
        "stage": "BATCH_PRODUCED",
        "evidence_scope": evidence_scope,
        **expected_decision_fields(recorded, evidence_scope),
        "evidence": [*data["evidence"], *derived_trace_evidence(batch)],
        **recorded,
    }


def build_sample_artifact(data: dict, project: dict) -> dict:
    """Assemble the sample artifact. The batch binding comes from the batch record."""
    batch = data["batch"]
    sample = data["sample"]
    evidence_scope = data["evidence_scope"]
    return {
        "schema_version": "0.1.0",
        "artifact_type": "sample",
        "project_id": project["project_id"],
        "stage": "BATCH_PRODUCED",
        "evidence_scope": evidence_scope,
        **expected_sample_decision_fields(
            sample, batch["batch_id"], batch.get("batch_verdict"), evidence_scope
        ),
        "evidence": data["evidence"],
        "batch_reference": batch["batch_id"],
        "formula_reference": batch["formula_reference"],
        **{field: sample[field] for field in SAMPLE_ARTIFACT_FIELDS},
    }


def sample_output_path(output_path: Path) -> Path:
    """The sample record that accompanies the batch record.

    The batch record and its sample are two artifacts of the same stage, so the sample
    keeps the batch record's own name with ``batch`` -> ``sample``: ``_tmp_batch.json``
    -> ``_tmp_sample.json`` and the canonical ``batch.json`` -> ``sample.json`` (the
    canonical first-record name the stage-gate panel matches for this type).
    """
    stem = output_path.stem
    if stem.endswith("batch"):
        stem = stem[: -len("batch")] + "sample"
    else:
        stem = stem + ".sample"
    return output_path.with_name(stem + output_path.suffix)


def write_artifact(path: Path, artifact: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_batch_artifact.py <input.json> <temporary-file>")
        return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, input_path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    _, project = schema_artifact(
        resolved_path(data["project_artifact"], input_path), "project.schema.json", "project_artifact"
    )
    batch_artifact = build_batch_artifact(data, project)
    sample_artifact = build_sample_artifact(data, project)
    sample_path = sample_output_path(output_path)
    write_artifact(output_path, batch_artifact)
    write_artifact(sample_path, sample_artifact)
    print(
        f"BUILT: {output_path} stage={batch_artifact['stage']} "
        f"batch_verdict={batch_artifact['batch_verdict']} decision={batch_artifact['decision']}"
    )
    print(
        f"BUILT: {sample_path} stage={sample_artifact['stage']} "
        f"sample_id={sample_artifact['sample_id']} decision={sample_artifact['decision']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
