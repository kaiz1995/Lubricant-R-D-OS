/**
 * 润滑油研发领域包权威契约映射 —— 唯一真源：lubricant-rd-domain-pack。
 *
 * 派生自：
 *   - skills/lubricant-rd-agent/scripts/route_step.py 的 ROUTE_TABLE / TYPE_ROUTES
 *   - schemas/<artifact_type>.schema.json 的 artifact_type const
 *   - fixtures/valid/*.json 的文件名
 *
 * 修改本文件前请先改领域包；lubricantContracts.test.ts 会守护二者一致性。
 */

export type ProjectType =
  | "NEW_PRODUCT"
  | "IMPROVEMENT"
  | "COST_DOWN"
  | "CUSTOMIZATION"
  | "EXPLORATION";

/** state-machine.json 中 11 步链所覆盖的 stage 子集。 */
export type ChainStage =
  | "PROJECT_DEFINED"
  | "DUTY_DEFINED"
  | "CHALLENGES_DEFINED"
  | "FAILURE_CTQ_DEFINED"
  | "TEST_METHODS_QUALIFIED"
  | "DESIGN_SPACE_DEFINED"
  | "EXPERIMENT_DESIGNED"
  | "EXPERIMENT_RUNNING"
  | "MODEL_BUILT"
  | "OPTIMIZED"
  | "VERIFIED";

/** 契约绑定部分：与领域包一一对应，不得随意改动。 */
export interface StageContract {
  /** 11 步链中的固定序号，1-based。 */
  readonly chainIndex: number;
  /** 领域包技能目录名，用于提示词路由。 */
  readonly skill: string;
  readonly stage: ChainStage;
  /** schemas/<artifactType>.schema.json 的 artifact_type const。 */
  readonly artifactType: string;
  /** 工作区内的规范文件名（根目录，或任意子目录 —— 由 basename 定位）。 */
  readonly file: string;
  /** 以下为展示文案，非契约。 */
  readonly titleZh: string;
  readonly description: string;
  readonly criteria: readonly string[];
}

