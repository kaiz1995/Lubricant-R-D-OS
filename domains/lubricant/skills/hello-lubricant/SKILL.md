---
name: hello-lubricant
description: Interactive orientation and workspace diagnostic smoke skill for the Lubricant R&D Domain Pack. Inspects environment readiness, explains the 11 R&D stages, and guides project setup. Use when user mentions "hello-lubricant", "润滑油开发帮助", "研发体系导引", "环境检查", "润滑油流程说明", or wants an overview of the lubricant R&D pipeline.
---

# Hello Lubricant (Orientation & Diagnostic Smoke Skill)

Orientation, environment diagnostic, and interactive onboarding guide for the Lubricant R&D Domain Pack.
Provides a comprehensive roadmap of the 11-stage forward development lifecycle and validates local schema/toolchain readiness.

---

## 1. Domain Pack Architecture Overview

The Lubricant R&D Domain Pack implements evidence-bound, scientific lubricant engineering across 11 stages:

```
[Stage 0: project-definition]      -> 立项与 5 类研发性质确认 (PROJECT_DEFINED)
  ↓
[Stage 1: duty-definition]         -> 7 项工况剖面录入与声明 (DUTY_DEFINED)
  ↓
[Stage 2: duty-challenge-analysis] -> 工况挑战图谱映射 (CHALLENGES_DEFINED)
  ↓
[Stage 3: failure-ctq-analysis]    -> 失效假设与双限 CTQ (FAILURE_CTQ_DEFINED)
  ↓
[Stage 3.5: test-method-qualification] -> 台架方法区分度/预测度评定 (TEST_METHODS_QUALIFIED)
  ↓
[Stage 4: formulation-design]      -> 配方设计空间与质量守恒 (DESIGN_SPACE_DEFINED)
  ↓
[Stage 5: doe-design]              -> 受限混料实验规划 (EXPERIMENT_DESIGNED)
  ↓
[Stage 6: experiment-import]       -> 物理台架实测数据接入 (EXPERIMENT_RUNNING)
  ↓
[Stage 7: statistical-analysis]    -> ANOVA 响应面拟合建模 (MODEL_BUILT)
  ↓
[Stage 8: optimization]            -> 多目标权衡与帕累托优化 (OPTIMIZED)
  ↓
[Stage 9: gate-review]             -> 综合门禁决议评审与冻结 (VERIFIED)
```

---

## 2. Supported Development Routes (5 Project Types)

1. **NEW_PRODUCT** (新产品正向开发): 完整经历 11 步研发全链条。
2. **IMPROVEMENT** (已有产品性能优化): 跳过工况定义，由失效分析切入瓶颈指标。
3. **COST_DOWN** (降本替代): 聚焦非劣效性 (Non-inferiority)，保留 CTQ 红线等效验证。
4. **CUSTOMIZATION** (客户定制): 客户专属工况驱动，对齐技术协议与指定台架。
5. **EXPLORATION** (机理/平台型探索): 科学假设驱动，允许失败，探究组分响应规律。

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

