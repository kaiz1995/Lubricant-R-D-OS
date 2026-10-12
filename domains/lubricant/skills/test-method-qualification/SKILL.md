---
name: test-method-qualification
description: Qualify one evidence-bound lubricant test method at TEST_METHODS_QUALIFIED; preflight verifies upstream artifacts, method provenance, role metrics (C/D/P), the serial repeatability-discrimination-independent-batch pipeline, and physical evidence scope before building the artifact. Use when user mentions "test-method-qualification", "测试方法评定", "台架评定", "方法标定", "区分度验证", "重复性", "FZG评定", or advancing to Stage 3.5 in lubricant R&D.
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
3. **REPEATABILITY is required for EVERY role** (`role_metric_errors`). A method whose repeatability was never established cannot support any claim: you do not know whether a difference you measured is a difference in the sample or in the stand. This is checked for every role, not only D and P.

---

## 2. The Three Qualification Sub-Steps Are SERIAL, Not Parallel

The single most important rule of the grease route (outer-loop step 5):

```
repeatability  ->  discrimination  ->  independent new batch check
(same sample       (does it separate    (re-verify on a FRESH batch;
 measured many      Known Good from     never build and verify on
 times: is it       Known Bad?)         the same data)
 computable?)
```

They are declared in the optional `qualification_pipeline` object, one entry per sub-step, each carrying `status` / `evidence_reference` / `computed_by` in `{ENGINE, MANUAL}`.

- You may NOT record `discrimination` without `repeatability` PASS: a discrimination result recorded on top of an unpassed repeatability step has no established measurement noise behind it.
- You may NOT record `independent_batch` without `discrimination` recorded, and it must be `PASS`. Re-verification on a fresh batch is the only check that a result is not an artefact of the batch that produced it. Building and verifying on the same data is not verification.
- `repeatability` and `discrimination` must be **computed by the ENGINE**. A hand-entered figure is a declaration, not a measurement: before a method can predict the bench, any optimisation algorithm only optimises the wrong target faster. Each entry in `qualification_metrics[]` also carries the optional `computed_by`, and a `MANUAL` value on either of those two metrics is refused.
- `reference_material_reference` names the Stage 4 reference dossier this qualification used as its discrimination ruler. Discrimination cannot be proved without physical Known Good / Known Bad objects, so a grease-route qualification names the dossier it consumed. If the supplied dossier's `downstream_flag` is `DISCRIMINATION_EVIDENCE_INCOMPLETE`, that state is reported and must be carried to the final gate.

### Route gating

The three rules above (mandatory `REPEATABILITY`, the serial pipeline, the ENGINE requirement) are enforced on the `PRECISION_GREASE_DEV` route only. The six oil project types keep their existing behaviour exactly: their `REPEATABILITY` metric stays optional and no pipeline is required. The gate is the upstream `project.json`'s `project_type`, read by the preflight; the validator, which sees only the artifact, detects the extension from the artifact itself (presence of `qualification_pipeline` or `reference_material_reference`). The shared schema declares all of the new fields as OPTIONAL, so no oil-route fixture changes.

---

## 3. Deterministic Execution Workflow

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
Atomically copy/move `<temporary-file.json>` to `<output.json>` only after Step 3 passes. **Naming rule**: if `test_method.json` does not yet exist in the workspace root, commit this record as `test_method.json`; otherwise commit it as `test_method-<project_id>-<method_id>.json`. That is, the first record of this stage occupies the canonical name `test_method.json` (the stage-gate panel uses this exact name to mark the stage complete), and subsequent records of the same stage are appended as suffixed names carrying the record ID. After the commit, run `python scripts/check_artifact_naming.py <workspace_root>` and correct any `HOLD` before proceeding. The checker also enforces that `project.json`'s `stage` stays the constant `PROJECT_DEFINED` — it is NOT the project's current stage, and must not be advanced.
```bash
# 🔴 CHECKPOINT · STOP: Stage 3.5 stops here at TEST_METHODS_QUALIFIED. Route to Stage 4 (formulation-design).
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: SYNTHETIC evidence cannot have status QUALIFIED` | 尝试用模拟/合成数据通过方法评定 | **STOP**。将 qualification_status 调整为 PENDING/NOT_QUALIFIED，等待物理实测报告。 |
| `HOLD: Role D requires discrimination metric` | 缺少区分度灵敏度量化描述 | **STOP**。要求用户提供标油与试验油的区分台阶数据。 |
| `HOLD: role D requires REPEATABILITY` | 未声明重复性指标 | **STOP**。要求先做同一样多次测量并声明 REPEATABILITY。缺了它，测到的差异分不清是样品差异还是台架噪声。 |
| `HOLD: repeatability must pass before discrimination` | 三步串联被当成并列（重复性未通过就记区分度） | **STOP**。先补齐重复性证据并令其 PASS，再记区分度。 |
| `HOLD: discrimination must be computed by the engine` | 区分度是手填数字 | **STOP**。不接受手填，必须由计算引擎算出。 |
| `HOLD: independent_batch must be PASS` | 独立新批次复核未通过或缺失 | **STOP**。在全新批次上复核；禁止用同一批数据既建又验。 |
| `HOLD: qualification_pipeline is required on the PRECISION_GREASE_DEV route` | 脂路线缺少串联管线 | **STOP**。补齐 repeatability / discrimination / independent_batch 三项。 |
| `HOLD: failure_ctq_artifact must have decision GO` | 上游失效分析未通过 | **STOP**。退回 Stage 3 补齐失效 CTQ 依据。 |
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 错误 | 检查输入文件与 `../../schemas/test_method.schema.json`。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Synthetic Promotion**: NEVER promote synthetic bench models to `QUALIFIED` status.
2. **NO Formulation Generation**: DO NOT draft recipes, candidate treat rates, or design space boundaries here.
3. **NO Role Metric Omission**: DO NOT assign `D` or `P` roles without the corresponding mechanism/discrimination metrics, and DO NOT omit `REPEATABILITY`.
4. **NO Parallel Pipeline**: DO NOT treat repeatability, discrimination, and the independent new batch check as three independent declarations. They are serial, and a later sub-step without its predecessor passing is a gap, not a stronger submission.
5. **NO Hand-Entered Discrimination**: DO NOT fill repeatability or discrimination numbers by hand. They must be engine-computed.
6. **NO Same-Batch Verification**: DO NOT verify a conclusion on the batch that produced it.
7. **NO Dirty Overwrites**: DO NOT overwrite existing test method files with mismatched `project_id` or `method_id`.

