---
name: process-scale-up
description: Fix the grease manufacturing process window at the amplified batch scale after the OPTIMIZED conclusion and emit a PROCESS_WINDOW_DEFINED process artifact carrying the 工艺窗口 evidence. Use when user mentions "process-scale-up", "工艺窗口", "放大", "scale-up", "PROCESS_WINDOW_DEFINED", "工艺窗口固化", "manufacturability", or the stage between OPTIMIZED and VERIFIED.
---

# Process Scale-Up (工艺窗口固化)

Fix one manufacturing window from two upstream conclusions: the evidence-bound process record (what the kettle can hold) and the OPTIMIZED conclusion (which candidate the design converged on). The output is the only artifact that may be cited as the 工艺窗口: `PROCESS-WINDOW:<window_id>`.

The window is a **fixed** conclusion, not a range of possibilities. Assigning a window from a single lab batch, or from evidence that still carries a GAP, is a hard reject.

Authority schema: `../../schemas/process.schema.json` (or local `references/process.schema.json` in deployed bundle). Upstream contracts: `../../schemas/process.schema.json` and `../../schemas/optimization.schema.json`. Downstream consumer: `../../schemas/design_freeze.schema.json` — its `MANUFACTURABILITY_ACCEPTABLE` condition MUST cite this window.

---

## 1. Prerequisites & Gating

Before requesting scale-up input:
- A `DESIGN_SPACE_DEFINED` process record MUST exist and validate against `process.schema.json`. If it is missing, redirect to `process-definition` first.
- An `OPTIMIZED` optimization artifact MUST exist with `decision: "GO"` and the **same** `project_id`. If it is missing or `HOLD`, redirect to `optimization` first.
- The declared `scale_up.batch_scale.scale_class` MUST advance strictly along `LAB → PILOT → PRODUCTION` relative to the process record, and `scale_up.amplification_factor` MUST exceed the process record's `amplification_factor`.

---

## 2. Input Specification

Input must be a single JSON object containing both upstream artifact paths and the `scale_up` block:

```json
{
  "process_artifact": "path/to/process.json",
  "optimization_artifact": "path/to/optimization.json",
  "scale_up": {
    "window_id": "PW-WGO-001-PROD",
    "basis": "Pilot-to-production amplification run under the qualified control points",
    "amplification_factor": 200.0,
    "batch_scale": {
      "scale_class": "PRODUCTION",
      "batch_size": { "value": 500, "unit": "kg", "source": "Amplification run record AR-001", "method_version": "scale-v2", "material_batch": "BATCH-PROD-001", "formula_version": "v0.2" }
    },
    "evidence_scope": "PHYSICAL",
    "evidence": [
      { "evidence_id": "EV-SCALE-001", "statement": "Amplification run reproduced the phase-inversion and milling window at production scale.", "source": "OPT-… (OPTIMIZED conclusion) + amplification run record AR-001", "status": "OBSERVED" }
    ]
  }
}
```

### Field Invariants
- Upstream alignment: the process record and the OPTIMIZED conclusion MUST share one `project_id`; a cross-project window is rejected.
- Scale step (hard): `scale_class` MUST be strictly later than the process record's class (`LAB < PILOT < PRODUCTION`) and `amplification_factor` MUST be strictly greater. A "scale-up" that does not scale is rejected.
- Scope retention: `scale_up.evidence_scope` MUST equal the process record's `evidence_scope`. A window fixed on synthetic evidence stays synthetic and can never reach `CLOSED`.
- Window evidence (hard): `process_window.validated` MUST become `true` and `process_window.evidence_reference` MUST be exactly `PROCESS-WINDOW:<window_id>`. That string is what `design_freeze` cites for `MANUFACTURABILITY_ACCEPTABLE`.
- Evidence integrity: the retained evidence list is the process record's evidence plus the scale-up evidence; `scale_up.evidence` MUST be non-empty, well-formed, and contain no `GAP` status.
- Provenance of the OPTIMIZED link: the OPTIMIZED linkage is enforced by the preflight (artifact existence, stage, `decision: "GO"`, project match) and recorded in each scale-up evidence `source`; no new process field was added for it.

---

## 3. Deterministic Execution Workflow

