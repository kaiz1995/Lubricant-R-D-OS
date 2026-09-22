# Phase 4.5 Validation Framework 设计

状态：待用户 Review。Review 通过前不写任何实现代码。

---

## 0. 定位

Validation Framework 是质量基础设施，不是第五个业务计算引擎。

它负责回答：这个计算 Artifact 是否有资格被下游研发决策使用？

Compute Artifact → Contract Validation → Provenance Validation → Numerical/Semantic Validation → Cross-stage Consistency → VALID/VALID_WITH_WARNINGS/REJECTED → 下游 Stage

核心原则：Validation != Recalculation。

不负责：重新计算 Cost、重新生成 DOE、重新拟合 Statistics、重新执行 Optimization、给出业务推荐、自动推进 Gate。

禁止为了验证结果正确而重新执行 cost formula / regression fitting / D-optimal / optimization grid。允许简单 invariant verification（如 sum(proportions)==1）。重新跑整个 Engine 与金结果比对属于 regression test，不是运行时 Validation。

---

## 1. 四层验证架构

### Layer 1 — Contract Validation

验证 artifact 在结构上是否合法：
- schema version 存在且合法
- engine_name/engine_version 存在
- required fields 齐全
- status 合法（OK/REJECTED）
- OK 状态 rejection_reasons 为空；REJECTED 状态非空
- input_digest 格式为 SHA256 hex
- result 结构符合对应 result schema
- evidence 结构合法

实现方式：用 jsonschema 对 compute_envelope + 对应 engine-specific result schema 做 validation。

### Layer 2 — Provenance Validation

回答：这个结果从哪里来的？

- input_digest 存在
- upstream artifact reference 完整（如 Optimization 引用的 statistics model digest 可追溯）
- engine_name/version/method 明确
- source model/cost/DOE reference 可追溯
- artifact dependency 形成闭环（无悬空引用）

### Layer 3 — Numerical/Semantic Validation

只做廉价 invariant checks，不复制算法。

Cost invariants：
- total_cost > 0（零成本走 REJECTED）
- contribution percentage sum ~= 100%（容差 1e-9）
- sensitivity ranking 与 components 内部一致（排序降序）

DOE invariants：
- proportions sum == mixture_total（容差 1e-9）
- bounds satisfied（每个组分在 [lower, upper] 内）—— Required Evidence Source: doe_result 自身或 source design-space parameters；证据缺失时 FATAL 不猜测
- run_count 与 runs 数组长度一致
- component 集一致（input components 与 design points 中的 component keys 一致）

Statistics invariants：
- coefficients 与 term_order 对齐（数量一致，顺序一致）
- model domain 声明存在
- ANOVA/regression 元数据完整
- status == OK 才允许下游消费
- fit_statistics.r_squared 范围以 Phase 4.3 statistics_result_schema.json 已冻结定义为准（当前 schema 定义 minimum=0 maximum=1），Validation 不自行发明新规则

Optimization invariants：
- recommended candidate 必须来自 feasible candidates（guardrail_status 不为 FAIL）
- non-inferiority 不为 FAIL
- rank 连续编号从 1 开始
- Pareto 信息内部一致（in_pareto_front=true 的候选 rank <= pareto_front_size）
- candidate proportions 在 model domain 声明内

### Layer 4 — Cross-stage Consistency

Phase 4.5 最重要能力。验证 DOE → Experiment → Statistics → Optimization 之间是否引用同一套：

- component_ids 一致（DOE 的 components 必须与 Statistics/Optimization 引用一致）
- CTQ/response 一致
- DOE artifact digest 被 Statistics 正确引用
- Statistics model digest 被 Optimization 正确引用
- cost basis 一致（Optimization 引用的 materials 表 digest 与 Cost artifact 一致）
- design-space/domain 一致
- engine versions 已记录

例：DOE 使用 PAO/GTL/AN/Ester 四组分，Statistics 只出现 PAO/GTL/Ester 缺少 AN → REJECTED，不能继续 Optimization。

