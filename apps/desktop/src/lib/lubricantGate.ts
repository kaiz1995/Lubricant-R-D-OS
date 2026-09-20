/**
 * 润滑油研发门禁（Gate）判定与落盘。
 *
 * 本模块是领域包 gate-review 技能的**镜像实现**，三处权威来源：
 *   - skills/gate-review/scripts/preflight_gate_review.py  → 前置校验规则与 UPSTREAM
 *   - skills/gate-review/scripts/gate_review_policy.py     → final_status / 决议措辞模板
 *   - skills/gate-review/scripts/build_gate_artifact.py    → 工件字段来源
 *   - schemas/gate.schema.json                             → 最终结构（unevaluatedProperties: false）
 *
 * ⚠️ 门禁契约里**没有**数值阈值校验（成本 ≤ X、微点蚀 ≥ Y 级）。实测
 * `final_status()` 只看三件事：evidence_scope 是否为 SYNTHETIC、
 * unsatisfied_conditions / evidence_gaps 是否为空、evidence 里有无 status=="GAP"。
 * 数值达标属于 Phase 4 计算引擎的职责（optimization_result 的
 * result.recommended_candidates[].total_cost / predicted_ctq），那些信封不在
 * 11 步工件链上，因此面板**不**做数值判定 —— 不假装能判。
 */
import { readArtifact, writeWorkspaceFile } from "./artifactFile";
import { isGateStatus, validateArtifactLite, type GateStatus } from "./lubricantContracts";
import type { ArtifactProbe, WorkspaceSnapshot } from "./lubricantArtifacts";

/** 镜像 preflight_gate_review.py 的 UPSTREAM：9 个上游工件及其应处 stage。 */
export const GATE_UPSTREAM = [
  { artifactType: "project", stage: "PROJECT_DEFINED", label: "立项章程" },
  { artifactType: "challenge", stage: "CHALLENGES_DEFINED", label: "技术挑战" },
  { artifactType: "failure_ctq", stage: "FAILURE_CTQ_DEFINED", label: "失效与 CTQ" },
  { artifactType: "test_method", stage: "TEST_METHODS_QUALIFIED", label: "测试方法" },
  { artifactType: "design_space", stage: "DESIGN_SPACE_DEFINED", label: "设计空间" },
  { artifactType: "experiment_design", stage: "EXPERIMENT_DESIGNED", label: "DOE 设计" },
  { artifactType: "experiment", stage: "EXPERIMENT_RUNNING", label: "实验数据" },
  { artifactType: "model", stage: "MODEL_BUILT", label: "统计模型" },
  { artifactType: "optimization", stage: "OPTIMIZED", label: "配方优化" },
] as const;

/** 镜像 preflight 的 scopes 集合：这 5 个工件的 evidence_scope 必须存在且一致。 */
const SCOPE_BEARING = [
  "test_method",
  "experiment_design",
  "experiment",
  "model",
  "optimization",
] as const;

/** 镜像 preflight 的链路完整性检查。 */
const LINKS: readonly { from: string; fromField: string; to: string; toField: string }[] = [
  { from: "failure_ctq", fromField: "challenge_reference", to: "challenge", toField: "challenge_id" },
  { from: "test_method", fromField: "target_failure_reference", to: "failure_ctq", toField: "failure_id" },
  { from: "design_space", fromField: "design_space_id", to: "test_method", toField: "__method_link__" },
  { from: "experiment_design", fromField: "design_space_reference", to: "design_space", toField: "design_space_id" },
  { from: "experiment", fromField: "experiment_design_reference", to: "experiment_design", toField: "experiment_design_id" },
  { from: "model", fromField: "experiment_reference", to: "experiment", toField: "experiment_id" },
  { from: "optimization", fromField: "model_reference", to: "model", toField: "model_id" },
];

export interface GateCheck {
  readonly id: string;
  readonly label: string;
  readonly ok: boolean;
  readonly detail: string;
}

export interface GateEvaluation {
  readonly checks: readonly GateCheck[];
  /** 阻止签发 GO 的原因；空数组表示可 GO（仍需 evidenceScope === PHYSICAL）。 */
  readonly blockers: readonly string[];
  readonly canGo: boolean;
  /** 取自 optimization.json 的 evidence_scope（与 build_gate_artifact.py 一致）。 */
  readonly evidenceScope: string | null;
  readonly projectId: string | null;
  readonly experimentId: string | null;
  /** 上游工件里已记录的缺口与未解条件，供面板预填 HOLD 理由。 */
  readonly upstreamUnresolved: readonly string[];
}

