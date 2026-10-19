---
name: formulation-design
description: Define one evidence-bound, testable design space at DESIGN_SPACE_DEFINED for lubricant formulation; preflight verifies upstream stage artifacts (project, challenge, failure CTQ, qualified test method), input bounds, material references, and the baseline process before building the artifact. Use when user mentions "formulation-design", "配方设计", "设计空间", "design space", "定义设计空间", "材料属性表", "基准工艺", "可行性区域", "ISO VG", or advancing lubricant R&D to DESIGN_SPACE_DEFINED.
---

# Formulation Design (DESIGN_SPACE_DEFINED)

Define an evidence-bound, testable design space record at `DESIGN_SPACE_DEFINED` for the Lubricant R&D Domain Pack.
Authority schema: `../../schemas/design_space.schema.json` (or local `references/design_space.schema.json` in deployed bundle).

---

## 1. Input Specification

Input must be a single JSON object containing exact upstream artifact paths and the target `design_space` specification:

`challenge_artifact` is required on the six oil routes. The `PRECISION_GREASE_DEV` route
carries no `CHALLENGES_DEFINED` step (`contracts/state-machine.json` puts it on no
`type_route`), so that route may omit the key: the preflight prints a `NOTE:` line instead
of demanding the artifact, and the built record carries the recorded-gap sentence
(`UNROUTED:<project_id>`) as `ASSUMED` evidence. Supplying a challenge artifact on either
route behaves exactly as before.

```json
{
  "project_artifact": "path/to/project_defined.json",
  "challenge_artifact": "path/to/challenges_defined.json",
  "failure_ctq_artifact": "path/to/failure_ctq_defined.json",
  "test_method_artifact": "path/to/test_methods_qualified.json",
  "design_space": {
    "design_space_id": "DS-WGO-001",
    "scope": "ISO VG 320 wind turbine gear oil formulation candidate window",
    "variables": [
      {
        "variable_id": "VAR-PAO-BASE",
        "variable_type": "MATERIAL_FAMILY",
        "lower_bound": {
          "value": 50.0,
          "unit": "wt%",
          "source": "SPEC-DOC-001",
          "method_version": "v1.0",
          "material_batch": "BATCH-202608-01",
          "formula_version": "v0.1"
        },
        "upper_bound": {
          "value": 85.0,
          "unit": "wt%",
          "source": "SPEC-DOC-001",
          "method_version": "v1.0",
          "material_batch": "BATCH-202608-01",
          "formula_version": "v0.1"
        },
        "constraint_rationale": "Viscosity blending balance requirement"
      }
    ],
    "ctq_references": ["CTQ-FZG-MICROPITTING"],
    "qualified_test_method_references": ["TM-FZG-001"],
    "constraints": ["sum(variables.wt%) == 100.0"],
    "evidence": [
      {
        "evidence_id": "EV-DS-001",
        "status": "VERIFIED",
        "scope": "PHYSICAL",
        "rationale": "Base oil and additive boundaries verified against bench data."
      }
    ]
  }
}
```

### Field Invariants
- Upstream alignment: All 4 upstream artifacts must share the same `project_id`, `decision: "GO"`, and status `ACTIVE`.
- Chain of custody: `failure_ctq_artifact.challenge_reference == challenge_artifact.challenge_id`, and `test_method_artifact.target_failure_reference == failure_ctq_artifact.failure_id`.
- Test method qualification: `test_method_artifact.qualification_status` must be `"QUALIFIED"`.
- Variable integrity: Each variable requires complete measurement metadata (`value`, `unit`, `source`, `method_version`, `material_batch`, `formula_version`).
- Bound ordering: `lower_bound.value <= upper_bound.value` with identical `unit`. Non-finite values (`NaN`, `Infinity`) are rejected.

---

## 1a. The Grease Route: Four Sub-Blocks and Three Feasibility Traps

The `PRECISION_GREASE_DEV` route (outer-loop step 6) declares where to look with four sub-blocks. These requirements are enforced in the POLICY LAYER on the upstream `project_type`, so the six oil routes keep their exact input shape and behaviour.

