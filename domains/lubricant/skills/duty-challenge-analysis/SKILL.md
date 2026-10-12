---
name: duty-challenge-analysis
description: Convert one validated lubricant duty profile into one traceable Challenge Map member at CHALLENGES_DEFINED; preflight verifies DUTY_DEFINED stage artifact and challenge evaluation dimensions before building the artifact. Use when user mentions "duty-challenge-analysis", "工况挑战分析", "精密脂工况挑战", "挑战图谱", "Challenge Map", "工况挑战", or advancing to Stage 2 in lubricant R&D.
---

# Duty Challenge Analysis (Stage 2)

Convert a validated lubricant duty profile into exactly one traceable Challenge Map member at `CHALLENGES_DEFINED` for the Lubricant R&D Domain Pack.
This is a tribological challenge analysis record, NOT a failure mechanism, CTQ, test plan, or formulation recipe.

Authority schema: `../../schemas/challenge.schema.json` (or local `references/challenge.schema.json` in deployed bundle).

---

## 1. Input Specification

A single JSON input object providing `duty_artifact`, `challenge`, and `challenge_evidence`:

```json
{
  "duty_artifact": "path/to/duty.json",
  "challenge": {
    "duty_reference": "DUTY-WGO-001",
    "challenge_id": "CHG-MICROPITTING-001",
    "category": "MECHANICAL_STRESS",
    "description": "High Hertzian contact pressure under low entrainment speed causing boundary film rupture",
    "severity": "HIGH",
    "exposure": "CONTINUOUS",
    "lubricant_sensitivity": "CRITICAL",
    "evidence_gap": "NONE",
    "priority": "P1"
  },
  "challenge_evidence": [
    {
      "evidence_id": "EV-CHG-001",
      "statement": "Hertzian stress > 1.6 GPa promotes micropitting fatigue on planetary gears",
      "source": "Gearbox Teardown Failure Analysis Report 2025",
      "status": "OBSERVED"
    }
  ]
}
```

### Invariants
- Upstream validity: `duty_artifact` must be schema-valid with `stage: "DUTY_DEFINED"` and `decision: "GO"`.
- Explicit evaluations: `severity`, `exposure`, `lubricant_sensitivity`, and `priority` must be explicitly provided using schema enums. Never infer grades from general category.
- Evidence traceability: Each item in `challenge_evidence` requires `evidence_id`, `statement`, `source`, and `status: "OBSERVED"`.

---

## 1A. Route-Gated Challenge Categories

`schemas/challenge.schema.json` carries one shared `category` enum, which may only GAIN
values: the twelve original oil-route values stay valid for the six oil project types, and
eight grease values were appended. The route-specific rejection lives in the policy layer
(`scripts/duty_challenge_policy.py`), not in the shared contract.

### Grease route (`project_type: "PRECISION_GREASE_DEV"`)

Rejected — oil-only values that name no grease challenge (`HOLD: challenge.category
WATER_CONTAMINATION names no grease challenge ...`): `WATER_CONTAMINATION`, `AIR_FOAM`,
`MIXING`. A grease has no foam reservoir and no sump oil to mix; water ingress into a sealed
precision reducer reduces to sealing integrity, which the route records as
`INTERFACE_COMPATIBILITY` (duty side: `sealing_and_contamination`).

Recorded — the eight grease challenges:

| Category | Addresses |
|---|---|
| `FRETTING_WEAR` | Micro-oscillation damage at the flexspline reversal zones (the core harmonic-drive failure mode) |
| `THIN_FILM_EP` | Boundary-regime contact where the entrained film cannot reform between reversals |
| `LOW_TEMP_TORQUE` | Start-up torque rise from grease stiffening at the low-temperature end |
| `SHEAR_STABILITY` | Thickener structure worked down under sustained micro-oscillation |
| `SOAP_FIBER_STRUCTURE` | Soap-fiber network stability driving bleed rate and consistency |
| `INTERFACE_COMPATIBILITY` | Elastomer / plastic / coating (DLC) contact with the grease |
| `HIGH_TEMP_OIL_SEPARATION` | Base-oil bleed at the high-temperature end |
| `EVAPORATION` | Base-oil loss over maintenance-free life |

