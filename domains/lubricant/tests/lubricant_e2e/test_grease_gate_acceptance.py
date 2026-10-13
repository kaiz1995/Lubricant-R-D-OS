"""Focused acceptance for the precision-grease route's step 14 at VERIFIED.

The route's step-14 optimization artifact legally lands at
``NON_INFERIORITY_PASSED`` (``schemas/optimization.schema.json`` enumerates both
that value and the oil routes' ``OPTIMIZED``). Two cross-artifact consumers used
to pin the single constant ``OPTIMIZED`` and therefore refused the route's own
legal artifact. Recorded BEFORE the fix, with this file's fixtures:

  * ``skills/gate-review/scripts/preflight_gate_review.py``
    ``HOLD: missing or invalid: optimization_artifact must be stage OPTIMIZED; no artifact generated``
  * ``scripts/audit_chain.py``
    ``FAIL optimization.json: stage is 'NON_INFERIORITY_PASSED', consumers require 'OPTIMIZED'``

The fix dispatches the expected stage on the charter's ``project_type``. This
file pins the before/after behaviour of both consumers and the oil-route
counter-controls that prove nothing was loosened:

  1. gate-review over the grease fixture chain (canonical names, real schemas):
     preflight READY -> build -> validate PASS, the before-fix refusal text is
     gone, and the emitted gate is still HOLD with the chain's SYNTHETIC scope
     (the widening must not open a synthetic path to GO);
  2. gate-review over the SAME chain with only ``project_type`` flipped to an
     oil type: refuses with exactly the before-fix text;
  3. audit_chain over the grease workspace: exit 0, zero problems;
  4. audit_chain over the same workspace with ``project_type`` flipped to an oil
     type and the stage kept at ``NON_INFERIORITY_PASSED``: exactly that one
     violation remains;
  5. audit_chain over the oil-type workspace with ``stage`` ``OPTIMIZED``:
     exit 0 (the oil requirement's positive direction is intact);
  6. the pack's own oil-route gate-review request fixtures keep their recorded
     exit codes, and the canonical one keeps its stdout byte for byte;
  7. an undecidable charter (absent / unreadable / oil type) still yields
     ``OPTIMIZED`` from both dispatch helpers.

Fixtures are the pack's recorded grease chain (``fixtures/optimization/`` and
``fixtures/process-scale-up/``) plus the pack's oil gate-review fixtures; the
only in-test mutation is the labelled ``project_type`` / ``stage`` flip that
builds each control, so no domain data is invented here.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
GATE_SCRIPTS = ROOT / "skills" / "gate-review" / "scripts"
PREFLIGHT = GATE_SCRIPTS / "preflight_gate_review.py"
AUDIT = ROOT / "scripts" / "audit_chain.py"
OIL_GATE_FIXTURES = FIXTURES / "gate-review"

GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"
OIL_PROJECT_TYPE = "NEW_PRODUCT"
GREASE_STAGE = "NON_INFERIORITY_PASSED"

# The two exact refusals recorded before the fix (see the module docstring).
BEFORE_FIX_GATE_ERROR = (
    "HOLD: missing or invalid: optimization_artifact must be stage OPTIMIZED; no artifact generated"
)
BEFORE_FIX_AUDIT_PROBLEM = (
    "optimization.json: stage is 'NON_INFERIORITY_PASSED', consumers require 'OPTIMIZED'"
)

# canonical target name -> pack fixture holding that artifact for the grease chain
GREASE_CHAIN = {
    "project.json": FIXTURES / "optimization" / "project-grease-active.json",
    "challenge.json": FIXTURES / "optimization" / "challenge-grease.json",
    "failure_ctq.json": FIXTURES / "optimization" / "failure-ctq-grease.json",
    "test_method.json": FIXTURES / "optimization" / "test-method-grease.json",
    "design_space.json": FIXTURES / "optimization" / "design-space-grease.json",
    "experiment_design.json": FIXTURES / "optimization" / "experiment-design-grease.json",
    "experiment.json": FIXTURES / "optimization" / "experiment-grease.json",
    "model.json": FIXTURES / "optimization" / "model-grease.json",
    "optimization.json": FIXTURES / "process-scale-up" / "optimization-grease.json",
}

# The request keys of the gate preflight, in the pack's canonical spelling.
UPSTREAM_KEYS = {
    "project_artifact": "project.json",
    "challenge_artifact": "challenge.json",
    "failure_ctq_artifact": "failure_ctq.json",
    "test_method_artifact": "test_method.json",
    "design_space_artifact": "design_space.json",
    "experiment_design_artifact": "experiment_design.json",
    "experiment_artifact": "experiment.json",
    "model_artifact": "model.json",
    "optimization_artifact": "optimization.json",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: Path, *arguments: object) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", script.name, *map(str, arguments)],
        cwd=script.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def chain_workspace(root: Path, project_type: str, optimization_stage: str | None = None) -> Path:
    """Copy the pack's grease chain into ``root`` under canonical names.

    ``project_type`` and ``optimization_stage`` are the two labelled control
    dials: the grease fixture bytes are otherwise untouched.
    """
    root.mkdir(parents=True, exist_ok=True)
    for name, source in GREASE_CHAIN.items():
        data = read_json(source)
        if name == "project.json":
            data["project_type"] = project_type
        if name == "optimization.json" and optimization_stage is not None:
            data["stage"] = optimization_stage
        write_json(root / name, data)
    return root


def gate_request(root: Path, gate_status: str = "HOLD") -> Path:
    request = {**UPSTREAM_KEYS, "gate": {
        "gate_id": "GATE-PGD-E2E-014",
        "scope": "step-14 gate acceptance over the pack's grease chain",
        "gate_status": gate_status,
        "satisfied_conditions": ["the fixture chain is linked and at GO"],
        "unsatisfied_conditions": [],
        "evidence_gaps": [],
        "risks": ["synthetic fixtures do not establish product performance"],
        "reason": "synthetic replay only; SYNTHETIC scope permits HOLD only",
        "evidence": [{
            "evidence_id": "E-G-PGD-014",
            "statement": "synthetic replay evidence for the step-14 gate acceptance",
            "source": "synthetic",
            "status": "OBSERVED",
        }],
    }}
    path = root / "input-gate.json"
    write_json(path, request)
    return path


def audit_problem_lines(stdout: str) -> list[str]:
    """The audit's problem statements, without the 'FAIL' bullet prefix."""
    problems = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("FAIL "):
            problems.append(stripped[len("FAIL "):])
    return problems


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def grease_gate_is_accepted() -> None:
    """1. gate-review READY -> build -> validate over the route's own chain."""
    with tempfile.TemporaryDirectory() as temporary:
        root = chain_workspace(Path(temporary) / "grease", GREASE_PROJECT_TYPE)
        request = gate_request(root)

        preflight = run(PREFLIGHT, request)
        assert preflight.returncode == 0, preflight.stdout + preflight.stderr
        assert preflight.stdout.strip() == "READY: input can form one VERIFIED Gate artifact only", (
            preflight.stdout
        )
        assert BEFORE_FIX_GATE_ERROR not in preflight.stdout, preflight.stdout

        gate_path = root / "gate.json"
        built = run(GATE_SCRIPTS / "build_gate_artifact.py", request, gate_path)
        assert built.returncode == 0, built.stdout + built.stderr
        validated = run(GATE_SCRIPTS / "validate_gate_artifact.py", gate_path)
        assert validated.returncode == 0, validated.stdout + validated.stderr
        assert validated.stdout.startswith("PASS:"), validated.stdout
        gate = read_json(gate_path)
        assert gate["stage"] == "VERIFIED", gate["stage"]
        # Fail-closed is intact: the fixture chain is SYNTHETIC, so the widening
        # of the optimization stage may not lift the disposition above HOLD.
        assert gate["gate_status"] == "HOLD", gate["gate_status"]
        assert gate["evidence_scope"] == "SYNTHETIC", gate["evidence_scope"]
    print("PASS: grease step-14 gate is accepted (READY -> BUILT -> PASS) and stays HOLD on SYNTHETIC scope")


