---
name: application-definition
description: Define one evidence-bound application (field / machine) validation record with acceptance criteria, a controlled verdict, counterexamples and a life-claim boundary. Use when user mentions "application-definition", "应用验证", "整机验证", "应用判据", "acceptance criteria", "life_claim_boundary", "寿命声明边界", "counterexample", or issuing an application verdict for a formula+process under a fixed process window.
---

# Application Definition

Define one evidence-bound application record: the acceptance criteria the applied formula+process must meet, the observed counterexamples, the boundary of the life/durability claim, and a controlled verdict.

Authority schema: `../../schemas/application.schema.json` (or local `references/application.schema.json` in deployed bundle).

Authoritative output contract, consumed downstream:
- **WP-06** (Stage 13 `APPLIED`) aggregates `application_id`, `result`, `acceptance_criteria`, `counterexamples`, `life_claim_boundary` and `bench_references` as the APPLIED-stage evidence. The verdict rules below are the interface: WP-06's "INCONCLUSIVE 不得进入 APPLIED" depends on this record never faking a PASS.

---

## 1. Prerequisites & Gating

Before requesting application inputs:
- A fixed process window SHOULD exist; the record cites it as `process_window_reference` in the form `PROCESS-WINDOW:<window_id>`. If it is not fixed yet, record the application criterion as `GAP` — never invent a window.
- **External blocker (application-判据 thresholds have no owner yet)**: this is handled by design, not by guessing. Leave the criterion with no threshold and `status: "GAP"`, and set `result` to `GAP` / `INCONCLUSIVE`. A fabricated PASS is the one thing this skill must never produce.
- Provenance is required: `source` and `evidence_id` must be present. Unknown values are recorded as `ASSUMED` with an explicit source, never defaulted.

---

## 2. Input Specification (contract in)

Input is a single JSON object containing only `application`:

```json
{
  "application": {
    "application_id": "APP-WGO-001",
    "project_reference": "WGO-001",
    "formula_reference": "FORMULA-WGO-001",
    "process_window_reference": "PROCESS-WINDOW:PW-WGO-001",
    "bench_references": ["BENCH-SZ-01"],
    "acceptance_criteria": [
      { "criterion_id": "C-1", "statement": "Leakage below limit at rated load.", "threshold": 1.0, "operator": "<=", "unit": "mL", "source": "Synthetic application spec", "evidence_id": "EV-APP-001", "status": "OBSERVED" },
      { "criterion_id": "C-2", "statement": "10-year life claim threshold.", "status": "GAP" }
    ],
    "result": "INCONCLUSIVE",
    "counterexamples": [],
    "life_claim_boundary": { "claim_scope": "10-year service life at rated load", "status": "GAP", "validated_conditions": [] },
    "source": "Synthetic application spec",
    "evidence_id": "EV-APP-001",
    "evidence_scope": "SYNTHETIC",
    "evidence": [
      { "evidence_id": "EV-APP-001", "statement": "Synthetic application criteria supplied for contract validation only; not a field or life conclusion.", "source": "Synthetic application fixture", "status": "ASSUMED" }
    ]
  }
}
```

### Field Invariants (contract in)
- Identity: `application_id`, `project_reference`, `formula_reference` are required non-empty strings; `process_window_reference` must start with `PROCESS-WINDOW:`.
- `bench_references`: array of bench ids (may be empty; WP-06 uses it for APPLIED evidence aggregation).
- `acceptance_criteria`: array, **may be empty**. Each criterion requires `criterion_id`, `statement`, `status`. If `threshold` is absent, `status` MUST be `GAP`; if `threshold` is present it must be a number and carry `operator` (`<`, `<=`, `==`, `>=`, `>`) plus `unit`, `source`, `evidence_id`, with `status` `OBSERVED` or `ASSUMED`.
- `result`: one of `PASS` / `FAIL` / `INCONCLUSIVE` / `GAP`. **If `acceptance_criteria` is empty, `result` MUST be `GAP`.**
- `counterexamples`: array; each entry requires `counterexample_id`, `statement`, `observation`, `evidence_reference`.
- `life_claim_boundary`: object with `claim_scope`, `status`, `validated_conditions[]` (each requires `condition_id`, `parameter`, `lower_bound`, `upper_bound`, `unit`). `status` is `OBSERVED` / `ASSUMED` / `GAP`. An empty `validated_conditions` is an explicit "no validated boundary".
- Provenance (hard): `source` and `evidence_id` are required.
- Evidence scope: `SYNTHETIC` or `PHYSICAL`; a SYNTHETIC record must never be presented as a field or life conclusion.
- GAP: `evidence` must be non-empty and contain no `GAP` for a PASS verdict.

