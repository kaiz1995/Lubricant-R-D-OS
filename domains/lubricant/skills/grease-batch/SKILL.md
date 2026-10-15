---
name: grease-batch
description: Record one executed grease batch at BATCH_PRODUCED - the full saponification / dehydration / phase-inversion / dilution-cooling / milling / deaeration / filling / ripening trajectory with setpoint, actual, duration and an explicit per-step deviation verdict, plus the charged raw-material lots, operator, equipment, anomalies, and the labelled sample taken from it. Use when user mentions "grease-batch", "制脂与制样", "工艺执行记录", "工艺偏差", "皂化温度曲线", "转相", "研磨参数", "投料批次", "样品标签", or advancing to BATCH_PRODUCED in lubricant R&D.
---

# Grease Batch (BATCH_PRODUCED · 制脂与制样)

Record one executed grease batch at `BATCH_PRODUCED`: what was charged, what the equipment
actually did, and what deviation that produced against the declared baseline process. This
is a production record, NOT a formulation design, NOT a screening result, NOT a bench
result, and NOT a claim about product performance.

Authority schema: `../../schemas/batch.schema.json` and `../../schemas/sample.schema.json`
(or local `references/*.schema.json` in the deployed bundle). Deviation-boundary and
release-rule anchor: `scripts/grease_batch_policy.py`.

Why this stage exists: this is where the project's central claim lands - **a soap grease's
structure is set by saponification, phase inversion, cooling rate and milling, so the same
formula through a different kettle may not be the same product.** Without this step
recorded independently, that fact is invisible to the system: two samples carry the same
`formula_reference` and every downstream comparison silently assumes they are the same
thing. `batch.json` is the object that makes "recipe + process = product" checkable, and
the trajectory is the only place where a setpoint-versus-actual deviation can be judged
against the product that resulted.

The sample object is produced beside the batch, never separately: a sample is a physical
portion of a batch and cannot be identified without it. Its `sample_id` must be the id the
label printer actually printed.

---

## 1. Input Specification (contract in)

Input is a single JSON object: the three upstream artifact paths, the batch record, the
sample record, and the artifact-level evidence. The following is the shape of a real
request (values illustrative):

```json
{
  "project_artifact": "project.json",
  "design_space_artifact": "design_space.json",
  "experiment_design_artifact": "experiment_design.json",
  "evidence_scope": "PHYSICAL",
  "evidence": [
    {
      "evidence_id": "E-BAT-001",
      "statement": "Kettle log KL-001 records setpoint, actual, duration and a tolerance band for every executed step.",
      "source": "Kettle log KL-001",
      "status": "OBSERVED"
    }
  ],
  "batch": {
    "batch_id": "BAT-PG-001",
    "formula_reference": "FORM-PG-001@v1",
    "scale_class": "LAB",
    "trajectory": [
      {
        "step_type": "SAPONIFICATION",
        "setpoint": 195,
        "actual": 196,
        "unit": "degC",
        "duration_s": 5400,
        "deviation": 1,
        "deviation_verdict": "WITHIN",
        "tolerance": 3,
        "source": "Kettle log KL-001 line 12",
        "evidence_id": "E-BAT-001"
      },
      {
        "step_type": "PHASE_INVERSION",
        "setpoint": "visual inversion point",
        "actual": "visual inversion point",
        "unit": "qualitative",
        "duration_s": 420,
        "deviation": "none recorded",
        "deviation_verdict": "WITHIN",
        "tolerance": "operator confirms the inversion point on the sight glass",
        "source": "Kettle log KL-001 line 24",
        "evidence_id": "E-BAT-001"
      }
    ],
    "raw_material_lots": ["LOT-2026-001", "LOT-2026-014"],
    "operator": "Operator OP-01",
    "equipment": "5 L pilot kettle K-01",
    "anomalies": [],
    "batch_verdict": "VALID"
  },
  "sample": {
    "sample_id": "SMP-PG-001",
    "label": {
      "printed_text": "SMP-PG-001 | BAT-PG-001 | FORM-PG-001@v1 | 2026-10-05",
      "printed_at": "2026-10-05T09:40:00"
    },
    "prepared_at": "2026-10-05",
    "storage": "Sealed 1 kg drum at 25 degC, dry indoor cabinet, sample shelf S-03.",
    "chain_of_custody": [
      {
        "from": "Kettle operator OP-01",
        "to": "Sample store SS-01",
        "at": "2026-10-05",
        "purpose": "Store the freshly filled drum until the screening bench run is scheduled."
      }
    ],
    "status": "IN_TRANSIT"
  }
}
```

