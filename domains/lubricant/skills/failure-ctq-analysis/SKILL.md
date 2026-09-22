---
name: failure-ctq-analysis
description: Convert one validated lubricant Challenge Map member into one evidence-bound Failure/CTQ record at FAILURE_CTQ_DEFINED; preflight verifies upstream artifacts, hypothesis formatting, lubricant contribution uncertainty, and dual CTQ limits. Use when user mentions "failure-ctq-analysis", "失效CTQ分析", "失效模式", "关键质量特性", "CTQ定义", or advancing to Stage 3 in lubricant R&D.
---

# Failure CTQ Analysis (Stage 3)

Convert a validated lubricant Challenge Map member into an evidence-bound Failure/CTQ record at `FAILURE_CTQ_DEFINED` for the Lubricant R&D Domain Pack.
This is a diagnostic hypothesis and CTQ metric specification, NOT a confirmed forensic conclusion or test method qualification.

Authority schema: `../../schemas/failure_ctq.schema.json` (or local `references/failure_ctq.schema.json` in deployed bundle).

---

## 1. Input Specification & Scientific Invariants

A single JSON input object providing `project_artifact`, `challenge_artifact`, and the `failure_ctq` data:

```json
{
  "project_artifact": "path/to/project.json",
  "challenge_artifact": "path/to/challenge.json",
  "failure_ctq": {
    "failure_id": "FAIL-MICROPITTING-001",
    "challenge_reference": "CHG-MICROPITTING-001",
    "failure_mode": "Gear tooth surface micropitting fatigue",
    "root_cause_hypotheses": [
      "Hypothesis: Asperity contact fatigue accelerated by low EHL film thickness ratio lambda < 1.0",
      "Hypothesis: Chemical wear from aggressive EP additive activation under high localized flash temperature"
    ],
    "lubricant_contribution": "POSSIBLE - Pending bench verification of anti-micropitting chemistry",
    "ctqs": [
      {
        "ctq_id": "CTQ-FZG-GF-STAGE",
        "classification": "CTQ",
        "observable": "FZG micropitting test failure load stage",
        "test_references": ["TEST-FZG-C-GF"],
        "specification_limit": {
          "value": 10.0,
          "comparator": ">=",
          "unit": "stage"
        },
        "engineering_risk_limit": {
          "value": 11.0,
          "comparator": ">=",
          "unit": "stage"
        },
        "evidence_required": "Standardized bench test report from accredited lab"
      }
    ],
    "test_chain": ["TM-FZG-001"],
    "evidence": [
      {
        "evidence_id": "EV-FCTQ-001",
        "statement": "Field gearbox inspections show micropitting initiating on dedicated planetary teeth",
        "source": "Vestas Field Inspection Bulletin 2025",
        "status": "OBSERVED"
      }
    ]
  }
}
```

### Invariants
1. **Hypothesis Prefix**: Every item in `root_cause_hypotheses` MUST start with `"Hypothesis: "` or `"假设: "`. Never state unverified causes as confirmed facts.
2. **Contribution Uncertainty**: `lubricant_contribution` must explicitly remain open or pending verification (e.g. `"POSSIBLE"`, `"PROBABLE_PENDING_VERIFICATION"`).
3. **Dual Limits Division**: Every CTQ must strictly separate:
   - `specification_limit`: Regulatory/customer compliance threshold.
   - `engineering_risk_limit`: Internal engineering safety margin. Never conflate them.
4. **Upstream Alignment**: `project_artifact` must be `PROJECT_DEFINED`, `challenge_artifact` must be `CHALLENGES_DEFINED`, and IDs must match.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/failure-ctq-analysis/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/failure-ctq-analysis/scripts/preflight_failure_ctq.py <input.json>
```
- Expected output on success: `READY: input can form one FAILURE_CTQ_DEFINED record only` (exit code 0).
- If preflight fails: Output starts with `HOLD: ...` (exit code 1).

### Step 2: Build Deterministic Artifact
Create candidate JSON at `stage: "FAILURE_CTQ_DEFINED"`, retaining the 7 decision fields (`decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`, `decision: "GO"`, `next_action: "Qualify the proposed test method."`).

### Step 3: Validate Artifact
```bash
python skills/failure-ctq-analysis/scripts/validate_failure_ctq_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: failure_ctq artifact conforms to the Stage 3 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` only after Step 3 passes.
```bash
# 🔴 CHECKPOINT · STOP: Stage 3 stops here at FAILURE_CTQ_DEFINED. Route to Stage 3.5 (test-method-qualification).
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: root_cause item does not start with Hypothesis:/假设:` | 根本原因被断言为已确诊事实 | **STOP**。要求用户修改表述，必须以 `Hypothesis:` 前缀表达未证伪的科学假设。 |
| `HOLD: specification_limit and engineering_risk_limit conflated` | 限值混为一谈或缺失其一 | **STOP**。要求分别提供工程风险控制线与客户规格底线。 |
| `HOLD: challenge_artifact must have decision GO` | 上游挑战未通过阶段门禁 | **STOP**。退回 Stage 2 补足工况挑战依据。 |
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 错误 | 检查输入文件语法及 Schema 路径。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Confirmed Root Cause**: DO NOT declare lubricant failure causes as definite conclusions without completed bench tests.
2. **NO Limit Conflation**: DO NOT use a single limit to serve both specification and engineering risk boundaries.
3. **NO Premature Formulation**: DO NOT suggest additive treat rates or chemical components in Stage 3.
4. **NO Dirty Overwrites**: DO NOT overwrite existing failure records with mismatched `project_id` or `failure_id`.

