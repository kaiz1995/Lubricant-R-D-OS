---
name: doe-design
description: Record one evidence-bound experiment-design request at EXPERIMENT_DESIGNED; preflight verifies 5 upstream stage artifacts, D/P qualified methods, the mixture↔factor bridge (constraint_role routes variables to components or factors), and bound constraints before building the artifact. On the PRECISION_GREASE_DEV route it defaults to a small sequential round (3–6 samples per round) and enforces the registered bench schedule. Use when user mentions "doe-design", "实验设计", "混料设计", "mixture DOE", "正交实验", "因子设计", "裂区", "小批序贯", "序贯实验", "资源受限贪心序贯", "台架档期约束", "CONSTRAINED_MIXTURE", "FRACTIONAL_FACTORIAL", "SPLIT_PLOT", "RESOURCE_CONSTRAINED_GREEDY_SEQUENTIAL", or advancing to Stage 5 in lubricant R&D.
---

# DOE Design (Stage 5)

Record an evidence-bound experiment design request at `EXPERIMENT_DESIGNED` for the Lubricant R&D Domain Pack.
This is an experiment design specification and handoff record, NOT an executed test run, measurement result, or statistical regression.

Authority schema: `../../schemas/experiment_design.schema.json` (or local `references/experiment_design.schema.json` in deployed bundle).

---

## 1. Input Specification, Supported Families & the Mixing/Factor Bridge

A single JSON input object providing the 5 upstream artifacts and the `experiment_design` request:

```json
{
  "project_artifact": "path/to/project.json",
  "challenge_artifact": "path/to/challenge.json",
  "failure_ctq_artifact": "path/to/failure_ctq.json",
  "test_method_artifact": "path/to/test_method.json",
  "design_space_artifact": "path/to/design_space.json",
  "experiment_design": {
    "experiment_design_id": "DOE-WGO-001",
    "family": "CONSTRAINED_MIXTURE",
    "target_count": 12,
    "mixture_total": {
      "value": 100.0,
      "unit": "wt%",
      "source": "FORMULATION-SPEC-001",
      "method_version": "v1.0",
      "material_batch": "BATCH-2026-01",
      "formula_version": "v1.0"
    },
    "factors": ["VAR-PAO-BASE", "VAR-ESTER-BASE", "VAR-ADD-PACK"],
    "evidence": [
      {
        "evidence_id": "EV-DOE-001",
        "statement": "Constrained mixture bounds span the viable viscosity and solubility window",
        "source": "Formulation Pre-study Tech Note 2026",
        "status": "OBSERVED"
      }
    ]
  }
}
```

One **optional** extra path may be supplied beside the five upstream artifacts:

```json
{ "bench_artifact": "path/to/bench.json" }
```

`bench_artifact` is the registered bench object (`bench.schema.json`) and it is read only on the
grease route (see §1.3). When it is absent, the design keeps the hand-filled
`resource_envelope.bench_slots` path it always had; nothing about the six oil routes changes.

### Supported families (aligned to what the Phase 4 engine can actually solve)

| `design.family` | Channel | Needs `mixture_total`? | Needs `resource_envelope`? | Referenced variables must resolve to |
|---|---|---|---|---|
| `MIXTURE`, `CONSTRAINED_MIXTURE` | mixture (`components`) | yes | **no** (forbidden) | `MIXTURE_CLOSED` |
| `FULL_FACTORIAL`, `FRACTIONAL_FACTORIAL`, `SPLIT_PLOT`, `BAYESIAN_SEQUENTIAL`, `RESOURCE_CONSTRAINED_GREEDY_SEQUENTIAL` | factor (`factors`) | **no** (forbidden) | **yes** | `INDEPENDENT` |
| `MIXTURE_PROCESS` | both | yes | **yes** | either |

Families outside this table (e.g. `RSM`, `TAGUCHI_ROBUST`) are rejected: either the schema enum does not offer them or the engine does not implement them yet.

### 1.1 The sequential family's honest name

The engine's sequential channel is **deterministic greedy selection from candidate lattice points**,
not model-driven sequential design: there is no Gaussian process and no posterior sampling. The old
label `BAYESIAN_SEQUENTIAL` promised more than the code does, so the family's honest name is
`RESOURCE_CONSTRAINED_GREEDY_SEQUENTIAL`.

- The honest name is the one to use. It is accepted by the input contract, the artifact contract and
  the engine, and the engine reports it back in `method` (`RESOURCE_CONSTRAINED_GREEDY_SEQUENTIAL_V1`).
