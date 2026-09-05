---
name: duty-challenge-analysis
description: Convert one validated lubricant duty profile into one traceable Challenge Map member at CHALLENGES_DEFINED; preflight verifies DUTY_DEFINED stage artifact and challenge evaluation dimensions before building the artifact. Use when user mentions "duty-challenge-analysis", "工况挑战分析", "挑战图谱", "Challenge Map", "工况挑战", or advancing to Stage 2 in lubricant R&D.
---

# Duty Challenge Analysis (Stage 2)

Convert a validated lubricant duty profile into exactly one traceable Challenge Map member at `CHALLENGES_DEFINED` for the Lubricant R&D Domain Pack.
This is a tribological challenge analysis record, NOT a failure mechanism, CTQ, test plan, or formulation recipe.

Authority schema: `../../schemas/challenge.schema.json` (or local `references/challenge.schema.json` in deployed bundle).

---

## 1. Input Specification

A single JSON input object providing `duty_artifact`, `challenge`, and `challenge_evidence`:

```json
{
  "duty_artifact": "path/to/duty.json",
  "challenge": {
    "duty_reference": "DUTY-WGO-001",
    "challenge_id": "CHG-MICROPITTING-001",
    "category": "MECHANICAL_STRESS",
    "description": "High Hertzian contact pressure under low entrainment speed causing boundary film rupture",
    "severity": "HIGH",
    "exposure": "CONTINUOUS",
    "lubricant_sensitivity": "CRITICAL",
    "evidence_gap": "NONE",
    "priority": "P1"
  },
  "challenge_evidence": [
    {
      "evidence_id": "EV-CHG-001",
      "statement": "Hertzian stress > 1.6 GPa promotes micropitting fatigue on planetary gears",
      "source": "Gearbox Teardown Failure Analysis Report 2025",
      "status": "OBSERVED"
    }
  ]
}
```

### Invariants
- Upstream validity: `duty_artifact` must be schema-valid with `stage: "DUTY_DEFINED"` and `decision: "GO"`.
- Explicit evaluations: `severity`, `exposure`, `lubricant_sensitivity`, and `priority` must be explicitly provided using schema enums. Never infer grades from general category.
- Evidence traceability: Each item in `challenge_evidence` requires `evidence_id`, `statement`, `source`, and `status: "OBSERVED"`.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/duty-challenge-analysis/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/duty-challenge-analysis/scripts/preflight_duty_challenge.py <input.json>
```
- Expected output on success: `READY: input can form one CHALLENGES_DEFINED record only` (exit code 0).
- If preflight fails: Output starts with `HOLD: ...` (exit code 1).

### Step 2: Build Deterministic Artifact
Create temporary candidate JSON with `stage: "CHALLENGES_DEFINED"`, retaining the 7 standard decision fields (`decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`, `decision: "GO"`, `next_action: "Define failure and CTQ relationships."`).

### Step 3: Validate Artifact
```bash
python skills/duty-challenge-analysis/scripts/validate_duty_challenge_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: challenge artifact conforms to the Stage 2 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` (defaults to `challenge-<project_id>-<challenge_id>.json`) only after Step 3 passes.
```bash
# 🔴 CHECKPOINT · STOP: Stage 2 stops here at CHALLENGES_DEFINED. Route to Stage 3 (failure-ctq-analysis).
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: duty_artifact is missing or decision is not GO` | 上游工况未定义或未通过门禁 | **STOP**。退回 Stage 1（`duty-definition`）完成工况定义并取得 GO。 |
| `HOLD: missing challenge field [severity/exposure/...]` | 挑战评估维度缺失 | **STOP**。要求用户提供完整的严重度与敏感度评估，不猜测等级。 |
| `HOLD: challenge_evidence lacks OBSERVED status` | 挑战依据缺少真实观测凭据 | **STOP**。要求补足现场拆解失效记录或技术文献来源。 |
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 错误 | 检查输入文件与 `../../schemas/challenge.schema.json`。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Forward Mapping**: DO NOT map into specific Failure CTQ metrics, test standards, or additive packages in Stage 2.
2. **NO Synthetic Grading**: DO NOT automatically grade severity or sensitivity without input statements.
3. **NO Premature Solutions**: DO NOT propose base oil viscosity or additive chemistry here.
4. **NO Dirty Overwrites**: DO NOT overwrite existing challenge files with mismatched `project_id` or `challenge_id`.

