---
name: bench-registration
description: Register one evidence-bound test bench (test stand) resource with availability windows, cycle time and per-run cost, and derive its usable slot capacity. Use when user mentions "bench-registration", "台架登记", "台架资源", "台架档期", "availability window", "可用台架位", "bench_slots", "cycle_days", "cost_per_run", or registering Suzhou bench capacity before planning runs.
---

# Bench Registration

Register one test-stand resource as an evidence-bound record: when it is available, how long one run occupies it, and what one run costs. The usable slot capacity is **derived**, never asserted by hand.

Authority schema: `../../schemas/bench.schema.json` (or local `references/bench.schema.json` in deployed bundle). Derived-capacity anchor: `scripts/bench_policy.py::available_bench_slots`.

Authoritative output contract, consumed downstream:
- **WP-04b** (`doe_input.resource_envelope.bench_slots`) reconciles its resource envelope against `available_bench_slots`. End-to-end linkage is a cross-worktree TODO (`tests/lubricant_e2e/test_application_bench.py`); the WP-04b field does not exist in this tree.
- **WP-06** (Stage 13 `APPLIED`) aggregates `bench_id` references as application evidence.

---

## 1. Prerequisites & Gating

Before requesting bench inputs:
- A bench is independent infrastructure and has **no upstream decision artifact requirement**. It MUST NOT be gated on a project stage it does not own.
- Every supplied value MUST carry provenance: the record needs `source` and `evidence_id`, and `cost_per_run` needs its own `source`. Values without provenance are rejected, never defaulted.
- If the bench parameters (Suzhou stand availability/cycle/cost) are unknown, record the record with `evidence.status = "ASSUMED"` and keep every unverified number explicitly marked — DO NOT invent dates, cycle times, or costs.

---

## 2. Input Specification (contract in)

Input is a single JSON object containing only `bench`:

```json
{
  "bench": {
    "bench_id": "BENCH-SZ-01",
    "project_reference": "WGO-001",
    "bench_name": "Suzhou grease bench 1",
    "location": "Suzhou",
    "availability_window": [
      { "window_id": "W-1", "start": "2026-01-01", "end": "2026-01-10" },
      { "window_id": "W-2", "start": "2026-02-01", "end": "2026-02-14", "reserved_days": 2 }
    ],
    "cycle_days": 3,
    "cost_per_run": { "value": 1200, "unit": "CNY/run", "source": "Synthetic bench quote" },
    "source": "Synthetic bench registration spec",
    "evidence_id": "EV-BENCH-001",
    "evidence_scope": "SYNTHETIC",
    "evidence": [
      { "evidence_id": "EV-BENCH-001", "statement": "Synthetic bench parameters supplied for contract validation only; not a booked or qualified capacity.", "source": "Synthetic bench fixture", "status": "ASSUMED" }
    ]
  }
}
```

### Field Invariants (contract in)
- Identity: `bench_id`, `project_reference`, `bench_name`, `location` are all required non-empty strings.
- Availability windows: `availability_window` is non-empty; each window requires `window_id`, `start`, `end` as ISO dates `YYYY-MM-DD` with `start <= end`; optional `reserved_days` is a non-negative integer (maintenance/blackout). `window_id` values must be distinct.
- Cycle time: `cycle_days` is a strictly positive finite number (wall-clock days one run occupies the bench).
- Cost: `cost_per_run` requires non-negative numeric `value`, non-empty `unit`, and non-empty `source`.
- Provenance (hard): `source` and `evidence_id` are required; a record without either is rejected.
- Evidence scope: `evidence_scope` is `SYNTHETIC` or `PHYSICAL`. A SYNTHETIC bench record must never be presented as booked, qualified, or release capacity.
- Derived field: **DO NOT supply `available_bench_slots`.** It is computed from `availability_window` and `cycle_days`; supplying it is a hard reject.
- GAP: `evidence` must be non-empty and contain no `GAP` status.

### Derived Capacity Rule (the single conversion)
```
available_bench_slots = Σ over availability_window
                        floor( usable_days(window) / cycle_days )
usable_days(window)   = max( (end - start).days + 1 - reserved_days , 0 )
```
Example: W-1 = 10 usable days, W-2 = 12 usable days, `cycle_days = 3` → `floor(10/3) + floor(12/3) = 3 + 4 = 7` slots.