export const STAGE_CHAIN: readonly StageContract[] = [
  {
    chainIndex: 1,
    skill: "project-definition",
    stage: "PROJECT_DEFINED",
    artifactType: "project",
    file: "project.json",
    titleZh: "立项与项目定义",
    description: "确定项目代号、应用场景目标、成本上限约束与团队权责。",
    criteria: [
      "明确应用机型与工况环境",
      "锁定 target_cost（含单位）",
      "完成立项评审批准",
    ],
  },
  {
    chainIndex: 2,
    skill: "duty-definition",
    stage: "DUTY_DEFINED",
    artifactType: "duty",
    file: "duty.json",
    titleZh: "严苛工况与指标定义",
    description: "将机械运转环境转化为润滑油理化与台架指标规格清单。",
    criteria: [
      "七类 duty_item 齐备（equipment/operating_conditions/maintenance/temperature/load/contamination/life）",
      "每项含 value / source / evidence_id / statement / status",
      "标注 OBSERVED 与 ASSUMED 的区别",
    ],
  },
  {
    chainIndex: 3,
    skill: "duty-challenge-analysis",
    stage: "CHALLENGES_DEFINED",
    artifactType: "challenge",
    file: "challenge.json",
    titleZh: "核心技术挑战梳理",
    description: "识别配方矛盾与极端工况下的技术难点与机理风险。",
    criteria: [
      "每项挑战含 severity / exposure / lubricant_sensitivity",
      "显式记录 evidence_gap",
      "按 priority 排序",
    ],
  },
  {
    chainIndex: 4,
    skill: "failure-ctq-analysis",
    stage: "FAILURE_CTQ_DEFINED",
    artifactType: "failure_ctq",
    file: "failure_ctq.json",
    titleZh: "失效模式与 CTQ",
    description: "明确齿轮点蚀、擦伤、起泡、沉积物等失效模式及 CTQ 阈值。",
    criteria: [
      "失效模式与机理一一对应",
      "CTQ 含阈值与单位",
      "test_chain 指向已确认的测试方法",
    ],
  },
  {
    chainIndex: 5,
    skill: "test-method-qualification",
    stage: "TEST_METHODS_QUALIFIED",
    artifactType: "test_method",
    file: "test_method.json",
    titleZh: "测试与表征方法确认",
    description: "锁定实验室与第三方台架评估的标准化测试规范。",
    criteria: [
      "standard 明确（如 DIN 51517-3 / FVA 54）",
      "qualification_status 为 QUALIFIED",
      "qualification_basis 有证据引用",
    ],
  },
  {
    chainIndex: 6,
    skill: "formulation-design",
    stage: "DESIGN_SPACE_DEFINED",
    artifactType: "design_space",
    file: "design_space.json",
    titleZh: "配方原材料与设计空间",
    description: "确定基础油与添加剂候选池及比例上下限。",
    criteria: [
      "variables 给出上下限与归一化约束",
      "ctq_references 指向前序 CTQ",
      "constraints 覆盖成本红线",
    ],
  },
  {
    chainIndex: 7,
    skill: "doe-design",
    stage: "EXPERIMENT_DESIGNED",
    artifactType: "experiment_design",
    file: "experiment_design.json",
    titleZh: "混料 DOE 实验设计",
    description: "运行混料设计算法，生成实验矩阵与 run_plan。",
    criteria: [
      "design 明确点生成策略（point_generation）",
      "混料归一化约束（mixture_total）",
      "responses 与 guardrails 齐备",
    ],
  },
  {
    chainIndex: 8,
    skill: "experiment-import",
    stage: "EXPERIMENT_RUNNING",
    artifactType: "experiment",
    file: "experiment.json",
    titleZh: "调配与台架实测数据",
    description: "试制调配实样，录入实测理化与台架数据。",
    criteria: [
      "runs 含实测数值与单位",
      "evidence_scope 为 PHYSICAL",
      "严禁捏造数据",
    ],
  },
  {
    chainIndex: 9,
    skill: "statistical-analysis",
    stage: "MODEL_BUILT",
    artifactType: "model",
    file: "model.json",
    titleZh: "响应面建模与统计分析",
    description: "建立基础油与添加剂对黏度指数、抗磨、成本的回归方程。",
    criteria: [
      "response_references 与 responses 对齐",
      "engine_handoff 记录计算引擎交接",
      "拟合优度与残差检验已记录",
    ],
  },
  {
    chainIndex: 10,
    skill: "optimization",
    stage: "OPTIMIZED",
    artifactType: "optimization",
    file: "optimization.json",
    titleZh: "多目标配方优化",
    description: "在性能最大化与成本约束下求解最佳配方。",
    criteria: [
      "objective_type 与 objectives 明确",
      "engine_handoff 记录求解器交接",
      "给出主选与候选配方",
    ],
  },
  {
    chainIndex: 11,
    skill: "gate-review",
    stage: "VERIFIED",
    artifactType: "gate",
    file: "gate.json",
    titleZh: "门禁终审（VERIFIED）",
    description: "综合全链条证据包完成 Gate 终审放行。",
    criteria: [
      "satisfied_conditions 与 unsatisfied_conditions 均已填写",
      "evidence_gaps 为空",
      "gate_status 取值合法（GO/HOLD/PIVOT/KILL/FREEZE）",
    ],
  },
];

const BY_STAGE: ReadonlyMap<string, StageContract> = new Map(
  STAGE_CHAIN.map((c) => [c.stage, c] as const),
);

/** 镜像 route_step.py 的 TYPE_ROUTES。 */
export const TYPE_ROUTES: Record<ProjectType, readonly ChainStage[]> = {
  NEW_PRODUCT: [
    "PROJECT_DEFINED", "DUTY_DEFINED", "CHALLENGES_DEFINED", "FAILURE_CTQ_DEFINED",
    "TEST_METHODS_QUALIFIED", "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED",
    "EXPERIMENT_RUNNING", "MODEL_BUILT", "OPTIMIZED", "VERIFIED",
  ],
  IMPROVEMENT: [
    "PROJECT_DEFINED", "FAILURE_CTQ_DEFINED", "TEST_METHODS_QUALIFIED",
    "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING",
    "MODEL_BUILT", "OPTIMIZED", "VERIFIED",
  ],
  COST_DOWN: [
    "PROJECT_DEFINED", "FAILURE_CTQ_DEFINED", "DESIGN_SPACE_DEFINED",
    "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING", "OPTIMIZED", "VERIFIED",
  ],
  CUSTOMIZATION: [
    "PROJECT_DEFINED", "FAILURE_CTQ_DEFINED", "TEST_METHODS_QUALIFIED",
    "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING", "VERIFIED",
  ],
  EXPLORATION: [
    "PROJECT_DEFINED", "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED",
    "EXPERIMENT_RUNNING", "MODEL_BUILT", "VERIFIED",
  ],
};

export const PROJECT_TYPES = Object.keys(TYPE_ROUTES) as ProjectType[];

export function isProjectType(value: unknown): value is ProjectType {
  return typeof value === "string" && value in TYPE_ROUTES;
}

