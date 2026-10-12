// The pane used to carry its own hand-written artifact file names, and 21 of
// them (sample_profile.json, baseline_bom.json, oil_degradation.json, …) had no
// schema, fixture or skill behind them anywhere in the domain pack — so a
// disk-driven progress bar could never light those steps. This module is the
// single mapping instead; these checks keep it honest.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import {
  GATE_STATUSES,
  ON_DEMAND_STAGES,
  PROJECT_TYPES,
  STAGE_CHAIN,
  TYPE_ROUTES,
  isGateStatus,
  isProjectType,
  routeFor,
  validateArtifactLite,
} from "./lubricantContracts";

describe("lubricant 契约映射", () => {
  it("STAGE_CHAIN 的 chainIndex 连续且唯一", () => {
    expect(STAGE_CHAIN.map((c) => c.chainIndex)).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
      14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25,
    ]);
  });

  it("文件名形如 x.json、无复合串；重名只限契约允许的跨路线共用工件", () => {
    const files = STAGE_CHAIN.map((c) => c.file);
    for (const f of files) {
      expect(f).toMatch(/^[a-z_]+\.json$/);
      expect(f).not.toContain("/");
    }
    // The two names the old pane got wrong.
    expect(files).toContain("experiment_design.json");
    expect(files).not.toContain("doe_design.json");

    // 一个工件文件被两个 stage 共用是允许的（跨路线复用同一种工件），但必须
    // 显式登记：调和油路线与精密脂路线各有一步产出同名工件。多出任何一条
    // 未登记的重名都要红。
    const duplicated = [...new Set(files.filter((f, i) => files.indexOf(f) !== i))].sort();
    expect(duplicated).toEqual(["failure_ctq.json", "optimization.json", "process.json"]);
    const owners = Object.fromEntries(
      duplicated.map((f) => [f, STAGE_CHAIN.filter((c) => c.file === f).map((c) => c.stage)]),
    );
    expect(owners).toEqual({
      "failure_ctq.json": ["FAILURE_CTQ_DEFINED", "FAILURE_MECHANISM_DEFINED"],
      "optimization.json": ["OPTIMIZED", "NON_INFERIORITY_PASSED"],
      "process.json": ["PROCESS_WINDOW_DEFINED", "PROCESS_SCALE_VALIDATED"],
    });

    // 共用之所以安全，是因为每条 route 内部不存在同名工件（一步一工件）；
    // 若哪天某条路线内部撞名，进度推导会把两步算成同一步 —— 这条守住它。
    const fileFor = new Map(STAGE_CHAIN.map((c) => [c.stage as string, c.file]));
    for (const [typeKey, stages] of Object.entries(TYPE_ROUTES)) {
      const perRoute = stages.map((s) => fileFor.get(s));
      expect(new Set(perRoute).size, `TYPE_ROUTES[${typeKey}] 内部出现同名工件`).toBe(perRoute.length);
    }
  });

  it("每个 project_type 的路由：stage 都在 STAGE_CHAIN 中、首步为 PROJECT_DEFINED、无重复", () => {
    const chainStages = new Set(STAGE_CHAIN.map((c) => c.stage));
    for (const [typeKey, stages] of Object.entries(TYPE_ROUTES)) {
      expect(stages[0], `${typeKey} 首步`).toBe("PROJECT_DEFINED");
      expect(new Set(stages).size, `${typeKey} 出现重复 stage`).toBe(stages.length);
      for (const stage of stages) {
        expect(chainStages.has(stage), `${typeKey} 含 STAGE_CHAIN 未定义的 ${stage}`).toBe(true);
      }
    }
  });

  it("油品 6 条路由在 STAGE_CHAIN 中保持先后顺序（唯一例外见下一条）", () => {
    const order = STAGE_CHAIN.map((c) => c.stage);
    for (const [typeKey, stages] of Object.entries(TYPE_ROUTES)) {
      if (typeKey === "PRECISION_GREASE_DEV") continue; // 见下一个用例
      let cursor = -1;
      for (const stage of stages) {
        const idx = order.indexOf(stage);
        expect(idx, `${typeKey}: ${stage} 未在 STAGE_CHAIN 或顺序颠倒`).toBeGreaterThan(cursor);
        cursor = idx;
      }
    }
  });

  it("精密脂的 12 个新 stage 按路线首次出现顺序登记在 STAGE_CHAIN 尾部（chainIndex 14..25）", () => {
    // PRECISION_GREASE_DEV 把新 stage 与油品台阶交叉排列（FAILURE_MECHANISM_DEFINED
    // → REFERENCE_MATERIAL_RESOLVED → TEST_METHODS_QUALIFIED → DESIGN_SPACE_DEFINED
    // → BENCH_RESOURCE_REGISTERED → …），所以它**不是** STAGE_CHAIN 的单调子序列：
    // STAGE_CHAIN 的顺序是登记顺序（新 stage 追加在 1..13 之后），不是该路线的执行
    // 顺序。面板步骤序列用 routeFor() 的路由顺序，与登记顺序无关。这里同时钉住
    // 「新 stage 是链尾 12 个、编号 14..25」与「登记顺序 = 路线首次出现顺序」。
    const NEW_STAGES = [
      "FAILURE_MECHANISM_DEFINED", "REFERENCE_MATERIAL_RESOLVED", "BENCH_RESOURCE_REGISTERED",
      "CAMPAIGN_OPENED", "BATCH_PRODUCED", "SCREENING_PASSED", "BENCH_TESTED",
      "VARIANCE_ASSESSED", "NEXT_BATCH_DECIDED", "NON_INFERIORITY_PASSED",
      "PROCESS_SCALE_VALIDATED", "KNOWLEDGE_ARCHIVED",
    ];
    expect(STAGE_CHAIN.slice(-12).map((c) => c.stage)).toEqual(NEW_STAGES);
    expect(STAGE_CHAIN.slice(-12).map((c) => c.chainIndex)).toEqual(
      Array.from({ length: 12 }, (_, i) => i + 14),
    );
    const firstSeen = [...new Set(TYPE_ROUTES.PRECISION_GREASE_DEV)].filter((s) =>
      (NEW_STAGES as readonly string[]).includes(s),
    );
    expect(firstSeen).toEqual(NEW_STAGES);
  });

  it("各类型步数符合领域包定义", () => {
    expect(routeFor("NEW_PRODUCT")).toHaveLength(12);
    expect(routeFor("IMPROVEMENT")).toHaveLength(10);
    expect(routeFor("COST_DOWN")).toHaveLength(8);
    expect(routeFor("CUSTOMIZATION")).toHaveLength(8);
    expect(routeFor("EXPLORATION")).toHaveLength(7);
    // 生产复现验证：8 步，配方不重新优化，且不带 VERIFIED（MODEL_BUILT 直接到 APPLIED）。
    expect(routeFor("PROCESS_ROBUSTNESS")).toHaveLength(8);
    expect(routeFor("PROCESS_ROBUSTNESS").map((c) => c.stage)).not.toContain("VERIFIED");
    // 精密传动脂开发：20 步（契约 type_routes 的新第 7 类；12 个新 stage 全在链上，
    // 缺任何一条这里都会短于 20 —— 下方还有逐项对齐契约的用例）。
    expect(routeFor("PRECISION_GREASE_DEV")).toHaveLength(20);
    expect(routeFor("PRECISION_GREASE_DEV").map((c) => c.stage)).toContain("KNOWLEDGE_ARCHIVED");
    expect(routeFor("UNKNOWN_TYPE")).toHaveLength(12);
    expect(routeFor(null)).toHaveLength(12);
  });

  it("未知 project_type 在 DEV 下告警、但仍回退 NEW_PRODUCT（返回值不变）", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      expect(routeFor("NOT_A_TYPE").map((c) => c.stage)).toEqual(
        routeFor("NEW_PRODUCT").map((c) => c.stage),
      );
      expect(warn).toHaveBeenCalledWith(expect.stringContaining("NOT_A_TYPE"));
    } finally {
      warn.mockRestore();
    }
  });

  it("null / undefined / 空串是合法回退路径，不告警", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      expect(routeFor(null)).toHaveLength(12);
      expect(routeFor(undefined)).toHaveLength(12);
      expect(routeFor("")).toHaveLength(12);
      expect(warn).not.toHaveBeenCalled();
    } finally {
      warn.mockRestore();
    }
  });

  it("路由里出现镜像未定义的 stage 时 DEV 下告警，但仍跳过、不抛错", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const route = TYPE_ROUTES.NEW_PRODUCT as unknown as string[];
    route.push("NOT_A_MIRRORED_STAGE");
    try {
      const steps = routeFor("NEW_PRODUCT");
      expect(steps).toHaveLength(12); // 行为与旧实现一致：未知 stage 被跳过
      expect(steps.map((c) => c.stage)).not.toContain("NOT_A_MIRRORED_STAGE");
      expect(warn).toHaveBeenCalledWith(expect.stringContaining("NOT_A_MIRRORED_STAGE"));
    } finally {
      route.pop();
      warn.mockRestore();
    }
  });

  it("按需阶段不出现在任何路由上（工艺窗口不进调和油主链）", () => {
    const onDemand = Object.keys(ON_DEMAND_STAGES);
    expect(onDemand).toContain("PROCESS_WINDOW_DEFINED");
    for (const stages of Object.values(TYPE_ROUTES)) {
      for (const stage of onDemand) {
        expect(stages as readonly string[]).not.toContain(stage);
      }
    }
    // 按需阶段的 skill 仍可解析，且后继由契约而非路由邻接给出。
    expect(ON_DEMAND_STAGES.PROCESS_WINDOW_DEFINED).toEqual({
      skill: "process-scale-up",
      nextStage: "VERIFIED",
    });
  });

  it("PROJECT_TYPES 覆盖全部 7 类，且拒绝非枚举值", () => {
    // The pack documents exactly seven workflows and project.schema.json
    // enumerates the same seven. CORRECTIVE_ACTION used to sit in the enum with
    // no route and no documentation — vestigial, removed 2026-09-20.
    // PRECISION_GREASE_DEV is the v0.8.0 seventh: 精密传动脂开发, 20 步。
    expect([...PROJECT_TYPES].sort()).toEqual([
      "COST_DOWN", "CUSTOMIZATION", "EXPLORATION", "IMPROVEMENT", "NEW_PRODUCT",
      "PRECISION_GREASE_DEV", "PROCESS_ROBUSTNESS",
    ]);
    expect(isProjectType("PRECISION_GREASE_DEV")).toBe(true);
    expect(isProjectType("CORRECTIVE_ACTION")).toBe(false);
    expect(isProjectType("NOT_A_TYPE")).toBe(false);
  });

  it("gate_status 值域与 state-machine.json 一致，无 REVISE", () => {
    expect([...GATE_STATUSES]).toEqual(["GO", "HOLD", "PIVOT", "KILL", "FREEZE"]);
    expect(isGateStatus("PIVOT")).toBe(true);
    expect(isGateStatus("REVISE")).toBe(false);
  });
});

