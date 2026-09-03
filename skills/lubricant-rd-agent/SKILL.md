---
name: lubricant-rd-agent
description: Router-only Meta-Skill for the Lubricant R&D Domain Pack. Read the current project state first; ALLOW only the immediate next stage of the planned order according to project_type, DENY cross-stage jumps, HOLD any request while evidence gaps or gate conditions remain unresolved, and reject advancement on SYNTHETIC evidence. It never performs business calculation.
---

# Lubricant R&D Agent (Meta-Skill)

This skill is the routing gate for the Domain Pack. It does not calculate, generate artifacts, or qualify methods. It decides one thing: may the project advance to the requested stage now?

## Usage contract

1. Read the current project state first: `stage`, `status`, `evidence_scope`, `gate_status`, `evidence_gaps`, `unsatisfied_conditions`, and optional `project_type`.
2. Route within the planned order according to the confirmed `project_type`:

   - **NEW_PRODUCT** (新产品正向开发):
     project-definition -> duty-definition -> duty-challenge-analysis -> failure-ctq-analysis -> test-method-qualification -> formulation-design -> doe-design -> experiment-import -> statistical-analysis -> optimization -> gate-review

   - **IMPROVEMENT** (已有产品性能优化):
     project-definition -> failure-ctq-analysis -> test-method-qualification -> formulation-design -> doe-design -> experiment-import -> statistical-analysis -> optimization -> gate-review

   - **COST_DOWN** (降本替代):
     project-definition -> failure-ctq-analysis -> formulation-design -> doe-design -> experiment-import -> optimization -> gate-review

   - **CUSTOMIZATION** (客户定制):
     project-definition -> failure-ctq-analysis -> test-method-qualification -> formulation-design -> doe-design -> experiment-import -> gate-review

   - **EXPLORATION** (机理/平台型探索):
     project-definition -> formulation-design -> doe-design -> experiment-import -> statistical-analysis -> gate-review

3. Decide by rule:
   - requested stage is the immediate next stage AND evidence is PHYSICAL AND the gate is GO with no unresolved gaps/conditions -> ALLOW and point to that skill.
   - requested stage skips one or more stages in the active workflow -> DENY cross-stage jump.
   - gate_status is not GO, or evidence_gaps/unsatisfied_conditions are non-empty -> HOLD and list what is missing.
   - evidence_scope is SYNTHETIC -> DENY: synthetic evidence cannot authorize stage advancement.
   - project status is terminal (FROZEN/CLOSED/KILLED/PIVOTED) -> DENY.

## Input

One JSON object with `project_state` and `requested_stage`. `project_state` carries the common artifact contract fields (see schemas/); this router reads only the routing-relevant subset:

```json
{
  "project_state": {
    "project_id": "WGO-DOE-001",
    "project_type": "COST_DOWN",
    "stage": "PROJECT_DEFINED",
    "status": "ACTIVE",
    "evidence_scope": "PHYSICAL",
    "gate_status": "GO",
    "evidence_gaps": [],
    "unsatisfied_conditions": []
  },
  "requested_stage": "FAILURE_CTQ_DEFINED"
}
```

Missing `evidence_scope` or a non-GO gate blocks advancement.

## Execution

Run `python scripts/route_step.py <input.json>`. Exit 0 prints ALLOW with the target skill; exit 1 prints DENY/HOLD with reasons. No artifact is written.

## Boundaries

The router never computes, never writes artifacts, and never upgrades SYNTHETIC evidence to method qualification or release approval. hello-lubricant is a load-and-invoke smoke skill and is not a routing target.