/** 某 project_type 下的有序步骤列表；未知类型回退 NEW_PRODUCT。 */
export function routeFor(projectType: string | null | undefined): StageContract[] {
  const key: ProjectType = isProjectType(projectType) ? projectType : "NEW_PRODUCT";
  const out: StageContract[] = [];
  for (const stage of TYPE_ROUTES[key]) {
    const contract = BY_STAGE.get(stage);
    if (contract) out.push(contract);
  }
  return out;
}

/* ------------------------------------------------------------------ *
 * 轻量结构校验（lite）
 * 完整校验由领域包 Python 侧负责：
 *   python lubricant-rd-domain-pack/scripts/validate_schemas.py
 * UI 只做「必填键存在 + artifact_type 匹配 + schema_version 匹配」，
 * 避免把 jsonschema 及其 $ref 解析器打进前端包。
 * ------------------------------------------------------------------ */

const SCHEMA_VERSION = "0.1.0";

/** common.schema.json#/$defs/artifact 的 required（所有工件共享）。 */
const COMMON_REQUIRED: readonly string[] = [
  "schema_version", "project_id", "stage", "decision_question", "hypothesis",
  "uncertainty", "evidence", "decision_rule", "result", "decision", "next_action",
];

/** 各 schema 自身的 required（不含 common 部分）。 */
const OWN_REQUIRED: Record<string, readonly string[]> = {
  project: ["artifact_type", "status", "project_name", "project_type", "product_family",
    "business_objective", "technical_objective", "hard_constraints", "target_cost",
    "benchmark_products", "success_criteria", "risk_class", "owner"],
  duty: ["artifact_type", "duty_id", "project_reference", "duty"],
  challenge: ["artifact_type", "duty_reference", "challenge_id", "category", "description",
    "severity", "exposure", "lubricant_sensitivity", "evidence_gap", "priority"],
  failure_ctq: ["artifact_type", "challenge_reference", "failure_id", "failure_mode",
    "mechanism", "failure_diagnosis", "root_cause_hypotheses", "lubricant_contribution",
    "ctqs", "test_chain"],
  test_method: ["artifact_type", "evidence_scope", "method_id", "name", "standard",
    "target_failure_reference", "role", "qualification_metrics", "qualification_basis",
    "qualification_status"],
  design_space: ["artifact_type", "design_space_id", "scope", "variables", "ctq_references",
    "qualified_test_method_references", "constraints"],
  experiment_design: ["artifact_type", "stage", "evidence_scope", "experiment_design_id",
    "design_space_reference", "test_method_references", "factor_references", "design",
    "run_plan", "responses", "guardrails", "expected_information_value"],
  experiment: ["artifact_type", "evidence_scope", "experiment_id",
    "experiment_design_reference", "design_space_reference", "test_method_references", "runs"],
  model: ["artifact_type", "stage", "evidence_scope", "model_id", "experiment_reference",
    "design_space_reference", "test_method_references", "requested_analyses",
    "response_references", "engine_handoff"],
  optimization: ["artifact_type", "stage", "evidence_scope", "optimization_id",
    "model_reference", "objective_type", "objectives", "methods", "engine_handoff"],
  gate: ["artifact_type", "evidence_scope", "gate_id", "experiment_reference", "scope",
    "gate_status", "satisfied_conditions", "unsatisfied_conditions", "evidence_gaps", "risks"],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** 返回缺失/不匹配的键列表；空数组表示通过。 */
export function validateArtifactLite(artifactType: string, value: unknown): string[] {
  if (!isRecord(value)) return ["顶层不是 JSON 对象"];
  const errors: string[] = [];
  if (value.artifact_type !== artifactType) {
    errors.push(`artifact_type 期望 "${artifactType}"，实际 ${JSON.stringify(value.artifact_type)}`);
  }
  if (value.schema_version !== SCHEMA_VERSION) {
    errors.push(`schema_version 期望 "${SCHEMA_VERSION}"`);
  }
  const required = [...COMMON_REQUIRED, ...(OWN_REQUIRED[artifactType] ?? [])];
  for (const key of required) {
    if (!(key in value)) errors.push(`缺少必填字段 ${key}`);
  }
  return errors;
}

/** state-machine.json 的权威 gate_statuses 值域。 */
export const GATE_STATUSES = ["GO", "HOLD", "PIVOT", "KILL", "FREEZE"] as const;
export type GateStatus = (typeof GATE_STATUSES)[number];

export function isGateStatus(value: unknown): value is GateStatus {
  return typeof value === "string" && (GATE_STATUSES as readonly string[]).includes(value);
}