| Sub-block | Field | Requirement |
|---|---|---|
| Material property table | `variables[].material_reference` | Each material-bearing variable references a `material` object, and the referenced `material_id` must resolve to a readable record. A bare name string is no longer acceptable for grease: without the object there is no supplier, lot, chemistry family, or property list, so the variable cannot be compared or reproduced. |
| Charge vs product | `variables[].role` in `{INPUT_MATERIAL, REACTION_PRODUCT}` | Every material-bearing variable declares which it is. |
| Process variables | `variables[]` with `variable_type: PROCESS_VARIABLE` | The kettle settings live here, not inside the formulation. |
| Baseline process | `baseline_process_reference` | REQUIRED. If the process changed, comparing formulae is invalid: two fraction lists run over different kettle settings are not the same experiment. |
| Feasibility structure | `constraints` (object form) and `feasibility_regions` | Bounds alone cannot express "this region is structurally infeasible". |

### The in-situ reaction semantics

Grease soap is **generated**, not charged: fatty acid plus LiOH react during saponification. A "thickener percentage" is therefore a **product** of the batch, not an input. A 100 % mixture closure closes the **CHARGE**, and that constraint does not hold for what determines the product — the charged fatty acid and base are not the substances the batch contains. Consequences enforced here:

- A variable over an in-situ feedstock (`THICKENER_RAW`, e.g. the fatty acid) is a `REACTION_PRODUCT`. Marking it `INPUT_MATERIAL` is rejected.
- `REACTION_PRODUCT` is **never** classified `MIXTURE_CLOSED` in the shared `scripts/constraint_role.py` resolver: both the derived role and an explicit `MIXTURE_CLOSED` declaration are refused.
- A declared `MIXTURE_CLOSURE_INPUTS` constraint closes the charge side only; the preflight prints which side the closure applies to so a run is never silent about it.

### The coupling warning

The real feasible region is a **coupled non-linear manifold, not a box**:

- Changing **soap concentration** simultaneously changes consistency, dropping point, oil separation, and low-temperature torque.
- Changing **base-oil viscosity** changes both consistency (thickener efficiency depends on the base oil) and torque.

A box of independent bounds therefore overstates the feasible set. Record the coupling in the `constraint_rationale` of each coupled variable and express the region structure in `feasibility_regions`; do not present independent boxes as if the axes were free.

### The three feasibility traps

1. **In-situ reaction**: the soap is a product, so the charge closure does not govern the product composition (see above).
2. **Coupling**: the variables interact; a bound on one is not a bound on the outcome.
3. **Non-convex / disconnected**: some soap/oil combinations simply do not form a stable grease. Bounds cannot express that. Declare it in `feasibility_regions`, using `convexity` and `connected` per region, and write a disconnected set as more than one region rather than as a box that silently claims the gap between them.

---

## 2. Deterministic Execution Workflow

All scripts reside in `skills/formulation-design/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
Always run preflight before creating or modifying any artifact:
```bash
python skills/formulation-design/scripts/preflight_formulation_design.py <input.json>
```
- Expected output on success: `READY: input can form one DESIGN_SPACE_DEFINED record only` (exit code 0).
- If preflight fails: Output starts with `HOLD: missing or invalid: ...; no artifact generated` (exit code 1). See Section 3 for error recovery.

### Step 2: Build Deterministic Artifact
Run the builder only after Step 1 passes:
```bash
python skills/formulation-design/scripts/build_design_space_artifact.py <input.json> <temporary-file.json>
```
The builder generates canonical decision fields (`decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`, `decision`, `next_action`).

### Step 3: Validate Artifact
Validate schema and policy conformance:
```bash
python skills/formulation-design/scripts/validate_design_space_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: deterministic design-space artifact conforms to the Stage 4 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to the target artifact path only when Step 3 returns `PASS`. **Naming rule**: if `design_space.json` does not yet exist in the workspace root, commit this record as `design_space.json`; otherwise commit it as `design_space-<project_id>-<design_space_id>.json`. That is, the first record of this stage occupies the canonical name `design_space.json` (the stage-gate panel uses this exact name to mark the stage complete), and subsequent records of the same stage are appended as suffixed names carrying the record ID. After the commit, run `python scripts/check_artifact_naming.py <workspace_root>` and correct any `HOLD` before proceeding. The checker also enforces that `project.json`'s `stage` stays the constant `PROJECT_DEFINED` — it is NOT the project's current stage, and must not be advanced.
```bash
# 🔴 CHECKPOINT · STOP: the design space stops here at DESIGN_SPACE_DEFINED. Next station: BENCH_RESOURCE_REGISTERED (PRECISION_GREASE_DEV, bench-registration) or EXPERIMENT_DESIGNED (oil routes, doe-design).
```

