---
name: external-record-import
description: Import one external collaboration record (outsourced test 外检 / outsourced service 外协 / vendor datasheet) with its provider and the mandatory data-usage-rights anchor. Use when user mentions "external-record-import", "外检记录", "外协数据", "外部试验", "数据使用权", "data_usage_rights_reference", "供应商数据表", "datasheet import", or bringing third-party lab data into the project evidence base.
---

# External Record Import

Import one batch of data obtained outside the project boundary as an evidence-bound record: who produced it (`provider`), what kind of collaboration it is (`record_type`), and — the hard rule — the reference to the agreement that authorises us to use the data (`data_usage_rights_reference`). **外检记录必须挂数据使用权引用**：缺使用权引用的外部数据一律拒绝导入，绝不缺省补齐。

Authority schema: `../../schemas/external_record.schema.json` (or local `references/external_record.schema.json` in deployed bundle). Fail-closed anchor: `scripts/external_record_policy.py::import_blockers`.

Authoritative output contract, consumed downstream:
- **experiment** (`external_record_reference`) may cite this artifact as `EXTERNAL:<external_id>` when runs were produced by an outsourced lab/service (optional field, WP-10).
- **interface** (`external_record_reference`) may cite this artifact the same way when compatibility observations were produced externally (optional field, WP-10).

---

## 1. Prerequisites & Gating

Before requesting external-record inputs:
- An external record is a resource object like bench (WP-05) and interface (WP-09), **not a chain stage**: it has **no upstream decision-artifact requirement** and MUST NOT be gated on a project stage it does not own.
- **Data usage rights (hard, plan WP-10)**: the record MUST carry `data_usage_rights_reference` naming the contract / NDA / data-usage agreement that grants the right to use the data inside this project. Missing or empty is rejected at preflight; the anchor is never guessed or defaulted.
- Every supplied value MUST carry provenance: the record needs `source` and `evidence_id`; each evidence item needs its own `evidence_id` / `statement` / `source`.
- Provenance alignment with WP-12 `claim_class`: evidence items on an external record are naturally `THIRD_PARTY_LAB` (independent lab measurement) or `MANUFACTURER_DATASHEET` (vendor-published, unverified) — never `INTERNAL_TEST` (own controlled measurements are recorded by their producing skills). Grading stays optional; absence means ungraded.
- If the usage agreement is not yet signed, do NOT import: keep the data out and record the blocker, instead of importing rights-less data.

---

## 2. Input Specification (contract in)

Input is a single JSON object containing only `external_record`:

```json
{
  "external_record": {
    "external_id": "EXT-001",
    "project_reference": "WGO-001",
    "record_type": "EXTERNAL_TEST",
    "provider": "National tribology test center",
    "data_usage_rights_reference": "DUA-2026-014",
    "source": "External lab report EXT-2026-014",
    "evidence_id": "E-EXT-001",
    "evidence_scope": "SYNTHETIC",
    "evidence": [
      { "evidence_id": "E-EXT-001", "statement": "Outsourced four-ball wear test report received for contract validation only.", "source": "External lab report EXT-2026-014", "status": "ASSUMED", "claim_class": "THIRD_PARTY_LAB" }
    ]
  }
}
```

### Field Invariants (contract in)
- Identity: `external_id`, `project_reference`, `provider`, `source`, `evidence_id` are required non-empty strings. `external_reference` is NOT an input — downstream consumers cite this record as `EXTERNAL:<external_id>`.
- Type: `record_type` is `EXTERNAL_TEST` (外检), `EXTERNAL_SERVICE` (外协), or `MANUFACTURER_DATASHEET` (供应商数据表).
- Usage rights (hard): `data_usage_rights_reference` is required and must be a non-empty string. It is the fail-closed anchor of this skill.
- Evidence scope: `evidence_scope` is `SYNTHETIC` or `PHYSICAL`. A SYNTHETIC external record must never be presented as a qualified or release conclusion.
- Evidence: `evidence` must be non-empty; GAP-status items block the import (fail-closed); optional `claim_class` on items follows the WP-12 four-value ladder.

