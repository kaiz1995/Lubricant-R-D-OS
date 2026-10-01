---
name: process-definition
description: Define one evidence-bound grease manufacturing process record alongside the Stage 4 design space; preflight verifies the upstream DESIGN_SPACE_DEFINED artifact and rejects any process parameter missing source or evidence_id. Use when user mentions "process-definition", "工艺定义", "制脂工艺", "工艺参数", "process window", "factor_role", "WHOLE_PLOT", "SUB_PLOT", or defining the grease manufacturing process (皂化/转相/研磨/均质) linked to a design space.
---

# Process Definition (design-space companion)

Define an evidence-bound grease manufacturing process record that is a peer dimension of the formulation design space. Process is not a factor hung inside the formulation: the same formula over a different kettle can produce a different product because the soap-fibre skeleton is set by saponification, phase inversion, cooling rate, and milling.

Authority schema: `../../schemas/process.schema.json` (or local `references/process.schema.json` in deployed bundle). Upstream artifact contract: `../../schemas/design_space.schema.json`.

---

## 1. Prerequisites & Gating

Before requesting process inputs:
- A `DESIGN_SPACE_DEFINED` design-space artifact MUST exist with `decision: "GO"` and a resolvable `project_id`.
- If it is missing, `HOLD`, or belongs to another project, do NOT invent process parameters. Direct the user back to `formulation-design` first.

---

## 2. Input Specification

Input must be a single JSON object containing the upstream `design_space_artifact` path and the `process` specification:

```json
{
  "design_space_artifact": "path/to/design-space.json",
  "process": {
    "process_id": "PROC-WGO-001",
    "project_reference": "WGO-001",
    "process_step": [
      { "step_id": "ST-001", "step_type": "SAPONIFICATION",
        "parameters": [
          { "parameter_id": "P-SAP-TEMP", "parameter_name": "saponification temperature", "lower_bound": 90, "upper_bound": 110, "unit": "degC", "source": "Synthetic process specification", "evidence_id": "EV-PROC-001", "status": "ASSUMED" }
        ] },
      { "step_id": "ST-002", "step_type": "DEHYDRATION",
        "parameters": [
          { "parameter_id": "P-DEH-TEMP", "parameter_name": "dehydration temperature", "lower_bound": 100, "upper_bound": 130, "unit": "degC", "source": "Synthetic process specification", "evidence_id": "EV-PROC-002", "status": "ASSUMED" }
        ] },
      { "step_id": "ST-003", "step_type": "PHASE_INVERSION",
        "parameters": [
          { "parameter_id": "P-PHI-TEMP", "parameter_name": "phase inversion temperature", "lower_bound": 150, "upper_bound": 180, "unit": "degC", "source": "Synthetic process specification", "evidence_id": "EV-PROC-003", "status": "ASSUMED" }
        ] },
      { "step_id": "ST-004", "step_type": "DILUTION_COOLING",
        "parameters": [
          { "parameter_id": "P-COOL-RATE", "parameter_name": "cooling rate", "lower_bound": 1, "upper_bound": 5, "unit": "degC/min", "source": "Synthetic process specification", "evidence_id": "EV-PROC-004", "status": "ASSUMED" }
        ] },
      { "step_id": "ST-005", "step_type": "MILLING",
        "parameters": [
          { "parameter_id": "P-MIL-GAP", "parameter_name": "mill gap", "lower_bound": 0.05, "upper_bound": 0.3, "unit": "mm", "source": "Synthetic process specification", "evidence_id": "EV-PROC-005", "status": "ASSUMED" }
        ] },
      { "step_id": "ST-006", "step_type": "HOMOGENIZATION",
        "parameters": [
          { "parameter_id": "P-HOM-PRES", "parameter_name": "homogenization pressure", "lower_bound": 5, "upper_bound": 20, "unit": "MPa", "source": "Synthetic process specification", "evidence_id": "EV-PROC-006", "status": "ASSUMED" }
        ] },
      { "step_id": "ST-007", "step_type": "VACUUM_DEAERATION",
        "parameters": [
          { "parameter_id": "P-VAC-PRES", "parameter_name": "vacuum pressure", "lower_bound": 1, "upper_bound": 10, "unit": "kPa", "source": "Synthetic process specification", "evidence_id": "EV-PROC-007", "status": "ASSUMED" }
        ] },
      { "step_id": "ST-008", "step_type": "FILLING",
        "parameters": [
          { "parameter_id": "P-FILL-TEMP", "parameter_name": "filling temperature", "lower_bound": 70, "upper_bound": 90, "unit": "degC", "source": "Synthetic process specification", "evidence_id": "EV-PROC-008", "status": "ASSUMED" }
        ] }
    ],
    "batch_scale": { "scale_class": "PILOT", "batch_size": { "value": 50, "unit": "kg", "source": "Synthetic process specification", "method_version": "scale-v1", "material_batch": "BATCH-SYN-001", "formula_version": "v0.1" } },
    "amplification_factor": 20.0,
    "process_window": { "window_id": "PW-WGO-001", "basis": "Synthetic process window supplied for contract validation only", "validated": false },
    "control_points": [
      { "control_point_id": "CP-001", "parameter_id": "P-PHI-TEMP", "control_type": "IN_PROCESS", "criterion": "Hold phase inversion within the supplied window", "source": "Synthetic process specification", "evidence_id": "EV-PROC-003" }
    ],
    "cpk": { "value": 1.33, "ctq_reference": "CTQ-001", "sample_size": 30 },
    "material_batch_reference": "BATCH-SYN-001",
    "factor_role": "SUB_PLOT",
    "evidence_scope": "SYNTHETIC",
    "evidence": [
      { "evidence_id": "EV-PROC-001", "statement": "Synthetic process bounds supplied for contract validation only; not a qualified process window.", "source": "Synthetic process fixture", "status": "ASSUMED" }
    ]
  }
}
```