---

## 3. Failure Modes & Fallback Recovery (Fail-Closed)

When any check fails, strictly follow the fallback table. Do NOT retry blindly.

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: missing or invalid: test_method_artifact must have decision GO` | 上游测试方法评定为 HOLD 或未通过 | **STOP**。不得创建设计空间。退回 Stage 3（`test-method-qualification`）要求补齐物理标定证据。 |
| `HOLD: missing or invalid: lower_bound > upper_bound` | 变量上下界逻辑倒置 | **STOP**。输出报错变量名与数值，要求用户校验物性限值并修复 input JSON，不猜测默认值。 |
| `HOLD: missing or invalid: project_id values must match` | 跨项目混用工件 | **STOP**。检查 4 个输入工件路径，确认归属于同一 project_id。 |
| `HOLD: ... material_reference is required on the PRECISION_GREASE_DEV route` | 材料只写了名称字符串 | **STOP**。要求提供 `material` 对象（供应商/牌号/批号/化学族/属性表），不接受裸字符串。 |
| `HOLD: ... material_reference: X does not resolve to a readable material record` | 引用的 material_id 不存在 | **STOP**。核对 material 工件路径与 `material_id`，不得凭空补一条材料。 |
| `HOLD: ... baseline_process_reference is required on the PRECISION_GREASE_DEV route` | 未声明本轮固定工艺基线 | **STOP**。补齐基准工艺引用。工艺变了，配方比较无效。 |
| `HOLD: ... is generated in situ by saponification, so it is a REACTION_PRODUCT and must not be declared INPUT_MATERIAL` | 把原位反应产物当投料 | **STOP**。皂是生成的产物，不是投料；改标 `REACTION_PRODUCT`，并注意混料闭合只闭合投料侧。 |
| `HOLD: missing or invalid: design_space.evidence contains GAP` | 证据链存在未解缺口 | **STOP**。保持 `decision: HOLD`，生成 gap 诊断报告，等待实验补足后再重试。 |
| `FAIL: cannot read artifact or schemas` | Schema 路径缺失或 JSON 语法损坏 | 检查 `../../schemas/` 与输入文件 JSON 格式，修复语法错误。 |

---

## 4. Red Lines & Blacklist (Strict Prohibition)

This skill operates strictly under Stage 4 boundaries. The following actions are prohibited:

1. **NO Forward Inference**: DO NOT invent, hallucinate, or infer missing bounds, additive ratios, formula percentages, material batches, or sources.
2. **NO Cross-Stage Mutation**: DO NOT generate DOE designs (Stage 5), blend recipes, candidate ratios, experiment matrices, or cost calculations in this skill.
3. **NO Bypass of Preflight**: DO NOT create or touch `<output.json>` directly without running `preflight_formulation_design.py` first.
4. **NO Dirty Overwrites**: DO NOT overwrite existing target artifacts if validation fails or yields non-zero exit codes.
5. **NO Soft Guidance Words**: Forbidden ambiguous words: "灵活调整", "视情况而定", "酌情设置", "可以考虑". All bounds and parameters must be concrete numbers and verifiable metadata.
6. **NO Bare Material Names**: DO NOT record a material-bearing variable as a name string. It must reference a `material` object whose `material_id` resolves.
7. **NO Product as Charge**: DO NOT mark an in-situ reaction product (grease soap, and anything a reaction generates) as a charged input. The charge closure does not hold for what determines the product.
8. **NO Box for a Coupled Region**: DO NOT present independent per-axis bounds as if the axes were free, and DO NOT hide a disconnected feasible set inside a single box. Record the coupling and the region structure.
9. **NO Undeclared Baseline Process**: DO NOT define a grease design space without the fixed process baseline for the iteration round.

