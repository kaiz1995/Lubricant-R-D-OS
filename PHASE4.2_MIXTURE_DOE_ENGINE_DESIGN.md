# Phase 4.2 Constrained Mixture DOE Engine 设计

状态：待用户 Review。Review 通过前不写任何实现代码。

---

## 1. 定位与上游关系

DOE Engine 是 Phase 3 `doe-design` Skill（EXPERIMENT_DESIGNED，run_plan.point_generation=PHASE4_DETERMINISTIC_ENGINE）的确定性承接方：把已批准的实验设计请求变成可执行、可复现的实验点矩阵 + Experiment Card。

职责边界（与 doe-design Skill 的 Output boundary 对齐）：

- Skill 只做请求记录与 handoff 资格判定（SKILL.md 第 36 行：Phase 4 alone generates deterministic DOE points）；本引擎只产点，不做统计充分性、模型适当性或任何下游结论。
- 引擎不产生 observed 数据、不推进状态机——实验执行仍属人工/外部环节。

## 2. Input 契约

新增 `domains/lubricant/schemas/doe_input.schema.json`（1.0.0）：

```yaml
doe_input:
  input_type: const "MIXTURE_DOE_DESIGN"
  components:                    # ≥3，≤12（q>12 混料设计失去工程意义，直接拒绝）
    - component_id: string (pattern 同现有)
      lower_bound: number [0,1]
      upper_bound: number [0,1]   # lower <= upper
  mixture_total: number (0,1]    # 默认 1.0，显式传入
  design_type: enum [SIMPLEX_MIXTURE, D_OPTIMAL_MIXTURE]   # 第一阶段仅此两种
  model_order: enum [LINEAR, QUADRATIC]   # 决定格点阶数 m
  target_runs: integer >= 0      # 仅 D_OPTIMAL 使用；SIMPLEX 必须为 0（run 数由格点结构决定）
  responses:                     # ≥1，来自 experiment_design 请求的 CTQ 集合
    - ctq_reference: string
      test_method_reference: string
      role: enum [OPTIMIZATION_RESPONSE, GUARDRAIL, DIAGNOSTIC_RESPONSE]
  experiment_card:               # 八字段全必填，缺一 → REJECTED
    decision_question / hypothesis / variables_note / constraints_note /
    responses_note / doe_selection_reason / expected_information_value / decision_rule
```

可行性前置校验（全部 REJECTED 路径）：

- Σlower_bounds ≤ mixture_total ≤ Σupper_bounds；
- 每个 component 单独可行：mixture_total − Σ(other uppers) ≤ upper_i，且 mixture_total − Σ(other lowers) ≥ lower_i；
- component_id 重复 → 拒绝；
- bounds 顺序颠倒（lower > upper）→ 拒绝。

单位约定：本期所有 fraction 为归一化质量分数（无单位比例），与现有 design_space fixture 的 normalized fraction 一致；带物理单位的混料留待后续版本。

## 3. 算法（Deterministic First）

### 3.1 Simplex Mixture Design（Scheffé 格点）

```text
m = {LINEAR: 1, QUADRATIC: 2}[model_order]
格点集 G = { x ∈ Z≥0^q : Σx_i = m }，每点坐标 x_i/m 即配方比例
```

枚举按元组字典序升序（天然确定性）。约束处理：

- 可行性过滤：x_i/m ∈ [lower_i, upper_i] 且 Σ=1；
- 过滤后为空 → **REJECTED（infeasible after lattice filtering），不投影**。理由：最近可行投影破坏格点正交性与文献可比性，且掩盖约束本身的设计问题——宁可 HOLD 不造点。

run 数由结构决定：无约束 LINEAR = q 点；QUADRATIC = C(q+1, 2) 点。有约束时为过滤后剩余数。target_runs 输入必须为 0，防止调用方误以为可指定。

### 3.2 D-optimal Mixture Design（贪心行列式最大化）

候选集构造：

1. 全体单纯形候选点（LINEAR 与 QUADRATIC 两套格点的并集）∩ 可行域过滤（规则同上，不可行剔除、不投影）；
2. 追加结构增强点：各约束顶点、可行总中心点、各 component 中界轴点（若可行）；
3. 全部候选去重后按元组字典序固定排序——全程无随机数。

选择算法：

```text
X = Scheffé 二阶模型矩阵（列序固定：q 个线性项按 component 字典序，C(q,2) 个交互项 x_i·x_j 按 i<j 字典序）
满秩前提：候选集中不存在使 X'X 可逆的 p 元组 → REJECTED（model not estimable with feasible candidates）
贪心：p = 模型参数数；先在全体候选中穷举首个 p 元组（字典序遍历）取 det(X'X) 最大者为起点，
     之后逐轮扫描全部候选（字典序），单点换入使 det(X'X) 相对增幅 > 1e-12 则交换；无增幅即收敛。
输出 run 数 = max(target_runs, p)，上限为候选总数。
```