def oil_route_still_requires_optimized() -> None:
    """2. The same chain under an oil project type keeps the before-fix refusal."""
    with tempfile.TemporaryDirectory() as temporary:
        root = chain_workspace(Path(temporary) / "oil_control", OIL_PROJECT_TYPE)
        request = gate_request(root)
        preflight = run(PREFLIGHT, request)
        assert preflight.returncode == 1, preflight.stdout
        assert preflight.stdout.strip() == BEFORE_FIX_GATE_ERROR, preflight.stdout
    print("PASS: oil project type still refuses NON_INFERIORITY_PASSED with the recorded pre-fix text")


def grease_audit_is_clean() -> None:
    """3. audit_chain over the grease workspace: zero violations."""
    with tempfile.TemporaryDirectory() as temporary:
        root = chain_workspace(Path(temporary) / "grease", GREASE_PROJECT_TYPE)
        audit = run(AUDIT, root)
        assert "chain audit over 9 artifacts" in audit.stdout, audit.stdout + audit.stderr
        problems = audit_problem_lines(audit.stdout)
        assert problems == [], audit.stdout
        assert BEFORE_FIX_AUDIT_PROBLEM not in audit.stdout, audit.stdout
        assert audit.returncode == 0, audit.stdout + audit.stderr
    print("PASS: audit_chain reports zero violations for the grease NON_INFERIORITY_PASSED artifact")


