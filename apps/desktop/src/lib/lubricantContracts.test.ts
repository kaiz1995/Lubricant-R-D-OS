// The pane used to carry its own hand-written artifact file names, and 21 of
// them (sample_profile.json, baseline_bom.json, oil_degradation.json, …) had no
// schema, fixture or skill behind them anywhere in the domain pack — so a
// disk-driven progress bar could never light those steps. This module is the
// single mapping instead; these checks keep it honest.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  GATE_STATUSES,
  PROJECT_TYPES,
  STAGE_CHAIN,
  TYPE_ROUTES,
  isGateStatus,
  isProjectType,
  routeFor,
  validateArtifactLite,
} from "./lubricantContracts";

describe("lubricant 契约映射", () => {
  it("11 步链的 chainIndex 连续且唯一", () => {
    expect(STAGE_CHAIN.map((c) => c.chainIndex)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
  });

  it("文件名唯一、形如 x.json、无复合串", () => {
    const files = STAGE_CHAIN.map((c) => c.file);
    expect(new Set(files).size).toBe(files.length);
    for (const f of files) {
      expect(f).toMatch(/^[a-z_]+\.json$/);
      expect(f).not.toContain("/");
    }
    // The two names the old pane got wrong.
    expect(files).toContain("experiment_design.json");
    expect(files).not.toContain("doe_design.json");
  });

  it("每个 project_type 的路由都是 11 步链的子序列，首步为 PROJECT_DEFINED", () => {
    const order = STAGE_CHAIN.map((c) => c.stage);
    for (const stages of Object.values(TYPE_ROUTES)) {
      expect(stages[0]).toBe("PROJECT_DEFINED");
      let cursor = -1;
      for (const stage of stages) {
        const idx = order.indexOf(stage);
        expect(idx).toBeGreaterThan(cursor);
        cursor = idx;
      }
    }
  });

  it("各类型步数符合领域包定义", () => {
    expect(routeFor("NEW_PRODUCT")).toHaveLength(11);
    expect(routeFor("IMPROVEMENT")).toHaveLength(9);
    expect(routeFor("COST_DOWN")).toHaveLength(7);
    expect(routeFor("CUSTOMIZATION")).toHaveLength(7);
    expect(routeFor("EXPLORATION")).toHaveLength(6);
    expect(routeFor("UNKNOWN_TYPE")).toHaveLength(11);
    expect(routeFor(null)).toHaveLength(11);
  });

  it("PROJECT_TYPES 覆盖全部 5 类，且拒绝非枚举值", () => {
    // The pack documents exactly five workflows and project.schema.json
    // enumerates the same five. CORRECTIVE_ACTION used to sit in the enum with
    // no route and no documentation — vestigial, removed 2026-09-20.
    expect([...PROJECT_TYPES].sort()).toEqual([
      "COST_DOWN", "CUSTOMIZATION", "EXPLORATION", "IMPROVEMENT", "NEW_PRODUCT",
    ]);
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
 * 领域包与 open-science 是同级目录（非子模块），所以这段检查在找不到
 * 领域包时会整块跳过 —— 换一台只有 open-science 的机器 clone 不会红。
 * 在本工作区里它会真正读到 route_step.py / schemas / fixtures / skills。
 * ------------------------------------------------------------------ */

const PACK = [
  resolve(process.cwd(), "../../../lubricant-rd-domain-pack"),
  resolve(process.cwd(), "../../lubricant-rd-domain-pack"),
].find((p) => existsSync(join(p, "contracts/state-machine.json")));

const describePack = PACK ? describe : describe.skip;

describePack("与 lubricant-rd-domain-pack 的一致性", () => {
  // Every pack read happens inside a test body: `describe.skip` still runs the
  // suite callback to collect tests, so module-level reads would throw on a
  // checkout that has no domain pack beside it.
  const read = (rel: string): string => readFileSync(join(PACK as string, rel), "utf8");
  const readJson = <T,>(rel: string): T => JSON.parse(read(rel)) as T;

  const routeSrc = () => read("skills/lubricant-rd-agent/scripts/route_step.py");
  const slice = (start: string, end: string): string => {
    const src = routeSrc();
    const from = src.indexOf(start);
    const to = src.indexOf(end, from);
    return from < 0 || to < 0 ? "" : src.slice(from, to);
  };

  /** route_step.py 的 ROUTE_TABLE：11 组 (skill, stage)。 */
  const routeTable = () =>
    [...slice("ROUTE_TABLE = (", "\n)").matchAll(/\(\s*"([^"]+)",\s*"([^"]+)"\s*\)/g)].map((m) => ({
      skill: m[1],
      stage: m[2],
    }));

  /** route_step.py 的 TYPE_ROUTES：project_type -> 有序 stage 列表。 */
  const typeRoutes = (): Record<string, string[]> => {
    const stagesFromTable = routeTable().map((r) => r.stage);
    const out: Record<string, string[]> = {};
    for (const m of slice("TYPE_ROUTES = {", "\n}").matchAll(/"(\w+)":\s*(\([^)]*\)|\w+),/g)) {
      out[m[1]] = m[2].startsWith("(")
        ? [...m[2].matchAll(/"(\w+)"/g)].map((x) => x[1])
        : stagesFromTable;
    }
    return out;
  };

  it("ROUTE_TABLE 有 11 组，且 skill / stage 顺序与本模块逐一对应", () => {
    const table = routeTable();
    expect(table).toHaveLength(11);
    expect(table.map((r) => r.skill)).toEqual(STAGE_CHAIN.map((c) => c.skill));
    expect(table.map((r) => r.stage)).toEqual(STAGE_CHAIN.map((c) => c.stage));
  });

  it("每个 artifact_type 都有 schema，且其 artifact_type const 与本模块一致", () => {
    for (const c of STAGE_CHAIN) {
      const schema = readJson<{ properties: { artifact_type: { const: string } } }>(
        `schemas/${c.artifactType}.schema.json`,
      );
      expect(schema.properties.artifact_type.const).toBe(c.artifactType);
    }
  });

  it("每个 file 都存在于 fixtures/valid/", () => {
    const validFixtures = new Set(readdirSync(join(PACK as string, "fixtures/valid")));
    for (const c of STAGE_CHAIN) {
      expect(validFixtures.has(c.file), `fixtures/valid 缺 ${c.file}`).toBe(true);
    }
  });

  it("每个 skill 目录都存在", () => {
    for (const c of STAGE_CHAIN) {
      expect(existsSync(join(PACK as string, "skills", c.skill, "SKILL.md"))).toBe(true);
    }
  });

  it("TYPE_ROUTES 与 route_step.py 完全一致", () => {
    const routes = typeRoutes();
    expect(Object.keys(routes).sort()).toEqual([...PROJECT_TYPES].sort());
    for (const [key, stages] of Object.entries(routes)) {
      expect(TYPE_ROUTES[key as keyof typeof TYPE_ROUTES], `TYPE_ROUTES[${key}]`).toEqual(stages);
    }
  });

  it("project.schema.json 的 project_type 枚举与 PROJECT_TYPES 完全一致", () => {
    // 三处必须同源：schema 枚举、route_step.py 的 TYPE_ROUTES、本模块的 PROJECT_TYPES。
    // 2026-09-20 之前 schema 多了一个无路由的 CORRECTIVE_ACTION，正是这条检查要防的漂移。
    const schema = readJson<{ properties: { project_type: { enum: string[] } } }>(
      "schemas/project.schema.json",
    );
    expect([...schema.properties.project_type.enum].sort()).toEqual([...PROJECT_TYPES].sort());
  });

  it("gate_statuses 与 state-machine.json 一致", () => {
    const machine = readJson<{ gate_statuses: string[] }>("contracts/state-machine.json");
    expect([...GATE_STATUSES]).toEqual(machine.gate_statuses);
  });

  it("lite 校验的必填键集合不宽于 schema 的 required", () => {
    // 反向守卫：schema 新增必填字段时这里会红，提醒同步 OWN_REQUIRED。
    for (const c of STAGE_CHAIN) {
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
});
