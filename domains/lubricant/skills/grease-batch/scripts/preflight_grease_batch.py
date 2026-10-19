"""Reject incomplete grease-batch input before a batch or sample artifact is built.

Stage 9 (grease-batch) is where "recipe + process = product" lands: the batch record is
the only place where a setpoint-versus-actual deviation can be judged against the product
that resulted. This gate is fail-closed. The three upstream artifacts (design space,
experiment design, and the project charter behind them) are validated structurally, the
trajectory is checked step by step, and every parameter must carry its own provenance.
A process parameter without ``source`` or ``evidence_id`` is a hard reject, not a
warning.

A missing process parameter is NOT an input error. The trajectory records only what was
actually executed; a step the batch did not run stays unrecorded and is reported as a
NOTE, because inventing a trajectory value is the one failure this preflight exists to
prevent (red line NO Invented Process Data).

Both a batch record and a sample record are produced from one request, because a sample
is a physical portion of the batch and cannot be identified without it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from grease_batch_policy import (
    BATCH_INPUT_FIELDS,
    EVIDENCE_FIELDS,
    EVIDENCE_SCOPES,
    EVIDENCE_STATUSES,
    INPUT_FIELDS,
    TRACE_EVIDENCE_PREFIX,
    batch_errors,
    batch_verdict_errors,
    gate_blockers,
    has_text,
    route_coverage_notes,
    sample_errors,
    step_notes,
    trajectory_errors,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = (
    "common.schema.json",
    "project.schema.json",
    "design_space.schema.json",
    "experiment_design.schema.json",
    "batch.schema.json",
    "sample.schema.json",
)
UPSTREAM_REQUIREMENTS = (
    ("project_artifact", "project.schema.json", "PROJECT_DEFINED"),
    ("design_space_artifact", "design_space.schema.json", "DESIGN_SPACE_DEFINED"),
    ("experiment_design_artifact", "experiment_design.schema.json", "EXPERIMENT_DESIGNED"),
)
ROUTED_PROJECT_TYPE = "PRECISION_GREASE_DEV"
REROUTE_HINT = "the batch record is the PRECISION_GREASE_DEV inner loop (step 9); on the oil routes this stage does not exist"


def _ensure_naming_checker_importable() -> None:
    """Make the shared naming checker importable in both layouts.

    Repository layout: the module lives in the pack-level ``scripts/`` tree.
    Deployed layout: the installer copies it beside this skill's scripts
    (install_domain_skill.py maps grease-batch -> check_artifact_naming.py).
    Probe both candidates and pin the first that actually contains the file; never
    inline a second copy. If neither holds it the gate cannot enforce the canonical
    artifact-name contract, so it raises rather than running with the contract
    silently unenforced.
    """
    for candidate in (SKILL_ROOT / "scripts", SKILL_ROOT.parents[1] / "scripts"):
        if (candidate / "check_artifact_naming.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return
    raise ImportError(
        "check_artifact_naming.py not found beside the skill scripts or in the pack scripts/ directory"
    )


_ensure_naming_checker_importable()

import check_artifact_naming  # noqa: E402


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def workspace_naming_errors(input_path: Path) -> list[str]:
    """Enforce the canonical-name contract on the workspace holding the input.

    The request file lives in the workspace root, so ``input_path.parent`` is the
    workspace. A bare staging directory without ``project.json`` is not treated as a
    workspace (keeps ad-hoc preflight invocations working). A mangled artifact name is
    invisible to the stage-gate panel, so every violation here is a HOLD.
    """
    workspace = input_path.parent
    if not (workspace / "project.json").is_file():
        return []
    try:
        _, violations = check_artifact_naming.check_workspace(str(workspace))
    except OSError:
        return []
    return [f"workspace naming: {violation}" for violation in violations]


def schema_artifact(path: Path, name: str, label: str) -> tuple[list[str], dict | None]:
    """Validate one upstream artifact against its own schema. Fail-closed on read errors."""
    try:
        schemas = schema_dir()
        loaded = {item: json.loads((schemas / item).read_text(encoding="utf-8")) for item in SCHEMA_NAMES}
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [
        f"{label}: {error.message}"
        for error in Draft202012Validator(loaded[name], registry=registry).iter_errors(artifact)
    ]
    return errors, artifact if not errors else None


def evidence_errors(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["evidence"]
    errors: list[str] = []
    for index, item in enumerate(value):
        label = f"evidence[{index}]"
        if not isinstance(item, dict) or set(item) != EVIDENCE_FIELDS:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"{label}.status")
        evidence_id = item.get("evidence_id")
        if has_text(evidence_id) and str(evidence_id).startswith(TRACE_EVIDENCE_PREFIX):
            errors.append(
                f"{label}.evidence_id {evidence_id} uses the reserved derived-trace prefix "
                f"{TRACE_EVIDENCE_PREFIX}; the trajectory trace ids are generated by the builder"
            )
    return errors


def resolved_evidence_ids(evidence: object) -> set[str]:
    if not isinstance(evidence, list):
        return set()
    return {
        item["evidence_id"]
        for item in evidence
        if isinstance(item, dict) and has_text(item.get("evidence_id")) and item.get("status") != "GAP"
    }


def batch_errors_for(data: dict) -> list[str]:
    """Every batch-side reason this request is not recordable. Empty list = it is."""
    batch = data.get("batch")
    if not isinstance(batch, dict):
        return ["batch must be an object"]
    unknown = sorted(set(batch) - BATCH_INPUT_FIELDS)
    missing = sorted(BATCH_INPUT_FIELDS - set(batch))
    if unknown or missing:
        return [
            "batch must contain only the batch-record input fields; "
            f"unexpected={unknown or 'none'} missing={missing or 'none'}"
        ]
    errors = batch_errors(batch)
    errors.extend(trajectory_errors(batch.get("trajectory"), resolved_evidence_ids(data.get("evidence"))))
    errors.extend(batch_verdict_errors(batch))
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != INPUT_FIELDS:
        extra = sorted(set(data) - INPUT_FIELDS)
        missing = sorted(INPUT_FIELDS - set(data))
        return [
            "input must contain only the grease-batch input fields; "
            f"unexpected={extra or 'none'} missing={missing or 'none'}"
        ]
    errors: list[str] = []
    artifacts: dict[str, dict | None] = {}
    for key, schema, stage in UPSTREAM_REQUIREMENTS:
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
    project = artifacts.get("project_artifact")
    design_space = artifacts.get("design_space_artifact")
    experiment_design = artifacts.get("experiment_design_artifact")
    if project is not None and project.get("status") != "ACTIVE":
        errors.append("project_artifact must have status ACTIVE")
    present = [item for item in (project, design_space, experiment_design) if item is not None]
    if len(present) == 3 and len({item.get("project_id") for item in present}) != 1:
        errors.append("project, design_space, and experiment_design project_id values must match")
    if experiment_design is not None and design_space is not None:
        if experiment_design.get("design_space_reference") != design_space.get("design_space_id"):
            errors.append(
                "experiment_design_artifact.design_space_reference must equal "
                "design_space_artifact.design_space_id"
            )
    if experiment_design is not None:
        run_plan = experiment_design.get("run_plan")
        if not isinstance(run_plan, dict) or not isinstance(run_plan.get("target_count"), int):
            errors.append("experiment_design_artifact.run_plan.target_count must be an integer")
    if data.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("evidence_scope must be SYNTHETIC or PHYSICAL")
    errors.extend(evidence_errors(data.get("evidence")))
    batch = data.get("batch")
    errors.extend(batch_errors_for(data))
    errors.extend(sample_errors(data.get("sample"), batch if isinstance(batch, dict) else {}))
    errors.extend(workspace_naming_errors(input_path))
    return errors


def project_type_notes(project: dict | None) -> list[str]:
    """A non-precision route is legal but worth saying out loud (never a HOLD)."""
    if not isinstance(project, dict):
        return []
    project_type = project.get("project_type")
    if project_type == ROUTED_PROJECT_TYPE:
        return []
    return [f"NOTE: project_type={project_type} is not {ROUTED_PROJECT_TYPE}; {REROUTE_HINT}"]


def gate_lines(data: dict) -> list[str]:
    """The release rule, computed deterministically so the caller sees it up front."""
    batch = data.get("batch") if isinstance(data, dict) else None
    if not isinstance(batch, dict):
        return []
    blockers = gate_blockers(batch)
    verdict = batch.get("batch_verdict")
    batch_id = batch.get("batch_id")
    sample = data.get("sample") if isinstance(data, dict) else None
    sample_id = sample.get("sample_id") if isinstance(sample, dict) else None
    if blockers:
        return [
            f"GATE: batch {batch_id} batch_verdict={verdict} -> decision HOLD; "
            f"{'; '.join(blockers)}; sample {sample_id} must not leave Stage 9 and Stage 10 must not proceed"
        ]
    return [
        f"GATE: batch {batch_id} batch_verdict=VALID -> decision GO; sample {sample_id} may be routed "
        "to Stage 10 (grease-screening) before it may consume a bench slot"
    ]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_grease_batch.py <input.json>")
        return 1
    input_path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, input_path)
    batch = data.get("batch") if isinstance(data, dict) else None
    for note in step_notes(batch):
        print(note)
    for note in route_coverage_notes(batch):
        print(note)
    for line in gate_lines(data):
        print(line)
    project_path = resolved_path(data.get("project_artifact"), input_path) if isinstance(data, dict) else None
    project = None
    if project_path is not None and project_path.is_file():
        try:
            project = json.loads(project_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            project = None
    for note in project_type_notes(project):
        print(note)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    print("READY: input can form one BATCH_PRODUCED record and its sample record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
