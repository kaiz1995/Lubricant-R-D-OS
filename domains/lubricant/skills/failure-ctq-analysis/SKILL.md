---
name: failure-ctq-analysis
description: Convert one validated lubricant Challenge Map member into one evidence-bound Failure/CTQ record at FAILURE_CTQ_DEFINED; preflight verifies upstream artifacts, hypothesis formatting, lubricant contribution uncertainty, and dual CTQ limits. Use when user mentions "failure-ctq-analysis", "失效CTQ分析", "失效机理与判据", "三层判据链", "失效模式", "关键质量特性", "CTQ定义", or advancing to Stage 3 in lubricant R&D.
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

## 1A. Route-Gated Policy: The Three-Layer Criteria Chain and the Diagnosis Chain

`schemas/failure_ctq.schema.json` is a shared contract: `criteria_layer` was added as an
OPTIONAL CTQ property, never to `required`. The grease-route enforcement lives in the policy
layer (`scripts/failure_ctq_policy.py`), gated on the project type.

### The three-layer criteria chain (grease route)
Every CTQ of a `PRECISION_GREASE_DEV` record must declare which layer of the criteria chain
it belongs to. `criteria_layer` ∈ {`SCREENING`, `BENCH`, `MACHINE`}:

| Layer | Used at | Example |
|---|---|---|
| `SCREENING` | The physicochemical screening step | Worked penetration change, oil separation, evaporation loss |
| `BENCH` | The bench step | SRV friction/wear, FZG stage |
| `MACHINE` | The whole-machine acceptance step | Start-up torque, backlash (回差), temperature rise, life |

A CTQ without a layer is rejected:
`HOLD: ... failure_ctq.ctqs[0].criteria_layer is required for PRECISION_GREASE_DEV: every CTQ
must declare which layer of the three-layer criteria chain (SCREENING, BENCH, MACHINE) it
belongs to`.

### The diagnosis chain (no shortcuts)
The record must hold all three links in order: **Failure Diagnosis → Root-Cause Hypothesis →
Lubricant Contribution**. Jumping from an observed symptom ("bearing wear") straight to a
lubricant cause ("insufficient anti-wear additive") is rejected — three ways:

1. `failure_diagnosis` empty: the diagnosis step was skipped.
2. `failure_diagnosis` a verbatim restatement of `failure_mode` / `mechanism`: the step was
   not written, only copied.
3. `failure_diagnosis` naming a lubricant cause (an additive, a base-oil property, a thickener
   quantity). The lubricant linkage belongs one link later, in `root_cause_hypotheses` →
   `lubricant_contribution`; a diagnosis that IS the lubricant cause leaves nothing to test.

### Harmonic-drive failure modes
The grease route requires at least one of the four harmonic-drive gear-grease mode families
across `failure_mode` + `mechanism`: **micro-pitting, fretting wear, grease hardening,
oil-bleed starvation**. An oil-shaped mode set (foam, demulsibility, sump oxidation) names
none of them and is rejected.

### What the oil routes see
Unchanged: no `criteria_layer` requirement, no harmonic-drive mode requirement, no extra
chain grammar — exactly the pre-existing prefix and uncertainty-marker checks.

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
```bash
python skills/failure-ctq-analysis/scripts/build_failure_ctq_artifact.py <input.json> <temporary-file.json>
```
Creates candidate JSON at `stage: "FAILURE_CTQ_DEFINED"`, retaining the 7 decision fields (`decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`, `decision: "GO"`, `next_action: "Qualify the proposed test method."`).
The builder re-runs the route policy at the construction boundary and projects each CTQ onto the contract's own field order, so a grease record cannot be assembled without its declared criteria layers.

### Step 3: Validate Artifact
```bash
python skills/failure-ctq-analysis/scripts/validate_failure_ctq_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: failure_ctq artifact conforms to the Stage 3 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` only after Step 3 passes. **Naming rule**: if `failure_ctq.json` does not yet exist in the workspace root, commit this record as `failure_ctq.json`; otherwise commit it as `failure_ctq-<project_id>-<failure_id>.json`. That is, the first record of this stage occupies the canonical name `failure_ctq.json` (the stage-gate panel uses this exact name to mark the stage complete), and subsequent records of the same stage are appended as suffixed names carrying the record ID. After the commit, run `python scripts/check_artifact_naming.py <workspace_root>` and correct any `HOLD` before proceeding. The checker also enforces that `project.json`'s `stage` stays the constant `PROJECT_DEFINED` — it is NOT the project's current stage, and must not be advanced.
```bash
# 🔴 CHECKPOINT · STOP: Stage 3 stops here at FAILURE_CTQ_DEFINED. Route to Stage 3.5 (test-method-qualification).
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: root_cause item does not start with Hypothesis:/假设:` | 根本原因被断言为已确诊事实 | **STOP**。要求用户修改表述，必须以 `Hypothesis:` 前缀表达未证伪的科学假设。 |
| `HOLD: specification_limit and engineering_risk_limit conflated` | 限值混为一谈或缺失其一 | **STOP**。要求分别提供工程风险控制线与客户规格底线。 |
| `HOLD: ... criteria_layer is required for PRECISION_GREASE_DEV` | 精密脂 CTQ 未声明所属判据层 | **STOP**。每个 CTQ 必须声明 SCREENING / BENCH / MACHINE 之一（三层判据链：理化筛测 → 台架 → 整机），否则无法路由到对应门禁。 |
| `HOLD: ... failure_diagnosis must not name a lubricant cause` | 从「轴承磨损」直跳「抗磨剂不足」 | **STOP**。诊断步只写物理/摩擦学状态；润滑剂关联网只能在 root_cause_hypotheses → lubricant_contribution 两环表达。 |
| `HOLD: ... failure_diagnosis must add the diagnosis step, not restate the failure mode` | 诊断步被空置或抄写失效模式 | **STOP**。要求写出诊断推理本身，不得以复制模式名代替诊断。 |
| `HOLD: ... failure_mode must name a harmonic-drive grease failure mode` | 失效模式仍是油的口径 | **STOP**。必须落到微点蚀 / 微振磨损 / 脂硬化 / 析油致润滑不足四类谐波专属模式之一。 |
| `HOLD: challenge_artifact must have decision GO` | 上游挑战未通过阶段门禁 | **STOP**。退回 Stage 2 补足工况挑战依据。 |
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 错误 | 检查输入文件语法及 Schema 路径。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Confirmed Root Cause**: DO NOT declare lubricant failure causes as definite conclusions without completed bench tests.
2. **NO Limit Conflation**: DO NOT use a single limit to serve both specification and engineering risk boundaries.
3. **NO Premature Formulation**: DO NOT suggest additive treat rates or chemical components in Stage 3.
4. **NO Dirty Overwrites**: DO NOT overwrite existing failure records with mismatched `project_id` or `failure_id`.
5. **NO Shortcut Diagnosis**: DO NOT jump from an observed symptom directly to a lubricant cause. On the grease route the chain Failure Diagnosis → Root-Cause Hypothesis → Lubricant Contribution is enforced: the diagnosis must state the physical/tribological condition, the hypotheses must carry the lubricant linkage, and the contribution must stay pending verification.
6. **NO Undeclared Criteria Layer**: On the grease route every CTQ must declare `criteria_layer` ∈ {`SCREENING`, `BENCH`, `MACHINE`}; an undeclared CTQ cannot be routed to the gate that will judge it.

