/**
 * 润滑油研发工作区工件探测。
 *
 * 设计约束（勿违反）：
 *  1. 不使用 resolveArtifactPath —— 其 miss 缓存（artifactFile.ts 的
 *     resolvedPaths）只在切换 workspace 时清空（runtime.ts 的 moveSession…），
 *     用它做轮询会让 Agent 新建的工件永远读不到。
 *  2. 只读，不写盘；写盘见后续 Task 4 的 gate 落盘。
 *  3. 浏览器（非 Tauri）下返回 live:false，由 UI 走显式 Mock 降级，
 *     绝不假装磁盘上有工件。
 */
import { isTauri } from "./tauri";
import { listDir, readArtifact } from "./artifactFile";
import {
  STAGE_CHAIN,
  routeFor,
  validateArtifactLite,
  type StageContract,
} from "./lubricantContracts";

/**
 * AGENTS.md 声明工件落在项目根目录或对应数据目录。listDir 非递归，所以每个
 * 候选目录要单独列一次；缺失目录在桌面端会 reject，逐个 try/catch。
 * 根目录排在最前，同名文件以根目录为准。
 */
const CANDIDATE_DIRS = ["", "docs", "data", "notes", "knowledge"] as const;

export interface ArtifactProbe {
  readonly artifactType: string;
  readonly file: string;
  /** 文件存在（无论校验是否通过）。 */
  readonly exists: boolean;
  /** 存在且 lite 校验通过。 */
  readonly valid: boolean;
  readonly errors: readonly string[];
  /** 解析出的 JSON 内容，供读取 project_type / stage / gate_status 等字段。 */
  readonly data: Record<string, unknown> | null;
  /** 命中时的根相对路径（用于后续 readArtifact / 打开预览）。 */
  readonly resolvedPath: string | null;
}

export interface WorkspaceSnapshot {
  /** false = 当前环境无磁盘能力（浏览器），UI 必须走 Mock 降级。 */
  readonly live: boolean;
  /** 探测时间戳，用于 UI 显示「x 秒前」。 */
  readonly probedAt: number;
  readonly probes: Readonly<Record<string, ArtifactProbe>>;
  /** project.json 的 project_type；存在时锁定 UI 的类型选择器。 */
  readonly projectType: string | null;
  /** project.json 的 stage。 */
  readonly projectStage: string | null;
  /** gate.json 的 gate_status。 */
  readonly gateStatus: string | null;
}

/** 浏览器下的空快照 —— 明确标记 live:false。 */
export function emptySnapshot(): WorkspaceSnapshot {
  return {
    live: false,
    probedAt: Date.now(),
    probes: {},
    projectType: null,
    projectStage: null,
    gateStatus: null,
  };
}