### Field Invariants (contract in)
- Upstream (hard): all three artifact paths are mandatory. `project.json` must be
  `stage: PROJECT_DEFINED`, `status: ACTIVE`, `decision: GO`; `design_space.json` must be
  `DESIGN_SPACE_DEFINED` and `decision: GO`; `experiment_design.json` must be
  `EXPERIMENT_DESIGNED` and `decision: GO`, and its `design_space_reference` must equal the
  supplied design space's `design_space_id`. Missing or invalid upstream = HOLD, nothing
  written.
- `evidence_scope`: `SYNTHETIC` or `PHYSICAL`. A SYNTHETIC record is fixture-only and can
  never authorize stage advancement.
- Trajectory step (input form): `step_type` ∈ the 12 grease route step types of
  `batch.schema.json`; `setpoint` / `actual` are numbers or non-empty strings;
  `unit`, `duration_s`, `deviation`; `deviation_verdict` ∈ {`WITHIN`,`DEVIATED`}; plus the
  input-only `tolerance`, `source`, `evidence_id`. An unknown field is a hard reject.
- `tolerance`: a non-negative number for a numeric step, a non-empty string for a
  qualitative step. This is the baseline band the deviation is judged against.
- Provenance (hard): every step needs its own `source` AND an `evidence_id` that resolves
  to an evidence item whose status is not `GAP`. A parameter without provenance is a hard
  reject, not a warning.
- `batch_verdict` ∈ {`VALID`,`DEVIATED`,`VOID`}; `scale_class` ∈ {`LAB`,`PILOT`,`PRODUCTION`};
  `raw_material_lots` non-empty and distinct; `anomalies` may be an EMPTY array - that
  records "none observed" and is a recorded absence, not missing data.
- Sample: `sample_id` must be a single printable token (no whitespace, no `|`) and
  `label.printed_text` must contain the sample id, the batch id and the formula reference -
  the id on the record must be the id the printer printed. `batch_reference` and
  `formula_reference` are **bound from the batch record** and supplying them is a hard
  reject. `chain_of_custody` is non-empty, in non-decreasing time order, and no handover may
  predate `prepared_at`.
- DO NOT supply `decision`, `decision_question`, `hypothesis`, `uncertainty`,
  `decision_rule`, `result` or `next_action`. All are DERIVED by `grease_batch_policy`;
  supplying them is a hard reject.

### Deviation Rule (the per-step judgement)
```
numeric step     : deviation must equal actual - setpoint (rounded-log tolerance 0.05)
                   |deviation| > tolerance  ->  the step MUST be recorded DEVIATED
                   |deviation| <= tolerance ->  WITHIN or DEVIATED (a stricter judgement is allowed)
qualitative step : deviation is the recorded observation; tolerance is the acceptance statement
```
Recording DEVIATED while the value is inside tolerance is allowed on purpose: a step may
run inside its band and still be unacceptable for a reason the band cannot express (a hold
that ran long, a drive that faulted). The reverse is what the rule forbids.

### Batch Verdict Rule (the release judgement)
```
VALID     legal only when NO step is DEVIATED
DEVIATED  must be justified: at least one DEVIATED step OR at least one recorded anomaly
VOID      must state why: batch.anomalies must be non-empty
```
The verdict is **declared by the caller and policed, never inferred** - whether a batch is
voided is a production decision that the record must carry, and a system that guessed it
would hide the decision.

### Release Rule (放行判据)
```
batch_verdict VALID     -> decision GO    : the sample may go to SCREENING_PASSED (grease-screening)
batch_verdict DEVIATED  -> decision HOLD  : disposition the deviation first; SCREENING_PASSED must not proceed
batch_verdict VOID      -> decision HOLD  : the batch is voided; the sample must not reach the bench
```

