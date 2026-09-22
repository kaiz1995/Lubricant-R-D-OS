---
name: gate-review
description: Record one evidence-bound review Gate at VERIFIED; preflight verifies the complete 9-artifact upstream chain through OPTIMIZED; HOLDs GO requests with unresolved conditions or evidence gaps and rejects unsupported dispositions. Use when user mentions "gate-review", "阶段门禁评审", "Stage Gate", "VERIFIED", "门禁决策", "GO/HOLD决议", or finalizing Stage 9 in lubricant R&D.
---

# Gate Review (Stage 9)

Record an evidence-bound review Gate at `VERIFIED` for the Lubricant R&D Domain Pack.
This is a governance verification and milestone disposition record, NOT a downstream closure or formulation freeze artifact.

Authority schema: `../../schemas/gate.schema.json` (or local `references/gate.schema.json` in deployed bundle).

---

## 1. Input Specification & Gating Disposition Invariants

A single JSON input object providing the complete 9 upstream stage artifacts through `OPTIMIZED` and the `gate` review submission:

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
  "optimization_artifact": "path/to/optimization.json",
  "gate": {
    "gate_id": "GATE-STAGE-FINAL-001",
    "scope": "Comprehensive Phase 3/4 Stage Gate Verification for ISO VG 320 WTG Oil",
    "gate_status": "GO",
    "satisfied_conditions": ["All CTQ limits verified via physical bench testing"],
    "unsatisfied_conditions": [],
    "retained_risks": ["Long-term filter clogging monitoring under field operation"],
    "evidence_gaps": [],
    "reason": "Deterministic verification achieved across tribological, physical, and cost objectives.",
    "evidence": [
      {
        "evidence_id": "EV-GATE-001",
        "statement": "Formal review board consensus achieved with all acceptance criteria satisfied.",
        "source": "R&D Gate Review Board Minutes 2026-08-25",
        "status": "OBSERVED"
      }
    ]
  }
}
```

### Disposition Rules
1. **GO Approval Conditions**:
   - `unsatisfied_conditions` MUST be empty (`[]`).
   - `evidence_gaps` MUST be empty (`[]`).
   - No evidence items with `status: "GAP"`.
   - If any of these are violated, the deterministic disposition MUST be `HOLD`.
2. **Alternative Dispositions**:
   - `PIVOT`, `KILL`, and `FREEZE` require an explicit non-empty `reason` and valid evidence without `GAP`.
3. **Stage Horizon**: This skill stops at `stage: "VERIFIED"`. It never writes `FROZEN` or `CLOSED`.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/gate-review/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/gate-review/scripts/preflight_gate_review.py <input.json>
```
- Expected output on success: `READY: input can form one VERIFIED record only` (exit code 0).
- If preflight fails: Output starts with `HOLD: ...` (exit code 1).

### Step 2: Build Deterministic Artifact
```bash
python skills/gate-review/scripts/build_gate_artifact.py <input.json> <temporary-file.json>
```

### Step 3: Validate Artifact
```bash
python skills/gate-review/scripts/validate_gate_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: gate artifact conforms to the Stage 9 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` only after Step 3 passes.
```bash
# 🔴 CHECKPOINT · STOP: Stage 9 stops here at VERIFIED. Project verification milestone achieved.
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: unsatisfied conditions or evidence gaps exist` | 存在未解决的技术风险或证据缺口 | **STOP**。将门禁决议设为 HOLD，输出缺陷项清单，通知责任人整改。 |
| `HOLD: upstream artifact chain broken` | 9 大前序工件中有缺失或未达 GO 状态 | **STOP**。排查并修复未通过门禁的上游阶段。 |
| `HOLD: PIVOT/KILL/FREEZE lacks explicit rationale` | 非 GO 决议缺少依据阐述 | **STOP**。要求评审委员会提供清晰的技术转向或终止依据。 |
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 错误 | 检查输入文件与 `../../schemas/gate.schema.json`。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Fake GO Dispositions**: NEVER grant a `GO` disposition when `unsatisfied_conditions` or `evidence_gaps` are non-empty.
2. **NO Stage Overstepping**: DO NOT write terminal stages (`FROZEN` or `CLOSED`) in this skill.
3. **NO New Calculations**: DO NOT calculate new regressions, DOE points, or optimization Pareto sets in Stage 9.
4. **NO Dirty Overwrites**: DO NOT overwrite existing gate records with mismatched `project_id` or `gate_id`.

