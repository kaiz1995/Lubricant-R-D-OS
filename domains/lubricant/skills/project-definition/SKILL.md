---
name: project-definition
description: Turn a complete lubricant R&D project brief into a traceable seven-block Project Charter at PROJECT_DEFINED; preflight verifies project classification, objectives, constraints, the cost basis and evidence (a benchmark is optional background only, never a gate). Use when user mentions "project-definition", "项目立项", "立项章程", "Project Charter", "新项目启动", or starting PROJECT_DEFINED in lubricant development.
---

# Project Definition (PROJECT_DEFINED)

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
6. `PROCESS_ROBUSTNESS` (工艺稳健性): 配方已定，只考工艺。跳过工况定义与挑战推导，直接由失效/CTQ 与已评定方法切入设计空间；强化工艺空间（不做多目标优化，故不含 `OPTIMIZED`），以工艺窗口为主输出，末尾经 `APPLIED`（应用与整机验证）证明批次一致性。
7. `PRECISION_GREASE_DEV` (精密传动脂开发): 配方与工艺共同定义产品（皂纤维骨架由皂化 / 转相 / 冷却 / 研磨决定），台架是瓶颈：小批序贯、内环循环 N 轮，最终判据只在整机（启动扭矩 / 回差 / 温升 / 寿命）。

> 允许的 `project_type` 以 `schemas/project.schema.json` 的 `project_type` 枚举为唯一权威（上列 7 类是它的取值），preflight 直接读该枚举、不再另存第二份清单；枚举读不到即 fail-closed。

### Seven-Block Charter Structure（七板块结构，2026-10-15 立项重构）

章程按七板块收集与记录，`reducer_model` 起的是脂类路线的真实起点作用（机型决定工况、摩擦副材料与表面处理）：

| # | 板块 | 字段 | 说明 |
|---|---|---|---|
| 1 | 项目基本信息与性质 | `project_id` / `project_name` / `project_type` / `product_family` / `owner` | 身份与权责，沿用原有字段 |
| 2 | 减速器机型与硬件载体 | `reducer_model` | 必填子字段 `model_size`（枚举 `14/17/20/25/32`）、`structure_form`（枚举 `CUP`/`HAT`/`ULTRA_FLAT`/`OTHER`）、`friction_pair_materials`（数组，如柔轮/刚轮材质）；可选 `reduction_ratio`、`surface_treatment`（含是否 DLC） |
| 3 | 商业诉求与交付形态 | `business_objective` / `application_scenario` / `delivery_form` | `application_scenario` 枚举 `INDUSTRIAL_ROBOT`/`COBOT`/`SEMICONDUCTOR_MEDICAL`/`AEROSPACE_DEFENSE`；`delivery_form` 枚举 `LAB`（500 g–2 kg）/`PILOT`（20–50 kg）/`PRODUCTION`（吨级） |
| 4 | 技术攻关焦点 | `technical_objective` | 本项目的技术主攻方向 |
| 5 | 边界与硬约束 | `hard_constraints` | 非空列表 |
| 6 | 成本天花板 | `cost_position` / `cost_ceiling` / `cost_basis_reason` | `cost_position` 只允许 `CEILING`：单机填脂量 10–50 g、性能与寿命绝对优先、不设主动降本目标。成本是约束，永不进入 CTQ |
| 7 | 成功判据与风险评级 | `success_criteria` / `success_criteria_status` / `risk_class` | `success_criteria_status` 枚举 `PROVISIONAL`/`FIXED`，允许暂定态，由第 3 步（`FAILURE_MECHANISM_DEFINED`）细化 |

> 板块 2 一旦声明就必须完整：只报机型不报摩擦副材料会让下一步（工况定义）用假设补空，preflight 直接拒绝半成品载体。**对油品路线可选的是**：整个板块 2、板块 3 的 `application_scenario` / `delivery_form`、板块 6 的 `cost_position` / `cost_ceiling`；`business_objective` 与成本依据（`target_cost` 或 `cost_basis_reason`）始终必填——六个油品章程不受影响。

### Interaction Rule
- **Mode A (自然语言预判与确认)**: 若用户已有初步描述，分析背景后推荐最可能类型并请用户确认：
  > "根据您的项目信息，本项目判定为【XX】性质的开发工作。请确认是否以此类型启动？（1. 新产品正向开发 2. 已有产品性能优化 3. 降本替代 4. 客户定制 5. 机理/平台型探索 6. 工艺稳健性 7. 精密传动脂开发）"
- **Mode B (主动提示用户选择)**: 若无足够背景，展示 7 种类型让用户选择后再索取输入。
- **No Form Dumping**: 禁止一次性堆叠索取全部七板块字段或工况参数，仅按确认的项目类型逐步索取核心输入。

### Benchmark Sourcing Rule（基准产品提问纪律）

向用户提问"成本天花板与基准产品（可选）"时：

