---
name: bench-registration
description: Register one evidence-bound test bench (test stand) resource with availability windows, cycle time and per-run cost, derive its usable slot capacity, and open the bench's inner-loop round plan in the same record (bench.json, stage BENCH_RESOURCE_REGISTERED) — the paired round ledger with its iteration cap. Use when user mentions "bench-registration", "台架登记", "台架资源", "台架档期", "availability window", "可用台架位", "bench_slots", "cycle_days", "cost_per_run", "campaign", "内环", "iterations", "pairing_design", or registering Suzhou bench capacity before planning runs.
---

# Bench Registration

Register one test-stand resource as an evidence-bound record — when it is available, how long one run occupies it, and what one run costs — and open the inner-loop round plan that will spend it: the paired rounds already recorded, how each one ended, and the iteration cap that bounds them. The usable slot capacity is **derived**, never asserted by hand.

This skill carries **one stage and one artifact**. Contract v1.0.0 merged the former pair (`BENCH_RESOURCE_REGISTERED` + the campaign opening) into the single record `bench.json` at stage `BENCH_RESOURCE_REGISTERED`: the registration of shared test-stand capacity and the round plan the inner loop spends it on live in the same record. The router maps the stage here on the `PRECISION_GREASE_DEV` route only (`skills/lubricant-rd-agent/scripts/route_step.py`, `ROUTE_TABLE`), so the six oil routes never reach this skill.

Authority schema: `../../schemas/bench.schema.json` (or local `references/bench.schema.json` in deployed bundle). Shared deterministic policy: `scripts/bench_policy.py` — the single module the preflight, the builder and the validator all call.

Authoritative output contract, consumed downstream:
- **WP-04b** (`doe_input.resource_envelope.bench_slots`) reconciles its resource envelope against `available_bench_slots`. End-to-end linkage is a cross-worktree TODO (`tests/lubricant_e2e/test_application_bench.py`); the WP-04b field does not exist in this tree.
- **WP-06** (Stage 13 `APPLIED`) aggregates `bench_id` references as application evidence.
- Downstream variance/model records point their `campaign_reference` at this record's `campaign_id`, and their `campaign_iteration` at the round the ledger stands at.

---

## 1. Prerequisites & Gating

Before requesting bench inputs:
- A bench is independent infrastructure and has **no upstream decision artifact requirement**. It MUST NOT be gated on a project stage it does not own. After the merge there are no upstream artifact paths at all: the bench block IS the registration, and its `project_reference` is the one project source the round plan shares.
- Every supplied value MUST carry provenance: the bench half needs `source` and `evidence_id`, and `cost_per_run` needs its own `source`; the round-plan half needs its own `source` and `evidence_id`. Values without provenance are rejected, never defaulted.
- If the bench parameters (Suzhou stand availability/cycle/cost) are unknown, record the record with `evidence.status = "ASSUMED"` and keep every unverified number explicitly marked — DO NOT invent dates, cycle times, or costs.
- If the iteration cap is unknown, omit `max_iterations` in the campaign block: it is read from `contracts/state-machine.json` (currently 12) and that provenance is recorded; DO NOT pick another number.

---

## 2. Input Specification (contract in)