---

## 2. Validation Result Schema

新增 domains/lubricant/schemas/validation_result_schema.json（v1.0.0），基于 compute_envelope allOf。

result 结构：

```yaml
validation_result:
  overall_status: enum [VALID, VALID_WITH_WARNINGS, REJECTED]
  artifact_type: string           # 被验证的 Primary Artifact 类型
  artifact_digest: string          # Primary Artifact canonical SHA256
  checks:
    - check_id: string
      layer: enum [CONTRACT, PROVENANCE, NUMERICAL, CROSS_STAGE]
      status: enum [PASS, WARNING, ERROR]
      severity: enum [INFO, WARNING, ERROR, FATAL]
      message: string
      evidence_reference: string
  errors: [string]
  warnings: [string]
  upstream_consistency:
    doe_to_statistics: enum [CONSISTENT, MISMATCH, NOT_CHECKED]
    statistics_to_optimization: enum [CONSISTENT, MISMATCH, NOT_CHECKED]
    cost_basis: enum [CONSISTENT, MISMATCH, NOT_CHECKED]
    design_space_domain: enum [CONSISTENT, MISMATCH, NOT_CHECKED]
  eligible_for_downstream: boolean
```

compute_envelope 保持冻结。

overall_status 由 checks 最高 severity 确定性推导：INFO → VALID；WARNING → VALID_WITH_WARNINGS；ERROR/FATAL → REJECTED。不由 validator 自行填写。

status/severity 合法组合约束：PASS → INFO；WARNING → WARNING；ERROR → ERROR | FATAL。禁止 PASS+FATAL 等非法组合，validator 必须拒绝。

ERROR/FATAL → eligible_for_downstream=false。WARNING → 当前 policy 默认 true 但必须进 evidence。

---

## 3. Severity Policy

| 最高 Severity | overall_status | eligible_for_downstream | 说明 |
|---|---|---|---|
| INFO | VALID | true | 纯信息 |
| WARNING | VALID_WITH_WARNINGS | true（默认放行但必须进 evidence） | 如 DOMAIN_SCREENED_APPROX |
| ERROR | REJECTED | false | invariant 失败 |
| FATAL | REJECTED | false | provenance/cross-stage 断裂或 required dependency 缺失 |

VALID_WITH_WARNINGS 是否 HOLD 由 warning severity/policy 决定，不由 Agent 自行判断。

---

## 4. Validation Registry 架构

不做巨大 if/else。按领域拆分注册：

```
compute/validation/
  __init__.py
  registry.py        # 注册表：(engine_name) -> {validator_fn, supported_versions, required_upstream}
  common.py          # 公共 Layer 1/2 validator（schema/envelope/digest/provenance）
  cost.py            # Cost invariants
  doe.py             # DOE invariants
  statistics.py      # Statistics invariants
  optimization.py    # Optimization invariants
  chain.py           # Cross-stage consistency (Layer 4)
  engine.py          # CLI 入口 main()
```

Registry metadata 结构（冻结）：
```python
REGISTRY = {
  "cost": {"validator": validate_cost, "supported_versions": ["0.1.0"], "required_upstream": []},
  "doe": {"validator": validate_doe, "supported_versions": ["0.1.0"], "required_upstream": []},
  "statistics": {"validator": validate_statistics, "supported_versions": ["0.1.0"], "required_upstream": ["doe_result"]},
  "optimization": {"validator": validate_optimization, "supported_versions": ["0.1.0"], "required_upstream": ["statistics_result", "cost_result"]},
}
```

Registry 必须校验：engine_name 在注册表内；engine_version 在 supported_versions 内；artifact_type 与 engine_name 对应关系正确。

未来 Reliability/Material/Compatibility Engine 可以注册新条目，不需要修改现有文件。

---

## 4a. Required Dependency Policy（冻结）