def oil_audit_still_flags_noninferiority() -> None:
    """4./5. The oil requirement is not loosened, and its OPTIMIZED path is clean."""
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        non_inferior = chain_workspace(base / "oil_noninferiority", OIL_PROJECT_TYPE)
        audit = run(AUDIT, non_inferior)
        assert audit.returncode == 1, audit.stdout
        assert audit_problem_lines(audit.stdout) == [BEFORE_FIX_AUDIT_PROBLEM], audit.stdout

        optimized = chain_workspace(base / "oil_optimized", OIL_PROJECT_TYPE, "OPTIMIZED")
        clean = run(AUDIT, optimized)
        assert clean.returncode == 0, clean.stdout + clean.stderr
        assert audit_problem_lines(clean.stdout) == [], clean.stdout
    print("PASS: oil workspace still flags the same stage mismatch, and its OPTIMIZED path stays clean")


def oil_gate_fixtures_unchanged() -> None:
    """6. The pack's own oil-route gate-review requests keep their recorded result."""
    recorded = {
        "valid-input.synthetic.json": 1,
        "hold-from-unsatisfied.synthetic.json": 1,
        "invalid-gap-evidence.json": 1,
        "invalid-go-unsatisfied.json": 1,
        "invalid-missing-optimization.json": 1,
        "invalid-pivot-no-reason.json": 1,
    }
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for source in sorted(OIL_GATE_FIXTURES.glob("*.json")):
            shutil.copyfile(source, root / source.name)
        for name, expected in recorded.items():
            result = run(PREFLIGHT, root / name)
            assert result.returncode == expected, f"{name}: {result.returncode}\n{result.stdout}"
            # The oil fixtures' optimization artifact is OPTIMIZED, so no stage
            # complaint may appear on any oil request.
            assert "must be stage" not in result.stdout, f"{name}: {result.stdout}"
        # The canonical oil request keeps its pre-change stdout byte for byte.
        canonical = run(PREFLIGHT, root / "valid-input.synthetic.json")
        assert canonical.stdout.strip() == (
            "HOLD: missing or invalid: test_method_artifact must have decision GO, "
            "experiment_design_artifact must have decision GO, experiment_artifact must have decision GO, "
            "model_artifact must have decision GO, optimization_artifact must have decision GO, "
            "test_method_artifact must be linked and qualified, "
            "SYNTHETIC evidence_scope permits Gate HOLD workflow validation only; no artifact generated"
        ), canonical.stdout
    print("PASS: the six oil gate-review requests keep their recorded outcomes byte for byte")


def undecidable_charter_keeps_optimized() -> None:
    """7. No readable project_type -> both dispatch helpers keep the original constant."""
    skill_scripts = str(PREFLIGHT.parent)
    sys.path.insert(0, skill_scripts)
    try:
        preflight = load_module("pg_gate_preflight_acceptance", PREFLIGHT)
        assert preflight.expected_stage("optimization_artifact", "OPTIMIZED", None) == "OPTIMIZED"
        assert preflight.expected_stage("optimization_artifact", "OPTIMIZED", {}) == "OPTIMIZED"
        assert preflight.expected_stage("optimization_artifact", "OPTIMIZED", {"project_type": OIL_PROJECT_TYPE}) == "OPTIMIZED"
        assert preflight.expected_stage("optimization_artifact", "OPTIMIZED", {"project_type": GREASE_PROJECT_TYPE}) == GREASE_STAGE
        # The dispatch is scoped to the one step-14 key: every other key keeps
        # its constant even on the grease route.
        assert preflight.expected_stage("model_artifact", "MODEL_BUILT", {"project_type": GREASE_PROJECT_TYPE}) == "MODEL_BUILT"
    finally:
        sys.path.remove(skill_scripts)
        sys.modules.pop("pg_gate_preflight_acceptance", None)

    audit = load_module("pg_audit_chain_acceptance", AUDIT)
    assert audit.expected_stage("OPTIMIZED", "optimization", None) == "OPTIMIZED"
    assert audit.expected_stage("OPTIMIZED", "optimization", OIL_PROJECT_TYPE) == "OPTIMIZED"
    assert audit.expected_stage("OPTIMIZED", "optimization", GREASE_PROJECT_TYPE) == GREASE_STAGE
    assert audit.expected_stage("MODEL_BUILT", "model", GREASE_PROJECT_TYPE) == "MODEL_BUILT"
    sys.modules.pop("pg_audit_chain_acceptance", None)
    print("PASS: an undecidable charter keeps OPTIMIZED in both consumers; the dispatch is one kind wide")


def main() -> int:
    grease_gate_is_accepted()
    oil_route_still_requires_optimized()
    grease_audit_is_clean()
    oil_audit_still_flags_noninferiority()
    oil_gate_fixtures_unchanged()
    undecidable_charter_keeps_optimized()
    print("PASS: precision-grease step 14 accepted by gate-review and audit_chain; oil routes unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