0. **对标是可选背景，不是门槛**（2026-10-15 立项重构）：`benchmark_products` 只作背景备注，**不填也可以**，且**不再需要任何豁免理由**——真正的对标在第 4 步（`REFERENCE_MATERIAL_RESOLVED` 参照物卷宗）按实物建档。`benchmark_waiver_reason` 保留为 legacy 字段（旧章程仍合法），但**不再要求**。提问时不得把对标写成必答项，也不得暗示"没有对标就不能立项"。
1. **先判应用域与产品形态**（油/脂/干膜/固体润滑），再生成对标选项。谐波减速器、丝杠导轨等精密传动应用以**润滑脂**为主，不得默认按"润滑油"框架提问。
2. **若用户要填对标，选项只能来自** `references/application-ecosystems.md` 中该应用域的生态图（随机配套标杆、专业供应商、确有产品线的国产厂家）。
3. **生态图未覆盖的应用域**：请用户直接提供基准产品，或明确授权调研后再提问，禁止用行业通用品牌兜底。
4. **禁止默认把长城/昆仑/统一等综合润滑油品牌列为"国产一线对标"**——仅当其在该应用域确有专用产品线时才可列入；否则等同于编造基准产品（见第 5 节黑名单）。

---

## 2. Input Specification

A valid input JSON is read as the seven blocks (2026-10-15 refactor). The grease-route additions — block 2 as a whole, block 3's `application_scenario` / `delivery_form`, and block 6's `cost_position` / `cost_ceiling` — stay optional for the six oil routes; everything the old contract required is still required.

**Block 1 — basic identity and nature**
- `project_id` (alphanumeric, `.`, `_`, `-`), `project_name`, `project_type` (one of the types declared by `schemas/project.schema.json` — the six oil routes plus `PRECISION_GREASE_DEV`), `product_family`.
- `owner` is required; `risk_class` (`LOW`, `MEDIUM`, `HIGH`, `STRATEGIC`) belongs to block 7 but is required on every route.

**Block 2 — reducer model and hardware carrier (grease route)**
- `reducer_model` is **optional as a whole, but complete once declared** (a half-declared carrier would let the duty step invent the rest, so preflight refuses it):
  - Required sub-fields: `model_size` (enum `14` / `17` / `20` / `25` / `32`), `structure_form` (enum `CUP` / `HAT` / `ULTRA_FLAT` / `OTHER`), `friction_pair_materials` (non-empty array, e.g. 柔轮/刚轮材质).
  - Optional sub-fields: `reduction_ratio` (as the OEM states it, e.g. `100:1`), `surface_treatment` (including whether a DLC coating is present).
  - Unknown sub-fields are rejected (`additionalProperties: false`).

**Block 3 — commercial intent and delivery form**
- `business_objective` is required on every route.
- `application_scenario` (optional; enum `INDUSTRIAL_ROBOT` / `COBOT` / `SEMICONDUCTOR_MEDICAL` / `AEROSPACE_DEFENSE`).
- `delivery_form` (optional; enum `LAB` = 500 g–2 kg, `PILOT` = 20–50 kg, `PRODUCTION` = 吨级).

**Block 4 — technical focus**
- `technical_objective` is required on every route.

**Block 5 — boundaries and hard constraints**
- Non-empty `hard_constraints`.

**Block 6 — cost ceiling**
- Cost is a CONSTRAINT, never a CRITERION. `target_cost` stays legal when supplied and keeps its complete measurement metadata (`value`, `unit`, `source`, `method_version`, `material_batch`, `formula_version`); when it is absent a non-empty `cost_basis_reason` is mandatory instead.
- `cost_ceiling` (optional measurement) records the highest unit cost the product may carry.
- `cost_position` (optional) accepts **`CEILING` only**: 单机填脂量 10–50 g、性能与寿命绝对优先、不设主动降本目标. Any other posture is refused — a grease charter never carries a reduction target.

**Block 7 — success criteria, provisional state and risk class**
- Non-empty `success_criteria` and a non-empty `risk_class`.
- `success_criteria_status` (optional; enum `PROVISIONAL` / `FIXED`). `PROVISIONAL` is legal and expected at charter time (客户整机阈值尚未谈定时如实记录，好过编造数字); step 3 (`FAILURE_MECHANISM_DEFINED`) refines it, and a provisional set must be re-visited there.

**Benchmark (optional background, not a block and not a gate)**
- `benchmark_products` is **optional background only** (2026-10-15 refactor): a name or two recorded for context. It is never a gate — the comparator that matters is the physical dossier built at step 4 (`REFERENCE_MATERIAL_RESOLVED`), so an absent list is legal on every route.
- `benchmark_waiver_reason` is a **legacy field**: kept so charters that already carry it stay valid, but **no longer required**. An absent benchmark needs no waiver.

**Evidence**
- Non-empty `source_evidence` with status `OBSERVED`.

---

## 3. Deterministic Execution Workflow

All scripts reside in `skills/project-definition/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/project-definition/scripts/preflight_project_definition.py <input.json>
```
- Expected output on success: `READY: input can form a PROJECT_DEFINED charter only` (exit code 0).
- On failure: Outputs missing/invalid fields and exits with code 1.