数值方法：det 用 LU 分解（stdlib 手写，约 30 行），q≤12 时稳定；不用连乘展开。

**适用范围声明（写入 engine.py docstring 与 ponytail 注释）**：贪心行列式最大化是 D-optimal 的一阶近似，候选规模 ≤ 数百、因子 ≤ 12 时工程可用；不保证全局最优（已知精度上限）。升级路径：Fedorov exchange algorithm（逐轮非劣保证）→ 先进 optimal design 库。Phase 4 明确不升级。

## 4. Output 契约

新增 `domains/lubricant/schemas/doe_result_schema.json`（1.0.0，allOf compute_envelope）：

```yaml
engine_name: const "doe"
engine_version: "0.1.0"
method: SIMPLEX_LATTICE_V1 | D_OPTIMAL_GREEDY_DET_V1
result:
  design_type: 同 input enum
  model_order: 同 input enum
  runs:
    - run_index: integer 从 1 起（run_id 由消费方命名，引擎不给语义 id）
      proportions: {component_id: fraction}   # Σ 精确 == 1.0
  run_count: integer
  candidates_considered: integer     # 审计字段；simplex 时等于 run_count
  selection_reason: string           # 固定文案模板，含 q/m/约束摘要
```

Experiment Card 处理：八字段不复制进 result——decision_question/hypothesis/decision_rule/expected_information_value 映射到 envelope 顶层既有公共决策字段，variables/constraints/responses 细节进 evidence statement。单一信息源，避免双份漂移；Gate 文档要求的八要素全覆盖。

proportions 精度机制：内部全程整数份计数（x_i ∈ Z，Σx_i = m·K），仅输出层除以 m·K——Σproportions 无浮点累加误差。

## 5. Validation Strategy

```text
tests/compute/test_doe_engine.py （main() 断言直跑）
├── q=3 无约束 LINEAR simplex → 3 顶点 {(1,0,0),(0,1,0),(0,0,1)} 文献锚点
├── q=3 无约束 QUADRATIC simplex → 6 点（3 顶点 + 3 二元中点）经典 Scheffé 结构
├── centroid 负向断言 → 本期 m≤2 不含 (1/3,1/3,1/3)
├── 有界约束过滤 → bounds [0.2,0.8] 型 fixture：顶点剔除、棱心保留
├── 不可行约束组合 → REJECTED（Σlowers > total 或 Σuppers < total）
├── 缺 Experiment Card 任一字段 → REJECTED
├── SIMPLEX + target_runs > 0 → REJECTED
├── 重复 component_id / lower > upper → REJECTED
├── D-optimal 小锚点 → 候选数恰等于 p 时全选（退化为完整格点，可手验）
├── D-optimal 收敛行为 → 无增幅即停；candidates_considered 记录正确
├── proportions 和恒等断言 → sum(runs[i].proportions.values()) == 1.0 浮点精确成立
├── Deterministic First → 同输入双跑字节相等
└── 金 fixture 复现 → 4 组分 WGO 场景 D_OPTIMAL target=16，金输出哈希锁死
```

fixture 语义延续 Gate 决议：input fixture 只验 input schema；金输入/金输出成对入库，哈希写入测试。

## 6. 与 Agent / Skill 连接（闭环位置）

```text
formulation-design ──▶ doe-design Skill（EXPERIMENT_DESIGNED 请求记录，已有）
                              │ run_plan.point_generation = PHASE4_DETERMINISTIC_ENGINE
                              ▼
compute/doe/engine.py   CLI: python -m domains.lubricant.compute.doe.engine <input.json> <output.json>
                              │ input schema 校验 → 可行性 → 点生成 → envelope
                              ▼
doe_result artifact（scripts/validate_compute_result.py 校验）
                              │ 人工执行实验（引擎外）
                              ▼
experiment record（EXPERIMENT_RUNNING，schema 已有）
                              ▼
statistics engine（Phase 4.3 接力）
```

Skill 文件零改动。CLI 失败路径同样走 envelope REJECTED 落盘（沿用 cost engine 模式）。

## 7. 明确不做（本期）

- Mixture×Process / RSM / Robust Design（占位声明见 PHASE4_DESIGN §8）；
- Bayesian Sequential Design（Phase 3 已在 Skill 层 HOLD，引擎 enum 直接不含）；
- 投影/修复类约束处理（§3.1 论证拒绝理由）;
- 随机化（randomized 是请求层计划信息；点矩阵确定性生成，运行顺序随机化属实验室执行事项，不进引擎）。

## 8. 实施清单（Review 通过后执行）

1. doe_input.schema.json 新增；
2. doe_result_schema.json 新增；
3. compute/doe/engine.py（simplex 先行、D-optimal 贪心随后、LU 工具函数）；
4. tests/compute/test_doe_engine.py 全套 §5 用例；
5. fixtures/compute/doe-gold-input.json / doe-gold-output.json + 哈希；
6. 回归：cost engine 测试、Phase 4.0 契约测试、Phase 3 全量仍绿。
