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
        return run_cli_args(str(path))


def run_cli_args(*arguments: str) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-B", str(ROUTE_SCRIPT), *arguments],
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

    # 9. Differentiated project_type workflows
    # COST_DOWN routes PROJECT_DEFINED directly to FAILURE_CTQ_DEFINED
    result = router.decide(physical_state("PROJECT_DEFINED", project_type="COST_DOWN"), "FAILURE_CTQ_DEFINED")
    assert result["decision"] == "ALLOW" and result["skill"] == "failure-ctq-analysis", result
    # EXPLORATION routes PROJECT_DEFINED directly to DESIGN_SPACE_DEFINED
    result = router.decide(physical_state("PROJECT_DEFINED", project_type="EXPLORATION"), "DESIGN_SPACE_DEFINED")
    assert result["decision"] == "ALLOW" and result["skill"] == "formulation-design", result
    # IMPROVEMENT routes PROJECT_DEFINED directly to FAILURE_CTQ_DEFINED
    result = router.decide(physical_state("PROJECT_DEFINED", project_type="IMPROVEMENT"), "FAILURE_CTQ_DEFINED")
    assert result["decision"] == "ALLOW" and result["skill"] == "failure-ctq-analysis", result

    # 10. A DECLARED project_type with no routed chain is DENIED (fail-closed),
    #     never silently handed the full NEW_PRODUCT chain. The pack documents
    #     exactly six workflows (README §5, project-definition/SKILL.md) and
    #     project.schema.json enumerates the same six, so anything else is a
    #     contract violation. A missing project_type still runs the full chain
    #     for pre-existing state.
    result = router.decide(physical_state("PROJECT_DEFINED", project_type="CORRECTIVE_ACTION"), "DUTY_DEFINED")
    assert result["decision"] == "DENY" and "no routed stage chain" in result["reason"], result
    result = router.decide(physical_state("PROJECT_DEFINED", project_type="NOT_A_TYPE"), "DUTY_DEFINED")
    assert result["decision"] == "DENY" and "no routed stage chain" in result["reason"], result
    # A MISSING project_type still runs the full chain (pre-existing state).
    result = router.decide(physical_state("PROJECT_DEFINED"), "DUTY_DEFINED")
    assert result["decision"] == "ALLOW" and result["skill"] == "duty-definition", result

    # 11. The differentiated routes are published by the shared contract (the
    #     same list validate_state_machine.py uses for GO adjacency), and the
    #     router's own skill table agrees with the contract's NEW_PRODUCT route.
    contract = json.loads((ROOT / "contracts" / "state-machine.json").read_text(encoding="utf-8"))
    assert router.CONTRACT is not None, router.CONTRACT_ERRORS
    assert router.TYPE_ROUTES == contract["type_routes"], router.TYPE_ROUTES
    assert router.TYPE_ROUTES["NEW_PRODUCT"] == list(router.STAGES), router.STAGES
    assert tuple(router.KNOWN_STAGES) == tuple(contract["stages"]), router.KNOWN_STAGES
    assert len(router.KNOWN_STAGES) == 15, router.KNOWN_STAGES
    assert router.STAGES == ROUTE_TABLE_REF, router.STAGES
    assert router.SKILL_FOR_STAGE["PROCESS_WINDOW_DEFINED"] == "process-scale-up", router.SKILL_FOR_STAGE
    assert router.NEXT_STAGE["OPTIMIZED"] == "PROCESS_WINDOW_DEFINED", router.NEXT_STAGE

    # 12. OPTIMIZED now advances to PROCESS_WINDOW_DEFINED, then to VERIFIED.
    result = router.decide(physical_state("OPTIMIZED"), "PROCESS_WINDOW_DEFINED")
    assert result["decision"] == "ALLOW" and result["skill"] == "process-scale-up", result
    result = router.decide(physical_state("PROCESS_WINDOW_DEFINED"), "VERIFIED")
    assert result["decision"] == "ALLOW" and result["skill"] == "gate-review", result

    # 13. Route-aware jumps: the same request is legal in COST_DOWN and illegal in
    #     NEW_PRODUCT, because the chains differ per project type.
    result = router.decide(physical_state("EXPERIMENT_RUNNING", project_type="COST_DOWN"), "OPTIMIZED")
    assert result["decision"] == "ALLOW" and result["skill"] == "optimization", result
    result = router.decide(physical_state("EXPERIMENT_RUNNING", project_type="NEW_PRODUCT"), "OPTIMIZED")
    assert result["decision"] == "DENY" and "cross-stage" in result["reason"], result

    # 14. A project type whose chain has no process-window stage cannot be handed it.
    result = router.decide(physical_state("EXPERIMENT_RUNNING", project_type="CUSTOMIZATION"), "PROCESS_WINDOW_DEFINED")
    assert result["decision"] == "DENY" and "VERIFIED" in result["reason"], result

    # 15. WP-03 sixth route: PROCESS_ROBUSTNESS is published by the contract and
    #     reaches PROCESS_WINDOW_DEFINED straight off MODEL_BUILT (no OPTIMIZED).
    #     The route's final stage APPLIED is not a router stage until WP-06, so it
    #     appears in the printed sequence but cannot be requested yet.
    assert len(router.TYPE_ROUTES) == 6, router.TYPE_ROUTES
    assert tuple(router.TYPE_ROUTES["PROCESS_ROBUSTNESS"]) == PROCESS_ROBUSTNESS_REF, router.TYPE_ROUTES["PROCESS_ROBUSTNESS"]
    assert tuple(router.TYPE_ROUTES) == ("NEW_PRODUCT", "IMPROVEMENT", "COST_DOWN", "CUSTOMIZATION", "EXPLORATION", "PROCESS_ROBUSTNESS"), tuple(router.TYPE_ROUTES)
    result = router.decide(physical_state("MODEL_BUILT", project_type="PROCESS_ROBUSTNESS"), "PROCESS_WINDOW_DEFINED")
    assert result["decision"] == "ALLOW" and result["skill"] == "process-scale-up", result
    # The skip is route-local: the same MODEL_BUILT -> VERIFIED jump is DENIED.
    result = router.decide(physical_state("MODEL_BUILT", project_type="PROCESS_ROBUSTNESS"), "VERIFIED")
    assert result["decision"] == "DENY" and "cross-stage" in result["reason"], result
    # APPLIED is not yet a known router stage (WP-06 adds it).
    assert "APPLIED" not in router.KNOWN_STAGES, router.KNOWN_STAGES

    # 16. `--list-stages <TYPE>` prints the contract sequence verbatim for every
    #     project type and fails closed on an unknown type.
    for project_type, expected in ((t, tuple(router.TYPE_ROUTES[t])) for t in router.TYPE_ROUTES):
        returncode, stdout = run_cli_args("--list-stages", project_type)
        assert returncode == 0, (project_type, returncode, stdout)
        assert tuple(stdout.splitlines()) == expected, (project_type, stdout)
    returncode, stdout = run_cli_args("--list-stages", "NOT_A_TYPE")
    assert returncode == 1 and "no routed stage chain" in stdout, (returncode, stdout)

    print(f"PASS: lubricant-rd-agent router ALLOW/DENY/HOLD contract ({len(ROUTE_TABLE_REF)} routable stages, {len(router.TYPE_ROUTES)} project types)")
    return 0


PROCESS_ROBUSTNESS_REF = ("PROJECT_DEFINED", "FAILURE_CTQ_DEFINED", "TEST_METHODS_QUALIFIED", "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING", "MODEL_BUILT", "PROCESS_WINDOW_DEFINED", "APPLIED")


ROUTE_TABLE_REF = ("PROJECT_DEFINED", "DUTY_DEFINED", "CHALLENGES_DEFINED", "FAILURE_CTQ_DEFINED", "TEST_METHODS_QUALIFIED", "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING", "MODEL_BUILT", "OPTIMIZED", "PROCESS_WINDOW_DEFINED", "VERIFIED")


if __name__ == "__main__":
    raise SystemExit(main())
