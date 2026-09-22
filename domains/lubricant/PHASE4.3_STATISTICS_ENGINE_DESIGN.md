# Phase 4.3 Statistics Engine 设计

状态：待用户 Review。Review 通过前不写任何实现代码。

---

## 1. 定位与上游关系

Statistics Engine 是 Phase 3 `statistical-analysis` Skill（MODEL_BUILT，engine_handoff=PHASE4_DETERMINISTIC_ENGINE）的确定性承接方：把已批准的分析请求 + 观测数据变成可审计的统计模型。

职责边界：

- 引擎只做 OLS 拟合、ANOVA、残差诊断、lack-of-fit——不产生研发结论、不推进状态机。
- MODEL_BUILT 语义由 Phase 3 artifact 承载；本引擎输出独立的 statistics_result artifact。
- LLM/Skill 只负责选择方法与解释结果；所有数值计算在本引擎内确定性完成。

## 2. Input 契约

新增 `domains/lubricant/schemas/statistics_input.schema.json`（1.0.0）：

```yaml
statistics_input:
  input_type: const "STATISTICAL_ANALYSIS"
  components:                    # ≥3，≤12（同 DOE 输入约定）
    - component_id: string
  model_order: enum [LINEAR, QUADRATIC]   # 决定设计矩阵结构
  design_points:                 # ≥1，来自 doe_result 或等价声明
    - run_reference: string      # 对应 experiment runs[].run_id
      proportions: {component_id: fraction}   # Σ=1.0
  observations:                  # ≥1，来自 experiment artifact
    - run_reference: string      # 必须能在 design_points 中找到
      ctq_reference: string
      value: number
  requested_analyses:            # ≥1，子集枚举
    - enum [ANOVA, REGRESSION, RESIDUAL, LACK_OF_FIT]
```

前置校验（REJECTED 路径）：

- component_id 重复 → 拒绝；
- design_points.proportions Σ≠1.0（容差 1e-9）→ 拒绝；
- observations.run_reference 不存在于 design_points → 拒绝；
- 同一 run_reference+ctq_reference 重复观测 → 拒绝；
- n_observations < p_model（参数数不足）→ REJECTED（model not estimable: insufficient observations）。

## 3. 算法（Deterministic First）

### 3.1 设计矩阵构造

Scheffé 多项式，非中心化参数化（parameters.parameterization = SCHEFFE_UNCENTERED_V1 显式记录）：

- LINEAR：列序 = q 个纯组分项 x_i（component 字典序）
- QUADRATIC：列序 = q 个线性项 + C(q,2) 个交互项 x_i·x_j（按 i<j 字典序）

项序在 parameters.term_order 数组中逐项记录，保证 ANOVA Type I 顺序平方和可复现。

### 3.2 OLS 求解

