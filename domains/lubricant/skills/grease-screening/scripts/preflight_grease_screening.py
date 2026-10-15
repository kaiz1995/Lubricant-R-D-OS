"""Reject incomplete grease-screening input before a screening artifact is built.

Stage 10 (grease-screening) is the first rework point of the inner loop. The bench is the
bottleneck - about 2 positions per round and roughly 30 days per round - so this gate
exists to stop obviously-unqualified samples from ever consuming a bench slot. It is
fail-closed on four fronts:

* the upstream batch record must be a RELEASED ``BATCH_PRODUCED`` record. A sample whose
  batch is DEVIATED or VOID has not been dispositioned, so screening it would spend lab
  time on an unreleased sample and quietly move it towards the bench;
* the screening record itself must be judgeable: the derived fields must not be supplied,
  every declared index must carry a verdict, and the required indices must be present;
* a bench request for the screened sample is refused outright when the screen did not
  clear it. That is N14 of the batch-2 acceptance list: screening is the bench's
  precondition;
* a sample record, when supplied, must be the sample the batch produced and the sample the
  screen ran on.

The screen is a GATE, never a selection criterion: physical/chemical indices usually have
low discrimination power between close candidate formulas, so a PASS means only "not
obviously unqualified". This preflight prints that limitation on every run so it cannot be
forgotten.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from grease_screening_policy import (
    EVIDENCE_FIELDS,
    EVIDENCE_SCOPES,
    EVIDENCE_STATUSES,
    INPUT_FIELDS,
    REQUIRED_INPUT_FIELDS,
    derived_gate,
    derived_overall_verdict,
    gate_blockers,
    has_text,
    low_discrimination_notes,
    screen_coverage_notes,
    screening_errors,
    test_notes,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_NAMES = (
    "common.schema.json",
    "project.schema.json",
    "batch.schema.json",
    "sample.schema.json",
    "screening.schema.json",
)
UPSTREAM_REQUIREMENTS = (
    ("project_artifact", "project.schema.json", "PROJECT_DEFINED"),
    ("batch_artifact", "batch.schema.json", "BATCH_PRODUCED"),
)
OPTIONAL_ARTIFACT_REQUIREMENTS = (("sample_artifact", "sample.schema.json", "BATCH_PRODUCED"),)
ROUTED_PROJECT_TYPE = "PRECISION_GREASE_DEV"
REROUTE_HINT = (
    "the physical/chemical screen is the PRECISION_GREASE_DEV inner loop (step 10); on the oil "
    "routes this stage does not exist"
)
# N14 of the batch-2 acceptance list: a screen that did not clear the sample cannot request a
# bench slot, because the bench is the scarcest resource of the inner loop.
N14_HOLD = (
    "bench_request refused: the screen did not clear this sample, so it must not consume a bench "
    "slot; screening is the bench's precondition (N14) and a failed sample goes back to Stage 9 "
    "(grease-batch) instead"
)


def _ensure_naming_checker_importable() -> None:
    """Make the shared naming checker importable in both layouts.

    Repository layout: the module lives in the pack-level ``scripts/`` tree.
    Deployed layout: the installer copies it beside this skill's scripts
    (install_domain_skill.py maps grease-screening -> check_artifact_naming.py).
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
    return errors


def batch_release_errors(batch: object) -> list[str]:
    """An unreleased batch has no screenable sample: fail closed on DEVIATED / VOID."""
    if not isinstance(batch, dict):
        return []
    verdict = batch.get("batch_verdict")
    if verdict == "VALID":
        return []
    return [
        f"batch_artifact.batch_verdict is {verdict}: a sample from an unreleased batch is not screenable, "
        "because the recorded deviation has not been dispositioned yet (Stage 9 holds)"
    ]


def sample_linkage_errors(sample: object, batch: object, screening: object) -> list[str]:
    """The screened sample must be the sample the batch record produced."""
    if not isinstance(sample, dict):
        return []
    errors: list[str] = []
    if isinstance(batch, dict) and sample.get("batch_reference") != batch.get("batch_id"):
        errors.append(
            f"sample_artifact.batch_reference {sample.get('batch_reference')!r} must equal "
            f"batch_artifact.batch_id {batch.get('batch_id')!r}"
        )
    if isinstance(screening, dict):
        sample_reference = screening.get("sample_reference")
        if has_text(sample_reference) and sample.get("sample_id") != sample_reference:
            errors.append(
                f"screening.sample_reference {sample_reference!r} must equal sample_artifact.sample_id "
                f"{sample.get('sample_id')!r}: the screen must be bound to the physical sample it ran on"
            )
    return errors


