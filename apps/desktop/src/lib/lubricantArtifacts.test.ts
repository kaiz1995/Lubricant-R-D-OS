// The pane used to hand-write 21 artifact file names, so nothing it showed was
// ever tied to a file on disk. These checks cover the probe + status derivation
// that replaced it, and the prompt builders handed to the composer.
import { beforeEach, describe, expect, it, vi } from "vitest";

const isTauri = { value: true };
const listDir = vi.fn();
const readArtifact = vi.fn();

vi.mock("./tauri", () => ({ get isTauri() { return isTauri.value; } }));
vi.mock("./artifactFile", () => ({
  listDir: (...a: unknown[]) => listDir(...a),
  readArtifact: (...a: unknown[]) => readArtifact(...a),
}));

const {
  buildGatePrompt,
  buildStepPrompt,
  deriveSteps,
  derivedCurrentStage,
  emptySnapshot,
  probeWorkspace,
} = await import("./lubricantArtifacts");
const { STAGE_CHAIN } = await import("./lubricantContracts");

const entry = (name: string, path = name, isDir = false) => ({
  path,
  name,
  isDir,
  size: 10,
  modified: 1,
});

/** A schema-valid project.json — every required key of project + common. */
const validProject = (over: Record<string, unknown> = {}) => ({
  schema_version: "0.1.0",
  artifact_type: "project",
  project_id: "WGO-001",
  stage: "PROJECT_DEFINED",
  decision_question: "q", hypothesis: "h", uncertainty: "u",
  evidence: [{ evidence_id: "E-1", statement: "s", source: "x", status: "OBSERVED" }],
  decision_rule: "r", result: "res", decision: "GO", next_action: "n",
  status: "ACTIVE", project_name: "n", project_type: "NEW_PRODUCT", product_family: "f",
  business_objective: "b", technical_objective: "t", hard_constraints: ["c"],
  target_cost: {
    value: 1, unit: "CNY/kg", source: "s",
    method_version: "v", material_batch: "m", formula_version: "f",
  },
  benchmark_products: ["p"], success_criteria: ["c"], risk_class: "LOW", owner: "o",
  ...over,
});

const utf8 = (obj: unknown) => ({
  path: "x", mime: "application/json", encoding: "utf8",
  data: typeof obj === "string" ? obj : JSON.stringify(obj), size: 10,
});

/** 各类型 OWN_REQUIRED 的占位值 —— lite 校验只查键存在，值不重要。 */
const OWN_EXTRAS: Record<string, Record<string, unknown>> = {
  duty: { duty_id: "D-1", project_reference: "P-1", duty: {} },
  challenge: {
    duty_reference: "D-1", challenge_id: "C-1", category: "c", description: "d",
    severity: "HIGH", exposure: "e", lubricant_sensitivity: "s",
    evidence_gap: "g", priority: 1,
  },
  failure_ctq: {
    challenge_reference: "C-1", failure_id: "F-1", failure_mode: "m",
    mechanism: "mech", failure_diagnosis: "diag", root_cause_hypotheses: [],
    lubricant_contribution: "l", ctqs: [], test_chain: [],
  },
  test_method: {
    evidence_scope: "PHYSICAL", method_id: "TM-1", name: "n",
    standard: "DIN 51517-3", target_failure_reference: "F-1", role: "r",
    qualification_metrics: [], qualification_basis: "b",
    qualification_status: "QUALIFIED",
  },
  design_space: {
    design_space_id: "DS-1", scope: "s", variables: [], ctq_references: [],
    qualified_test_method_references: [], constraints: [],
  },
  experiment_design: {
    evidence_scope: "PHYSICAL", experiment_design_id: "EXP-1",
    design_space_reference: "DS-1", test_method_references: [],
    factor_references: [], design: {}, run_plan: [], responses: [],
    guardrails: [], expected_information_value: "v",
  },
};

