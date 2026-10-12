---
name: knowledge-archive
description: Close a project's knowledge at KNOWLEDGE_ARCHIVED by landing the six knowledge assets (recommended formula / feasible design space / critical failure boundaries / evidence package / material knowledge / model) as one knowledge_asset record, with CLOSED_KNOWLEDGE reachable only when all six are present and the evidence package is QUALIFIED, and SYNTHETIC projects capped at DRAFT forever. Use when user mentions "knowledge-archive", "知识入库", "知识资产", "六类知识资产", "CLOSED_KNOWLEDGE", "DRAFT_KNOWLEDGE", "知识沉淀", "知识检索索引", or advancing to Stage 17 in lubricant R&D.
---

# Knowledge Archive (Stage 17 · 知识入库)

Close the knowledge of a finished project at `KNOWLEDGE_ARCHIVED`: land the six knowledge
assets the redesign names as one `knowledge_asset` record, so later projects can retrieve
them. This is a structured archive, NOT a design freeze, NOT a release decision, and NOT a
product conclusion.

Authority schema: `../../schemas/knowledge_asset.schema.json` (or local
`references/knowledge_asset.schema.json` in the deployed bundle). Closure rule and
decision wording: `scripts/knowledge_archive_policy.py`.

Why this stage exists: the schema had **no producer at all** before this skill - the
retrieval module's own docstring recorded that "Nothing currently produces
`knowledge_asset`, so an empty index is the normal state". Walking the whole workflow ended
with knowledge nowhere to land. This skill is that missing producer.

**Going `DRAFT_KNOWLEDGE` is a legitimate, expected outcome - not a failure to be papered
over.** Better to record the five assets that exist and the one that does not than to
invent the sixth so the record looks closed.

---

## 1. Input Specification (contract in)

Input is a single JSON object: the upstream charter path, the caller's closure claim, the
six asset entries, the evidence scope, and the artifact-level evidence.

```json
{
  "project_artifact": "project.json",
  "asset_status": "CLOSED_KNOWLEDGE",
  "evidence_scope": "PHYSICAL",
  "knowledge_assets": {
    "recommended_formula": { "artifact_reference": "FORMULA-REC-PGD-001", "present": true },
    "feasible_design_space": { "artifact_reference": "DS-FEASIBLE-PGD-001", "present": true },
    "critical_failure_boundaries": { "artifact_reference": "CFB-PGD-001", "present": true },
    "evidence_package": {
      "artifact_reference": "EP-PGD-001",
      "present": true,
      "qualification_reference": "EQ-PGD-001",
      "qualification": "QUALIFIED"
    },
    "material_knowledge": { "artifact_reference": "MAT-KNOW-PGD-001", "present": true },
    "model": { "artifact_reference": "MODEL-PGD-001", "present": true }
  },
  "evidence": [
    {
      "evidence_id": "E-KA-PGD-001",
      "statement": "The closure evidence package is qualified.",
      "source": "qualification record EQ-PGD-001",
      "status": "OBSERVED"
    }
  ]
}
```

### Field Invariants (contract in)
- Upstream (hard): `project_artifact` is mandatory. It must validate against
  `schemas/project.schema.json`, be `stage: PROJECT_DEFINED`, `status: ACTIVE`,
  `decision: GO`, and carry the single `project_id` the archive inherits. Missing or
  invalid upstream = HOLD, nothing written.
- `asset_status`: the caller's CLAIM, `DRAFT_KNOWLEDGE` or `CLOSED_KNOWLEDGE`. It is
  downgrade-only: a claim the assets do not justify is recorded as `DRAFT_KNOWLEDGE` and
  the shortfall is printed as a NOTE. It is never upgraded.
- `evidence_scope`: `SYNTHETIC` or `PHYSICAL`. A SYNTHETIC record is capped at
  `DRAFT_KNOWLEDGE`, force-marked `SYNTHETIC_DEMO_ONLY`, and can never authorize stage
  advancement.
- `knowledge_assets`: exactly the six keys. Each entry carries `artifact_reference` and
  `present`; the `evidence_package` entry may also carry `qualification_reference` and
  `qualification` ∈ {`QUALIFIED`,`PROVISIONAL`,`UNQUALIFIED`}. An unknown field is a hard
  reject.
