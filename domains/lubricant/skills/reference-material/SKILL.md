---
name: reference-material
description: Build the physical reference-material dossier for a precision-gear grease campaign at REFERENCE_MATERIAL_RESOLVED - a Known Good and a Known Bad, each carrying material identity, formula identity, mechanism-bound history evidence, storage SOP and safety reference. Use when user mentions "reference-material", "参照物卷宗", "已知好样", "已知坏样", "方法标定参照物", "历史失效证据", or advancing to REFERENCE_MATERIAL_RESOLVED in lubricant R&D.
---

# Reference Material (REFERENCE_MATERIAL_RESOLVED · 参照物卷宗)

Record the physical reference set for a precision-gear grease campaign at `REFERENCE_MATERIAL_RESOLVED`: a
Known Good that must pass and a Known Bad that must fail. This is a dossier of material history, NOT a
method qualification, NOT a discrimination claim, and NOT a formulation or bench result.

Authority schema: `../../schemas/reference.schema.json` (or local `references/reference.schema.json` in the
deployed bundle). Derived-tier and propagation anchor: `scripts/reference_material_policy.py`.

Why this stage exists: Stage 5 (method qualification) must prove that a test stand can tell a good sample
from a bad one. That proof is impossible without two physical objects. In the real WGO_001 case the known-good
and known-bad work was done by hand, per project, from scratch - and BOTH dossiers ended `UNRESOLVED`, which
was the correct outcome because no evidence supported a better one. This skill makes that work an object with
a gate.

**Going `UNRESOLVED` is a legitimate, expected outcome - not a failure to be papered over.** Better to admit
there is no bad sample than to invent one.

---

## 1. Input Specification (contract in)

Input is a single JSON object: the upstream charter path, the reference-set id, the two dossier sides, and the
artifact-level evidence. The following is the shape of a real request (values illustrative):

```json
{
  "project_artifact": "project.json",
  "reference_id": "REF-PGD-001",
  "evidence_scope": "PHYSICAL",
  "known_good": [
    {
      "reference_id": "REF-PGD-001-G1",
      "resolution": "RESOLVED",
      "selection_rung": "DIRECT_HISTORY",
      "material_identity": "OEM precision-gear grease, trade name ..., lot LOT-...-0001",
      "formula_identity": "FORM-PG-000@v1",
      "history_evidence": [
        {
          "evidence_reference": "Service history SH-G-001: 24 months in the reference harmonic drive with no bearing event recorded.",
          "mechanism_reference": "MECHANISM-NONE: no failure mechanism is demonstrated by this no-event history."
        }
      ],
      "storage_sop": "SOP-STORE-001",
      "safety_reference": "SDS-...-2025"
    }
  ],
  "known_bad": [
    {
      "reference_id": "REF-PGD-001-B1",
      "resolution": "RESOLVED",
      "selection_rung": "DIRECT_HISTORY",
      "material_identity": "Contaminated grease, contaminant identity and concentration, lot LOT-...-0002",
      "formula_identity": "FORM-PG-000@v0",
      "history_evidence": [
        {
          "evidence_reference": "Bench failure event FE-B-001: grease hardening and torque rise after the accelerated run.",
          "mechanism_reference": "MECHANISM-PG-GREASE-HARDENING-001: the recorded failure demonstrates hardening driven by an under-milled soap structure."
        }
      ],
      "storage_sop": "SOP-STORE-002",
      "safety_reference": "SDS-...-2025"
    }
  ],
  "evidence": [
    {
      "evidence_id": "E-REF-001",
      "statement": "The Known Bad dossier cites a failure event bound to the mechanism it demonstrates.",
      "source": "bench report JP...",
      "status": "OBSERVED"
    }
  ]
}
```

### Field Invariants (contract in)
- Upstream (hard): `project_artifact` is mandatory. It must validate against
  `schemas/project.schema.json`, be `stage: PROJECT_DEFINED`, `status: ACTIVE`, `decision: GO`, and carry the
  single `project_id` that the reference record inherits. Missing or invalid upstream = HOLD, nothing written.
- `reference_id`: non-empty; identifies the set as a whole (dossier ids identify dossiers inside it).
- `evidence_scope`: `SYNTHETIC` or `PHYSICAL`. A SYNTHETIC record is fixture-only and can never authorize
  stage advancement.
- Dossier fields (both sides): `reference_id`, `resolution` ∈ {`RESOLVED`,`UNRESOLVED`}, `selection_rung`
  ∈ {`DIRECT_HISTORY`,`LONG_RUN_NO_EVENT`,`UNRESOLVED`}, `material_identity`, `formula_identity`,
  `history_evidence[]`, `storage_sop`, `safety_reference`. An unknown field is a hard reject.
- `known_good` / `known_bad` may be EMPTY arrays: that is an open recording, and the side is simply not
  available yet. It is not a reason to invent a sample.
