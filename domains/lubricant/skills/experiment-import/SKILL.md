---
name: experiment-import
description: Import one PHYSICAL experiment record with DOE-point and execution provenance at EXPERIMENT_RUNNING, and one bench run at BENCH_TESTED on the PRECISION_GREASE_DEV route; preflight verifies 6 upstream artifacts, raw DOE SHA-256 digest, calibration provenance, and the censoring discipline. Use when user mentions "experiment-import", "实验导入", "实验数据接入", "台架数据摄取", "台架实测", "删失", "物理实验记录", or advancing to Stage 6 in lubricant R&D.
---

# Experiment Import (Stage 6 · and Stage 11 on the grease route)

Import one PHYSICAL experiment record with strict execution and DOE-point provenance at `EXPERIMENT_RUNNING` for the Lubricant R&D Domain Pack.
This is a raw experimental record ingestion and provenance lock, NOT a statistical regression or performance conclusion.

**Two artifact kinds, one skill.** The same gate also produces the `bench_test` record of the
`PRECISION_GREASE_DEV` inner loop at `BENCH_TESTED` (step 11). The bench entry point is
selected only when the request carries a `bench_test` record and no `experiment` record, so
every experiment request keeps exactly the behaviour it had; and it is itself gated on the
supplied charter routing as `PRECISION_GREASE_DEV`, because `BENCH_TESTED` is on no oil
route. See §5.

Authority schemas: `../../schemas/experiment.schema.json` for the experiment path and
`../../schemas/bench_test.schema.json` for the bench path (or the local
`references/*.schema.json` in the deployed bundle). The censoring discipline of the bench
path lives in `scripts/bench_test_policy.py`, which the preflight, the builder and the
validator all share.

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

## 2. Deterministic Execution Workflow (experiment path)

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

## 5. Bench-Test Path (Stage 11 · `BENCH_TESTED`, `PRECISION_GREASE_DEV` only)

The bench is the only source of real performance evidence for a grease and the scarcest
resource of the campaign (about two positions per round, roughly 30 days per round), so the
quality of this record decides whether the inner loop can converge. This path is a **record
of one run**, not a verdict: whether the round's difference is real is decided at Step 12
(variance-assessment).

### Input (a `bench_test` record; the `experiment` record must be absent)
```json
{
  "project_artifact": "project.json",
  "evidence_scope": "PHYSICAL",
  "evidence": [
    {
      "evidence_id": "E-BT-001",
      "statement": "Bench log BL-001 records the protocol version, the fixed setpoints, the ambient conditions and the end of the 10 h observation window.",
      "source": "Bench log BL-001",
      "status": "OBSERVED"
    }
  ],
  "bench_test": {
    "run_id": "RUN-PG-001",
    "bench_reference": "BENCH-SZ-01",
    "batch_reference": "BAT-PG-001",
    "sample_reference": "SMP-PG-001",
    "protocol_version": "BENCH_PROTOCOL_V2",
    "setpoints": ["load 1.5 kN", "speed 1200 rpm", "temperature 80 degC"],
    "environment": { "temperature_c": 23.5, "humidity_percent": 45.0 },
    "raw_record_reference": "RAW-PG-001",
    "event_occurred": false,
    "event_time": null,
    "censoring_type": "RIGHT",
    "stop_reason": "ADMINISTRATIVE_10H_END",
    "anomalies": [],
    "campaign_iteration": 1
  }
}
```
The input must contain exactly `project_artifact`, `bench_test`, `evidence_scope` and
`evidence`. The artifact-level fields (`schema_version`, `artifact_type`, `project_id`,
`stage`, `decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`,
`decision`, `next_action`) are DERIVED by `bench_test_policy`; supplying any of them is a
hard reject. `project.json` must be `PROJECT_DEFINED`, `ACTIVE`, `decision: GO`, and
`project_type: PRECISION_GREASE_DEV`.

### The censoring discipline (red line 3: 删失不得当终点)
Provenance: `WGO_001_S1_BENCH_METHOD_QUALIFICATION_PLAN.md` — "right-censored 10h
observations **NEVER** treated as `event_time=10h`". A run that reached the end of its
window without an event tells us only that no event happened *inside* the window; the
window length is a censoring time, not an end-point. Once such a value is written as an
end-point, the variance estimate is wrong and every downstream conclusion is void.

```
1. A censoring time is never an end-point   : event_occurred=false forces event_time=null,
                                              whatever the censoring_type says
2. A censored run must declare why it stopped: censoring_type != NONE requires a non-empty
                                              stop_reason; an unexplained stop is not an observation
3. An event-free run must also say why       : stricter than the schema -- censoring_type NONE
                                              with event_occurred=false still needs a stop_reason
4. An event claim must carry its time        : event_occurred=true requires a numeric event_time >= 0
```
Rules 1 and 2 mirror the two `if/then` rules of `schemas/bench_test.schema.json`; rules 3
and 4 are this policy's own and are stricter on purpose (the schema only forces
`stop_reason` for a non-`NONE` censoring type). A run that produced no event and declares no
censoring would otherwise be the one record that looks completed while carrying no
explanation.

