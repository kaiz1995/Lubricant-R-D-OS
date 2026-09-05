---
name: experiment-import
description: Import one PHYSICAL experiment record with DOE-point and execution provenance at EXPERIMENT_RUNNING; preflight verifies 6 upstream artifacts, raw DOE SHA-256 digest, and calibration provenance. Use when user mentions "experiment-import", "实验导入", "实验数据接入", "台架数据摄取", "物理实验记录", or advancing to Stage 6 in lubricant R&D.
---

# Experiment Import (Stage 6)

Import one PHYSICAL experiment record with strict execution and DOE-point provenance at `EXPERIMENT_RUNNING` for the Lubricant R&D Domain Pack.
This is a raw experimental record ingestion and provenance lock, NOT a statistical regression or performance conclusion.

Authority schema: `../../schemas/experiment.schema.json` (or local `references/experiment.schema.json` in deployed bundle).

---

## 1. Input Specification & Provenance Invariants

A single JSON input object providing the 6 upstream artifacts, the raw DOE output reference, and `execution_record`:

```json
{
  "project_artifact": "path/to/project.json",
  "challenge_artifact": "path/to/challenge.json",
  "failure_ctq_artifact": "path/to/failure_ctq.json",
  "test_method_artifact": "path/to/test_method.json",
  "design_space_artifact": "path/to/design_space.json",
  "experiment_design_artifact": "path/to/experiment_design.json",
  "doe_output_file": "path/to/doe_output.json",
  "execution_record": {
    "experiment_id": "EXP-WGO-001",
    "evidence_scope": "PHYSICAL",
    "operator": "Lab Tech Zhang (Certification L2-Tribology)",
    "instrument": "FZG Gear Test Rig #3 (Rig-ID: FZG-03-A)",
    "calibration_record": {
      "calibration_id": "CAL-2026-05",
      "valid_until": "2026-12-31",
      "standard": "ISO/IEC 17025"
    },
    "timestamp": "2026-08-25T14:30:00+08:00",
    "runs": [
      {
        "run_index": 1,
        "formula_version": "v1.0",
        "measured_responses": [
          {
            "ctq_reference": "CTQ-FZG-GF-STAGE",
            "value": 11.0,
            "unit": "stage",
            "raw_log_reference": "LOG-RUN-001.pdf"
          }
        ]
      }
    ]
  }
}
```

### Invariants
1. **Physical Scope Strict Gate**: Accepts `evidence_scope: "PHYSICAL"` ONLY. Any `SYNTHETIC` data is strictly rejected with `HOLD`.
2. **SHA-256 Digest Integrity**: The preflight script computes the SHA-256 digest of `doe_output_file`; it must match the registered runs.
3. **Traceability**: Requires non-empty `operator`, `instrument`, valid `calibration_record`, and timezone-bearing `timestamp`.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/experiment-import/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/experiment-import/scripts/preflight_experiment_import.py <input.json>
```
- Expected output on success: `READY: input can form one EXPERIMENT_RUNNING record only` (exit code 0).
- If preflight fails: Output starts with `HOLD: ...` (exit code 1).

### Step 2: Build Deterministic Artifact
```bash
python skills/experiment-import/scripts/build_experiment_artifact.py <input.json> <temporary-file.json>
```

### Step 3: Validate Artifact
```bash
python skills/experiment-import/scripts/validate_experiment_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: experiment artifact conforms to the Stage 6 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` only after Step 3 passes.
```bash
# 🔴 CHECKPOINT · STOP: Stage 6 stops here at EXPERIMENT_RUNNING. Pass to Stage 7 (statistical-analysis).
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: SYNTHETIC evidence is not permitted in experiment-import` | 试图摄入无物理标定的合成/模拟数据 | **STOP**。禁止入库。要求提供真实实验室试验记录与仪器日志。 |
| `HOLD: DOE output SHA-256 mismatch or invalid` | 实验跑点与批准的 DOE 规划失配 | **STOP**。重新对齐 `doe_output_file`，确保实验点与设计完全一致。 |
| `HOLD: missing calibration or timezone in timestamp` | 溯源元数据不全（无时间戳时区或仪器检定过期） | **STOP**。要求补齐 ISO 17025 检定凭证和 ISO 8601 时区时间戳。 |
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 错误 | 检查输入文件与 `../../schemas/experiment.schema.json`。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Synthetic Data Entry**: NEVER allow synthetic, simulated, or predicted runs to enter as experimental evidence.
2. **NO Statistical Fitting**: DO NOT compute regression equations, p-values, or response surface maps in Stage 6.
3. **NO Performance Conclusions**: DO NOT declare formula qualification or compliance before Stage 7 & 8 analysis.
4. **NO Dirty Overwrites**: DO NOT overwrite existing experiment records with mismatched `project_id` or `experiment_id`.

