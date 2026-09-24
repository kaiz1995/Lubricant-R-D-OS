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

> 本节为本分支新增内容，概述产品定位与核心设计。完整技术细节（系统架构、快速开始、离线验证、桌面端使用指引、项目状态、许可证）见 [`domains/lubricant/README.md`](./domains/lubricant/README.md)。
>
> **名词说明：** 上游项目 GitHub 名为 [Open Science](https://github.com/ai4s-research/open-science)，桌面产品品牌为 **Lubricant Science Desktop**，内置 Agent 运行时为 **OpenCode**。本分支在此基础上叠加工业润滑油领域层。

### 1. 产品定位

**Lubricant R&D OS** 是一套运行在 Lubricant Science 科研工作台上的**工业润滑油产品开发决策助手（R&D Copilot & Operating System）**。

它**不是**"输入技术指标，AI 自动吐出配方"的黑盒生成器。核心使命是：

> **把润滑油研发从"经验试错与逆向仿制"升级为"科学决策与证据闭环"**。
> 让每一个配方决策都有工况证据支撑，每一次实验设计都最大化信息增益，每一个阶段流转都可追溯、可审计、可复用。

### 2. 核心优势

工业润滑油配方属于核心商业机密，研发决策依赖严谨的物理实验与数据溯源。基于 Lubricant Science 底座开发，具备四大不可替代的优势：

| 优势 | 一句话 | 关键机制 |
|---|---|---|
| **2.1 科研数据血统追溯** | 从终版配方一路回溯到原始实验记录 | 每次写入/执行实时落盘到 `provenance.jsonl` + `runs.jsonl`（append-only），双向索引自动串联证据链 |
| **2.2 数据主权与可选离线** | "数据不出网"是可选项，选择权在企业 | 存储层+访问层始终本地；推理层可选本地模型（零出网）或云端模型（仅提示词出网） |
| **2.3 语义与计算严格解耦** | 模型说人话，引擎算准数 | 成本/DOE/统计/优化由确定性引擎执行，模型无法改写数字；合成数据自动打标隔离 |
| **2.4 开箱即用的科研基建** | 不必从零造桌面壳、运行时、执行环境 | Tauri 2 跨平台壳 + OpenCode sidecar + Python/R 内核 + MCP 协议层，底座约 8.3 万行代码 |

> 每条优势的完整「痛点 → 机制 → 边界」展开见 [`domains/lubricant/README.md § 2`](./domains/lubricant/README.md#2-核心优势)。

### 3. 研发背景与行业痛点

传统工业润滑油研发长期受五个痼疾困扰：

1. **重逆向、轻正向** —— 高度依赖"找竞品 → 剖析 → 仿制 → 试错"，工况变化或原料断供时无法自主应对。
2. **实验碎片化（OFAT 陷阱）** —— 一次只改一个变量，缺少统一的设计空间与假设检验框架。
3. **课题长流水** —— 无明确终止条件（Stopping Rule）和设计冻结（Design Freeze）标准。
4. **"拿未校验的尺子量配方"** —— 评价方法缺乏工况相关性与区分度，产生假阳性/假阴性。
5. **原料牌号依赖** —— 缺乏基于物化描述符（粘度指数、极性、溶解度、烃组成）的属性管理体系。

### 4. 核心研发哲学（Decision-Driven R&D）

* **关注工况而非标准** —— 润滑油在具体摩擦副、温度谱、载荷谱下承受挑战，不只是"通过标准"。
* **风险控制 + 商业价值优化** —— 约束满足型产品追求 Minimize Cost s.t. CTQᵢ ≥ Limitᵢ；综合价值型产品追求安全余量与长期可靠性。
* **先证明尺子可靠** —— 研发早期对评价方法做资格确认（Method Qualification），验证区分性与工况相关性。
* **正向为主、逆向为辅** —— 逆向分析仅作边界核对与对比基线（Benchmark Calibration）。
* **证据隔离铁律** —— 严禁 AI 编造数据；合成数据（`SYNTHETIC`）与物理数据（`PHYSICAL`）严格隔离，合成数据仅用于验证软件流转。

### 5. 五大类研发性质与差异化流程

系统在项目定义阶段（Stage 0）识别项目性质，自动分流到匹配流程：

| 研发性质 | 核心驱动 | 阶段数 | 说明 |
|---|---|---|---|
| **新产品正向开发** `NEW_PRODUCT` | 需求与工况 | 11 步 | 完整工况推导 → 混料空间 → 多目标优化 |
| **性能优化** `IMPROVEMENT` | 现场失效 | 9 步 | 跳过全套工况重推，聚焦瓶颈指标定向改良 |
| **降本替代** `COST_DOWN` | 非劣效性 | 7 步 | 基于成熟基线，划定 CTQ 不劣化底线 |
| **客户定制** `CUSTOMIZATION` | 技术协议/OEM | 7 步 | 以客户指定台架为准，快速匹配成熟平台微调 |
| **机理探索** `EXPLORATION` | 科学假设 | 6 步 | 不考核商业目标，重点提取变量影响规律 |

> 各路线的详细阶段路径见 [`domains/lubricant/README.md § 9.3`](./domains/lubricant/README.md#93-工件链11-步与-5-条路线)。

### 6. 领域技能清单（12 个研发阶段技能 + 1 个环境自检）

每个 Skill 均为自包含目录（`SKILL.md` + `scripts/`），由 OpenCode Agent 运行时扫描加载，无需修改运行时源码即可增删。输出遵循标准 JSON Schema：

| Skill | 阶段 | 产出工件 | 职责 |
|---|---|---|---|
| `project-definition` | Stage 0 | `project.json` | 确认研发性质，定义目标与约束 |
| `duty-definition` | Stage 1 | `duty.json` | 结构化录入 7 大工况 |
| `duty-challenge-analysis` | Stage 1 | `challenge.json` | 从工况推导润滑挑战 Map |
| `failure-ctq-analysis` | Stage 2 | `failure_ctq.json` | 梳理失效机制与 CTQ |
| `test-method-qualification` | Stage 2 | `test_method.json` | 评价方法资格确认 |
| `formulation-design` | Stage 3 | `design_space.json` | 建立混料设计空间与约束 |
| `doe-design` | Stage 3 | `experiment_design.json` | 生成混料实验设计 |
| `experiment-import` | Stage 3 | `experiment.json` | 录入实验结果，校验溯源 |
| `statistical-analysis` | Stage 4 | `model.json` | 回归与响应面建模 |
| `optimization` | Stage 4 | `optimization.json` | 多目标约束优化 |
| `gate-review` | 评审门禁 | `gate.json` | 汇总证据链，执行 GO/HOLD/PIVOT/KILL 决策 |
| `lubricant-rd-agent` | 核心路由 | — | 元技能路由器：跨阶段拦截、性质分流、证据门控 |
| `hello-lubricant` | 环境自检 | — | 验证领域包安装与运行时环境是否就绪 |

### 7. 目录结构

```
Lubricant-R-D-OS/                    # 主仓库（open-science 下游 fork）
└── domains/lubricant/               # ← 本领域包（92 个提交的历史随合并保留）
    ├── README.md  LICENSE           # 领域包完整文档 / MIT
    ├── contracts/
    │   └── state-machine.json       # 阶段状态机（ALLOW / DENY / HOLD 门控）
    ├── schemas/                     # 16 个工件 JSON Schema (Draft 2020-12)
    ├── skills/                      # 13 个技能目录（12 研发阶段 + 1 环境自检）
    ├── domains/lubricant/           # 领域计算引擎与数据层
    │   ├── compute/{cost,doe,statistics,optimization,validation}/
    │   └── db.py                    # SQLite 五表数据层
    ├── tests/                       # 自动化测试套件（13 个可执行测试）
    ├── scripts/                     # 安装、校验、打包、仪表盘生成
    ├── templates/project-workspace/ # 新项目工作区模板
    ├── fixtures/  data/  integrations/
    └── PHASE4*.md                   # Phase 4 引擎设计文档
        REAL_CASE_WGO_001*.md        # 真实课题（V600 风电齿轮油）记录
```

> ⚠️ **已知冗余**：领域包内部也有一个 `domains/lubricant/` 命名空间（Python 包路径 `domains.lubricant.compute...`），合并后成为 `domains/lubricant/domains/lubricant/`。这是原样保留的 —— 扁平化会破坏所有引擎的 import 路径，收益不抵风险。

---

## ▾ 以下为上游 Lubricant Science Desktop 原始说明

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