每种 artifact_type 有明确的必要上游依赖：
- cost_result → 无 Phase 4 compute 上游依赖（可独立验证）
- doe_result → 可独立做 local validation
- statistics_result → 必须能追溯 DOE/experiment 来源（required for downstream eligibility）
- optimization_result → 必须能追溯 statistics model + cost basis/cost artifact（required）

chain_context 中缺失 required dependency 时：不是 NOT_CHECKED，而是 FATAL，eligible_for_downstream=false。
NOT_CHECKED 只允许用于非必要检查。

---

## 5. Artifact Digest Contract（ARTIFACT_DIGEST_V1）

三个 digest 概念语义区分：
- input_digest：engine 的输入原始 bytes SHA256，由 compute_envelope 冻结定义，Validation 复用不重定义。
- artifact_digest：整个 envelope JSON 的 canonical SHA256，由 Phase 4.5 定义。
- upstream digest/reference：artifact 中引用的上游 artifact digest。

ARTIFACT_DIGEST_V1 算法：UTF-8 encoding、sorted keys、无多余空白 separators=(",", ":")、SHA256。

Provenance Validation 必须执行：canonical_digest(chain_context[i].data) == chain_context[i].declared_digest，否则 FATAL。
禁止仅检查 SHA256 字符串格式。

---

## 6. Deterministic First

相同 Artifact 集 → 逐字节相同 Validation Result。

- check 顺序固定（按 layer 再按 check_id 字典序）
- error/warning 排序固定
- 不依赖文件系统遍历顺序
- 不调用 LLM
- 无随机数
- 双跑 SHA256 相等测试

---

## 7. Input 契约

新增 domains/lubricant/schemas/validation_input.schema.json（v1.0.0）：

一次 Validation Request 只验证一个 Primary Artifact（不做 batch validation）：

```yaml
validation_input:
  input_type: const "VALIDATION_REQUEST"
  artifact:                         # 单个 Primary Artifact
    artifact_type: enum [cost_result, doe_result, statistics_result, optimization_result]
    data: object                    # 完整 envelope JSON
  chain_context:                    # 上游 artifact 用于 provenance / cross-stage 验证
    - artifact_type: string
      digest: string                # declared canonical SHA256
      data: object                  # 完整 envelope JSON
```

---

## 8. 测试方案

tests/compute/test_validation_engine.py 至少覆盖：

1. 合法 Cost artifact → VALID
2. Cost contribution sum 异常 → REJECTED
3. 合法 DOE artifact → VALID
4. DOE proportion/bounds 破坏 → REJECTED
5. 合法 Statistics artifact（含 doe context）→ VALID
6. Statistics term/component mismatch → REJECTED
7. DOMAIN_SCREENED_APPROX → VALID_WITH_WARNINGS
8. 合法 Optimization artifact（含 statistics+cost context）→ VALID
9. Optimization 推荐 guardrail FAIL candidate → REJECTED
10. Statistics 缺失 DOE context → FATAL / REJECTED
11. Optimization 缺失 statistics 或 cost context → FATAL / REJECTED
12. DOE→Statistics component mismatch → REJECTED (cross-stage)
13. Statistics model digest 与 Optimization 引用不一致 → REJECTED
14. chain_context declared digest 与实际 canonical digest 不匹配 → FATAL
15. Unknown engine/version → REJECTED
16. artifact_type/engine_name mismatch → REJECTED
17. Deterministic double-run byte identical
18. Gold fixture hash freeze

金 fixture：
- fixtures/compute/validation-gold-input.json
- fixtures/compute/validation-gold-output.json

回归：Phase 3 e2e + Phase 4.0-4.4 全部已有测试。

---

## 9. Schema Versioning

| Schema | Version | 变更类型 |
|--------|---------|----------|
| validation_input.schema.json | 1.0.0 | 新增 |
| validation_result_schema.json | 1.0.0 | 新增 |

冻结不变：全部 Phase 3 schema + Phase 4.0-4.4 所有已冻结 schema/engine/fixture。

---