- `BAYESIAN_SEQUENTIAL` keeps working as an **alias** and is the same family on the same channel. A
  request spelled with the alias produces exactly the envelope it produced before (same runs, same
  legacy `method` string), which is why pre-existing inputs are byte-identical.
- On the grease route the honest name is reported **whichever spelling was used**, because that route
  must never carry a label it cannot back.
- The algorithm is unchanged. Renaming changed a name, not a design.

### 1.2 Resource envelope (WP-04b)

```json
"resource_envelope": {
  "bench_slots": 2, "lot_capacity": 16, "cycle_days": 3.0,
  "cost_cap": 0.0, "external_test_lead_time": 0.0
}
```

`bench_slots` is the number of concurrent bench positions available for the **next** round; its conversion basis references `bench.availability_window` (WP-05) and is documented rather than enforced until that object exists. `lot_capacity` bounds how many lots the horizon can produce, `cycle_days` is one run's turnaround, and `cost_cap` / `external_test_lead_time` are declared resource inputs the engine carries but does not yet consume into the ranking (WP-05 bench coupling).

- `bench_slots < 1`, `lot_capacity < 1`, or `cycle_days <= 0` are **rejected** with a named reason.
- The engine then reports `resource_feasible`, `information_gain_per_slot`, and `recommended_next_runs[]`: at most `bench_slots` runs, each carrying the hypothesis it discriminates (`hypothesis_reference` / `effect_reference`) and a discriminative-power reason, plus `whole_plot_index` on split-plot designs so the next round can be executed grouped by whole plot.
- The sequential family draws a **deterministic, non-probabilistic** greedy batch from the candidate lattice, bounded by `bench_slots`. A recommendation for an effect that no run in the batch isolates carries `"run_index": null` plus the settings of the extra run needed at that effect's all-high corner.

### 1.3 Grease route (`PRECISION_GREASE_DEV`): small rounds, and the bench as a hard constraint

This section applies **only** when the validated `project_artifact.project_type` is
`PRECISION_GREASE_DEV`. Every other route — the six oil project types — keeps the behaviour described
above, unchanged.

**Default to a small sequential round, not one big DOE.** The bench is the bottleneck: about **2
positions per round** and about **30 days per round**. One big fixed design is therefore not feasible.
The plan records a single 20-point design as roughly **7 months** of bench time; at 2 positions per
round and 30 days per round the round arithmetic alone is 20 ÷ 2 = 10 rounds × 30 days ≈ 10 months,
and either way a project can afford about one such design a year. The grease route's default is a
small sequential round of **3–6 samples per round**, each round decided from the previous round's
result.

- A `RESOURCE_CONSTRAINED_GREEDY_SEQUENTIAL` request whose `run_plan.target_count` exceeds **6** is
  refused by name: that is the one-big-DOE pattern the route rejects.
- The window's floor is a *preference*, not a refusal. The registered bench may legitimately pull a
  round below 3 — a 2-position round is exactly the **paired round** the plan asks for, which buys
  more resolution than trying to measure sigma precisely.
- A one-shot design family (`FULL_FACTORIAL` and friends) stays expressible: a pure process-factor
  experiment must remain representable. Such a design is bounded by the bench capacity alone.

**The bench schedule is a hard constraint.** When `bench_artifact` is supplied:

- The round size and the design size must not exceed the bench's `available_bench_slots`.
- `available_bench_slots` is **DERIVED** by `bench-registration` (`floor(usable_days / cycle_days)`
  summed over `availability_window`) and asserted by its validator. This skill never recomputes it
  and never accepts a hand-set value in its place; it reads the derived figure.
- A hand-filled `resource_envelope.bench_slots` that **contradicts** the bench's derived capacity is
  refused: on this route the registered bench schedule is the authority. A matching declaration is
  the pre-existing hand-filled path and still works.
- A bench with `available_bench_slots = 0` cannot host any round and is refused.

The built artifact records which schedule bounded the round: `bench_reference` and
`available_bench_slots` (a copy of the derived value) are written **only** when a bench artifact was
supplied, so a pre-existing input builds exactly the artifact it built before. On the engine side the
same facts are reported under `parameters.grease_plan`, which is emitted only on the grease route.

### Bridge rule (single source of truth: `../../scripts/constraint_role.py`)

`design_space.variables[].constraint_role` decides where a variable goes. When the field is absent it is **derived** from `variable_type` — `FORMULATION_VARIABLE` → `MIXTURE_CLOSED`, `MATERIAL_FAMILY` / `PROCESS_VARIABLE` → `INDEPENDENT` — by the same shared module the Stage 4 formulation preflight uses. The variable's material-side `role` is passed through as well, so a variable over an in-situ reaction product (`role: REACTION_PRODUCT`, e.g. grease soap generated during saponification) resolves to `INDEPENDENT` instead of being rejected against its `FORMULATION_VARIABLE` type. Omitting `role` returns exactly the pre-extension result.

