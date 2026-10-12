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

    # 6. Last routed stage has no further step: APPLIED is the NEW_PRODUCT tail.
    result = router.decide(physical_state("APPLIED"), "FROZEN")
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
    assert router.TYPE_ROUTES["NEW_PRODUCT"] == list(router.FALLBACK_STAGES), router.FALLBACK_STAGES
    assert router.ON_DEMAND_NEXT == {"PROCESS_WINDOW_DEFINED": "VERIFIED"}, router.ON_DEMAND_NEXT
    assert tuple(router.KNOWN_STAGES) == tuple(contract["stages"]), router.KNOWN_STAGES
    assert len(router.KNOWN_STAGES) == 28, router.KNOWN_STAGES
    assert router.STAGES == ROUTE_TABLE_REF, router.STAGES
    assert router.SKILL_FOR_STAGE["PROCESS_WINDOW_DEFINED"] == "process-scale-up", router.SKILL_FOR_STAGE
    assert router.SKILL_FOR_STAGE["APPLIED"] == "application-validation", router.SKILL_FOR_STAGE
    assert router.NEXT_STAGE["OPTIMIZED"] == "PROCESS_WINDOW_DEFINED", router.NEXT_STAGE

    # 12. The main chain runs OPTIMIZED -> VERIFIED -> APPLIED. The process
    #     window is NOT a step of it: PROCESS_WINDOW_DEFINED is on demand
    #     (`on_demand_stages`), reachable only by calling process-scale-up
    #     directly, and its sole published hand-off is VERIFIED.
    result = router.decide(physical_state("OPTIMIZED"), "VERIFIED")
    assert result["decision"] == "ALLOW" and result["skill"] == "gate-review", result
    result = router.decide(physical_state("OPTIMIZED"), "PROCESS_WINDOW_DEFINED")
    assert result["decision"] == "DENY" and "cross-stage" in result["reason"], result
    # An on-demand stage still hands off — but only to its published next_stage.
    result = router.decide(physical_state("PROCESS_WINDOW_DEFINED"), "VERIFIED")
    assert result["decision"] == "ALLOW" and result["skill"] == "gate-review", result
    result = router.decide(physical_state("PROCESS_WINDOW_DEFINED"), "APPLIED")
    assert result["decision"] == "DENY" and "cross-stage" in result["reason"], result
    result = router.decide(physical_state("VERIFIED"), "APPLIED")
    assert result["decision"] == "ALLOW" and result["skill"] == "application-validation", result

    # 13. Route-aware jumps: the same request is legal in COST_DOWN and illegal in
    #     NEW_PRODUCT, because the chains differ per project type.
    result = router.decide(physical_state("EXPERIMENT_RUNNING", project_type="COST_DOWN"), "OPTIMIZED")
    assert result["decision"] == "ALLOW" and result["skill"] == "optimization", result
    result = router.decide(physical_state("EXPERIMENT_RUNNING", project_type="NEW_PRODUCT"), "OPTIMIZED")
    assert result["decision"] == "DENY" and "cross-stage" in result["reason"], result

    # 14. No route contains the on-demand process-window stage, so requesting it
    #     as a workflow step is denied on every project type.
    result = router.decide(physical_state("EXPERIMENT_RUNNING", project_type="CUSTOMIZATION"), "PROCESS_WINDOW_DEFINED")
    assert result["decision"] == "DENY" and "VERIFIED" in result["reason"], result

    # 15. WP-03 sixth route: PROCESS_ROBUSTNESS is published by the contract.
    #     Production-reproduction work re-runs design and modelling after a
    #     kettle/batch swap and closes on application validation — no OPTIMIZED
    #     (the formula is not re-optimised) and no process-window step.
    assert len(router.TYPE_ROUTES) == 7, router.TYPE_ROUTES
    assert tuple(router.TYPE_ROUTES["PROCESS_ROBUSTNESS"]) == PROCESS_ROBUSTNESS_REF, router.TYPE_ROUTES["PROCESS_ROBUSTNESS"]
    assert tuple(router.TYPE_ROUTES) == ("NEW_PRODUCT", "IMPROVEMENT", "COST_DOWN", "CUSTOMIZATION", "EXPLORATION", "PROCESS_ROBUSTNESS", "PRECISION_GREASE_DEV"), tuple(router.TYPE_ROUTES)
    result = router.decide(physical_state("MODEL_BUILT", project_type="PROCESS_ROBUSTNESS"), "APPLIED")
    assert result["decision"] == "ALLOW" and result["skill"] == "application-validation", result
    # The skip is route-local: MODEL_BUILT cannot jump straight to VERIFIED here.
    result = router.decide(physical_state("MODEL_BUILT", project_type="PROCESS_ROBUSTNESS"), "VERIFIED")
    assert result["decision"] == "DENY" and "cross-stage" in result["reason"], result
    # WP-06 flipped the WP-03 placeholder: APPLIED is a known routed stage now.
    assert "APPLIED" in router.KNOWN_STAGES, router.KNOWN_STAGES
    # On-demand hand-off is stage-driven, not route-driven: even inside a route
    # that never declares it, PROCESS_WINDOW_DEFINED still offers VERIFIED.
    result = router.decide(physical_state("PROCESS_WINDOW_DEFINED", project_type="PROCESS_ROBUSTNESS"), "VERIFIED")
    assert result["decision"] == "ALLOW" and result["skill"] == "gate-review", result

    # 16. `--list-stages <TYPE>` prints the contract sequence verbatim for every
    #     project type and fails closed on an unknown type.
    for project_type, expected in ((t, tuple(router.TYPE_ROUTES[t])) for t in router.TYPE_ROUTES):
        returncode, stdout = run_cli_args("--list-stages", project_type)
        assert returncode == 0, (project_type, returncode, stdout)
        assert tuple(stdout.splitlines()) == expected, (project_type, stdout)
    returncode, stdout = run_cli_args("--list-stages", "NOT_A_TYPE")
    assert returncode == 1 and "no routed stage chain" in stdout, (returncode, stdout)

    # 17. WP-14 seventh route: PRECISION_GREASE_DEV is published by the contract
    #     and runs its grease-specific stages as first-class workflow steps. The
    #     block-16 loop already covers it (it iterates TYPE_ROUTES); this pins
    #     the sequence itself, and the legacy oil route is unchanged.
    assert tuple(router.TYPE_ROUTES["PRECISION_GREASE_DEV"]) == PRECISION_GREASE_DEV_REF, router.TYPE_ROUTES["PRECISION_GREASE_DEV"]
    assert router.TYPE_ROUTES["NEW_PRODUCT"] == list(router.FALLBACK_STAGES) == ["PROJECT_DEFINED", "DUTY_DEFINED", "CHALLENGES_DEFINED", "FAILURE_CTQ_DEFINED", "TEST_METHODS_QUALIFIED", "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING", "MODEL_BUILT", "OPTIMIZED", "VERIFIED", "APPLIED"], router.TYPE_ROUTES["NEW_PRODUCT"]
    assert len(router.FALLBACK_STAGES) == 12, router.FALLBACK_STAGES
    assert router.SKILL_FOR_STAGE["KNOWLEDGE_ARCHIVED"] == "knowledge-archive", router.SKILL_FOR_STAGE
    assert router.SKILL_FOR_STAGE["BATCH_PRODUCED"] == "grease-batch", router.SKILL_FOR_STAGE

    # 18. Route-aware jumps hold on the new route too: DUTY_DEFINED advances to
    #     FAILURE_MECHANISM_DEFINED, while TEST_METHODS_QUALIFIED (four steps
    #     later on this route) stays denied as a cross-stage jump.
    result = router.decide(physical_state("DUTY_DEFINED", project_type="PRECISION_GREASE_DEV"), "TEST_METHODS_QUALIFIED")
    assert result["decision"] == "DENY" and "cross-stage" in result["reason"], result
    result = router.decide(physical_state("DUTY_DEFINED", project_type="PRECISION_GREASE_DEV"), "FAILURE_MECHANISM_DEFINED")
    assert result["decision"] == "ALLOW" and result["skill"] == "failure-ctq-analysis", result

    # 19. Batch 4: the inner-loop ring (`loop_edges`). The PRECISION_GREASE_DEV
    #     inner loop is a loop body, so the declared back edges become ADDITIONAL
    #     legal targets — they never replace the route's own next step. Inter-ring
    #     backtracking is NOT an edge and stays DENIED (decision 3, plan N21/N22).
    assert list(router.LOOP_EDGES) == contract["loop_edges"], router.LOOP_EDGES
    assert router.LOOP_TARGETS == {
        "VARIANCE_ASSESSED": ["BATCH_PRODUCED"],
        "SCREENING_PASSED": ["BATCH_PRODUCED"],
    }, router.LOOP_TARGETS
    assert router.MAX_ITERATIONS == contract["max_iterations"] == 12, router.MAX_ITERATIONS
    grease_route = router.TYPE_ROUTES["PRECISION_GREASE_DEV"]
    for edge in router.LOOP_EDGES:
        # An edge is a controlled BACK edge of one route: both endpoints on the
        # same route, target strictly earlier (otherwise it is not a loop).
        assert edge["from"] in grease_route and edge["to"] in grease_route, edge
        assert grease_route.index(edge["to"]) < grease_route.index(edge["from"]), edge
        # The loop only ever returns to the batch, which has a producer skill.
        assert edge["to"] == "BATCH_PRODUCED", edge
        assert router.SKILL_FOR_STAGE[edge["to"]] == "grease-batch", router.SKILL_FOR_STAGE
        for oil_type, oil_route in router.TYPE_ROUTES.items():
            if oil_type == "PRECISION_GREASE_DEV":
                continue
            assert not (edge["from"] in oil_route and edge["to"] in oil_route), (edge, oil_type)

    # Ring edge request: ALLOW, routed to the producing skill (grease-batch).
    result = router.decide(physical_state("SCREENING_PASSED", project_type="PRECISION_GREASE_DEV"), "BATCH_PRODUCED")
    assert result["decision"] == "ALLOW" and result["skill"] == "grease-batch", result
    assert "inner-loop edge" in result["reason"], result
    result = router.decide(physical_state("VARIANCE_ASSESSED", project_type="PRECISION_GREASE_DEV"), "BATCH_PRODUCED")
    assert result["decision"] == "ALLOW" and result["skill"] == "grease-batch", result
    # The route's own next step stays legal next to the edge (addition, not replacement).
    result = router.decide(physical_state("SCREENING_PASSED", project_type="PRECISION_GREASE_DEV"), "BENCH_TESTED")
    assert result["decision"] == "ALLOW" and result["skill"] == "experiment-import", result
    result = router.decide(physical_state("VARIANCE_ASSESSED", project_type="PRECISION_GREASE_DEV"), "MODEL_BUILT")
    assert result["decision"] == "ALLOW" and result["skill"] == "statistical-analysis", result
    # A DENY between the two legal targets names both, so callers are not misled.
    result = router.decide(physical_state("SCREENING_PASSED", project_type="PRECISION_GREASE_DEV"), "VARIANCE_ASSESSED")
    assert result["decision"] == "DENY" and "BENCH_TESTED" in result["reason"] and "BATCH_PRODUCED" in result["reason"], result
    # CLI parity: the ring is ALLOWed through the script too (exit 0).
    returncode, stdout = run_cli({"project_state": physical_state("SCREENING_PASSED", project_type="PRECISION_GREASE_DEV"), "requested_stage": "BATCH_PRODUCED"})
    assert returncode == 0 and "ALLOW" in stdout and "grease-batch" in stdout, (returncode, stdout)

    # 20. The exemption is ROUTE-LOCAL and the ring is not a general backtrack.
    #     N21: inter-ring backtracking inside the grease route stays DENIED.
    result = router.decide(physical_state("BENCH_TESTED", project_type="PRECISION_GREASE_DEV"), "TEST_METHODS_QUALIFIED")
    assert result["decision"] == "DENY" and "cross-stage" in result["reason"], result
    #     N22: the documented NEW_PRODUCT denial (OPTIMIZED -> method qualification).
    result = router.decide(physical_state("OPTIMIZED", project_type="NEW_PRODUCT"), "TEST_METHODS_QUALIFIED")
    assert result["decision"] == "DENY" and "cross-stage" in result["reason"], result
    #     The same ring request outside its route is denied: an oil project_type,
    #     a project_type that does not declare the endpoint, and no project_type.
    for ptype in ("NEW_PRODUCT", "PROCESS_ROBUSTNESS"):
        result = router.decide(physical_state("VARIANCE_ASSESSED", project_type=ptype), "BATCH_PRODUCED")
        assert result["decision"] == "DENY", (ptype, result)
    result = router.decide(physical_state("SCREENING_PASSED", project_type="NEW_PRODUCT"), "BATCH_PRODUCED")
    assert result["decision"] == "DENY", result
    result = router.decide(physical_state("VARIANCE_ASSESSED"), "BATCH_PRODUCED")
    assert result["decision"] == "DENY", result
    #     A ring edge never makes an unrelated jump legal: from BENCH_TESTED the
    #     only target is VARIANCE_ASSESSED (no edge leaves BENCH_TESTED).
    result = router.decide(physical_state("BENCH_TESTED", project_type="PRECISION_GREASE_DEV"), "BATCH_PRODUCED")
    assert result["decision"] == "DENY" and "cross-stage" in result["reason"], result

    # 21. `SKILL_FOR_STAGE` is no longer a bare index: a routed stage with no
    #     producer fails closed with a reason instead of raising KeyError. Every
    #     stage any request can reach (routes + ring targets + on-demand
    #     hand-offs) must have a producer, and the hardened lookup is exercised on
    #     a synthetic gap.
    reachable = {stage for route in router.TYPE_ROUTES.values() for stage in route}
    reachable |= {edge["to"] for edge in router.LOOP_EDGES}
    reachable |= set(router.ON_DEMAND_NEXT)
    reachable |= set(router.ON_DEMAND_NEXT.values())
    for stage in sorted(reachable):
        assert stage in router.SKILL_FOR_STAGE, f"{stage} has no producing skill in ROUTE_TABLE"
    missing = router.SKILL_FOR_STAGE.pop("BATCH_PRODUCED")
    try:
        result = router.decide(physical_state("SCREENING_PASSED", project_type="PRECISION_GREASE_DEV"), "BATCH_PRODUCED")
        assert result["decision"] == "DENY" and "no producing skill" in result["reason"], result
    finally:
        router.SKILL_FOR_STAGE["BATCH_PRODUCED"] = missing

    # 22. `--list-loop-edges <TYPE>` prints a route's declared back edges only
    #     (same fail-closed contract as `--list-stages`).
    returncode, stdout = run_cli_args("--list-loop-edges", "PRECISION_GREASE_DEV")
    assert returncode == 0, (returncode, stdout)
    assert stdout.splitlines() == [
        "VARIANCE_ASSESSED -> BATCH_PRODUCED (LOOP_BACK)",
        "SCREENING_PASSED -> BATCH_PRODUCED (REWORK)",
    ], stdout
    for oil_type in ("NEW_PRODUCT", "IMPROVEMENT", "COST_DOWN", "CUSTOMIZATION", "EXPLORATION", "PROCESS_ROBUSTNESS"):
        returncode, stdout = run_cli_args("--list-loop-edges", oil_type)
        assert returncode == 0 and stdout == "", (oil_type, returncode, stdout)
    returncode, stdout = run_cli_args("--list-loop-edges", "NOT_A_TYPE")
    assert returncode == 1 and "no routed stage chain" in stdout, (returncode, stdout)

    print(f"PASS: lubricant-rd-agent router ALLOW/DENY/HOLD contract ({len(ROUTE_TABLE_REF)} routable stages, {len(router.TYPE_ROUTES)} project types)")
    return 0


