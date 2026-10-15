---
name: hello-lubricant
description: Interactive orientation and workspace diagnostic smoke skill for the Lubricant R&D Domain Pack. Inspects environment readiness, explains the 27-stage contract and its 7 project-type routes, and guides project setup. Use when user mentions "hello-lubricant", "润滑材料开发帮助", "研发体系导引", "环境检查", "润滑材料流程说明", or wants an overview of the lubricant R&D pipeline.
---

# Hello Lubricant (Orientation & Diagnostic Smoke Skill)

Orientation, environment diagnostic, and interactive onboarding guide for the Lubricant R&D Domain Pack.
Provides a roadmap of the shared stage contract `contracts/state-machine.json` (currently v1.0.0): 27 stages,
7 project-type routes, 1 on-demand stage and 1 inner-loop ring. Validates local schema/toolchain readiness.

---

## 1. Domain Pack Architecture Overview

The Lubricant R&D Domain Pack implements evidence-bound, scientific lubricant engineering on the shared
stage contract `contracts/state-machine.json`. Its 27 stages break down as: 23 sit on the 7 `type_routes`,
1 is on-demand by design (`PROCESS_WINDOW_DEFINED`, on no route), and `DRAFT` / `FROZEN` / `CLOSED` are
lifecycle stages.

The full forward-development route (`NEW_PRODUCT`) walks 12 stages:

```
[Stage 1: project-definition]       -> 立项与研发性质确认 (PROJECT_DEFINED)
  ↓
[Stage 2: duty-definition]          -> 7 项工况剖面录入与声明 (DUTY_DEFINED)
  ↓
[Stage 3: duty-challenge-analysis]  -> 工况挑战图谱映射 (CHALLENGES_DEFINED)
  ↓
[Stage 4: failure-ctq-analysis]     -> 失效假设与双限 CTQ (FAILURE_CTQ_DEFINED)
  ↓
[Stage 5: test-method-qualification] -> 台架方法区分度/预测度评定 (TEST_METHODS_QUALIFIED)
  ↓
[Stage 6: formulation-design]       -> 配方设计空间与质量守恒 (DESIGN_SPACE_DEFINED)
  ↓
[Stage 7: doe-design]               -> 受限混料实验规划 (EXPERIMENT_DESIGNED)
  ↓
[Stage 8: experiment-import]        -> 物理台架实测数据接入 (EXPERIMENT_RUNNING)
  ↓
[Stage 9: statistical-analysis]     -> ANOVA 响应面拟合建模 (MODEL_BUILT)
  ↓
[Stage 10: optimization]            -> 多目标权衡与帕累托优化 (OPTIMIZED)
  ↓
[Stage 11: gate-review]             -> 综合门禁决议评审与冻结 (VERIFIED)
  ↓
[Stage 12: application-validation]  -> 应用工件准入复检 (APPLIED)
```

---

## 2. Supported Development Routes (7 Project Types)

Route order and length are published by the contract — print a route instead of retyping it:

```bash
python skills/lubricant-rd-agent/scripts/route_step.py --list-stages PROCESS_ROBUSTNESS
python skills/lubricant-rd-agent/scripts/route_step.py --list-loop-edges PRECISION_GREASE_DEV
```

1. **NEW_PRODUCT** (新产品正向开发): 完整经历 12 步研发全链条。
2. **IMPROVEMENT** (已有产品性能优化): 跳过工况定义，由失效分析切入瓶颈指标（10 步）。
3. **COST_DOWN** (降本替代): 聚焦非劣效性 (Non-inferiority)，保留 CTQ 红线等效验证（8 步）。
4. **CUSTOMIZATION** (客户定制): 客户专属工况驱动，对齐技术协议与指定台架（8 步）。
5. **EXPLORATION** (机理/平台型探索): 科学假设驱动，允许失败，探究组分响应规律（7 步）。
6. **PROCESS_ROBUSTNESS** (工艺稳健性): 配方已定，只考工艺——跳过工况定义与挑战推导，不做多目标优化，以工艺窗口为主输出，末尾经 `APPLIED` 证明批次一致性（8 步）。
7. **PRECISION_GREASE_DEV** (精密传动脂开发): 第 7 条路线，**19 个 stage / 17 个工艺步骤**，分三环 —— 外环配方与工艺设计（8 步）、内环台架迭代（5 步，循环 N 轮）、收口（4 步）。内环只有两条契约声明的回边（`SCREENING_PASSED → BATCH_PRODUCED` REWORK；`VARIANCE_ASSESSED → BATCH_PRODUCED` LOOP_BACK），轮次上限 `max_iterations = 12`。**环间回退（如台架发现方法不可靠、判据不可达）系统仍 `DENY`**：没有 `BACKTRACK` 通道，只能人工判断 + 系统外决策 + 手工构造新工件（不留系统痕迹）。

Two capabilities sit outside every route: `PROCESS_WINDOW_DEFINED` is an on-demand stage on no route
(produced by `process-scale-up`, handing off to `VERIFIED`), while the grease route's step 15 uses its own
`PROCESS_SCALE_VALIDATED` and never reuses it.

---

## 3. Workspace Diagnostic Checks

To verify environment readiness before running project pipelines:

```bash
# 1. 验证所有基础 JSON Schema 完整性
python scripts/validate_schemas.py

# 2. 验证状态机流转契约
python scripts/validate_state_machine.py

# 3. 运行端到端链条验证
python tests/lubricant_e2e/test_stage_chain.py
```

```bash
# 🔴 CHECKPOINT · STOP: 若上述诊断脚本报错，先修复环境依赖再启动具体研发阶段。
```

---

## 4. Failure Modes & Fallback Actions

| Issue Symptom | Root Cause | Fallback Action |
|---|---|---|
| Schema 验证失败 | `schemas/` 目录缺失或 JSON 语法损坏 | 检查 `schemas/*.schema.json` 完整性，还原官方标准 schema。 |
| Python 依赖缺失 | 缺少 jsonschema, referencing 等核心库 | 运行环境已内建完整依赖，确认使用推荐的 Python 解释器。 |
| 无法确定项目路径 | 用户需求模糊不清 | 引导用户运行 `project-definition` 启动 Mode A/B 分类对话。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Production Mutation**: DO NOT write or overwrite production stage artifacts in this orientation skill.
2. **NO Stage Jumping Guidance**: NEVER advise users to skip required stage gates without conforming to their `project_type`.

