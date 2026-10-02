---
name: interface-definition
description: Define one material / coating / interface record (counterpart pair, optional coating system, per-condition compatibility evidence) with a fail-closed compatibility verdict, and gate design_freeze COMPATIBILITY_PASSED citations. Use when user mentions "interface-definition", "界面定义", "材料相容性", "涂层界面", "DLC涂层", "配副材料", "compatibility evidence", "COMPATIBILITY_PASSED", "相容性证据", or recording which material meets which surface before a design freeze.
---

# Interface Definition

Define one material / coating / tribological contact pair as an evidence-bound record: who meets whom (counterpart a/b), the coating system when one side is coated, and per-condition compatibility observations. The compatibility verdict is **fail-closed**: without compatibility evidence a PASS is not admissible, and `COMPATIBILITY_PASSED` cannot be satisfied.

Authority schema: `../../schemas/interface.schema.json` (or local `references/interface.schema.json` in deployed bundle). Fail-closed anchors: `scripts/interface_policy.py::pass_blockers` (the PASS rule) and `scripts/interface_policy.py::freeze_compatibility_errors` (the COMPATIBILITY_PASSED link).

Authoritative output contract, consumed downstream:
- **failure_ctq** (`interface_failure_modes`) may cite this record as `interface_reference` (optional field, WP-09).
- **design_freeze** `COMPATIBILITY_PASSED` freeze condition must cite this artifact as `INTERFACE:<interface_id>`; the cited record must exist and carry verdict PASS. Enforcement lives in `interface_policy.freeze_compatibility_errors` plus the e2e contract (`tests/lubricant_e2e/test_interface_definition.py`); the schema-level pattern on `design_freeze.schema.json` is deferred while `tests/test_r25_contracts.py` is owned by the parallel WP-12.

---

## 1. Prerequisites & Gating

Before requesting interface inputs:
- An interface record is a resource object like bench (WP-05), **not a chain stage**: it has **no upstream decision-artifact requirement** and MUST NOT be gated on a project stage it does not own.
- Every supplied value MUST carry provenance: the record needs `source` and `evidence_id`, each compatibility observation needs `method_reference` and `evidence_id`. Values without provenance are rejected, never defaulted.
- External dependency (DLC coating parameters, supplier batches) is handled **by declaration**: the optional `coating` object is either fully present with its provenance (`coating_system`, `coating_reference`, `supplier`, `supplier_batch_reference`, `source`) or omitted entirely — never partially guessed.
- If compatibility observations are missing, record `verdict = "GAP"` with an empty `compatibility_evidence`. DO NOT fabricate a PASS.

---

## 2. Input Specification (contract in)

Input is a single JSON object containing only `interface`:

```json
{
  "interface": {
    "interface_id": "IF-DLC-001",
    "project_reference": "WGO-001",
    "interface_type": "COATING_SUBSTRATE",
    "counterpart_a": { "role": "COATING", "designation": "DLC", "source": "supplier sheet DS-2026-09" },
    "counterpart_b": { "role": "SUBSTRATE", "designation": "GCr15 bearing steel", "source": "internal spec MS-001" },
    "coating": {
      "coating_system": "DLC",
      "coating_reference": "DLC-PARAM-SHEET-01",
      "supplier": "ACME Coatings",
      "supplier_batch_reference": "B-2026-09-01",
      "source": "supplier sheet DS-2026-09"
    },
    "compatibility_evidence": [
      { "compatibility_id": "CMP-001", "method_reference": "TM-001", "condition": "1.2 GPa contact, 80 C, 72 h grease immersion", "result": "PASS", "evidence_id": "EV-COMPAT-001", "status": "OBSERVED" }
    ],
    "verdict": "PASS",
    "source": "compatibility lab report CLR-2026-014",
    "evidence_id": "EV-IF-001",
    "evidence_scope": "SYNTHETIC",
    "evidence": [
      { "evidence_id": "EV-IF-001", "statement": "Synthetic compatibility record supplied for contract validation only; not a qualified release conclusion.", "source": "Synthetic interface fixture", "status": "ASSUMED" }
    ]
  }
}
```

### Field Invariants (contract in)
- Identity: `interface_id`, `project_reference`, `source`, `evidence_id` are required non-empty strings. `interface_reference` is NOT an input — it is the derived `INTERFACE:<interface_id>` citation form.
- Type: `interface_type` is `COATING_SUBSTRATE`, `LUBRICANT_SURFACE`, or `MATERIAL_PAIR`.
- Counterparts: `counterpart_a` / `counterpart_b` each require `role` (`COATING`, `SUBSTRATE`, `LUBRICANT`, `COUNTERFACE`, `SEAL`, `OTHER`), `designation`, `source`; optional `material_reference`, `supplier`, `supplier_batch_reference`.
- Coating: optional; when present it must carry `coating_system`, `coating_reference`, `supplier`, `supplier_batch_reference`, `source`; optional `thickness_um` / `surface_hardness` are positive numbers and `hardness_unit` must accompany `surface_hardness`.
- Compatibility evidence: `compatibility_evidence` is an array (may be empty, which forces `verdict = "GAP"`); each item requires `compatibility_id`, `method_reference`, `condition`, `result` (`PASS`/`FAIL`/`INCONCLUSIVE`/`GAP`), `evidence_id`, `status` (`OBSERVED`/`ASSUMED`/`GAP`).
- Verdict (fail-closed): a PASS is only admissible with non-empty, all-`OBSERVED`, all-`PASS` compatibility evidence and no GAP evidence. Empty evidence list forces `verdict = "GAP"`. `FAIL` / `INCONCLUSIVE` are legitimate recorded outcomes and are never upgraded.
- Evidence scope: `evidence_scope` is `SYNTHETIC` or `PHYSICAL`. A SYNTHETIC interface record must never be presented as qualified or release evidence.
- GAP: `evidence` must be non-empty; GAP-status items in `evidence` block a PASS verdict.