PROCESS_ROBUSTNESS_REF = ("PROJECT_DEFINED", "FAILURE_CTQ_DEFINED", "TEST_METHODS_QUALIFIED", "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING", "MODEL_BUILT", "APPLIED")


PRECISION_GREASE_DEV_REF = ("PROJECT_DEFINED", "DUTY_DEFINED", "FAILURE_MECHANISM_DEFINED", "REFERENCE_MATERIAL_RESOLVED", "TEST_METHODS_QUALIFIED", "DESIGN_SPACE_DEFINED", "BENCH_RESOURCE_REGISTERED", "CAMPAIGN_OPENED", "EXPERIMENT_DESIGNED", "BATCH_PRODUCED", "SCREENING_PASSED", "BENCH_TESTED", "VARIANCE_ASSESSED", "MODEL_BUILT", "NEXT_BATCH_DECIDED", "NON_INFERIORITY_PASSED", "PROCESS_SCALE_VALIDATED", "VERIFIED", "APPLIED", "KNOWLEDGE_ARCHIVED")


ROUTE_TABLE_REF = ("PROJECT_DEFINED", "DUTY_DEFINED", "CHALLENGES_DEFINED", "FAILURE_CTQ_DEFINED", "TEST_METHODS_QUALIFIED", "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING", "MODEL_BUILT", "OPTIMIZED", "PROCESS_WINDOW_DEFINED", "VERIFIED", "APPLIED", "FAILURE_MECHANISM_DEFINED", "REFERENCE_MATERIAL_RESOLVED", "BENCH_RESOURCE_REGISTERED", "CAMPAIGN_OPENED", "BATCH_PRODUCED", "SCREENING_PASSED", "BENCH_TESTED", "VARIANCE_ASSESSED", "NEXT_BATCH_DECIDED", "NON_INFERIORITY_PASSED", "PROCESS_SCALE_VALIDATED", "KNOWLEDGE_ARCHIVED")


if __name__ == "__main__":
    raise SystemExit(main())