- `present: false` is a first-class recording: the asset is not available yet. Its
  `artifact_reference` must still carry an explicit absence marker (`MISSING`,
  `NOT_SUPPLIED`); a fabricated reference is the one failure this gate exists to prevent.
- `evidence`: non-empty, each item `evidence_id` / `statement` / `source` / `status`. A
  `GAP` status is a hard reject here - a missing asset belongs on its asset entry as
  `present: false`, not on the request as an open gap.
- DO NOT supply `synthetic_marker`: it is DERIVED from the evidence scope; supplying it is
  a hard reject (it is not part of the input field set).

### Closure Rule (derived, not asserted)
```
derived_status = CLOSED_KNOWLEDGE  iff  evidence_scope is PHYSICAL
                                  AND  all six assets present
                                  AND  evidence_package present, qualification QUALIFIED,
                                       with a qualification_reference
                 DRAFT_KNOWLEDGE   otherwise
recorded_status = CLOSED_KNOWLEDGE iff the claim is CLOSED_KNOWLEDGE and it is justified
                  DRAFT_KNOWLEDGE  otherwise (downgrade-only)
decision        = FREEZE  iff CLOSED_KNOWLEDGE and no artifact-level GAP
                  HOLD    otherwise
```
`DRAFT_KNOWLEDGE` is always legal. The six-asset requirement is not a formality: a knowledge
record missing the model asset cannot be reused for prediction, and one missing the
critical-failure boundaries cannot warn the next project away from a known wall.

### Red line (redesign §6.3): cost never enters a CTQ criterion
Cost is a CONSTRAINT, never a CRITERION. Its correct home is step 6 filter / step 14
constraint / step 16 ceiling check. An asset reference that declares itself a cost CTQ
(for example `CTQ-COST-MIN-001`) is a hard reject: archiving it would freeze the error into
every later retrieval.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/knowledge-archive/scripts/` (or relative `scripts/` from the
skill directory).

### Step 1: Preflight Verification
```bash
python -B skills/knowledge-archive/scripts/preflight_knowledge_archive.py <input.json>
```
- Validates the upstream charter, the six asset entries, the artifact evidence, the
  cost-criterion red line, and the workspace's artifact names.
- Success: prints `READY: input can form one KNOWLEDGE_ARCHIVED knowledge_asset record
  (N/6 assets present)`, then a `NOTE:` line whenever the claim will not be reached (exit 0).
- Failure: output starts with `HOLD: missing or invalid: ...; no artifact generated`
  (exit 1) and nothing is written.

### Step 2: Build Deterministic Artifact
```bash
python -B skills/knowledge-archive/scripts/build_knowledge_asset_artifact.py <input.json> <temporary-file.json>
```
The builder re-runs the preflight checks, then assembles the artifact from
`knowledge_archive_policy.py`: the six entries as supplied, the downgrade-only
`asset_status`, the derived decision block, and `stage = "KNOWLEDGE_ARCHIVED"`. A SYNTHETIC
record is force-marked. It never invents an asset, a qualification, or a closure.

### Step 3: Validate Artifact
```bash
python -B skills/knowledge-archive/scripts/validate_knowledge_asset_artifact.py <temporary-file.json>
```
- Validates against `schemas/knowledge_asset.schema.json` with its two `if/then` closure
  rules, then re-derives the whole policy from the artifact's own fields and asserts every
  field equals it.
- Success: `PASS: deterministic knowledge_asset artifact conforms to the knowledge-asset
  contract` (exit 0).
- A `DRAFT_KNOWLEDGE` artifact PASSES: it is a truthful record of an unfinished archive.

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3
returns `PASS`. **Naming rule**: if `knowledge_asset.json` does not yet exist in the
workspace root, commit this record as `knowledge_asset.json`; otherwise commit it as
`knowledge_asset-<project_id>-<archive-id>.json`. After the commit, run
`python scripts/check_artifact_naming.py <workspace_root>` and correct any `HOLD` before
proceeding. The checker also enforces that `project.json`'s `stage` stays the constant
`PROJECT_DEFINED` - it is NOT the project's current stage, and must not be advanced.
```bash
# 🔴 CHECKPOINT · STOP: Stage 17 stops here at KNOWLEDGE_ARCHIVED.
```

---

## 3. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: ... project_artifact ... must be PROJECT_DEFINED, ACTIVE, and GO` | 上游章程缺失、schema 不符或未放行 | **STOP**。退回 Stage 1 补齐 `project.json`，不得用手填字段代替上游工件。 |
| `HOLD: ... input must contain only the knowledge-archive input fields; unexpected=...` | 输入含未知字段（常见：手填了 `synthetic_marker`） | **STOP**。`synthetic_marker` 由证据口径推导，不得手填；按报错列出的字段名核对。 |
| `HOLD: ... asset_reference[n] '...' reads as a cost CTQ criterion` | 成本被写进 CTQ 判据 | **STOP**。成本只能进 `cost_ceiling`（约束）；把该资产引用改回技术判据，成本上限留在 Project charter。 |
| `HOLD: ... knowledge_assets must contain exactly the six assets; ... missing=...` | 六类资产块缺键 | **STOP**。缺的资产用 `present: false` + 显式缺失标记（`MISSING`）记录，不得删键、不得编造引用。 |
| `HOLD: ... evidence contains GAP` | 把"缺资产"写成请求层 GAP | **STOP**。把缺口落到资产条目的 `present: false`，请求层证据保持非 GAP。 |
| `NOTE: CLOSED_KNOWLEDGE requires all six assets present; missing ... -> DRAFT_KNOWLEDGE` | 声称闭合但资产不足 | 这是**预期结果**，不是可修复的错误：工件以 `DRAFT_KNOWLEDGE` 落盘。补齐资产或证据包资质后再重跑；禁止为凑 `CLOSED_KNOWLEDGE` 编造资产。 |
| `NOTE: a SYNTHETIC project can never reach CLOSED_KNOWLEDGE ...` | 合成证据项目声明闭合 | 这是**预期结果**：合成项目永远只能 `DRAFT_KNOWLEDGE`（NO Synthetic Closure），工件带 `SYNTHETIC_DEMO_ONLY` 标记落盘。 |
| `FAIL: ... asset_status CLOSED_KNOWLEDGE is not justified by the artifact's own assets` | 落盘工件被手工改成 `CLOSED_KNOWLEDGE` | **STOP**。恢复策略推导值，用 builder 重新生成；不得手改工件。 |
| `FAIL: ... synthetic_marker is only legal on a SYNTHETIC record` | 手工给物理记录加上合成标记 | **STOP**。标记由证据口径推导，重新生成工件。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法损坏 | 检查 `../../schemas/` 与输入文件 JSON 格式。 |

