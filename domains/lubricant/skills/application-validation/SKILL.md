---
name: application-validation
description: Gate one verified project's entry into the WP-06 APPLIED stage by aggregating the application record. Use when user mentions "application-validation", "应用与整机验证", "APPLIED", "应用验证门禁", "application verdict gate", or asking whether a VERIFIED project may advance to application-and-machine validation.
---

# Application Validation (APPLIED entry gate)

Decide whether one **VERIFIED** project may enter Stage 13 `APPLIED` (应用与整机验证). The gate aggregates the built application record from `application-definition` and applies one asymmetric, fail-closed rule:

> **INCONCLUSIVE 不得进入 APPLIED。** An undetermined verdict is not a validation pass. FAIL and GAP are likewise blocked; only a fail-closed admissible PASS may advance.

Authority contract: the APPLIED entry rules in `scripts/application_validation_policy.py`, which import the PASS rule from `skills/application-definition/scripts/application_policy.py` (single source of truth; the pack installer deploys it beside this skill's scripts).

Upstream output contract consumed here (produced by `application-definition`):
- `application_id`, `project_reference`, `formula_reference`, `process_window_reference`, `bench_references`, `acceptance_criteria`, `result` (PASS / FAIL / INCONCLUSIVE / GAP), `counterexamples`, `life_claim_boundary`, plus `artifact_type = "application"`.

---

## 1. Prerequisites & Gating

Before requesting this gate:
- The project must be at stage `VERIFIED` (the review gate passed). A project at any other stage is rejected — only a verified project can be applied.
- A built application artifact must exist. This gate never invents, edits, or re-scores criteria; it consumes the record as-is and re-checks its admissibility.
- **External blocker (判据阈值无属主) is handled by design**: a record with undetermined criteria can only carry `result: "GAP"` / `"INCONCLUSIVE"`, and both are blocked here. A fabricated PASS is the one thing this gate must never allow.

---

## 2. Input Specification (contract in)

Input is a single JSON object containing only `application_validation`:

```json
{
  "application_validation": {
    "project_reference": "WGO-001",
    "current_stage": "VERIFIED",
    "application": {
      "artifact_type": "application",
      "application_id": "APP-WGO-001",
      "project_reference": "WGO-001",
      "result": "PASS",
      "acceptance_criteria": [ "…OBSERVED criteria with determined thresholds…" ],
      "counterexamples": [],
      "life_claim_boundary": { "…OBSERVED with non-empty validated_conditions…" },
      "bench_references": ["BENCH-SZ-01"],
      "evidence": [ "…no GAP entries…" ]
    }
  }
}
```

### Field Invariants (contract in)
- `project_reference`: non-empty string; must equal `application.project_reference`.
- `current_stage`: must be exactly `VERIFIED`.
- `application`: the built application artifact object (`artifact_type = "application"`), not the raw application-definition input.

### The APPLIED Entry Rule (contract guarantee)
Entry is admissible **only** when all of the following hold; otherwise the preflight holds and no APPLIED entry happens:
1. `current_stage = "VERIFIED"`.
2. `application.result = "PASS"`. **`INCONCLUSIVE` never enters APPLIED** (nor do `FAIL` / `GAP`).
3. The PASS is fail-closed admissible (re-checked via the single-source rule): non-empty all-OBSERVED criteria with determined thresholds, non-empty OBSERVED `life_claim_boundary`, empty `counterexamples`, no GAP evidence.
4. `bench_references` cites at least one registered bench.

---

## 3. Deterministic Execution Workflow

All scripts reside in `skills/application-validation/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/application-validation/scripts/preflight_application_validation.py <input.json>
```
- Success: prints `READY: the application record gates entry into APPLIED` (exit 0).
- Failure: output starts with `HOLD: missing or invalid: ...; no APPLIED entry` (exit 1).

### Step 2: State-Machine Advancement (outside this skill)
A READY verdict authorizes — it does not perform — the transition. The project advances `VERIFIED → APPLIED` only via a state-machine `GO` (the router routes that step to this skill), and later `APPLIED → FROZEN` is the **only** FREEZE entry.

```bash
# 🔴 CHECKPOINT · STOP: the gate stops here.
# Do NOT freeze, close, or claim a field / life / release conclusion from this gate.
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... INCONCLUSIVE cannot enter APPLIED` | 应用验证结论未定却想进 APPLIED | **STOP**。补齐判据观测值后把 verdict 升为 PASS，或显式记 GAP；绝不带未定结论进场。 |
| `HOLD: ... application result must be PASS to enter APPLIED (got FAIL/GAP)` | 结论为 FAIL/GAP | **STOP**。先解决失败项/判据缺口，再重新门禁。 |
| `HOLD: ... current_stage must be VERIFIED to enter APPLIED` | 项目不在 VERIFIED | **STOP**。先走完审查门禁到 VERIFIED。 |
| `HOLD: ... acceptance_criteria must be a non-empty array to claim PASS` | 判据缺失却宣称 PASS | **STOP**。补判据或把 verdict 降为 GAP；缺判据一律拒绝。 |
| `HOLD: ... life_claim_boundary must be OBSERVED with at least one validated condition to claim PASS` | 寿命边界为空却宣称 PASS | **STOP**。补齐边界条件或保持非 PASS。 |
| `HOLD: ... application.bench_references must list at least one registered bench` | 未挂台架 | **STOP**。引用至少一个已登记台架（bench-registration 产出）。 |
| `FAIL: cannot read input` | 输入缺失或 JSON 损坏 | 检查输入文件路径与 JSON 格式。 |

---

## 5. Red Lines & Blacklist (Strict Prohibition)

1. **NO INCONCLUSIVE Advancement**: DO NOT allow an `INCONCLUSIVE` verdict to enter `APPLIED` under any wording ("先按已定处理", "回头补数"). This is the single most important prohibition.
2. **NO Fabricated PASS**: DO NOT accept a PASS whose criteria/boundary/counterexample conditions do not hold; the PASS rule is re-checked from the single source, never trusted from the record.
3. **NO Stage Jumping**: DO NOT gate entry from any stage other than `VERIFIED`, and DO NOT advance more than one stage (APPLIED itself advances only by a separate state-machine GO).
4. **NO Freeze From Here**: FREEZE requires `APPLIED → FROZEN`; this skill neither freezes nor closes.
5. **NO New Evidence**: this gate aggregates and re-checks; it does not create experiment, model, life, or release evidence.
6. **NO Synthetic Advancement**: a SYNTHETIC-scope application record must never be presented as physical application evidence for APPLIED.
7. **NO Bypass of Preflight**: DO NOT declare APPLIED entry without running `preflight_application_validation.py`.
8. **NO Soft Guidance Words**: Forbidden ambiguous words: "灵活调整", "视情况而定", "酌情设置", "可以考虑". The verdict is READY or HOLD, nothing else.
