<div align="center">

[![Lubricant Science Desktop — Local-first AI research workbench](./docs/assets/banner.webp)](https://github.com/ai4s-research/open-science)

# Lubricant Science Desktop

**Local-first, model-agnostic AI research workbench for macOS, Windows & Linux.**

Formerly Lubricant Science. An open-source desktop alternative to Claude Science and
similar AI-for-science workbenches — built with Tauri, MCP, agent skills, and
reproducible artifacts. It connects agents, notebooks, files, figures, reports,
runs, and review into one auditable desktop workflow.

<p>
  <b>English</b> ·
  <a href="./README.zh.md">简体中文</a> ·
  <a href="./README.ja.md">日本語</a> ·
  <a href="./README.es.md">Español</a> ·
  <a href="./README.de.md">Deutsch</a> ·
  <a href="./README.fr.md">Français</a> ·
  <a href="./README.ko.md">한국어</a>
</p>

<p>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://doi.org/10.5281/zenodo.21351225"><img src="https://img.shields.io/badge/DOI-10.5281%2Fzenodo.21351225-1682D4" alt="DOI"></a>
  <a href="https://internscience.github.io/ResearchClawBench-Home/"><img src="https://img.shields.io/badge/%F0%9F%8F%86%20%231-ResearchClawBench-FFB300" alt="#1 on ResearchClawBench"></a>
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-blue" alt="Platforms">
  <img src="https://img.shields.io/badge/i18n-7%20languages-5B8DEF" alt="7 interface languages">
  <img src="https://img.shields.io/badge/built%20with-Tauri%202%20%2B%20React-24C8DB" alt="Built with Tauri + React">
  <img src="https://img.shields.io/badge/runtime-OpenCode-success" alt="OpenCode runtime">
  <a href="https://discord.gg/fWNMDKcd5P"><img src="https://img.shields.io/badge/Join-Discord-5865F2" alt="Join Discord"></a>
  <a href="http://makeapullrequest.com"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome"></a>
  <a href="https://linux.do"><img src="https://img.shields.io/badge/Join-linux.do-orange" alt="linux.do"></a>
</p>

</div>

---

> [!IMPORTANT]
> **本仓库是 Lubricant R&D OS —— 工业润滑油研发分支，不是上游原版。**
>
> 它是 [ai4s-research/open-science](https://github.com/ai4s-research/open-science) 的长期下游分支，在其上叠加了**工业润滑油产品开发**领域层与三栏研发工作台：
>
> - **领域层** → [`domains/lubricant/`](./domains/lubricant/)：12 个研发阶段技能、16 个工件 JSON Schema、阶段状态机、Phase 4 计算引擎（成本 / 混料 DOE / 统计 / 多目标优化）、13 个自动化测试。详见[领域包文档](./domains/lubricant/README.md)。
> - **三栏工作台** → 左侧边栏与中间会话流沿用原生 Lubricant Science；右侧新增「**研发阶段与门禁**」面板，由工作区磁盘上的真实工件驱动，展示 11 步工件链、整体进度与门禁决议。进入方式：侧边栏「润滑研发 Copilot」，或 `/lubricant` 路由。
> - **上游基线** → `0.5.2`（`cea3c3a`）；同步状态与核心改动清单见 [`UPSTREAM.md`](./UPSTREAM.md)。
>
> 下文「[润滑研发领域层](#润滑研发领域层lubricant-rd-os)」为本分支新增内容；其后的 News 与各功能章节是上游 Lubricant Science 的原始说明。桌面端的全部能力（会话、笔记本、文件、图表、报告、运行、评审）在本分支中**保留且未改动**。

---

## 润滑研发领域层（Lubricant R&D OS）

> 本节为本分支新增内容。首页收录**产品定位、核心优势、研发背景与行业痛点、核心研发哲学、五大类研发性质与差异化流程**；其余内容（系统架构设计、快速开始与离线验证、桌面端使用指引、当前项目状态、许可证）见 [`domains/lubricant/README.md`](./domains/lubricant/README.md)。

### 1. 产品定位

**Lubricant R&D OS** 是一套运行在 Lubricant Science 科研工作台上的**工业润滑油产品开发决策助手（R&D Copilot & Operating System）**。

它**不是**一个简单的"输入几个技术指标，AI 自动吐出配方"的黑盒生成器。它的核心使命是：

> **把润滑油研发从"经验试错与逆向仿制"升级为"科学决策与证据闭环"**。
> 让每一个配方决策都有工况证据支撑，每一次实验设计都最大化信息增益，每一个阶段流转都可追溯、可审计、可复用。

### 2. 核心优势

工业润滑油配方属于核心商业机密，研发决策又依赖严谨的物理实验与数据溯源。相比通用聊天型 AI 或从零自研桌面软件，基于 Lubricant Science 开发具备四大不可替代的底座优势。

#### 2.1 完整的科研数据血统追溯（Scientific Provenance）

**痛点。** 通用 Agent 的推导过程活在会话上下文里 —— 那是**易失缓存**，不是持久存储。上下文一压缩，前面的推理会被"总结"后塞回（是**总结**，不是**备份**），被判定为不重要的细节就此永久消失：为什么排除这组混兑点、哪个约束卡住了成本上限、第一次试算为何失败。会话一结束，更是整体归零。更关键的是，即使聊天记录还在，它也只是**线性文本流水** —— 拿着 `Freeze Formula V7`，无法从这个文件倒推回它是哪句话、哪次计算、哪批实验造出来的。**结论与证据的连接点丢了，这才是"黑盒"的准确定义。**

**机制。** 落盘时机被前置到「每次写入 / 每次执行」，而不是等会话结束：

| 记录 | 位置 | 触发时机 |
|---|---|---|
| 文件版本记录 | `.openscience/provenance.jsonl` | Agent 每次写入工作区文件 |
| 执行记录 | `.openscience/runs.jsonl` | Agent 每次执行代码 |

两条日志都是 **append-only**（只增不改，互斥锁串行化），同一文件多次修改累积为 `v1 / v2 / v3 …`。「无缝追溯」靠的是**双向可走的索引**：版本记录带 `path`（反查某文件的全部历史）与 `run_id`（指向那次执行）；执行记录带 `command` / `code`（脚本哈希）/ `outputs` / `env` / `log_hash`。脚本读取的输入文件也在工作区内，**同样自带记录**，链条自然接上 —— 从终版配方可一路回溯到 DOE 混兑点、实验批次、检验方法版本、原料批次物化属性，直到物理实验原始记录。

记录的不只是"改了什么"，还有**"凭什么这么改"**：当时的 Python 版本、依赖包快照、硬件环境，以及由哪个会话、哪个模型产出。**上下文压缩掉的东西，磁盘上有备份。**

**边界。** 覆盖范围是**工作区内**发生的一切：数据从未进过工作区（如手工改的 Excel）、或人在工作区外改文件，链条会缺环；记录亦有上限（`content` 截断 10 万字符、`log` 截断 20 万字符、单次最多 200 个输出文件、超 5MB 只记路径与大小）。准确表述是：**凡在工作区内由 Agent 写入或执行产生的工件，均可完整追溯。**

#### 2.2 工业级数据隐私与离线闭环（Local-First Architecture）

**痛点。** 云端 SaaS 的数据物理上在服务商的机器里，"删除"通常只是标记删除，备份与日志副本不可控 —— 你能依靠的只有**对方的承诺**。

**机制。** Local-First 是**三层**，其中两层无条件成立，一层取决于选型：

| 层 | 保障内容 | 成立条件 |
|---|---|---|
| **存储层** | 数据落在哪 | **无条件成立** |
| **访问层** | 谁能碰数据 | **无条件成立** |
| **推理层** | 数据出不出网 | **取决于模型选型** |

- **存储层** —— 默认工作区 `~/Documents/OpenScience`，会话、项目、文件、双日志、notebook 全在其下；SQLite 只是**派生索引**，`runs.jsonl` 才是真相源，索引损坏可从日志重建（**审计证据不依赖数据库完好**）；工作区同时是**本地 git 仓库**，代码层面禁止配置远端与 push —— 不是承诺不上传，是**没有上传的能力**。
- **访问层** —— 底座 `AGENTS.md` 的 *Safety defaults* 三条硬约束：Agent **只能访问当前工作区**（越界路径直接拒绝）；执行命令、删除文件、安装依赖、建立远程连接**均需人工批准**，且"**永不发布 off**"；API key 只进**系统钥匙串**，**绝不写入 provenance、日志、崩溃报告、git 或导出项目**（连 provenance 都不许存 —— 否则审计材料本身就成了泄露源）。本地预览网关默认只监听 `127.0.0.1`。
- **推理层** —— 接**本地模型**（Ollama / LM Studio / vLLM，走 `127.0.0.1`）时**出网流量为零**，且回环地址豁免代理，流量不出机器；接**云端模型**时提示词出网，但通道可控（代理支持 `system` / `custom` / `none` 三档，可指向企业自建内网网关）。

**边界。** 不要说"绝对不出网" —— **默认不出网、出网必须主动选择**才是准确表述；本地模型在复杂推理与长文档理解上与云端旗舰存在量级差距，安全与能力是 trade-off；"离线闭环"指**数据面**，装包、拉模型、检索文献仍需网络。

#### 2.3 LLM 语义路由与确定性科学计算的严格解耦

**痛点。** 通用 Agent 让大模型直接输出数字 —— 估算粘度、核算成本、拟合回归曲线。这些数字**看起来完全合理**，却没有任何真实计算支撑。代价是四重的：数字凭直觉发现不了错；错误向下游传播（一个虚假粘度值会让 DOE 选点全部偏离，实验白做）；最危险的是"混合幻觉"（算对 90%、错 10%，最难识别）；审计时问"这个数怎么来的"，答"模型算的"等于没有回答。

**机制。** 一条硬边界 —— **语义归模型，数字归引擎**：

| 环节 | 责任方 |
|---|---|
| 理解意图 / 结构化提取 / 解释结果 | 大模型 |
| **成本计算 · DOE 混兑点 · 方差分析 · 多目标优化** | **确定性引擎** |
| **阶段判定（GO / HOLD）· 产出校验** | **策略规则与校验器** |

四个机制保证这条边界成立：

1. **接口隔离** —— 引擎入口只做"stdin 读 JSON → 按 `--engine` 分发到纯函数 → stdout 写 JSON"，模型只构造输入，**数字由脚本输出，模型没有机会改写**。
2. **确定性优先** —— 源码注释明确 *"same input bytes produce byte-identical envelopes"*；为此连 F 分布 CDF 都自行实现（正则化不完全 beta + Lentz 连分数，依据 Numerical Recipes 3rd ed. §6.4），并**刻意不依赖第三方科学计算库** —— 库升级可能改变数值，破坏可复现性。方法与引擎均带版本号。
3. **证据边界** —— 输入必须声明 `SYNTHETIC` 或 `PHYSICAL`；合成数据的结果会被**自动打上** `NOT_FOR_PHYSICAL_RELEASE` / `CANNOT_QUALIFY_METHOD` 标签，**人无法手动摘掉**，且输出携带 `input_sha256` 绑定输入。
4. **规则硬编码** —— GO / HOLD 由策略脚本中的纯函数判定，而非模型判断；产出中还写入主动免责："本记录**不构成配方、实验、性能、成本或优化的结论**"。

> **一句话：模型负责说人话，引擎负责算准数，账本负责证明这个数是谁算的。**

#### 2.4 开箱即用的专业科研基础设施（无需重复造轮子）

**痛点。** 从零自研一套能承载配方研发的桌面工作台，需要自行解决六类基础设施。这些工作与润滑油机理**毫无关系**，却必须完成，完成后也不产生任何领域价值。

**机制。** 底座已完整封装：

| 基建类别 | 已封装内容 | 规模 |
|---|---|---|
| 跨平台桌面壳 | Tauri 2；macOS `.dmg` / `.app`（含签名公证）、Windows NSIS + WiX、Linux `.deb` / `.rpm` | 3 平台 |
| Agent 运行时 | OpenCode 作为隔离 sidecar：随包分发、独立端口、app 私有配置、自动启动 | 4 个随包二进制 |
| 多模型适配 | provider 凭据注入、审批模式与权限规则适配、自定义 OpenAI 兼容端点 | 1,464 行 |
| MCP 协议层 | 一键将开源科学 MCP server 装入**独立 uv 环境**（不动用户 Python 环境） | 849 行 |
| 计算执行环境 | Python / R 常驻内核、uv 环境管理、Jupyter、本地预览服务 | 1,952 行 |
| 项目与会话隔离 | 工作区沙箱、本地 git 快照、会话同步 | 2,698 行 |

随包分发的四个二进制为 `opencode` / `uv` / `agent-browser` / `osd`，**用户无需自行安装 Node、Python 或浏览器驱动**；底座（不含第三方二进制）总代码量约 **8.3 万行**。

**比代码更贵的是踩过的坑**（写代码可估工期，踩坑不能）：企业内网的 TLS 检查与杀毒软件会让依赖安装**静默挂死**（现改为流式输出 + 无输出超时自动终止）；Agent 运行时的权限规则会被**拍平后按"最后匹配生效"求值**，每种审批模式都须显式声明对外部目录的意图；多平台发布曾因一次 tag 推送产生两个相同构建而**抢同一个 Release**（现加并发组约束）。

**边界。** "开箱即用"限定在**基建**层面 —— 底座给的是"能跑科学计算的车间"，不是"润滑油配方算法"；润滑机理模型、DOE 设计规则、检验方法判定阈值仍需自行沉淀（以 Skill 形式实现）。另需主动说明：OpenCode 是第三方运行时，其 API / 配置 / 权限模型变更时需跟随适配 —— 这是换取"不必自研 Agent 内核"的代价。

### 3. 研发背景与行业痛点

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

### 4. 核心研发哲学（Decision-Driven R&D）

本项目严格遵循决策驱动研发框架（Decision-Driven R&D Framework）：

* **润滑油不是在"通过标准"，而是在具体设备工况下承受特定挑战**：关注具体摩擦副、温度谱、载荷谱、污染与寿命。
* **研发目标是"风险控制 + 商业价值优化"，而非单一指标最优**：
  * **约束满足型产品**（常规工业油）：在满足 CTQ 与风险阈值的前提下，追求成本最低与供应链稳定（$Minimize\ Cost\ s.t.\ CTQ_i \ge Limit_i$）。
  * **综合价值型产品**（风电齿轮油、空压机油）：追求性能安全余量与关键失效机理的长期可靠性。
* **"先证明尺子可靠，再用尺子量配方"**：必须在研发早期对测试评价方法进行资格确认（Method Qualification），验证其区分性与工况相关性。
* **逆向开发的角色定位**：正向设计为主体，逆向分析仅作为边界核对与对比基线（Benchmark Calibration），而非开发起点。
* **证据级别与隔离铁律**：严禁 AI 编造数据，严格隔离合成占位数据（`SYNTHETIC`）与真实物理实验数据（`PHYSICAL`）。合成数据仅用于验证软件流转，物理放行必须依赖真实实验证据。

---

### 5. 五大类研发性质与差异化流程

工业润滑油开发不是一条死板流水线。系统在**项目定义阶段（Stage 0）**首先识别或引导用户确认项目的具体性质，并自动分流到匹配的专属流程：

| 研发性质 | 核心驱动逻辑 | 差异化阶段路径（Stage 流转） | 核心关注点与输入要求 |
|---|---|---|---|
| **1. 新产品正向开发**<br>(`NEW_PRODUCT`) | 需求与工况驱动 | `Project → Duty(7项) → Challenge → Failure/CTQ → Method Qual → Design Space → DOE → Running → Model → Opt → Gate` | 完整 7 大工况、润滑挑战映射、失效机理深度分析、混料空间与多目标优化。 |
| **2. 已有产品性能优化**<br>(`IMPROVEMENT`) | 现场失效与痛点驱动 | `Project → Failure/CTQ(问题诊断) → Method Qual(灵敏度) → Design Space → DOE → Running → Model → Opt → Gate` | **跳过全套工况重推**。聚焦现场真实失效证据，先验证评价方法灵敏度，再对瓶颈指标做定向配方改良。 |
| **3. 降本替代**<br>(`COST_DOWN`) | 非劣效性驱动<br>(Non-inferiority) | `Project → Failure/CTQ(非劣效红线) → Design Space → DOE → Running → Opt → Gate` | **不推新工况**。基于成熟基线配方与成本结构，划定 CTQ 不劣化底线，优化替代材料属性安全域。 |
| **4. 客户定制**<br>(`CUSTOMIZATION`) | 技术协议/OEM规范驱动 | `Project → Failure/CTQ(协议指标映射) → Method Qual(指定台架) → Design Space → DOE → Running → Gate` | 以客户技术协议和指定认证台架为准绳，快速匹配成熟平台做微调验证。 |
| **5. 机理/平台型探索**<br>(`EXPLORATION`) | 科学假设驱动 | `Project → Design Space → DOE → Running → Model → Gate` | **不考核商业 target_cost 和量产**。允许试错，重点提取变量影响规律与知识资产沉淀。 |

### 6. 12 个领域技能清单 (Skills)

每个 Skill 均为**自包含目录**（`SKILL.md` + `scripts/`），由 Lubricant Science 内置的 **OpenCode Agent 运行时**扫描加载：运行时读取 `SKILL.md` 的 YAML frontmatter（`name` + `description`）把技能注册为可按需调用的能力，**无需修改运行时源码**即可增删技能 —— 这正是领域包能独立插拔的原因。每个技能输出遵循标准 JSON Schema 的结构化工件：

| Skill 名称 | 所属阶段 | 输出状态 / 工件 | 关键功能与职责 |
|---|---|---|---|
| `project-definition` | Stage 0 | `PROJECT_DEFINED` | 引导用户确认 5 类研发性质，定义商业/技术目标、硬约束与项目章程。 |
| `duty-definition` | Stage 1 | `DUTY_DEFINED` | 结构化录入 7 大工况（设备、工况谱、维护、温度、负荷、污染、寿命）。 |
| `duty-challenge-analysis` | Stage 1 | `CHALLENGES_DEFINED` | 从工况推导润滑挑战 Map（严重度、暴露度、敏感度分级）。 |
| `failure-ctq-analysis` | Stage 2 | `FAILURE_CTQ_DEFINED` | 梳理失效机制与关键质量特性（CTQ），建立挑战到性能的映射链。 |
| `test-method-qualification` | Stage 2 | `TEST_METHODS_QUALIFIED` | 评价方法资格确认，验证测试方法与真实工况的相关性及区分能力。 |
| `formulation-design` | Stage 3 | `DESIGN_SPACE_DEFINED` | 建立基础油与添加剂混料设计空间，设定物理与化学约束边界。 |
| `doe-design` | Stage 3 | `EXPERIMENT_DESIGNED` | 结构化生成混料实验设计（D-Optimal / Extreme Vertices）评估请求。 |
| `experiment-import` | Stage 3 | `EXPERIMENT_RUNNING` | 录入实验测试观测结果，强制校验测试批次与物理溯源凭证。 |
| `statistical-analysis` | Stage 4 | `MODEL_BUILT` | 拟合回归与响应面模型，提供残差检验与模型解释力报告。 |
| `optimization` | Stage 4 | `OPTIMIZED` | 基于成本与 CTQ 模型执行多目标约束优化，给出候选配方推荐。 |
| `gate-review` | 评审门禁 | `VERIFIED` | 汇总阶段证据链，执行正式审查决策（GO / HOLD / PIVOT / KILL）。 |
| `lubricant-rd-agent` | 核心路由 | — | 元技能（Meta-Skill）路由器，执行跨阶段拦截、性质分流与证据门控。 |

### 7. 目录结构

```
Lubricant-R-D-OS/                    # 主仓库（open-science 下游 fork）
└── domains/lubricant/               # ← 本领域包（92 个提交的历史随合并保留）
    ├── README.md  LICENSE           # 领域包完整文档 / MIT
    ├── contracts/
    │   └── state-machine.json       # 阶段状态机（ALLOW / DENY / HOLD 门控）
    ├── schemas/                     # 16 个工件 JSON Schema (Draft 2020-12)
    ├── skills/                      # 13 个技能目录（12 个领域技能 + 环境自检）
    ├── domains/lubricant/           # 领域计算引擎与数据层
    │   ├── compute/{cost,doe,statistics,optimization,validation}/
    │   └── db.py                    # SQLite 五表数据层
    ├── tests/                       # 自动化测试套件（13 个可执行测试）
    ├── scripts/                     # 安装、校验、打包、仪表盘生成
    ├── templates/project-workspace/ # 新项目工作区模板（AGENTS.md + 活报告模板）
    ├── fixtures/  data/  integrations/
    └── PHASE4*.md                   # Phase 4 引擎设计文档
        REAL_CASE_WGO_001*.md        # 真实课题（V600 风电齿轮油）记录
        WGO_001_*.md
```

> ⚠️ **已知冗余**：领域包内部也有一个 `domains/lubricant/` 命名空间（Python 包路径 `domains.lubricant.compute...`），合并后成为 `domains/lubricant/domains/lubricant/`。这是原样保留的 —— 扁平化会破坏所有引擎的 import 路径，收益不抵风险。

---

## News

- **2026-08-18** — 🖥️ **Runs without a screen, and the terminal command comes with it.** `osd server` starts the whole workbench — workspace, agent runtime, and the *same* web UI — on a machine with no display, and `osd session send … --wait` drives it from a script or another agent. `osd` ships inside the desktop installer and puts itself on your PATH on first launch; on a server the archive needs nothing installed. Models, keys and approvals are all configurable from the terminal (`osd model`, `osd auth`, `osd approval`).
- **2026-08-13** — 🔌 **Speaks the Agent Client Protocol, both directions.** Drive Codex, Gemini CLI, Claude Code, or any other ACP agent from inside this app — with its own models, history, and your MCP connectors — or drive Lubricant Science itself from Zed, JetBrains, or Neovim. *(v0.4.0)*
- **2026-08-01** — 🗂️ **Projects, memory, and full history.** Group sessions into named projects (import an existing repo *in place*, no copying), give the agent persistent global and project memory, and reach every past conversation through a searchable history with archive, restore, and export. *(v0.3.1)*
- **2026-07-24** — 🪟 **Split-pane tiling.** Tile sessions side by side, drag panes to re-dock them, keep several independent Screens, and run a different model in each pane. *(v0.3.0)*
- **2026-07-21** — 🌐 **Access from anywhere — even your phone.** A token-authenticated gateway serves the *real* desktop UI to a CLI, a browser on your LAN, or your phone (loopback by default; LAN is opt-in). Start a run at your desk and read the finished figure and report on your phone. *(v0.2.3)*
- **2026-07-21** — 🧭 **Browser control.** The agent can drive your own Chrome — profile and logins intact — to read the live web the way you do, or an isolated private browser on demand. *(v0.2.3)*
- **2026-07-09** — 🎉 **#1 on ResearchClawBench.** Lubricant Science Desktop ranks #1 by scored-task average on [ResearchClawBench](https://internscience.github.io/ResearchClawBench-Home/), an end-to-end benchmark for autonomous scientific research agents (Pass@1 leaderboard).

---

## Contents

- [🛢️ 润滑研发领域层（Lubricant R&D OS）](#润滑研发领域层lubricant-rd-os)
- [✨ What it does](#what-it-does)
- [🎬 See it in action](#see-it-in-action)
- [🧪 Current capabilities](#current-capabilities)
- [🔌 Skills and connectors](#skills-and-connectors)
- [📦 Install](#install)
- [🖥️ Headless & CLI (`osd`)](#headless--cli-osd)
- [🚀 Build from source](#build-from-source)
- [🔒 Safety and privacy](#safety-and-privacy)
- [🗂️ Repository layout](#repository-layout)
- [📌 Status](#status)
- [🤝 Contributing](#contributing)
- [📖 Citation](#citation)
- [⚖️ License](#license)

## What it does

**Runs the whole research loop** — from a broad direction to a finished paper:
exploration, literature survey, hypothesis, experiment code, analysis, figures, and
write-up, in one continuous, auditable session.

- **Autonomous research agents** — the bundled `ai4s-agent` chains specialist skills
  end to end (explore → survey → experiment → write), and each stage drops a real,
  inspectable artifact into your workspace, not just a chat reply.
- **Everything traces back** — figures, tables, reports, notebooks, and run outputs
  link to the exact code, inputs, environment, model output, and conversation that
  produced them.
- **Local-first and yours** — sessions, data, provenance, notebooks, and run records
  live in local folders on your machine. Nothing leaves by default.
- **Model-agnostic runtime** — the UI talks through `packages/sdk` to a bundled,
  pinned OpenCode sidecar. Bring your own model; providers, skills, and MCP servers
  stay pluggable.
- **Reproducible by construction** — local, SSH/Slurm, Modal, and notebook-batch runs
  are captured as reproducible run records, not loose terminal scrollback.
- **Reach it from anywhere** — a built-in, token-authenticated gateway serves the
  *real* desktop UI to a browser on your LAN or phone (or, with a tunnel, from
  anywhere) — kick off a run at your desk and check on it from your phone over lunch.
  Off by default; loopback-only until you opt in, and API keys never leave the machine.
- **Drives your own browser** — the agent can control your real Chrome, with your
  profile and logins intact, to read the live web the way you do — or an isolated
  private browser when you'd rather it not.
- **Plan before it acts** — `/plan` lays out an execution plan before touching a
  file, and `/goal` fixes the objective, constraints, and acceptance criteria the
  agent then works toward.
- **Built for long projects** — named projects group their sessions, two layers of
  persistent memory (global and per-project) carry what matters between them, and a
  long conversation compacts itself as it approaches the model's context window.
- **Work several threads at once** — tile panes side by side, keep independent
  Screens, and give each pane its own model.
- **Extensible** — agent skills, MCP servers and one-click science connectors,
  `/` commands, `!` shell mode, and a model-agnostic SDK.

## See it in action

**One prompt -> a publication-grade figure, and every point traces to the exact code
and inputs that made it.** No black boxes: open any artifact to see its generating
script, its data files, and the conversation that produced it.

![A rendered cross-species atlas figure beside its generating script and input files in the artifact inspector](./docs/assets/showcase-provenance.webp)

**Literature -> a verifiable report.** Fan the search out across sources, draft a
manuscript rendered as a PDF, and gate it on a citation review — DOIs resolved,
unsourced numbers and figure/code inconsistencies flagged — before anything ships.

![A protein-language-model literature survey compiled into a PDF manuscript, with a citation reviewer confirming every DOI resolves](./docs/assets/showcase-literature.webp)

**Drives your own Chrome.** The agent reads the live web through your real browser
profile — logins and all — then turns what it finds into a figure and a sortable CSV.

![The agent driving the user's own Chrome via open-science-browser to harvest bioRxiv preprints into a chart and CSV](./docs/assets/showcase-browser.webp)

**Research from anywhere — even your phone.** A built-in authenticated gateway serves
the *real* desktop UI to a browser on your LAN (or a tunnel), so you can kick off a run
at your desk and read the finished figure and report on your phone.

<table align="center">
  <tr>
    <td align="center" width="33%"><img src="./docs/assets/showcase-mobile-home.webp" width="240" alt="The workbench in a phone browser: the new-session screen with starter analyses"><br><sub>New session</sub></td>
    <td align="center" width="33%"><img src="./docs/assets/showcase-mobile-run.webp" width="240" alt="A completed dose-response analysis — script, results, figure, and report — on a phone"><br><sub>A finished analysis</sub></td>
    <td align="center" width="33%"><img src="./docs/assets/showcase-mobile-reproduce.webp" width="240" alt="Reproducing an scVI benchmark, with its ARI-vs-epoch figure, viewed on a phone"><br><sub>A reproduced benchmark</sub></td>
  </tr>
</table>

<details>
<summary><b>More screenshots</b></summary>

<br>

![Reproducing an scVI integration benchmark on a remote A100 with a pinned environment, execution log, and provenance](./docs/assets/showcase-remote.webp)

![An 8-arm scVI hyperparameter sweep table beside a live analysis notebook sharing the agent's kernel](./docs/assets/showcase-experiment.webp)

</details>

## Current capabilities

**The research loop, as skills.** One meta-skill runs the full pipeline; each stage
is a self-contained skill that produces a real, gradeable artifact — runnable on any
model OpenCode supports:

| Skill | Role | Primary output |
| --- | --- | --- |
| `ai4s-agent` | Runs the four skills below, in order | The full research package |
| `research-explorer` | Turn a broad direction into concrete topics | `research_exploration.md`, `topic_matrix.md`, `literature_pre_survey.md` |
| `literature-survey` | Write a literature survey | 6–20 pp PDF, 60+ real citations, LaTeX source, taxonomy figures |
| `experiment-suite` | Build an experiment package | Design doc, runnable code, `results.json` with provenance, figures, report |
| `paper-writer` | Write a research paper | 8–14 pp PDF, 200+ citations, 4–8 figures, tables |
| `mindmap-render` | Render a mindmap | Image generated from a `topic_matrix.md` |
| `integrity-auditor` | Audit a paper's integrity | Image / numerical / logical findings, 4-level evidence grading, `audit_report.md` |

These ship in the `ai4s-skills` pack alongside first-party review skills and the
office/document skills below.

### Platform

| Area | Current state |
| --- | --- |
| Desktop shell | Tauri 2 + React + TypeScript + Vite, with macOS, Windows, and Linux desktop builds. |
| Runtime | Bundled OpenCode sidecar, auto-started by the app, isolated from the user's own OpenCode config/data. |
| Projects | Named project workspaces that group their sessions; import an existing folder in place (never copied) or adopt one already inside the workspace; move an existing session into a project. |
| Sessions | Multi-session chat/history, dated workspace folders, searchable history with archive/restore/export, `@` file and `#` conversation references, `/` commands, and `!` shell mode. |
| Layout | N-ary split-pane tiling with drag-to-dock, independent Screens, per-pane model and reasoning effort, and cross-screen pane drag. |
| Agent modes | `/plan` for plan-then-execute, `/goal` for objective and acceptance criteria, live subagent status in its own panel, and Stop that reflects the runtime's real server state. |
| Memory | Global and per-project memory layers, switchable, plus automatic context compaction as a conversation approaches the model's window. |
| Remote compute | Register machines from your `~/.ssh/config`, probe them, and submit, track, or cancel jobs from the app. |
| Appearance | Light, Warm, and Dark themes with per-theme accents, and UI zoom. |
| Files | Global and per-session file browsing, context menu actions, external open/reveal, copy path, and local preview server. |
| Headless & CLI | `osd server` runs the workbench with no window — same workspace, same runtime, same web UI, served from one self-contained directory — and `osd` drives it (or a running desktop app) from a terminal: sessions, projects, runs, files, approvals, `--wait`, `--json`. |
| Remote access | Token-authenticated gateway that serves the real UI to a CLI, a LAN web browser, or your phone (loopback by default, LAN opt-in); read-only vs full access modes; copy a link with the token embedded to connect in one tap. API keys never cross the wire. |
| Editor interop (ACP) | Speaks the Agent Client Protocol in both directions: run any ACP agent (Codex, Gemini CLI, Claude Code, …) as the runtime behind the ordinary UI, with its own model and reasoning selectors, history replay, and this app's MCP connectors; or let an external editor (Zed, JetBrains, Neovim, …) drive Lubricant Science, reusing the gateway token. |
| Browser control | The agent drives your own Chrome — profile and login state preserved — reading pages through the accessibility tree, or an isolated/private browser on demand. |
| Notebooks | Real `.ipynb` files, Python and R notebook creation, local kernel execution, managed Jupyter environment via bundled `uv`, and an Open JupyterLab action. |
| Runs | Append-only run logs, global SQLite run index, search/facets/pagination, local/remote surfaces, output links, logs, and reproduce prompts. |
| Provenance | `.openscience/provenance.jsonl` tracks file versions and links produced artifacts back to the run or edit that created them. |
| Review | Traceability, statistics-integrity, domain-check, large-file, publication-figure, remote-compute, and Modal run skills are bundled as first-party skills. |
| Viewers | PDF, image, video, HTML, Markdown, code, CSV/TSV tables with charts, DOCX, XLSX, PPTX, molecules, 3D meshes, genome tracks, FITS, DOS/DOSCAR, EIGENVAL bands, qcode, anomaly maps, and phase files. |
| Models | OpenCode provider catalog, OAuth/API-key provider flows, custom OpenAI-compatible endpoints, and local/provider-specific options supported by OpenCode. |
| Interface languages | English, Simplified Chinese, Japanese, Spanish, German, French, and Korean. Portuguese (Brazil) and Arabic are registered but not selectable yet. |

## Skills and connectors

Bundled skills are fetched for builds and releases instead of being committed into
git history:

- `ai4s-skills` pack from `ai4s-research/ai4s-skills`.
- Office/document skills from the Apache-2.0 `anthropics/skills` repository:
  `docx`, `pdf`, `pptx`, and `xlsx`.
- First-party core skills in `runtime/skills/core/`:
  `traceability-review`, `stats-integrity`, `domain-check`, `large-file`,
  `publication-figures`, `remote-compute`, and `modal-run`.

One-click science MCP connectors currently include:

- Literature search: arXiv, PubMed, Crossref, Semantic Scholar, bioRxiv/medRxiv.
- Biomedical databases: PubMed, ClinicalTrials.gov, MyVariant/ClinVar.
- Materials Project.
- FRED economic data.
- Space weather.
- Open-Meteo weather and climate.
- USGS water data.

You can also add any local or remote MCP server from Settings. See
[`docs/CONNECT_YOUR_TOOLS.md`](./docs/CONNECT_YOUR_TOOLS.md).

For a neutral positioning note, see
[`Lubricant Science Desktop vs OpenScience`](./docs/open-science-desktop-vs-openscience.md).

## Install

Download the latest installer from the
[Releases page](https://github.com/ai4s-research/open-science/releases/latest).

- **macOS**: `.dmg` / `.app`, Apple Silicon and Intel, macOS 13 Ventura or later.
- **Windows**: NSIS `.exe`, Windows 10/11 x64 — installs per user, no admin needed. A `.msi` is also published for IT-managed deployment; pick one format and stay on it.
- **Linux**: `.deb` and `.rpm` on x86_64 Linux.

The macOS packages are Developer ID signed, notarized, and stapled, so they open
normally — no `xattr` workaround needed. Windows and Linux builds are not signed yet.

**Windows**: if SmartScreen appears, choose **More info -> Run anyway**.

**Linux**:

```bash
sudo apt install ./Open.Science_*.deb
# or
sudo rpm -i Open.Science-*.rpm
```

## Headless & CLI (`osd`)

A research machine usually has no screen. `osd` is the same workbench without
one: the same workspace layout, the same agent runtime, the same projects, and
the same web UI — served over HTTP instead of drawn in a window.

**On a server, take the archive.** `osd-<version>-<target>` from Releases
unpacks and runs with nothing installed — verified on a bare Ubuntu container
with no packages added at all.

```bash
# Configure the machine (works before any server is running)
./osd auth set anthropic --key sk-…       # stays on this machine, never on the wire
./osd model set anthropic/claude-opus-4-5 # the default for every turn
./osd server --lan                        # prints its URL and access token
```

Keys never have to touch a file: the agent runtime inherits this process's
environment, so `ANTHROPIC_API_KEY=sk-… ./osd server` needs no `auth set` at
all. A self-hosted or proxied endpoint goes in the same command
(`--base-url https://my-gateway.internal/v1`), and `osd auth ls` prints provider
names only — no key is ever printed by anything. Changing a key needs a restart;
the CLI says so rather than leaving you to wonder.

Open the printed URL and you get the real desktop UI in a browser, phone
included. Or drive it from a terminal — on the same machine, over SSH, or from
your laptop:

```bash
osd project new "Reef survey"
id=$(osd session new --project "Reef survey")
osd session send "$id" "Fit the 2015–2024 bleaching trend and write report.md" \
    --model anthropic/claude-sonnet-4-5 --wait
osd fs ls figures/
osd fs get report.md --output ./report.md
```

On Windows the same commands work in PowerShell; only the shell's own syntax
differs:

```powershell
$id = osd session new --project "Reef survey"
osd session send $id "Fit the 2015-2024 bleaching trend and write report.md" --wait
```

**On your own machine it is already installed.** The desktop installer carries
`osd`, and the app puts it on your PATH the first time it starts, so a new
terminal has the command with nothing to set up. It writes one small wrapper
(`~/.local/bin/osd`, or `~/bin` when a terminal already searches that) — never a
symlink, because `osd` finds its runtime next to its real executable. If that
folder is not on PATH, the app adds it to your login profile and Settings →
Remote Access says which file it touched. Nothing else on your shell is changed.

`--wait` returns when the turn is finished, not when it was accepted, and fails
loudly if it produced no reply. `--json` prints the API's own response for
scripts.

### Which model, and who approves what

`osd model` shows the default, `osd model ls` lists what the runtime can
actually serve (the providers this machine has credentials for, current one
marked), and `osd model set <provider/model>` changes it — over the gateway, so
it works against a remote server too. Any single turn can override it with
`osd session send --model … --agent … --effort …`.

Approvals still apply: the agent asks before running commands, deleting files,
installing dependencies or reaching the network. Without a window, `--wait` names
what is waiting and offers both answers — `osd permission ls` /
`osd permission allow <id>` in the terminal, or the gateway URL it prints, which
carries the token so a browser on your laptop or phone can approve it.

For a machine with nobody watching, opt out explicitly:

```bash
osd approval            # what has to be asked today
osd approval set full   # never ask — commands, deletions, installs, network
```

`full` is a deliberate choice, not a default: the agent stays confined to the
workspace, but nothing pauses for you. `osd approval set approve` puts every
rule back.

### As a service

`osd server` is an ordinary foreground process, so systemd runs it as-is. This
unit was run end to end on Ubuntu — enable, restart, crash, stop:

```ini
# /etc/systemd/system/osd.service
[Unit]
Description=Lubricant Science Desktop (headless)
After=network-online.target

[Service]
Type=simple
User=ubuntu
Environment=HOME=/home/ubuntu
ExecStart=/opt/osd/osd server --port 4788
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`sudo systemctl enable --now osd` and the printed URL and token land in
`journalctl -u osd`. A unit is also the tidiest way to run it: systemd stops the
whole cgroup, so the agent runtime never survives the server, however it dies.

With no `--gateway` given, `osd` talks to a gateway already running on the same
machine — including the desktop app's — so with the app open, `osd session ls`
just works. Otherwise point it anywhere with `osd login --gateway <url> --token
<token>`.

What is *not* there without a desktop: local Jupyter kernels, native file
dialogs, and the OS file manager — the web UI hides those rather than offering
controls that would fail. Two more are worth knowing: **provenance and run
records are written by the desktop client**, so a headless server keeps the
workspace's file history through git snapshots but does not append to
`provenance.jsonl` or the run index.

## Build from source

Prerequisites:

- Node.js >= 20
- pnpm 9
- Rust toolchain
- macOS, Windows, or Linux system dependencies required by Tauri

```bash
git clone https://github.com/ai4s-research/open-science
cd open-science
pnpm install

# Fetch pinned sidecars and bundled skills. These are git-ignored.
bash scripts/dev/fetch-opencode.sh
bash scripts/dev/fetch-uv.sh
bash scripts/dev/fetch-skills.sh

# The osd terminal client is bundled too — it is ours, so it is built, not fetched.
bash scripts/dev/build-osd-sidecar.sh $(rustc -vV | sed -n 's/host: //p')

# Run in development or build installers.
pnpm --filter @ai4s/desktop tauri dev
pnpm --filter @ai4s/desktop tauri build
```

Useful checks:

```bash
pnpm test
pnpm typecheck
pnpm lint
```

## Safety and privacy

- Workspace files, raw data, session history, provenance, notebooks, and run records
  stay local by default.
- Command execution, file deletion, dependency installation, and remote connections
  are human-approved flows in the desktop app.
- Provider credentials are written to app-private runtime config, not to the
  workspace, provenance, git, exports, or global OpenCode config.
- Settings includes a plain-language data-flow view explaining what can be sent to
  the selected model provider.

## Repository layout

| Path | Purpose |
| --- | --- |
| `apps/desktop/` | Tauri + React desktop app. |
| `packages/sdk/` | `OpenCodeClient`; keeps the UI from calling OpenCode directly. |
| `packages/shared/` | Shared domain types and chart palette. |
| `packages/ui/` | Shared UI package. |
| `runtime/skills/core/` | First-party scientific skills. |
| `runtime/skills/external/` | Build-fetched external skills. |
| `runtime/harness/` | Runtime harness knowledge and operator context. |
| `runtime/mcp/` | MCP runtime notes/configuration. |
| `examples/` | Built-in example workspaces. |
| `crates/osd-core/` | The server core — workspace, sidecar, gateway. No Tauri, so it runs headless. |
| `crates/osd-cli/` | `osd`: the headless server and its client. |
| `scripts/dev/` | Sidecar, `uv`, skill fetchers, and focused regression probes. |
| `docs/` | Product, technical, operator, connector, and research notes. |

## Status

The project is a working desktop MVP in active development. The most reliable current
implementation log is [`PROGRESS.md`](./PROGRESS.md). Product and architecture notes
live in [`docs/PRD.md`](./docs/PRD.md) and
[`docs/TECHNICAL_DESIGN.md`](./docs/TECHNICAL_DESIGN.md), but those documents include
target design as well as historical status notes.

Near-term work is focused on Windows code signing, auto-update, broader
Windows/Linux verification, richer connector hardening, and continued
reproducibility review. macOS releases are already signed and notarized.

## Contributing

Issues and PRs are welcome. Keep changes minimal and verifiable, follow
[`AGENTS.md`](./AGENTS.md), and run the checks before opening a PR. For discussion,
join the [Lubricant Science Discord](https://discord.gg/fWNMDKcd5P) or the
[linux.do](https://linux.do) community.

## Citation

If you use Lubricant Science Desktop in your research, please cite it:

```bibtex
@software{open_science_desktop,
  author  = {{The Lubricant Science Desktop Contributors}},
  title   = {Lubricant Science Desktop: a local-first, model-agnostic AI research workbench},
  year    = {2026},
  version = {0.5.2},
  doi     = {10.5281/zenodo.22136307},
  url     = {https://github.com/ai4s-research/open-science},
  license = {MIT}
}
```

GitHub's **"Cite this repository"** button (top of the repo page, generated from
[`CITATION.cff`](./CITATION.cff)) provides the same reference in APA and BibTeX.

## License

[MIT](./LICENSE). Bundled third-party skills and connectors keep their own licenses.

> Lubricant Science Desktop is beta research tooling. Treat outputs as drafts: verify numbers,
> citations, code, and conclusions before publication or decision-making.
