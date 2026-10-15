---
name: grease-screening
description: Record one cheap physical/chemical screen at SCREENING_PASSED - cone penetration (including worked-penetration change), dropping point, oil separation, evaporation loss, shear stability and appearance uniformity, each with value, unit, limit and verdict - and decide the bench gate. Use when user mentions "grease-screening", "理化筛测", "筛测判据", "锥入度", "滴点", "析油率", "蒸发损失", "剪切安定性", "不送台架", or advancing to SCREENING_PASSED in lubricant R&D.
---

# Grease Screening (SCREENING_PASSED · 理化筛测)

Record one cheap physical/chemical screen at `SCREENING_PASSED` and decide whether the
sample may occupy a bench slot. This is a GATE, NOT a selection criterion, NOT a
performance claim, NOT a bench result, and NOT a model input.

Authority schema: `../../schemas/screening.schema.json` (or local
`references/screening.schema.json` in the deployed bundle). Verdict, gate and release-rule
anchor: `scripts/grease_screening_policy.py`.

Why this stage exists: **the bench is the bottleneck of the whole campaign** - about 2
positions per round and roughly 30 days per round. A slot spent on an obviously-unqualified
sample is a month lost, so cheap fast tests exist to reject what nobody should have sent.
This is also the inner loop's **first rework point**: a FAIL sends the sample straight back
to Stage 9 (grease-batch) without ever touching the bench.

**Read this before using any number this stage produces: physical/chemical indices usually
have LOW discrimination power between close candidate formulas.** Most qualified greases
pass all of them, so a screen that separates nothing still passes everything. This stage
can therefore only ever answer "is this sample obviously unqualified?" - never "is this
candidate better?". A PASS means exactly `not obviously unqualified`. Anyone who optimises
cone penetration, dropping point or oil separation as if they were performance metrics is
misusing this stage, and any code path that would rank candidates by a screened index is a
defect against the purpose of this stage. Selection happens at the bench (Stage 11) and in
the sequential decision (Stage 13), never here.

---

## 1. Input Specification (contract in)

Input is a single JSON object: the upstream artifact paths, the optional bench request,
the screening measurements, and the artifact-level evidence. The following is the shape of
a real request (values illustrative):

```json
{
  "project_artifact": "project.json",
  "batch_artifact": "batch.json",
  "sample_artifact": "sample.json",
  "evidence_scope": "PHYSICAL",
  "evidence": [
    {
      "evidence_id": "E-SC-001",
      "statement": "Screening lab worksheet SL-001 records value, unit, limit and verdict for each screened index.",
      "source": "Screening lab worksheet SL-001",
      "status": "OBSERVED"
    }
  ],
  "screening": {
    "screening_id": "SCR-PG-001",
    "sample_reference": "SMP-PG-001",
    "tests": [
      { "test_id": "ST-001", "test_name": "PENETRATION", "value": 265, "unit": "0.1 mm", "limit": 340, "verdict": "PASS" },
      { "test_id": "ST-002", "test_name": "WORKED_PENETRATION_CHANGE", "value": 12, "unit": "0.1 mm", "limit": 30, "verdict": "PASS" },
      { "test_id": "ST-003", "test_name": "DROPPING_POINT", "value": 185, "unit": "degC", "limit": "180 min", "verdict": "PASS" },
      { "test_id": "ST-004", "test_name": "OIL_SEPARATION", "value": 1.2, "unit": "percent mass", "limit": 5, "verdict": "PASS" },
      { "test_id": "ST-005", "test_name": "EVAPORATION_LOSS", "value": 2.5, "unit": "percent mass", "limit": 3, "verdict": "PASS" },
      { "test_id": "ST-006", "test_name": "SHEAR_STABILITY", "value": 8, "unit": "percent change", "limit": 10, "verdict": "PASS" },
      { "test_id": "ST-007", "test_name": "APPEARANCE_UNIFORMITY", "value": "uniform", "unit": "visual grade", "limit": "uniform", "verdict": "PASS" }
    ],
    "measurement_replicates": 3
  },
  "bench_request": "SMP-PG-001"
}
```