### The Fail-Closed Verdict Rule (contract guarantee)
A `PASS` verdict is admissible **only** when all of the following hold; otherwise the preflight holds and the artifact cannot be built:
1. `acceptance_criteria` is non-empty and **every** criterion has `status = OBSERVED` and a determined numeric `threshold`.
2. `life_claim_boundary.status = OBSERVED` and `validated_conditions` is non-empty. **An empty life-claim boundary can never support a PASS.**
3. `counterexamples` is empty.
4. `evidence` contains no `GAP`.

---

## 3. Deterministic Execution Workflow

All scripts reside in `skills/application-definition/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/application-definition/scripts/preflight_application_definition.py <input.json>
```
- Success: prints `READY: input can form one application record only` (exit 0).
- Failure: output starts with `HOLD: missing or invalid: ...; no artifact generated` (exit 1).

### Step 2: Build Deterministic Artifact
```bash
python skills/application-definition/scripts/build_application_artifact.py <input.json> <temporary-file.json>
```
The builder sets `project_id = project_reference`, generates the canonical decision fields (`decision = GO` iff `result = PASS`, else `HOLD`), and sets `stage = "APPLIED"` (the WP-06 Stage 13 token; entry into the stage is gated by `application-validation`).

### Step 3: Validate Artifact
```bash
python skills/application-definition/scripts/validate_application_artifact.py <temporary-file.json>
```
- Re-runs the verdict rule and asserts the deterministic decision fields.
- Success: `PASS: deterministic application artifact conforms to the application contract` (exit 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3 returns `PASS`.
```bash
# 🔴 CHECKPOINT · STOP: the application record stops here.
# Do NOT gate the APPLIED entry (application-validation), freeze, or claim a field / life / release conclusion.
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... acceptance_criteria must be a non-empty array to claim PASS` | 没有判据却宣称 PASS | **STOP**。补判据，或把 `result` 改为 `GAP`/`INCONCLUSIVE`。 |
| `HOLD: ... acceptance_criteria[N].status must be OBSERVED to claim PASS (criteria with GAP block PASS)` | 判据缺阈值/未定，却宣称 PASS | **STOP**。判据阈值未定时保持 GAP，不得伪造 PASS。 |
| `HOLD: ... acceptance_criteria[N].status must be GAP when threshold is not determined` | 判据无阈值却未显式标 GAP | **STOP**。显式写 `status: "GAP"`，不允许静默省略。 |
| `HOLD: ... life_claim_boundary must be OBSERVED with at least one validated condition to claim PASS` | `life_claim_boundary` 为空却宣称 PASS | **STOP**。补齐已验证边界条件，或把 verdict 降为非 PASS。 |
| `HOLD: ... counterexamples must be empty to claim PASS` | 存在反例却宣称 PASS | **STOP**。verdict 改为 `FAIL`/`INCONCLUSIVE`。 |
| `HOLD: ... application.result must be GAP when acceptance_criteria is empty` | 判据为空且 verdict 非 GAP | **STOP**。空判据只能配 `result: "GAP"`。 |
| `HOLD: ... application.process_window_reference must be PROCESS-WINDOW:<window_id>` | 未引用已冻结工艺窗口 | **STOP**。引用固定窗口，或将该判据标 GAP，不得编造窗口。 |
| `HOLD: ... application.evidence contains GAP; a PASS verdict is not allowed` | 证据缺口却宣称 PASS | **STOP**。先解缺口，保持非 PASS。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法损坏 | 检查 `../../schemas/` 与输入文件 JSON 格式。 |

---

## 5. Red Lines & Blacklist (Strict Prohibition)

1. **NO Fabricated PASS**: DO NOT emit `result: "PASS"` when any criterion is GAP, the life-claim boundary is empty, or a counterexample exists. This is the single most important prohibition.
2. **NO Silently Missing Criteria**: DO NOT drop an undetermined criterion. It must appear with `status: "GAP"`.
3. **NO Invented Thresholds**: DO NOT invent acceptance thresholds, life boundaries, or window parameters. Unknown values stay `GAP`/`ASSUMED`.
4. **NO Field / Life Claims**: DO NOT state a field, durability, or release conclusion from this record; it only records supplied evidence and a controlled verdict.
5. **NO Cross-Stage Spillover**: DO NOT advance the state machine to `APPLIED`, freeze the design, run gate review, or run DOE in this skill.
6. **NO Synthetic Closure**: DO NOT let a SYNTHETIC application record reach `CLOSED` or be treated as physical release evidence.
7. **NO Bypass of Preflight**: DO NOT create the output artifact without running `preflight_application_definition.py` first.
8. **NO Soft Guidance Words**: Forbidden ambiguous words: "灵活调整", "视情况而定", "酌情设置", "可以考虑". Criteria must be concrete, or explicitly GAP.