/** 任意链上类型的一个能通过 validateArtifactLite 的工件。 */
const liteValid = (artifactType: string, over: Record<string, unknown> = {}) => ({
  schema_version: "0.1.0",
  artifact_type: artifactType,
  project_id: "HDG-NP-001",
  stage: "PROJECT_DEFINED",
  decision_question: "q", hypothesis: "h", uncertainty: "u",
  evidence: [], decision_rule: "r", result: "res", decision: "GO", next_action: "n",
  ...OWN_EXTRAS[artifactType],
  ...over,
});

beforeEach(() => {
  isTauri.value = true;
  listDir.mockReset();
  readArtifact.mockReset();
  // Root lists project.json + a nested duty.json under docs/; the other
  // candidate dirs reject, as a real workspace without them would.
  listDir.mockImplementation(async (dir: string) => {
    if (dir === "") return [entry("project.json"), entry("docs", "docs", true)];
    if (dir === "docs") return [entry("duty.json", "docs/duty.json")];
    throw new Error("not a directory");
  });
  readArtifact.mockImplementation(async (path: string) => {
    if (path === "project.json") return utf8(validProject());
    if (path === "docs/duty.json") return utf8({ artifact_type: "duty", schema_version: "0.1.0" });
    return null;
  });
});

describe("probeWorkspace", () => {
  it("浏览器下返回 live:false，不假装有磁盘", async () => {
    isTauri.value = false;
    const snap = await probeWorkspace();
    expect(snap.live).toBe(false);
    expect(snap.probes).toEqual({});
    expect(listDir).not.toHaveBeenCalled();
  });

  it("扫描候选目录并逐个 try/catch，缺失目录不影响其它目录", async () => {
    const snap = await probeWorkspace();
    expect(snap.live).toBe(true);
    expect(listDir).toHaveBeenCalledTimes(5);
    expect(snap.probes.project.valid).toBe(true);
    expect(snap.probes.duty.exists).toBe(true);
  });

  it("能读到子目录中的工件，并记录其根相对路径", async () => {
    const snap = await probeWorkspace();
    expect(snap.probes.duty.resolvedPath).toBe("docs/duty.json");
  });

  it("从 project.json 提取 project_type 与 stage 作为权威", async () => {
    const snap = await probeWorkspace();
    expect(snap.projectType).toBe("NEW_PRODUCT");
    expect(snap.charterStage).toBe("PROJECT_DEFINED");
  });

  it("结构不合规的工件 exists 但 valid=false，并给出原因", async () => {
    readArtifact.mockImplementation(async (path: string) =>
      path === "project.json"
        ? utf8(validProject({ artifact_type: "not_project" }))
        : utf8({ artifact_type: "duty", schema_version: "0.1.0" }),
    );
    const snap = await probeWorkspace();
    expect(snap.probes.project.exists).toBe(true);
    expect(snap.probes.project.valid).toBe(false);
    expect(snap.probes.project.errors.some((e) => e.includes("artifact_type"))).toBe(true);
    // 坏掉的 project.json 不得充当权威：既不锁定类型，也不宣称 stage
    expect(snap.projectType).toBeNull();
    expect(snap.charterStage).toBeNull();
  });

  it("坏掉的 gate.json 不宣称门禁已签署", async () => {
    readArtifact.mockImplementation(async (path: string) => {
      if (path === "gate.json") return utf8({ artifact_type: "gate", gate_status: "GO" });
      return null;
    });
    listDir.mockImplementation(async (dir: string) => {
      if (dir !== "") throw new Error("not a directory");
      return [entry("gate.json")];
    });
    const snap = await probeWorkspace();
    expect(snap.probes.gate.exists).toBe(true);
    expect(snap.probes.gate.valid).toBe(false);
    expect(snap.gateStatus).toBeNull();
  });

  it("JSON 解析失败被单独标记，而不是抛错", async () => {
    readArtifact.mockImplementation(async (path: string) =>
      path === "project.json" ? utf8("{ not json") : null,
    );
    const snap = await probeWorkspace();
    expect(snap.probes.project.errors).toEqual(["JSON 解析失败"]);
  });

  it("未在索引中的文件不触发读取", async () => {
    await probeWorkspace();
    const asked = readArtifact.mock.calls.map((c) => c[0]);
    expect(asked).toEqual(["project.json", "docs/duty.json"]);
    // 13 个链上工件里只有这两个存在
    expect(asked).not.toContain("gate.json");
    expect(asked).not.toContain("experiment_design.json");
  });

  it("探测整条 13 步链（project_type 本身就在工件里，鸡生蛋）", async () => {
    const snap = await probeWorkspace();
    expect(Object.keys(snap.probes).sort()).toEqual(
      STAGE_CHAIN.map((c) => c.artifactType).sort(),
    );
  });
});