- `MIXTURE_CLOSED` → the engine's `components[]` (participates in the mixture closure and `mixture_total`).
- `INDEPENDENT` → the engine's `factors[]` (its own independent bounds, no closure).
- A variable placed on the wrong side of the declared family's channel is **rejected by name**.
- `factors[].role` (`WHOLE_PLOT` / `SUB_PLOT`) in the compute contract is a *different, orthogonal* axis: it is the split-plot whole/sub-plot role, not the mixing role. It is data-driven: an explicit per-factor `role` wins, otherwise the process-level `process_factor_role` (the compute mirror of `process.factor_role`) applies — never a hardcoded factor list.

### Feasibility Invariants
1. **Upstream Alignment (5 Artifacts)**: All 5 upstream artifacts must share `project_id`, `decision: "GO"`, and status `ACTIVE`.
2. **Method Role Requirement**: Linked `test_method_artifact` must be `QUALIFIED` and contain role `"D"` (Discrimination) or `"P"` (Prediction). A C-only method is strictly rejected with `HOLD`.
3. **Channel Feasibility**:
   - `family` must be one of the supported families above.
   - Mixture families: `sum(factor.lower_bounds) <= mixture_total <= sum(factor.upper_bounds)`; factors must reference valid `variable_id` entries in the design space.
   - Factor families: no `mixture_total`; every referenced variable must resolve to `INDEPENDENT`; a well-formed `resource_envelope` is required.
   - Every `variable_id` must exist in the design space, and a declared `constraint_role` must agree with the `variable_type`-derived role.
4. **Grease Route Only**: when `project_artifact.project_type` is `PRECISION_GREASE_DEV`, the round must
   respect the 3–6 window's top and the registered bench capacity (§1.3). No other route is affected.


---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/doe-design/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/doe-design/scripts/preflight_doe_design.py <input.json>
```
- Expected output on success: `READY: input can form one EXPERIMENT_DESIGNED record only` (exit code 0).
- If preflight fails: Output starts with `HOLD: ...` (exit code 1).

### Step 2: Build Deterministic Artifact
```bash
python skills/doe-design/scripts/build_experiment_design_artifact.py <input.json> <temporary-file.json>
```

### Step 3: Validate Artifact
```bash
python skills/doe-design/scripts/validate_experiment_design_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: experiment-design artifact conforms to the Stage 5 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` only after Step 3 passes. **Naming rule**: if `experiment_design.json` does not yet exist in the workspace root, commit this record as `experiment_design.json`; otherwise commit it as `experiment_design-<project_id>-<experiment_design_id>.json`. That is, the first record of this stage occupies the canonical name `experiment_design.json` (the stage-gate panel uses this exact name to mark the stage complete), and subsequent records of the same stage are appended as suffixed names carrying the record ID. After the commit, run `python scripts/check_artifact_naming.py <workspace_root>` and correct any `HOLD` before proceeding. The checker also enforces that `project.json`'s `stage` stays the constant `PROJECT_DEFINED` — it is NOT the project's current stage, and must not be advanced.
```bash
# 🔴 CHECKPOINT · STOP: Stage 5 stops here at EXPERIMENT_DESIGNED. Pass to Phase 4 compute engine or Stage 6 (experiment-import).
```

### Grease route (PRECISION_GREASE_DEV): the same four steps, one extra path

The workflow is identical; what changes is the request shape and the extra upstream path. Add
`"bench_artifact": "path/to/bench.json"` beside the five upstream paths and plan **one small round**:

```json
"design": { "family": "RESOURCE_CONSTRAINED_GREEDY_SEQUENTIAL", "rationale": "…", "effects_to_estimate": ["…"] },
"run_plan": { "target_count": 3, "replicate_count": 0, "center_point_count": 0,
              "randomized": true, "point_generation": "PHASE4_DETERMINISTIC_ENGINE" },
