---
name: doe-design
description: Record one evidence-bound experiment-design request at EXPERIMENT_DESIGNED; preflight verifies 5 upstream stage artifacts, D/P qualified methods, the mixture↔factor bridge (constraint_role routes variables to components or factors), and bound constraints before building the artifact. Use when user mentions "doe-design", "实验设计", "混料设计", "mixture DOE", "正交实验", "因子设计", "裂区", "CONSTRAINED_MIXTURE", "FRACTIONAL_FACTORIAL", "SPLIT_PLOT", or advancing to Stage 5 in lubricant R&D.
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

### Supported families (aligned to what the Phase 4 engine can actually solve)

| `design.family` | Channel | Needs `mixture_total`? | Needs `resource_envelope`? | Referenced variables must resolve to |
|---|---|---|---|---|
| `MIXTURE`, `CONSTRAINED_MIXTURE` | mixture (`components`) | yes | **no** (forbidden) | `MIXTURE_CLOSED` |
| `FULL_FACTORIAL`, `FRACTIONAL_FACTORIAL`, `SPLIT_PLOT`, `BAYESIAN_SEQUENTIAL` | factor (`factors`) | **no** (forbidden) | **yes** | `INDEPENDENT` |
| `MIXTURE_PROCESS` | both | yes | **yes** | either |

Families outside this table (e.g. `RSM`, `TAGUCHI_ROBUST`) are rejected: either the schema enum does not offer them or the engine does not implement them yet.

### Resource envelope (WP-04b)

```json
"resource_envelope": {
  "bench_slots": 2, "lot_capacity": 16, "cycle_days": 3.0,
  "cost_cap": 0.0, "external_test_lead_time": 0.0
}
```

`bench_slots` is the number of concurrent bench positions available for the **next** round; its conversion basis references `bench.availability_window` (WP-05) and is documented rather than enforced until that object exists. `lot_capacity` bounds how many lots the horizon can produce, `cycle_days` is one run's turnaround, and `cost_cap` / `external_test_lead_time` are declared resource inputs the engine carries but does not yet consume into the ranking (WP-05 bench coupling).

- `bench_slots < 1`, `lot_capacity < 1`, or `cycle_days <= 0` are **rejected** with a named reason.
- The engine then reports `resource_feasible`, `information_gain_per_slot`, and `recommended_next_runs[]`: at most `bench_slots` runs, each carrying the hypothesis it discriminates (`hypothesis_reference` / `effect_reference`) and a discriminative-power reason, plus `whole_plot_index` on split-plot designs so the next round can be executed grouped by whole plot.
- `BAYESIAN_SEQUENTIAL` is the resource-constrained sequential family: the engine draws a **deterministic, non-probabilistic** greedy batch from the candidate lattice, bounded by `bench_slots`. A recommendation for an effect that no run in the batch isolates carries `"run_index": null` plus the settings of the extra run needed at that effect's all-high corner.

### Bridge rule (single source of truth: `../../scripts/constraint_role.py`)

`design_space.variables[].constraint_role` decides where a variable goes. When the field is absent it is **derived** from `variable_type` — `FORMULATION_VARIABLE` → `MIXTURE_CLOSED`, `MATERIAL_FAMILY` / `PROCESS_VARIABLE` → `INDEPENDENT` — by the same shared module the Stage 4 formulation preflight uses.

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
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 错误 | 检查输入文件与 `../../schemas/experiment_design.schema.json`。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Simulated Run Points**: DO NOT inject synthetic experiment run tables or observed response points in Stage 5.
2. **NO Regression Modeling**: DO NOT build response surface models, ANOVA tables, or regression formulas here.
3. **NO C-only Bypass**: DO NOT allow test methods with only role `C` to authorize mixture experimentation.
4. **NO Dirty Overwrites**: DO NOT overwrite existing design artifacts with mismatched `project_id` or `experiment_design_id`.

