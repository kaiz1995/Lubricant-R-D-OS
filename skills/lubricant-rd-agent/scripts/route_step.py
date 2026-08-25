"""Router check for the lubricant-rd-agent Meta-Skill.

Pure stdlib. Reads one JSON object with project_state + requested_stage and
prints ALLOW (exit 0) or DENY/HOLD with reasons (exit 1). Never writes
artifacts and never performs business calculation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


# Frozen planned order: skill -> target stage it produces.
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
    ("gate-review", "VERIFIED"),
)

STAGES = tuple(stage for _, stage in ROUTE_TABLE)
SKILL_FOR_STAGE = dict((stage, skill) for skill, stage in ROUTE_TABLE)
NEXT_STAGE = dict(zip(STAGES, STAGES[1:]))
START_STAGE = "DRAFT"
TERMINAL_STATUSES = {"FROZEN", "CLOSED", "KILLED", "PIVOTED"}
KNOWN_STAGES = (START_STAGE, *STAGES)


def decide(project_state: object, requested_stage: str) -> dict:
    """Return {'decision': 'ALLOW'|'DENY'|'HOLD', 'reason': str, 'skill': str|None}."""
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

    if current == START_STAGE:
        target_stage = "PROJECT_DEFINED"
    else:
        target_stage = NEXT_STAGE.get(current)
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


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python route_step.py <input.json>")
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
