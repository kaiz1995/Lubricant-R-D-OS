# Lubricant R&D OS — 工业润滑油决策驱动研发操作系统

> **基于 [ai4s-research/open-science](https://github.com/ai4s-research/open-science) 架构的工业润滑油产品开发 AI Agent 领域包（Domain Pack）**  
> 当前版本：`V0` | 规范契约：`Draft 2020-12 JSON Schema` | 许可证：`MIT`

---

## 1. 这是什么（产品定位）

**Lubricant R&D OS** 是一套运行在 Open Science 科研工作台上的**工业润滑油产品开发决策助手（R&D Copilot & Operating System）**。

它**不是**一个简单的"输入几个技术指标，AI 自动吐出配方"的黑盒生成器。它的核心使命是：

> **把润滑油研发从"经验试错与逆向仿制"升级为"科学决策与证据闭环"**。  
> 让每一个配方决策都有工况证据支撑，每一次实验设计都最大化信息增益，每一个阶段流转都可追溯、可审计、可复用。

---

## 2. 研发背景与行业痛点

传统工业润滑油研发长期被三大痼疾困扰：

1. **重逆向、轻正向，缺乏体系化方法**：
   - 研发高度依赖"找竞品 → 剖析配方 → 仿制小样 → 台架试错"。逆向开发有参考价值，但不能成为研发主体。一旦工况变化或原料断供，缺乏推导逻辑导致无法自主应对。
2. **实验碎片化与经验式试错（OFAT 陷阱）**：
   - 习惯于"换个添加剂、改个比例、做个试验"的一次只改一个变量（OFAT）模式，缺少统一的设计空间、变量约束和假设检验框架。
3. **课题长流水，缺乏阶段退出与设计冻结机制**：
   - 降本、性能调整、原料替换年年持续，研发没有明确的终止条件（Stopping Rule）和设计冻结（Design Freeze）标准。
4. **"拿着未经校验的尺子量配方"**：
   - 很多台架试验和实验室评价方法本身缺乏工况相关性与区分度，导致用不灵敏的方法筛选配方，得出假阳性或假阴性结论。
5. **原料波动与牌号依赖**：
   - 过于依赖特定供应商的具体商品牌号，缺乏基于基础油物化描述符（粘度指数、极性、溶解度、烃组成）与功能模块的属性管理体系。

---

## 3. 核心研发哲学（Decision-Driven R&D）

本项目严格遵循决策驱动研发框架（Decision-Driven R&D Framework）：

* **润滑油不是在"通过标准"，而是在具体设备工况下承受特定挑战**：关注具体摩擦副、温度谱、载荷谱、污染与寿命。
* **研发目标是"风险控制 + 商业价值优化"，而非单一指标最优**：
  * **约束满足型产品**（常规工业油）：在满足 CTQ 与风险阈值的前提下，追求成本最低与供应链稳定（$Minimize\ Cost\ s.t.\ CTQ_i \ge Limit_i$）。
  * **综合价值型产品**（风电齿轮油、空压机油）：追求性能安全余量与关键失效机理的长期可靠性。
* **"先证明尺子可靠，再用尺子量配方"**：必须在研发早期对测试评价方法进行资格确认（Method Qualification），验证其区分性与工况相关性。
* **逆向开发的角色定位**：正向设计为主体，逆向分析仅作为边界核对与对比基线（Benchmark Calibration），而非开发起点。
* **证据级别与隔离铁律**：严禁 AI 编造数据，严格隔离合成占位数据（`SYNTHETIC`）与真实物理实验数据（`PHYSICAL`）。合成数据仅用于验证软件流转，物理放行必须依赖真实实验证据。

---

## 4. 五大类研发性质与差异化流程

工业润滑油开发不是一条死板流水线。系统在**项目定义阶段（Stage 0）**首先识别或引导用户确认项目的具体性质，并自动分流到匹配的专属流程：

| 研发性质 | 核心驱动逻辑 | 差异化阶段路径（Stage 流转） | 核心关注点与输入要求 |
|---|---|---|---|
| **1. 新产品正向开发**<br>(`NEW_PRODUCT`) | 需求与工况驱动 | `Project → Duty(7项) → Challenge → Failure/CTQ → Method Qual → Design Space → DOE → Running → Model → Opt → Gate` | 完整 7 大工况、润滑挑战映射、失效机理深度分析、混料空间与多目标优化。 |
| **2. 已有产品性能优化**<br>(`IMPROVEMENT`) | 现场失效与痛点驱动 | `Project → Failure/CTQ(问题诊断) → Method Qual(灵敏度) → Design Space → DOE → Running → Model → Opt → Gate` | **跳过全套工况重推**。聚焦现场真实失效证据，先验证评价方法灵敏度，再对瓶颈指标做定向配方改良。 |
| **3. 降本替代**<br>(`COST_DOWN`) | 非劣效性驱动<br>(Non-inferiority) | `Project → Failure/CTQ(非劣效红线) → Design Space → DOE → Running → Opt → Gate` | **不推新工况**。基于成熟基线配方与成本结构，划定 CTQ 不劣化底线，优化替代材料属性安全域。 |
| **4. 客户定制**<br>(`CUSTOMIZATION`) | 技术协议/OEM规范驱动 | `Project → Failure/CTQ(协议指标映射) → Method Qual(指定台架) → Design Space → DOE → Running → Gate` | 以客户技术协议和指定认证台架为准绳，快速匹配成熟平台做微调验证。 |
| **5. 机理/平台型探索**<br>(`EXPLORATION`) | 科学假设驱动 | `Project → Design Space → DOE → Running → Model → Gate` | **不考核商业 target_cost 和量产**。允许试错，重点提取变量影响规律与知识资产沉淀。 |

---

## 5. 系统架构设计

系统采用**解耦的三层架构**，确保通用科研底座与润滑油领域逻辑相互隔离，支持随上游 Open Science 持续平滑升级：

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Open Science 桌面工作台                         │
│       (Tauri 2 + React + OpenCode Agent Runtime + 本地工作区 + Provenance) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 调用 / 加载
┌───────────────────────────────────▼────────────────────────────────────┐
│                  Lubricant R&D Domain Pack (本仓库)                    │
│                                                                        │
│  [Stage 0-4 研发技能群 (12 Skills)]                                    │
│  - project-definition          - duty-definition                       │
│  - duty-challenge-analysis     - failure-ctq-analysis                  │
│  - test-method-qualification   - formulation-design                    │
│  - doe-design                  - experiment-import                     │
│  - statistical-analysis        - optimization                          │
│  - gate-review                 - lubricant-rd-agent (元路由器)          │
│                                                                        │
│  [数据契约与状态机]                                                    │
│  - Draft 2020-12 JSON Schemas (10类核心研发工件标准契约)                │
│  - 阶段状态机 (contracts/state-machine.json: ALLOW/DENY/HOLD 门控)     │
│                                                                        │
│  [数据层与计算引擎 (Phase 4)]                                          │
│  - SQLite 五表存储 (material / formula / test_method / experiment 等) │
│  - Cost Engine (原料成本核算)   - Mixture DOE Engine (混料极值设计)   │
│  - Statistics Engine (响应面回归) - Optimization Engine (Pareto 优化)    │
└────────────────────────────────────────────────────────────────────────┘
```

### 为什么选择基于 Open Science 开发？（核心优势）

工业润滑油配方属于核心商业机密，且研发决策依赖严谨的物理实验与数据溯源。相比使用通用聊天型 AI 或从零自研桌面软件，基于 Open Science 开发具备以下四大不可替代的底座优势：

1. **完整的科研数据血统追溯（Scientific Provenance）**：
   - *通用 Agent 痛点*：上下文窗口一旦压缩或会话结束，研发推导过程和参数逻辑丢失，成为不可审计的黑盒。
   - *Open Science 优势*：原生提供以 Run 和 Session 为核心的不可篡改执行追踪记录（`.openscience/provenance.jsonl`）。任何一个终版配方（如 Freeze Formula V7），均可向上无缝追溯至其数学优化模型、DOE 混兑点、物理实验批次、检验方法版本以及原料批次物化属性，满足严苛的工程审计要求。
2. **工业级数据隐私与离线闭环（Local-First Architecture）**：
   - *通用 Agent 痛点*：依赖云端 SaaS 交互，涉及企业绝密的基础油组分、添加剂配比、专有成本与客户工况面临泄密风险。
   - *Open Science 优势*：基于 Tauri 2 + 本地 SQLite + 本地沙箱文件系统，数据 100% 留存于企业内网或本地工作台。既可无缝对接本地离线开源大模型，也可在安全网络环境下接入商用模型，从物理层面隔离配方机密。
3. **开箱即用的专业科研基础设施（无需重复造轮子）**：
   - *通用 Agent 痛点*：从零开发桌面端交互、多模型适配、运行时进程管理和工具链调度需耗费团队 70% 以上的工程基建精力。
   - *Open Science 优势*：底座已完整封装跨平台桌面应用壳、OpenCode Agent Runtime、MCP 协议拓展支持、Python/Jupyter 计算执行环境与项目/会话隔离机制，使领域专家能 100% 聚焦于润滑油机理、DOE 算法与研发流程本身。
4. **LLM 语义路由与确定性科学计算的严格解耦**：
   - *通用 Agent 痛点*：直接让大模型捏造数字、估算粘度或拟合回归曲线，极易产生“看似合理但实际完全错误”的工程幻觉。
   - *Open Science 优势*：提供规范的 Skill 扩展协议与 Python 宿主运行能力。大模型仅作为“研发副驾驶”负责理解意图、结构化提取与语义解释；而配方成本、约束混料极值设计（Mixture DOE）、方差分析（ANOVA）与多目标优化等计算完全由独立的确定性数学引擎执行，确保数字严谨可信。

---

## 6. 12 个领域技能清单 (Skills)

每个 Skill 均可被 OpenCode 独立加载，并输出遵循标准 JSON Schema 的结构化工件：

| Skill 名称 | 所属阶段 | 输出状态 / 工件 | 关键功能与职责 |
|---|---|---|---|
| `project-definition` | Stage 0 | `PROJECT_DEFINED` | 引导用户确认 5 类研发性质，定义商业/技术目标、硬约束与项目章程。 |
| `duty-definition` | Stage 1 | `DUTY_DEFINED` | 结构化录入 7 大工况（设备、工况谱、维护、温度、负荷、污染、寿命）。 |
| `duty-challenge-analysis`| Stage 1 | `CHALLENGES_DEFINED` | 从工况推导润滑挑战 Map（严重度、暴露度、敏感度分级）。 |
| `failure-ctq-analysis` | Stage 2 | `FAILURE_CTQ_DEFINED` | 梳理失效机制与关键质量特性（CTQ），建立挑战到性能的映射链。 |
| `test-method-qualification` | Stage 2 | `TEST_METHODS_QUALIFIED` | 评价方法资格确认，验证测试方法与真实工况的相关性及区分能力。 |
| `formulation-design` | Stage 3 | `DESIGN_SPACE_DEFINED` | 建立基础油与添加剂混料设计空间，设定物理与化学约束边界。 |
| `doe-design` | Stage 3 | `EXPERIMENT_DESIGNED` | 结构化生成混料实验设计（D-Optimal / Extreme Vertices）评估请求。 |
| `experiment-import` | Stage 3 | `EXPERIMENT_RUNNING` | 录入实验测试观测结果，强制校验测试批次与物理溯源凭证。 |
| `statistical-analysis` | Stage 4 | `MODEL_BUILT` | 拟合回归与响应面模型，提供残差检验与模型解释力报告。 |
| `optimization` | Stage 4 | `OPTIMIZED` | 基于成本与 CTQ 模型执行多目标约束优化，给出候选配方推荐。 |
| `gate-review` | 评审门禁 | `VERIFIED` | 汇总阶段证据链，执行正式审查决策（GO / HOLD / PIVOT / KILL）。 |
| `lubricant-rd-agent` | 核心路由 | — | 元技能（Meta-Skill）路由器，执行跨阶段拦截、性质分流与证据门控。 |

---

## 7. 快速开始与使用指南

### 7.1 前置条件
- 已安装 [Open Science Desktop](https://github.com/ai4s-research/open-science/releases) v0.5.1 或更高版本
- 本地安装 Python 3.10+ 环境

### 7.2 安装领域包技能至 Open Science
在仓库根目录执行 PowerShell 命令，一键将 12 个领域技能部署到 Open Science Desktop 用户目录：

```powershell
# 将全部 12 个领域技能安装到 Desktop
python scripts/install_domain_skill.py --all `
  --target "C:\Users\<用户名>\AppData\Roaming\com.ai4s.workbench\runtime\xdg-config\opencode\skills\user"
```

安装完成后重启 Open Science 桌面端，在工作台「技能」面板中即可直接查看和使用。

### 7.3 软件侧离线自动化验证
领域包自带完整的无外部依赖原生测试套件，无需启动桌面端即可完成端到端验证：

```powershell
# 1. 验证工作区打包与数据范围安全隔离
python -B tests/test_workspace_bundle.py

# 2. 验证 SQLite 数据库原子性与数据上限
python -B tests/test_lubricant_db.py

# 3. 验证 12 个 Skill 部署兼容性
python -B tests/upstream_compat/test_skill_install.py

# 4. 验证元技能多流程分支路由逻辑
python -B tests/test_meta_skill_routing.py

# 5. 执行全量 Release 前置检查门禁
python -B tests/test_release_preflight.py
```

---

## 8. 当前项目状态与检查点

| 检查门禁 (Gate) | 当前状态 | 判定说明 |
|---|---|---|
| **P0: 安装路径保护** | ✅ PASS | 严格防范目录穿透与敏感路径覆盖，支持原子回滚。 |
| **P1: 合成数据打包** | ✅ PASS | `SYNTHETIC_DEMO_ONLY` 隔离闭环，物理数据混入自动拦截。 |
| **P2: 数据库原子性** | ✅ PASS | 事务写入、防公式注入、重复项拒绝均通过测试。 |
| **P3: 安装幂等性** | ✅ PASS | 安装失败零残留，环境指纹一致。 |
| **P4: 发布前置门禁** | ✅ PASS | Preflight 自动扫描全量 Schema、证书与测试套件。 |
| **P5: 上游合并兼容** | ✅ PASS | Open Science v0.5.1 代码合入，1166 项核心测试全绿通过。 |
| **P6: 桌面实机验收** | ✅ PASS | 真实 Desktop 会话调用成功，Provenance 链条闭环。 |
| **G5: 真实数据补全** | 🔄 IN PROGRESS | 依托 V600 风电齿轮油等真实课题实战推进中；PDS 基线与历史台架已录入，物理样品（B0）已调配，待实验室物理实测闭环。 |
| **G6: 物理发布签字** | ⏸ HOLD | 待真实物理数据（WGO_001 等）注入并完成完整台架验证后签署。 |

---

## 9. 目录结构说明

```
lubricant-rd-domain-pack/
├── contracts/               # 状态机与研发生命周期契约定义
│   └── state-machine.json
├── schemas/                 # 10 大核心研发工件 JSON Schema 规范 (Draft 2020-12)
│   ├── common.schema.json
│   ├── project.schema.json
│   ├── duty.schema.json
│   ├── challenge.schema.json
│   ├── failure_ctq.schema.json
│   ├── test_method.schema.json
│   ├── design_space.schema.json
│   ├── experiment_design.schema.json
│   ├── experiment.schema.json
│   └── gate.schema.json
├── skills/                  # 12 个独立研发阶段 Skill
│   ├── project-definition/
│   ├── duty-definition/
│   ├── duty-challenge-analysis/
│   ├── failure-ctq-analysis/
│   ├── test-method-qualification/
│   ├── formulation-design/
│   ├── doe-design/
│   ├── experiment-import/
│   ├── statistical-analysis/
│   ├── optimization/
│   ├── gate-review/
│   └── lubricant-rd-agent/  # 智能路由与阶段流转仲裁器
├── domains/lubricant/       # 领域计算引擎与数据管理
│   ├── db.py                # SQLite 五表数据层
│   ├── cost_engine.py       # 成本计算引擎
│   ├── mixture_doe.py       # 混料实验设计引擎
│   ├── statistics_engine.py # 回归建模引擎
│   └── optimization_engine.py# 多目标 Pareto 优化器
├── scripts/                 # 构建、安装、校验与仪表盘生成脚本
├── tests/                   # 自动化单元与集成测试套件
└── LICENSE                  # MIT 开源许可证
```

---

## 10. 许可证

本项目基于 [MIT License](./LICENSE) 协议开源。
