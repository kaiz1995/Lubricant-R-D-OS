---
name: project-definition
description: Turn a complete lubricant R&D project brief into a traceable Project Charter at PROJECT_DEFINED; hold without writing an artifact when required inputs are missing.
---

# Project Definition

Create only the Stage 0 Project Charter. This is a decision record, not a formulation, performance claim, Challenge Map, or downstream-stage artifact.

Use `../../schemas/project.schema.json` as the source-pack authority when it is available. The installed deployment includes an identical `references/project.schema.json` and `references/common.schema.json` copy for validation; it is a deployment copy, not a second maintained schema.

## Interaction Protocol: Work Nature Classification & Confirmation

Before requesting detailed charter fields or assuming a standard new-product pipeline, the Agent MUST establish and confirm the `project_type` with the user.

The 5 supported development project types:
1. `NEW_PRODUCT` (新产品正向开发): 需求与工况驱动，经历 7 项完整工况分析、失效/CTQ、测试方法鉴定、混料DOE、优化与验证冻结。
2. `IMPROVEMENT` (已有产品性能优化): 现场失效与痛点驱动，基于成熟基线产品，重点诊断失效模式、验证评定方法灵敏度、针对性优化瓶颈指标。
3. `COST_DOWN` (降本替代): 非劣效性驱动 (Non-inferiority)，基于现有配方与成本基线，重点划定 CTQ 不劣化红线、原材料属性匹配与等效验证。
4. `CUSTOMIZATION` (客户定制): 客户技术协议与OEM专属工况驱动，对齐协议技术指标与指定台架，匹配现有成熟平台并微调。
5. `EXPLORATION` (机理/平台型探索): 科学假设驱动，允许失败，重点考察变量影响规律与机理模型，不以单一商业量产目标为死限。

### Interaction Rule
- **Mode A (自然语言预判与确认)**: If the user provides preliminary project description or files, the Agent analyzes the background, infers the most likely type, presents the rationale, and asks the user to confirm:
  > "根据您的项目信息，本项目判定为【XX】性质的开发工作。请确认是否以此类型启动？（可选选项：1. 新产品正向开发 2. 已有产品性能优化 3. 降本替代 4. 客户定制 5. 机理/平台型探索）"
- **Mode B (主动提示用户选择)**: If the user asks to start a project without sufficient background, the Agent presents the 5 types and asks the user to choose before requesting structured inputs.
- **Never dump all fields in one shot**: Do NOT dump a 10+ field form or ask for 7-item duty conditions simultaneously. Only prompt for the inputs relevant to the confirmed project type.

## Required input

Require all of these before creating an artifact:

- `project_id` (letters, digits, `.`, `_`, `-` only), `project_name`, `project_type` (`NEW_PRODUCT`, `IMPROVEMENT`, `COST_DOWN`, `CUSTOMIZATION`, `EXPLORATION`, or `CORRECTIVE_ACTION`), and `product_family`.
- `business_objective`, `technical_objective`, non-empty `hard_constraints`, and non-empty `success_criteria`.
- `target_cost` with `value`, `unit`, `source`, `method_version`, `material_batch`, and `formula_version`. (For `EXPLORATION`, value can be 0 or research budget with unit `CNY`, source `research_budget`, material_batch `not_applicable`, formula_version `not_applicable`).
- Non-empty `benchmark_products` (for `EXPLORATION`, baseline chemistry reference), `risk_class` (`LOW`, `MEDIUM`, `HIGH`, or `STRATEGIC`), and `owner`.
- Non-empty `source_evidence`; every item must include `evidence_id`, `statement`, `source`, and `status: OBSERVED`. The statement and source must identify the supplied requirement, brief, or record.

Run `python scripts/preflight_project_definition.py <input.json>` first. Do not treat a plausible product assumption as a supplied input.

## HOLD rule

If any required input is absent, blank, invalid, or lacks source evidence, report `HOLD`, list each missing or invalid field, and state that no Project Charter was created. Do not write a partial artifact, infer a target cost, invent a benchmark, or turn a gap into a conclusion.

## Artifact

For valid input, write valid UTF-8 JSON to the user-specified output path, or `project.json` in the current workspace when no path is specified. Before overwriting an existing file, read it: overwrite only if it is JSON with `artifact_type: "project"` and the same `project_id`; otherwise report the exact conflict and do not write.

Create one artifact that conforms to the project schema with:

- `artifact_type: "project"`, `schema_version: "0.1.0"`, `stage: "PROJECT_DEFINED"`, and `status: "ACTIVE"`.
- The supplied project fields and `source_evidence` copied into `evidence` without invented evidence.
- Public decision fields with these exact keys: `decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`, `decision`, and `next_action`. Do not use `gate_0_question`, `charter_scoping_hypothesis`, or `rule` as aliases or substitutes. The question concerns proceeding to downstream work; the hypothesis scopes the charter; uncertainty states downstream conditions/hypotheses are not yet defined; the rule requires recorded goals, constraints, and success criteria; the result only records the charter; `decision` is `"GO"`; `next_action` routes to the appropriate next stage for the confirmed `project_type`.

Write the candidate to a temporary sibling JSON file first. Run `python scripts/validate_project_artifact.py <temporary-file>`; only on `PASS` atomically replace the intended output. If preflight or validation fails, delete no existing output, report the actual errors, and do not claim completion.

Do not state that a formula or performance target has been achieved, and do not create any Challenge, CTQ, test, design-space, experiment, optimization, gate-review, or freeze artifact.
