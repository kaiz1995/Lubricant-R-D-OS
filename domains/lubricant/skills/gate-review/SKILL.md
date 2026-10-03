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

### Signoff Role Mapping (WP-08)

The gate artifact may additionally RECORD the following optional signoff fields (schema: `gate.schema.json`; `dissent` items follow `common.schema.json#/$defs/dissent_item`):

| Field | Role semantics | Recorded meaning |
|---|---|---|
| `technical_reviewer` | Named technical reviewer of this gate | The person who performed the technical review that this gate records (answers V3 "谁复核的"). |
| `reviewed_at` | Time of the technical review | ISO-8601 timestamp of that review. |
| `approver` | Named approver of this gate | The person who accepted the gate disposition (answers V3 "谁批准的"). |
| `approved_at` | Time of the approval | ISO-8601 timestamp of that approval. |
| `dissent[]` | Recorded dissents | Each item is `{reviewer, comment, status: OPEN\|RESOLVED}`; an `OPEN` item is an unresolved dissent. |

**Record-only, no authentication**: these fields are *records only*. No script in this skill (or in the domain) checks authority, identity, or permission — naming a reviewer/approver confers no capability and validates no identity (计划 §7 第 2 条：签批只记录不鉴权). The FREEZE precondition ("a `technical_reviewer` is named AND no unresolved dissent exists") is adjudicated **solely** by `scripts/validate_state_machine.py` at the state-machine FREEZE branch, never by this skill: this skill still stops at `VERIFIED` and never decides FREEZE.

`build_gate_artifact.py` carries these fields through to the artifact verbatim when present in the input `gate` object; omitting them leaves the artifact schema-valid (they are optional).

REVISE interplay (WP-08/WP-13 migration): a `PROCESS_ONLY` intra-stage revision may cite this gate's `gate_id` in `revision.reuses_review_of` to reuse the signoff recorded here; a `FORMULA_OR_CTQ` revision must re-review and may cite the fresh re-review gate via `revision.re_review.gate_review_id`, which lets V3 resolve the original/fresh signoff through the gate artifact instead of trusting an embedded note.

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
Atomically copy/move `<temporary-file.json>` to `<output.json>` only after Step 3 passes. **Naming rule**: if `gate.json` does not yet exist in the workspace root, commit this record as `gate.json`; otherwise commit it as `gate-<project_id>-<gate_id>.json`. That is, the first record of this stage occupies the canonical name `gate.json` (the stage-gate panel uses this exact name to mark the stage complete), and subsequent records of the same stage are appended as suffixed names carrying the record ID. After the commit, run `python scripts/check_artifact_naming.py <workspace_root>` and correct any `HOLD` before proceeding. The checker also enforces that `project.json`'s `stage` stays the constant `PROJECT_DEFINED` — it is NOT the project's current stage, and must not be advanced.
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