正规方程 (X'X)b = X'y；高斯消元求逆（n×p 小规模，stdlib 手写 ~30 行 LU）；

rank 缺失检测：(X'X) 行列式绝对值 < 1e-12 × max(diag) → REJECTED（singular information matrix），不做伪逆。

输出系数 b、标准误 SE(b_i)=sqrt(σ²·[(X'X)^{-1}]_{ii})、t 值 t_i=b_i/SE(b_i)、p 值=2·(1−F(|t_i|; df_error, df_error))（t 分布通过 F(1,m) 等价计算）。

### 3.3 ANOVA Type I（顺序平方和）

按 term_order 依次计算：SS_i = RSS(reduced to first i terms) − RSS(first i−1 terms)。总平方和 SST = Σ(y−ȳ)²。误差 SS = SSE = RSS(full model)，df_error = n − p。

每项 F = (SS_i/1)/MSE，p 值 = 1 − F_cdf(F; 1, df_error)。

### 3.4 F 分布 CDF（正则化不完全 Beta）

I_x(a,b) 用 Lentz 改进 continued fraction（Numerical Recipes §6.4，Lentz 1976）：

```
F_cdf(f; d1, d2) = I_{d1·f/(d1·f+d2)}(d1/2, d2/2)
```

边界条件：
- df ≤ 0 或 f < 0 → 参数校验层拒绝；
- x=0 → 返回 0；x=1 → 返回 1；
- f=0 → F_cdf=0；f→∞ → F_cdf→1（渐近分支 f > 1e12 直接返回 1.0 减去小修正）；
- continued fraction 收敛阈值 3e-16，最大迭代 500 次。

### 3.5 Residual Analysis

残差 e_i = y_i − ŷ_i；标准化残差 r_i = e_i / sqrt(MSE)；仅报告偏度/峰度（不做正式正态性检验）。

### 3.6 Lack-of-Fit

有重复 design point（同一 proportions 向量出现 ≥2 次）时：
- SS_LOF = SSE − SS_PE（pure error from replicates）
- df_LOF = m_distinct − p；df_PE = n − m_distinct
- F_LOF = (SS_LOF/df_LOF)/(SS_PE/df_PE)
无重复点时 lack_of_fit.status = NOT_APPLICABLE。

## 4. Output 契约

新增 `domains/lubricant/schemas/statistics_result_schema.json`（1.0.0，allOf compute_envelope）：

```yaml
engine_name: const "statistics"
engine_version: "0.1.0"
method: OLS_ANOVA_V1
result:
  response_ctq: string           # 本结果的响应变量
  coefficients:
    - term: string               # 如 "x_PAO6" 或 "x_PAO6*x_Ester"
      estimate: number
      std_error: number
      t_value: number
      p_value: number [0,1]
  anova_table:
    - source: string             # term 名或 "RESIDUAL"
      type: enum [TERM, RESIDUAL]
      sum_squares: number ≥0
      df: integer ≥0
      mean_square: number ≥0     # df>0 时
      f_value: number ≥0         # TERM 行
      p_value: number [0,1]      # TERM 行
  fit_statistics:
    r_squared: number [0,1]
    adj_r_squared: number
    sigma_squared: number ≥0
  residual_analysis:
    residuals: [{run_reference, residual}]
    standardized_residuals: [{run_reference, std_residual}]
    skewness: number
    kurtosis: number
  lack_of_fit:
    status: enum [COMPUTED, NOT_APPLICABLE]
    sum_squares_lof / df_lof / sum_squares_pe / df_pe / f_value / p_value  # COMPUTE 时全必填
```

多 CTQ 处理：每次调用只分析一个 ctq_reference（从 observations 中筛选）；如果请求包含多个 CTQ，调用方需多次调用引擎。result.response_ctq 记录分析的 CTQ。

## 5. Validation Strategy（数值验证四件套优先）

```
tests/statistics/numerical_validation/
├── test_known_anova.py        # 教科书级已知案例，SS/MS/F/p 逐值断言
├── test_known_pvalues.py      # 已知 F 分位数锚点（多组 df 组合）
├── test_extreme_df.py         # 极端自由度稳定性
└── test_boundary_prob.py      # p 值边界行为
```

锚点来源（写入各测试文件头部注释）：scipy.stats.f.cdf 离线高精度值（15 位有效数字固化入库）、NIST/Scheffé 教科书 ANOVA 案例。锚点不依赖运行时联网核对。

功能测试（tests/compute/test_statistics_engine.py 直跑 main() 断言）：

- q=3 无约束 QUADRATIC 6 点 + 合成 y → 回归系数手算锚点比对
- 完美拟合（y = 精确线性函数）→ R²=1.0，residual 全零
- 秩缺失（重复 design points 导致 X'X 奇异）→ REJECTED
- 观测数 < 参数数 → REJECTED
- proportions Σ≠1 → REJECTED
- observations 引用不存在 run → REJECTED
- 重复观测 → REJECTED
- lack-of-fit 有/无重复点两种路径
- 同输入双跑字节相等（含 CLI 路径）
- 金 fixture 复现哈希锁死

## 6. 与 Agent / Skill 连接（闭环位置）

```text
statistical-analysis Skill（MODEL_BUILT 请求记录，已有）
                              │ engine_handoff=PHASE4_DETERMINISTIC_ENGINE
                              ▼
compute/statistics/engine.py   CLI: python -m domains.lubricant.compute.statistics.engine <input.json> <output.json>
                              │ input schema 校验 → 数据配对 → 设计矩阵 → OLS → ANOVA → envelope
                              ▼
statistics_result artifact（scripts/validate_compute_result.py 校验）
                              │
                              ▼
optimization engine（Phase 4.4 接力）
```

Skill 文件零改动。CLI 失败路径同样走 envelope REJECTED 落盘。

## 7. 明确不做（本期）

- Bayesian / hierarchical models
- Robust regression / weighted least squares
- 正式正态性检验（Shapiro-Wilk 等）——只报告偏度/峰度
- 多响应同时建模（MANOVA / PLS）
- 变量选择（stepwise / lasso）——模型形式由 model_order 完全决定

## 8. 实施清单（Review 通过后执行）

1. statistics_input.schema.json 新增
2. statistics_result_schema.json 新增
3. compute/statistics/engine.py（LU 求逆 + OLS + ANOVA + Lentz betacf + F cdf）
4. tests/statistics/numerical_validation/ 四件套（锚点值先离线计算后入库）
5. tests/compute/test_statistics_engine.py 功能测试
6. fixtures/compute/statistics-gold-input.json / statistics-gold-output.json + 哈希
7. 回归：Phase 3 / 4.0 / 4.1 / 4.2 全量仍绿

