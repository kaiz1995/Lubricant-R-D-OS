---
name: project-definition
description: Turn a complete lubricant R&D project brief into a traceable Project Charter at PROJECT_DEFINED; preflight verifies project classification, objectives, constraints, cost target, benchmarks, and evidence. Use when user mentions "project-definition", "项目立项", "立项章程", "Project Charter", "新项目启动", or starting Stage 0 in lubricant development.
---

# Project Definition (Stage 0)

Create only the Stage 0 Project Charter (`PROJECT_DEFINED`) for the Lubricant R&D Domain Pack.
This is a scoping and governance decision record, NOT a formulation, performance claim, Challenge Map, or downstream artifact.

Authority schema: `../../schemas/project.schema.json` (or local `references/project.schema.json` in deployed bundle).

---

## 1. Project Type Classification & Interaction Protocol

Before requesting detailed charter fields or assuming a standard new-product pipeline, the Agent MUST establish and confirm `project_type` with the user.

Supported Development Project Types:
1. `NEW_PRODUCT` (新产品正向开发): 需求与工况驱动，经历 7 项完整工况分析、失效/CTQ、方法评定、混料DOE、优化与验证冻结。
2. `IMPROVEMENT` (已有产品性能优化): 现场失效驱动，基于成熟基线产品，重点诊断失效模式、验证评定方法灵敏度、优化瓶颈指标。
3. `COST_DOWN` (降本替代): 非劣效性驱动 (Non-inferiority)，基于现有配方与成本基线，重点划定 CTQ 不劣化红线、原材料属性匹配与等效验证。
4. `CUSTOMIZATION` (客户定制): 客户技术协议与OEM专属工况驱动，对齐协议技术指标与指定台架，匹配现有成熟平台并微调。
5. `EXPLORATION` (机理/平台型探索): 科学假设驱动，允许失败，重点考察变量影响规律与机理模型，不以单一商业量产目标为死限。

### Interaction Rule
- **Mode A (自然语言预判与确认)**: 若用户已有初步描述，分析背景后推荐最可能类型并请用户确认：
  > "根据您的项目信息，本项目判定为【XX】性质的开发工作。请确认是否以此类型启动？（1. 新产品正向开发 2. 已有产品性能优化 3. 降本替代 4. 客户定制 5. 机理/平台型探索）"
- **Mode B (主动提示用户选择)**: 若无足够背景，展示 5 种类型让用户选择后再索取输入。
- **No Form Dumping**: 禁止一次性堆叠索取全部 10+ 字段或工况参数，仅按确认的项目类型逐步索取核心输入。

---

## 2. Input Specification

A valid input JSON requires:
- `project_id` (alphanumeric, `.`, `_`, `-`), `project_name`, `project_type` (one of the 5 valid types), `product_family`.
- `business_objective`, `technical_objective`, non-empty `hard_constraints`, and non-empty `success_criteria`.
- `target_cost` containing complete measurement metadata (`value`, `unit`, `source`, `method_version`, `material_batch`, `formula_version`).
- Non-empty `benchmark_products`, `risk_class` (`LOW`, `MEDIUM`, `HIGH`, `STRATEGIC`), and `owner`.
- Non-empty `source_evidence` with status `OBSERVED`.

---

## 3. Deterministic Execution Workflow

All scripts reside in `skills/project-definition/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/project-definition/scripts/preflight_project_definition.py <input.json>
```
- Expected output on success: `READY: input can form one PROJECT_DEFINED record only` (exit code 0).
- On failure: Outputs missing/invalid fields and exits with code 1.

### Step 2: Build Project Charter Artifact
Create temporary candidate JSON with `stage: "PROJECT_DEFINED"`, `status: "ACTIVE"`, and the 7 canonical decision fields (`decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`, `decision: "GO"`, `next_action`).

### Step 3: Validate Artifact
```bash
python skills/project-definition/scripts/validate_project_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: project artifact conforms to the Stage 0 contract` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` (defaults to `project.json`) only after Step 3 passes.
```bash
# 🔴 CHECKPOINT · STOP: Stage 0 stops here at PROJECT_DEFINED. Route to next stage according to project_type.
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: missing required fields: project_type` | 未确认项目性质 | **STOP**。暂停并启动 Mode A/B 协议向用户确认项目分类。 |
| `HOLD: missing measurement metadata for target_cost` | 目标成本缺乏量化依据/版本 | **STOP**。要求用户提供明确成本上限数值与货币单位，不推测默认值。 |
| `HOLD: source_evidence contains GAP or missing` | 缺少输入证据或立项依据不足 | **STOP**。要求提供立项技术简报或客户协议编号，不伪造证据条目。 |
| `FAIL: cannot read artifact or schemas` | JSON 损坏或 schema 路径错误 | 校验文件编码与 JSON 语法，修复后重新运行校验。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Downstream Artifact Generation**: DO NOT create Duty, Challenge, Failure CTQ, Test Method, Formulation, DOE, or Optimization artifacts in Stage 0.
2. **NO Synthetic Assumptions**: DO NOT invent benchmark products, performance values, target costs, or evidence sources.
3. **NO Dirty Overwrites**: DO NOT overwrite existing non-project files or files with mismatched `project_id`.
4. **NO Silent Advance**: DO NOT proceed to Stage 1 without user confirmation of the Project Charter.

