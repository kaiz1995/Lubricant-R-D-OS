---
name: bench-registration
description: Register one evidence-bound test bench (test stand) resource with availability windows, cycle time and per-run cost, and derive its usable slot capacity. Also opens the inner-loop bench campaign over registered benches (campaign.json, stage CAMPAIGN_OPENED). Use when user mentions "bench-registration", "台架登记", "台架资源", "台架档期", "availability window", "可用台架位", "bench_slots", "cycle_days", "cost_per_run", "campaign", "战役", "内环", "iterations", "pairing_design", or registering Suzhou bench capacity before planning runs.
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
# 🔴 CHECKPOINT · STOP: the bench record stops here at DRAFT (it is registered infrastructure, not a chain stage).
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

---

# Part B — CAMPAIGN_OPENED: the inner-loop carrier

The skill carries a second stage, and it is the same bottleneck seen from the other side. `BENCH_RESOURCE_REGISTERED` (Part A) records *that the stand exists*; `CAMPAIGN_OPENED` records *the loop that will spend it*. The router maps the stage here on the `PRECISION_GREASE_DEV` route only (`skills/lubricant-rd-agent/scripts/route_step.py`, `ROUTE_TABLE`), so the six oil routes never reach this part.

Authority schema: `../../schemas/campaign.schema.json`. Shared policy: `scripts/campaign_policy.py`.

## 6. Input Specification (campaign contract in)

```json
{
  "project_artifact": "../precision-grease/project-active.json",
  "bench_artifacts": ["bench.json"],
  "campaign": {
    "campaign_id": "CMP-PGD-B1-001",
    "project_reference": "PGD-B1-001",
    "bench_references": ["BENCH-PGD-B1-01"],
    "current_iteration": 2,
    "iterations": [
      { "iteration": 1, "samples": ["SMP-PGD-B1-R1A", "SMP-PGD-B1-R1B"], "stop_state": "CONTINUE",
        "screening_reference": "SCR-PGD-B1-R1", "variance_reference": "VAR-PGD-B1-R1",
        "model_reference": null, "next_batch_reference": "NEXT-PGD-B1-R1",
        "bench_test_references": ["BT-PGD-B1-R1A-1", "BT-PGD-B1-R1B-1"] }
    ],
    "pairing_design": { "paired": true, "description": "A/B pair runs in the same round and is swapped in the next round." },
    "evidence_scope": "SYNTHETIC",
    "source": "Synthetic campaign-registration fixture",
    "evidence_id": "EV-CMP-PGD-B1-001",
    "evidence": [
      { "evidence_id": "EV-CMP-PGD-B1-001", "statement": "...", "source": "...", "status": "ASSUMED" }
    ]
  }
}
```

### Field Invariants (campaign contract in)
- Upstreams (hard): `project_artifact` and `bench_artifacts` are paths (relative to the request file or absolute) to built artifacts. The project charter must be schema-valid and belong to `project_reference`; every bench must be schema-valid, belong to the same project, and be cited by `bench_references`. A supplied bench that no reference cites is an omission; a reference that resolves to no supplied bench is a provenance hole.
- Identity: `campaign_id`, `project_reference`, `source`, `evidence_id` are required non-empty strings.
- `bench_references`: non-empty array of distinct bench ids, every one of them registered and supplied.
- `max_iterations`: optional positive integer. **If absent it is read from `contracts/state-machine.json` (`max_iterations`, currently 12) and the artifact writes that provenance into `result` and into the appended evidence item `E-CONTRACT-CAMPAIGN-MAX-ITERATIONS`; no other number is ever invented.** An absent cap with an unreadable contract is a HOLD.
- `current_iteration`: positive integer, 1-based. It must not exceed `max_iterations` and must not sit before the rounds already recorded.
- `iterations`: non-empty array, oldest first, one entry per round actually run; `iteration` numbering is 1-based and contiguous; every entry needs `samples` (non-empty) and `stop_state` (one of `CONTINUE`, `GOAL_MET`, `NO_NEW_INFORMATION`, `RESOURCE_EXHAUSTED`, `PIVOT`, `KILL`). **Only `CONTINUE` authorizes another round**, so no round may follow one that ended otherwise, and the count may not exceed `max_iterations`.
- `pairing_design`: exactly `paired` (boolean) and `description` (non-empty). The paired A/B design is the one this project prefers: at a fixed sigma, pairing buys more resolution than trying to measure sigma precisely.
- Evidence: non-empty, no `GAP`; the reserved id `E-CONTRACT-CAMPAIGN-MAX-ITERATIONS` may not be supplied by the caller.
- A `SYNTHETIC` bench record must never back a `PHYSICAL` campaign (Part A red line 6).

### Decision rule (deterministic)
`decision` is `GO` exactly when no evidence item is `GAP`, `current_iteration <= max_iterations`, and the newest recorded round ended `CONTINUE`; otherwise `HOLD`. A campaign whose newest round ended `GOAL_MET` / `NO_NEW_INFORMATION` / `RESOURCE_EXHAUSTED` / `PIVOT` / `KILL` is still recorded truthfully, with `HOLD`: the record does not authorize another bench round. The validator re-derives the whole block and refuses a hand-edited artifact.