"resource_envelope": { "bench_slots": 3, "lot_capacity": 4, "cycle_days": 30, "cost_cap": 60000, "external_test_lead_time": 14 }
```

`target_count` is the round size (3–6) and `resource_envelope.bench_slots` must equal the bench
artifact's derived `available_bench_slots`. The built artifact then carries `project_type`,
`bench_reference` and `available_bench_slots` so the round's bound is auditable downstream. Passing the
engine request on, the engine reports `parameters.grease_plan` with the round size, the bench capacity
and whether the schedule came from the bench artifact or from the hand-filled envelope.

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: method does not have role D or P` | 评定方法仅有合规性 (C)，无区分或预测能力 | **STOP**。退回 Stage 3.5 重新评定具有区分度 (D) 的试验台架。 |
| `HOLD: mixture_total is infeasible` | 因子上下界之和无法覆盖目标总量 (如100 wt%) | **STOP**。检查各组分上下限范围，修复输入文件中的配比界限。 |
| `HOLD: unsupported design family` | 选择了未实现的算法族 | **STOP**。改用受支持家族（混料族 / 因子族 / MIXTURE_PROCESS）。 |
| `HOLD: <VAR> ... belongs in DOE components / DOE factors` | 变量错位：`MIXTURE_CLOSED` 变量放进了因子族，或 `INDEPENDENT` 变量放进了混料族 | **STOP**。按 `constraint_role` 将变量归位：参与混料闭合的进 `components`，独立因子进 `factors`。 |
| `HOLD: mixture_total must be absent for a factor-only family` | 因子族里多填了 `mixture_total` | **STOP**。因子设计无混料闭合，删除 `mixture_total`。 |
| `HOLD: resource_envelope is required for family …` | 因子/工艺族缺资源声明 | **STOP**。补 `resource_envelope`（至少给出 `bench_slots` 与 `lot_capacity` 的真实口径）。 |
| `HOLD: resource_envelope.bench_slots must be >= 1` | `bench_slots` 为 0 或负 | **STOP**。下一轮无台架位即不可排产；先确认可用台架位再提交。 |
| `HOLD: resource_envelope must be absent for a mixture family` | 混料族里多填了资源声明 | **STOP**。混料通道不消费资源包，删除该字段（资源约束属工艺/因子通道）。 |
| `HOLD: run_plan.target_count must not exceed 6 …` | 脂路线提交了一次性大 DOE（超出小批序贯窗口上限） | **STOP**。改为小批序贯轮次（3–6 样/轮）；一次 20 点设计在 2 台架位/轮下约需 7 个月台架时间，路线默认拒绝。 |
| `HOLD: … exceeds the bench's available positions …` | 设计规模超过台架可用位数（第 8 步放行判据） | **STOP**。缩小本轮设计规模，或先扩宽台架可用档期并重新登记 `bench.json`（`available_bench_slots` 为推导值，不得手填）。 |
| `HOLD: resource_envelope.bench_slots=… contradicts the supplied bench artifact's derived available_bench_slots=…` | 手填资源包络与 `bench.json` 推导出的可用台架位数不一致 | **STOP**。脂路线上以已登记台架档期为准；把手填值改为与推导值一致，或撤销 `bench_artifact` 回到纯手填路径。 |
| `HOLD: bench_artifact.available_bench_slots must be the integer derived by bench-registration` | 台架工件缺少（或被手改）推导位数 | **STOP**。用 `bench-registration` 重新生成台架工件，不要手填该字段。 |
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 错误 | 检查输入文件与 `../../schemas/experiment_design.schema.json`。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Simulated Run Points**: DO NOT inject synthetic experiment run tables or observed response points in Stage 5.
2. **NO Regression Modeling**: DO NOT build response surface models, ANOVA tables, or regression formulas here.
3. **NO C-only Bypass**: DO NOT allow test methods with only role `C` to authorize mixture experimentation.
4. **NO Dirty Overwrites**: DO NOT overwrite existing design artifacts with mismatched `project_id` or `experiment_design_id`.
5. **NO One-Shot Big DOE on the Grease Route**: DO NOT plan a single large fixed design for
   `PRECISION_GREASE_DEV`. The route's default is a small sequential round (3–6 samples per round)
   because the bench is the bottleneck (about 2 positions and 30 days per round). A pure
   process-factor design that legitimately needs more runs stays expressible, but it is bounded by the
   bench capacity.
6. **NO Hand-Set Bench Capacity**: DO NOT hand-set `available_bench_slots`, and DO NOT let a
   hand-filled `resource_envelope.bench_slots` override the registered bench. The derived capacity is
   the authority and a contradiction is refused, not reconciled.
7. **NO Capability Overclaim in the Method Name**: DO NOT label the sequential channel as a
   model-driven (Bayesian) design. The engine performs deterministic greedy selection from candidate
   lattice points and reports `RESOURCE_CONSTRAINED_GREEDY_SEQUENTIAL_V1`. The legacy alias still runs
   and still reports its legacy string, but the honest name is the one to use.