### Field Invariants
- Upstream alignment: the process is created only from a `DESIGN_SPACE_DEFINED` design space with `decision: "GO"`; `process.project_reference` MUST equal the upstream `project_id`.
- Parameter provenance (hard): every parameter REQUIRES non-empty `source` and `evidence_id`. A parameter without either is rejected with a per-parameter error; it is never defaulted.
- Parameter ordering: `lower_bound <= upper_bound`, both finite numbers, with an explicit `unit`.
- Step vocabulary: `step_type` is one of the 8 grease-manufacturing steps (`SAPONIFICATION`, `DEHYDRATION`, `PHASE_INVERSION`, `DILUTION_COOLING`, `MILLING`, `HOMOGENIZATION`, `VACUUM_DEAERATION`, `FILLING`).
- Control points: every `control_point.parameter_id` MUST reference a parameter declared in `process_step`.
- Scale: `amplification_factor` is a positive number; `batch_scale.scale_class` is one of `LAB` / `PILOT` / `PRODUCTION`.
- Split-plot role: `factor_role` is one of `WHOLE_PLOT` / `SUB_PLOT` (orthogonal to the design-space `constraint_role`).
- Evidence scope: `evidence_scope` is `SYNTHETIC` or `PHYSICAL`; a SYNTHETIC record must never reach `CLOSED`.
- Evidence integrity: `process.evidence` must be non-empty and contain no `GAP` status.

---

## 3. Deterministic Execution Workflow

All scripts reside in `skills/process-definition/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/process-definition/scripts/preflight_process_definition.py <input.json>
```
- Expected output on success: `READY: input can form one process record only` (exit code 0).
- If preflight fails: output starts with `HOLD: missing or invalid: ...; no artifact generated` (exit code 1). See Section 4.

### Step 2: Build Deterministic Artifact
```bash
python skills/process-definition/scripts/build_process_artifact.py <input.json> <temporary-file.json>
```
The builder generates canonical decision fields (`decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`, `decision`, `next_action`).

### Step 3: Validate Artifact
```bash
python skills/process-definition/scripts/validate_process_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: deterministic process artifact conforms to the process contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3 returns `PASS`.
```bash
# 🔴 CHECKPOINT · STOP: the process record stops here. It links to DESIGN_SPACE_DEFINED.
# Do NOT advance the state machine, generate a DOE matrix, or claim a validated process window.
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... design_space_artifact must be stage DESIGN_SPACE_DEFINED` | 上游设计空间缺失或阶段不符 | **STOP**。先运行 `formulation-design` 得到设计空间工件，不得凭空定义工艺。 |
| `HOLD: ... design_space_artifact must have decision GO` | 上游设计空间仍为 HOLD | **STOP**。要求先解掉设计空间缺口，禁止越级定义工艺。 |
| `HOLD: ... process.project_reference must equal the upstream design_space project_id` | 工艺工件与设计空间跨项目 | **STOP**。核对两个工件路径，确认归属同一 `project_id`。 |
| `HOLD: ... parameters[N].source is required for every process parameter` | 工艺参数缺来源 | **STOP**。输出缺失参数名，要求用户补齐来源，不猜默认值。 |
| `HOLD: ... parameters[N].evidence_id is required for every process parameter` | 工艺参数缺证据引用 | **STOP**。输出缺失参数名，要求用户补齐证据引用。 |
| `HOLD: ... control_points[N].parameter_id ... does not exist` | 控制点悬挂在不存在的参数上 | **STOP**。先定义该参数或修正控制点引用。 |
| `HOLD: ... process.evidence contains GAP` | 证据链存在未解缺口 | **STOP**。保持 HOLD，生成 gap 诊断，等待证据补足。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法损坏 | 检查 `../../schemas/` 与输入文件 JSON 格式。 |

---

## 5. Red Lines & Blacklist (Strict Prohibition)

1. **NO Invented Process Data**: DO NOT invent, hallucinate, or infer saponification temperatures, cooling rates, mill gaps, or any process bound.
2. **NO Provenance-Free Parameters**: DO NOT emit a parameter without both `source` and `evidence_id`. Missing provenance is a hard reject, not a warning.
3. **NO Window Claims**: DO NOT set `process_window.validated` to `true` or claim capability/Cpk conclusions from synthetic evidence.
4. **NO Cross-Stage Spillover**: DO NOT run DOE, generate factor matrices, build experiment artifacts, or advance the state machine in this skill.
5. **NO Synthetic Closure**: DO NOT let a SYNTHETIC process record reach `CLOSED`.
6. **NO Bypass of Preflight**: DO NOT create the output artifact without running `preflight_process_definition.py` first.
7. **NO Soft Guidance Words**: Forbidden ambiguous words: "灵活调整", "视情况而定", "酌情设置", "可以考虑". All bounds must be concrete numbers with verifiable metadata.
