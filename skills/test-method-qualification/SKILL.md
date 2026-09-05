---
name: test-method-qualification
description: Qualify one evidence-bound lubricant test method at TEST_METHODS_QUALIFIED; preflight verifies upstream artifacts, method provenance, role metrics (C/D/P), and physical evidence scope before building the artifact. Use when user mentions "test-method-qualification", "测试方法评定", "台架评定", "方法标定", "区分度验证", "FZG评定", or advancing to Stage 3.5 in lubricant R&D.
---

# Test Method Qualification (Stage 3.5)

Qualify one evidence-bound lubricant test method at `TEST_METHODS_QUALIFIED` for the Lubricant R&D Domain Pack.
This is a method sensitivity and mechanism relevance qualification record, NOT a formulation design or downstream result.

Authority schema: `../../schemas/test_method.schema.json` (or local `references/test_method.schema.json` in deployed bundle).

---

## 1. Input Specification & Role Governance

A single JSON input object providing upstream artifacts, `evidence_scope`, and `test_method`:

```json
{
  "project_artifact": "path/to/project.json",
  "challenge_artifact": "path/to/challenge.json",
  "failure_ctq_artifact": "path/to/failure_ctq.json",
  "evidence_scope": "PHYSICAL",
  "test_method": {
    "method_id": "TM-FZG-001",
    "method_name": "FZG Micropitting Test Method C-GF/8.3/90",
    "standard": "FVA 54/7",
    "challenge_reference": "CHG-MICROPITTING-001",
    "target_failure_reference": "FAIL-MICROPITTING-001",
    "roles": ["D", "P"],
    "metrics": {
      "discrimination": "Distinguishes baseline from anti-micropitting chemistry at delta load stage >= 2",
      "mechanism_relevance": "Reproduces elastohydrodynamic boundary wear under controlled speed and temperature",
      "field_relevance": "Correlates with Vestas field gearbox micropitting incidence"
    },
    "qualification_status": "QUALIFIED",
    "evidence_pointers": ["EV-TM-BENCH-001"]
  },
  "evidence": [
    {
      "evidence_id": "EV-TM-BENCH-001",
      "statement": "Round-robin bench repeatability confirmed with standard reference fluids",
      "source": "Independent Lab Certification Lab-2025-09",
      "status": "OBSERVED"
    }
  ]
}
```

### Invariants & Role Rules
1. **Method Roles (C / D / P)**:
   - `C` (Compliance): Standard compliance check.
   - `D` (Discrimination): Requires explicit `discrimination` metric demonstrating sensitivity between formulations.
   - `P` (Prediction): Requires `mechanism_relevance` PLUS `field_relevance` or `benchmark_ranking`.
2. **Physical Scope Requirement**:
   - `QUALIFIED` status strictly requires `evidence_scope: "PHYSICAL"` and `status: "OBSERVED"` evidence.
   - `evidence_scope: "SYNTHETIC"` can ONLY record `PENDING` or `NOT_QUALIFIED` with `decision: "HOLD"`. Synthetic data cannot authorize stage progression.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/test-method-qualification/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/test-method-qualification/scripts/preflight_test_method.py <input.json>
```
- Expected output on success: `READY: input can form one TEST_METHODS_QUALIFIED record only` (exit code 0).
- If preflight fails: Output starts with `HOLD: ...` (exit code 1).

### Step 2: Build Deterministic Artifact
```bash
python skills/test-method-qualification/scripts/build_test_method_artifact.py <input.json> <temporary-file.json>
```

### Step 3: Validate Artifact
```bash
python skills/test-method-qualification/scripts/validate_test_method_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: deterministic test-method artifact conforms to the Stage 3.5 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` only after Step 3 passes.
```bash
# 🔴 CHECKPOINT · STOP: Stage 3.5 stops here at TEST_METHODS_QUALIFIED. Route to Stage 4 (formulation-design).
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: SYNTHETIC evidence cannot have status QUALIFIED` | 尝试用模拟/合成数据通过方法评定 | **STOP**。将 qualification_status 调整为 PENDING/NOT_QUALIFIED，等待物理实测报告。 |
| `HOLD: Role D requires discrimination metric` | 缺少区分度灵敏度量化描述 | **STOP**。要求用户提供标油与试验油的区分台阶数据。 |
| `HOLD: failure_ctq_artifact must have decision GO` | 上游失效分析未通过 | **STOP**。退回 Stage 3 补齐失效 CTQ 依据。 |
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 错误 | 检查输入文件与 `../../schemas/test_method.schema.json`。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Synthetic Promotion**: NEVER promote synthetic bench models to `QUALIFIED` status.
2. **NO Formulation Generation**: DO NOT draft recipes, candidate treat rates, or design space boundaries here.
3. **NO Role Metric Omission**: DO NOT assign `D` or `P` roles without the corresponding mechanism/discrimination metrics.
4. **NO Dirty Overwrites**: DO NOT overwrite existing test method files with mismatched `project_id` or `method_id`.