All scripts reside in `skills/process-scale-up/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/process-scale-up/scripts/preflight_process_scale_up.py <input.json>
```
- Expected output on success: `READY: input can fix one PROCESS_WINDOW_DEFINED process record only` (exit code 0).
- If preflight fails: output starts with `HOLD: missing or invalid: ...; no artifact generated` (exit code 1). See Section 4.

### Step 2: Build Deterministic Artifact
```bash
python skills/process-scale-up/scripts/build_process_window_artifact.py <input.json> <temporary-file.json>
```
The builder emits `artifact_type: "process"`, `stage: "PROCESS_WINDOW_DEFINED"`, regenerates the canonical decision fields, retains both evidence sets, and stamps `process_window.evidence_reference`.

### Step 3: Validate Artifact
```bash
python skills/process-scale-up/scripts/validate_process_window_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: deterministic process-window artifact conforms to the process contract at PROCESS_WINDOW_DEFINED` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3 returns `PASS`.
```bash
# 🔴 CHECKPOINT · STOP: the window stops here. It links DESIGN_SPACE_DEFINED (process) +
# OPTIMIZED (optimization) → PROCESS_WINDOW_DEFINED.
# Do NOT run gate-review, mark the project VERIFIED, or claim release approval from this skill.
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... process_artifact must be stage DESIGN_SPACE_DEFINED` | 上游工艺记录缺失或阶段不符 | **STOP**。先运行 `process-definition` 得到工艺记录，不得凭空固化窗口。 |
| `HOLD: ... optimization_artifact must have decision GO` | 优化结论仍是 HOLD | **STOP**。先回到 `optimization` 解掉缺口，禁止越级固化窗口。 |
| `HOLD: ... must belong to the same project_id` | 工艺记录与优化结论跨项目 | **STOP**。核对两个上游工件路径，确认归属同一 `project_id`。 |
| `HOLD: ... scale_up.amplification_factor must exceed the process record amplification_factor` | 声明的放大倍数没有真正放大 | **STOP**。给出真实放大倍数与对应批次规模，不猜默认值。 |
| `HOLD: ... scale_up.batch_scale.scale_class must advance beyond the process record scale class` | 批次规模没有沿 LAB→PILOT→PRODUCTION 前进 | **STOP**。核对批次规模与 `scale_class` 的对应关系。 |
| `HOLD: ... scale_up.evidence_scope must retain the process record evidence_scope` | 证据口径在中途被拔高 | **STOP**。窗口口径必须与上游工艺记录一致，SYNTHETIC 不得升级为 PHYSICAL。 |
| `HOLD: ... scale_up.evidence contains GAP` | 放大证据链存在未解缺口 | **STOP**。保持 HOLD，输出 gap 诊断，等待证据补足。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法损坏 | 检查 `../../schemas/` 与输入文件 JSON 格式。 |

---

## 5. Red Lines & Blacklist (Strict Prohibition)

1. **NO Invented Amplification Evidence**: DO NOT invent amplification factors, production batch sizes, or run records.
2. **NO Window Without Scale-Up**: DO NOT fix a window whose `scale_class` is the same as or earlier than the process record, or whose `amplification_factor` does not increase.
3. **NO Scope Upgrade**: DO NOT raise a SYNTHETIC process record to a PHYSICAL window, and DO NOT let a SYNTHETIC window reach `CLOSED`.
4. **NO Free-Form Manufacturability Citation**: DO NOT let `MANUFACTURABILITY_ACCEPTABLE` cite anything other than `PROCESS-WINDOW:<window_id>`.
5. **NO Capability or Release Claims**: DO NOT claim Cpk, capability, release approval, or product performance from this skill; the window is a fixed manufacturing constraint, not a release decision.
6. **NO Cross-Stage Spillover**: DO NOT run gate-review, FREEZE the design, or advance the state machine in this skill.
7. **NO Bypass of Preflight**: DO NOT create the output artifact without running `preflight_process_scale_up.py` first.
8. **NO Soft Guidance Words**: Forbidden ambiguous words: "灵活调整", "视情况而定", "酌情设置", "可以考虑". All values must be concrete numbers with verifiable metadata.