## 7. Deterministic Execution Workflow (campaign)

### Step 1: Preflight Verification
```bash
python skills/bench-registration/scripts/preflight_campaign_registration.py <input.json>
```
- Success: prints `READY: input can open one bench campaign at stage CAMPAIGN_OPENED`, then `NOTE: max_iterations=<N> defaulted from contracts/state-machine.json` when the cap was defaulted, then one `DERIVED: bench <id> available_bench_slots=<N>` line per supplied bench (the value is *called* from `bench_policy`, never recomputed here). A cap above the registered slots is reported with a `NOTE` and is not rejected — a registration records only the availability it was given. Exit 0.
- Failure: `HOLD: missing or invalid: ...; no artifact generated` (exit 1).

### Step 2: Build Deterministic Artifact
```bash
python skills/bench-registration/scripts/build_campaign_artifact.py <input.json> <temporary-file.json>
```
The builder sets `stage = "CAMPAIGN_OPENED"` and `project_id = project_reference`, appends the contract-default provenance item when (and only when) it defaulted the cap, and generates the canonical decision block.

### Step 3: Validate Artifact
```bash
python skills/bench-registration/scripts/validate_campaign_artifact.py <temporary-file.json>
```
- Structural: validates against `campaign.schema.json` with `common.schema.json` in the registry.
- Semantic: re-derives the cross-field rule, the "only CONTINUE authorizes another round" rule, the provenance item and the decision block; also refuses any extra property.
- Success: `PASS: deterministic campaign artifact conforms to the campaign contract` (exit 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3 returns `PASS`.
```bash
# 🔴 CHECKPOINT · STOP: the campaign record stops here at CAMPAIGN_OPENED. It opens the inner loop; next station: EXPERIMENT_DESIGNED (doe-design). It does not run a round.
# Do NOT book bench slots, reserve capacity, emit a DOE envelope, advance the state machine,
# or claim any round's outcome that was not supplied.
```

## 8. Failure Modes & Fallback Recovery (campaign, Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... unexpected=... missing=...` | 请求含未知字段或缺少必填字段（如 `pairing_design`） | **STOP**。按报错列出的一侧字段名核对，只保留契约字段。 |
| `HOLD: ... campaign.current_iteration N must not exceed max_iterations M` | 跨字段规则被破坏（JSON Schema 无法结构化表达，由 validator 执行） | **STOP**。核对 max_iterations 与 current_iteration，不得抬高上限去迁就计数器。 |
| `HOLD: ... campaign.iterations[i].stop_state must be CONTINUE` | 已停止的轮次之后又记录了新轮次 | **STOP**。只有 CONTINUE 授权下一轮；核对真实轮次记录。 |
| `HOLD: ... evidence_id E-CONTRACT-CAMPAIGN-MAX-ITERATIONS is reserved` | 调用方伪造契约默认值的来源标记 | **STOP**。删除该证据项，让 builder 自行追加。 |
| `HOLD: ... is SYNTHETIC and may not back a PHYSICAL campaign` | 合成台架被当作物理产能 | **STOP**。改用已登记的物理台架，或把 campaign 标为 SYNTHETIC。 |
| `HOLD: ... resolves to no supplied bench artifact` | 引用了未登记的台架 / 上游未提供 | **STOP**。先登记台架（Part A），再把它的 `bench.json` 作为上游传入。 |
| `HOLD: ... max_iterations is absent and contracts/state-machine.json is absent/cannot be read` | 台次上限缺失且契约不可读 | **STOP**。修复契约路径或显式提供 `max_iterations`；不得凭空取数。 |
| `FAIL: max_iterations N carries the E-CONTRACT-CAMPAIGN-MAX-ITERATIONS provenance, but contracts/state-machine.json publishes M` | 落盘工件被手改（改了上限却留着来源标记） | **STOP**。删除手改值，用 builder 重新生成。 |
| `FAIL: decision must equal the deterministic campaign policy` | 落盘工件的判定被手改（如把 HOLD 改成 GO） | **STOP**。用 builder 重新生成。 |

## 9. Red Lines & Blacklist (campaign side)

1. **NO Invented Cap**: `max_iterations` is the caller's value or the contract's published one, with its provenance recorded. Never a third number.
2. **NO Silent Loop Extension**: a round that ended anything but `CONTINUE` closes the loop in this record; do not open another round behind it and do not soften the decision.
3. **NO Capacity Claim**: a campaign records no capacity, books no slot and reserves no run; `available_bench_slots` stays on the bench record.
4. **NO Unregistered Bench**: every `bench_references` entry must resolve to a supplied, schema-valid bench of the same project.
5. **NO Synthetic Closure**: a SYNTHETIC bench never backs a PHYSICAL campaign.
6. **NO Bypass of Preflight**: DO NOT create the output artifact without running `preflight_campaign_registration.py` first.