Input is a single JSON object containing exactly two keys, `bench` and `campaign`:

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
  },
  "campaign": {
    "campaign_id": "CMP-WGO-001",
    "current_iteration": 1,
    "iterations": [],
    "pairing_design": { "paired": true, "description": "A/B pair runs in the same round and is swapped in the next round." },
    "evidence_scope": "SYNTHETIC",
    "source": "Synthetic round-plan request",
    "evidence_id": "EV-CMP-WGO-001",
    "evidence": [
      { "evidence_id": "EV-CMP-WGO-001", "statement": "Synthetic round-plan request supplied for contract validation only.", "source": "Synthetic campaign fixture", "status": "ASSUMED" }
    ]
  }
}
```

### Field Invariants (bench half, contract in)
- Identity: `bench_id`, `project_reference`, `bench_name`, `location` are all required non-empty strings.
- Availability windows: `availability_window` is non-empty; each window requires `window_id`, `start`, `end` as ISO dates `YYYY-MM-DD` with `start <= end`; optional `reserved_days` is a non-negative integer (maintenance/blackout). `window_id` values must be distinct.
- Cycle time: `cycle_days` is a strictly positive finite number (wall-clock days one run occupies the bench).
- Cost: `cost_per_run` requires non-negative numeric `value`, non-empty `unit`, and non-empty `source`.
- Provenance (hard): `source` and `evidence_id` are required; a record without either is rejected.
- Evidence scope: `evidence_scope` is `SYNTHETIC` or `PHYSICAL`. A SYNTHETIC bench record must never be presented as booked, qualified, or release capacity.
- Derived field: **DO NOT supply `available_bench_slots`.** It is computed from `availability_window` and `cycle_days`; supplying it is a hard reject.
- GAP: `evidence` must be non-empty and contain no `GAP` status.

### Field Invariants (round-plan half, contract in)
- Identity: `campaign_id`, `source`, `evidence_id` are required non-empty strings.
- `project_reference` is **optional** in the campaign block: after the merge the record has exactly one project source, `bench.project_reference`. If supplied it MUST equal `bench.project_reference` (preflight-cross-checked), never a second opinion.
- `evidence_scope` MUST equal `bench.evidence_scope` (preflight-cross-checked): the artifact carries one scope, taken from the bench half.
- `max_iterations`: optional positive integer. **If absent it is read from `contracts/state-machine.json` (`max_iterations`, currently 12) and the artifact records that provenance in `result` and in the appended evidence item `E-CONTRACT-CAMPAIGN-MAX-ITERATIONS`; no other number is ever invented.** An absent cap with an unreadable contract is a HOLD.
- `current_iteration`: positive integer, 1-based. It must not exceed `max_iterations` and it IS the round the ledger stands at (validator-enforced, not structurally expressible): `1` while the ledger is empty (the plan is opened *before* round 1 runs — W0), `len(iterations) + 1` when the newest recorded round ended `CONTINUE` (that round opened the next one — W1), and `len(iterations)` when the newest recorded round ended otherwise (the ledger closed at that round — W2).
- `iterations`: array of round entries, oldest first, **legitimately empty until round 1's boundary is reached** (the plan is opened before any round has run, so W0 authorizes the first round and the decision is `GO`); `iteration` numbering is 1-based and contiguous; every entry needs `samples` (non-empty) and `stop_state` (one of `CONTINUE`, `GOAL_MET`, `NO_NEW_INFORMATION`, `RESOURCE_EXHAUSTED`, `PIVOT`, `KILL`). **Only `CONTINUE` authorizes another round**, so no round may follow one that ended otherwise, and the count may not exceed `max_iterations`.
- `model_reference` / `next_batch_reference` are **exit-round only** (E2=B): they are written only on the round that exits the inner loop, so every round that looped back (`stop_state == CONTINUE`) must carry `null` for both. `screening_reference` / `variance_reference` are per-round and carry no such rule.
- `pairing_design`: exactly `paired` (boolean) and `description` (non-empty). The paired A/B design is the one this project prefers: at a fixed sigma, pairing buys more resolution than trying to measure sigma precisely.
- Evidence: non-empty, no `GAP`; the reserved id `E-CONTRACT-CAMPAIGN-MAX-ITERATIONS` may not be supplied by the caller.

### Derived Capacity Rule (the single conversion)
```
available_bench_slots = Σ over availability_window
                        floor( usable_days(window) / cycle_days )
