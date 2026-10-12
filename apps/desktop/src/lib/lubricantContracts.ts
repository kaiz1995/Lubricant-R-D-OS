/**
 * 润滑材料研发领域包权威契约映射 —— 唯一真源：domains/lubricant（领域包）。
 *
 * 派生自：
 *   - contracts/state-machine.json 的 stages / type_routes / on_demand_stages
 *     （v0.8.0：28 段、7 类路由 + 1 个按需阶段；第 7 类 PRECISION_GREASE_DEV
 *     是精密传动脂开发路线，独占 12 个新 stage）
 *   - skills/lubricant-rd-agent/scripts/route_step.py 的 ROUTE_TABLE（skill → stage 顺序）
 *   - schemas/<artifact_type>.schema.json 的 artifact_type const 与 required
 *   - fixtures/valid/*.json 的文件名
 *
 * 修改本文件前请先改领域包；lubricantContracts.test.ts 会守护二者一致性。
 */

export type ProjectType =
  | "NEW_PRODUCT"
  | "IMPROVEMENT"
  | "COST_DOWN"
  | "CUSTOMIZATION"
  | "EXPLORATION"
  | "PROCESS_ROBUSTNESS"
  | "PRECISION_GREASE_DEV";

/** STAGE_CHAIN 覆盖的 stage 子集（含不在任何路由上的按需阶段）。 */
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
  | "PROCESS_WINDOW_DEFINED"
  | "VERIFIED"
  | "APPLIED"
  // v0.8.0 精密传动脂（PRECISION_GREASE_DEV）路线的 12 个新 stage。
  | "FAILURE_MECHANISM_DEFINED"
  | "REFERENCE_MATERIAL_RESOLVED"
  | "BENCH_RESOURCE_REGISTERED"
  | "CAMPAIGN_OPENED"
  | "BATCH_PRODUCED"
  | "SCREENING_PASSED"
  | "BENCH_TESTED"
  | "VARIANCE_ASSESSED"
  | "NEXT_BATCH_DECIDED"
  | "NON_INFERIORITY_PASSED"
  | "PROCESS_SCALE_VALIDATED"
  | "KNOWLEDGE_ARCHIVED";