---

## 4. Red Lines & Blacklist (Strict Prohibition)

1. **NO Synthetic Closure**: DO NOT let a SYNTHETIC project reach `CLOSED_KNOWLEDGE`, and DO NOT drop the `SYNTHETIC_DEMO_ONLY` marker. Synthetic evidence may validate the software chain, never close knowledge.
2. **NO Invented Assets**: DO NOT fabricate an asset reference, a qualification record, or a closure claim. An asset that does not exist is recorded `present: false` with an explicit absence marker.
3. **NO Cost Criteria**: DO NOT archive a cost identity as a CTQ criterion. Cost is a constraint (ceiling), never a criterion (redesign §6.3).
4. **NO Bypass of Preflight**: DO NOT create, move, or touch the output artifact before `preflight_knowledge_archive.py` has passed. An invalid request produces no artifact at all.
5. **NO Dirty Overwrites**: DO NOT overwrite an existing `knowledge_asset.json` on a validation failure, and do not commit a second record under a taken canonical name. A failed run changes nothing on disk.
6. **NO Cross-Stage Mutation**: DO NOT freeze the design, advance the state machine, close the project, or claim release approval here. This stage lands knowledge assets and stops.
7. **NO Hand-Set Status or Marker**: DO NOT write `asset_status` above what the assets justify, and DO NOT write `synthetic_marker`. Both are derived by `knowledge_archive_policy` and re-asserted on validation.
8. **NO Soft Guidance Words**: forbidden ambiguous words: "灵活调整", "视情况而定", "酌情设置", "可以考虑". Every asset carries a concrete reference and a concrete presence flag.