describe("deriveSteps", () => {
  it("首次探测尚未返回时不假装有进度：全部 pending", () => {
    const steps = deriveSteps("NEW_PRODUCT", null);
    expect(steps).toHaveLength(13);
    expect(steps.every((s) => s.status === "pending")).toBe(true);
    expect(steps.every((s) => s.probe === null)).toBe(true);
  });

  it("离线时返回静态 Mock 状态，仅用于 UI 冒烟", () => {
    const steps = deriveSteps("NEW_PRODUCT", emptySnapshot());
    expect(steps).toHaveLength(13);
    expect(steps[0].status).toBe("completed");
    expect(steps[1].status).toBe("active");
    expect(steps[2].status).toBe("pending");
    expect(steps[0].probe).toBeNull();
  });

  it("按 project_type 取路由：COST_DOWN 是 9 步", () => {
    expect(deriveSteps("COST_DOWN", emptySnapshot())).toHaveLength(9);
    expect(deriveSteps("EXPLORATION", emptySnapshot())).toHaveLength(7);
    expect(deriveSteps("IMPROVEMENT", emptySnapshot())).toHaveLength(11);
  });

  it("合法工件点亮该步，第一个缺口成为进行中", async () => {
    const snap = await probeWorkspace();
    const steps = deriveSteps(snap.projectType, snap);
    expect(steps[0].status).toBe("completed");
    expect(steps[1].status).toBe("active");
    expect(steps[2].status).toBe("pending");
  });

  it("工件存在但结构不合规时不算完成，且该步成为进行中", async () => {
    readArtifact.mockImplementation(async (path: string) =>
      path === "project.json"
        ? utf8(validProject({ schema_version: "9.9.9" }))
        : null,
    );
    const snap = await probeWorkspace();
    const steps = deriveSteps("NEW_PRODUCT", snap);
    expect(steps[0].status).toBe("active");
    expect(steps[0].probe?.exists).toBe(true);
    expect(steps[0].probe?.valid).toBe(false);
  });

  it("只有第一个缺口是 active，其余都是 pending", async () => {
    const snap = await probeWorkspace();
    const steps = deriveSteps("NEW_PRODUCT", snap);
    expect(steps.filter((s) => s.status === "active")).toHaveLength(1);
    expect(steps.filter((s) => s.status === "completed")).toHaveLength(1);
  });
});

