---
name: variance-assessment
description: Assess whether an observed bench difference is real or noise at VARIANCE_ASSESSED - nested variance decomposition, repeatability sigma, effect size, power and the four-verdict decision. Use when user mentions "variance-assessment", "方差与重复性判定", "方差分解", "重复性判定", "这个差异是真的吗", "检验功效", "UNDERPOWERED", "SIGMA_MAX", or advancing to step 12 in precision-grease R&D.
---

# Variance Assessment (Step 12 · 方差与重复性判定)

Record the engine-computed answer to the question that decides whether the whole inner loop is meaningful:
**is this difference real, or is it noise?** The record is built at `VARIANCE_ASSESSED` and carries a nested
variance decomposition, an effect size, the power against the pre-registered delta, and exactly one of four
frozen verdicts.

This is NOT a model update (step 13), NOT a formulation decision, and NOT an optimization. It reports what
the engine found and routes the campaign accordingly.

Authority schema: `../../schemas/variance.schema.json` (or local `references/variance.schema.json` in the
deployed bundle). Derived-tier and routing anchor: `scripts/variance_assessment_policy.py`. Engine IO
contracts (nested, consumed by the engine, not by this skill's validator):
`../../domains/lubricant/schemas/variance_input.schema.json` and `variance_result_schema.json`.

---

## 0. The three rules this skill exists to enforce

### Rule 1 — the LLM does no deterministic computation, and `UNDERPOWERED` is never folded away

Every number in the record comes from the frozen statistics engine (`ENGINE_NAME = statistics`,
`METHOD = NESTED_VARIANCE_V1`). The skill builds the engine input, calls the engine, and projects the engine's
answer; it never computes a statistic and never accepts a hand-entered figure. `computed_by` is the constant
`ENGINE`, and the validator re-derives the frozen identities (`k_ratio = delta / (sigma_total * k)`,
`SIGMA_MAX = delta / k`, every resolution row as `4 * sigma / sqrt(n)`) from the artifact's own numbers, so a
hand-edited figure cannot pass.

The engine returns exactly four verdicts and this skill passes them through **unchanged**:

| Verdict | Condition | What it authorizes |
|---|---|---|
| `CONSISTENT_DIFFERENCE` | difference exceeds `k * sigma` and the same-arm replicates agree on outcome | the only verdict that releases the step-13 model update |
| `NO_DETECTABLE_DIFFERENCE` | the design was capable (power ≥ 0.80, sigma estimable, delta resolvable) and found nothing | record the direction as excluded; do NOT update the model |
| `UNDERPOWERED` | the design could NOT have answered the question (power < 0.80, sigma not estimable, or the method's own sigma exceeds `SIGMA_MAX = delta / k`) | **nothing** — the question is unanswerable at this resolution |
| `REPLICATE_INCONSISTENT` | same-arm replicates contradict on outcome, or share a `sample_id` across `batch_id`s | **nothing** — no difference claim is admissible from this round |

> **`UNDERPOWERED` must stay its own verdict. Collapsing it into `NO_DETECTABLE_DIFFERENCE` is the most
> expensive error in grease R&D.** "We cannot measure it" is not "there is no difference": the conflation
> converts an incapable design into a positive finding and so justifies a wrong product decision. The engine
> keeps the two separate on purpose, and this skill never rewrites a verdict. The validator enforces the
> direction that matters: a record whose own numbers say the design was incapable cannot be stored with a
> softer verdict.

### Rule 2 — when k < 3, do NOT add samples: change the method or the criterion

The frozen planning rule is `n ≈ 16/(Δ/σ)² = 16/k²` per arm at α = 0.05 and power 0.80:

| k = Δ/σ | per-arm n | total runs | bench rounds | calendar time |
|---|---|---|---|---|
| k ≥ 3 | 2 | 4 | 2 | ≈ 2 months, feasible |
| k = 2 | 4 | 8 | 4 | ≈ 4 months, marginal |
| k = 1.5 | 8 | 16 | 8 | ≈ 8 months, infeasible |
| k ≤ 1 | ≥ 16 | 32 | 16 | ≈ 16 months, hopeless |

At **2 bench positions per round and 30 days per round**, a k = 1.5 question needs about **8 months for one
conclusion** — a project cannot afford two such judgements a year. **So the requirement does not go on the
sample size; it goes on the METHOD:**

```
SIGMA_MAX = Δ / k        (k = 3)
```

i.e. *"this method's own repeatability sigma must be small enough that a k = 3 separation is visible at
n ≈ 2–3"*. WGO_001: Δ = 1.5 h (additive 4.5 h vs blank 2.5 h), k = 3 → **SIGMA_MAX_REQUIREMENT = 0.5 h**.

**If it cannot be computed, the METHOD is unqualified — that is not a data shortage.** The recovery for an
`UNDERPOWERED` verdict is therefore *change the method (return to step 5) or change the criterion (return to
step 3)*, and the skill's `next_action` says exactly that. Adding replicates is not on the list.

### Rule 3 — sigma needs no dedicated measurement: it accumulates for free

**Sigma does NOT need a dedicated measurement campaign.** It accumulates naturally because a **blank reference
sample goes onto the bench every round** — 0 extra bench positions, and the blank is needed anyway to monitor
bench drift (without it you cannot even tell whether this round's numbers are comparable with last month's).

| Round | blank-sample sigma data | what can be judged |
|---|---|---|
| 1 | n = 1 | baseline only |
| 2 | n = 2 | a first sense of "how much is a lot" |
| **3** | **n = 3** | **sigma is estimable (±50 %), judgements become possible** |
| 6 | n = 6 | sigma is stable (±32 %) |
| 10 | n = 10 | quite reliable (±24 %) |

This is the project's most important cost saving: the earlier estimate that method characterisation would
consume 40–50 % of first-year bench capacity was wrong because it assumed sigma needed dedicated runs. Start
with uncertainty and let it converge — WGO_001 recorded `CONTROL_BAND_V0` marked
`PROVISIONAL_INSUFFICIENT_N` rather than waiting to measure sigma precisely.

**Resolution table — why bench time is a bad place to buy resolution.** The engine reports the smallest
reliably detectable difference ≈ `4σ/√n`:

| σ (bench noise) | n = 3 | n = 6 | n = 12 |
|---|---|---|---|
| 20 h | 46 h | 33 h | 23 h |
| **50 h** | **115 h** | **82 h** | **58 h** |
| 100 h | 230 h | 165 h | 115 h |

The square root is the whole message: **going from n = 3 to n = 12 quadruples the bench effort and only halves
the smallest visible difference.** Effort belongs in the three levers that consume no extra bench positions:

1. **Bigger signal** — pursue changes worth hundreds of hours (thickener system, base-oil family, additive
   presence) rather than 30 h refinements that this resolution can never see.
2. **Lower sigma** — fixed assembly (same operator, same fill mass, same preload), same batch of reducers, and
   intermediate readings (day 1/7/14 torque and temperature) so the criterion becomes a *rate of change*
   instead of an end-point. Halving sigma is worth as much as quadrupling n.
3. **Paired comparison** — A and B on the bench in the SAME round, swapped next round. Benches months apart
   fold drift, season and reducer-batch variation straight into the A−B difference; running them together
   cancels all of it. This is the smartest use of two bench positions.

---

## 1. Input Specification (contract in)

Input is a single JSON object: the step-11 bench-test records, the engine input, the declared input shape, and
the artifact-level evidence. Values below are illustrative:

```json
{
  "campaign_reference": "CMP-PGD-VAR-001",
  "variance_id": "VAR-PGD-001",
  "iteration": 1,
  "evidence_scope": "PHYSICAL",
  "input_mode": "FROZEN_SIGMA",
  "bench_test_artifacts": ["run-b01.json", "run-b02.json", "run-b07.json", "run-a01.json", "run-a02.json"],
  "engine_input": {
    "input_type": "VARIANCE_ANALYSIS",
    "analyses": ["VARIANCE_COMPONENTS", "POWER_ANALYSIS", "CONSISTENCY_CHECK"],
    "replicate_structure": [
      { "level": "BATCH", "n": 3, "group_reference": "ARM-BLANK", "batch_reference": "BATCH-201", "sample_reference": "SAM-B01" },
      { "level": "BENCH", "n": 2, "group_reference": "RUN-B01", "batch_reference": "BATCH-201", "sample_reference": "SAM-B01" }
    ],
    "observations": [
      { "observation_reference": "OBS-B01", "level": "MEASUREMENT", "group_reference": "ARM-BLANK",
        "sample_id": "SAM-B01", "batch_id": "BATCH-201", "run_reference": "RUN-B01",
        "value": 4.2, "at": "2026-02-20T09:00:00Z", "event_occurred": true, "event_time": 4.2 }
    ],
    "censoring": [
      { "observation_reference": "OBS-B07", "event_occurred": false, "event_time": null,
        "censoring_type": "RIGHT", "stop_reason": "RIGHT-censored at the 10 h protocol limit; no event observed, so the 10 h value is not an end-point" }
    ],
    "intervention_events": [
      { "event_id": "IV-01", "description": "bench re-adjusted and re-tested mid-campaign",
        "at": "2026-03-12T09:00:00Z", "until": "2026-03-13T18:00:00Z", "confounds": true }
    ],
    "comparison_arms": { "arm_a_group_reference": "ARM-ADDITIVE", "arm_b_group_reference": "ARM-BLANK" },
    "frozen_sigma_reference": "METHOD-CHAR-S1A-004",
    "frozen_sigma": 0.2,
    "control_band": 0.6,
    "preregistered_delta": 1.5,
    "k_required": 3,
    "alpha": 0.05,
    "target_power": 0.8,
    "resolution_n_values": [2, 3, 6, 12]
  },
  "model_prediction_interval": { "model_reference": "MODEL-PGD-001", "half_width": 2.5, "unit": "h" },
  "evidence": [
    { "evidence_id": "E-VAR-001", "statement": "The frozen sigma comes from the step-5 method characterisation record.",
      "source": "method characterisation S1A-004", "status": "OBSERVED" }
  ]
}
```

### Field Invariants (contract in)

- **Upstream (hard)**: `bench_test_artifacts` is a non-empty array of step-11 `bench_test` record paths. Each
  must validate against `schemas/bench_test.schema.json` and be `stage: BENCH_TESTED`. A record's `decision` is
  **not** required to be GO: a bench run is a run record, and requiring GO would forbid exactly the input this
  step exists to handle — a round that ended in a censored observation.
- All supplied records must agree on **one** `project_id` and **one** `evidence_scope`; the artifact inherits
  both. The declared `iteration` must equal every record's `campaign_iteration`: one variance assessment covers
  one round, never a pool of rounds.
- **Every observation traces to a supplied run.** `run_reference` must resolve to a supplied bench-test record,
  `sample_id`/`batch_id` must equal that record's `sample_reference`/`batch_reference`, and a supplied record
  that no observation references is refused as an omission rather than silently dropped. An upstream run whose
  `censoring_type` is not `NONE` may never reappear as a completed observation, and an uncensored run's
  `event_time` must appear as the value of one of its observations.
- **The three data-quality rules**, enforced here before anything is written:
  1. **Censoring is never an end-point.** A censored observation must not carry `event_time`, must not claim
     `event_occurred: true`, and must declare a non-empty `stop_reason`. A censored observation without one is
     **refused fail-closed** — an unexplained stop is not an observation. Every `censoring` entry, including a
     `NONE` entry, carries a `stop_reason` so the record always states why the run stopped.
  2. **Material identity must be verifiable.** Every observation carries `sample_id` + `batch_id`. A pair that
     shares a `sample_id` while differing in `batch_id` is **not refused here** — it is different things wearing
     the same name, and the engine must return `REPLICATE_INCONSISTENT` for it **regardless of the numbers**.
  3. **Confounding must be excludable.** An intervention window is declared with `confounds: true`; an
     unparseable timestamp, or an observation with no timestamp while such a window exists, is refused because
     the engine cannot prove the observation sits outside the window.
- **`input_mode`** declares which of the three accepted input shapes was used, and the request must actually
  carry that input: `FROZEN_SIGMA` needs `frozen_sigma > 0` plus `frozen_sigma_reference`; `RUN_RECORDS` needs a
  declared replicate structure with a `BENCH` or `BATCH` level; `PREREGISTERED_DELTA` needs
  `preregistered_delta > 0`. The record states which one it used, so the reader never guesses where the noise
  scale came from.
- **The frozen planning constants are not negotiable**: `k_required = 3`, `alpha = 0.05`,
  `target_power = 0.80`. A request that relaxes one is refused rather than silently honoured, so a sample-size
  question can never be answered by two different numbers in two different documents.
- **`engine_input` must not carry a computed result.** There is no field for one: the schema forbids unknown
  properties, and `engine_input` is the engine's own input contract. The engine's `variance_input.schema.json`
  is enforced by the engine itself when the builder calls it.
- `model_prediction_interval` is **optional** and is a *declared* half-width, not a computed one.
- **`evidence`** is non-empty and every item carries `evidence_id`, `statement`, `source`, `status`. A `GAP`
  status is a hard reject here: an unanswerable question belongs on the record as the engine's `UNDERPOWERED`
  verdict, not on the request as an open gap.

### Derived, never asserted

```
decision     = GO  iff verdict == CONSISTENT_DIFFERENCE and no artifact evidence item is GAP
               HOLD otherwise
stop routing = NO_NEW_INFORMATION iff verdict == CONSISTENT_DIFFERENCE
                                    and |engine difference| <= model_prediction_interval.half_width
               CONTINUE otherwise
sigma source = FROZEN_METHOD_CHARACTERIZATION when a frozen sigma is supplied,
               ESTIMATED_FROM_THIS_DESIGN otherwise
```

`stop_state NO_NEW_INFORMATION` is the answer to "a significant difference whose samples fall inside the
model's prediction interval": the model **already predicts** this difference, so another bench round re-learns
what is known. **Stop the inner loop with the existing evidence** instead of spending months to confirm it.

### Stated boundary (not hidden)

`schemas/variance.schema.json` carries no field for the stop routing, so a hand-edited artifact that drops the
`NO_NEW_INFORMATION` sentence cannot be detected by re-derivation. What the validator does enforce is the
direction that matters: the `NO_NEW_INFORMATION` routing is **only legal on a `CONSISTENT_DIFFERENCE`
verdict**, so it can never be attached to an incapable design.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/variance-assessment/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python -B skills/variance-assessment/scripts/preflight_variance_assessment.py <input.json>
```
- Validates the step-11 records, the provenance links, the three data-quality rules, the declared input shape
  and the frozen constants; then prints `READY: input can form one VARIANCE_ASSESSED record`, followed by
  `GATE:` lines (verdict handling, frozen constants, whether arms are declared, whether power will be
  computable) and `NOTE:` lines (which input shape was used, the sigma source, k = Δ/σ).
- Failure: output starts with `HOLD: missing or invalid: ...; no artifact generated` (exit 1) and nothing is
  written.

### Step 2: Build Deterministic Artifact
```bash
python -B skills/variance-assessment/scripts/build_variance_artifact.py <input.json> <temporary-file.json>
```
The builder re-runs the preflight checks, **calls the frozen statistics engine** over `engine_input`
(`variance_engine_bridge.py` finds the engine tree in either layout), and **refuses to write anything when the
engine rejects the input**. It then projects the engine envelope and the canonical decision block into the
artifact shape. Every number in the output is the engine's; the builder computes nothing.

### Step 3: Validate Artifact
```bash
python -B skills/variance-assessment/scripts/validate_variance_artifact.py <temporary-file.json>
```
- Validates against `schemas/variance.schema.json`, then recomputes the frozen identities and the whole
  deterministic policy from the artifact's own fields and asserts every one of them.
- Success: `PASS: deterministic variance-assessment artifact conforms to the variance contract (verdict=...
  computed_by=ENGINE)` (exit 0).
- A `HOLD` decision artifact with verdict `UNDERPOWERED` or `REPLICATE_INCONSISTENT` **PASSES**: it is a
  truthful record of a round that could not answer the question.

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3 returns `PASS`.
**Naming rule**: if `variance.json` does not yet exist in the workspace root, commit this record as
`variance.json`; otherwise commit it as `variance-<project_id>-<variance_id>.json`. That is, the first record of
this stage occupies the canonical name `variance.json` (the stage-gate panel matches this exact name to mark
the stage complete), and later records of the same stage are appended as suffixed names carrying the record id.
After the commit, run `python scripts/check_artifact_naming.py <workspace_root>` and correct any `HOLD` before
proceeding.
```bash
# 🔴 CHECKPOINT · STOP: step 12 stops here at VARIANCE_ASSESSED. Route by verdict; do not compute a model.
```

### Routing after the checkpoint

| Verdict | `decision` | Next move |
|---|---|---|
| `CONSISTENT_DIFFERENCE` (outside the prediction interval) | GO | step 13: update the model from the observations that passed this check, carrying the applicability boundary |
| `CONSISTENT_DIFFERENCE` (inside the prediction interval) | GO | **stop the inner loop** with `stop_state NO_NEW_INFORMATION` and close out with the existing evidence |
| `NO_DETECTABLE_DIFFERENCE` | HOLD | record the direction as excluded; return to step 9 with a different candidate or criterion |
| `UNDERPOWERED` | HOLD | **change the method or the criterion** (step 5 or step 3); the method is unqualified until its own sigma meets `SIGMA_MAX = Δ/k` |
| `REPLICATE_INCONSISTENT` | HOLD | repair the replicate structure (verifiable identity, same-arm outcome agreement), then re-assess |

---

## 3. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... bench_test_artifacts[i] cannot be read` / `... must be stage BENCH_TESTED` | 上游第 11 步台架记录缺失、损坏或阶段不符 | **STOP**。回到第 11 步补齐台架记录，不得手填观测值代替。 |
| `HOLD: ... bench_test records must all carry the same project_id` / `... one valid evidence_scope` | 混入了别的项目或别的证据域的 run | **STOP**。只对同一项目、同一证据域的一轮 run 做一次方差判定。 |
| `HOLD: ... iteration N does not match the campaign_iteration of every supplied bench_test record` | 把两轮 run 混成一次判定 | **STOP**。一次方差判定只覆盖一轮；按轮次分开提交。 |
| `HOLD: ... run_reference ... resolves to no supplied bench_test record` | 观测没有上游台架记录（无出处） | **STOP**。补上该 run 的第 11 步记录；没有记录的观测不得参与判定。 |
| `HOLD: ... bench_test run ... is supplied but no observation references it` | 交了 run 却没有判定它（静默丢弃） | **STOP**。要么为该 run 提供观测，要么从输入中移除并说明原因——不许悄悄丢。 |
| `HOLD: ... is recorded as censored (RIGHT) but no observation of that run carries a matching censoring entry` | 上游删失 run 在下游被当成完整观测 | **STOP**。恢复删失语义（`event_occurred: false`、`event_time: null`、带 `stop_reason` 的删失条目）。 |
| `HOLD: ... is censored but carries event_time=...` | 把删失时刻写成终点值（N9） | **STOP**。删失值永远不得记为 `event_time`；改为 `event_time: null` 并写明 `stop_reason`。 |
| `HOLD: ... is censored without a stop_reason` | 删失未说明停止原因 | **STOP**。补真实停止原因；无法说明就不得作为观测使用。 |
| `HOLD: ... sample_reference ... but observation ... claims sample_id ...` | 观测的材料身份与上游 run 不一致 | **STOP**。以实物记录为准修正身份；同名不同物的重复不算重复（N10 由引擎判 `REPLICATE_INCONSISTENT`）。 |
| `HOLD: ... no parseable at while a confounds=true intervention exists` | 存在混杂窗口但观测无时间戳 | **STOP**。补时间戳，或声明该窗口 `confounds: false` 并给出理由——引擎不猜。 |
| `HOLD: ... k_required is frozen at 3` / `... alpha is frozen at 0.05` / `... target_power is frozen at 0.8` | 试图放宽冻结的规划常数 | **STOP**。常数由包冻结，保证同一问题在不同文档里不会得到两个答案；k < 3 时改方法或改判据，不是放宽 k。 |
| `HOLD: ... input_mode FROZEN_SIGMA requires engine_input.frozen_sigma > 0` | 声明了冻结 σ 却没有给 | **STOP**。提供第 5 步冻结的 σ 与 `frozen_sigma_reference`，或改用 `RUN_RECORDS` / `PREREGISTERED_DELTA` 形状。 |
| `HOLD: ... evidence contains GAP` | 把"这个问题答不出来"写成请求层 GAP | **STOP**。让引擎给出 `UNDERPOWERED` 判定并落在工件上，请求层证据保持非 GAP。 |
| `HOLD: the statistics engine rejected the input: ...` | 引擎自己拒绝了输入（业务规则） | **STOP**。按引擎给出的 `rejection_reasons` 修正输入；引擎拒绝时不落盘任何文件。 |
| `HOLD: the statistics engine tree was not found from this skill's location` | 部署缺少引擎树 | 检查部署：仓库布局需 `domains/lubricant/compute/statistics/engine.py`，部署布局需 `<skill>/engine/lubricant/`。 |
| `FAIL: the artifact must equal the deterministic variance-assessment policy for ...` | 落盘工件被手工改写（例如把 `UNDERPOWERED` 软化成 `NO_DETECTABLE_DIFFERENCE`） | **STOP**。用 builder 重新生成；不得手改工件。 |
| `FAIL: sigma_max_requirement must equal delta / 3 = ...` | 手工改了冻结要求值 | **STOP**。恢复策略推导值，重新生成。 |
| `GATE: POWER_ANALYSIS is requested without a pre-registered delta` | 没有预注册 Δ 却要功效 | 这是**预期的**：引擎报 `NOT_COMPUTABLE`，判定为 `UNDERPOWERED`。补第 3 步的 Δ，或接受该轮无法回答差异问题。 |

---

## 4. Red Lines & Blacklist (Strict Prohibition)

1. **NO Hand-Computed Statistics**: DO NOT compute, adjust or round a variance component, sigma, effect size,
   power, k-ratio or resolution value. Every number comes from the engine; `computed_by` is `ENGINE` and the
   validator re-derives the frozen identities from the artifact's own numbers.
2. **NO Collapsing `UNDERPOWERED`**: DO NOT report an incapable design as `NO_DETECTABLE_DIFFERENCE`, and DO
   NOT soften the verdict when re-writing the artifact. "Cannot measure it" is not "there is no difference" —
   this is the most expensive error in grease R&D.
3. **NO Sample-Size Fix for k < 3**: DO NOT answer an `UNDERPOWERED` verdict by adding replicates. The rule is
   to change the method or the criterion (`SIGMA_MAX = Δ/k`); if the method cannot deliver, the METHOD is
   unqualified, not the data insufficient.
4. **NO Censoring as an End-Point**: DO NOT record a censoring time as `event_time`, DO NOT present an upstream
   censored run as a completed observation, and DO NOT omit a `stop_reason`. A censored observation without one
   is refused fail-closed.
5. **NO Averaging Across Material Identity**: DO NOT treat two replicates that share a `sample_id` but differ in
   `batch_id` as a replicate pair. They are different things with the same name; the engine judges
   `REPLICATE_INCONSISTENT` regardless of the numbers.
6. **NO Unprovenanced Observations**: DO NOT assess an observation whose `run_reference` resolves to no step-11
   record, and DO NOT silently drop a supplied run that no observation references.
7. **NO Bypass of Preflight**: DO NOT create, move, or touch the output artifact before
   `preflight_variance_assessment.py` has passed, and DO NOT write anything when the engine rejects the input.
8. **NO Dirty Overwrites**: DO NOT overwrite an existing `variance.json` on a validation failure, and do not
   commit a second record under a taken canonical name. A failed run changes nothing on disk.
9. **NO Cross-Stage Mutation**: DO NOT update the model, choose a formulation, design a DOE, allocate bench
   slots, or advance the state machine here. Step 12 reports the verdict and routes; step 13 owns the model.
10. **NO Soft Guidance Words**: forbidden ambiguous words: "灵活调整", "视情况而定", "酌情设置", "可以考虑". The
    verdict, the routing and the numbers are concrete.
11. **NO Synthetic Closure**: DO NOT present a SYNTHETIC variance record as physical evidence. A SYNTHETIC
    record is fixture-only and can never authorize stage advancement.

---

## 5. Where sigma comes from (and why it is free)

Sigma is an **asset that accumulates**, not a one-off prerequisite task. Three sources, none of which needs a
dedicated campaign:

| Source | How | Cost | What it gives |
|---|---|---|---|
| **Blank reference sample on every round** ★ main | the blank needed anyway for drift monitoring | **0 extra bench positions** | sigma accumulates round by round: ±50 % at n = 3, ±32 % at n = 6, ±24 % at n = 10 |
| **Cheap physical tests, repeated** | 10 penetration readings / 10 oil-separation dishes on one sample | very low | measurement repeatability `sigma_meas` — which splits the noise: if bench noise is 50 h and measurement noise 2 h, the noise is bench and reducer variation, so lowering measurement effort buys nothing |
| **Historical data mining** | find clean "same formula, same current family, no equipment intervention" replicate pairs in old bench records | 0 (pure analysis) | WGO_001 found two such pairs in 42 columns of history; one was usable, one was discarded as confounded |

**A multi-reading run is not a replicate.** Measuring one sample ten times at one sitting estimates
`sigma_meas` only; using those readings as independent replicates for a formulation comparison is the classic
pseudo-replication error. What gates the decision is bench and batch variation.