### Known validation boundary (stated, not hidden)
`schemas/batch.schema.json` fixes seven fields per trajectory step with
`additionalProperties: false`, so `tolerance`, `source` and `evidence_id` cannot be stored
on the step itself. The builder therefore emits one canonical derived evidence item per
step - id `E-TRAJ-<batch_id>-<n>`, statement `TRAJ {<fixed JSON payload>}` - and the
validator re-derives that line from the artifact's own trajectory, so the tolerance
boundary is re-checked on the frozen artifact and not only at the gate. Stated limit: an
editor who rewrites a step AND its trace line can still forge a consistent artifact; the
trace makes the edit visible, it does not make forgery impossible, and no code path accepts
a hand-edited trajectory silently. There is no way to strengthen this without changing the
frozen schema, which this skill must not do.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/grease-batch/scripts/` (or relative `scripts/` from the skill
directory).

### Step 1: Preflight Verification
```bash
python -B skills/grease-batch/scripts/preflight_grease_batch.py <input.json>
```
- Validates the three upstream artifacts, the trajectory step by step, the batch verdict,
  the sample record, the artifact evidence, and the workspace's artifact names.
- Success: prints one `NOTE:` line per judged step, a `NOTE:` line naming route steps the
  trajectory does not record, then a `GATE:` line stating the release outcome, then
  `READY: input can form one BATCH_PRODUCED record and its sample record` (exit 0).
- Failure: output starts with `HOLD: missing or invalid: ...; no artifact generated`
  (exit 1) and nothing is written.

### Step 2: Build Deterministic Artifacts
```bash
python -B skills/grease-batch/scripts/build_batch_artifact.py <input.json> <temporary-file.json>
```
The builder re-runs the preflight checks, strips the input-only trajectory fields, emits
the derived `TRAJ` trace, and assembles both artifacts from `grease_batch_policy.py`:
the batch record at `stage = "BATCH_PRODUCED"` with `project_id` from the charter, and the
sample record beside it (`_tmp_batch.json` -> `_tmp_sample.json`, canonical `batch.json` ->
`sample.json`). It never invents a step, a lot, an operator, a deviation, or a label.

### Step 3: Validate Artifacts
```bash
python -B skills/grease-batch/scripts/validate_batch_artifact.py <temporary-file.json>
```
- Validates the batch against `schemas/batch.schema.json` and the sample beside it against
  `schemas/sample.schema.json`, then recomputes the whole deterministic policy from the
  artifact's own fields: the trace, the tolerance boundary, the verdict legality, the
  release rule, and the canonical decision blocks.
- Success: `PASS: deterministic batch artifact and its sample record conform to the batch
  contract (<sample>.json)` (exit 0).
- A `HOLD` artifact with `batch_verdict: DEVIATED` PASSES: it is a truthful record of a
  deviated batch.

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move the temporary files to the target artifact paths only when Step 3
returns `PASS`.
**Naming rule**: if `batch.json` does not yet exist in the workspace root, commit this
record as `batch.json` and its sample as `sample.json`; otherwise commit them as
`batch-<project_id>-<batch_id>.json` and `sample-<project_id>-<sample_id>.json`. That is,
the first record of each stage type occupies the canonical name (the stage-gate panel uses
this exact name to mark the stage complete), and subsequent records of the same stage are
appended as suffixed names carrying the record id. After the commit, run
`python scripts/check_artifact_naming.py <workspace_root>` and correct any `HOLD` before
proceeding. The checker also enforces that `project.json`'s `stage` stays the constant
`PROJECT_DEFINED` - it is NOT the project's current stage, and must not be advanced.
```bash
# 🔴 CHECKPOINT · STOP: the batch record stops here at BATCH_PRODUCED. Next station: SCREENING_PASSED (grease-screening).
```

---

## 3. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... project_artifact ...` / `... must be stage PROJECT_DEFINED` | 上游章程缺失、schema 不符或未放行 | **STOP**。退回 Stage 1 补齐 `project.json`，不得用手填字段代替上游工件。 |
| `HOLD: ... design_space_artifact ...` / `... must be stage DESIGN_SPACE_DEFINED` / `... must have decision GO` | 设计空间未冻结或未放行 | **STOP**。退回 Stage 6，先让设计空间落盘为 GO。 |
| `HOLD: ... experiment_design_artifact.design_space_reference must equal design_space_artifact.design_space_id` | 试验设计引用的空间与供给的空间不是同一个 | **STOP**。核对第 8 步引用，重取正确的设计空间工件；不得改引用字段凑通。 |
| `HOLD: ... input must contain only the grease-batch input fields; unexpected=... missing=...` | 输入含未知字段或缺少契约字段 | **STOP**。按报错列出的字段名核对；`decision` / `decision_question` 等由策略推导，不得手填。 |
| `HOLD: ... batch.trajectory[N].source is required: a process parameter without provenance is a hard reject` | 工艺参数无来源 | **STOP**。补齐该步的 `source` 与 `evidence_id`；拿不到记录就先不要写这一步，缺就留缺口。 |
| `HOLD: ... batch.trajectory[N].evidence_id ... does not resolve to an evidence item` | 参数引用的证据项不存在 | **STOP**。补上真实的证据项，或把该参数改挂到已有的 OBSERVED 证据上。 |
| `HOLD: ... batch.trajectory[N].deviation must equal actual - setpoint: recorded X, computed Y` | 偏差值与设定/实际不符 | **STOP**。按原始记录重算偏差；不得手改 actual 去凑一个好看的偏差。 |
| `HOLD: ... batch.trajectory[N]: deviation X exceeds the declared tolerance Y but the step is recorded WITHIN` | 超差步被记为合格 | **STOP**。把该步改记 `DEVIATED`；若该步实际在差内，说明 `tolerance` 填错了，按基准工艺重填。 |
| `HOLD: ... batch.batch_verdict VALID is illegal while trajectory[N] is recorded DEVIATED` | 用 VALID 掩盖超差 | **STOP**。改记 `DEVIATED` 并说明处置，或按真实工艺重做该批。 |
| `HOLD: ... batch.batch_verdict DEVIATED must be justified` / `VOID must state why` | 判了超差/作废却没写依据 | **STOP**。把真实异常写进 `batch.anomalies`，或改回与轨迹一致的判语。 |
| `HOLD: ... sample.label.printed_text must contain ...` | 记录的样品号与标签打印内容不一致 | **STOP**。以标签打印机实际打印的内容为准修正记录；不得改标签去凑记录。 |
| `HOLD: ... sample ... batch_reference ... must not be supplied` | 手填了由批次记录绑定的字段 | **STOP**。删除该字段，`batch_reference` / `formula_reference` 由 builder 从批次记录绑定。 |
| `HOLD: ... sample.chain_of_custody must be a non-empty array` | 样品无交接链 | **STOP**。补真实交接记录；没有交接记录的样品不能作为下游测量证据。 |
| `HOLD: ... workspace naming: ...` | 工作区存在面板认不出的工件名 | **STOP**。按 `check_artifact_naming.py` 的报错改名，再重跑 preflight。 |
| `GATE: batch ... batch_verdict=DEVIATED -> decision HOLD; ... sample ... must not leave BATCH_PRODUCED and SCREENING_PASSED must not proceed` | 批次超差 | **保留工件并停在第 9 步**。这是真实结局，不是可修复的错误：先把偏差处置完（判可用则重记判语，判不可用则作废重做），再谈筛测。 |
| `FAIL: ...: the recorded trajectory does not match its derived trace E-TRAJ-...` | 落盘工件被手工改过 | **STOP**。恢复原始轨迹，用 builder 重新生成；不得手改工件。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法损坏 | 检查 `../../schemas/` 与输入文件 JSON 格式。 |