describe("validateArtifactLite", () => {
  it("拒绝 V1.0 的非法 gate 草案", () => {
    const illegal = { artifact_type: "gate", stage: 1, decision: "GO", sign_off_by: "x" };
    expect(validateArtifactLite("gate", illegal).length).toBeGreaterThan(0);
  });

  it("接受领域包 fixtures/valid/gate.json 的真实形状", () => {
    const real = {
      schema_version: "0.1.0", artifact_type: "gate", project_id: "WGO-001",
      stage: "TEST_METHODS_QUALIFIED", evidence_scope: "PHYSICAL",
      decision_question: "q", hypothesis: "h", uncertainty: "u",
      evidence: [{ evidence_id: "E-1", statement: "s", source: "x", status: "OBSERVED" }],
      decision_rule: "r", result: "res", decision: "GO", next_action: "n",
      gate_id: "G-001", experiment_reference: "EXP-001", scope: "s", gate_status: "GO",
      satisfied_conditions: ["a"], unsatisfied_conditions: [], evidence_gaps: [], risks: ["r"],
    };
    expect(validateArtifactLite("gate", real)).toEqual([]);
  });

  it("报出 artifact_type 不匹配与缺失必填字段", () => {
    const errors = validateArtifactLite("duty", { artifact_type: "project", schema_version: "0.1.0" });
    expect(errors.some((e) => e.includes("artifact_type"))).toBe(true);
    expect(errors.some((e) => e.includes("缺少必填字段"))).toBe(true);
  });

  it("拒绝非对象与非 0.1.0 版本", () => {
    expect(validateArtifactLite("gate", null)).toEqual(["顶层不是 JSON 对象"]);
    expect(validateArtifactLite("gate", [1, 2])).toEqual(["顶层不是 JSON 对象"]);
    const errors = validateArtifactLite("gate", { artifact_type: "gate", schema_version: "0.2.0" });
    expect(errors.some((e) => e.includes("schema_version"))).toBe(true);
  });
});