/** 契约绑定部分：与领域包一一对应，不得随意改动。 */
export interface StageContract {
  /** STAGE_CHAIN 中的固定序号，1-based（含按需阶段）。 */
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
    description: "将机械运转环境转化为润滑材料理化与台架指标规格清单。",
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
    // 按需阶段：可被本技能产出，但不在任何 type_route 上（见 ON_DEMAND_STAGES）。
    // 它留在 STAGE_CHAIN 里，好让探测与契约表仍能解析产出的 process.json；
    // routeFor() 永远不会输出它。
    chainIndex: 11,
    skill: "process-scale-up",
    stage: "PROCESS_WINDOW_DEFINED",
    artifactType: "process",
    file: "process.json",
    titleZh: "工艺窗口与放大（按需）",
    description: "按需能力：工艺生成产品结构的品类（润滑脂的皂化/转相/研磨）用它固化唯一工艺窗口。不在任何研发路线上 —— 调和油的工艺是二阶变量。",
    criteria: [
      "工艺窗口 evidence_reference 已挂（PROCESS-WINDOW:<window_id> 且 process_window.validated=true）",
      "amplification_factor 有来源，且严格大于上游工艺记录",
      "放大批次换釜复现一致，scale_class 沿 LAB→PILOT→PRODUCTION 前进",
      "证据非空、无 GAP，evidence_scope 与上游工艺记录一致",
    ],
  },
  {
    chainIndex: 12,
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
  {
    chainIndex: 13,
    skill: "application-validation",
    stage: "APPLIED",
    artifactType: "application",
    file: "application.json",
    titleZh: "应用与整机验证（APPLIED）",
    description: "在 VERIFIED 之上聚合应用记录，门禁项目进入应用与整机验证阶段。",
    criteria: [
      "INCONCLUSIVE 不得进入 APPLIED（FAIL / GAP 同样阻断）",
      "life_claim_boundary 非空且 status=OBSERVED，至少一条 validated_condition",
      "acceptance_criteria 全部 OBSERVED 且带确定阈值，counterexamples 为空",
      "bench_references 至少引用一个已登记台架",
    ],
  },
  /* ---- v0.8.0 精密传动脂路线（PRECISION_GREASE_DEV）独享的 12 个 stage ---- *
   * 前 7 条（14~20）是调和油路线跳过或折叠掉的工序，后 5 条（21~25）是
   * 内环迭代与知识封存的闭环工序。注意三条**共用工件**（跨路线复用，同一
   * 条 route 内不会重复出现）：failure_ctq.json（失效机制 + CTQ 两段共享）、
   * optimization.json（优化 + 非劣效共享）、process.json（工艺窗口按需阶段 +
   * 工艺放大共享）。routeFor() 按 stage 取契约，共用不影响进度推导。          */
  {
    chainIndex: 14,
    skill: "failure-ctq-analysis",
    stage: "FAILURE_MECHANISM_DEFINED",
    artifactType: "failure_ctq",
    file: "failure_ctq.json",
    titleZh: "失效机制与判据界定",
    description: "把失效模式落到机理与判据层：每个 CTQ 必须声明它属于筛测、台架还是整机判据。",
    criteria: [
      "每条失效模式与机理一一对应，并给出润滑剂贡献路径",
      "每个 CTQ 声明判据层级（筛测 / 台架 / 整机），禁止混层",
      "root_cause_hypotheses 与 failure_diagnosis 均有证据，缺证据者显式标 GAP",
      "test_chain 指向已确认的测试方法，未确认者标注待资格",
    ],
  },
  {
    chainIndex: 15,
    skill: "reference-material",
    stage: "REFERENCE_MATERIAL_RESOLVED",
    artifactType: "reference",
    file: "reference.json",
    titleZh: "参照物卷宗（已知好/坏样）",
    description: "登记已知好样与已知坏样实物及其历史证据，至少一方 RESOLVED 才可进入方法资格。",
    criteria: [
      "known_good / known_bad 至少一方有实物与可追溯来源",
      "tier 明确（DIRECT_HISTORY / LONG_RUN_NO_EVENT / UNRESOLVED）",
      "历史证据与参照物绑定，每条可回指 evidence_id",
      "downstream_flag 如实反映区分性证据是否齐备",
    ],
  },
  {
    chainIndex: 16,
    skill: "bench-registration",
    stage: "BENCH_RESOURCE_REGISTERED",
    artifactType: "bench",
    file: "bench.json",
    titleZh: "台架资源与档期登记",
    description: "登记可用台架位数、单轮占用天数与单轮成本，作为台架战役的资源包络。",
    criteria: [
      "可用位数由档期与单轮天数换算得出，不得手填",
      "单轮成本含数值、单位与来源",
      "availability_window 起止合法（start 早于 end），reserved_days 已扣除",
    ],
  },
  {
    chainIndex: 17,
    skill: "bench-registration",
    stage: "CAMPAIGN_OPENED",
    artifactType: "campaign",
    file: "campaign.json",
    titleZh: "台架战役开启（内环迭代）",
    description: "开启内环迭代的台架战役载体，含成对比较设计与迭代轮次上限。",
    criteria: [
      "pairing_design 成对比较设计齐备，缺失不得开战",
      "bench_references 指向已登记台架",
      "iterations 每轮记录 stop_state，且不得超过 max_iterations",
    ],
  },
  {
    chainIndex: 18,
    skill: "grease-batch",
    stage: "BATCH_PRODUCED",
    artifactType: "batch",
    file: "batch.json",
    titleZh: "制脂与制样（工艺全轨迹）",
    description: "记录皂化 / 脱水 / 转相 / 冷却 / 研磨全轨迹与原材料批次，工艺偏差显式登记。",
    criteria: [
      "trajectory 覆盖全部单元操作，工艺偏差显式记录、不得抹平",
      "raw_material_lots 与 formula_reference 可追溯，样品交接链完整",
      "batch_verdict 取值合法（VALID / DEVIATED / VOID），偏差未判定不得放行",
    ],
  },
  {
    chainIndex: 19,
    skill: "grease-screening",
    stage: "SCREENING_PASSED",
    artifactType: "screening",
    file: "screening.json",
    titleZh: "理化筛测（送台架门槛）",
    description: "先做理化筛测再送台架：筛测只当门槛，不当选优依据。",
    criteria: [
      "overall_verdict 为 PASS 才可 gate_to_bench=RELEASED",
      "FAIL / INCONCLUSIVE 一律不得送台架（gate_to_bench=BLOCKED）",
      "tests 与 measurement_replicates 齐备，每个结果可回指原始测量",
    ],
  },
  {
    chainIndex: 20,
    skill: "experiment-import",
    stage: "BENCH_TESTED",
    artifactType: "bench_test",
    file: "bench_test.json",
    titleZh: "台架实测与删失登记",
    description: "录入台架实测记录：删失不得记为终点值，停机原因必填。",
    criteria: [
      "censoring_type 明确（RIGHT / LEFT / INTERVAL / NONE），删失值不得当终点值",
      "event_occurred / event_time 与 anomalies 一致，停机原因必填",
      "raw_record_reference 指向原始记录，不得只留整理稿",
    ],
  },
  {
    chainIndex: 21,
    skill: "variance-assessment",
    stage: "VARIANCE_ASSESSED",
    artifactType: "variance",
    file: "variance.json",
    titleZh: "方差与重复性判定",
    description: "判定观测差异是否真实存在；测不出差异时要区分「真的没差异」与「功效不足」。",
    criteria: [
      "verdict 明确（真实差异 / 无可检出差异 / 功效不足 / 重复不一致）",
      "power 与 k_ratio 支撑判定，UNDERPOWERED 不得当作没差异",
      "computed_by 指向计算引擎，禁止手工计算方差",
    ],
  },
  {
    chainIndex: 22,
    skill: "doe-design",
    stage: "NEXT_BATCH_DECIDED",
    artifactType: "next_batch",
    file: "next_batch.json",
    titleZh: "模型更新与序贯决策",
    description: "用新数据更新模型并给出下一轮小批的决策与理由（或显式终止理由）。",
    criteria: [
      "指明下一轮批次与理由，或显式记录终止理由",
      "模型更新引用了最新一轮台架与筛测数据",
      "结论与证据链一致，不得以单点结果下结论",
    ],
  },
  {
    chainIndex: 23,
    skill: "optimization",
    stage: "NON_INFERIORITY_PASSED",
    artifactType: "optimization",
    file: "optimization.json",
    titleZh: "优化与非劣效判定",
    description: "默认约束满足型优化，以参照物为基准做非劣效判定；成本是约束而非判据。",
    criteria: [
      "以参照物为基准给出非劣效结论，方法与阈值明确",
      "成本只作约束，不参与判据",
      "候选配方与引擎交接记录齐备",
    ],
  },
  {
    chainIndex: 24,
    skill: "process-scale-up",
    stage: "PROCESS_SCALE_VALIDATED",
    artifactType: "process",
    file: "process.json",
    titleZh: "工艺窗口与放大验证",
    description: "固化 validated 的工艺窗口并验证放大可行性，制造可行性须指向 PROCESS-WINDOW 引用。",
    criteria: [
      "process_window.validated 为 true，窗口有 basis 与来源",
      "制造可行性引用 PROCESS-WINDOW:<window_id>，不得空口声明",
      "放大倍数有来源，换釜复现记录一致，scale_class 沿 LAB→PILOT→PRODUCTION 前进",
    ],
  },
  {
    chainIndex: 25,
    skill: "knowledge-archive",
    stage: "KNOWLEDGE_ARCHIVED",
    artifactType: "knowledge_asset",
    file: "knowledge_asset.json",
    titleZh: "知识入库（资产封存）",
    description: "六类知识资产齐备才可 CLOSED_KNOWLEDGE；SYNTHETIC 证据只能停在 DRAFT。",
    criteria: [
      "六类资产齐备（推荐配方 / 可行设计空间 / 临界失效边界 / 证据包 / 材料知识 / 模型）",
      "asset_status=CLOSED_KNOWLEDGE 才可归档，SYNTHETIC 强制 DRAFT_KNOWLEDGE",
      "每条资产带证据引用，可被后续项目的知识检索复用",
    ],
  },
];