---

## 4. Red Lines & Blacklist (Strict Prohibition)

1. **NO Invented Process Data**: DO NOT invent a setpoint, an actual, a duration, a
   tolerance, an operator, an equipment name, a lot number, or an anomaly to make the
   trajectory look complete. A value nobody recorded stays unrecorded - missing data is a
   GAP, never an invention. The pack's original red line, and the one this stage exists to
   hold.
2. **NO Provenance-Free Parameters**: DO NOT record a step without `source` and a resolving
   `evidence_id`. A parameter without provenance is a hard reject, not a warning.
3. **NO Softened Deviation**: DO NOT record `WITHIN` on a step whose `|deviation|` exceeds
   its declared `tolerance`, and DO NOT declare `batch_verdict: VALID` over a `DEVIATED`
   step. An out-of-tolerance batch is recorded `DEVIATED` and must state whether it is
   voided.
4. **NO Invented Sample Identity**: DO NOT fabricate a `sample_id`, a label text, a
   `printed_at`, a storage location, or a custody handover. The sample id must match the
   label printer's convention and the printed text must be what was printed.
5. **NO Bypass of Preflight**: DO NOT create, move, or touch the output artifacts before
   `preflight_grease_batch.py` has passed. An invalid request produces no artifact at all.
6. **NO Dirty Overwrites**: DO NOT overwrite an existing `batch.json` / `sample.json` on a
   validation failure, and do not commit a second record under a taken canonical name. A
   failed run changes nothing on disk.
7. **NO Soft Guidance Words**: forbidden ambiguous words: "灵活调整", "视情况而定",
   "酌情设置", "可以考虑". Every step carries a concrete setpoint, actual, unit, duration and
   tolerance.
8. **NO Cross-Stage Mutation**: DO NOT screen the sample, allocate a bench slot, run a
   variance judgement, update a model, or advance the state machine here. BATCH_PRODUCED records
   the batch and stops.
9. **NO Synthetic Closure**: DO NOT let a SYNTHETIC batch record authorize stage
   advancement, and never present a synthetic trajectory as a real kettle log.
