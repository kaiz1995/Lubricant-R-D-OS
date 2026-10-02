"""End-to-end checks for the WP-03 sixth project route (PROCESS_ROBUSTNESS).

Two-step acceptance (plan §WP-03):
  Step 1 (this package):
    (a) route_step ALLOWs the route-adjacent MODEL_BUILT -> PROCESS_WINDOW_DEFINED.
    (b) validate_state_machine ALLOWs the *same* before/after GO event (the real
        decision point; route_step alone would be a false green).
    (c) `--list-stages PROCESS_ROBUSTNESS` prints the 9 planned stages, item by item.
    (d) The illegal MODEL_BUILT -> VERIFIED jump is DENIED by route_step AND
        rejected by validate_state_machine.
  Step 2 (WP-06, TODO placeholder below): PROCESS_WINDOW_DEFINED -> APPLIED -> ...

The route's final stage APPLIED is deliberately published before WP-06 adds it to
the stage universe (plan: two-step design). This test proves the partial state is
safe: the route-adjacent APPLIED edge is rejected deterministically ("unknown
stage") instead of raising, and no other branch breaks.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTE_SCRIPT = ROOT / "skills/lubricant-rd-agent/scripts/route_step.py"
VALIDATE_SCRIPT = ROOT / "scripts/validate_state_machine.py"
CONTRACT_PATH = ROOT / "contracts" / "state-machine.json"

PROJECT_TYPE = "PROCESS_ROBUSTNESS"
# The exact 9-stage sequence from plan §WP-03 (verbatim, in order).
EXPECTED_ROUTE = (
    "PROJECT_DEFINED",
    "FAILURE_CTQ_DEFINED",
    "TEST_METHODS_QUALIFIED",
    "DESIGN_SPACE_DEFINED",
    "EXPERIMENT_DESIGNED",
    "EXPERIMENT_RUNNING",
    "MODEL_BUILT",
    "PROCESS_WINDOW_DEFINED",
    "APPLIED",
)
PRE_EXISTING_TYPES = ("NEW_PRODUCT", "IMPROVEMENT", "COST_DOWN", "CUSTOMIZATION", "EXPLORATION")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_state_machine", VALIDATE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_route(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(ROUTE_SCRIPT), *arguments],
        cwd=ROUTE_SCRIPT.parent,
        capture_output=True,
        text=True,
    )


def run_route_json(payload: dict) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "route-input.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return run_route(str(path))


def state(stage: str, **overrides) -> dict:
    value = {
        "project_id": "WGO-PR-001",
        "stage": stage,
        "status": "ACTIVE",
        "version": 3,
        "decision_question": "Is the manufacturing process window fixed for the fixed formula?",
        "evidence": ["E-PR-001"],
        "evidence_scope": "PHYSICAL",
    }
    value.update(overrides)
    return value


def go_event(before_stage: str, after_stage: str, **overrides) -> dict:
    event = {
        "kind": "GO",
        "gate_status": "GO",
        "project_type": PROJECT_TYPE,
        "before": state(before_stage),
        "after": state(after_stage),
    }
    event.update(overrides)
    return event


def main() -> int:
    validator = load_validator()
    contract = read_json(CONTRACT_PATH)

    # 0. The published route is the planned 9-stage sequence and APPLIED is not yet
    #    a stage (WP-06 owns that half).
    assert tuple(contract["type_routes"][PROJECT_TYPE]) == EXPECTED_ROUTE, contract["type_routes"][PROJECT_TYPE]
    assert len(contract["type_routes"]) == 6, sorted(contract["type_routes"])
    assert "APPLIED" not in contract["stages"], contract["stages"]
    assert "PROCESS_WINDOW_DEFINED" in contract["stages"], contract["stages"]

    # (a) route_step: the plan's exact probe, MODEL_BUILT -> PROCESS_WINDOW_DEFINED.
    probe = {
        "project_state": {
            "stage": "MODEL_BUILT",
            "status": "ACTIVE",
            "evidence_scope": "PHYSICAL",
            "project_type": PROJECT_TYPE,
        },
        "requested_stage": "PROCESS_WINDOW_DEFINED",
    }
    result = run_route_json(probe)
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert result.stdout.startswith("ALLOW:") and "process-scale-up" in result.stdout, result.stdout

    # (b) validate_state_machine: the SAME legal step must also pass here — route_step
    #     only recommends a next step; the state machine is the real decision point.
    assert validator.validate(go_event("MODEL_BUILT", "PROCESS_WINDOW_DEFINED")) is None, "validate rejected the legal PROCESS_ROBUSTNESS step"

    # (d) The illegal cross-stage jump is rejected by BOTH consumers.
    illegal = run_route_json({**probe, "requested_stage": "VERIFIED"})
    assert illegal.returncode == 1 and illegal.stdout.startswith("DENY:") and "cross-stage" in illegal.stdout, illegal.stdout
    reason = validator.validate(go_event("MODEL_BUILT", "VERIFIED"))
    assert reason == "GO must advance exactly one stage", reason

    # The route-local skip is what makes (b) legal: global order also has
    # MODEL_BUILT -> OPTIMIZED -> PROCESS_WINDOW_DEFINED, but the PROCESS_ROBUSTNESS
    # chain does not contain OPTIMIZED, so the parser must follow the route.
    assert "OPTIMIZED" not in EXPECTED_ROUTE

    # A PROJECT_ROBUSTNESS event without the declaration falls back to the global
    # order and can no longer take the skip (fail closed, no implicit routing).
    undeclared = go_event("MODEL_BUILT", "PROCESS_WINDOW_DEFINED")
    undeclared.pop("project_type")
    assert validator.validate(undeclared) == "GO must advance exactly one stage"

    # (c) --list-stages prints the sequence item by item.
    listed = run_route("--list-stages", PROJECT_TYPE)
    assert listed.returncode == 0, f"{listed.stdout}{listed.stderr}"
    assert tuple(listed.stdout.splitlines()) == EXPECTED_ROUTE, listed.stdout

    # Regression: every pre-existing route is printed exactly as the contract has it.
    for project_type in PRE_EXISTING_TYPES:
        listed = run_route("--list-stages", project_type)
        assert listed.returncode == 0, (project_type, listed.stdout, listed.stderr)
        assert tuple(listed.stdout.splitlines()) == tuple(contract["type_routes"][project_type]), (project_type, listed.stdout)

    # An unknown type is an explicit error, never an empty or guessed chain.
    unknown = run_route("--list-stages", "NOT_A_TYPE")
    assert unknown.returncode == 1 and "no routed stage chain" in unknown.stdout, unknown.stdout

    # HOLD / ROLLBACK / FREEZE branches accept a PROCESS_ROBUSTNESS declaration
    # without raising (the missing APPLIED stage must not break unrelated actions).
    hold = {
        "kind": "HOLD",
        "gate_status": "HOLD",
        "project_type": PROJECT_TYPE,
        "before": state("MODEL_BUILT"),
        "after": state("MODEL_BUILT", status="HOLD"),
    }
    assert validator.validate(hold) is None, validator.validate(hold)

    stages = contract["stages"]
    rollback = {
        "kind": "ROLLBACK",
        "gate_status": "HOLD",
        "project_type": PROJECT_TYPE,
        "before": state("PROCESS_WINDOW_DEFINED", version=4),
        "after": state("MODEL_BUILT", status="HOLD", version=5),
        "accepted_stages": stages[: stages.index("MODEL_BUILT") + 1],
        "revision": {"reason": "window not reproducible", "operator": "owner", "impact": "re-fit window"},
    }
    assert validator.validate(rollback) is None, validator.validate(rollback)

    freeze = {
        "kind": "FREEZE",
        "gate_status": "FREEZE",
        "project_type": PROJECT_TYPE,
        "before": state("VERIFIED"),
        "after": state("FROZEN", status="FROZEN"),
        "freeze_record": {"reason": "verified", "evidence_package": ["E-PR-001"]},
    }
    assert validator.validate(freeze) is None, validator.validate(freeze)

    # The APPLIED edge is route-adjacent but APPLIED is not a stage until WP-06, so
    # today it is rejected deterministically (a clean "unknown stage", not a crash).
    applied_route = run_route_json({**probe, "project_state": {**probe["project_state"], "stage": "PROCESS_WINDOW_DEFINED"}, "requested_stage": "APPLIED"})
    assert applied_route.returncode == 1 and "is not a known stage" in applied_route.stdout, applied_route.stdout
    applied_reason = validator.validate(go_event("PROCESS_WINDOW_DEFINED", "APPLIED"))
    assert applied_reason == "state has an unknown stage", applied_reason

    # TODO (WP-06 step 2): once contracts/state-machine.json adds APPLIED between
    # PROCESS_WINDOW_DEFINED and FROZEN, extend this file so
    # PROCESS_WINDOW_DEFINED -> APPLIED (GO) is ALLOW and APPLIED -> FROZEN is the
    # only FREEZE entry. Both assertions above must be flipped at that point.

    print("PASS: PROCESS_ROBUSTNESS route reachable and validated (route_step + validate_state_machine)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