### Step 2: Build Project Charter Artifact
```bash
python skills/project-definition/scripts/build_project_artifact.py <input.json> <temporary-file.json>
```
- Deterministically assembles the candidate charter: `stage: "PROJECT_DEFINED"` (constant marker), `status: "ACTIVE"`, the 7 canonical decision fields (`decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`, `decision`, `next_action`), and the input's project fields and `source_evidence` verbatim — no value is invented. Expected output on success: `BUILT: <temporary-file.json>` (exit code 0).
- On failure: Refuses with the same `HOLD: missing or invalid: ...` findings as Step 1 and writes no artifact.

### Step 3: Validate Artifact
```bash
python skills/project-definition/scripts/validate_project_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: project artifact conforms to Project Charter schema` (exit code 0).

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` only after Step 3 passes.
- The landed name must be the canonical stage name `project.json` (or the legal suffixed form `project-<project_id>-<id>.json`), directly under the workspace root. The panel and `scripts/check_artifact_naming.py` match it exactly; a name like `project.grease.json` is classified as a mangled stage artifact and the stage would read as missing. A temp/suffixed candidate name used for Step 2/3 must not be the name that lands.
```bash
# 🔴 CHECKPOINT · STOP: the Project Charter stops here at PROJECT_DEFINED. Next station per project_type: DUTY_DEFINED (NEW_PRODUCT, PRECISION_GREASE_DEV), FAILURE_CTQ_DEFINED (IMPROVEMENT, COST_DOWN, CUSTOMIZATION, PROCESS_ROBUSTNESS), or DESIGN_SPACE_DEFINED (EXPLORATION).
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: missing required fields: project_type` | 未确认项目性质 | **STOP**。暂停并启动 Mode A/B 协议向用户确认项目分类。 |
| `HOLD: ... target_cost (or cost_basis_reason when no cost target is set)` | 既无成本上限也无成本依据说明 | **STOP**。要求用户提供成本上限数值与单位，或写明不设成本目标的原因（`cost_basis_reason`）；不推测默认值。 |
| `HOLD: ... cost_position must be CEILING when supplied` | 成本姿态写成降本目标 | **STOP**。脂路线成本只能是天花板：改写 `cost_position = CEILING`，成本不得作为 CTQ 判据。 |
| `HOLD: ... reducer_model.<sub-field>` / `reducer_model.model_size is invalid` / `reducer_model.structure_form is invalid` | 机型载体半声明或取值越界 | **STOP**。补齐 `model_size` / `structure_form` / `friction_pair_materials`，或整体不填；不得让下一步用假设补空。 |
| `HOLD: ... success_criteria_status must be PROVISIONAL or FIXED` | 成功判据状态取值非法 | **STOP**。判据未定就记 `PROVISIONAL`（合法），定了才记 `FIXED`；不得用编造阈值绕过。 |
| `HOLD: source_evidence contains GAP or missing` | 缺少输入证据或立项依据不足 | **STOP**。要求提供立项技术简报或客户协议编号，不伪造证据条目。 |
| `FAIL: cannot read artifact or schemas` | JSON 损坏或 schema 路径错误 | 校验文件编码与 JSON 语法，修复后重新运行校验。 |

> **已不再是失败**（2026-10-15 立项重构）：未填 `benchmark_products` **是合法的**，不构成 HOLD，也不再要求 `benchmark_waiver_reason`。对标是可选背景，真正的对标在第 4 步按实物建档。Agent 不得因为"没有对标"而拦住用户。

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Downstream Artifact Generation**: DO NOT create Duty, Challenge, Failure CTQ, Test Method, Formulation, DOE, or Optimization artifacts in Stage 0.
2. **NO Synthetic Assumptions**: DO NOT invent benchmark products, performance values, cost figures, or evidence sources. 对标既然只是可选背景，就更没有编造它的理由：**不填是合法的，编造不是**。此约束同样覆盖**交互提问阶段**——向用户展示的对标选项若与应用域生态不符（如对无产品线品牌套用"国产一线"），视同编造。
3. **NO Benchmark Gate**: DO NOT block a charter for naming no benchmark, and DO NOT demand a `benchmark_waiver_reason`. 对标不是门槛；真正的对标在第 4 步（`REFERENCE_MATERIAL_RESOLVED`）按实物建档。
4. **NO Cost Reduction Target**: DO NOT record a cost posture other than `CEILING` on a grease charter, and DO NOT let cost enter a CTQ. 成本是天花板与约束，不是优化目标。
5. **NO Half-Declared Carrier**: DO NOT record a partial `reducer_model`（只报机型不报摩擦副材料）——半成品载体等于把编造权交给下一步，preflight 直接拒绝。
6. **NO Dirty Overwrites**: DO NOT overwrite existing non-project files or files with mismatched `project_id`.
7. **NO Silent Advance**: DO NOT proceed to Stage 1 without user confirmation of the Project Charter.