const BY_STAGE: ReadonlyMap<string, StageContract> = new Map(
  STAGE_CHAIN.map((c) => [c.stage, c] as const),
);

/**
 * 镜像 state-machine.json 的 type_routes（7 类）。
 *
 * 注意：PROCESS_WINDOW_DEFINED **不在任何一条路由上** —— 它是 on-demand
 * 阶段（见 ON_DEMAND_STAGES）。工艺窗口固化对润滑脂是一等维度（皂化 / 转相 /
 * 冷却速率决定皂纤维骨架，同配方换釜可出不同产品），对调和油只是二阶变量
 * （物理混合，不生成产品结构）。把它排进每条油品链会迫使研发员为走完流程
 * 填写一个无意义的工件 —— 与本领域包 NO Invented Process Data 红线直接冲突。
 *
 * 第 7 类 PRECISION_GREASE_DEV（精密传动脂）是唯一走满 20 步的路线：它用
 * 独立的 PROCESS_SCALE_VALIDATED 表达工艺放大，不复用按需阶段
 * PROCESS_WINDOW_DEFINED（契约 on_demand_stages 的 note 明确此事）。
 */
export const TYPE_ROUTES: Record<ProjectType, readonly ChainStage[]> = {
  NEW_PRODUCT: [
    "PROJECT_DEFINED", "DUTY_DEFINED", "CHALLENGES_DEFINED", "FAILURE_CTQ_DEFINED",
    "TEST_METHODS_QUALIFIED", "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED",
    "EXPERIMENT_RUNNING", "MODEL_BUILT", "OPTIMIZED", "VERIFIED", "APPLIED",
  ],
  IMPROVEMENT: [
    "PROJECT_DEFINED", "FAILURE_CTQ_DEFINED", "TEST_METHODS_QUALIFIED",
    "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING",
    "MODEL_BUILT", "OPTIMIZED", "VERIFIED", "APPLIED",
  ],
  COST_DOWN: [
    "PROJECT_DEFINED", "FAILURE_CTQ_DEFINED", "DESIGN_SPACE_DEFINED",
    "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING", "OPTIMIZED", "VERIFIED", "APPLIED",
  ],
  CUSTOMIZATION: [
    "PROJECT_DEFINED", "FAILURE_CTQ_DEFINED", "TEST_METHODS_QUALIFIED",
    "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING", "VERIFIED", "APPLIED",
  ],
  EXPLORATION: [
    "PROJECT_DEFINED", "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED",
    "EXPERIMENT_RUNNING", "MODEL_BUILT", "VERIFIED", "APPLIED",
  ],
  PROCESS_ROBUSTNESS: [
    "PROJECT_DEFINED", "FAILURE_CTQ_DEFINED", "TEST_METHODS_QUALIFIED",
    "DESIGN_SPACE_DEFINED", "EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING",
    "MODEL_BUILT", "APPLIED",
  ],
  // 精密传动脂开发：20 步，逐项照抄契约 type_routes（含 12 个新 stage）。
  // 与油品路线并列，不是它的延长线：内环迭代（战役 → 制脂 → 筛测 → 台架 →
  // 方差 → 下一批）插在 DOE 与模型之间，末端多出非劣效 / 工艺放大 / 知识入库。
  PRECISION_GREASE_DEV: [
    "PROJECT_DEFINED", "DUTY_DEFINED", "FAILURE_MECHANISM_DEFINED",
    "REFERENCE_MATERIAL_RESOLVED", "TEST_METHODS_QUALIFIED", "DESIGN_SPACE_DEFINED",
    "BENCH_RESOURCE_REGISTERED", "CAMPAIGN_OPENED", "EXPERIMENT_DESIGNED",
    "BATCH_PRODUCED", "SCREENING_PASSED", "BENCH_TESTED", "VARIANCE_ASSESSED",
    "MODEL_BUILT", "NEXT_BATCH_DECIDED", "NON_INFERIORITY_PASSED",
    "PROCESS_SCALE_VALIDATED", "VERIFIED", "APPLIED", "KNOWLEDGE_ARCHIVED",
  ],
};

