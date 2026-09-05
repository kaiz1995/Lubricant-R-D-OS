---
name: formulation-design
description: Define one evidence-bound, testable design space at DESIGN_SPACE_DEFINED for lubricant formulation; preflight verifies upstream stage artifacts (project, challenge, failure CTQ, qualified test method) and input bounds before building the artifact. Use when user mentions "formulation-design", "配方设计", "设计空间", "design space", "定义设计空间", "ISO VG", or advancing lubricant R&D to Stage 4.
---

# Formulation Design (Stage 4)

Define an evidence-bound, testable design space record at `DESIGN_SPACE_DEFINED` for the Lubricant R&D Domain Pack.
Authority schema: `../../schemas/design_space.schema.json` (or local `references/design_space.schema.json` in deployed bundle).

---

## 1. Input Specification

Input must be a single JSON object containing exact upstream artifact paths and the target `design_space` specification:

```json
{
  "project_artifact": "path/to/project_defined.json",
  "challenge_artifact": "path/to/challenges_defined.json",
  "failure_ctq_artifact": "path/to/failure_ctq_defined.json",
  "test_method_artifact": "path/to/test_methods_qualified.json",
  "design_space": {
    "design_space_id": "DS-WGO-001",
    "scope": "ISO VG 320 wind turbine gear oil formulation candidate window",
    "variables": [
      {
        "variable_id": "VAR-PAO-BASE",
        "variable_type": "MATERIAL_FAMILY",
        "lower_bound": {
          "value": 50.0,
          "unit": "wt%",
          "source": "SPEC-DOC-001",
          "method_version": "v1.0",
          "material_batch": "BATCH-202608-01",
          "formula_version": "v0.1"
        },
        "upper_bound": {
          "value": 85.0,
          "unit": "wt%",
          "source": "SPEC-DOC-001",
          "method_version": "v1.0",
          "material_batch": "BATCH-202608-01",
          "formula_version": "v0.1"
        },
        "constraint_rationale": "Viscosity blending balance requirement"
      }
    ],
    "ctq_references": ["CTQ-FZG-MICROPITTING"],
    "qualified_test_method_references": ["TM-FZG-001"],
    "constraints": ["sum(variables.wt%) == 100.0"],
    "evidence": [
      {
        "evidence_id": "EV-DS-001",
        "status": "VERIFIED",
        "scope": "PHYSICAL",
        "rationale": "Base oil and additive boundaries verified against bench data."
      }
    ]
  }
}
```

### Field Invariants
- Upstream alignment: All 4 upstream artifacts must share the same `project_id`, `decision: "GO"`, and status `ACTIVE`.
- Chain of custody: `failure_ctq_artifact.challenge_reference == challenge_artifact.challenge_id`, and `test_method_artifact.target_failure_reference == failure_ctq_artifact.failure_id`.
- Test method qualification: `test_method_artifact.qualification_status` must be `"QUALIFIED"`.
- Variable integrity: Each variable requires complete measurement metadata (`value`, `unit`, `source`, `method_version`, `material_batch`, `formula_version`).
- Bound ordering: `lower_bound.value <= upper_bound.value` with identical `unit`. Non-finite values (`NaN`, `Infinity`) are rejected.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/formulation-design/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
Always run preflight before creating or modifying any artifact:
```bash
python skills/formulation-design/scripts/preflight_formulation_design.py <input.json>
```
- Expected output on success: `READY: input can form one DESIGN_SPACE_DEFINED record only` (exit code 0).
- If preflight fails: Output starts with `HOLD: missing or invalid: ...; no artifact generated` (exit code 1). See Section 3 for error recovery.

### Step 2: Build Deterministic Artifact
Run the builder only after Step 1 passes:
```bash
python skills/formulation-design/scripts/build_design_space_artifact.py <input.json> <temporary-file.json>
```
The builder generates canonical decision fields (`decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`, `decision`, `next_action`).

### Step 3: Validate Artifact
Validate schema and policy conformance:
```bash
python skills/formulation-design/scripts/validate_design_space_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: deterministic design-space artifact conforms to the Stage 4 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3 returns `PASS`.
```bash
# 🔴 CHECKPOINT · STOP: Stage 4 stops here at DESIGN_SPACE_DEFINED.
```

---

## 3. Failure Modes & Fallback Recovery (Fail-Closed)

When any check fails, strictly follow the fallback table. Do NOT retry blindly.

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: missing or invalid: test_method_artifact must have decision GO` | 上游测试方法评定为 HOLD 或未通过 | **STOP**。不得创建设计空间。退回 Stage 3（`test-method-qualification`）要求补齐物理标定证据。 |
| `HOLD: missing or invalid: lower_bound > upper_bound` | 变量上下界逻辑倒置 | **STOP**。输出报错变量名与数值，要求用户校验物性限值并修复 input JSON，不猜测默认值。 |
| `HOLD: missing or invalid: project_id values must match` | 跨项目混用工件 | **STOP**。检查 4 个输入工件路径，确认归属于同一 project_id。 |
| `HOLD: missing or invalid: design_space.evidence contains GAP` | 证据链存在未解缺口 | **STOP**。保持 `decision: HOLD`，生成 gap 诊断报告，等待实验补足后再重试。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法损坏 | 检查 `../../schemas/` 与输入文件 JSON 格式，修复语法错误。 |

---

## 4. Red Lines & Blacklist (Strict Prohibition)

This skill operates strictly under Stage 4 boundaries. The following actions are prohibited:

1. **NO Forward Inference**: DO NOT invent, hallucinate, or infer missing bounds, additive ratios, formula percentages, material batches, or sources.
2. **NO Cross-Stage Mutation**: DO NOT generate DOE designs (Stage 5), blend recipes, candidate ratios, experiment matrices, or cost calculations in this skill.
3. **NO Bypass of Preflight**: DO NOT create or touch `<output.json>` directly without running `preflight_formulation_design.py` first.
4. **NO Dirty Overwrites**: DO NOT overwrite existing target artifacts if validation fails or yields non-zero exit codes.
5. **NO Soft Guidance Words**: Forbidden ambiguous words: "灵活调整", "视情况而定", "酌情设置", "可以考虑". All bounds and parameters must be concrete numbers and verifiable metadata.