describe("前缀名容忍解析（记录 ID 后缀）", () => {
  /** 全部候选文件都在根目录；path 即文件名，内容按名字查表。 */
  const mockRoot = (contents: Record<string, unknown>) => {
    const names = Object.keys(contents);
    listDir.mockImplementation(async (dir: string) => {
      if (dir !== "") throw new Error("not a directory");
      return names.map((n) => entry(n));
    });
    readArtifact.mockImplementation(async (path: string) =>
      path in contents ? utf8(contents[path]) : null,
    );
  };

  it("T1 前缀名回退：challenge-<记录ID>.json 点亮步骤 3", async () => {
    const name = "challenge-HDG-NP-001-HDG-CHAL-001.json";
    mockRoot({ [name]: liteValid("challenge") });
    const snap = await probeWorkspace();
    expect(snap.probes.challenge.exists).toBe(true);
    expect(snap.probes.challenge.valid).toBe(true);
    expect(snap.probes.challenge.resolvedPath).toBe(name);
    expect(snap.probes.challenge.matches).toEqual([name]);
    // 无 project.json 时 projectType 为 null，路由回退 NEW_PRODUCT（13 步），
    // 步骤 1 是唯一缺口 → active，已合法的前缀名 challenge 是步骤 3 → completed
    const steps = deriveSteps(snap.projectType, snap);
    expect(steps[2].artifactType).toBe("challenge");
    expect(steps[2].status).toBe("completed");
  });

  it("T2 分隔符边界：experiment_design-X.json 不得点亮 experiment 步骤", async () => {
    mockRoot({
      "project.json": validProject(),
      "duty.json": liteValid("duty"),
      "challenge-A-1.json": liteValid("challenge"),
      "failure_ctq-A-1.json": liteValid("failure_ctq"),
      "test_method-A-1.json": liteValid("test_method"),
      "design_space-A-1.json": liteValid("design_space"),
      // 合法的 experiment_design 工件 —— 但名字与 experiment 只差一个 `_`
      "experiment_design-X.json": liteValid("experiment_design"),
    });
    const snap = await probeWorkspace();
    expect(snap.probes.experiment_design.valid).toBe(true);
    expect(snap.probes.experiment.exists).toBe(false);
    const steps = deriveSteps(snap.projectType, snap);
    expect(steps[6].artifactType).toBe("experiment_design");
    expect(steps[6].status).toBe("completed");
    expect(steps[7].artifactType).toBe("experiment");
    // 前 7 步齐了，experiment 是第一个缺口 → active，绝非 completed
    expect(steps[7].status).toBe("active");
  });

  it("T3 规范名优先：challenge.json 与 challenge-A-1.json 并存时选中规范名", async () => {
    mockRoot({
      "challenge.json": liteValid("challenge", { challenge_id: "C-EXACT" }),
      "challenge-A-1.json": liteValid("challenge", { challenge_id: "C-PREFIX" }),
    });
    const snap = await probeWorkspace();
    expect(snap.probes.challenge.resolvedPath).toBe("challenge.json");
    expect(snap.probes.challenge.data?.challenge_id).toBe("C-EXACT");
    expect(snap.probes.challenge.valid).toBe(true);
    expect(snap.probes.challenge.matches).toEqual(["challenge.json", "challenge-A-1.json"]);
  });

  it("T4 名称正确但内容不合 schema 不得误报完成", async () => {
    mockRoot({
      "project.json": validProject(),
      "duty.json": liteValid("duty"),
      // artifact_type 对、schema_version 对，但缺一大片必填字段
      "challenge.json": { artifact_type: "challenge", schema_version: "0.1.0" },
    });
    const snap = await probeWorkspace();
    expect(snap.probes.challenge.exists).toBe(true);
    expect(snap.probes.challenge.valid).toBe(false);
    expect(snap.probes.challenge.errors.some((e) => e.includes("缺少必填字段"))).toBe(true);
    const steps = deriveSteps(snap.projectType, snap);
    expect(steps[0].status).toBe("completed");
    expect(steps[1].status).toBe("completed");
    expect(steps[2].artifactType).toBe("challenge");
    expect(steps[2].status).toBe("active");
  });

  it("T5 代表记录确定性：多条前缀命中按文件名升序取第一个", async () => {
    // 故意把 002 放在前面，证明结果不依赖目录返回顺序
    mockRoot({
      "challenge-A-002.json": liteValid("challenge", { challenge_id: "C-002" }),
      "challenge-A-001.json": liteValid("challenge", { challenge_id: "C-001" }),
    });
    const snap = await probeWorkspace();
    expect(snap.probes.challenge.resolvedPath).toBe("challenge-A-001.json");
    expect(snap.probes.challenge.data?.challenge_id).toBe("C-001");
    expect(snap.probes.challenge.valid).toBe(true);
    expect(snap.probes.challenge.matches).toEqual(["challenge-A-001.json", "challenge-A-002.json"]);
  });
});

