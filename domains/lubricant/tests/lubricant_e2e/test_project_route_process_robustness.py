"""End-to-end checks for the WP-03 sixth project route (PROCESS_ROBUSTNESS).

Production-reproduction work (kettle / batch swap on a frozen formula) re-runs
design and modelling and closes on application validation. It is **no longer a
process-window route**: PROCESS_WINDOW_DEFINED left every type_route and is now
published as an on-demand stage (contract ``on_demand_stages``), because the
window it fixes only exists for products whose structure is set by the
manufacturing process — grease (saponification / phase inversion / cooling /
milling). A blended oil is physically mixed: its process is a second-order
variable, so routing a process-window step on every oil project forced a
meaningless artifact into the chain.

Acceptance:
  (a) route_step ALLOWs the route-adjacent MODEL_BUILT -> APPLIED.
  (b) validate_state_machine ALLOWs the *same* before/after GO event (the real
      decision point; route_step alone would be a false green).
  (c) `--list-stages PROCESS_ROBUSTNESS` prints the 8 published stages, item by item.
  (d) The illegal MODEL_BUILT -> VERIFIED jump is DENIED by route_step AND
      rejected by validate_state_machine.
  (e) The on-demand stage still hands off — PROCESS_WINDOW_DEFINED -> VERIFIED
      passes BOTH consumers, no route contains the stage, and the hand-off is
      not a free pass (off-target successors are rejected).
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
# The exact 8-stage sequence published by the contract (verbatim, in order):
# no OPTIMIZED (the formula is not re-optimised) and no process-window step.
EXPECTED_ROUTE = (
    "PROJECT_DEFINED",
    "FAILURE_CTQ_DEFINED",
    "TEST_METHODS_QUALIFIED",
    "DESIGN_SPACE_DEFINED",
    "EXPERIMENT_DESIGNED",
    "EXPERIMENT_RUNNING",
    "MODEL_BUILT",
    "APPLIED",
)
PRE_EXISTING_TYPES = ("NEW_PRODUCT", "IMPROVEMENT", "COST_DOWN", "CUSTOMIZATION", "EXPLORATION")

# On-demand stage: materialisable by process-scale-up, on no route.
ON_DEMAND_STAGE = "PROCESS_WINDOW_DEFINED"
ON_DEMAND_NEXT = "VERIFIED"


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
        "decision_question": "Does the reproduction batch reproduce the frozen formula?",
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

    # 0. The published route is the 8-stage production-reproduction sequence and
    #    WP-06 has added APPLIED to the stage universe (between VERIFIED and FROZEN).
    assert tuple(contract["type_routes"][PROJECT_TYPE]) == EXPECTED_ROUTE, contract["type_routes"][PROJECT_TYPE]
    assert len(contract["type_routes"]) == 6, sorted(contract["type_routes"])
    assert "APPLIED" in contract["stages"], contract["stages"]
    assert contract["stages"].index("APPLIED") == contract["stages"].index("VERIFIED") + 1, contract["stages"]
    assert contract["stages"].index("FROZEN") == contract["stages"].index("APPLIED") + 1, contract["stages"]
    # The on-demand stage is still known to the state machine — it is simply off
    # every route, and its successor is published rather than implied.
    assert ON_DEMAND_STAGE in contract["stages"], contract["stages"]
    assert ON_DEMAND_STAGE in contract["on_demand_stages"], contract["on_demand_stages"]
    assert contract["on_demand_stages"][ON_DEMAND_STAGE]["next_stage"] == ON_DEMAND_NEXT, contract["on_demand_stages"]
    for published in contract["type_routes"].values():
        assert ON_DEMAND_STAGE not in published, published

    # (a) route_step: the route-adjacent step is MODEL_BUILT -> APPLIED.
    probe = {
        "project_state": {
            "stage": "MODEL_BUILT",
            "status": "ACTIVE",
            "evidence_scope": "PHYSICAL",
            "project_type": PROJECT_TYPE,
        },
        "requested_stage": "APPLIED",
    }
    result = run_route_json(probe)
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert result.stdout.startswith("ALLOW:") and "application-validation" in result.stdout, result.stdout

    # (b) validate_state_machine: the SAME legal step must also pass here —
    #     route_step only recommends a next step; the state machine is the real
    #     decision point.
    assert validator.validate(go_event("MODEL_BUILT", "APPLIED")) is None, "validate rejected the legal PROCESS_ROBUSTNESS step"

    # (d) The illegal cross-stage jump is rejected by BOTH consumers.
    illegal = run_route_json({**probe, "requested_stage": "VERIFIED"})
    assert illegal.returncode == 1 and illegal.stdout.startswith("DENY:") and "cross-stage" in illegal.stdout, illegal.stdout
    reason = validator.validate(go_event("MODEL_BUILT", "VERIFIED"))
    assert reason == "GO must advance exactly one stage", reason

    # The route-local skip is what makes (b) legal: the global order has
    # MODEL_BUILT -> OPTIMIZED in between, but the PROCESS_ROBUSTNESS chain does
    # not contain OPTIMIZED, so the parser must follow the route.
    assert "OPTIMIZED" not in EXPECTED_ROUTE

    # A PROCESS_ROBUSTNESS event without the declaration falls back to the global
    # order and can no longer take the skip (fail closed, no implicit routing).
    undeclared = go_event("MODEL_BUILT", "APPLIED")
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

    # (e) On-demand hand-off. A grease project (or any project that explicitly
    #     calls process-scale-up) may still fix a window. The stage sits on no
    #     route, so route_step resolves its successor from the contract's
    #     published next_stage — and validate_state_machine agrees.
    on_demand_probe = {
        "project_state": {
            "stage": ON_DEMAND_STAGE,
            "status": "ACTIVE",
            "evidence_scope": "PHYSICAL",
            "project_type": PROJECT_TYPE,
        },
        "requested_stage": ON_DEMAND_NEXT,
    }
    on_demand = run_route_json(on_demand_probe)
    assert on_demand.returncode == 0, f"{on_demand.stdout}{on_demand.stderr}"
    assert on_demand.stdout.startswith("ALLOW:") and "gate-review" in on_demand.stdout, on_demand.stdout
    assert validator.validate(go_event(ON_DEMAND_STAGE, ON_DEMAND_NEXT)) is None, "validate rejected the on-demand hand-off"

    # The hand-off is not a free pass: only the published next_stage is legal.
    off_target = run_route_json({**on_demand_probe, "requested_stage": "APPLIED"})
    assert off_target.returncode == 1 and off_target.stdout.startswith("DENY:"), off_target.stdout
    assert validator.validate(go_event(ON_DEMAND_STAGE, "APPLIED")) == "GO must advance exactly one stage"

    # And it cannot be adopted as a workflow step on a route.
    adopted = run_route_json({**probe, "requested_stage": ON_DEMAND_STAGE})
    assert adopted.returncode == 1 and adopted.stdout.startswith("DENY:"), adopted.stdout

    # HOLD / ROLLBACK / FREEZE branches accept a PROCESS_ROBUSTNESS declaration
    # without raising.
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
        "before": state("APPLIED", version=4),
        "after": state("MODEL_BUILT", status="HOLD", version=5),
        "accepted_stages": stages[: stages.index("MODEL_BUILT") + 1],
        "revision": {"reason": "reproduction batch diverged", "operator": "owner", "impact": "re-fit model"},
    }
    assert validator.validate(rollback) is None, validator.validate(rollback)

    freeze = {
        "kind": "FREEZE",
        "gate_status": "FREEZE",
        "project_type": PROJECT_TYPE,
        "before": state("APPLIED"),
        # WP-08: freezing also requires a named technical_reviewer on the after state.
        "after": state("FROZEN", status="FROZEN", technical_reviewer="Lead tribologist"),
        "freeze_record": {"reason": "applied", "evidence_package": ["E-PR-001"]},
    }
    assert validator.validate(freeze) is None, validator.validate(freeze)
    # FREEZE cannot skip APPLIED: VERIFIED -> FROZEN is deterministically rejected
    # (WP-06: application and machine validation must happen before freezing).
    skipped_freeze = {
        "kind": "FREEZE",
        "gate_status": "FREEZE",
        "project_type": PROJECT_TYPE,
        "before": state("VERIFIED"),
        "after": state("FROZEN", status="FROZEN"),
        "freeze_record": {"reason": "verified only", "evidence_package": ["E-PR-001"]},
    }
    assert validator.validate(skipped_freeze) == "FREEZE requires APPLIED to FROZEN", validator.validate(skipped_freeze)

    print("PASS: PROCESS_ROBUSTNESS production-reproduction route validated (route_step + validate_state_machine), on-demand process window off every route")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
