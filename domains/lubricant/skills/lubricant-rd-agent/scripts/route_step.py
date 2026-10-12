"""Router check for the lubricant-rd-agent Meta-Skill.

Pure stdlib. Reads one JSON object with project_state + requested_stage and
prints ALLOW (exit 0) or DENY/HOLD with reasons (exit 1). Never writes
artifacts and never performs business calculation.

A second form, `--list-stages <PROJECT_TYPE>`, prints the full stage sequence of
one declared project type (one stage per line) so callers can read the route
without duplicating it. A third form, `--list-loop-edges <PROJECT_TYPE>`, prints
that route's declared inner-loop back edges (`from -> to (kind)`) for the same
reason. All forms fail closed when the contract is unreadable.

The differentiated per-project_type stage chains are NOT hardcoded here: they
are read from the shared contract `contracts/state-machine.json` (`type_routes`),
the same list `scripts/validate_state_machine.py` uses for its GO adjacency
assertion. One list, two consumers, so the router and the state machine cannot
drift apart. The inner-loop back edges (`loop_edges`) are read the same way.
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
    ("application-validation", "APPLIED"),
    # PRECISION_GREASE_DEV (the 7th route) runs all 17 of its steps as
    # first-class stages. The stages below are the ones the oil routes skip,
    # fold into a neighbour, or never had; each needs a producer here or the
    # router raises KeyError on SKILL_FOR_STAGE instead of failing closed.
    ("failure-ctq-analysis", "FAILURE_MECHANISM_DEFINED"),
    ("reference-material", "REFERENCE_MATERIAL_RESOLVED"),
    ("bench-registration", "BENCH_RESOURCE_REGISTERED"),
    ("bench-registration", "CAMPAIGN_OPENED"),
    ("grease-batch", "BATCH_PRODUCED"),
    ("grease-screening", "SCREENING_PASSED"),
    ("experiment-import", "BENCH_TESTED"),
    ("variance-assessment", "VARIANCE_ASSESSED"),
    ("doe-design", "NEXT_BATCH_DECIDED"),
    ("optimization", "NON_INFERIORITY_PASSED"),
    ("process-scale-up", "PROCESS_SCALE_VALIDATED"),
    ("knowledge-archive", "KNOWLEDGE_ARCHIVED"),
)

STAGES = tuple(stage for _, stage in ROUTE_TABLE)
SKILL_FOR_STAGE = dict((stage, skill) for skill, stage in ROUTE_TABLE)

# On-demand stages: materialisable by a skill, but on no type_route. The list
# is published by the same contract (one list, two consumers) so the router and
# the state machine cannot drift apart.
#
# Why PROCESS_WINDOW_DEFINED sits here: it fixes a *manufacturing* window whose
# product structure is set by saponification / phase inversion / cooling /
# milling — i.e. it is a first-class dimension for grease, and a second-order
# variable for blended oils (a physical mixing operation that does not create
# product structure). Routing it on every oil project forced a meaningless
# artifact into the chain, in direct conflict with the pack's own
# NO Invented Process Data red line. It stays callable on demand and still
# hands off to VERIFIED when a project does produce it.
ON_DEMAND_STAGES = CONTRACT["on_demand_stages"] if CONTRACT else {}
ON_DEMAND_NEXT = dict((stage, spec["next_stage"]) for stage, spec in ON_DEMAND_STAGES.items())

# Differentiated workflows, published by the contract (one list, two consumers).
TYPE_ROUTES = CONTRACT["type_routes"] if CONTRACT else {}

# Inner-loop ring edges (contract `loop_edges`, v0.9.0): the controlled back
# edges of the PRECISION_GREASE_DEV inner loop. An edge with `from == current`
# adds ONE legal target (`to`) next to the route's normal next step; it never
# replaces it. Inter-ring backtracking is not an edge and stays DENIED — the
# contract publishes no BACKTRACK action (decision 3).
LOOP_EDGES = tuple(CONTRACT.get("loop_edges", ())) if CONTRACT else ()
MAX_ITERATIONS = CONTRACT.get("max_iterations") if CONTRACT else None
LOOP_TARGETS: dict[str, list[str]] = {}
for _edge in LOOP_EDGES:
    LOOP_TARGETS.setdefault(_edge["from"], []).append(_edge["to"])

# The undifferentiated fallback chain, used only when state declares no routed
# project_type. It is the contract's NEW_PRODUCT route, not "every stage the
# router can materialise": ROUTE_TABLE also carries the stages of the
# PRECISION_GREASE_DEV route (a 17-step workflow published as its own
# type_routes entry), and folding those into the fallback would walk an
# unrouted legacy project through a chain it was never designed for.
#
# Deriving it from the route also keeps on-demand stages out by construction
# (they sit on no route), and removes the third hand-maintained copy of the
# chain that used to live here.
FALLBACK_STAGES = tuple(TYPE_ROUTES.get("NEW_PRODUCT", ()))
START_STAGE = "DRAFT"
TERMINAL_STATUSES = {"FROZEN", "CLOSED", "KILLED", "PIVOTED"}

# Stage universe = the contract's stages (28 since PRECISION_GREASE_DEV added
# its 12). A contract that cannot be read leaves the universe empty so decide()
# denies every request instead of guessing.
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
    route = TYPE_ROUTES.get(ptype, FALLBACK_STAGES) if isinstance(ptype, str) else FALLBACK_STAGES

    if current == START_STAGE:
        target_stage = "PROJECT_DEFINED"
    elif current in route:
        idx = route.index(current)
        target_stage = route[idx + 1] if idx + 1 < len(route) else None
    elif current in ON_DEMAND_NEXT:
        # An on-demand stage sits on no route, so its hand-off is the next_stage
        # published in the contract rather than a route neighbour.
        target_stage = ON_DEMAND_NEXT[current]
    elif current in FALLBACK_STAGES:
        idx = FALLBACK_STAGES.index(current)
        target_stage = FALLBACK_STAGES[idx + 1] if idx + 1 < len(FALLBACK_STAGES) else None
    else:
        target_stage = None

    # Legal targets: the route's next step, PLUS any declared inner-loop ring
    # edge leaving this stage (`loop_edges`). An edge is offered only when the
    # active route contains it as well, so the exemption can never leak into a
    # route that does not declare both endpoints (the six oil routes have
    # neither stage). It is an addition, never a replacement: the normal next
    # step stays legal.
    next_targets = [target_stage] if target_stage is not None else []
    ring_targets = [target for target in LOOP_TARGETS.get(current, ()) if target in route]
    next_targets.extend(ring_targets)

    if not next_targets:
        return {"decision": "DENY", "reason": f"stage {current} is the final routed stage; no further step exists", "skill": None}

    if requested_stage == current:
        return {"decision": "HOLD", "reason": f"project is already at {current}; no step to take", "skill": None}
    if requested_stage not in next_targets:
        if len(next_targets) == 1:
            reason = f"cross-stage jump rejected: next allowed stage is {next_targets[0]}, requested {requested_stage}"
        else:
            reason = (
                f"cross-stage jump rejected: next allowed stages are {', '.join(next_targets)}, "
                f"requested {requested_stage}"
            )
        return {"decision": "DENY", "reason": reason, "skill": None}

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

    # Fail closed instead of the bare KeyError this used to raise: a stage the
    # contract publishes but ROUTE_TABLE has no producer for is a deployment bug,
    # and a crash is not a routing decision.
    skill = SKILL_FOR_STAGE.get(requested_stage)
    if skill is None:
        return {
            "decision": "DENY",
            "reason": (
                f"stage {requested_stage} has no producing skill in ROUTE_TABLE; "
                "add the (skill, stage) entry in skills/lubricant-rd-agent/scripts/route_step.py"
            ),
            "skill": None,
        }

    reason = "declared inner-loop edge permitted" if requested_stage in ring_targets else "single-step advancement permitted"
    return {"decision": "ALLOW", "reason": reason, "skill": skill}


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


def list_loop_edges(project_type: str) -> int:
    """Print the declared inner-loop back edges of one route: `from -> to (kind)`.

    Only edges whose two endpoints both sit on that route are printed, because
    the exemption is route-local; a route without edges prints nothing and still
    exits 0. Publishing this here (same pattern as `--list-stages`) keeps callers
    from keeping a third copy of the ring in sync by hand.
    """
    if CONTRACT is None:
        print(f"DENY: routing contract unavailable: {'; '.join(CONTRACT_ERRORS)}")
        return 1
    route = TYPE_ROUTES.get(project_type)
    if route is None:
        print(f"DENY: project_type {project_type!r} has no routed stage chain; publish type_routes[{project_type!r}] in contracts/state-machine.json")
        return 1
    for edge in LOOP_EDGES:
        if edge["from"] in route and edge["to"] in route:
            print(f"{edge['from']} -> {edge['to']} ({edge['kind']})")
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--list-stages":
        if len(sys.argv) != 3:
            print("Usage: python route_step.py --list-stages <PROJECT_TYPE>")
            return 1
        return list_stages(sys.argv[2])
    if len(sys.argv) >= 2 and sys.argv[1] == "--list-loop-edges":
        if len(sys.argv) != 3:
            print("Usage: python route_step.py --list-loop-edges <PROJECT_TYPE>")
            return 1
        return list_loop_edges(sys.argv[2])
    if len(sys.argv) != 2:
        print("Usage: python route_step.py <input.json>")
        print("       python route_step.py --list-stages <PROJECT_TYPE>")
        print("       python route_step.py --list-loop-edges <PROJECT_TYPE>")
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
