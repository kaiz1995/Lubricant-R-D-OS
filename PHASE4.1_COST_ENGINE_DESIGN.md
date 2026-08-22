# Phase 4.1 Cost Engine 设计（PHASE4.1_COST_ENGINE_DESIGN）

状态：待用户 Review。Review 通过前不写任何实现代码。

---

## 1. 定位

Cost Engine 不是财务系统，不做库存、采购或总账。它是配方设计阶段的成本决策组件：给定一个配方的组成与材料价格表，产出总成本、组分贡献与成本结构解释，供 DOE 目标设定、Optimization 约束和 Gate Review 引用。

边界（Phase 4.1 明确不做）：

- 自动采购价格预测 / AI 价格预测 / Bayesian 成本模型；
- 市场数据爬取；
- Process Cost、Packaging Cost、Manufacturing Cost（仅接口预留，见 §6）。

## 2. Mathematical Model

基础模型（第一阶段唯一公式）：

```text
C = Σ(x_i × p_i)        i = 1..n
S_i = (x_i × p_i) / C   （cost contribution ratio, C > 0）
```

- x_i：组分质量分数（0 < x_i ≤ 1，Σx_i = 1 ± 1e-9）。
- p_i：该组分的单位价格（> 0；= 0 拒绝——免费原材料在研发语境下几乎必然是数据录入错误，宁可 HOLD）。
- S_i：成本贡献占比 ∈ (0, 1]，ΣS_i = 1。

浮点处理：求和用 `math.fsum` 保证顺序无关的确定性；输出保留全精度，不四舍五入（展示层自行格式化）。相同输入 + 相同 parameters → 逐字节相同输出。

后续扩展（本期不实现，仅在 §4 注记占位方向）：

- 价格敏感度 ∂C/∂p_i = x_i（线性模型下解析解）；
- 配方敏感度 ∂C/∂x_i = p_i − C（替换视角）；
- 价格区间不确定性（p_low/p_high → C 区间）；
- Process / Packaging / Manufacturing cost 附加项。

## 3. Input 契约

新增独立输入 schema（不与 result 混装），目录同 `domains/lubricant/schemas/`：

```text
cost_input.schema.json
```

数据模型：

```yaml
Material:
  material_id: string (pattern ^[A-Za-z0-9][A-Za-z0-9._-]*$)
  name: string
  category: enum [BASE_OIL, ADDITIVE, THICKENER, OTHER]
  supplier: string | null (optional)
  unit: const "CNY_PER_KG"
  price: number > 0（exclusiveMinimum 0）
  currency: const "CNY"
  effective_date: string (date format)

Formula:
  formula_id: string
  version: string
  components:
    - material_id: string（必须存在于 materials 表）
      fraction: number (0 < fraction <= 1)

Input top-level:
  input_type: const "COST_CALCULATION"
  formula: Formula
  materials: Material[]          # 价格表整体传入，引擎无内置价
  price_timestamp: string (date) # 追溯锚点，写入 evidence
```

关键约束：

- **价格不硬编码**：materials 表由调用方传入，engine.py 内零价格常量。
- fraction 总和校验：|Σx_i − 1| ≤ 1e-9，否则 REJECTED。
- material_id 重复（formula 或表内）→ REJECTED。
- formula 引用表中不存在的 material_id → REJECTED（缺失价格拒绝）。

## 4. Output 契约（Schema Versioning）

```text
compute_envelope.schema.json : 冻结不动
cost_result_schema.json      : 1.0.0 → 1.1.0（additive extension）
cost_input.schema.json       : 新增 1.0.0
```

cost_result_schema 变更内容——result 内新增 required 字段组 `sensitivity`：

```yaml
sensitivity:
  ranking:                       # ComponentContribution[]，按 percentage 降序
    - component_id: string
      contribution: number       # x_i × p_i 原值
      percentage: number         # S_i × 100
  method_note: const "CONTRIBUTION_RATIO_V1"
```

