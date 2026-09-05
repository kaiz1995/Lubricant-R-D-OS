---
name: lubricant-rd-agent
description: Router-only Meta-Skill for the Lubricant R&D Domain Pack. Evaluates current project state and gate readiness; ALLOWs only the immediate next stage according to project_type, DENYs cross-stage jumps, and HOLDs requests while evidence gaps or gate conditions remain unresolved. Use when user mentions "lubricant-rd-agent", "路由检查", "阶段流转", "推进阶段", "route step", "研发流程门禁", or requesting stage advancement in lubricant development.
---

# Lubricant R&D Agent (Meta-Skill Router)

The central orchestrator and gatekeeper for the Lubricant R&D Domain Pack.
This skill strictly evaluates stage advancement feasibility. It does not perform business calculation, generate data artifacts, or qualify methods.

---

## 1. Routing Contracts by Project Type

Advancement follows a deterministic, ordered stage chain configured by `project_type`:

- **NEW_PRODUCT** (新产品正向开发):
  `project-definition` (PROJECT_DEFINED) -> `duty-definition` (DUTY_DEFINED) -> `duty-challenge-analysis` (CHALLENGES_DEFINED) -> `failure-ctq-analysis` (FAILURE_CTQ_DEFINED) -> `test-method-qualification` (TEST_METHODS_QUALIFIED) -> `formulation-design` (DESIGN_SPACE_DEFINED) -> `doe-design` (EXPERIMENT_DESIGNED) -> `experiment-import` (EXPERIMENT_RUNNING) -> `statistical-analysis` (MODEL_BUILT) -> `optimization` (OPTIMIZED) -> `gate-review` (VERIFIED)

- **IMPROVEMENT** (已有产品性能优化):
  `PROJECT_DEFINED` -> `FAILURE_CTQ_DEFINED` -> `TEST_METHODS_QUALIFIED` -> `DESIGN_SPACE_DEFINED` -> `EXPERIMENT_DESIGNED` -> `EXPERIMENT_RUNNING` -> `MODEL_BUILT` -> `OPTIMIZED` -> `VERIFIED`

- **COST_DOWN** (降本替代):
  `PROJECT_DEFINED` -> `FAILURE_CTQ_DEFINED` -> `DESIGN_SPACE_DEFINED` -> `EXPERIMENT_DESIGNED` -> `EXPERIMENT_RUNNING` -> `OPTIMIZED` -> `VERIFIED`

- **CUSTOMIZATION** (客户定制):
  `PROJECT_DEFINED` -> `FAILURE_CTQ_DEFINED` -> `TEST_METHODS_QUALIFIED` -> `DESIGN_SPACE_DEFINED` -> `EXPERIMENT_DESIGNED` -> `EXPERIMENT_RUNNING` -> `VERIFIED`

- **EXPLORATION** (机理/平台型探索):
  `PROJECT_DEFINED` -> `DESIGN_SPACE_DEFINED` -> `EXPERIMENT_DESIGNED` -> `EXPERIMENT_RUNNING` -> `MODEL_BUILT` -> `VERIFIED`

---

## 2. Input Specification

A single JSON object providing `project_state` and `requested_stage`:

```json
{
  "project_state": {
    "project_id": "WGO-DOE-001",
    "project_type": "NEW_PRODUCT",
    "stage": "PROJECT_DEFINED",
    "status": "ACTIVE",
    "evidence_scope": "PHYSICAL",
    "gate_status": "GO",
    "evidence_gaps": [],
    "unsatisfied_conditions": []
  },
  "requested_stage": "DUTY_DEFINED"
}
```

---

## 3. Deterministic Execution & Decision Rules

Execute the standalone routing verification script:

```bash
python skills/lubricant-rd-agent/scripts/route_step.py <input.json>
```

### Decision Logic
1. **ALLOW (Exit code 0)**:
   - `requested_stage` is the immediate adjacent next stage in the active workflow.
   - `evidence_scope == "PHYSICAL"`.
   - `gate_status == "GO"` and both `evidence_gaps` and `unsatisfied_conditions` are empty.
   - Status is `ACTIVE`.
2. **DENY (Exit code 1)**:
   - Cross-stage jump: requested stage skips one or more steps.
   - Synthetic evidence: `evidence_scope == "SYNTHETIC"` cannot authorize stage advancement.
   - Terminal status: project is in `FROZEN`, `CLOSED`, `KILLED`, or `PIVOTED`.
   - Unknown stage or invalid input format.
3. **HOLD (Exit code 1)**:
   - Gate status is not `GO` (e.g. `HOLD`).
   - `evidence_gaps` or `unsatisfied_conditions` contain unresolved items.
   - Project is already at the requested stage.

```bash
# 🔴 CHECKPOINT · STOP: Halt execution upon DENY or HOLD. Report blocking criteria to user.
```

---

## 4. Failure Modes & Fallback Actions (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `DENY: cross-stage jump rejected` | 试图跳过前置阶段直接推进 | **STOP**。回退到当前阶段的合法紧邻下一阶段（按照 project_type 顺序流转）。 |
| `DENY: SYNTHETIC evidence cannot authorize stage advancement` | 缺少真实物理台架/实验数据 | **STOP**。禁止放行。必须在对应技能中采集或导入 PHYSICAL 范围实验数据。 |
| `HOLD: unresolved: evidence gap: ...` | 前置评估存在未解缺口 | **STOP**。输出缺口清单，调用前序技能补齐对应物性、文献或台架标定证据。 |
| `DENY: project status is terminal` | 项目已处于终止或冻结状态 | **STOP**。不得推进，需项目主管发起再激活（RE-OPEN）流程。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Business Calculations**: DO NOT calculate blend ratios, costs, regression formulas, or statistics.
2. **NO Artifact Generation**: DO NOT write or modify any domain artifacts; this skill only emits routing decisions.
3. **NO Synthetic Promotion**: DO NOT promote SYNTHETIC evidence to PHYSICAL or grant Stage Gate exceptions.
4. **NO Silent Routing**: DO NOT proceed to run downstream skills when `route_step.py` exits with non-zero (DENY/HOLD).

