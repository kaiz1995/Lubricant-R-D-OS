/**
 * 独立验收测试 —— 由审查方（非实施方）编写，用于验收「面板进度与实际进度不一致」修复。
 *
 * 与 lubricantArtifacts.test.ts 分离，理由：实施方的自测不能作为验收依据。
 *
 * 本文件的核心用例 AC-4 使用**真实会话的文件名清单**（38 个）回放：
 *   D:\HuaweiMoveData\Users\张大脸小太阳\Documents\OpenScience\sessions\2026-10-02-1949
 * 文件内容使用各类型的最小合法工件（只验命名解析，不验内容语义）。
 *
 * 验收标准见《面板进度不一致_根因分析与解决方案_V1.0.md》第六节 AC-1 ~ AC-8。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const isTauri = { value: true };
const listDir = vi.fn();
const readArtifact = vi.fn();

vi.mock("./tauri", () => ({ get isTauri() { return isTauri.value; } }));
vi.mock("./artifactFile", () => ({
  listDir: (...a: unknown[]) => listDir(...a),
  readArtifact: (...a: unknown[]) => readArtifact(...a),
}));

const { buildGatePrompt, deriveSteps, derivedCurrentStage, probeWorkspace } = await import("./lubricantArtifacts");

const entry = (name: string) => ({ path: name, name, isDir: false, size: 10, modified: 1 });
const utf8 = (obj: unknown) => ({
  path: "x", mime: "application/json", encoding: "utf8",
  data: JSON.stringify(obj), size: 10,
});

/** 所有工件共享的必填键（lubricantContracts.ts 的 COMMON_REQUIRED）。 */
const common = (artifactType: string, stage: string, idKey: string, idVal: string) => ({
  schema_version: "0.1.0",
  artifact_type: artifactType,
  project_id: "HDG-NP-001",
  stage,
  decision_question: "q", hypothesis: "h", uncertainty: "u",
  evidence: [{ evidence_id: "E-1", statement: "s", source: "x", status: "OBSERVED" }],
  decision_rule: "r", result: "res", decision: "GO", next_action: "n",
  [idKey]: idVal,
});

/** 各类型的最小合法工件（仅满足 lite 校验的必填键存在性）。 */
const MINIMAL: Record<string, (suffix: string) => Record<string, unknown>> = {
  project: () => ({
    ...common("project", "PROJECT_DEFINED", "project_id", "HDG-NP-001"),
    status: "ACTIVE", project_name: "n", project_type: "NEW_PRODUCT", product_family: "f",
    business_objective: "b", technical_objective: "t", hard_constraints: ["c"],
    target_cost: { value: 1, unit: "CNY/kg", source: "s" },
    benchmark_products: ["p"], success_criteria: ["c"], risk_class: "HIGH", owner: "o",
  }),
  duty: (s) => ({
    ...common("duty", "DUTY_DEFINED", "duty_id", `DUTY-${s}`),
    project_reference: "HDG-NP-001", duty: { x: 1 },
  }),
  challenge: (s) => ({
    ...common("challenge", "CHALLENGES_DEFINED", "challenge_id", `CHAL-${s}`),
    duty_reference: "DUTY-001", category: "CONTACT", description: "d",
    severity: "HIGH", exposure: "HIGH", lubricant_sensitivity: "HIGH",
    evidence_gap: ["g"], priority: "HIGH",
  }),
  failure_ctq: (s) => ({
    ...common("failure_ctq", "FAILURE_CTQ_DEFINED", "failure_id", `FAIL-${s}`),
    challenge_reference: "CHAL-001", failure_mode: "f", mechanism: "m",
    failure_diagnosis: "d", root_cause_hypotheses: ["假设: x"],
    lubricant_contribution: "可能", ctqs: [], test_chain: [],
  }),
  test_method: (s) => ({
    ...common("test_method", "TEST_METHODS_QUALIFIED", "method_id", `TM-${s}`),
    evidence_scope: "PHYSICAL", name: "n", standard: "ASTM D4170-16",
    target_failure_reference: "FAIL-001", role: ["C"],
    qualification_metrics: [], qualification_basis: [],
    qualification_status: "QUALIFIED",
  }),
  design_space: (s) => ({
    ...common("design_space", "DESIGN_SPACE_DEFINED", "design_space_id", `DS-${s}`),
    scope: "s", variables: [], ctq_references: [], qualified_test_method_references: [],
    constraints: [],
  }),
  experiment_design: (s) => ({
    ...common("experiment_design", "EXPERIMENT_DESIGNED", "experiment_design_id", `EXP-${s}`),
    evidence_scope: "PHYSICAL", design_space_reference: "DS-001",
    test_method_references: [], factor_references: [], design: {}, run_plan: {},
    responses: [], guardrails: [], expected_information_value: {},
  }),
  gate: (s) => ({
    ...common("gate", "VERIFIED", "gate_id", `GATE-${s}`),
    evidence_scope: "PHYSICAL", experiment_reference: "EXP-001", scope: "s",
    gate_status: "GO", satisfied_conditions: [], unsatisfied_conditions: [],
    evidence_gaps: [], risks: [],
  }),
};

