# Phase 4.4 Optimization Engine 设计

状态：待用户 Review。Review 通过前不写任何实现代码。

---

## 0. 定位

Phase 4.4 Optimization Engine 是研发闭环中"从统计模型到推荐候选"的确定性筛选器。它不是通用优化库，而是：

Statistical Model (Phase 4.3 output) → Candidate Space（Grid Search 枚举）→ Hard Constraint Filtering → Guardrail / Non-inferiority Filtering → Feasible Region → Pareto Ranking / Weighted Objective Ranking → Recommended Candidates → Gate Review

核心设计原则：

1. 先可行性，后优化。任何排序都只在通过硬约束和性能门槛的 Feasible Region 内进行。
2. 成本不能抵消关键性能不合格。性能不合格的候选无论多便宜都不进入 Feasible Region。
3. 只消费 Phase 4.3 模型，不重新拟合。引擎输入是 statistics_result envelope 中的系数向量 + term_order + model_order。
4. Cost 复用 Phase 4.1 Cost Engine。不重复实现成本公式。
5. 禁止模型有效域外静默外推。Grid Search 的候选空间必须限制在 DOE 设计空间的有效域内。
6. Deterministic First。同输入字节级一致输出。
7. 输出是待验证候选，不是最终配方。

第一版允许的方法（且仅限）：Grid Search / Constraint Filtering / Non-inferiority Filtering / Pareto Ranking / Weighted Objective Ranking。

明确排除：Bayesian Optimization / Random Search / Genetic Algorithm / RL / Active Learning / Agent 自主优化。

---

## 1. Input 契约

新增 domains/lubricant/schemas/optimization_input.schema.json（version 1.0.0）。

### 顶层结构

- input_type: const "OPTIMIZATION_REQUEST"
- statistical_models: ≥1 项，来自 statistics_result envelopes
  - ctq_reference: string
  - model_order: enum [LINEAR, QUADRATIC]
  - coefficients: [{term: string, estimate: number}]，从 statistics_result.result.coefficients 提取
  - term_order: [string]，显式记录列序
  - r_squared: number
  - sigma_squared: number
- candidate_space:
  - component_ids: [string]，≥3，≤12，字典序必须与 term_order 中 x_ 后缀一致
  - bounds: [{component_id, lower, upper}]，每维 [0,1]
  - grid_resolution: integer，≥2；总格点数硬上限 10000
    （ponytail: 第一版全枚举；如需更大空间改用 adaptive refinement）
- hard_constraints: 可为空数组
  - constraint_id, reference_id (ctq 或 COST), direction (MINIMIZE/MAXIMIZE), threshold
- guardrails:
  - guardrail_id, ctq_reference
  - direction: enum [HIGHER_IS_BETTER, LOWER_IS_BETTER]
  - minimum_margin: number
  - tolerance_mode: enum [RELATIVE_PERCENT, ABSOLUTE]（默认 RELATIVE_PERCENT）
- baseline:
  - proportions: {component_id: fraction}，Σ=1.0
  - ctq_values: {ctq_reference: number}
  - total_cost: number（可选）
- cost_input:
  - materials: 与 cost_input.schema.json 一致
  - formula_template: 不带 fraction 的 component 列表
- ranking_method: enum [PARETO, WEIGHTED_OBJECTIVE]
- weights: 仅 WEIGHTED_OBJECTIVE 时必填；所有 weight > 0 且 Σ=1.0
  - [{objective_ref, weight}]，objective_ref 可以是 ctq_reference 或 "COST"
- max_recommendations: integer，默认 10

### 前置校验（REJECTED 路径）

- component_ids 与 term_order x_ 后缀不一致 → REJECTED
- bounds.lower >= bounds.upper → REJECTED
- sum(lower) > 1.0 或 sum(upper) < 1.0 → REJECTED（simplex 无交集）
- 候选点总数 > 10000 → REJECTED
- guardrails.ctq_reference 不存在于 statistical_models → REJECTED
- baseline.proportions sum != 1.0 → REJECTED
- ranking_method=WEIGHTED_OBJECTIVE 且 weights 缺失或 sum != 1.0 → REJECTED
- cost_input.materials 为空 → REJECTED

---

## 2. Output 契约

新增 domains/lubricant/schemas/optimization_result_schema.json（version 1.0.0）。

基于 compute_envelope（allOf），additionalProperties=false。