### Workflow
```bash
python -B skills/experiment-import/scripts/preflight_experiment_import.py <input.json>
# NOTE: one line per run stating the observation exactly as recorded, plus the discipline
# GATE: the step-11 outcome, or HOLD when the record contradicts the censoring discipline
# READY: bench run can be recorded as one BENCH_TESTED observation, censoring included   (exit 0)

python -B skills/experiment-import/scripts/build_bench_test_artifact.py <input.json> <temporary-file.json>
# BUILT: <path> stage=BENCH_TESTED run_id=...   +   OBSERVATION: censoring_type=... event_time=...

python -B skills/experiment-import/scripts/validate_bench_test_artifact.py <temporary-file.json>
# PASS: deterministic bench_test artifact conforms to the BENCH_TESTED contract and the censoring discipline
```
Then commit the temporary file as `bench_test.json` (first record) or
`bench_test-<project_id>-<run_id>.json` (subsequent records), and run
`python scripts/check_artifact_naming.py <workspace_root>`.
```bash
# 🔴 CHECKPOINT · STOP: Stage 11 stops here at BENCH_TESTED. Pass to Stage 12 (variance-assessment).
```

### Bench-path failure modes

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... censored observation must not carry an event_time: ... recorded event_occurred=True event_time=10` | 把右删失的窗口长度记成了终点值（N9） | **STOP**。按原始记录改回 `event_occurred: false` + `event_time: null`，并写明 `stop_reason`；不得把删失时间当观测结果使用。 |
| `HOLD: ... censored observation without a stop_reason is refused: an unexplained stop is not an observation` | 删失未说明停机原因 | **STOP**。补齐 `stop_reason`（如 `ADMINISTRATIVE_10H_END`）；没有停机原因的记录不算一次观测。 |
| `HOLD: ... the run produced no event (event_occurred=false) and declares no censoring (censoring_type NONE) without a stop_reason` | 无事件又未声明删失，也没有停机原因 | **STOP**。说明该 run 为何结束（如 `ran to the end of the protocol window without the defined event`）。 |
| `HOLD: ... event_occurred=true requires a numeric event_time >= 0` | 声称发生事件却没记事件时间 | **STOP**。补真实事件时间；拿不到就先按删失记录，不得猜一个数。 |
| `HOLD: ... bench_test.bench_reference is required: every bench run must hang its run id, its bench, its batch, its sample, the frozen protocol version and the raw record it was distilled from` | 台架溯源字段缺失（无台架编号/批次/样品/协议版本/原始记录） | **STOP**。按台架日志补齐；第 11 步放行判据就是这些引用齐备。 |
| `HOLD: ... project_artifact.project_type is 'COST_DOWN': the bench run is the PRECISION_GREASE_DEV inner loop (step 11); BENCH_TESTED is on no oil route` | 在非精密脂路线上请求台架实测 | **STOP**。`BENCH_TESTED` 只属于 `PRECISION_GREASE_DEV` 路线；六条油路线没有这一步。 |
| `FAIL: ... the recorded trajectory ...` / `FAIL: bench_test.schema.json: False was expected (path ['event_occurred'])` | 落盘工件被手工改过（删失时间写回 `event_time`） | **STOP**。恢复原始观测，用 builder 重新生成；不得手改工件。 |

---

## 6. Strict Blacklist (Prohibitions)

1. **NO Synthetic Data Entry**: NEVER allow synthetic, simulated, or predicted runs to enter as experimental evidence.
2. **NO Statistical Fitting**: DO NOT compute regression equations, p-values, or response surface maps in Stage 6.
3. **NO Performance Conclusions**: DO NOT declare formula qualification or compliance before Stage 7 & 8 analysis.
4. **NO Dirty Overwrites**: DO NOT overwrite existing experiment records with mismatched `project_id` or `experiment_id`.
5. **NO Censoring Recorded As An End-Point**: DO NOT write an observation window length, a censoring time, or any
   substituted value into `event_time` on a run that produced no event. A right-censored run is
   recorded as `event_occurred: false` with `event_time: null` and a declared `stop_reason`.
   This is the pack's red line 3 (删失不得当终点) and the reason this path exists.
6. **NO Unexplained Stop**: DO NOT record a censored or event-free run without a `stop_reason`.
   An unexplained stop is not an observation, and administrative censoring must never be
   presented silently as a completed run.
7. **NO Invented Bench Data**: DO NOT invent a setpoint, an environment reading, a stop reason, an
   anomaly, or a bench/batch/sample reference to make a run look complete. A value nobody
   recorded stays unrecorded - missing data is a GAP, never an invention.
8. **NO Cross-Stage Mutation**: DO NOT compute a variance component, a power figure, or a
   replicate-consistency verdict here. Stage 11 records the run and stops; Step 12 judges it.
   The run's `decision` is `UNDECIDED` for exactly this reason.