/**
 * 镜像 state-machine.json 的 `on_demand_stages`：可由技能产出、但不在任何
 * 路由上的阶段。后继由契约的 next_stage 决定，不由路由邻接决定。
 */
export const ON_DEMAND_STAGES: Record<string, { readonly skill: string; readonly nextStage: ChainStage }> = {
  PROCESS_WINDOW_DEFINED: { skill: "process-scale-up", nextStage: "VERIFIED" },
};

export const PROJECT_TYPES = Object.keys(TYPE_ROUTES) as ProjectType[];

export function isProjectType(value: unknown): value is ProjectType {
  return typeof value === "string" && value in TYPE_ROUTES;
}

/**
 * 开发期告警：只在 DEV 构建里输出。
 *
 * 旧实现遇到契约/镜像漂移是**静默**的：路由里的未知 stage 被直接丢掉、
 * 未知 project_type 被静默换成 NEW_PRODUCT，界面上完全看不出来 —— 面板
 * 只是少几步或悄悄走错链。这里把漂移变成可见的 console.warn（生产构建下
 * `import.meta.env.DEV` 为 false，分支被静态剔除）。
 */
function warnDev(message: string): void {
  if (import.meta.env.DEV) console.warn(`[lubricantContracts] ${message}`);
}

/** 某 project_type 下的有序步骤列表；未知类型回退 NEW_PRODUCT（DEV 下告警）。 */
export function routeFor(projectType: string | null | undefined): StageContract[] {
  const known = isProjectType(projectType);
  if (!known && typeof projectType === "string" && projectType.length > 0) {
    // 非空但不在枚举里 = 契约新增了类型而镜像没跟上，或工作区写错了值。
    // null / undefined / "" 是「项目尚未声明类型」的合法回退路径，不告警。
    warnDev(
      `未知 project_type "${projectType}"，已回退 NEW_PRODUCT；请核对 ` +
        `domains/lubricant/contracts/state-machine.json 的 type_routes 与 TYPE_ROUTES 是否漂移`,
    );
  }
  const key: ProjectType = known ? projectType : "NEW_PRODUCT";
  const out: StageContract[] = [];
  for (const stage of TYPE_ROUTES[key]) {
    const contract = BY_STAGE.get(stage);
    if (contract) {
      out.push(contract);
    } else {
      warnDev(
        `${key} 的路由含 STAGE_CHAIN 未定义的 stage "${stage}"，该步已跳过；` +
          `请核对 state-machine.json 的 stages 与 STAGE_CHAIN 是否漂移`,
      );
    }
  }
  return out;
}

/* ------------------------------------------------------------------ *
 * 轻量结构校验（lite）
 * 完整校验由领域包 Python 侧负责：
 *   python domains/lubricant/scripts/validate_schemas.py
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
    "business_objective", "technical_objective", "hard_constraints",
    // target_cost 已由领域包移出 required（成本是天花板不是目标）：改由
    // cost_basis_reason 条件必填（schema 走 allOf if/then），且可改用 cost_ceiling。
    // lite 校验只做结构必填、不复刻业务条件（见上方「轻量结构校验」说明）。
    // benchmark_products 同理：条件必填，凭 benchmark_waiver_reason 豁免。
    "success_criteria", "risk_class", "owner"],
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
  process: ["artifact_type", "process_id", "project_reference", "process_step", "batch_scale",
    "amplification_factor", "process_window", "control_points", "cpk", "material_batch_reference",
    "factor_role"],
  // process_window_reference 刻意不列入：工艺窗口是按需工件（仅润滑脂），
  // 调和油的 application 记录天然没有窗口可引用。schema 保留该键为可选。
  application: ["artifact_type", "application_id", "project_reference", "formula_reference",
    "acceptance_criteria", "result", "counterexamples",
    "life_claim_boundary", "source", "evidence_id", "evidence_scope"],
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