def bench_request_errors(bench_request: object, screening: object) -> list[str]:
    """N14: a sample whose screen did not clear it must not be requested for the bench."""
    if not has_text(bench_request):
        return ["bench_request must be a non-empty sample reference"]
    if not isinstance(screening, dict):
        return []
    sample_reference = screening.get("sample_reference")
    if has_text(sample_reference) and bench_request != sample_reference:
        return [
            f"bench_request {bench_request!r} must be the screened sample {sample_reference!r}: a bench slot "
            "is requested for a sample that was actually screened"
        ]
    tests = screening.get("tests")
    verdict = derived_overall_verdict(tests)
    if verdict is None:
        return []
    if verdict == "FAIL" or derived_gate(verdict) == "BLOCKED":
        return [
            N14_HOLD
            + f" (worst per-test verdict={verdict})"
        ]
    return []


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if not REQUIRED_INPUT_FIELDS <= set(data) <= INPUT_FIELDS:
        extra = sorted(set(data) - INPUT_FIELDS)
        missing = sorted(REQUIRED_INPUT_FIELDS - set(data))
        return [
            "input must contain only the grease-screening input fields; "
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
        if artifact is not None and artifact.get("decision") != "GO":
            errors.append(f"{key} must have decision GO")
    for key, schema, stage in OPTIONAL_ARTIFACT_REQUIREMENTS:
        if key not in data:
            artifacts[key] = None
            continue
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
    batch = artifacts.get("batch_artifact")
    sample = artifacts.get("sample_artifact")
    screening = data.get("screening")
    if project is not None and project.get("status") != "ACTIVE":
        errors.append("project_artifact must have status ACTIVE")
    present = [item for item in (project, batch, sample) if item is not None]
    if len(present) >= 2 and len({item.get("project_id") for item in present}) != 1:
        errors.append("project, batch, and sample project_id values must match")
    errors.extend(batch_release_errors(batch))
    if data.get("evidence_scope") not in EVIDENCE_SCOPES:
        errors.append("evidence_scope must be SYNTHETIC or PHYSICAL")
    errors.extend(evidence_errors(data.get("evidence")))
    errors.extend(screening_errors(screening))
    errors.extend(sample_linkage_errors(sample, batch, screening))
    if "bench_request" in data:
        errors.extend(bench_request_errors(data.get("bench_request"), screening))
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
    screening = data.get("screening") if isinstance(data, dict) else None
    if not isinstance(screening, dict):
        return []
    tests = screening.get("tests")
    verdict = derived_overall_verdict(tests)
    gate = derived_gate(verdict) if verdict else None
    screening_id = screening.get("screening_id")
    sample_reference = screening.get("sample_reference")
    # Judge the recorded verdict the artifact will carry, not whatever the caller declared:
    # the derived fields are never supplied, so the judgement is built from the tests.
    judged = {
        "screening_id": screening_id,
        "sample_reference": sample_reference,
        "tests": tests,
        "overall_verdict": verdict,
        "gate_to_bench": gate,
    }
    blockers = gate_blockers(judged)
    lines = [
        f"GATE: screening {screening_id} worst per-test verdict={verdict} -> gate_to_bench={gate} "
        f"-> decision {'HOLD' if blockers else 'GO'}"
    ]
    if blockers:
        lines.append(f"GATE: {'; '.join(blockers)}")
    else:
        lines.append(
            f"GATE: sample {sample_reference} is not obviously unqualified; it may enter the bench queue, "
            "and this gate result is not a selection claim about it"
        )
    return lines


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_grease_screening.py <input.json>")
        return 1
    input_path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, input_path)
    screening = data.get("screening") if isinstance(data, dict) else None
    for line in low_discrimination_notes():
        print(line)
    for note in test_notes(screening):
        print(note)
    for note in screen_coverage_notes(screening):
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
    print("READY: input can form one SCREENING_PASSED record only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
