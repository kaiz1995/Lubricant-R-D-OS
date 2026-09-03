# Lubricant R&D OS — 润滑油产品开发 AI 助手

> 基于 [ai4s-research/open-science](https://github.com/ai4s-research/open-science) 的润滑油研发领域包，当前版本：**V0**

---

## 这是什么

**Lubricant R&D OS** 是一个运行在 [Open Science](https://github.com/ai4s-research/open-science) 桌面软件上的润滑油产品开发 AI 助手（Copilot）。

它不是"输入指标→AI自动给配方"的生成器。定位是：

> **把润滑油研发过程结构化**，让每一个开发决策都有证据支撑，每一步都可追溯、可审计、可复用。

## 背景：为什么需要这个

工业润滑油研发长期面临三个问题：

1. **缺乏体系**：主要靠逆向开发（剖析竞品→仿制小样→调整），没有统一的问题定义和决策规则。
2. **实验碎片化**：大量工作是"换一个添加剂"、"改一个比例"，实验之间缺少统一的设计空间和假设框架（OFAT 问题）。
3. **没有终点**：项目没有明确的阶段退出机制，同一课题年复一年持续，无法积累可复用的研发知识。

Lubricant R&D OS 的目标是把"经验式研发"升级为：

> **需求与工况驱动 → 失效风险驱动 → 证据驱动 → 实验设计驱动 → 商业决策驱动**

的可复用研发体系（Decision-Driven R&D Framework）。

## 它解决什么问题

| 原来的问题 | 本系统提供的结构化支撑 |
|---|---|
| 不知道为什么开发这个产品 | 项目章程（Project Charter）定义目标、约束、风险等级 |
| 不清楚设备工况和润滑挑战 | Duty/Challenge 分析，证据绑定，不允许编造 |
| 无法明确哪些性能最重要 | Failure/CTQ 分析，链接失效机制与关键质量特性 |
| 测试方法选择随意 | Test Method Qualification，有区分性和工况相关性验证 |
| 实验设计缺乏科学性 | DOE 结构化请求，混料设计，约束空间 |
| 分析和优化无标准流程 | 统计建模请求 + 优化请求，结构化交付 |
| 项目没有退出机制 | Gate Review，有明确的 VERIFIED/HOLD/FAIL 结论 |
| 知识无法沉淀复用 | 所有 artifact 都是 JSON schema 验证的结构化记录 |

## 它如何工作

本领域包以 **Skills（技能）** 的形式扩展 Open Science，每个 Skill 对应研发流程中的一个阶段：

```
Project Definition
  → Duty Definition（工况/设备）
    → Duty-Challenge Analysis（润滑挑战）
      → Failure/CTQ Analysis（失效机制/关键质量特性）
        → Test Method Qualification（测试方法鉴定）
          → DOE Design（实验设计）
            → Experiment Import（实验数据录入）
              → Statistical Analysis（统计建模）
                → Optimization（优化）
                  → Gate Review（阶段评审）
```

每一步由 AI 引导用户提供真实数据，生成 **schema 验证的 JSON artifact**，写入 Open Science workspace，并记录 provenance（来源追踪）。**所有 artifact 都必须有证据来源，不允许 AI 编造数据。**

`lubricant-rd-agent`（元技能路由器）确保：单步操作 ALLOW；跨阶段跳跃 DENY；没有物理证据时 HOLD 并列出缺口。

## Skills 列表

| Skill | 阶段 | 输出状态 | 说明 |
|---|---|---|---|
| `project-definition` | Stage 0 | `PROJECT_DEFINED` | 项目章程，含商业目标、技术目标、风险等级 |
| `duty-definition` | Stage 1 | `DUTY_DEFINED` | 设备工况、温度、负荷、维护、污染、寿命 |
| `duty-challenge-analysis` | Stage 1 | `CHALLENGES_DEFINED` | 润滑挑战 Map，severity/exposure/sensitivity 评级 |
| `failure-ctq-analysis` | Stage 2 | `FAILURE_CTQ_DEFINED` | 失效机制与关键质量特性，链接 Challenge |
| `test-method-qualification` | Stage 2 | `METHOD_QUALIFIED` | 测试方法鉴定，区分性与工况相关性验证 |
| `formulation-design` | Stage 3 | `DESIGN_SPACE_DEFINED` | 配方设计空间定义（约束混料） |
| `doe-design` | Stage 3 | `EXPERIMENT_DESIGNED` | DOE 请求，不生成实验点，只结构化请求 |
| `experiment-import` | Stage 3 | `EXPERIMENTS_RECORDED` | 实验数据录入，物理证据字段强制验证 |
| `statistical-analysis` | Stage 4 | `MODEL_BUILT` | 统计建模请求，不计算模型，结构化交付 |
| `optimization` | Stage 4 | `OPTIMIZED` | 优化请求，不生成候选配方，结构化交付 |
| `gate-review` | Gate | `VERIFIED` | 阶段评审，明确 GO/HOLD/KILL 结论 |
| `lubricant-rd-agent` | 元路由 | — | 路由所有技能，执行阶段隔离和证据锁 |

## 技术架构

Open Science Desktop（Tauri 2 + React + OpenCode Runtime）基础上的外挂领域包：

```
lubricant-rd-domain-pack/
├── skills/          ← 12 个研发阶段 Skill
├── schemas/         ← JSON Schema Draft 2020-12，10 种 artifact 契约
├── contracts/       ← 状态机 lifecycle/Gate 契约
├── scripts/         ← 安装器、校验器、Release preflight、仪表盘生成
├── tests/           ← 4 类直接测试（bundle / db / install / preflight）
├── domains/         ← SQLite 五表数据层
└── data/real_cases/ ← 真实案例目录（WGO_001 风电齿轮油，证据收集中）
```

**证据隔离**：所有数据都带 `evidence_scope` 标签（`SYNTHETIC` / `PHYSICAL`）。V0 仅允许 `SYNTHETIC_DEMO_ONLY` 范围的 artifact 打包发布；物理实验数据进来之前，系统自动 HOLD 相关 Gate。

## 快速开始

前提：Open Science Desktop v0.5.1+（[下载](https://github.com/ai4s-research/open-science/releases)）、Python 3.10+

安装 Skill：

```powershell
python scripts/install_domain_skill.py project-definition `
  --target "C:\Users\<用户名>\AppData\Roaming\com.ai4s.workbench\runtime\xdg-config\opencode\skills\user"
```

重启 Open Science Desktop 后，在「技能」页搜索 `project-definition` 即可看到。

验证（不依赖 Desktop）：

```powershell
python -B tests/test_workspace_bundle.py
python -B tests/test_lubricant_db.py
python -B tests/upstream_compat/test_skill_install.py
python -B tests/test_release_preflight.py
```

## 当前状态（V0）

| 检查点 | 状态 | 说明 |
|---|---|---|
| P0 安装路径保护 | ✅ PASS | 禁止覆盖受保护/符号链接目录 |
| P1 Synthetic Bundle | ✅ PASS | 物理数据混入自动拒绝 |
| P2 数据库原子性 | ✅ PASS | CSV 导入/碰撞拒绝/大数据上限 |
| P3 导入原子性 | ✅ PASS | 安装失败无残留，支持回滚 |
| P4 Release Preflight | ✅ PASS | 含 LICENSE、schema、bundle、12 Skill |
| P5 上游 v0.5.1 兼容 | ✅ PASS | 1166 测试通过，域包 4/4 PASS |
| P6 Desktop 实机验收 | ✅ PASS | 真实 Desktop 调用，provenance 闭环 |
| G5 真实数据 | ⏸ HOLD | 等待真实物理实验数据 |
| G6 发布签字 | ⏸ HOLD | 等待真实数据后补签 |

## 非目标（V0 不做的事）

- 不自动生成配方
- 不计算 DOE 实验点
- 不拟合统计模型
- 不提供 MCP Server 或独立 UI
- Phase 4 计算引擎已设计，尚未接入 Runtime

## 许可证

MIT — 见 [LICENSE](./LICENSE)

---

> **注意**：本仓库当前 V0 阶段，所有已验收的 artifact 均为 `SYNTHETIC_DEMO_ONLY` 范围，不代表任何真实产品性能或配方结论。