usable_days(window)   = max( (end - start).days + 1 - reserved_days , 0 )
```
Example: W-1 = 10 usable days, W-2 = 12 usable days, `cycle_days = 3` → `floor(10/3) + floor(12/3) = 3 + 4 = 7` slots.

### Decision rule (deterministic)
`decision` is `GO` exactly when no supplied evidence item is `GAP` (either half), otherwise `HOLD`: the artifact answers one question — whether the input is sufficient to register the bench and open its round plan. The ledger's own legality (cap, W0/W1/W2 position, only-`CONTINUE`, exit-round-only references) is enforced separately by the cross-field validators, and `result` reports the slot count and the ledger state so both readings are visible on the artifact. The validator re-derives the whole block and refuses a hand-edited artifact.

---

## 3. Deterministic Execution Workflow

All scripts reside in `skills/bench-registration/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/bench-registration/scripts/preflight_bench_registration.py <input.json>
```
- Success: prints `READY: input can register one bench record and open its round plan at stage BENCH_RESOURCE_REGISTERED`, then `DECISION: GO (the builder will record exactly this verdict)` — the preflight calls the same policy function as the builder and the validator, so the three stages can never disagree — then `DERIVED: available_bench_slots=<N>`, then a `NOTE:` line when the cap was defaulted from the contract, a `NOTE:` line when `max_iterations` exceeds the registered slots (reported, never rejected — a registration records only the availability it was given), and a `NOTE:` line with the ledger state (rounds recorded / round standing at). Exit 0.
- Failure: output starts with `HOLD: missing or invalid: ...; no artifact generated` (exit 1).

### Step 2: Build Deterministic Artifact
```bash
python skills/bench-registration/scripts/build_bench_artifact.py <input.json> <temporary-file.json>
```
The builder computes `available_bench_slots`, merges the two blocks into the one `bench.json` shape (`stage = "BENCH_RESOURCE_REGISTERED"`, `project_id = bench.project_reference`, artifact-level `source`/`evidence_id`/`evidence_scope` from the bench half, `evidence` = bench.evidence + campaign.evidence with bench first), appends the contract-default provenance item when (and only when) it defaulted the cap, and generates the canonical decision block. It computes no capacity of its own beyond `bench_policy`.

### Step 3: Validate Artifact
```bash
python skills/bench-registration/scripts/validate_bench_artifact.py <temporary-file.json>
```
- Structural: validates against `bench.schema.json` with `common.schema.json` in the registry.
- Semantic: recomputes `available_bench_slots` and asserts it equals the stored value; re-derives the cross-field ledger rule, the "only CONTINUE authorizes another round" and exit-round-only (E2=B) rules, the contract-default provenance item and the merged decision block; also refuses any extra property.
- Success: `PASS: deterministic merged bench artifact conforms to the bench contract` (exit 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3 returns `PASS`.
```bash
# 🔴 CHECKPOINT · STOP: the merged record stops here at BENCH_RESOURCE_REGISTERED — the bench is registered and its
# round plan is open; next station: EXPERIMENT_DESIGNED (doe-design). It does not run a round.
# Do NOT book bench slots, reserve capacity, emit a DOE envelope, advance the state machine,
# or claim any round's outcome that was not supplied.
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... input must contain only ['bench', 'campaign']` | 请求键不合法（缺块或含上游工件键） | **STOP**。只保留 `bench` 与 `campaign` 两块；上游工件路径已随契约合并取消。 |
| `HOLD: ... bench must contain only the bench-registration input fields; ... unexpected=... missing=...` | bench 块含未知字段或字段缺失 | **STOP**。按报错列出的一侧字段名核对，只保留契约字段。 |
| `HOLD: ... available_bench_slots is derived by bench_policy and must not be supplied` | 手工提供了派生字段 | **STOP**。删除该字段，可用台架位由 preflight/build 自动折算。 |
| `HOLD: ... bench.availability_window[N].start must be an ISO date YYYY-MM-DD` | 档期日期格式非法或为空 | **STOP**。改为 `YYYY-MM-DD`，不得猜测档期。 |
| `HOLD: ... bench.availability_window[N].start must be <= end` | 档期起止倒置 | **STOP**。核对真实档期后重填。 |
| `HOLD: ... bench.cycle_days must be a positive number` | 单次占用周期缺失或非正 | **STOP**。要求提供正数 cycle_days，不使用默认值。 |
| `HOLD: ... bench.cost_per_run.source` | 单次成本无来源 | **STOP**。输出缺失来源，要求补齐报价出处。 |
| `HOLD: ... campaign must contain the campaign-registration request fields; ... missing=...` | 轮次计划块含未知字段或缺少必填字段（如 `pairing_design`） | **STOP**。按报错列出的一侧字段名核对，只保留契约字段。 |
| `HOLD: ... campaign.current_iteration N must not exceed max_iterations M` | 跨字段规则被破坏（JSON Schema 无法结构化表达，由 validator 执行） | **STOP**。核对 max_iterations 与 current_iteration，不得抬高上限去迁就计数器。 |
| `HOLD: ... campaign.iterations[i].stop_state must be CONTINUE` | 已停止的轮次之后又记录了新轮次 | **STOP**。只有 CONTINUE 授权下一轮；核对真实轮次记录。 |
| `HOLD: ... campaign.iterations[i].model_reference must be null while this round ended CONTINUE` | 退出轮专属引用（E2=B）被写在了回环轮上 | **STOP**。回环轮（CONTINUE）的 `model_reference`/`next_batch_reference` 必须为 null；只有退出轮才写。 |
| `HOLD: ... campaign.project_reference 'X' must equal bench.project_reference 'Y'` | 合并记录出现两个项目来源 | **STOP**。删掉 campaign 块的 `project_reference`（唯一项目来源是 bench 块的），或改为相同值。 |
| `HOLD: ... campaign.evidence_scope 'X' must equal bench.evidence_scope 'Y'` | 两个块声明了不同的证据范围 | **STOP**。工件只承载一个范围（取 bench 块的）；核对两块后重填。 |
| `HOLD: ... evidence_id E-CONTRACT-CAMPAIGN-MAX-ITERATIONS is reserved` | 调用方伪造契约默认值的来源标记 | **STOP**。删除该证据项，让 builder 自行追加。 |
| `HOLD: ... max_iterations is absent and contracts/state-machine.json is absent/cannot be read` | 台次上限缺失且契约不可读 | **STOP**。修复契约路径或显式提供 `max_iterations`；不得凭空取数。 |
| `HOLD: ... bench.evidence contains GAP` / `... campaign.evidence contains GAP` | 证据链存在未解缺口 | **STOP**。保持 HOLD，生成 gap 诊断，等待证据补足。 |
| `FAIL: available_bench_slots must equal the derived N` | 落盘工件被杀手工改过 | **STOP**。删除手改值，用 builder 重新生成。 |
| `FAIL: max_iterations N carries the E-CONTRACT-CAMPAIGN-MAX-ITERATIONS provenance, but contracts/state-machine.json publishes M` | 落盘工件被手改（改了上限却留着来源标记） | **STOP**。删除手改值，用 builder 重新生成。 |
| `FAIL: ... must equal the deterministic bench policy` | 落盘工件的判定被手改（如把 HOLD 改成 GO） | **STOP**。用 builder 重新生成。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法损坏 | 检查 `../../schemas/` 与输入文件 JSON 格式。 |

---

## 5. Red Lines & Blacklist (Strict Prohibition)

1. **NO Invented Bench Data**: DO NOT invent availability dates, cycle times, or per-run costs. Unknown values stay `ASSUMED` with an explicit source, never fabricated.
2. **NO Hand-Set Capacity**: DO NOT write `available_bench_slots` by hand. It is derived by `bench_policy.available_bench_slots` and re-checked on validation.
3. **NO Capacity Booking**: DO NOT reserve slots, book runs, or assert the bench is free. Registration only records supplied availability, and the round plan reserves nothing either.
4. **NO Qualification Claims**: DO NOT claim the bench is qualified, calibrated, or release-ready from this record.
5. **NO Cross-Stage Spillover**: DO NOT emit a DOE resource envelope, run DOE, build experiment artifacts, run a round, or advance the state machine in this skill.
6. **NO Synthetic Closure**: DO NOT let a SYNTHETIC bench record reach `CLOSED` or be presented as physical capacity; a SYNTHETIC record never backs a PHYSICAL plan (both halves must declare the same scope).
7. **NO Bypass of Preflight**: DO NOT create the output artifact without running `preflight_bench_registration.py` first.
8. **NO Soft Guidance Words**: Forbidden ambiguous words: "灵活调整", "视情况而定", "酌情设置", "可以考虑". All values must be concrete numbers with verifiable metadata.
9. **NO Invented Cap**: `max_iterations` is the caller's value or the contract's published one, with its provenance recorded. Never a third number.
10. **NO Silent Loop Extension**: a round that ended anything but `CONTINUE` closes the loop in this record; do not open another round behind it and do not soften the decision.
11. **NO Split Record**: the merged record has exactly one project and one `evidence_scope`; a divergent campaign-side `project_reference` or `evidence_scope` is refused, never silently overwritten.
