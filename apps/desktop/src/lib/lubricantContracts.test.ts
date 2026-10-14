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
  LOOP_EDGES,
  MAX_ITERATIONS,
  ON_DEMAND_STAGES,
  PROJECT_TYPES,
  STAGE_CHAIN,
  TYPE_ROUTES,
  innerLoopStages,
  isGateStatus,
  isProjectType,
  routeFor,
  validateArtifactLite,
} from "./lubricantContracts";

describe("lubricant 契约映射", () => {
  it("STAGE_CHAIN 的 chainIndex 连续且唯一", () => {
    expect(STAGE_CHAIN.map((c) => c.chainIndex)).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
      14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
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

  it("精密脂的 11 个新 stage 按路线首次出现顺序登记在 STAGE_CHAIN 尾部（chainIndex 14..24）", () => {
    // PRECISION_GREASE_DEV 把新 stage 与油品台阶交叉排列（FAILURE_MECHANISM_DEFINED
    // → REFERENCE_MATERIAL_RESOLVED → TEST_METHODS_QUALIFIED → DESIGN_SPACE_DEFINED
    // → BENCH_RESOURCE_REGISTERED → …），所以它**不是** STAGE_CHAIN 的单调子序列：
    // STAGE_CHAIN 的顺序是登记顺序（新 stage 追加在 1..13 之后），不是该路线的执行
    // 顺序。面板步骤序列用 routeFor() 的路由顺序，与登记顺序无关。这里同时钉住
    // 「新 stage 是链尾 11 个、编号 14..24」与「登记顺序 = 路线首次出现顺序」。
    const NEW_STAGES = [
      "FAILURE_MECHANISM_DEFINED", "REFERENCE_MATERIAL_RESOLVED", "BENCH_RESOURCE_REGISTERED",
      "BATCH_PRODUCED", "SCREENING_PASSED", "BENCH_TESTED",
      "VARIANCE_ASSESSED", "NEXT_BATCH_DECIDED", "NON_INFERIORITY_PASSED",
      "PROCESS_SCALE_VALIDATED", "KNOWLEDGE_ARCHIVED",
    ];
    expect(STAGE_CHAIN.slice(-11).map((c) => c.stage)).toEqual(NEW_STAGES);
    expect(STAGE_CHAIN.slice(-11).map((c) => c.chainIndex)).toEqual(
      Array.from({ length: 11 }, (_, i) => i + 14),
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
    // 精密传动脂开发：19 步（契约 type_routes 的新第 7 类；11 个新 stage 全在链上，
    // 缺任何一条这里都会短于 19 —— 下方还有逐项对齐契约的用例）。
    expect(routeFor("PRECISION_GREASE_DEV")).toHaveLength(19);
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
    // PRECISION_GREASE_DEV is the v0.8.0 seventh: 精密传动脂开发, 19 步。
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

describe("步骤展示文案（G-2 / G-4 / G-5 / H-1 的面板侧）", () => {
  const contractOf = (stage: string) => {
    const contract = STAGE_CHAIN.find((c) => c.stage === stage);
    if (!contract) throw new Error(`STAGE_CHAIN 缺 ${stage}`);
    return contract;
  };

  it("G-4：duty 卡片说明十四维工况，两个命门维度都点名", () => {
    const duty = contractOf("DUTY_DEFINED");
    // 第一条 criteria 同时出现 motion_regime 与 torque_requirement，否则研发员
    // 按卡片备料必漏这两个命门维度，到准入才被打回。
    expect(duty.criteria[0]).toContain("十四类 duty_item 齐备");
    expect(duty.criteria[0]).toContain("motion_regime");
    expect(duty.criteria[0]).toContain("torque_requirement");
    expect(duty.description).toContain("十四维");
    // 命门条款：可以记 ASSUMED，但必须带 source 与 evidence_id
    expect(duty.criteria.some((c) => c.includes("命门维度"))).toBe(true);
  });

  it("G-5：两条 CTQ 链 criteria 逐字一致（PENDING:<method_id> 前向引用口径）", () => {
    const RULE =
      "test_chain 指向测试方法：已判定的写裸 method_id，未判定的写 PENDING:<method_id>，在方法资格确认后回填";
    const oil = contractOf("FAILURE_CTQ_DEFINED").criteria;
    const grease = contractOf("FAILURE_MECHANISM_DEFINED").criteria;
    expect(oil).toContain(RULE);
    expect(grease).toContain(RULE);
    // 旧口径（含糊表述）必须消失，两条链不得各说一套
    for (const criteria of [oil, grease]) {
      expect(criteria.some((c) => c.includes("未确认者标注待资格"))).toBe(false);
    }
  });

  it("H-1：优化步骤改成「请求登记」口径，面板全表不再承诺非劣效结论", () => {
    const optimization = contractOf("NON_INFERIORITY_PASSED");
    expect(optimization.titleZh).toBe("优化请求登记（非劣效口径）");
    expect(optimization.description).toContain("不产出候选配方或非劣效结论");
    expect(optimization.criteria.some((c) => c.includes("不写入候选或结论"))).toBe(true);
    // 验收口径：两条旧承诺串在面板源码零命中（shell grep -E 覆盖）。这里对整表
    // 展示文案做同义断言；断言参数拆开拼接，避免本行成为那条 grep 的自命中源。
    const text = STAGE_CHAIN.flatMap((c) => [c.titleZh, c.description, ...c.criteria]).join("\n");
    expect(text).not.toContain("给出" + "非劣效结论");
    expect(text).not.toContain("候选配方与" + "引擎交接");
  });

  it("H-1：知识入库第一条 criteria 用「推荐口径」，不再写「推荐配方」", () => {
    const archive = contractOf("KNOWLEDGE_ARCHIVED");
    expect(archive.criteria[0]).toContain("推荐口径");
    expect(archive.criteria[0]).not.toContain("推荐配方");
  });

  it("G-2：APPLIED 是唯一登记「产出技能 ≠ 准入技能」的步骤", () => {
    const applied = contractOf("APPLIED");
    // skill 保持准入技能不动（ROUTE_TABLE 的 24 组逐一对应断言钉死它）
    expect(applied.skill).toBe("application-validation");
    expect(applied.producerSkill).toBe("application-definition");
    expect(applied.admissionSkill).toBe("application-validation");
    // 其余步骤的产出者 = skill，不填 producerSkill（防漂移：新增登记必须显式改这里）
    expect(STAGE_CHAIN.filter((c) => c.producerSkill !== undefined).map((c) => c.stage)).toEqual([
      "APPLIED",
    ]);
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
  // 2026-10-12：next_batch.schema.json 已随包落盘，登记表清空。
  // 保留空集合与守卫本身，以便后续新增 artifactType 时仍有显式登记位。
  const SCHEMA_NOT_SHIPPED = new Set<string>();

  /** route_step.py 的 ROUTE_TABLE：24 组 (skill, stage)。 */
  const routeTable = () =>
    [...slice("ROUTE_TABLE = (", "\n)").matchAll(/\(\s*"([^"]+)",\s*"([^"]+)"\s*\)/g)].map((m) => ({
      skill: m[1],
      stage: m[2],
    }));

  it("ROUTE_TABLE 有 24 组，且 skill / stage 顺序与本模块逐一对应", () => {
    const table = routeTable();
    expect(table).toHaveLength(24);
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
    //   next_batch.json —— 连 schema 都未发货（见上一条）。
    // 显式登记；领域包补货后必须删条目（反向断言会红）。
    // 2026-10-14：bench.json 的合并工件样例（原 campaign.json 改造）已随包
    //   落盘，移出登记表。
    const noFixtureShipped = new Set([
      "process.json", "application.json",
      // 2026-10-12：next_batch.json 样例已补，移出登记表。
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
    // route_step.py 把 11 个新 stage 派给技能，技能名逐字来自 route_step.py，
    // 由上面 ROUTE_TABLE 用例强制。目录尚未随领域包落盘的显式登记在此；
    // 补货后必须删条目（反向断言会红）。
    //
    // 2026-10-12：reference-material / grease-batch / grease-screening /
    // variance-assessment 四个已随包落盘（各自带 SKILL.md 与策略模块），故从
    // 登记表移除；只剩 knowledge-archive（第 17 步知识入库）未发货。
    // 2026-10-12：knowledge-archive（第 17 步知识入库）已随包落盘，
    // 12 个新 stage 的技能目录全部就位，登记表清空。
    const skillNotShipped = new Set<string>();
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

  it("LOOP_EDGES / MAX_ITERATIONS 与 state-machine.json 的 loop_edges / max_iterations 逐项一致", () => {
    // v0.9.0 语义变更：内环 5 步变成带退出判据的循环体，回边由契约声明。
    // 契约可带文档键（note），本模块只镜像驱动行为的 from / to / kind。
    const contract = readJson<{
      loop_edges: { from: string; to: string; kind: string }[];
      max_iterations: number;
    }>("contracts/state-machine.json");
    const mapped = LOOP_EDGES.map((edge) => ({ from: edge.from, to: edge.to, kind: edge.kind }));
    expect(mapped).toEqual(
      contract.loop_edges.map((edge) => ({ from: edge.from, to: edge.to, kind: edge.kind })),
    );
    expect(MAX_ITERATIONS).toBe(contract.max_iterations);
    // 单位是「台架轮次」，且必须是正数：0 轮等于内环根本跑不起来。
    expect(Number.isInteger(MAX_ITERATIONS)).toBe(true);
    expect(MAX_ITERATIONS).toBeGreaterThan(0);
  });

  it("环边是受控回边：不出现在任何路由的相邻位上，且两端在同一条路由上", () => {
    // 环边如果出现在 TYPE_ROUTES 的相邻位上，它就不是回边而是普通前进，
    // 契约的 loop_edges 就变成了第二个真源（此处红）。
    for (const edge of LOOP_EDGES) {
      for (const [typeKey, stages] of Object.entries(TYPE_ROUTES)) {
        const from = (stages as readonly string[]).indexOf(edge.from);
        const to = (stages as readonly string[]).indexOf(edge.to);
        if (from < 0 || to < 0) {
          // 端点不同时在该路线上 = 该路线不受这条边影响（油品路线即如此）。
          expect(from < 0 && to < 0, `${typeKey} 只含 ${edge.from} 与 ${edge.to} 中的一个`).toBe(true);
          continue;
        }
        expect(to, `${typeKey}: ${edge.from} -> ${edge.to} 必须是回边（序号更小），不是相邻前进`).toBeLessThan(from);
        // 且它不得是路由自己的下一格（否则 loop_edges 就是路由的第二份拷贝）。
        expect(to, `${typeKey}: ${edge.from} -> ${edge.to} 不是路由的下一格`).not.toBe(from + 1);
      }
    }
  });

  it("环边两端只在 PRECISION_GREASE_DEV 一条路线上，且回边目标在 STAGE_CHAIN 中可解析", () => {
    const owners = LOOP_EDGES.map((edge) =>
      Object.entries(TYPE_ROUTES)
        .filter(([, stages]) => {
          const list = stages as readonly string[];
          return list.includes(edge.from) && list.includes(edge.to);
        })
        .map(([typeKey]) => typeKey),
    );
    expect(owners).toEqual([["PRECISION_GREASE_DEV"], ["PRECISION_GREASE_DEV"]]);
    // 回边目标必须是路线首（BATCH_PRODUCED）；没有生产者的 stage 面板解析不出来。
    for (const edge of LOOP_EDGES) {
      expect(edge.to).toBe("BATCH_PRODUCED");
    }
    // 6 条油品路线的内环切片为空 —— 面板只在脂路线上渲染内环读数。
    for (const typeKey of PROJECT_TYPES) {
      const loop = innerLoopStages(typeKey);
      if (typeKey === "PRECISION_GREASE_DEV") {
        expect(loop).toEqual([
          "BATCH_PRODUCED", "SCREENING_PASSED", "BENCH_TESTED", "VARIANCE_ASSESSED",
        ]);
      } else {
        expect(loop, `${typeKey} 不该有内环`).toEqual([]);
      }
    }
  });

  it("routeFor 不因环边而多出步骤（环边不是路由项，进度推导不受影响）", () => {
    // 内环的重复落盘（第二轮 screening.json）不会让步骤表变长：步骤序列仍由
    // TYPE_ROUTES 决定，环边只在路由时提供"额外合法目标"。
    const stages = routeFor("PRECISION_GREASE_DEV").map((c) => c.stage);
    expect(stages).toHaveLength(19);
    expect(new Set(stages).size).toBe(19);
    for (const edge of LOOP_EDGES) {
      expect(stages).toContain(edge.from);
      expect(stages).toContain(edge.to);
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