- `history_evidence[]`: each item carries `evidence_reference` and `mechanism_reference`, both non-empty.
  `mechanism_reference` must read `<MECHANISM-ID>: <statement>` with a concrete id. `MECHANISM-NONE: ...` is
  honest for a Known Good whose history records the ABSENCE of an event; it never establishes a Known Bad.
- Absence: when a document genuinely does not exist, write an explicit absence marker (`MISSING`,
  `NOT_SUPPLIED`) instead of a fabricated SOP number or safety sheet. An absence marker cannot support
  `RESOLVED` - it forces that dossier to `UNRESOLVED`.
- Artifact-level `evidence`: non-empty; each item has `evidence_id`, `statement`, `source`, `status`.
  A `GAP` status is a hard reject here - a missing reference material belongs on the dossier as
  `resolution: UNRESOLVED`, not on the request as an open gap.
- DO NOT supply `tier` or `downstream_flag`. Both are DERIVED by `reference_material_policy`; supplying them
  is a hard reject.

### Resolution Rule (the tier ladder)
A dossier is recorded `RESOLVED` only when it declares `RESOLVED` AND its own records support it: a ladder
rung, material identity, formula identity, storage SOP, safety reference, and at least one well-formed history
item; a Known Bad must additionally bind at least one recorded failure to the mechanism it demonstrates.
Anything short of that is recorded `UNRESOLVED`. The ladder, in order:

```
Rung 1  DIRECT_HISTORY      a mature sample with a written bench/history record
Rung 2  LONG_RUN_NO_EVENT   a sample with a 10 h no-event record
Rung 3  UNRESOLVED          nothing found - record it, do NOT invent a sample
```

### Propagation Rule (derived, not asserted)
```
tier            = highest rung achieved by any RESOLVED dossier, else UNRESOLVED
downstream_flag = DISCRIMINATION_EVIDENCE_COMPLETE   iff a Known Bad is RESOLVED
                  DISCRIMINATION_EVIDENCE_INCOMPLETE otherwise
decision        = GO  iff at least ONE side is RESOLVED and no artifact evidence item is GAP
                  HOLD otherwise
```
`DISCRIMINATION_EVIDENCE_INCOMPLETE` is a HARD STOP for Stage 5, not a carried state: Stage 5 reads this
flag off the dossier and refuses to proceed while it is INCOMPLETE. A Stage 4 `decision: GO` is therefore
NECESSARY BUT NOT SUFFICIENT - it says at least one side is RESOLVED, not that a Known Bad exists.

