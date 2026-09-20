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
    expect(snap.projectStage).toBe("PROJECT_DEFINED");
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
    expect(snap.projectStage).toBeNull();
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
    // 11 个链上工件里只有这两个存在
    expect(asked).not.toContain("gate.json");
    expect(asked).not.toContain("experiment_design.json");
  });

  it("探测整条 11 步链（project_type 本身就在工件里，鸡生蛋）", async () => {
    const snap = await probeWorkspace();
    expect(Object.keys(snap.probes).sort()).toEqual(
      STAGE_CHAIN.map((c) => c.artifactType).sort(),
    );
  });
});

describe("deriveSteps", () => {
  it("首次探测尚未返回时不假装有进度：全部 pending", () => {
    const steps = deriveSteps("NEW_PRODUCT", null);
    expect(steps).toHaveLength(11);
    expect(steps.every((s) => s.status === "pending")).toBe(true);
    expect(steps.every((s) => s.probe === null)).toBe(true);
  });

  it("离线时返回静态 Mock 状态，仅用于 UI 冒烟", () => {
    const steps = deriveSteps("NEW_PRODUCT", emptySnapshot());
    expect(steps).toHaveLength(11);
    expect(steps[0].status).toBe("completed");
    expect(steps[1].status).toBe("active");
    expect(steps[2].status).toBe("pending");
    expect(steps[0].probe).toBeNull();
  });

  it("按 project_type 取路由：COST_DOWN 是 7 步", () => {
    expect(deriveSteps("COST_DOWN", emptySnapshot())).toHaveLength(7);
    expect(deriveSteps("EXPLORATION", emptySnapshot())).toHaveLength(6);
    expect(deriveSteps("IMPROVEMENT", emptySnapshot())).toHaveLength(9);
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