### Field Invariants (contract in)
- Upstream (hard): `project_artifact` and `batch_artifact` are mandatory.
  `project.json` must be `stage: PROJECT_DEFINED`, `status: ACTIVE`, `decision: GO`;
  `batch.json` must be `stage: BATCH_PRODUCED` **and `decision: GO`**. A batch recorded
  `DEVIATED` or `VOID` has not been dispositioned, so its sample is not screenable: that is
  a HOLD, not a warning. `sample_artifact` is optional but, when supplied, must be
  `stage: BATCH_PRODUCED` and its `sample_id` must equal `screening.sample_reference`.
- `evidence_scope`: `SYNTHETIC` or `PHYSICAL`. A SYNTHETIC record is fixture-only and can
  never authorize stage advancement.
- Screening input fields: `screening_id`, `sample_reference`, `tests`,
  `measurement_replicates`. An unknown field is a hard reject.
- Each test: `test_id` (distinct), `test_name` ∈ the seven frozen indices, `value`, `unit`,
  `limit` (number, string, or null), `verdict` ∈ {`PASS`,`FAIL`,`INCONCLUSIVE`}, plus the
  input-only `note`. One entry per index: measuring the same index twice is a hard reject.
  `PENETRATION` and `DROPPING_POINT` are mandatory - the frozen screen of this campaign is
  not complete without them.
- `measurement_replicates`: a strictly positive integer (replicate count per index).
- `bench_request` (optional): the sample reference a bench slot is requested for. A request
  for a sample whose screen did not clear it is a hard reject (N14).
- DO NOT supply `overall_verdict` or `gate_to_bench`. Both are DERIVED by
  `grease_screening_policy`; supplying either is a hard reject.
- A measurement that was not determined is recorded `verdict: INCONCLUSIVE` with `value`
  carrying an explicit marker such as `not determined` and `note` stating why. It is never
  silently omitted.

### Derived Verdict Rule (computed, never declared)
```
overall_verdict = worst per-test verdict     PASS < INCONCLUSIVE < FAIL
gate_to_bench   = BLOCKED if overall_verdict is FAIL, else RELEASED
```
`gate_to_bench` mirrors the `if/then` rule of `schemas/screening.schema.json`
(`overall_verdict: FAIL` → `gate_to_bench: BLOCKED`) and is derived here so the rule can
never be violated by an artifact this skill produces.

### Release Rule (放行判据) - the first rework point of the inner loop
```
overall_verdict PASS          -> decision GO    : the sample may enter the bench queue
overall_verdict FAIL          -> decision HOLD  : do NOT send to the bench; go straight back
                                                 to Stage 9 (grease-batch) and remake the batch
overall_verdict INCONCLUSIVE  -> decision HOLD  : not obviously unqualified, but not cleared
                                                 either; resolve the undetermined index first
```
The skill's `decision` is deliberately **stricter than the gate field**: the schema fixes
what the gate value may be, while only an all-PASS screen is an actual clearance. A FAIL
returns to Stage 9 without consuming bench capacity - that edge is the reason this stage
exists, and it is normal flow, not an error path.