describe("prompt builders", () => {
  it("步骤提示词带上技能路径、真实文件名、考核标准与 PHYSICAL 要求", () => {
    const step = STAGE_CHAIN[6];
    const prompt = buildStepPrompt(step);
    expect(prompt).toContain(`skills/${step.skill}`);
    expect(prompt).toContain("experiment_design.json");
    expect(prompt).toContain(step.criteria[0]);
    expect(prompt).toContain("PHYSICAL");
    expect(prompt).toContain(step.stage);
  });

  it("门禁提示词禁止 REVISE，并提醒 schema 不允许额外字段", () => {
    const prompt = buildGatePrompt("OPTIMIZED", ["gate.json 未就绪"]);
    expect(prompt).toContain("GO / HOLD / PIVOT / KILL / FREEZE");
    expect(prompt).toContain("不得使用 REVISE");
    expect(prompt).toContain("unevaluatedProperties");
    expect(prompt).toContain("gate.json 未就绪");
  });

  it("无缺口时门禁提示词要求填写 satisfied/unsatisfied 并保持 evidence_gaps 为空", () => {
    const prompt = buildGatePrompt(null, []);
    expect(prompt).toContain("evidence_gaps 为空");
    expect(prompt).toContain("未知");
  });
});

describe("derivedCurrentStage 与 charterStage 的语义区分", () => {
  /** 全部候选文件在根目录；内容按文件名查表（与前缀名 describe 同手法）。 */
  const mockRoot = (contents: Record<string, unknown>) => {
    const names = Object.keys(contents);
    listDir.mockImplementation(async (dir: string) => {
      if (dir !== "") throw new Error("not a directory");
      return names.map((n) => entry(n));
    });
    readArtifact.mockImplementation(async (path: string) =>
      path in contents ? utf8(contents[path]) : null,
    );
  };

  it("前 7 步完成、第 8 步未完成时推导出 EXPERIMENT_DESIGNED", async () => {
    mockRoot({
      "project.json": validProject(),
      "duty.json": liteValid("duty"),
      "challenge-A-1.json": liteValid("challenge"),
      "failure_ctq-A-1.json": liteValid("failure_ctq"),
      "test_method-A-1.json": liteValid("test_method"),
      "design_space-A-1.json": liteValid("design_space"),
      "experiment_design-A-1.json": liteValid("experiment_design"),
    });
    const snap = await probeWorkspace();
    // 步骤链判定：前 7 步 completed，第 8 步（experiment）是缺口
    const steps = deriveSteps(snap.projectType, snap);
    expect(steps.slice(0, 7).every((s) => s.status === "completed")).toBe(true);
    expect(steps[7].artifactType).toBe("experiment");
    expect(steps[7].status).toBe("active");
    expect(derivedCurrentStage(snap.projectType, snap)).toBe("EXPERIMENT_DESIGNED");
  });

  it("无任何步骤完成时返回 null", async () => {
    mockRoot({
      "project.json": { artifact_type: "project", schema_version: "0.1.0" },
    });
    const snap = await probeWorkspace();
    expect(snap.projectType).toBeNull();
    expect(derivedCurrentStage(snap.projectType, snap)).toBeNull();
  });

  it("snapshot 为 null 时返回 null，不抛异常", () => {
    expect(derivedCurrentStage("NEW_PRODUCT", null)).toBeNull();
    expect(derivedCurrentStage(null, null)).toBeNull();
  });

  it("charterStage 读 project.json 自身 stage 常量，与推导阶段语义不同", async () => {
    mockRoot({
      "project.json": validProject(),
      "duty.json": liteValid("duty"),
    });
    const snap = await probeWorkspace();
    // charterStage 是 project.json 自身的 stage —— 领域包 7 个 preflight
    // 硬要求它恒为 PROJECT_DEFINED，是常量而非推进位置
    expect(snap.charterStage).toBe("PROJECT_DEFINED");
    // 推导阶段是最后一个完成步骤的契约 stage，二者可以不同
    expect(derivedCurrentStage(snap.projectType, snap)).toBe("DUTY_DEFINED");
    expect(snap.charterStage).not.toBe(derivedCurrentStage(snap.projectType, snap));
    // 门禁提示词喂的是推导阶段，而不是 charterStage 常量
    const prompt = buildGatePrompt(derivedCurrentStage(snap.projectType, snap), []);
    expect(prompt).toContain("DUTY_DEFINED");
    expect(prompt).not.toContain("PROJECT_DEFINED");
  });
});