---

## 3. Deterministic Execution Workflow

All scripts reside in `skills/bench-registration/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/bench-registration/scripts/preflight_bench_registration.py <input.json>
```
- Success: prints `READY: input can register one bench record only` then `DERIVED: available_bench_slots=<N>` (exit 0).
- Failure: output starts with `HOLD: missing or invalid: ...; no artifact generated` (exit 1).

### Step 2: Build Deterministic Artifact
```bash
python skills/bench-registration/scripts/build_bench_artifact.py <input.json> <temporary-file.json>
```
The builder computes `available_bench_slots` and generates canonical decision fields; it sets `project_id = project_reference` and `stage = "DRAFT"` (a bench is a resource, not a chain stage).

### Step 3: Validate Artifact
```bash
python skills/bench-registration/scripts/validate_bench_artifact.py <temporary-file.json>
```
- Recomputes `available_bench_slots` and asserts it equals the stored value; also asserts the deterministic decision fields.
- Success: `PASS: deterministic bench artifact conforms to the bench contract` (exit 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3 returns `PASS`.
```bash
# 🔴 CHECKPOINT · STOP: the bench record stops here. It is registered infrastructure.
# Do NOT book capacity, reserve runs, emit a DOE resource envelope, advance the state machine,
# or claim the bench is qualified / available for release.
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... bench must contain only the bench-registration input fields; ... unexpected=... missing=...` | 输入含未知字段或有字段缺失 | **STOP**。按报错列出的一侧字段名核对，只保留契约字段。 |
| `HOLD: ... available_bench_slots is derived by bench_policy and must not be supplied` | 手工提供了派生字段 | **STOP**。删除该字段，可用台架位由 preflight/build 自动折算。 |
| `HOLD: ... bench.availability_window[N].start must be an ISO date YYYY-MM-DD` | 档期日期格式非法或为空 | **STOP**。改为 `YYYY-MM-DD`，不得猜测档期。 |
| `HOLD: ... bench.availability_window[N].start must be <= end` | 档期起止倒置 | **STOP**。核对真实档期后重填。 |
| `HOLD: ... bench.cycle_days must be a positive number` | 单次占用周期缺失或非正 | **STOP**。要求提供正数 cycle_days，不使用默认值。 |
| `HOLD: ... bench.cost_per_run.source` | 单次成本无来源 | **STOP**。输出缺失来源，要求补齐报价出处。 |
| `HOLD: ... bench.evidence contains GAP` | 证据链存在未解缺口 | **STOP**。保持 HOLD，生成 gap 诊断，等待证据补足。 |
| `FAIL: available_bench_slots must equal the derived N` | 落盘工件被杀手工改过 | **STOP**。删除手改值，用 builder 重新生成。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法损坏 | 检查 `../../schemas/` 与输入文件 JSON 格式。 |

---

## 5. Red Lines & Blacklist (Strict Prohibition)

1. **NO Invented Bench Data**: DO NOT invent availability dates, cycle times, or per-run costs. Unknown values stay `ASSUMED` with an explicit source, never fabricated.
2. **NO Hand-Set Capacity**: DO NOT write `available_bench_slots` by hand. It is derived by `bench_policy.available_bench_slots` and re-checked on validation.
3. **NO Capacity Booking**: DO NOT reserve slots, book runs, or assert the bench is free. Registration only records supplied availability.
4. **NO Qualification Claims**: DO NOT claim the bench is qualified, calibrated, or release-ready from this record.
5. **NO Cross-Stage Spillover**: DO NOT emit a DOE resource envelope, run DOE, build experiment artifacts, or advance the state machine in this skill.
6. **NO Synthetic Closure**: DO NOT let a SYNTHETIC bench record reach `CLOSED` or be presented as physical capacity.
7. **NO Bypass of Preflight**: DO NOT create the output artifact without running `preflight_bench_registration.py` first.
8. **NO Soft Guidance Words**: Forbidden ambiguous words: "灵活调整", "视情况而定", "酌情设置", "可以考虑". All values must be concrete numbers with verifiable metadata.