### Known validation boundary (stated, not hidden)
`schemas/screening.schema.json` fixes six fields per test with `additionalProperties:
false`, so the input-only `note` has no slot in the artifact. The reason an index is
`INCONCLUSIVE` therefore cannot survive into the stored record; the validator cannot check
it there, and that limit is stated rather than hidden. The normal path is exact, because
the gate requires the reason before anything is written.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/grease-screening/scripts/` (or relative `scripts/` from the
skill directory).

### Step 1: Preflight Verification
```bash
python -B skills/grease-screening/scripts/preflight_grease_screening.py <input.json>
```
- Validates the upstream batch (including its release state), the optional sample binding,
  every screened index, the bench request (N14), the artifact evidence, and the workspace's
  artifact names.
- Success: prints the standing low-discrimination `NOTE:`, one `NOTE:` per judged index, a
  `NOTE:` naming frozen indices the screen does not measure, then `GATE:` lines stating the
  derived verdict, the derived gate and the decision, then
  `READY: input can form one SCREENING_PASSED record only` (exit 0).
- Failure: output starts with `HOLD: missing or invalid: ...; no artifact generated`
  (exit 1) and nothing is written.

### Step 2: Build Deterministic Artifact
```bash
python -B skills/grease-screening/scripts/build_screening_artifact.py <input.json> <temporary-file.json>
```
The builder re-runs the preflight checks, strips the input-only `note`, derives
`overall_verdict` (worst per-test verdict) and `gate_to_bench`, and assembles the artifact
from `grease_screening_policy.py` at `stage = "SCREENING_PASSED"` with `project_id` from the
charter. It never invents an index, a limit, or a measurement.

### Step 3: Validate Artifact
```bash
python -B skills/grease-screening/scripts/validate_screening_artifact.py <temporary-file.json>
```
- Validates against `schemas/screening.schema.json` with its `if/then` gate rule, then
  recomputes the whole deterministic policy from the artifact's own tests and asserts every
  field equals it.
- Success: `PASS: deterministic screening artifact conforms to the screening contract`
  (exit 0).
- A `HOLD` artifact with `overall_verdict: FAIL` and `gate_to_bench: BLOCKED` PASSES: it is a
  truthful record of a failed screen.

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3
returns `PASS`.
**Naming rule**: if `screening.json` does not yet exist in the workspace root, commit this
record as `screening.json`; otherwise commit it as
`screening-<project_id>-<screening_id>.json`. That is, the first record of this stage
occupies the canonical name `screening.json` (the stage-gate panel uses this exact name to
mark the stage complete), and subsequent records of the same stage are appended as suffixed
names carrying the record id. After the commit, run
`python scripts/check_artifact_naming.py <workspace_root>` and correct any `HOLD` before
proceeding. The checker also enforces that `project.json`'s `stage` stays the constant
`PROJECT_DEFINED` - it is NOT the project's current stage, and must not be advanced.
```bash
# 🔴 CHECKPOINT · STOP: the screen stops here at SCREENING_PASSED. Next station: BENCH_TESTED (experiment-import), or BATCH_PRODUCED via the REWORK edge.
```

---

## 3. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... batch_artifact ...` / `... must be stage BATCH_PRODUCED` / `... must have decision GO` | 上游批次缺失、未落盘或未放行 | **STOP**。退回 Stage 9 完成 `batch.json`；不得凭空造批次引用。 |
| `HOLD: ... batch_artifact.batch_verdict is DEVIATED: a sample from an unreleased batch is not screenable` | 批次超差未处置就想送筛测 | **STOP**。先在第 9 步处置偏差（判可用则重记判语，判不可用则作废重做），再谈筛测。 |
| `HOLD: ... bench_request refused: ... screening is the bench's precondition (N14)` | 筛测未通过仍请求台架 | **STOP**。不送台架，回第 9 步重做样品；这正是内环的第一个回退点。 |
| `HOLD: ... screening.overall_verdict and screening.gate_to_bench are derived ... must not be supplied` | 手填了派生字段 | **STOP**。删除这两个字段，总判语由每条 verdict 的最差值推导，台架门随之推导。 |
| `HOLD: ... screening.tests must contain the DROPPING_POINT index` | 冻结筛测项被静默省略 | **STOP**。补测该指标；确实没做就记 `INCONCLUSIVE` 并写明原因，不得省略。 |
| `HOLD: ... screening.tests[N].note must state why this index is INCONCLUSIVE` | 未测定却没写原因 | **STOP**。写清为什么没测出来；"没测"本身是记录，不是空白。 |
| `HOLD: ... screening.sample_reference ... must equal sample_artifact.sample_id` | 筛测挂到了别的样品 | **STOP**。核对实际测量的物理样品，改引用而不是改样品号。 |
| `HOLD: ... sample_artifact.batch_reference ... must equal batch_artifact.batch_id` | 样品与批次不匹配 | **STOP**。退回第 9 步核对样品来源。 |
| `HOLD: ... workspace naming: ...` | 工作区存在面板认不出的工件名 | **STOP**。按 `check_artifact_naming.py` 的报错改名，再重跑 preflight。 |
| `GATE: the screen FAILED (X): the sample does not go to the bench, it goes back to Stage 9` | 筛测不合格 | **保留工件并停在第 10 步**。这是预期结局：回第 9 步重做样品，台架位不受影响。不得为了"别浪费一批"把 FAIL 改成 PASS。 |
| `GATE: the screen is INCONCLUSIVE (X): ... it does not consume a bench slot until that index is resolved` | 有指标未测定 | 补测该指标或按 INCONCLUSIVE 保留记录；在判据未解之前不占用台架位。 |
| `FAIL: ... overall_verdict ... does not equal the worst per-test verdict ...` | 落盘工件被手工改过 | **STOP**。恢复真实 verdict，用 builder 重新生成；不得手改工件。 |
| `FAIL: ... gate_to_bench RELEASED is illegal over overall_verdict FAIL` | 失败筛测被放行 | **STOP**。这正是 `screening.schema.json` 的 if/then 规则要拦的事；恢复 `BLOCKED`。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法错误 | 检查 `../../schemas/` 与输入文件 JSON 格式。 |

