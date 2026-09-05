---
name: optimization
description: Record one evidence-bound optimization request at OPTIMIZED; preflight verifies 8 upstream stage artifacts through MODEL_BUILT, objective response links, and supported optimization methods (PARETO, DESIRABILITY, NON_INFERIORITY). Use when user mentions "optimization", "多目标优化", "帕累托前沿", "满意度函数", "DESIRABILITY", "PARETO", "NON_INFERIORITY", or advancing to Stage 8 in lubricant R&D.
---

# Optimization (Stage 8)

Record an evidence-bound optimization request at `OPTIMIZED` for the Lubricant R&D Domain Pack.
This is an optimization problem specification and handoff contract, NOT a simulated Pareto solution or recipe recommendation.

Authority schema: `../../schemas/optimization.schema.json` (or local `references/optimization.schema.json` in deployed bundle).

---

## 1. Input Specification & Supported Methods

A single JSON input object providing the 8 upstream artifacts through `MODEL_BUILT` and the `optimization` request:

```json
{
  "project_artifact": "path/to/project.json",
  "challenge_artifact": "path/to/challenge.json",
  "failure_ctq_artifact": "path/to/failure_ctq.json",
  "test_method_artifact": "path/to/test_method.json",
  "design_space_artifact": "path/to/design_space.json",
  "experiment_design_artifact": "path/to/experiment_design.json",
  "experiment_artifact": "path/to/experiment.json",
  "model_artifact": "path/to/model.json",
  "optimization": {
    "optimization_id": "OPT-WGO-001",
    "objective_type": "MULTI_OBJECTIVE",
    "objectives": [
      {
        "response_reference": "CTQ-FZG-GF-STAGE",
        "direction": "MAXIMIZE",
        "weight": 1.0
      }
    ],
    "methods": ["PARETO", "DESIRABILITY"],
    "evidence": [
      {
        "evidence_id": "EV-OPT-001",
        "statement": "Optimization trade-off space defined across anti-micropitting stage and viscosity limits",
        "source": "Optimization Strategy Protocol 2026",
        "status": "OBSERVED"
      }
    ]
  }
}
```

### Supported Method Contract
- **Supported Methods**: `"PARETO"`, `"DESIRABILITY"`, and `"NON_INFERIORITY"` ONLY.
- **Unsupported Methods**: Bayesian Optimization is deliberately unsupported in this phase; requests with unsupported methods are strictly rejected with `HOLD`.
- **Response Continuity**: Every response in `objectives` must exist in `model_artifact.response_references`.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/optimization/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/optimization/scripts/preflight_optimization.py <input.json>
```
- Expected output on success: `READY: input can form one OPTIMIZED record only` (exit code 0).
- If preflight fails: Output starts with `HOLD: ...` (exit code 1).

### Step 2: Build Deterministic Artifact
```bash
python skills/optimization/scripts/build_optimization_artifact.py <input.json> <temporary-file.json>
```

### Step 3: Validate Artifact
```bash
python skills/optimization/scripts/validate_optimization_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: optimization artifact conforms to the Stage 8 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` only after Step 3 passes.
```bash
# 🔴 CHECKPOINT · STOP: Stage 8 stops here at OPTIMIZED. Pass to Phase 4 compute engine or Stage 9 (gate-review).
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: unsupported optimization method` | 包含非 PARETO/DESIRABILITY/NON_INFERIORITY 算法 | **STOP**。将优化算法调整为支持的三大方法之一。 |
| `HOLD: objective response not in model` | 优化目标未在统计模型中建立响应面 | **STOP**。退回 Stage 7 将该 CTQ 纳入响应面建模范围。 |
| `HOLD: upstream artifact stage is not MODEL_BUILT` | 流程尚未完成统计回归建模 | **STOP**。先运行 `statistical-analysis` 完成模型建构。 |
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 错误 | 检查输入文件与 `../../schemas/optimization.schema.json`。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Handcrafted Pareto Fronts**: DO NOT fabricate Pareto optimal points or solve trade-offs without the Phase 4 engine.
2. **NO Recipe Freezing Here**: DO NOT declare design freeze or final formulation approval in Stage 8.
3. **NO Unsupported Algorithms**: DO NOT bypass algorithm checks with unverified Bayesian or heuristic methods.
4. **NO Dirty Overwrites**: DO NOT overwrite existing optimization artifacts with mismatched `project_id` or `optimization_id`.