result 结构：
- total_candidates_evaluated: integer
- hard_constraint_passed: integer
- guardrail_passed: integer（即 feasible region 大小）
- pareto_front_size: integer（仅 PARETO 方法时非零）
- recommended_candidates: 排序后推荐候选列表（不使用 best_formula）
  - rank: integer（1-based 连续编号）
  - candidate_role: enum [PARETO_FRONT, WEIGHTED_RANK_TOP, MIN_COST_FEASIBLE]
  - proportions: {component_id: fraction}
  - predicted_ctq: {ctq_reference: number}
  - total_cost: number
  - currency: string
  - in_pareto_front: boolean
  - weighted_score: number | null（WEIGHTED_OBJECTIVE 时有值）
  - margin_report: [{guardrail_id, margin_value, passes}]
- method_summary:
  - ranking_method: string
  - grid_resolution: integer
  - effective_domain_note: string

---

## 3. Hard Constraint / Guardrail / Non-inferiority 语义区别

| 层次 | 性质 | 失败后果 | 示例 |
|------|------|----------|------|
| Hard Constraint | 绝对边界，不可违反 | 候选被丢弃 | 总成本 <= 5000 元/批 |
| Guardrail | 关键性能最低门槛（相对 baseline） | 候选被丢弃，无论多便宜 | 油膜强度不得低于 baseline 的 95% |
| Non-inferiority | 多维度相对比较 | 候选被丢弃 | 所有 CTQ 均不劣于 baseline 超过容差 |

三层依次执行：Hard → Guardrail → Non-inferiority → 幸存者 = Feasible Region。

Cost 可承担两种角色：
COST_CONSTRAINT：资格门槛（Hard Constraint 层）。
MINIMIZE_COST_OBJECTIVE：Feasible Region 内排序目标。
降本不达标 → 直接淘汰；达标的再参与排序。
性能不合格者在 Guardrail 就被淘汰，不因成本低而补偿回来。

---

## 4. Margin 定义

Higher-is-better（如粘度指数、油膜强度）：

margin_i = (predicted_i - baseline_ref) / baseline_ref * 100%

passes 当且仅当 margin_i >= minimum_margin

Lower-is-better（如酸值、摩擦系数）：

margin_i = (baseline_ref - predicted_i) / baseline_ref * 100%

passes 当且仅当 margin_i >= minimum_margin

baseline_ref = 0 行为冻结：
- tolerance_mode = RELATIVE_PERCENT 且 baseline_ref = 0 → REJECTED（relative division by zero）。
- tolerance_mode = ABSOLUTE 且 baseline_ref = 0 → 使用绝对偏差，不自动降级。
引擎不得偷偷改变调用者的业务语义。

---

## 5. Statistical Model Artifact 输入及有效域检查

statistics_result envelope 作为 JSON 文件路径传入 CLI，引擎读取 result.coefficients 和 parameters.term_order。

term_order 字符串格式固定：
- LINEAR: x_{component_id}
- QUADRATIC: x_{id_a}*x_{id_b}（a < b 字典序）

引擎按相同规则生成候选点特征向量 X_candidate，dot(X_candidate, beta) 得到预测值。

Domain Guard（Model Domain Guard V1）：

domain_check_method: BOUNDING_BOX_APPROX_V1
检查规则：对每个组分 i：source_doe_min[i] - tol <= x_i <= source_doe_max[i] + tol
source_doe_min/max 来自 DOE design_points 各组分的实际范围，tol=1e-9。
此方法是近似筛查，不能证明候选点为严格 interpolation。
不得在 evidence 或输出中使用 NO_EXTRAPOLATION 表述；使用 DOMAIN_SCREENED_APPROX。

超出 domain 的候选计入 total_candidates_evaluated 但不计入 passed 计数。
method_summary.effective_domain_note 记录 source DOE design space bounds 和 domain_check_method。

如果 candidate_space.bounds 与 DOE design space 无交集 → 整个请求 REJECTED（no candidates within source DOE design space）。

ponytail: BOUNDING_BOX_APPROX_V1; upgrade path: convex hull / polytope support check.

---

## 6. Cost Engine 复用

通过同进程 import 调用 Phase 4.1 Cost Engine public API calculate_cost()。
该 API 必须执行完整审计链路：cost_input validation → input_digest → compute envelope → cost_result schema → evidence。
禁止消费裸 float 或裸 dict 作为成本值；禁止复制成本公式。
cost_envelope.status != OK → 候选标记 COST_CALCULATION_FAILED，不进入结果。
total_cost/currency 从 cost_envelope.result 提取。
每个推荐候选保存 cost_evaluation 引用块 {engine_name, engine_version, input_digest, total_cost}。
价格来源唯一性由 Cost Engine 保证。

---

## 7. Pareto Ranking 与 Weighted Objective 规则

### Pareto Ranking

