# Phase 4 计算引擎设计（PHASE4_DESIGN）

状态：待用户确认。本文档为 Phase 4 开发的唯一设计依据；确认前不扩展任何计算模块实现。

---

## 1. 定位与总原则

Phase 4 不新增业务流程 Skill，只建立确定性计算层（Engineering Compute Layer），补齐 Phase 3 遗留的 engine_handoff 承接方：

- `statistical-analysis` 产出 model artifact（MODEL_BUILT，engine_handoff=PHASE4_DETERMINISTIC_ENGINE）→ Statistics Engine 接管计算。
- `optimization` 产出 optimization artifact（OPTIMIZED，engine_handoff=PHASE4_DETERMINISTIC_ENGINE）→ Optimization Engine 接管计算。
- `doe-design` 的 run_plan.point_generation=PHASE4_DETERMINISTIC_ENGINE → DOE Engine 接管实验点生成。

### Deterministic First（最高原则）

相同输入（Input Data + Method + Parameters）必须得到逐字节可复现的结果：

- 引擎内禁止随机性；DOE 点集、网格搜索遍历顺序全部确定性定义。
- 结果必须携带 engine 版本号与方法参数，保证追溯链完整：Decision Question → Input Data → Calculation Method → Result → Engineering Decision。
- LLM / Agent 只负责：选择方法、解释结果、生成研发建议；不参与数学计算。

### Extension over Modification

- 不修改 open-science/ 核心（当前 dev/lubricant-rd-v0 @ b38c3f2，保持 clean）。
- 不修改任何 Phase 3 schema 与 Skill 契约（schema valid=10 invalid=12 failures=0 的已验证状态必须保持稳定）。
- 所有 Phase 4 新增内容位于 `domains/lubricant/` 下。

---

## 2. Compute Layer 架构

```text
lubricant-rd-agent (Skill 编排, LLM 决策)
        │  engine_handoff = PHASE4_DETERMINISTIC_ENGINE
        ▼
domains/lubricant/compute/
├── cost/            # Phase 4.1 配方成本引擎
├── doe/             # Phase 4.2 Constrained Mixture DOE 引擎
├── statistics/      # Phase 4.3 统计引擎 (ANOVA/regression/residual/lack-of-fit)
├── optimization/    # Phase 4.4 最小确定性优化引擎 (Grid Search + Pareto + Weighted)
└── validation/      # 计算结果质量验证 (fixture 复现、数值锚点、不变量检查)
```

每个子目录统一结构：

```text
compute/<module>/
├── engine.py          # 纯函数入口：load(input) -> result dict，无副作用
└── __init__.py
```

调用方式：CLI 入口 `python -m domains.lubricant.compute.<module>.engine <input.json> <output.json>`，供 Skill 脚本与后续 MCP 包装复用。Python 标准库 only（json/math/statistics/argparse/pathlib/unittest），无第三方依赖。

---

## 3. Schema 设计（独立新增，不改旧契约）

Phase 3 schemas/ 保持不动（model.schema.json = Analysis Request Contract，optimization.schema.json = Handoff Contract）。Phase 4 新建独立结果契约目录，避免污染已验证契约集：

```text
domains/lubricant/schemas/
├── cost-result.schema.json         # 4.1
├── doe-result.schema.json          # 4.2 实验矩阵 + Experiment Card 字段
├── statistics-result.schema.json   # 4.3 ANOVA/regression 拟合结果
├── optimization-result.schema.json # 4.4 可行解排序/Pareto/加权最优
├── validation-result.schema.json   # validation 模块输出
└── compute-envelope.schema.json    # 公共信封：engine_version/method/input_digest/result
```

公共信封字段（所有 result schema 通过 $ref 复用）：

```yaml
compute_envelope:
  schema_version: "0.1.0"
  engine_version: "0.1.0"          # 每模块独立递增
  method: <string>                 # 如 GRID_SEARCH_PARETO / OLS_ANOVA_TYPE_I
  parameters: <object>             # 方法参数全集，缺省值显式展开写入
  input_digest: <sha256 of canonical input json>
  status: OK | REJECTED            # 输入不满足前提时 REJECTED + reasons，不产数
```

说明：Phase 3 的 model/optimization schema 是"请求"，本层 schema 是"结果"，二者通过 project_id / experiment_reference / model_reference 关联，不互相嵌套。

---

## 4. 各模块设计

### 4.1 Cost Engine（优先）

输入（JSON）：配方组成（component_id + 质量分数，总和必须=100%±0.01）、原材料单价表（component_id + 单价 + 单位 + 价格来源/日期）。