/**
 * 真实会话 2026-10-02-1949 根目录的 38 个制品文件名（逐字取自磁盘）。
 * 注意：仅 project.json 与 duty.json 采用面板期望的规范名，其余 36 个带记录 ID 后缀。
 */
const REAL_SESSION_FILES: readonly string[] = [
  "project.json",
  "duty.json",
  "challenge-HDG-NP-001-HDG-CHAL-001.json",
  "challenge-HDG-NP-001-HDG-CHAL-002.json",
  "challenge-HDG-NP-001-HDG-CHAL-003.json",
  "challenge-HDG-NP-001-HDG-CHAL-004.json",
  "challenge-HDG-NP-001-HDG-CHAL-005.json",
  "failure_ctq-HDG-NP-001-HDG-FAIL-001.json",
  "failure_ctq-HDG-NP-001-HDG-FAIL-002.json",
  "failure_ctq-HDG-NP-001-HDG-FAIL-003.json",
  "failure_ctq-HDG-NP-001-HDG-FAIL-004.json",
  "failure_ctq-HDG-NP-001-HDG-FAIL-005.json",
  "test_method-HDG-NP-001-HDG-TM-001.json",
  "test_method-HDG-NP-001-HDG-TM-002.json",
  "test_method-HDG-NP-001-HDG-TM-003.json",
  "test_method-HDG-NP-001-HDG-TM-004.json",
  "test_method-HDG-NP-001-HDG-TM-005.json",
  "test_method-HDG-NP-001-HDG-TM-006.json",
  "test_method-HDG-NP-001-HDG-TM-007.json",
  "test_method-HDG-NP-001-HDG-TM-008.json",
  "test_method-HDG-NP-001-HDG-TM-009.json",
  "test_method-HDG-NP-001-HDG-TM-010.json",
  "test_method-HDG-NP-001-HDG-TM-011.json",
  "test_method-HDG-NP-001-HDG-TM-012.json",
  "test_method-HDG-NP-001-HDG-TM-013.json",
  "test_method-HDG-NP-001-HDG-TM-014.json",
  "design_space-HDG-NP-001-HDG-DS-001.json",
  "design_space-HDG-NP-001-HDG-DS-002.json",
  "design_space-HDG-NP-001-HDG-DS-003.json",
  "design_space-HDG-NP-001-HDG-DS-004.json",
  "design_space-HDG-NP-001-HDG-DS-005.json",
  "design_space-HDG-NP-001-HDG-DS-006.json",
  "design_space-HDG-NP-001-HDG-DS-007.json",
  "design_space-HDG-NP-001-HDG-DS-008.json",
  "design_space-HDG-NP-001-HDG-DS-009.json",
  "design_space-HDG-NP-001-HDG-DS-010.json",
  "design_space-HDG-NP-001-HDG-DS-011.json",
  "experiment_design-HDG-NP-001-HDG-EXP-001.json",
];

