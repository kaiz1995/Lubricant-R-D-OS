---
name: statistical-analysis
description: Record one evidence-bound statistical-analysis request at MODEL_BUILT; preflight verifies 7 upstream artifacts through EXPERIMENT_RUNNING and response CTQ method chains before building the artifact. Use when user mentions "statistical-analysis", "统计分析", "显著性分析", "响应面拟合", "ANOVA", "回归建模", or advancing to Stage 7 in lubricant R&D.
---

# Statistical Analysis (Stage 7)

Record an evidence-bound statistical analysis request at `MODEL_BUILT` for the Lubricant R&D Domain Pack.
This is an analysis request and handoff contract, NOT a simulated regression result or optimization claim.

Authority schema: `../../schemas/model.schema.json` (or local `references/model.schema.json` in deployed bundle).

---

## 1. Input Specification & Response Chain Invariants

A single JSON input object providing the 7 upstream artifacts and the `analysis` request:

```json
{
  "project_artifact": "path/to/project.json",
  "challenge_artifact": "path/to/challenge.json",
  "failure_ctq_artifact": "path/to/failure_ctq.json",
  "test_method_artifact": "path/to/test_method.json",
  "design_space_artifact": "path/to/design_space.json",
  "experiment_design_artifact": "path/to/experiment_design.json",
  "experiment_artifact": "path/to/experiment.json",
  "analysis": {
    "model_id": "MODEL-WGO-001",
    "requested_analyses": ["ANOVA", "MIXTURE_RSM", "RESIDUAL_DIAGNOSTICS"],
    "response_references": ["CTQ-FZG-GF-STAGE"],
    "evidence": [
      {
        "evidence_id": "EV-STAT-001",
        "statement": "Response data verified for variance stability and degree of freedom sufficiency",
        "source": "Statistical Pre-flight Evaluation Note",
        "status": "OBSERVED"
      }
    ]
  }
}
```

### Invariants
1. **Full Chain Traceability (7 Artifacts)**: All 7 artifacts through `EXPERIMENT_RUNNING` must be present, schema-valid, with `decision: "GO"`.
2. **Response Chain Continuity**: Every `response_references` item must exist in:
   - Failure CTQ record (`ctqs`).
   - Design space (`ctq_references`).
   - Observed experiment measurements (`measured_responses`).
   - Linked qualified test method.
3. **Engine Boundary**: ANOVA, Scheffé polynomial regression, R² fitting, p-values, and lack-of-fit belong exclusively to the Phase 4 deterministic engine (`run_compute.py`).

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/statistical-analysis/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/statistical-analysis/scripts/preflight_statistical_analysis.py <input.json>
```
- Expected output on success: `READY: input can form one MODEL_BUILT record only` (exit code 0).
- If preflight fails: Output starts with `HOLD: ...` (exit code 1).

### Step 2: Build Deterministic Artifact
```bash
python skills/statistical-analysis/scripts/build_model_artifact.py <input.json> <temporary-file.json>
```

### Step 3: Validate Artifact
```bash
python skills/statistical-analysis/scripts/validate_model_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: model artifact conforms to the Stage 7 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` only after Step 3 passes.
```bash
# 🔴 CHECKPOINT · STOP: Stage 7 stops here at MODEL_BUILT. Pass to Phase 4 compute engine or Stage 8 (optimization).
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: response CTQ missing in observed experiment` | 实验数据未测定对应 CTQ 响应 | **STOP**。退回 Stage 6 补充该 CTQ 的实测台架记录。 |
| `HOLD: upstream artifact stage is not EXPERIMENT_RUNNING` | 流程尚未完成物理实验接入 | **STOP**。按流程先完成实验数据导入。 |
| `HOLD: evidence contains GAP` | 统计分析先决条件未满足 | **STOP**。审查样本量与自由度，补足前置条件。 |
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 错误 | 检查输入文件与 `../../schemas/model.schema.json`。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO LLM Regression Guessing**: DO NOT invent regression coefficients, F-statistics, or p-values.
2. **NO Optimization Skipping**: DO NOT jump directly to solving optimal formulations in Stage 7.
3. **NO Unlinked Responses**: DO NOT analyze response metrics that lack complete upstream CTQ chains.
4. **NO Dirty Overwrites**: DO NOT overwrite existing model artifacts with mismatched `project_id` or `model_id`.