The shared values that still describe a grease challenge (e.g. `PARTICLE_CONTAMINATION` for
wear debris, `MATERIAL_COMPATIBILITY`) remain recordable; only the three named values are
rejected.

### How the project type is resolved
1. An explicit `project_artifact` on the input: its `project_type` decides.
2. Otherwise the shape of the validated duty artifact: a duty profile recording a dimension
   outside the legacy seven is a non-oil route (only the grease route has such dimensions).

Both signals can only ever ADD grease enforcement over an already grease-shaped input, so an
oil input resolves to the legacy path and behaves exactly as before.

### What the oil routes see
Unchanged: all twelve original categories, and the same `challenge.category is invalid`
string for an unknown value.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/duty-challenge-analysis/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/duty-challenge-analysis/scripts/preflight_duty_challenge.py <input.json>
```
- Expected output on success: `READY: input can form one CHALLENGES_DEFINED record only` (exit code 0).
- If preflight fails: Output starts with `HOLD: ...` (exit code 1).

### Step 2: Build Deterministic Artifact
```bash
python skills/duty-challenge-analysis/scripts/build_duty_challenge_artifact.py <input.json> <temporary-file.json>
```
Creates the candidate JSON with `stage: "CHALLENGES_DEFINED"`, retaining the 7 standard decision fields (`decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`, `decision: "GO"`, `next_action: "Define failure and CTQ relationships."`).
The builder re-checks the category against the policy set for this route at the construction boundary, so it can never assemble a grease record around an oil-only category.

### Step 3: Validate Artifact
```bash
python skills/duty-challenge-analysis/scripts/validate_duty_challenge_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: challenge artifact conforms to the Stage 2 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` only after Step 3 passes. **Naming rule**: if `challenge.json` does not yet exist in the workspace root, commit this record as `challenge.json`; otherwise commit it as `challenge-<project_id>-<challenge_id>.json`. That is, the first record of this stage occupies the canonical name `challenge.json` (the stage-gate panel uses this exact name to mark the stage complete), and subsequent records of the same stage are appended as suffixed names carrying the record ID. After the commit, run `python scripts/check_artifact_naming.py <workspace_root>` and correct any `HOLD` before proceeding. The checker also enforces that `project.json`'s `stage` stays the constant `PROJECT_DEFINED` — it is NOT the project's current stage, and must not be advanced.
```bash
# 🔴 CHECKPOINT · STOP: Stage 2 stops here at CHALLENGES_DEFINED. Route to Stage 3 (failure-ctq-analysis).
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: duty_artifact is missing or decision is not GO` | 上游工况未定义或未通过门禁 | **STOP**。退回 Stage 1（`duty-definition`）完成工况定义并取得 GO。 |
| `HOLD: missing challenge field [severity/exposure/...]` | 挑战评估维度缺失 | **STOP**。要求用户提供完整的严重度与敏感度评估，不猜测等级。 |
| `HOLD: challenge.category WATER_CONTAMINATION / AIR_FOAM / MIXING names no grease challenge` | 精密脂路线使用了油专属词表 | **STOP**。这三类对脂无意义（无泡沫储层、无混油、密封件内进水归并为密封完整性）。改记 `INTERFACE_COMPATIBILITY`（界面/介质侵入）或其余七个脂类挑战；不得退化为通用油气挑战。 |
| `HOLD: challenge_evidence lacks OBSERVED status` | 挑战依据缺少真实观测凭据 | **STOP**。要求补足现场拆解失效记录或技术文献来源。 |
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 错误 | 检查输入文件与 `../../schemas/challenge.schema.json`。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Forward Mapping**: DO NOT map into specific Failure CTQ metrics, test standards, or additive packages in Stage 2.
2. **NO Synthetic Grading**: DO NOT automatically grade severity or sensitivity without input statements.
3. **NO Premature Solutions**: DO NOT propose base oil viscosity or additive chemistry here.
4. **NO Dirty Overwrites**: DO NOT overwrite existing challenge files with mismatched `project_id` or `challenge_id`.
5. **NO Oil-Shaped Grease Challenges**: On the grease route, DO NOT record `WATER_CONTAMINATION`, `AIR_FOAM` or `MIXING`. They stay legal for the six oil routes only; a grease record that carries one is rejected rather than relabelled.