/**
 * 由文件名推断该给 readArtifact 返回哪类工件内容。
 * 关键：必须按「最长匹配」判定类型，否则 experiment_design-* 会被误判为 experiment。
 */
function payloadFor(name: string): Record<string, unknown> {
  const base = name.replace(/\.json$/, "");
  const suffix = (base.match(/-([A-Z]+-\d+)$/) ?? [])[1] ?? "001";
  const ordered = ["experiment_design", "failure_ctq", "test_method", "design_space", "challenge", "project", "duty", "gate"];
  for (const t of ordered) {
    if (base === t || base.startsWith(`${t}-`)) {
      const make = MINIMAL[t];
      if (make) return make(suffix);
    }
  }
  throw new Error(`验收夹具未覆盖的类型: ${name}`);
}

beforeEach(() => {
  isTauri.value = true;
  listDir.mockReset();
  readArtifact.mockReset();
  listDir.mockImplementation(async (dir: string) => {
    if (dir === "") return REAL_SESSION_FILES.map(entry);
    throw new Error("not a directory");
  });
  readArtifact.mockImplementation(async (path: string) => utf8(payloadFor(path)));
});

describe("AC-4 真实会话回放（核心验收）", () => {
  it("38 个真实文件名应让步骤 1~7 为 completed、8 为 active、9~13 为 pending", async () => {
    const snapshot = await probeWorkspace();
    const steps = deriveSteps("NEW_PRODUCT", snapshot);

    const report = steps.map((s) => `#${s.chainIndex} ${s.file}=${s.status}`);

    // 逐项断言，失败时输出全表便于定位
    const actual = steps.map((s) => s.status);
    const expected = [
      "completed", "completed", "completed", "completed", "completed", "completed", "completed",
      "active",
      "pending", "pending", "pending", "pending", "pending",
    ];
    expect(actual, `\n实际:\n${report.join("\n")}\n`).toEqual(expected);

    // 步骤 3 是本次缺陷的观测点，单独显式断言
    expect(steps[2].status, "步骤 3 核心技术挑战梳理 应为 completed").toBe("completed");
    expect(steps[2].probe?.exists).toBe(true);
    expect(steps[2].probe?.valid).toBe(true);
  });
});

describe("AC-5 分隔符边界安全", () => {
  it("experiment_design-*.json 不得被当作 experiment（步骤 8）的产物", async () => {
    listDir.mockImplementation(async (dir: string) => {
      if (dir === "") {
        return [entry("project.json"), entry("duty.json"), entry("experiment_design-HDG-NP-001-HDG-EXP-001.json")];
      }
      throw new Error("not a directory");
    });
    readArtifact.mockImplementation(async (path: string) => utf8(payloadFor(path)));

    const snapshot = await probeWorkspace();
    const steps = deriveSteps("NEW_PRODUCT", snapshot);

    // 步骤 7（experiment_design）应被前缀规则命中 → completed
    expect(steps[6].file).toBe("experiment_design.json");
    expect(steps[6].status, "步骤 7 应由 experiment_design-*.json 命中").toBe("completed");

    // 步骤 8（experiment）必须完全无命中：这是分隔符 `-` 约束的安全性质。
    // 若前缀匹配写成 name.startsWith(artifactType)，experiment_design-* 会误配到这里。
    expect(steps[7].file).toBe("experiment.json");
    expect(steps[7].probe?.exists, "步骤 8 不应有任何命中文件").toBe(false);
    expect(steps[7].status, "步骤 8 不得因 experiment_design-* 文件而变 completed").not.toBe("completed");
  });
});

