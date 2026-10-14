---
name: lubricant-rd-agent
description: Router-only Meta-Skill for the Lubricant R&D Domain Pack. Evaluates current project state and gate readiness; ALLOWs only the immediate next stage according to project_type, DENYs cross-stage jumps, and HOLDs requests while evidence gaps or gate conditions remain unresolved. Also documents the intra-stage revision (REVISE) action used for repeated bench-swap reproductions, and the inner-loop ring edges (loop_edges) of the PRECISION_GREASE_DEV route. Use when user mentions "lubricant-rd-agent", "路由检查", "阶段流转", "推进阶段", "route step", "研发流程门禁", "段内 revision", "换釜复现", "内环迭代", "环边", or requesting stage advancement in lubricant development.
---

# Lubricant R&D Agent (Meta-Skill Router)

The central orchestrator and gatekeeper for the Lubricant R&D Domain Pack.
This skill strictly evaluates stage advancement feasibility. It does not perform business calculation, generate data artifacts, or qualify methods.

---

## 1. Routing Contracts by Project Type

Advancement follows a deterministic, ordered stage chain configured by `project_type`. Seven routes are published by `contracts/state-machine.json` (`type_routes`); each ends at `APPLIED`, and the chain lengths are 12 / 10 / 8 / 8 / 7 / 8 / 19.

- **NEW_PRODUCT** (新产品正向开发):
  `project-definition` (PROJECT_DEFINED) -> `duty-definition` (DUTY_DEFINED) -> `duty-challenge-analysis` (CHALLENGES_DEFINED) -> `failure-ctq-analysis` (FAILURE_CTQ_DEFINED) -> `test-method-qualification` (TEST_METHODS_QUALIFIED) -> `formulation-design` (DESIGN_SPACE_DEFINED) -> `doe-design` (EXPERIMENT_DESIGNED) -> `experiment-import` (EXPERIMENT_RUNNING) -> `statistical-analysis` (MODEL_BUILT) -> `optimization` (OPTIMIZED) -> `gate-review` (VERIFIED) -> `application-validation` (APPLIED)

- **IMPROVEMENT** (已有产品性能优化):
  `PROJECT_DEFINED` -> `FAILURE_CTQ_DEFINED` -> `TEST_METHODS_QUALIFIED` -> `DESIGN_SPACE_DEFINED` -> `EXPERIMENT_DESIGNED` -> `EXPERIMENT_RUNNING` -> `MODEL_BUILT` -> `OPTIMIZED` -> `VERIFIED` -> `APPLIED`

- **COST_DOWN** (降本替代):
  `PROJECT_DEFINED` -> `FAILURE_CTQ_DEFINED` -> `DESIGN_SPACE_DEFINED` -> `EXPERIMENT_DESIGNED` -> `EXPERIMENT_RUNNING` -> `OPTIMIZED` -> `VERIFIED` -> `APPLIED`

- **CUSTOMIZATION** (客户定制):
  `PROJECT_DEFINED` -> `FAILURE_CTQ_DEFINED` -> `TEST_METHODS_QUALIFIED` -> `DESIGN_SPACE_DEFINED` -> `EXPERIMENT_DESIGNED` -> `EXPERIMENT_RUNNING` -> `VERIFIED` -> `APPLIED`

- **EXPLORATION** (机理/平台型探索):
  `PROJECT_DEFINED` -> `DESIGN_SPACE_DEFINED` -> `EXPERIMENT_DESIGNED` -> `EXPERIMENT_RUNNING` -> `MODEL_BUILT` -> `VERIFIED` -> `APPLIED`

- **PROCESS_ROBUSTNESS** (生产复现):
  `PROJECT_DEFINED` -> `FAILURE_CTQ_DEFINED` -> `TEST_METHODS_QUALIFIED` -> `DESIGN_SPACE_DEFINED` -> `EXPERIMENT_DESIGNED` -> `EXPERIMENT_RUNNING` -> `MODEL_BUILT` -> `APPLIED`
  (No `OPTIMIZED`: the formula is not re-optimised after a kettle/batch swap.)