计算：各组分成本贡献 = 份额×单价；总成本；成本占比排序；敏感性 = 单价±10% 时总成本变化（线性，直接解析）。

输出：total_cost、cost_drivers（降序）、highest_cost_component、cost_percentage、sensitivity、optimization_direction（文本建议由 Agent 层生成，引擎只输出数值事实）。

验收：风电齿轮油案例中 PAO6/AN/Ester/Additive 类配方的固定输入产生固定输出，单测锁定数值。

### 4.2 Constrained Mixture DOE Engine（核心）

输入：components（≥3，含名称与边界约束 min/max %）、constraints（线性等式 total=100%、不等式）、design_type（D_OPTIMAL_MIXTURE 或 SIMPLEX_MIXTURE，第一阶段仅此两种）、responses 列表、Experiment Card 决策字段（decision_question/hypothesis/decision_rule 等）。

算法：

- Simplex Mixture Design：{q-1} 阶单纯形格点（Scheffé），边界裁剪后将不可行格点替换为最近可行投影点并去重，全部点显式记录。
- D-optimal Mixture Design：候选点集（单纯形格点 ∩ 约束可行域，含顶点/棱心/总中心）上做贪心行列式最大化（候选点规模 ≤ 数百时够用；这是已知精度上限，后续可换 Fedorov 交换算法——代码注释标注 ponytail ceiling）。
- 全程无随机数：D-optimal 的初始候选顺序按 component 元组字典序固定。

输出：runs（每 run 为 components 百分比向量，总和精确=100）、design_type、selection_reason、expected_information_value、以及 Experiment Card 必填字段（Decision Question / Hypothesis / Variables / Constraints / Responses / DOE Selection Reason / Expected Information Value / Decision Rule）——缺任一字段则 status=REJECTED，不产矩阵。

### 4.3 Statistics Engine

输入：experiment runs（run × response 测量矩阵，来自 experiment schema 数据）+ design matrix（来自 4.2 结果或等价声明）+ requested_analyses（ANOVA / linear / quadratic / interaction / residual / lack-of-fit）。

算法（纯标准库实现）：