describe("AC-6 规范名优先", () => {
  it("challenge.json 与 challenge-A-1.json 同时存在时应选中 challenge.json", async () => {
    listDir.mockImplementation(async (dir: string) => {
      if (dir === "") return [entry("challenge.json"), entry("challenge-A-1.json")];
      throw new Error("not a directory");
    });
    readArtifact.mockImplementation(async (path: string) => {
      if (path === "challenge.json") return utf8(MINIMAL.challenge("CANON"));
      if (path === "challenge-A-1.json") return utf8(MINIMAL.challenge("OTHER"));
      throw new Error("unexpected " + path);
    });

    const snapshot = await probeWorkspace();
    const probe = snapshot.probes.challenge;
    expect(probe?.resolvedPath).toBe("challenge.json");
    expect((probe?.data as Record<string, unknown>)?.challenge_id).toBe("CHAL-CANON");
  });
});

describe("AC-7 负例：名称正确但内容非法", () => {
  it("非法 challenge.json 对应步骤应为 active，不得为 completed", async () => {
    listDir.mockImplementation(async (dir: string) => {
      if (dir === "") return [entry("project.json"), entry("duty.json"), entry("challenge.json")];
      throw new Error("not a directory");
    });
    readArtifact.mockImplementation(async (path: string) => {
      if (path === "challenge.json") return utf8({ artifact_type: "challenge" }); // 缺必填键
      return utf8(payloadFor(path));
    });

    const snapshot = await probeWorkspace();
    const steps = deriveSteps("NEW_PRODUCT", snapshot);
    expect(steps[2].status).toBe("active");
    expect(steps[2].probe?.valid).toBe(false);
  });
});

describe("AC-8 门禁联动", () => {
  it("合法 gate.json 应被读出门禁状态", async () => {
    listDir.mockImplementation(async (dir: string) => {
      if (dir === "") return [entry("gate.json")];
      throw new Error("not a directory");
    });
    readArtifact.mockImplementation(async (path: string) => utf8(payloadFor(path)));

    const snapshot = await probeWorkspace();
    expect(snapshot.gateStatus).toBe("GO");
  });
});

describe("AC-10 项目当前阶段由步骤链推导（R6：project.json.stage 是常量）", () => {
  it("真实会话快照下 derivedCurrentStage 应为 EXPERIMENT_DESIGNED，而 charterStage 仍是 PROJECT_DEFINED", async () => {
    const snapshot = await probeWorkspace();

    // 领域包 7 个 preflight 硬要求 project.json.stage === "PROJECT_DEFINED"，
    // 所以它必然恒为该常量，不能当作「当前阶段」。
    expect(snapshot.charterStage).toBe("PROJECT_DEFINED");

    // 当前阶段必须从步骤链推导：最后一个 completed 步骤 = 第 7 步。
    expect(derivedCurrentStage("NEW_PRODUCT", snapshot)).toBe("EXPERIMENT_DESIGNED");

    // 两者语义不同，本用例的存在就是为了钉死这一点。
    expect(snapshot.charterStage).not.toBe(derivedCurrentStage("NEW_PRODUCT", snapshot));
  });

  it("门禁提示词里必须是推导阶段，不得是 charterStage 常量", async () => {
    const snapshot = await probeWorkspace();
    const prompt = buildGatePrompt(derivedCurrentStage("NEW_PRODUCT", snapshot), []);
    expect(prompt).toContain("EXPERIMENT_DESIGNED");
    expect(prompt).not.toContain("当前 project stage = PROJECT_DEFINED");
  });

  it("快照为 null 或 env 无磁盘能力时返回 null，且不抛异常", () => {
    expect(derivedCurrentStage("NEW_PRODUCT", null)).toBeNull();
    expect(derivedCurrentStage(null, null)).toBeNull();
  });

  it("无任何步骤完成时返回 null", async () => {
    listDir.mockImplementation(async (dir: string) => {
      if (dir === "") return [entry("project.json")];
      throw new Error("not a directory");
    });
    readArtifact.mockImplementation(async (path: string) => {
      if (path === "project.json") return utf8({ artifact_type: "project" }); // 非法 → 步骤 1 不 completed
      throw new Error("unexpected " + path);
    });

    const snapshot = await probeWorkspace();
    expect(derivedCurrentStage("NEW_PRODUCT", snapshot)).toBeNull();
  });
});