- **PRECISION_GREASE_DEV** (精密传动脂开发):
  `PROJECT_DEFINED` -> `DUTY_DEFINED` -> `FAILURE_MECHANISM_DEFINED` -> `REFERENCE_MATERIAL_RESOLVED` -> `TEST_METHODS_QUALIFIED` -> `DESIGN_SPACE_DEFINED` -> `BENCH_RESOURCE_REGISTERED` -> `EXPERIMENT_DESIGNED` -> `BATCH_PRODUCED` -> `SCREENING_PASSED` -> `BENCH_TESTED` -> `VARIANCE_ASSESSED` -> `MODEL_BUILT` -> `NEXT_BATCH_DECIDED` -> `NON_INFERIORITY_PASSED` -> `PROCESS_SCALE_VALIDATED` -> `VERIFIED` -> `APPLIED` -> `KNOWLEDGE_ARCHIVED`
  (19 stages over 17 process steps; steps 9-13 form the inner-loop ring — see §6.)

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
| `DENY: cross-stage jump rejected` on `BENCH_TESTED → TEST_METHODS_QUALIFIED` | 环间回退（台架发现方法不可靠 / 判据不可达 / 工况理解错误） | **STOP + 人工判断**。系统内没有合法通道（无 `BACKTRACK`）：人工决策 + 系统外手工构造新工件。**不得**用环边 / `REVISE` / `ROLLBACK` 伪装（§6.3）。 |
| `DENY: iteration N exceeds max_iterations` | 内环轮次已达上限（12 ≈ 一年台架轮次） | **STOP**。停止迭代，记录 `PIVOT` 或 `KILL`；不得再开新一轮。 |

---

## 5. Intra-Stage Revision (REVISE) — 段内迭代，不移动 `stage`

当配方已冻结、需要在**同一个 stage 内反复换釜/换批复现**时，**不要走 `ROLLBACK`**。`ROLLBACK`
的前缀断言（`accepted_stages == stages[:after_index+1]`）要求整链回退再整链重走，会让 `version`
与 gate 签批记录无限膨胀（配方一个字不改，却每次重做整条 gate 链）；绕过状态机私改工件则破坏契约。

`REVISE` action 解决这一断点：

- `stage` **不变**、`status` 保持 `ACTIVE`、`version` **递增**、`accepted_stages` 前缀**不变**。
- 必须携带 `revision` 记录：`reason` / `operator` / `impact`。

`impact` 分级决定签批（对齐实施计划 V1.4 C1，防止 V3"谁批准的"指向旧配方版本的签批人）：

| `impact` | 含义 | 签批要求 |
|---|---|---|
| `PROCESS_ONLY` | 只动工艺（换釜/换批/放大），配方与 CTQ 不变 | **复用**原 gate 复核签批；`revision.reuses_review_of` = 被沿用复核的版本号（≤ 当前 version），revision 记录须注明"沿用第 N 版复核" |
| `FORMULA_OR_CTQ` | 配方或 CTQ 变更 | **强制该段重新技术复核**；`revision.re_review` 须含 `technical_reviewer` 与 `reviewed_version`（= 新版本号），否则 `REVISE` 被拒 |

示例（`PROCESS_ONLY`，沿用第 7 版复核；换釜/换批复现场景，段内迭代不移动 stage）：

```json
{
  "kind": "REVISE", "gate_status": "GO",
  "accepted_stages": ["DRAFT", "PROJECT_DEFINED", "...", "MODEL_BUILT"],
  "before": { "stage": "MODEL_BUILT", "status": "ACTIVE", "version": 7, "...": "..." },
  "after":  { "stage": "MODEL_BUILT", "status": "ACTIVE", "version": 8, "...": "..." },
  "revision": { "reason": "换 2 号生产釜复现，配方未变", "operator": "R&D owner",
                "impact": "PROCESS_ONLY", "reuses_review_of": 7, "revision_index": 1 }
}
```

### 5.1 上限：同一 `stage` 内 ≤ 3 次

同一 stage 内连续 `REVISE` **不得超过 3 次**。第 3 次之后若仍需复现，**停止段内迭代，重新评估设计
空间**——这正是实施计划 §7.1 触发条件 2（换釜复现成为常规动作、同一产品累计 ≥3 次 → 启动二维
状态机评估）的落地信号。

**上限是软约定，不是硬校验**：`validate_state_machine.py` 是单事件、无历史的状态校验，无法可靠
统计一段内的 revision 次数，且硬编码计数既可伪造又属于"过程政策"而非"状态合法性"。因此只在
可选字段 `revision.revision_index` > 3 时打印 `WARNING`（不阻断 exit 0），真正约束由本条约定与
流程评审承担。

---

## 6. Inner-Loop Iteration (内环迭代) — controlled back edges, inter-ring backtracking stays DENIED

The PRECISION_GREASE_DEV (精密传动脂) inner loop of 5 steps is a loop body with an exit
criterion, not a linear chain:

```
BATCH_PRODUCED → SCREENING_PASSED → BENCH_TESTED → VARIANCE_ASSESSED
      ↑                 │                                    │
      └── REWORK ───────┘              └──── LOOP_BACK ──────┘
                          VARIANCE_ASSESSED → MODEL_BUILT  (exit)
```

Both back edges are published by the contract (`contracts/state-machine.json` → `loop_edges`).
Read them, never retype them:

```bash
python skills/lubricant-rd-agent/scripts/route_step.py --list-loop-edges PRECISION_GREASE_DEV
# VARIANCE_ASSESSED -> BATCH_PRODUCED (LOOP_BACK)
# SCREENING_PASSED -> BATCH_PRODUCED (REWORK)
```

### 6.1 When to redo, when to continue, when to exit

| Situation | Edge | What it means | `iteration` |
|---|---|---|---|
| 理化筛测 FAIL / INCONCLUSIVE（`screening.json` → `gate_to_bench = BLOCKED`） | `SCREENING_PASSED → BATCH_PRODUCED` (**REWORK**) | Remake the batch/sample; the bench slot is not spent — so the cap does NOT apply to this edge | unchanged (same round) |
| Round finished, criterion not met, information still expected | `VARIANCE_ASSESSED → BATCH_PRODUCED` (**LOOP_BACK**) | Start the next bench round (new formula / new batch) | +1 |
| Criterion met / no new information / bench slots exhausted | none — normal advance | `VARIANCE_ASSESSED → MODEL_BUILT` leaves the inner loop | — |
| `iteration` has reached `max_iterations` (12 ≈ one year of bench rounds) | none | STOP the loop: record `PIVOT` or `KILL`. A further round is rejected: `iteration 13 exceeds max_iterations 12; stop the inner loop and record PIVOT or KILL` | — |

Every round's ending must land in the merged bench artifact `bench.json` as `stop_state`
(`CONTINUE` / `GOAL_MET` / `NO_NEW_INFORMATION` / `RESOURCE_EXHAUSTED` / `PIVOT` / `KILL`).

### 6.2 Semantics of a ring-edge advance (and what it deliberately does NOT change)

- **Routing**: when the current stage is the `from` of a declared edge, that edge's `to`
  becomes an ADDITIONAL legal target — the route's own next step stays legal. From
  `SCREENING_PASSED` both `BENCH_TESTED` (forward) and `BATCH_PRODUCED` (rework) ALLOW.
- **State machine**: a ring advance is a legal `GO`. `version` and the stage-sequence
  history are NOT rewritten (a back edge increments an `iteration` counter, not a version),
  and the event must carry `iteration` (1-based, ≤ `max_iterations`) — the validator is
  stateless, so the caller carries the count.
- **Evidence is append-only (铁律 8)**: round 3 must never void what rounds 1–2 recorded.
  `ROLLBACK`'s "invalidate the stages you passed" semantics is exactly what the ring does
  NOT do, which is why the grease route does not use `ROLLBACK` at all.
- **Route-local**: an edge is honoured only inside a route that contains BOTH endpoints.
  The six oil routes declare none, so their routing behaviour is unchanged.

### 6.3 ★ Boundary: inter-ring backtracking requires human judgement (环间回退需人工判断)

The bench showing the method unreliable, the criterion being unreachable, or the duty
being misunderstood — i.e. **inter-ring backtracking** such as
`BENCH_TESTED → TEST_METHODS_QUALIFIED` — is still **DENIED by the system**:

```
DENY: cross-stage jump rejected: next allowed stage is VARIANCE_ASSESSED, requested TEST_METHODS_QUALIFIED
```

Decision 3 ships **no `BACKTRACK` action**, so there is no in-system channel for it. The
scientist must **judge it by hand, decide outside the system, and construct the new
artifact manually** (refactor plan §4.5 — an accepted, documented gap, not a bug). Do not
try to express it through a ring edge, `REVISE`, or `ROLLBACK`: that writes history the
contract does not sanction.

Watch this boundary: if inter-ring backtracking fires often (say twice in a month), the ring
design is wrong and `BACKTRACK` must be re-evaluated (refactor plan §4.5 observation metric).

---

## 7. Strict Blacklist (Prohibitions)

1. **NO Business Calculations**: DO NOT calculate blend ratios, costs, regression formulas, or statistics.
2. **NO Artifact Generation**: DO NOT write or modify any domain artifacts; this skill only emits routing decisions.
3. **NO Synthetic Promotion**: DO NOT promote SYNTHETIC evidence to PHYSICAL or grant Stage Gate exceptions.
4. **NO Silent Routing**: DO NOT proceed to run downstream skills when `route_step.py` exits with non-zero (DENY/HOLD).