---

## 4. Red Lines & Blacklist (Strict Prohibition)

1. **NO Screening as Selection** - **理化指标的区分度通常很低，只能当门槛，不能当选优依据。** DO NOT
   rank candidates by a screened index, DO NOT present a PASS as evidence that a sample is
   better than another, and DO NOT let any downstream stage treat a screened value as a
   performance metric. A PASS means exactly "not obviously unqualified". Optimising cone
   penetration (or dropping point, or oil separation) as if it were a performance metric is
   a misuse of this stage.
2. **NO Failed Sample to the Bench**: DO NOT release a sample whose screen failed. A FAIL
   goes back to Stage 9 (grease-batch) - that is the inner loop's first rework point, not an
   exception to be argued away. Screening is the bench's precondition (N14).
3. **NO Invented Screen Data**: DO NOT invent a measured value, a limit, or a verdict to make
   the screen look complete. An index nobody measured stays unrecorded or is recorded
   `INCONCLUSIVE` with its reason; a missing limit is not filled in with a plausible number.
4. **NO Hand-Set Verdict or Gate**: DO NOT write `overall_verdict` or `gate_to_bench`. Both are
   derived by `grease_screening_policy` (the aggregate is the worst per-test verdict) and
   re-asserted on validation.
5. **NO Omitted Index**: DO NOT silently drop a frozen index from the screen. An undetermined
   index is recorded `INCONCLUSIVE` with its reason; `PENETRATION` and `DROPPING_POINT` are
   mandatory.
6. **NO Unreleased Sample**: DO NOT screen a sample from a batch recorded `DEVIATED` or
   `VOID`. The deviation must be dispositioned at Stage 9 first.
7. **NO Bypass of Preflight**: DO NOT create, move, or touch the output artifact before
   `preflight_grease_screening.py` has passed. An invalid request produces no artifact at all.
8. **NO Dirty Overwrites**: DO NOT overwrite an existing `screening.json` on a validation
   failure, and do not commit a second record under a taken canonical name. A failed run
   changes nothing on disk.
9. **NO Soft Guidance Words**: forbidden ambiguous words: "灵活调整", "视情况而定", "酌情设置",
   "可以考虑". Every index carries a concrete value, unit, limit and verdict.
10. **NO Cross-Stage Mutation**: DO NOT allocate a bench slot, run a bench test, compute a
    variance component, update a model, or advance the state machine here. Stage 10 records
    the screen, states the gate, and stops.
11. **NO Synthetic Closure**: DO NOT let a SYNTHETIC screen authorize stage advancement, and
    never present a synthetic screen as a physical screening result.