候选 A dominates B 当且仅当：对所有 objective 维度，A 不劣于 B 且至少一维严格优于 B。
浮点容差 comparison_tolerance = 1e-12 写入 parameters 和 evidence。
dominance 判断统一使用 a >= b - comparison_tolerance。

objective 方向由 guardrails.direction 决定。未出现在 guardrails 中的 CTQ 不参与 Pareto 比较。

Pareto front 内部无排序，按 proportions 字典序稳定排列。

最终推荐列表 = Pareto front 前 max_recommendations 个。

### Weighted Objective Ranking

仅在 Feasible Region 内使用。

归一化方法名 FEASIBLE_SET_MINMAX_V1。min/max 取自当前 Feasible Region（不是全域）。
normalized score 是候选集依赖的——增减候选可能改变同一配方的 score。
此行为记录在 method_summary 中，未来升级时方法名改变以避免语义漂移。

higher_is_better: normalized = (value - min_feasible) / (max_feasible - min_feasible)
lower_is_better: normalized = (max_feasible - value) / (max_feasible - min_feasible)

步骤 2：score = sum(weight_j * normalized_j)

步骤 3：降序排列，同分按 proportions 字典序升序稳定排序。

防退化保证：
- Feasible Region 只有 1 个候选 → 自动 rank=1
- Feasible Region 为空 → status=OK，candidates=[]，evidence 记录原因

关键保证：性能不合格的候选已被 Guardrail/Non-inferiority 淘汰，永远不会出现在 Weighted Score 计算中。因此不可能出现"性能不合格但成本低所以综合分第一"的情况。

---

## 8. Deterministic First、金 fixture 与回归测试方案

### Deterministic 保证

- Grid Search 纯枚举，无随机性
- 排序使用 Python sorted（稳定排序），tie-breaker 为 proportions 字典序
- 浮点运算顺序固定（逐组分遍历顺序 = component_ids 字典序）
- 双跑字节级一致

### 功能测试计划（tests/compute/test_optimization_engine.py）

1. Happy path PARETO：3 组分 QUADRATIC，grid_resolution=5，Pareto front 非空，rank 连续
2. Happy path WEIGHTED_OBJECTIVE：同上，weighted_score 存在且降序
3. Hard constraint 全部淘汰：hard_constraint_passed=0 → candidates=[]
4. Guardrail 过滤：minimum_margin 设高值 → 大部分淘汰
5. Non-inferiority 过滤：某 CTQ 劣于 baseline 超容差 → 淘汰
6. 有效域外排除：bounds 故意超 DOE 观察 → OUT_OF_DOMAIN 排除，计数正确
7. 成本复用验证：手动计算理论成本 vs 引擎输出一致
8. 性能劣但成本低者不出现在结果中
9. 空 feasible region → status=OK，candidates=[]
10. 双跑字节相等
11. 金 fixture SHA256 锁死

### 金 fixture

- fixtures/compute/optimization-gold-input.json
- fixtures/compute/optimization-gold-output.json
- SHA256 写入测试断言

### 回归

全量：Phase 3 e2e + Phase 4.0/4.1/4.2/4.3 全部已有测试。

---

## 9. Future Extension（不在本阶段实现）

- Convex hull 有效域精确判定（替代当前 box 近似）
- Process cost 扩展后自动继承 Cost Engine 升级
- Desirability function（Derringer-Suich）
- Adaptive grid refinement
- Multi-point recommendation with diversity criterion

---

## 10. Schema Versioning

| Schema | Version | 变更类型 |
|--------|---------|----------|
| optimization_input.schema.json | 1.0.0 | 新增 |
| optimization_result_schema.json | 1.0.0 | 新增 |

冻结不变：model.schema.json / optimization.schema.json（Phase 3）/ compute_envelope.schema.json / cost_result_schema.json / doe_input.schema.json / doe_result_schema.json / statistics_input.schema.json / statistics_result_schema.json。

---

## 11. 风电齿轮油验收场景映射

ISO VG 320 风电齿轮油，降本 10-20%。

DOE (4.2) → Experiment Data → Statistical Model (4.3)：VI、油膜强度、酸值各建模型 → Optimization (4.4)：
- candidate_space: PAO/Ester/Additive 三组分 bounds
- hard_constraints: total_cost <= baseline_cost * 0.85
- guardrails: VI >= baseline-2%, 油膜强度 >= baseline-5%, 酸值 <= baseline+0%
- ranking: PARETO 或 WEIGHTED_OBJECTIVE
→ Recommended Candidates（<=10 个）→ Gate Review（人工判断 + evidence 审计）

本引擎输出的是 Gate Review 输入材料，不是最终决策。