function emptyProbe(contract: StageContract): ArtifactProbe {
  return {
    artifactType: contract.artifactType,
    file: contract.file,
    exists: false,
    valid: false,
    errors: [],
    data: null,
    resolvedPath: null,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** 建立「文件名 → 根相对路径」映射；逐个目录 try/catch，缺失目录不致命。 */
async function collectFileIndex(): Promise<Map<string, string>> {
  const index = new Map<string, string>();
  for (const dir of CANDIDATE_DIRS) {
    let entries;
    try {
      entries = await listDir(dir, "workspace");
    } catch {
      continue; // 目录不存在 / 无权限 / 非目录 —— 跳过，不影响其它目录
    }
    for (const entry of entries) {
      if (entry.isDir) continue;
      if (!index.has(entry.name)) index.set(entry.name, entry.path);
    }
  }
  return index;
}

async function probeOne(
  contract: StageContract,
  index: ReadonlyMap<string, string>,
): Promise<ArtifactProbe> {
  const base = emptyProbe(contract);
  const resolvedPath = index.get(contract.file);
  if (!resolvedPath) return base;

  let file;
  try {
    file = await readArtifact(resolvedPath, "workspace");
  } catch {
    return { ...base, exists: true, resolvedPath, errors: ["读取失败"] };
  }
  if (!file) return { ...base, exists: true, resolvedPath, errors: ["读取失败"] };
  if (file.encoding !== "utf8") {
    return { ...base, exists: true, resolvedPath, errors: ["非 UTF-8 文本"] };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(file.data);
  } catch {
    return { ...base, exists: true, resolvedPath, errors: ["JSON 解析失败"] };
  }

  const errors = validateArtifactLite(contract.artifactType, parsed);
  return {
    ...base,
    exists: true,
    valid: errors.length === 0,
    errors,
    resolvedPath,
    data: isRecord(parsed) ? parsed : null,
  };
}

/**
 * 探测当前活动工作区中的全部 11 个链上工件。
 *
 * 探测的是整条 11 步链而不是某个 project_type 的子集：project_type 本身就
 * 存放在 project.json 里，必须先读到它才能确定路由（鸡生蛋问题）。
 */
export async function probeWorkspace(): Promise<WorkspaceSnapshot> {
  const probedAt = Date.now();
  if (!isTauri) return { ...emptySnapshot(), probedAt };

  const index = await collectFileIndex();
  const entries = await Promise.all(
    STAGE_CHAIN.map(async (c) => [c.artifactType, await probeOne(c, index)] as const),
  );
  const probes = Object.fromEntries(entries);

  // 只有结构合规的工件才能充当权威来源：一份坏掉的 project.json 不该锁定
  // 类型选择器，也不该宣称项目处于某个 stage。
  const project = probes.project?.valid ? probes.project.data : null;
  const gate = probes.gate?.valid ? probes.gate.data : null;

  return {
    live: true,
    probedAt,
    probes,
    projectType: str(project?.project_type),
    projectStage: str(project?.stage),
    gateStatus: str(gate?.gate_status),
  };
}

export type StepStatus = "completed" | "active" | "pending";

export interface StepView extends StageContract {
  readonly status: StepStatus;
  readonly probe: ArtifactProbe | null;
}

/**
 * 按 routeFor 的顺序推导每步状态。
 *
 * - 工件存在且 lite 校验通过 → completed
 * - 第一个不满足者 → active
 * - 其余 → pending
 *
 * 三种「没有真实数据」的情形必须区分开，不能都装成有进度：
 * - `snapshot === null`（首次探测尚未返回）→ 全部 pending，界面显示扫描中
 * - `snapshot.live === false`（浏览器）→ 静态 Mock，仅供 UI 冒烟
 */
export function deriveSteps(
  projectType: string | null | undefined,
  snapshot: WorkspaceSnapshot | null,
): StepView[] {
  const contracts = routeFor(projectType);
  if (!snapshot) {
    return contracts.map((c) => ({ ...c, status: "pending" as const, probe: null }));
  }
  if (!snapshot.live) {
    return contracts.map((c, i) => ({
      ...c,
      status: i === 0 ? ("completed" as const) : i === 1 ? ("active" as const) : ("pending" as const),
      probe: null,
    }));
  }
  const views: StepView[] = [];
  let activeAssigned = false;
  for (const c of contracts) {
    const probe = snapshot.probes[c.artifactType] ?? null;
    let status: StepStatus;
    if (probe?.valid) {
      status = "completed";
    } else if (!activeAssigned) {
      status = "active";
      activeAssigned = true;
    } else {
      status = "pending";
    }
    views.push({ ...c, status, probe });
  }
  return views;
}

/**
 * 生成交给中栏 Composer 的标准化提示词（Task 3）。
 *
 * 带上领域包技能名与真实文件名，避免 Agent 自创字段；显式要求 PHYSICAL
 * 证据，因为 route_step.py 对 SYNTHETIC 直接 DENY。
 */
export function buildStepPrompt(step: Pick<StepView, "titleZh" | "stage" | "file" | "skill" | "criteria">): string {
  return [
    `请推进「${step.titleZh}」（stage=${step.stage}，工件 ${step.file}）。`,
    `严格按领域包技能 skills/${step.skill} 的规范生成工件，不要自创字段。`,
    `准入考核标准：${step.criteria.join("；")}。`,
    `证据范围必须为 PHYSICAL；不得捏造实验数据。`,
    `工件落盘到项目根目录，并在完成后更新 docs/ 下的活报告。`,
  ].join("\n");
}

/** 门禁终审的提示词 —— gate 决议由 Agent 按 gate-review 技能产出。 */
export function buildGatePrompt(projectStage: string | null, gaps: readonly string[]): string {
  return [
    `请执行 skills/gate-review 门禁终审，生成 gate.json。`,
    `当前 project stage = ${projectStage ?? "未知"}。`,
    `gate_status 只能取 GO / HOLD / PIVOT / KILL / FREEZE；不得使用 REVISE。`,
    gaps.length
      ? `以下未解项必须先写入 unsatisfied_conditions 或 evidence_gaps：${gaps.join("；")}。`
      : `satisfied_conditions 与 unsatisfied_conditions 均需填写，evidence_gaps 为空才可 GO。`,
    `注意 gate.json 的 schema 禁止额外字段（unevaluatedProperties: false），签名与时间戳不要写进该文件。`,
  ].join("\n");
}