---

## 3. Deterministic Execution Workflow

All scripts reside in `skills/external-record-import/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/external-record-import/scripts/preflight_external_record_import.py <input.json>
```
- Success: prints `READY: input can form one external collaboration record only` (exit 0).
- Failure: output starts with `HOLD: missing or invalid: ...; no artifact generated` (exit 1); a missing usage-rights anchor is named explicitly.

### Step 2: Build Deterministic Artifact
```bash
python skills/external-record-import/scripts/build_external_record_artifact.py <input.json> <temporary-file.json>
```
The builder generates canonical decision fields; it sets `project_id = project_reference` and `stage = "DRAFT"` (an external record is a resource, not a chain stage).

### Step 3: Validate Artifact
```bash
python skills/external-record-import/scripts/validate_external_record_artifact.py <temporary-file.json>
```
- Re-runs the schema contract and the usage-rights / GAP rules; asserts the deterministic decision fields.
- Success: `PASS: deterministic external-record artifact conforms to the external-record contract` (exit 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3 returns `PASS`.
```bash
# 🔴 CHECKPOINT · STOP: the external record stops here. It is imported data.
# Do NOT advance the state machine, claim the data is qualified or release-ready,
# or treat third-party/vendor claims as verified — cross-check before relying on them.
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... external_record must contain only the external-record-import input fields; ... missing=['data_usage_rights_reference']` | 输入缺数据使用权引用字段 | **STOP**。先取得使用权协议，再以 `data_usage_rights_reference` 显式引用后重新导入。 |
| `HOLD: ... external_record.data_usage_rights_reference is mandatory for external collaboration data` | 使用权引用为空白 | **STOP**。同上——外部数据没有使用权锚点不得进入证据基。 |
| `HOLD: ... external_record.evidence contains GAP; resolve the recorded gap before importing` | 证据链存在未解缺口 | **STOP**。保持 HOLD，等待证据补足。 |
| `HOLD: ... external_record.record_type must be EXTERNAL_TEST, EXTERNAL_SERVICE, or MANUFACTURER_DATASHEET` | 记录类型非法 | **STOP**。按三类枚举之一填写。 |
| `HOLD: ... external_record.evidence[N].claim_class` | claim_class 不在四级枚举内 | **STOP**。按 WP-12 四级（MANUFACTURER_DATASHEET/THIRD_PARTY_LAB/INTERNAL_TEST/REGULATORY_OR_STANDARD）或省略。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法损坏 | 检查 `../../schemas/` 与输入文件 JSON 格式。 |

---

## 5. Red Lines & Blacklist (Strict Prohibition)

1. **NO Rights-less Import**: 无数据使用权引用的外部数据绝不导入（计划 WP-10 验收明文）；`data_usage_rights_reference` 缺失或空白一律 HOLD，绝不缺省补齐。
2. **NO Invented Providers or Agreements**: DO NOT invent provider names, agreement numbers, or report references. Unknown values stay out of the record, never fabricated.
3. **NO Provenance Upgrade**: 外部记录的证据项天然是 `THIRD_PARTY_LAB` / `MANUFACTURER_DATASHEET`；DO NOT grade them `INTERNAL_TEST`（内部受控测量由其生产 skill 记录），也绝不把第三方/厂商结论当作已验证。
4. **NO GAP Import**: 证据链存在 GAP 状态项时不得导入；先补证据再导入。
5. **NO Cross-Stage Spillover**: DO NOT advance the state machine, build experiment/interface artifacts, or emit gates in this skill.
6. **NO Bypass of Preflight**: DO NOT create the output artifact without running `preflight_external_record_import.py` first.
7. **NO Soft Guidance Words**: Forbidden ambiguous words: "应该可以用", "先用再说", "视情况而定", "酌情处理". Usage rights must trace to a concrete agreement reference.