- 设计矩阵构造：Scheffé 一阶（纯混合物）/ 二阶（+二元交互项 x_i·x_j）；中心化与非中心化两种参数化中固定选用一种并在 parameters 中显式记录，杜绝歧义。
- OLS 求解：正规方程 (X'X)b=X'y，高斯消元求逆（n×p 规模小，无需迭代法）；rank 缺失检测（X'X 奇异 → REJECTED，不做伪逆）。
- ANOVA Type I（顺序平方和，与 DOE 项录入顺序一致并在 parameters 中记录项序）。
- F 分布 p 值：自实现正则化不完全 Beta 函数 I_x(a,b)——continued fraction（Lentz 算法），公式与算法来源在模块 docstring 中注明（Numerical Recipes §6.4 / Lentz 1976），并附边界条件处理：df≤0、F<0 → REJECTED；F→0/∞ 的渐近分支；x=0/1 精确返回。

可靠性要求（用户明确要求，不得为免依赖牺牲正确性）：

```text
tests/statistics/numerical_validation/
├── test_known_anova.py        # 教科书级已知 ANOVA 案例，SS/MS/F/p 逐值断言
├── test_known_pvalues.py      # 已知 F 分布 p-value 锚点（多组 df 组合）
├── test_extreme_df.py         # 极端自由度 df=1、df 很大、非整数 df 的稳定性
└── test_boundary_prob.py      # p 值边界：0、1、单调性、对称恒等式
```

每个测试文件头部注明锚点数值来源（教科书/文献/独立高精度工具离线计算值），锚点本身入库固化，不依赖运行时联网核对。

输出：coefficients（含标准误、t 值、p 值）、significance、ANOVA 表、R²/adjusted R²、residual analysis（残差、标准化残差、正态性仅报告偏度峰度，不做正式检验）、lack-of-fit（有重复点时）、validation 摘要。结果对应状态机 MODEL_BUILT 语义，但作为独立 result artifact 存放。

### 4.4 Optimization Engine（最小确定性版）

定位：验证工程闭环，不追求高级算法。明确禁止：Bayesian Optimization、Reinforcement Learning、AI Agent 自主优化。

输入：statistics-result（模型系数）+ design space 约束 + objectives（direction: MINIMIZE/MAXIMIZE/TARGET + criterion）。

仅实现四种能力：

1. Grid Search：约束域内确定性网格（步长入参，默认 1%，浮点累加用整数份计数避免误差漂移），枚举全部候选配方。
2. Constraint Filtering：硬约束（粘度等级保持、相容性声明等以谓词形式传入）过滤。
3. Pareto Ranking：非支配排序，同层内按字典序稳定排序。
4. Weighted Objective：加权标量化，权重与归一化方式显式入参并写入 parameters。

输出：feasible_count、pareto_front、weighted_best（含各目标预测值与置信区间引用）、search_metadata（网格规格、剪枝统计）。

---

## 5. Skill 调用关系（闭环）

```text
formulation-design ──▶ doe-design ──▶ [DOE Engine] ──▶ doe-result (EXPERIMENT_DESIGNED 语义)
                                              │
                                              ▼
                                     experiment (人工执行, EXPERIMENT_RUNNING)
                                              │
                                              ▼
 statistical-analysis ──▶ [Statistics Engine] ──▶ statistics-result (MODEL_BUILT 语义)
                                              │
                                              ▼
       optimization ──▶ [Optimization Engine] ──▶ optimization-result (OPTIMIZED 语义)
                                              │
                                              ▼
                                        gate-review (VERIFIED)
```

连接方式：Skill 脚本在 preflight 通过后调用对应 engine CLI，engine 输出落盘为 result artifact 并经 validate 校验后才能被下游 Skill 读作上游证据。Skill 文本本身不写任何数学逻辑（维持 Phase 3 决策边界）。

---

## 6. 测试方案

分层：

1. 单元：每个 engine 纯函数级断言（含非法输入 → REJECTED + reasons）。
2. 数值验证：§4.3 的 tests/statistics/numerical_validation/ 四件套；DOE 用小规模已知设计（如 q=3 simplex centroid 7 点）对照文献值；Cost 手算锚点。
3. 固定 fixture 复现：每模块 ≥1 个金 fixture，输出全文哈希锁死，CI 断言逐字节一致（Deterministic First 的机器判据）。
4. 链路：扩展 tests/lubricant_e2e/test_phase4_chain.py——doe-result → experiment → statistics-result → optimization-result 状态语义贯通，且不破坏现有 test_phase3_chain.py 与 test_stage_chain.py。
5. 回归：Phase 3 全部既有测试（schema valid=10 invalid=12 failures=0、state-machine、install-compat）必须在每次提交后仍全绿。

## 7. 风电齿轮油验收路径（ISO VG 320 降本 10–20%）

分两步走，第一步是 Phase 4 自身的完成标准，第二步是 Phase 5/6 的范围：

Step 1（Phase 4 完成判据，合成数据）：

1. Project Requirement：project fixture（COST_DOWN 类型，hard_constraints 含粘度等级 VG320 与兼容性要求）。
2. Design Space：现有 design_space fixture 模式，变量为 PAO/GTL/AN/Ester 边界。
3. Mixture DOE：DOE Engine 产出含 Experiment Card 的受约束混料设计（如 4 组分 D-optimal 16 runs）。
4. Experiment Data：合成响应数据 fixture（氧化/磨损/泡沫，带重复点以支持 lack-of-fit）。
5. Statistical Model：Statistics Engine 产出 Scheffé 二阶模型 + ANOVA + lack-of-fit。
6. Optimization：Optimization Engine 在成本最小化 + 性能非劣效约束下给出 Pareto 前沿与 weighted best。
7. Gate Review：现有 gate-review Skill 能读取上述链条完成 VERIFIED 判定（若 gate-review 需要读新 result artifact，仅扩其输入装配脚本，不改其契约文本）。

Step 2（真实数据试点）：替换 Step 1 第 4 步为真实实验数据，其余流程不变——属于 Phase 6，不在本设计范围内。

## 8. 明确暂缓（与 Gate 文档一致）

- Bayesian Optimization / QSPR / Hansen / Weibull / Arrhenius：Phase 6+。
- 自动配方预测：不做（执行方案 §88 同）。
- 工艺成本、Mixture×Process、RSM、Robust Design：接口预留（schema enum 占位），实现延后。

## 9. 实施顺序（确认后执行）

1. schemas + compute envelope（半天量级）→ schema 自校验测试绿。
2. Cost Engine + fixture 锁定（最小，先打通 CLI→result→validate 链路模式）。
3. DOE Engine（simplex 先行，D-optimal 贪心随后）。
4. Statistics Engine（先 OLS+ANOVA，再 numerical validation 四件套，最后 residual/LOF）。
5. Optimization Engine（Grid→Filter→Pareto→Weighted）。
6. test_phase4_chain.py 闭环 + Phase 3 回归全绿 → 交付风电齿轮油 Step 1 案例。