版本判定说明：

- sensitivity 定义为 **required**（采纳你的建议）。理由：Cost Engine 的研发价值是成本解释而非报价；没有 sensitivity 的结果无法回答"调哪个组分最有效"，属于不完整交付。
- 为什么旧结果无法满足新契约：1.0.0 结果缺 sensitivity，按 1.1.0 校验必 FAIL。
- Migration 政策：**不做迁移工具**。理由：Phase 4 无生产历史结果，仓库内不存在任何 1.0.0 结果实例 fixture（正例仅存于测试内存对象）。政策：旧文件可读但标记 legacy_incomplete；新产出一律 1.1.0。
- schema_version 字段保持信封级 "0.1.0" 不变——它标识 envelope 协议版本而非模块契约版本；模块版本由 engine_version 承载（cost 引擎 0.1.0 起步）。本次 additive bump 在 CHANGELOG 注记 1.0.0→1.1.0。

## 5. Sensitivity 定义

第一阶段公式即 §2 的 S_i。ranking 按 percentage 降序输出并附原始数值双份（contribution + percentage），消费方无需重复计算。method_note 固定字符串锁定算法版本——未来换算法时旧 ranking 不被误读为新口径。并列贡献时排序键为 component_id 字典序，保证 Deterministic First。

∂C/∂p_i 与 ∂C/∂x_i 属后续扩展，本期 schema 不出现。

## 6. Validation Strategy

```text
tests/compute/test_cost_engine.py   （main() 断言直跑风格，沿用现有模式）
├── 单组分 100%              → C = p_1, S_1 = 1.0
├── 多组分混合               → 手算锚点逐值断言（3 组分固定数）
├── Σfraction ≠ 100%（±1e-9 外）→ REJECTED
├── 缺失价格（引用未登记 material_id）→ REJECTED
├── price = 0                → REJECTED（schema 层 exclusiveMinimum 拦截）
├── negative price           → REJECTED（schema 层 + 引擎双保险）
├── 重复 material_id         → REJECTED
├── 极端输入：fraction 1e-12、单价 1e6 → 不溢出、fsum 一致
├── sensitivity 稳定排序     → 并列贡献按 component_id 字典序断言
├── Deterministic First      → 同一输入跑两遍，输出全文 sha256 相等
└── fixture 复现             → fixtures/compute/cost-gold-input.json 金输出哈希锁死
```

fixture 语义（Phase 4.0 Gate 决议）：每个 fixture 只对应一个契约——cost 输入 fixture 只验 input schema，金输出只验 cost_result_schema，不复用不混装。

## 7. 与 Agent / Skill 连接

```text
formulation-design Skill (DESIGN_SPACE_DEFINED)
        │  调用方组装 cost_input（formula + materials 表）
        ▼
domains/lubricant/compute/cost/engine.py
  CLI: python -m domains.lubricant.compute.cost.engine <input.json> <output.json>
        │  校验 input schema → 计算 → 组装 envelope
        ▼
cost_result artifact（scripts/validate_compute_result.py 校验）
        ├──▶ optimization（目标函数成本项输入）
        └──▶ gate-review（成本证据链）
```

Phase 4.1 只做 engine.py 及 CLI；Skill 文件零改动。formulation-design SKILL.md 第 15 行明确禁止该 Skill 自行生成 cost——计算完全下沉引擎，符合既有决策边界。

## 8. 实施清单（Review 通过后执行）

1. cost_input.schema.json 新增；
2. cost_result_schema.json 1.0.0→1.1.0 additive 扩展；
3. compute/cost/engine.py（纯函数 + CLI + input schema 自校验）;
4. tests/compute/test_cost_engine.py 全套 §6 用例；
5. fixtures/compute/cost-gold-input.json + 金输出哈希；
6. 回归：Phase 4.0 测试与 Phase 3 全量测试仍绿。
