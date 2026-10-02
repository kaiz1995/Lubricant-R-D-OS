"""Router check for the lubricant-rd-agent Meta-Skill.

Pure stdlib. Reads one JSON object with project_state + requested_stage and
prints ALLOW (exit 0) or DENY/HOLD with reasons (exit 1). Never writes
artifacts and never performs business calculation.

A second form, `--list-stages <PROJECT_TYPE>`, prints the full stage sequence of
one declared project type (one stage per line) so callers can read the route
without duplicating it. Both forms fail closed when the contract is unreadable.

The differentiated per-project_type stage chains are NOT hardcoded here: they
are read from the shared contract `contracts/state-machine.json` (`type_routes`),
the same list `scripts/validate_state_machine.py` uses for its GO adjacency
assertion. One list, two consumers, so the router and the state machine cannot
drift apart.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ERRORS: list[str] = []


def load_contract() -> dict | None:
    """Read the shared state-machine contract from the pack or the deployed skill."""
    for candidate in (SKILL_ROOT.parents[1] / "contracts", SKILL_ROOT / "references"):
        path = candidate / "state-machine.json"
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                CONTRACT_ERRORS.append(f"{path}: {error}")
                return None
    CONTRACT_ERRORS.append("state-machine.json is absent from the pack contracts/ and deployed references/ directories")
    return None


CONTRACT = load_contract()

# Frozen planned order: skill -> target stage it produces. This is the router's
# own fact (which skill materialises a stage); the *workflow* order per project
# type comes from the contract.
ROUTE_TABLE = (
    ("project-definition", "PROJECT_DEFINED"),
    ("duty-definition", "DUTY_DEFINED"),
    ("duty-challenge-analysis", "CHALLENGES_DEFINED"),
    ("failure-ctq-analysis", "FAILURE_CTQ_DEFINED"),
    ("test-method-qualification", "TEST_METHODS_QUALIFIED"),
    ("formulation-design", "DESIGN_SPACE_DEFINED"),
    ("doe-design", "EXPERIMENT_DESIGNED"),
    ("experiment-import", "EXPERIMENT_RUNNING"),
    ("statistical-analysis", "MODEL_BUILT"),
    ("optimization", "OPTIMIZED"),
    ("process-scale-up", "PROCESS_WINDOW_DEFINED"),
    ("gate-review", "VERIFIED"),
)

STAGES = tuple(stage for _, stage in ROUTE_TABLE)
SKILL_FOR_STAGE = dict((stage, skill) for skill, stage in ROUTE_TABLE)
START_STAGE = "DRAFT"
TERMINAL_STATUSES = {"FROZEN", "CLOSED", "KILLED", "PIVOTED"}

# Differentiated workflows for the 6 project types, published by the contract.
TYPE_ROUTES = CONTRACT["type_routes"] if CONTRACT else {}
# Stage universe = the contract's 15 stages. A contract that cannot be read
# leaves the universe empty so decide() denies every request instead of guessing.
KNOWN_STAGES = tuple(CONTRACT["stages"]) if CONTRACT else ()
NEXT_STAGE = dict(zip(KNOWN_STAGES, KNOWN_STAGES[1:]))


def decide(project_state: object, requested_stage: str) -> dict:
    """Return {'decision': 'ALLOW'|'DENY'|'HOLD', 'reason': str, 'skill': str|None}."""
    if CONTRACT is None:
        return {"decision": "DENY", "reason": f"routing contract unavailable: {'; '.join(CONTRACT_ERRORS)}", "skill": None}
    if not isinstance(project_state, dict):
        return {"decision": "DENY", "reason": "project_state must be a JSON object", "skill": None}
    if not isinstance(requested_stage, str) or requested_stage not in KNOWN_STAGES:
        return {"decision": "DENY", "reason": f"requested_stage {requested_stage!r} is not a known stage", "skill": None}

    current = project_state.get("stage")
    if current not in KNOWN_STAGES:
        return {"decision": "DENY", "reason": f"current stage {current!r} is not a known stage", "skill": None}

    scope = project_state.get("evidence_scope")
    if scope not in {"SYNTHETIC", "PHYSICAL"}:
        return {"decision": "DENY", "reason": "evidence_scope must be SYNTHETIC or PHYSICAL", "skill": None}

    status = project_state.get("status")
    if status in TERMINAL_STATUSES:
        return {"decision": "DENY", "reason": f"project status {status} is terminal and cannot advance", "skill": None}

    ptype = project_state.get("project_type")
    # A declared project_type must be one the contract routes. The pack documents
    # exactly six workflows (README §5, project-definition/SKILL.md) and
    # `project.schema.json` enumerates the same six, so an unrouted value is a
    # contract violation — DENY it rather than silently handing it the full
    # NEW_PRODUCT chain. A missing project_type stays on the full chain for
    # pre-existing state.
    if ptype is not None and (not isinstance(ptype, str) or ptype not in TYPE_ROUTES):
        return {
            "decision": "DENY",
            "reason": f"project_type {ptype!r} has no routed stage chain; publish type_routes[{ptype!r}] in contracts/state-machine.json before advancing",
            "skill": None,
        }
    route = TYPE_ROUTES.get(ptype, STAGES) if isinstance(ptype, str) else STAGES

    if current == START_STAGE:
        target_stage = "PROJECT_DEFINED"
    elif current in route:
        idx = route.index(current)
        target_stage = route[idx + 1] if idx + 1 < len(route) else None
    elif current in STAGES:
        idx = STAGES.index(current)
        target_stage = STAGES[idx + 1] if idx + 1 < len(STAGES) else None
    else:
        target_stage = None

    if target_stage is None:
        return {"decision": "DENY", "reason": f"stage {current} is the final routed stage; no further step exists", "skill": None}

    if requested_stage == current:
        return {"decision": "HOLD", "reason": f"project is already at {current}; no step to take", "skill": None}
    if requested_stage != target_stage:
        return {"decision": "DENY", "reason": f"cross-stage jump rejected: next allowed stage is {target_stage}, requested {requested_stage}", "skill": None}

    gaps = project_state.get("evidence_gaps") or []
    unsatisfied = project_state.get("unsatisfied_conditions") or []
    gate_status = project_state.get("gate_status")
    missing = [f"evidence gap: {item}" for item in gaps if isinstance(item, str)] + [
        f"unsatisfied condition: {item}" for item in unsatisfied if isinstance(item, str)
    ]
    if gate_status == "HOLD":
        missing.append("gate_status is HOLD")
    if missing:
        return {"decision": "HOLD", "reason": "unresolved: " + "; ".join(missing), "skill": None}
    if gate_status not in (None, "GO"):
        return {"decision": "HOLD", "reason": f"gate_status {gate_status!r} is not GO", "skill": None}
    if scope == "SYNTHETIC":
        return {"decision": "DENY", "reason": "SYNTHETIC evidence cannot authorize stage advancement; PHYSICAL evidence required", "skill": None}

    return {"decision": "ALLOW", "reason": "single-step advancement permitted", "skill": SKILL_FOR_STAGE[requested_stage]}


def list_stages(project_type: str) -> int:
    """Print the stage sequence of one declared project type, one stage per line."""
    if CONTRACT is None:
        print(f"DENY: routing contract unavailable: {'; '.join(CONTRACT_ERRORS)}")
        return 1
    route = TYPE_ROUTES.get(project_type)
    if route is None:
        print(f"DENY: project_type {project_type!r} has no routed stage chain; publish type_routes[{project_type!r}] in contracts/state-machine.json")
        return 1
    for stage in route:
        print(stage)
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--list-stages":
        if len(sys.argv) != 3:
            print("Usage: python route_step.py --list-stages <PROJECT_TYPE>")
            return 1
        return list_stages(sys.argv[2])
    if len(sys.argv) != 2:
        print("Usage: python route_step.py <input.json>")
        print("       python route_step.py --list-stages <PROJECT_TYPE>")
        return 1
    path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"DENY: cannot read input: {error}")
        return 1
    if not isinstance(data, dict) or "project_state" not in data or "requested_stage" not in data:
        print("DENY: input must contain project_state and requested_stage")
        return 1
    result = decide(data["project_state"], data["requested_stage"])
    decision = result["decision"]
    print(f"{decision}: {result['reason']}" + (f" -> route to skills/{result['skill']}" if result["skill"] else ""))
    return 0 if decision == "ALLOW" else 1


if __name__ == "__main__":
    sys.exit(main())