export interface GateEvidenceItem {
  readonly evidence_id: string;
  readonly statement: string;
  readonly source: string;
  readonly status: "OBSERVED" | "ASSUMED" | "GAP";
}

export interface GateSubmission {
  readonly gateId: string;
  readonly scope: string;
  readonly gateStatus: GateStatus;
  /** PIVOT / KILL / FREEZE 必填（非空），否则 preflight 会拒。 */
  readonly reason: string;
  readonly satisfiedConditions: readonly string[];
  readonly unsatisfiedConditions: readonly string[];
  readonly evidenceGaps: readonly string[];
  readonly risks: readonly string[];
  readonly evidence: readonly GateEvidenceItem[];
}

export type GateArtifact = Record<string, unknown>;

function str(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function arr(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

/** 镜像 gate_review_policy.has_gap。 */
export function hasGap(evidence: readonly GateEvidenceItem[]): boolean {
  return evidence.some((item) => item.status === "GAP");
}

/** 镜像 gate_review_policy.final_status。 */
export function finalStatus(
  submission: Pick<
    GateSubmission,
    "gateStatus" | "unsatisfiedConditions" | "evidenceGaps" | "evidence"
  >,
  evidenceScope: string | null,
): GateStatus {
  if (evidenceScope === "SYNTHETIC") return "HOLD";
  const unresolved =
    submission.unsatisfiedConditions.length > 0 ||
    submission.evidenceGaps.length > 0 ||
    hasGap(submission.evidence);
  if (submission.gateStatus === "GO" && unresolved) return "HOLD";
  return submission.gateStatus;
}

/** 从探测结果中取出某工件的 JSON 内容（仅当结构合规）。 */
function dataOf(snapshot: WorkspaceSnapshot, artifactType: string): Record<string, unknown> | null {
  const probe: ArtifactProbe | undefined = snapshot.probes[artifactType];
  return probe?.valid ? probe.data : null;
}

/** 面板侧的门禁前置校验，逐条对应 preflight_gate_review.errors_for。 */
export function evaluateGate(snapshot: WorkspaceSnapshot | null): GateEvaluation {
  const checks: GateCheck[] = [];
  const blockers: string[] = [];

  const add = (id: string, label: string, ok: boolean, detail: string) => {
    checks.push({ id, label, ok, detail });
    // 阻塞项带上检查名，既方便面板直接展示，也让它能原样进 unsatisfied_conditions
    if (!ok) blockers.push(`${label}：${detail}`);
  };

  if (!snapshot?.live) {
    return {
      checks: [
        {
          id: "environment",
          label: "工作区可读",
          ok: false,
          detail: "当前环境无磁盘访问（浏览器），无法校验门禁条件",
        },
      ],
      blockers: ["当前环境无磁盘访问（浏览器），无法校验门禁条件"],
      canGo: false,
      evidenceScope: null,
      projectId: null,
      experimentId: null,
      upstreamUnresolved: [],
    };
  }

  const data = new Map<string, Record<string, unknown> | null>();
  for (const item of GATE_UPSTREAM) data.set(item.artifactType, dataOf(snapshot, item.artifactType));

  // 1) 9 个上游工件齐备且结构合规
  const missing = GATE_UPSTREAM.filter((item) => !data.get(item.artifactType)).map(
    (item) => `${item.artifactType}.json`,
  );
  add(
    "upstream-present",
    "9 个上游工件齐备且结构合规",
    missing.length === 0,
    missing.length
      ? `缺失或不合规：${missing.join("、")}`
      : `${GATE_UPSTREAM.length} 个上游工件全部就绪`,
  );

  // 2) 各上游 stage 正确
  const wrongStage = GATE_UPSTREAM.filter((item) => {
    const d = data.get(item.artifactType);
    return d && d.stage !== item.stage;
  }).map((item) => `${item.artifactType}(期望 ${item.stage})`);
  add(
    "upstream-stage",
    "上游工件 stage 与链位一致",
    wrongStage.length === 0,
    wrongStage.length ? `stage 不符：${wrongStage.join("、")}` : "全部匹配",
  );

  // 3) 各上游 decision 为 GO
  const notGo = GATE_UPSTREAM.filter((item) => {
    const d = data.get(item.artifactType);
    return d && d.decision !== "GO";
  }).map((item) => `${item.artifactType}(${String(data.get(item.artifactType)?.decision)})`);
  add(
    "upstream-decision",
    "上游工件 decision 均为 GO",
    notGo.length === 0,
    notGo.length ? `非 GO：${notGo.join("、")}` : "全部 GO",
  );

  // 4) project.status === ACTIVE
  const project = data.get("project");
  add(
    "project-active",
    "project.json 状态为 ACTIVE",
    project?.status === "ACTIVE",
    project ? `status = ${String(project.status)}` : "project.json 不可用",
  );

  // 5) 全部上游 project_id 一致
  const ids = GATE_UPSTREAM.map((item) => str(data.get(item.artifactType)?.project_id)).filter(
    (v): v is string => v !== null,
  );
  const uniqueIds = [...new Set(ids)];
  add(
    "project-id",
    "上游工件 project_id 一致",
    ids.length > 0 && uniqueIds.length === 1,
    uniqueIds.length === 1 ? uniqueIds[0] : `出现多个 project_id：${uniqueIds.join("、") || "无"}`,
  );

  // 6) 5 个承范围工件的 evidence_scope 存在且一致
  const scopes = SCOPE_BEARING.map((t) => str(data.get(t)?.evidence_scope)).filter(
    (v): v is string => v !== null,
  );
  const uniqueScopes = [...new Set(scopes)];
  const scopesValid =
    scopes.length === SCOPE_BEARING.length &&
    uniqueScopes.length === 1 &&
    (uniqueScopes[0] === "SYNTHETIC" || uniqueScopes[0] === "PHYSICAL");
  add(
    "evidence-scope",
    "证据范围一致且合法",
    scopesValid,
    scopesValid
      ? `evidence_scope = ${uniqueScopes[0]}`
      : `5 个承范围工件需存在且一致，实际：${uniqueScopes.join("、") || "无"}`,
  );

  const evidenceScope = uniqueScopes.length === 1 ? uniqueScopes[0] : null;

  // 7) test_method 已资格确认且指向 failure_ctq
  const method = data.get("test_method");
  const failure = data.get("failure_ctq");
  const methodLinked =
    !!method &&
    !!failure &&
    method.target_failure_reference === failure.failure_id &&
    method.qualification_status === "QUALIFIED";
  add(
    "method-qualified",
    "test_method 已资格确认并关联失效项",
    methodLinked,
    methodLinked
      ? `qualification_status = QUALIFIED，method_id = ${String(method.method_id)}`
      : `需 target_failure_reference 指向 failure_ctq 且 qualification_status = QUALIFIED，实际 ${String(method?.qualification_status)}`,
  );

  // 8) 链路完整性（design_space → test_method 的比较方式与 preflight 一致）
  const broken: string[] = [];
  for (const link of LINKS) {
    const from = data.get(link.from);
    const to = data.get(link.to);
    if (!from || !to) continue;
    if (link.toField === "__method_link__") {
      const expected = [str(to.method_id)];
      const actual = arr(from.qualified_test_method_references).map(String);
      if (actual.length !== expected.length || actual[0] !== expected[0]) {
        broken.push(`${link.from}.qualified_test_method_references ≠ [${String(to.method_id)}]`);
      }
      continue;
    }
    if (from[link.fromField] !== to[link.toField]) {
      broken.push(`${link.from}.${link.fromField} ≠ ${link.to}.${link.toField}`);
    }
  }
  add(
    "chain-links",
    "工件引用链完整",
    broken.length === 0,
    broken.length ? broken.join("；") : "7 条引用全部对齐",
  );

  // 9) 上游未解缺口汇总（preflight 不检查，但 HOLD 语义要求面板先暴露）
  const upstreamGaps: string[] = [];
  for (const item of GATE_UPSTREAM) {
    const d = data.get(item.artifactType);
    if (!d) continue;
    for (const g of arr(d.evidence_gaps)) upstreamGaps.push(`${item.artifactType}: ${String(g)}`);
  }
  const upstreamUnresolved: string[] = [];
  for (const item of GATE_UPSTREAM) {
    const d = data.get(item.artifactType);
    if (!d) continue;
    for (const u of arr(d.unsatisfied_conditions))
      upstreamUnresolved.push(`${item.artifactType}: ${String(u)}`);
  }

  return {
    checks,
    blockers,
    canGo: blockers.length === 0 && evidenceScope === "PHYSICAL",
    evidenceScope,
    projectId: uniqueIds.length === 1 ? uniqueIds[0] : null,
    experimentId: str(data.get("experiment")?.experiment_id),
    upstreamUnresolved: [...upstreamGaps, ...upstreamUnresolved],
  };
}

/**
 * 按 build_gate_artifact.py + gate_review_policy.expected_decision_fields 组装工件。
 *
 * 字段来源必须逐一对齐，否则 `unevaluatedProperties: false` 或 required 会拒。
 */
export function buildGateArtifact(
  evaluation: Pick<GateEvaluation, "evidenceScope" | "projectId" | "experimentId">,
  submission: GateSubmission,
): GateArtifact {
  const status = finalStatus(submission, evaluation.evidenceScope);
  const gateId = submission.gateId;
  const synthetic = evaluation.evidenceScope === "SYNTHETIC";

  const decisionQuestion = `Does review Gate ${gateId} have sufficient supplied conditions and evidence?`;
  const hypothesis = `${gateId} records supplied review conditions without creating a Freeze or Close artifact.`;
  const uncertainty =
    "This review records supplied conditions, gaps, risks, and disposition only; it does not create new experiment, model, optimization, Freeze, Close, or product-performance evidence.";
  const decisionRule =
    "GO requires no unsatisfied conditions, no evidence gaps, and no GAP evidence; PIVOT, KILL, and FREEZE require explicit reason and evidence; otherwise retain HOLD.";
  const result = synthetic
    ? `${gateId} is WORKFLOW_VALIDATED only; SYNTHETIC evidence cannot authorize a state transition.`
    : `${gateId} has deterministic gate disposition ${status} from the supplied review conditions and evidence.`;
  const nextAction =
    status === "GO"
      ? "Advance only under the state-machine action authorized by this recorded Gate."
      : synthetic
        ? "Retain this WORKFLOW_VALIDATED replay without state transition."
        : "Retain the supplied review record and resolve or execute its stated disposition without creating a Freeze or Close artifact here.";

  return {
    schema_version: "0.1.0",
    artifact_type: "gate",
    project_id: evaluation.projectId ?? "unknown-project",
    stage: "VERIFIED",
    evidence_scope: evaluation.evidenceScope,
    decision_question: decisionQuestion,
    hypothesis,
    uncertainty,
    evidence: submission.evidence.map((item) => ({ ...item })),
    decision_rule: decisionRule,
    result,
    decision: status,
    next_action: nextAction,
    gate_id: gateId,
    experiment_reference: evaluation.experimentId ?? "unknown-experiment",
    scope: submission.scope,
    satisfied_conditions: [...submission.satisfiedConditions],
    unsatisfied_conditions: [...submission.unsatisfiedConditions],
    evidence_gaps: [...submission.evidenceGaps],
    risks: [...submission.risks],
    gate_status: status,
  };
}

/** 生成下一个 gate_id：已存在 GATE-<pid>-NNN 时递增序号，避免静默覆盖。 */
export function nextGateId(projectId: string | null, existingGateId: string | null): string {
  const prefix = `GATE-${projectId ?? "PROJECT"}-`;
  const match = existingGateId ? /^(.*?)-(\d+)$/.exec(existingGateId) : null;
  if (match && existingGateId?.startsWith(prefix)) {
    return `${prefix}${String(Number(match[2]) + 1).padStart(3, "0")}`;
  }
  return `${prefix}001`;
}

export interface GateDraftInput {
  readonly gateId: string;
  readonly scope: string;
  readonly gateStatus: GateStatus;
  /** PIVOT / KILL / FREEZE 必填（preflight 会拒空 reason）。 */
  readonly reason: string;
  /** 每行一条风险；留空时回落到上游工件已记录的 risks。 */
  readonly risksText: string;
}

/**
 * 由探测结果与检查结论生成一份可提交的 gate 记录。
 *
 * 面板只让研发员决定「决议 + 理由 + 风险」，其余字段（已满足条件、证据包、
 * 缺口）一律从工件推导 —— 手填这些字段等于绕过证据链。
 */
export function suggestGateSubmission(
  snapshot: WorkspaceSnapshot,
  evaluation: GateEvaluation,
  draft: GateDraftInput,
): GateSubmission {
  const satisfiedConditions = evaluation.checks
    .filter((c) => c.ok)
    .map((c) => `${c.label}：${c.detail}`);

  // GO 不允许带未解条件；其他决议把阻塞项原样记为未解条件
  const unsatisfiedConditions =
    draft.gateStatus === "GO" ? [] : [...evaluation.blockers];

  // 上游工件**没有** risks 字段（实测只有 gate.schema.json 有），所以这里不做
  // 汇总 —— 空着就如实写「未记录残余风险」，而不是编造一条看起来像结论的风险。
  const typedRisks = draft.risksText
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  const risks = typedRisks.length ? typedRisks : ["未记录残余风险"];

  const evidence: GateEvidenceItem[] = [];
  for (const item of GATE_UPSTREAM) {
    const probe = snapshot.probes[item.artifactType];
    if (!probe?.valid) continue;
    evidence.push({
      evidence_id: `E-${item.artifactType.toUpperCase().replace(/_/g, "-")}`,
      statement: `${item.label}工件已就绪（stage=${item.stage}，decision=GO）`,
      source: probe.resolvedPath ?? `${item.artifactType}.json`,
      status: "OBSERVED",
    });
  }

  return {
    gateId: draft.gateId,
    scope: draft.scope,
    gateStatus: draft.gateStatus,
    reason: draft.reason,
    satisfiedConditions,
    unsatisfiedConditions,
    evidenceGaps: [...evaluation.upstreamUnresolved],
    risks,
    evidence,
  };
}

export interface GateWriteResult {
  readonly path: string;
  readonly gateStatus: GateStatus;
  readonly historyPath: string | null;
}

/**
 * 落盘 gate.json，并把签名与时间戳追加到 docs/gate-history.jsonl。
 *
 * 签名/时间戳**不能**写进 gate.json —— gate.schema.json 的
 * `unevaluatedProperties: false` 会直接判非法（已实测 REJECT）。
 */
export async function writeGateArtifact(
  artifact: GateArtifact,
  history: { operator: string; signedAt: string; note?: string },
): Promise<GateWriteResult> {
  const errors = validateArtifactLite("gate", artifact);
  if (errors.length) {
    throw new Error(`拒绝写入不合规的 gate.json：${errors.join("；")}`);
  }

  // 捕获原文以便回滚
  let previous: string | null = null;
  try {
    const file = await readArtifact("gate.json", "workspace");
    if (file?.encoding === "utf8") previous = file.data;
  } catch {
    previous = null;
  }

  const content = `${JSON.stringify(artifact, null, 2)}\n`;
  await writeWorkspaceFile("gate.json", content, "workspace");

  // 回读自检；失败则回滚
  try {
    const back = await readArtifact("gate.json", "workspace");
    const parsed: unknown = back?.encoding === "utf8" ? JSON.parse(back.data) : null;
    const backErrors = validateArtifactLite("gate", parsed);
    if (backErrors.length) throw new Error(backErrors.join("；"));
  } catch (error) {
    if (previous !== null) {
      try {
        await writeWorkspaceFile("gate.json", previous, "workspace");
      } catch {
        /* 回滚也失败时保留原始错误 */
      }
    }
    throw new Error(`gate.json 回读自检失败，已回滚：${String(error)}`);
  }

  // 追加式历史记录：写不进也不影响 gate.json 已落盘的事实
  let historyPath: string | null = null;
  try {
    const line = JSON.stringify({
      gate_id: artifact.gate_id,
      gate_status: artifact.gate_status,
      operator: history.operator,
      signed_at: history.signedAt,
      note: history.note ?? null,
    });
    let existing = "";
    try {
      const file = await readArtifact("docs/gate-history.jsonl", "workspace");
      if (file?.encoding === "utf8") existing = file.data.endsWith("\n") || !file.data ? file.data : `${file.data}\n`;
    } catch {
      existing = "";
    }
    await writeWorkspaceFile("docs/gate-history.jsonl", `${existing}${line}\n`, "workspace");
    historyPath = "docs/gate-history.jsonl";
  } catch {
    historyPath = null;
  }

  const status = artifact.gate_status;
  return {
    path: "gate.json",
    gateStatus: isGateStatus(status) ? status : "HOLD",
    historyPath,
  };
}
