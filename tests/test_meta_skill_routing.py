"""Runnable checks for the lubricant-rd-agent Meta-Skill router."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTE_SCRIPT = ROOT / "skills/lubricant-rd-agent/scripts/route_step.py"


def load_router():
    spec = importlib.util.spec_from_file_location("route_step", ROUTE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_cli(payload: dict) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "input.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-B", str(ROUTE_SCRIPT), str(path)],
            cwd=ROUTE_SCRIPT.parent,
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout.strip()


def physical_state(stage: str, **overrides) -> dict:
    state = {
        "project_id": "WGO-DOE-001",
        "stage": stage,
        "status": "ACTIVE",
        "evidence_scope": "PHYSICAL",
        "gate_status": "GO",
        "evidence_gaps": [],
        "unsatisfied_conditions": [],
    }
    state.update(overrides)
    return state


def main() -> int:
    router = load_router()

    # 1. ALLOW exactly one stage: PROJECT_DEFINED -> DUTY_DEFINED.
    result = router.decide(physical_state("PROJECT_DEFINED"), "DUTY_DEFINED")
    assert result["decision"] == "ALLOW" and result["skill"] == "duty-definition", result

    # 2. DENY cross-stage jump (skips duty-definition / duty-challenge-analysis).
    result = router.decide(physical_state("PROJECT_DEFINED"), "CHALLENGES_DEFINED")
    assert result["decision"] == "DENY" and "cross-stage" in result["reason"], result
    returncode, stdout = run_cli({"project_state": physical_state("DUTY_DEFINED"), "requested_stage": "FAILURE_CTQ_DEFINED"})
    assert returncode == 1 and "DENY" in stdout and "cross-stage" in stdout, (returncode, stdout)

    # 3. DENY SYNTHETIC advancement even when everything else is satisfied.
    result = router.decide(physical_state("PROJECT_DEFINED", evidence_scope="SYNTHETIC"), "DUTY_DEFINED")
    assert result["decision"] == "DENY" and "SYNTHETIC" in result["reason"], result

    # 4. HOLD when gate is not GO or evidence gaps remain; ALLOW after resolution.
    held = physical_state("DUTY_DEFINED", gate_status="HOLD", evidence_gaps=["bench method characterization missing"])
    result = router.decide(held, "CHALLENGES_DEFINED")
    assert result["decision"] == "HOLD" and "bench method characterization missing" in result["reason"], result
    resolved = physical_state("DUTY_DEFINED", gate_status="GO", evidence_gaps=[])
    result = router.decide(resolved, "CHALLENGES_DEFINED")
    assert result["decision"] == "ALLOW" and result["skill"] == "duty-challenge-analysis", result

    # 5. Terminal project status cannot advance.
    result = router.decide(physical_state("OPTIMIZED", status="FROZEN"), "VERIFIED")
    assert result["decision"] == "DENY" and "terminal" in result["reason"], result

    # 6. Last routed stage has no further step.
    result = router.decide(physical_state("VERIFIED"), "FROZEN")
    assert result["decision"] == "DENY", result

    # 7. DRAFT -> PROJECT_DEFINED is the single allowed first step.
    result = router.decide(physical_state("DRAFT"), "PROJECT_DEFINED")
    assert result["decision"] == "ALLOW" and result["skill"] == "project-definition", result

    # 8. CLI happy path: ALLOW exits 0 and names the target skill.
    returncode, stdout = run_cli({"project_state": physical_state("PROJECT_DEFINED"), "requested_stage": "DUTY_DEFINED"})
    assert returncode == 0 and "ALLOW" in stdout and "duty-definition" in stdout, (returncode, stdout)

    print(f"PASS: lubricant-rd-agent router ALLOW/DENY/HOLD contract ({len(ROUTE_TABLE_REF)} routable stages)")
    return 0


ROUTE_TABLE_REF = ("PROJECT_DEFINED", "DUTY_DEFINED", "CHALLENGES_DEFINED", "FAILURE_CTQ_DEFINED", "TEST_METHODS_QUALIFIED", "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING", "MODEL_BUILT", "OPTIMIZED", "VERIFIED")


if __name__ == "__main__":
    raise SystemExit(main())