### Known validation boundary (stated, not hidden)
`schemas/reference.schema.json` fixes the dossier shape and carries **no ladder-rung field**, so the rung a
dossier achieved is input-side information. The validator therefore enforces the resolved/UNRESOLVED direction
exactly - no `tier` above `UNRESOLVED` without a RESOLVED dossier, and no `UNRESOLVED` tier standing over one -
but it cannot tell rung 1 from rung 2 in a hand-edited artifact whose dossiers are all legitimately RESOLVED.
The normal path is exact because the builder derives `tier` from the claimed rung; the dangerous direction (a
resolution or a `COMPLETE` flag justified by nothing) is fully closed. There is no way to strengthen the rung
check without changing the frozen schema, which this skill must not do.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/reference-material/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python -B skills/reference-material/scripts/preflight_reference_material.py <input.json>
```
- Validates the upstream charter, every dossier, the artifact evidence, and the workspace's artifact names.
- Success: prints `READY: input can form one REFERENCE_MATERIAL_RESOLVED record`, then a `GATE:` line stating
  the resolved counts, the derived tier and the downstream flag, then `NOTE:` lines per dossier (exit 0).
- Failure: output starts with `HOLD: missing or invalid: ...; no artifact generated` (exit 1) and nothing is
  written.

### Step 2: Build Deterministic Artifact
```bash
python -B skills/reference-material/scripts/build_reference_artifact.py <input.json> <temporary-file.json>
```
The builder re-runs the preflight checks, then assembles the artifact from
`reference_material_policy.py`: recorded dossiers (resolution downgrade-only), the derived `tier`, the derived
`downstream_flag`, and the canonical decision block. It sets `stage = "REFERENCE_MATERIAL_RESOLVED"` and
`project_id` from the charter. It never invents a sample, a mechanism binding, or a tier.

### Step 3: Validate Artifact
```bash
python -B skills/reference-material/scripts/validate_reference_artifact.py <temporary-file.json>
```
- Validates against `schemas/reference.schema.json` with its two `if/then` propagation rules, then recomputes
  the whole deterministic policy from the artifact's own dossiers and asserts every field equals it.
- Success: `PASS: deterministic reference-material artifact conforms to the reference contract` (exit 0).
- A `HOLD` decision artifact with `tier: UNRESOLVED` PASSES: it is a truthful record of an unresolved set.

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3 returns `PASS`.
**Naming rule**: if `reference.json` does not yet exist in the workspace root, commit this record as
`reference.json`; otherwise commit it as `reference-<project_id>-<reference_id>.json`. That is, the first
record of this stage occupies the canonical name `reference.json` (the stage-gate panel uses this exact name to
mark the stage complete), and subsequent records of the same stage are appended as suffixed names carrying the
record id. After the commit, run `python scripts/check_artifact_naming.py <workspace_root>` and correct any
`HOLD` before proceeding. The checker also enforces that `project.json`'s `stage` stays the constant
`PROJECT_DEFINED` - it is NOT the project's current stage, and must not be advanced.
```bash
# 🔴 CHECKPOINT · STOP: the reference dossier stops here at REFERENCE_MATERIAL_RESOLVED. Next station: TEST_METHODS_QUALIFIED (test-method-qualification).
```

---

## 3. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... project_artifact ...` / `... must be PROJECT_DEFINED, ACTIVE, and GO` | 上游章程缺失、schema 不符或未放行 | **STOP**。退回 Stage 1 补齐 `project.json`，不得用手填字段代替上游工件。 |
| `HOLD: ... input must contain only the reference-material input fields; unexpected=... missing=...` | 输入含未知字段或缺少契约字段 | **STOP**。按报错列出的字段名核对；`tier` / `downstream_flag` 由策略推导，不得手填。 |
| `HOLD: ... reference_id must be a non-empty string; record an explicit absence marker such as MISSING when no document exists` | 身份字段为空 | **STOP**。补真实身份；确实没有就写 `MISSING`，由策略将该卷宗记为 `UNRESOLVED`。 |
| `HOLD: ... selection_rung must be DIRECT_HISTORY or LONG_RUN_NO_EVENT to claim RESOLVED` | 声称 `RESOLVED` 却未声明阶梯层级 | **STOP**。声明真实层级；不足以支撑 `RESOLVED` 就改为 `UNRESOLVED`。 |
| `HOLD: ... evidence contains GAP` | 把"缺参照物"写成请求层 GAP | **STOP**。把缺口落到卷宗的 `resolution: UNRESOLVED`，请求层证据保持非 GAP。 |
| `HOLD: ... workspace naming: ...` | 工作区存在面板认不出的工件名 | **STOP**。按 `check_artifact_naming.py` 的报错改名，再重跑 preflight。 |
| `NOTE: ... recorded UNRESOLVED: known_bad history_evidence must bind at least one recorded failure to the mechanism it demonstrates` | Known Bad 的失效证据未绑定机理（如"高硫一般不好"） | 这是**预期结果**，不是可修复的错误。若找不到绑定机理的证据，保留 `UNRESOLVED`；禁止为凑 `RESOLVED` 编造机理。 |
| `GATE: no side RESOLVED ... -> decision HOLD; ... Stage 5 must not proceed` | 两侧都 `UNRESOLVED` | **保留工件并停在第 4 步**。这就是 WGO_001 的真实结局：`downstream_flag=DISCRIMINATION_EVIDENCE_INCOMPLETE` 会被第 5 步**硬拒绝**（不是继承状态）。Stage 4 的 `GO` 是必要不充分条件。 |
| `FAIL: ...: storage_sop is recorded as absent, so the dossier cannot be RESOLVED` | 落盘工件被手工改成 `RESOLVED` | **STOP**。恢复策略推导值，用 builder 重新生成；不得手改工件。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法损坏 | 检查 `../../schemas/` 与输入文件 JSON 格式。 |

---

## 4. Red Lines & Blacklist (Strict Prohibition)

1. **NO Invented Reference Materials**: DO NOT fabricate a sample, lot, supplier, SOP number or safety sheet to make a side look resolved. A material that does not exist is recorded `UNRESOLVED` at rung 3.
2. **NO Unbound Failure Evidence**: DO NOT record a Known Bad as `RESOLVED` on a general statement. Its failure must bind the mechanism it demonstrates (`<MECHANISM-ID>: <statement>`); `MECHANISM-NONE` binds nothing and cannot establish a Known Bad.
3. **NO Bypass of Preflight**: DO NOT create, move, or touch the output artifact before `preflight_reference_material.py` has passed. An invalid request produces no artifact at all.
4. **NO Dirty Overwrites**: DO NOT overwrite an existing `reference.json` on a validation failure, and do not commit a second record under a taken canonical name. A failed run changes nothing on disk.
5. **NO Soft Guidance Words**: forbidden ambiguous words: "灵活调整", "视情况而定", "酌情设置", "可以考虑". Dossiers carry concrete identities, rungs and references.
6. **NO Cross-Stage Mutation**: DO NOT qualify a test method, compute discrimination, design a formula, plan bench slots, or advance the state machine here. Stage 4 records the reference set and stops.
7. **NO Hand-Set Tier or Flag**: DO NOT write `tier` or `downstream_flag`. Both are derived by `reference_material_policy` and re-asserted on validation.
8. **NO Suppressed Incompleteness**: DO NOT hide a `DISCRIMINATION_EVIDENCE_INCOMPLETE` state, and DO NOT present a SYNTHETIC reference record as a physical reference set.