---

## 3. Deterministic Execution Workflow

All scripts reside in `skills/interface-definition/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/interface-definition/scripts/preflight_interface_definition.py <input.json>
```
- Success: prints `READY: input can form one interface record only` (exit 0).
- Failure: output starts with `HOLD: missing or invalid: ...; no artifact generated` (exit 1).

### Step 2: Build Deterministic Artifact
```bash
python skills/interface-definition/scripts/build_interface_artifact.py <input.json> <temporary-file.json>
```
The builder generates canonical decision fields; it sets `project_id = project_reference` and `stage = "DRAFT"` (an interface is a resource, not a chain stage).

### Step 3: Validate Artifact
```bash
python skills/interface-definition/scripts/validate_interface_artifact.py <temporary-file.json>
```
- Re-runs the schema contract and the fail-closed verdict rules; asserts the deterministic decision fields.
- Success: `PASS: deterministic interface artifact conforms to the interface contract` (exit 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3 returns `PASS`.
```bash
# 🔴 CHECKPOINT · STOP: the interface record stops here. It is recorded evidence.
# Do NOT advance the state machine, run a design freeze, treat COMPATIBILITY_PASSED as satisfied
# without a PASS-verdict artifact cited as INTERFACE:<interface_id>, or claim release qualification.
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... interface must contain only the interface-definition input fields; ... unexpected=... missing=...` | 输入含未知字段或有字段缺失 | **STOP**。按报错列出的一侧字段名核对，只保留契约字段。 |
| `HOLD: ... interface.verdict must be GAP when compatibility_evidence is empty` | 无相容性证据却声称 PASS 之外的结论 | **STOP**。无证据即置 `verdict = "GAP"`，绝不编造。 |
| `HOLD: ... compatibility_evidence[0].result must be PASS to claim PASS` | 证据中存在 FAIL/INCONCLUSIVE/GAP 观察 | **STOP**。保持非 PASS 结论，等待复测证据。 |
| `HOLD: ... compatibility_evidence[0].status must be OBSERVED to claim PASS` | 证据为 ASSUMED/GAP 状态 | **STOP**。ASSUMED/GAP 观察阻断 PASS。 |
| `HOLD: ... interface.evidence contains GAP; a PASS verdict is not allowed` | 证据链存在未解缺口 | **STOP**。保持 HOLD，生成 gap 诊断，等待证据补足。 |
| `HOLD: ... interface.coating.coating_reference` | 涂层对象不完整（缺参数表/批次/来源） | **STOP**。涂层对象要么带全溯源字段，要么整体省略，不得部分猜测。 |
| `COMPATIBILITY_PASSED must cite an interface artifact as INTERFACE:<interface_id>` | freeze 条件引用格式非法 | **STOP**。改用 `INTERFACE:<interface_id>` 引用已存在的 interface 工件。 |
| `COMPATIBILITY_PASSED cites unknown interface <id>` | 引用的 interface 工件不存在 | **STOP**。先定义并构建该 interface 工件。 |
| `COMPATIBILITY_PASSED cites interface <id> whose verdict is ...` | 引用的工件无相容性证据支持 PASS | **STOP**。补齐 all-OBSERVED all-PASS 证据后重建工件。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法损坏 | 检查 `../../schemas/` 与输入文件 JSON 格式。 |

---

## 5. Red Lines & Blacklist (Strict Prohibition)

1. **NO Fabricated PASS**: 无相容性证据时 `COMPATIBILITY_PASSED` 无法满足；`verdict = "PASS"` 仅在非空、全 OBSERVED、全 PASS 的 `compatibility_evidence` 且无 GAP 证据时可用。空白证据一律 GAP。
2. **NO Invented Compatibility Data**: DO NOT invent compatibility observations, method references, or conditions. Unknown values stay `GAP`/`ASSUMED` with explicit provenance, never fabricated.
3. **NO Partial Coating Guess**: 涂层外部依赖以声明处理：`coating` 对象要么字段齐全带溯源，要么整体省略；不得只填一半。
4. **NO Verdict Upgrades**: DO NOT upgrade a FAIL / INCONCLUSIVE record to PASS in place; new evidence means a new observation item, not a silent edit.
5. **NO Hand-Set Citation**: `COMPATIBILITY_PASSED` 引用必须是 `INTERFACE:<interface_id>` 且指向真实存在、verdict 为 PASS 的工件；`freeze_compatibility_errors` 会逐条拒绝并点名阻断项。
6. **NO Cross-Stage Spillover**: DO NOT advance the state machine, run a design freeze, or emit failure-CTQ records in this skill.
7. **NO Bypass of Preflight**: DO NOT create the output artifact without running `preflight_interface_definition.py` first.
8. **NO Soft Guidance Words**: Forbidden ambiguous words: "应该没问题", "视情况而定", "酌情处理", "可以先标记". All verdicts must trace to concrete evidence items with verifiable metadata.