/* ------------------------------------------------------------------ *
 * 与领域包的一致性守护
 *
 * 领域包就在本仓库内（domains/lubricant，非子模块），所以这段检查直接读它：
 * contracts/state-machine.json 是 stages / type_routes 的唯一真源。找不到时
 * 整块跳过，避免在裁剪过的 checkout 上误红。
 * ------------------------------------------------------------------ */

const PACK = [
  resolve(process.cwd(), "../../domains/lubricant"),
  resolve(process.cwd(), "domains/lubricant"),
].find((p) => existsSync(join(p, "contracts/state-machine.json")));

const describePack = PACK ? describe : describe.skip;

describePack("与 domains/lubricant 领域包的一致性", () => {
  // Every pack read happens inside a test body: `describe.skip` still runs the
  // suite callback to collect tests, so module-level reads would throw on a
  // checkout that has no domain pack.
  const read = (rel: string): string => readFileSync(join(PACK as string, rel), "utf8");
  const readJson = <T,>(rel: string): T => JSON.parse(read(rel)) as T;

  const routeSrc = () => read("skills/lubricant-rd-agent/scripts/route_step.py");
  const slice = (start: string, end: string): string => {
    const src = routeSrc();
    const from = src.indexOf(start);
    const to = src.indexOf(end, from);
    return from < 0 || to < 0 ? "" : src.slice(from, to);
  };

  /**
   * 面板不渲染的生命周期 stage：DRAFT 是草稿态，FROZEN / CLOSED 是终态。
   * 依据契约 lifecycle_stage_sets —— 三者都只映射到自身（单元素集合），不是
   * 研发工序。反向防漂移用例会核算本表与契约完全一致。
   */
  const NON_CHAIN_LIFECYCLE_STAGES = new Set(["DRAFT", "FROZEN", "CLOSED"]);

  /**
   * 尚未随领域包发货 schema 的 artifact_type。route_step.py 已把
   * NEXT_BATCH_DECIDED 派给 doe-design，但 schemas/next_batch.schema.json 还没
   * 落盘。显式登记而不是静默跳过；领域包补上后必须删条目（有用例反向核对）。
   */
  const SCHEMA_NOT_SHIPPED = new Set(["next_batch"]);

  /** route_step.py 的 ROUTE_TABLE：25 组 (skill, stage)。 */
  const routeTable = () =>
    [...slice("ROUTE_TABLE = (", "\n)").matchAll(/\(\s*"([^"]+)",\s*"([^"]+)"\s*\)/g)].map((m) => ({
      skill: m[1],
      stage: m[2],
    }));

  it("ROUTE_TABLE 有 25 组，且 skill / stage 顺序与本模块逐一对应", () => {
    const table = routeTable();
    expect(table).toHaveLength(25);
    expect(table.map((r) => r.skill)).toEqual(STAGE_CHAIN.map((c) => c.skill));
    expect(table.map((r) => r.stage)).toEqual(STAGE_CHAIN.map((c) => c.stage));
  });

  it("正向：STAGE_CHAIN 的 stage 都是 state-machine.json 的 stages（镜像 ⊆ 契约）", () => {
    const machine = readJson<{ stages: string[] }>("contracts/state-machine.json");
    const known = new Set(machine.stages);
    for (const c of STAGE_CHAIN) {
      expect(known.has(c.stage), `state-machine.json 未定义 ${c.stage}`).toBe(true);
    }
  });

  it("反向防漂移：契约 stages 除三个生命周期 stage 外，全部都在 STAGE_CHAIN 中", () => {
    // 上一条只查正向（镜像 ⊆ 契约），查不出「契约加了 stage、镜像没跟上」——
    // v0.8.0 一次加 12 个 stage，正是这一类漂移：正向断言全绿，面板却少渲染
    // 12 步。这里把反方向也钉住：契约 stage 必须要么进 STAGE_CHAIN，要么在
    // 排除表里显式登记。
    const machine = readJson<{
      stages: string[];
      lifecycle_stage_sets: Record<string, string[]>;
    }>("contracts/state-machine.json");

    // 排除表不是随手写的常量：契约里 DRAFT / FROZEN / CLOSED 各自映射到只含
    // 自身的单元素集合 —— 它们是生命周期容器（草稿态 + 两个终态），按定义不是
    // 研发工序，面板不渲染。这里从契约现算并比对，排除表一旦与契约脱节即红。
    const lifecycleOnly = Object.entries(machine.lifecycle_stage_sets)
      .filter(([status, stages]) => stages.length === 1 && stages[0] === status)
      .map(([status]) => status)
      .sort();
    expect(lifecycleOnly).toEqual([...NON_CHAIN_LIFECYCLE_STAGES].sort());

    const mirrored = new Set<string>(STAGE_CHAIN.map((c) => c.stage));
    const uncovered = machine.stages.filter(
      (s) => !mirrored.has(s) && !NON_CHAIN_LIFECYCLE_STAGES.has(s),
    );
    expect(
      uncovered,
      `STAGE_CHAIN 未覆盖契约 stage: ${uncovered.join(", ")} —— 契约/镜像已漂移`,
    ).toEqual([]);
    // 被排除的也必须恰好是这三个：契约新增的任何 stage 都不许悄悄落进排除区。
    const excluded = machine.stages.filter((s) => !mirrored.has(s)).sort();
    expect(excluded).toEqual([...NON_CHAIN_LIFECYCLE_STAGES].sort());
  });

  it("每个 artifact_type 都有 schema（未随包发货者显式登记），且其 const 与本模块一致", () => {
    for (const c of STAGE_CHAIN) {
      if (SCHEMA_NOT_SHIPPED.has(c.artifactType)) {
        expect(
          existsSync(join(PACK as string, `schemas/${c.artifactType}.schema.json`)),
          `领域包已补 ${c.artifactType}.schema.json，请从 SCHEMA_NOT_SHIPPED 移除`,
        ).toBe(false);
        continue;
      }
      const schema = readJson<{ properties: { artifact_type: { const: string } } }>(
        `schemas/${c.artifactType}.schema.json`,
      );
      expect(schema.properties.artifact_type.const).toBe(c.artifactType);
    }
  });

  it("每个 file 都存在于 fixtures/valid/（未随包发货者显式登记）", () => {
    const validFixtures = new Set(readdirSync(join(PACK as string, "fixtures/valid")));
    // 尚无 fixtures/valid 样例的链上工件：
    //   process.json / application.json —— WP 新增工件，只有 schema + skill 内
    //     构建脚本的测试覆盖；
    //   bench.json —— 台架登记由 e2e 在临时工作区现搭
    //     （tests/lubricant_e2e/test_application_bench.py）；
    //   next_batch.json —— 连 schema 都未发货（见上一条）。
    // 显式登记；领域包补货后必须删条目（反向断言会红）。
    const noFixtureShipped = new Set([
      "process.json", "application.json", "bench.json", "next_batch.json",
    ]);
    for (const c of STAGE_CHAIN) {
      if (noFixtureShipped.has(c.file)) {
        expect(
          validFixtures.has(c.file),
          `领域包已补 ${c.file} 样例，请从 noFixtureShipped 移除`,
        ).toBe(false);
        continue;
      }
      expect(validFixtures.has(c.file), `fixtures/valid 缺 ${c.file}`).toBe(true);
    }
  });

  it("每个 skill 目录都存在（未随包发货者显式登记）", () => {
    // route_step.py 把 12 个新 stage 派给技能，技能名逐字来自 route_step.py，
    // 由上面 ROUTE_TABLE 用例强制。目录尚未随领域包落盘的显式登记在此；
    // 补货后必须删条目（反向断言会红）。
    //
    // 2026-10-12：reference-material / grease-batch / grease-screening /
    // variance-assessment 四个已随包落盘（各自带 SKILL.md 与策略模块），故从
    // 登记表移除；只剩 knowledge-archive（第 17 步知识入库）未发货。
    const skillNotShipped = new Set(["knowledge-archive"]);
    const missing = new Set<string>();
    for (const c of STAGE_CHAIN) {
      if (existsSync(join(PACK as string, "skills", c.skill, "SKILL.md"))) continue;
      expect(
        skillNotShipped.has(c.skill),
        `skills/${c.skill}/SKILL.md 不存在，且未登记为「未发货」`,
      ).toBe(true);
      missing.add(c.skill);
    }
    expect([...missing].sort()).toEqual([...skillNotShipped].sort());
  });

  it("TYPE_ROUTES 与 state-machine.json 的 type_routes 逐项一致（直接读契约，防漂移）", () => {
    const routes = readJson<{ type_routes: Record<string, string[]> }>(
      "contracts/state-machine.json",
    ).type_routes;
    expect(Object.keys(routes).sort()).toEqual([...PROJECT_TYPES].sort());
    for (const [key, stages] of Object.entries(routes)) {
      expect(TYPE_ROUTES[key as keyof typeof TYPE_ROUTES], `TYPE_ROUTES[${key}]`).toEqual(stages);
    }
  });

  it("ON_DEMAND_STAGES 与 state-machine.json 的 on_demand_stages 逐项一致", () => {
    const contract = readJson<{
      on_demand_stages: Record<string, { skill: string; next_stage: string }>;
    }>("contracts/state-machine.json").on_demand_stages;
    const mapped = Object.fromEntries(
      Object.entries(ON_DEMAND_STAGES).map(([stage, spec]) => [
        stage,
        { skill: spec.skill, next_stage: spec.nextStage },
      ]),
    );
    // The contract may carry extra documentation keys (applicable_to / note);
    // this module mirrors the two that drive routing.
    expect(Object.keys(mapped).sort()).toEqual(Object.keys(contract).sort());
    for (const [stage, spec] of Object.entries(mapped)) {
      expect(spec.skill, `${stage}.skill`).toBe(contract[stage].skill);
      expect(spec.next_stage, `${stage}.next_stage`).toBe(contract[stage].next_stage);
    }
  });

  it("project.schema.json 的 project_type 枚举与 PROJECT_TYPES 一致（三处同源）", () => {
    // 三处必须同源：state-machine.json 的 type_routes、project.schema.json 的枚举、
    // 本模块的 PROJECT_TYPES。2026-09-20 之前 schema 多了一个无路由的
    // CORRECTIVE_ACTION，正是这条检查要防的漂移。
    //
    // v0.8.0：PRECISION_GREASE_DEV 已同时进入契约与 project.schema.json 的枚举，
    // 三处一致，不再有未发货缺口（下面的差集断言会守住这一点）。
    const schema = readJson<{ properties: { project_type: { enum: string[] } } }>(
      "schemas/project.schema.json",
    );
    expect([...schema.properties.project_type.enum].sort()).toEqual([...PROJECT_TYPES].sort());
    // 差集必须为空：任何一侧新增而另一侧漏改都会红。
    const actualGap = [...PROJECT_TYPES].filter(
      (t) => !schema.properties.project_type.enum.includes(t),
    );
    expect(actualGap).toEqual([]);
  });

  it("gate_statuses 与 state-machine.json 一致", () => {
    const machine = readJson<{ gate_statuses: string[] }>("contracts/state-machine.json");
    expect([...GATE_STATUSES]).toEqual(machine.gate_statuses);
  });

  it("lite 校验的必填键集合不宽于 schema 的 required", () => {
    // 反向守卫：schema 新增必填字段时这里会红，提醒同步 OWN_REQUIRED。
    for (const c of STAGE_CHAIN) {
      // 未发货 schema 的工件无法比对；只做 common 必填的 lite 校验本就是
      // 保守的一面（这里跳过不影响守卫方向：lite 只可能更窄，不会更宽）。
      if (SCHEMA_NOT_SHIPPED.has(c.artifactType)) continue;
      const schema = readJson<{ required: string[] }>(`schemas/${c.artifactType}.schema.json`);
      const full: Record<string, unknown> = {
        schema_version: "0.1.0",
        artifact_type: c.artifactType,
        project_id: "P",
        stage: "PROJECT_DEFINED",
        decision_question: "q", hypothesis: "h", uncertainty: "u",
        evidence: [], decision_rule: "r", result: "res", decision: "GO", next_action: "n",
      };
      for (const key of schema.required) full[key] = "x";
      const missing = validateArtifactLite(c.artifactType, full).filter((e) =>
        e.startsWith("缺少必填字段"),
      );
      expect(missing, `${c.artifactType} 的 OWN_REQUIRED 缺: ${missing.join(", ")}`).toEqual([]);
    }
  });

  it("project 缺 benchmark_products 但带豁免理由时通过 lite 校验", () => {
    // 2026-10-02 领域包把 benchmark_products 从 required 改为条件必填
    // （benchmark_waiver_reason + allOf if/then），lite 只做结构必填，不复刻该
    // 业务条件——合法的豁免 project 不得被判 invalid。
    const schema = readJson<{ required: string[] }>("schemas/project.schema.json");
    const obj: Record<string, unknown> = {
      schema_version: "0.1.0",
      artifact_type: "project",
      project_id: "P",
      stage: "PROJECT_DEFINED",
      decision_question: "q", hypothesis: "h", uncertainty: "u",
      evidence: [], decision_rule: "r", result: "res", decision: "GO", next_action: "n",
      benchmark_waiver_reason: "无公开对标的，客户定制工况",
    };
    for (const key of schema.required) {
      expect(key).not.toBe("benchmark_products");
      obj[key] = "x";
    }
    const errors = validateArtifactLite("project", obj);
    expect(errors.filter((e) => e.startsWith("缺少必填字段 benchmark_products"))).toEqual([]);
  });

  it("project.schema.json 仍保留 benchmark_products 与 benchmark_waiver_reason 字段", () => {
    // 防漂移：两个键可以从 required 挪走，但不得从 properties 整个删掉，
    // 否则豁免机制与正常填法都会失去落点。
    const schema = readJson<{ properties: Record<string, unknown> }>(
      "schemas/project.schema.json",
    );
    expect(schema.properties).toHaveProperty("benchmark_products");
    expect(schema.properties).toHaveProperty("benchmark_waiver_reason");
  });
});
