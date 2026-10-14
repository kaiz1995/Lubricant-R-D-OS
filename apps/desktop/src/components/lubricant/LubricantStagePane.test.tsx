// The step and gate buttons hand a prepared prompt to the middle pane's
// composer rather than sending it — the same handoff ProvenancePanel's
// "Reproduce" uses. These checks pin that: the draft reaches the store, it
// carries the domain pack's real skill path and file name, and nothing is
// sent behind the researcher's back.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const isTauri = { value: true };
const listDir = vi.fn();
const readArtifact = vi.fn();

// Partial mocks: the render tree also reaches trafficLightsPresent / isMacUA
// (via PaneTitlebarInset) and the rest of artifactFile, so only the I/O this
// test drives is replaced.
vi.mock("@/lib/tauri", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/tauri")>()),
  get isTauri() {
    return isTauri.value;
  },
}));
vi.mock("@/lib/artifactFile", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/artifactFile")>()),
  listDir: (...a: unknown[]) => listDir(...a),
  readArtifact: (...a: unknown[]) => readArtifact(...a),
  writeWorkspaceFile: vi.fn(),
}));

const { LubricantStagePane } = await import("./LubricantStagePane");
const { useUiStore } = await import("@/lib/store");
const { useRuntimeStore } = await import("@/lib/runtime");

/** A schema-valid project.json for a NEW_PRODUCT project. */
const PROJECT = {
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
    value: 22, unit: "CNY/kg", source: "s",
    method_version: "v", material_batch: "m", formula_version: "f",
  },
  benchmark_products: ["p"], success_criteria: ["c"], risk_class: "STRATEGIC", owner: "o",
};

const entry = (name: string) => ({ path: name, name, isDir: false, size: 10, modified: 1 });

function workspaceWith(project: unknown = PROJECT) {
  listDir.mockImplementation(async (dir: string) => {
    if (dir === "") return [entry("project.json")];
    throw new Error("not a directory");
  });
  readArtifact.mockImplementation(async (path: string) =>
    path === "project.json"
      ? { path, mime: "application/json", encoding: "utf8", data: JSON.stringify(project), size: 10 }
      : null,
  );
}

const renderPane = () =>
  render(<LubricantStagePane sessionId="ses_1" sessionDir="/ws" onClose={() => {}} />);

beforeEach(() => {
  isTauri.value = true;
  listDir.mockReset();
  readArtifact.mockReset();
  useUiStore.setState({ composerDraft: null });
  workspaceWith();
});

describe("LubricantStagePane — 草稿注入", () => {
  it("点步骤按钮把提示词写进 composer 草稿，而不是直接发送", async () => {
    const sendSpy = vi.fn();
    const original = useRuntimeStore.getState().sendPrompt;
    useRuntimeStore.setState({ sendPrompt: sendSpy });

    renderPane();
    await userEvent.click(await screen.findByRole("button", { name: /在会话中推进此步骤/ }));

    const draft = useUiStore.getState().composerDraft;
    expect(draft).toBeTruthy();
    // 领域包技能路径 + 真实文件名 —— 旧版这里是虚构的 sample_profile.json 之类
    expect(draft).toContain("skills/duty-definition");
    expect(draft).toContain("duty.json");
    expect(draft).toContain("PHYSICAL");
    expect(draft).toContain("DUTY_DEFINED");
    // 不自动发送
    expect(sendSpy).not.toHaveBeenCalled();

    useRuntimeStore.setState({ sendPrompt: original });
  });

  it("草稿里带该步的准入考核标准", async () => {
    renderPane();
    await userEvent.click(await screen.findByRole("button", { name: /在会话中推进此步骤/ }));

    // duty-definition 的第一条 criteria（G-4：十四维；两个命门维度必须点名，
    // 否则研发员按卡片备料必漏 motion_regime / torque_requirement）
    const draft = useUiStore.getState().composerDraft as string;
    expect(draft).toContain("十四类 duty_item 齐备");
    expect(draft).toContain("motion_regime");
    expect(draft).toContain("torque_requirement");
  });

  it("门禁按钮注入的是 gate-review 提示词，含决议值域与 schema 约束", async () => {
    renderPane();
    await userEvent.click(await screen.findByRole("button", { name: /在会话中执行门禁终审/ }));

    const draft = useUiStore.getState().composerDraft;
    expect(draft).toContain("skills/gate-review");
    expect(draft).toContain("GO / HOLD / PIVOT / KILL / FREEZE");
    expect(draft).toContain("不得使用 REVISE");
    expect(draft).toContain("unevaluatedProperties");
  });

  it("反复点击是覆盖草稿，不累积发送", async () => {
    renderPane();
    const button = await screen.findByRole("button", { name: /在会话中推进此步骤/ });
    await userEvent.click(button);
    const first = useUiStore.getState().composerDraft;
    await userEvent.click(button);
    expect(useUiStore.getState().composerDraft).toBe(first);
  });
});

describe("LubricantStagePane — 浏览器降级", () => {
  beforeEach(() => {
    isTauri.value = false;
  });

  it("显示离线徽标，且不假装磁盘上有工件", async () => {
    renderPane();
    expect(await screen.findByText(/离线预览 · Mock 数据/)).toBeInTheDocument();
    expect(listDir).not.toHaveBeenCalled();
  });

  it("不渲染门禁签发表单，只给一句说明（写盘只在桌面版可用）", async () => {
    renderPane();
    // 不是"渲染一个禁用按钮" —— 整个签发表单都不出现
    await waitFor(() =>
      expect(screen.getByText(/磁盘写入仅在桌面版可用/)).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: /签发门禁决议/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("但提示词注入仍可用（不依赖磁盘）", async () => {
    renderPane();
    await userEvent.click(await screen.findByRole("button", { name: /在会话中推进此步骤/ }));
    expect(useUiStore.getState().composerDraft).toContain("duty.json");
  });
});

describe("LubricantStagePane — 主题色 token", () => {
  // 这里曾经写着 `bg-primary text-white`。`primary` 不在 tailwind.config.js 的色板里，
  // 于是 `bg-primary` 一个 class 都生成不出来 —— 没有背景，而白字落在浅色面板上，
  // 按钮看起来完全是空白的（鼠标悬停能看到 title，但看不到字）。正确的一对是
  // `accent` + `accent-fg`。
  const source = () =>
    readFileSync(
      join(process.cwd(), "src/components/lubricant/LubricantStagePane.tsx"),
      "utf8",
    );

  const palette = () => {
    const config = readFileSync(join(process.cwd(), "tailwind.config.js"), "utf8");
    const block = config.slice(config.indexOf("colors:"), config.indexOf("fontFamily:"));
    const keys = new Set(
      [...block.matchAll(/["']?([a-z][a-z0-9-]*)["']?\s*:/g)].map((m) => m[1]),
    );
    keys.delete("colors");
    return keys;
  };

  /** Tailwind 的尺寸/方位/结构后缀，以及 CSS 关键字 —— 都不是主题色。 */
  const KEYWORDS = new Set([
    "xs", "sm", "base", "lg", "xl",
    "center", "left", "right", "justify", "start", "end",
    "b", "t", "l", "r", "x", "y", "s", "e",
    "white", "black", "transparent", "current", "inherit", "none", "auto", "full",
  ]);

  it("只用 tailwind.config.js 里定义的颜色，不发明 token", () => {
    const known = palette();
    expect(known.size).toBeGreaterThan(8); // 色板读到了

    const unknown = new Set<string>();
    // 只查主题色会出现的工具类；带数字后缀的是标准 Tailwind 色阶（red-500 等），跳过。
    for (const m of source().matchAll(/(?:^|[\s"'`])(?:bg|text|border|from|to|via)-([a-z][a-z0-9-]*)/g)) {
      const token = m[1];
      if (/-\d+$/.test(token)) continue;
      if (token.includes("gradient")) continue;
      if (KEYWORDS.has(token) || known.has(token)) continue;
      unknown.add(token);
    }
    expect([...unknown]).toEqual([]);
  });

  it("填充按钮用 accent + accent-fg 这一对（对比度由主题保证）", () => {
    const text = source();
    // 有 bg-accent 的地方必须有 accent-fg 配它，否则就是白字/黑字撞背景
    expect(text).toContain("bg-accent text-accent-fg");
    expect(text).not.toContain("text-white");
    expect(text).not.toContain("bg-primary");
    expect(text).not.toContain("text-primary");
  });
});

describe("LubricantStagePane — 契约驱动渲染", () => {
  it("类型选择器是 7 个 domain pack 里的 project_type", async () => {
    renderPane();
    for (const label of [
      "正向开发", "性能优化", "配方降本", "客户定制", "机理探索", "生产复现", "精密脂",
    ]) {
      expect(await screen.findByRole("button", { name: label })).toBeInTheDocument();
    }
    // 旧版的两个虚构流程不应出现
    expect(screen.queryByRole("button", { name: "竞品对标" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "故障排查" })).not.toBeInTheDocument();
  });

  it("project.json 存在时锁定类型选择器为 NEW_PRODUCT", async () => {
    renderPane();
    // NEW_PRODUCT 的 12 步（PROCESS_WINDOW_DEFINED 是按需阶段，不进主链）
    await waitFor(() =>
      expect(screen.getByText(/工件链阶段步骤（12 步独立推进）/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/类型由 project\.json 的 project_type 锁定/)).toBeInTheDocument();
  });

  it("project.json 锁定为 PRECISION_GREASE_DEV 时渲染 19 步新链", async () => {
    workspaceWith({ ...PROJECT, project_type: "PRECISION_GREASE_DEV" });
    renderPane();
    // 19 步 = 契约新第 7 类路由；新 stage 必须真的出现在步骤表里
    await waitFor(() =>
      expect(screen.getByText(/工件链阶段步骤（19 步独立推进）/)).toBeInTheDocument(),
    );
    expect(screen.getByText("19 阶段")).toBeInTheDocument();
    expect(screen.getByText("知识入库（资产封存）")).toBeInTheDocument();
    expect(screen.getByText("台架资源与轮次计划")).toBeInTheDocument();
    // 步骤徽章必须按本条路线内的位置编号（1..19），不得直接用与油品链
    // 交叉的全局 chainIndex（那会渲染出 1,2,14,15,5,… 的乱序）。
    for (let n = 1; n <= 19; n += 1) {
      expect(screen.getByText(String(n)), `缺少步骤徽章 ${n}`).toBeInTheDocument();
    }
    expect(screen.queryByText("24")).not.toBeInTheDocument();
  });

  it("精密脂路线标记内环：回边两端与迭代体共 4 步，且不显示轮次时说明未开启", async () => {
    // v0.9.0：内环 5 步是带退出判据的循环体。面板只做最小呈现 —— 内环步骤
    // 打「内环」标记 + 一行迭代读数（合并工件未落盘则显示未开启，不猜）。
    workspaceWith({ ...PROJECT, project_type: "PRECISION_GREASE_DEV" });
    renderPane();
    await waitFor(() => expect(screen.getByText("内环迭代")).toBeInTheDocument());
    expect(screen.getByText(/BATCH_PRODUCED → VARIANCE_ASSESSED/)).toBeInTheDocument();
    expect(
      screen.getByText(/未开启（合并工件未落盘）· 上限 12 轮/),
    ).toBeInTheDocument();
    // BATCH_PRODUCED / SCREENING_PASSED / BENCH_TESTED / VARIANCE_ASSESSED 各一枚标记。
    const chips = screen.getAllByText("内环");
    expect(chips).toHaveLength(4);
    expect(chips.map((chip) => chip.getAttribute("title")).join("\n")).toContain(
      "SCREENING_PASSED → BATCH_PRODUCED（REWORK）",
    );
  });

  it("合并工件落盘时读盘显示当前轮次，不用猜", async () => {
    const BENCH = {
      schema_version: "0.1.0",
      artifact_type: "bench",
      project_id: "PGD-001",
      stage: "BENCH_RESOURCE_REGISTERED",
      decision_question: "q", hypothesis: "h", uncertainty: "u",
      evidence: [{ evidence_id: "E-1", statement: "s", source: "x", status: "OBSERVED" }],
      decision_rule: "r", result: "res", decision: "GO", next_action: "n",
      current_iteration: 2,
    };
    listDir.mockImplementation(async (dir: string) => {
      if (dir === "") return [entry("project.json"), entry("bench.json")];
      throw new Error("not a directory");
    });
    readArtifact.mockImplementation(async (path: string) => {
      const data = path === "project.json" ? PROJECT : path === "bench.json" ? BENCH : null;
      if (!data) return null;
      return {
        path, mime: "application/json", encoding: "utf8",
        data: JSON.stringify(
          path === "project.json" ? { ...PROJECT, project_type: "PRECISION_GREASE_DEV" } : data,
        ),
        size: 10,
      };
    });
    renderPane();
    await waitFor(() => expect(screen.getByText("第 2 / 12 轮")).toBeInTheDocument());
  });

  it("油品路线不渲染任何内环读数（环边是脂路线独占）", async () => {
    renderPane();
    await screen.findByText(/工件链阶段步骤（12 步独立推进）/);
    expect(screen.queryByText("内环迭代")).not.toBeInTheDocument();
    expect(screen.queryByText("内环")).not.toBeInTheDocument();
    expect(screen.queryByText(/BATCH_PRODUCED → VARIANCE_ASSESSED/)).not.toBeInTheDocument();
  });

  it("工件不合规时不点亮该步，并显示原因", async () => {
    workspaceWith({ ...PROJECT, artifact_type: "foo" });
    renderPane();
    // 第 1 步不应是「已完成」
    await waitFor(() => expect(screen.getByText("不合规")).toBeInTheDocument());
    expect(screen.getAllByText(/artifact_type 期望/).length).toBeGreaterThan(0);
  });

  it("工件链显示的是领域包真实文件名，不含旧版虚构名", async () => {
    renderPane();
    await screen.findByText(/工件链阶段步骤/);
    expect(screen.getByText("experiment_design.json")).toBeInTheDocument();
    for (const ghost of ["doe_design.json", "sample_profile.json", "baseline_bom.json"]) {
      expect(screen.queryByText(ghost)).not.toBeInTheDocument();
    }
  });

  it("展开步骤显示命中记录与实际 stage（G-3：同一探针服务两个语义时可分辨）", async () => {
    const { container } = renderPane();
    await screen.findByText(/工件链阶段步骤（12 步独立推进）/);
    const card = container.querySelector('[data-stage="PROJECT_DEFINED"]') as HTMLElement;
    await userEvent.click(within(card).getByText("立项与项目定义"));
    expect(within(card).getByText("命中记录：")).toBeInTheDocument();
    expect(within(card).getByText(/project\.json（stage=PROJECT_DEFINED）/)).toBeInTheDocument();
  });

  it("application 步骤展开显示准入 result（G-2：result=GAP 一眼可见）", async () => {
    const APPLICATION = {
      schema_version: "0.1.0",
      artifact_type: "application",
      project_id: "WGO-001",
      stage: "APPLIED",
      decision_question: "q", hypothesis: "h", uncertainty: "u",
      evidence: [], decision_rule: "r", result: "GAP", decision: "HOLD", next_action: "n",
      application_id: "APP-1", project_reference: "P-1", formula_reference: "F-1",
      acceptance_criteria: [], counterexamples: [], life_claim_boundary: "b",
      source: "s", evidence_id: "E-1", evidence_scope: "PHYSICAL",
    };
    listDir.mockImplementation(async (dir: string) => {
      if (dir === "") return [entry("project.json"), entry("application.json")];
      throw new Error("not a directory");
    });
    readArtifact.mockImplementation(async (path: string) => {
      const data =
        path === "project.json" ? PROJECT : path === "application.json" ? APPLICATION : null;
      if (!data) return null;
      return {
        path, mime: "application/json", encoding: "utf8",
        data: JSON.stringify(data), size: 10,
      };
    });

    const { container } = renderPane();
    await screen.findByText(/工件链阶段步骤（12 步独立推进）/);
    const card = container.querySelector('[data-stage="APPLIED"]') as HTMLElement;
    await userEvent.click(within(card).getByText("应用与整机验证（APPLIED）"));
    expect(within(card).getByText(/result=GAP/)).toBeInTheDocument();
  });
});

describe("LubricantStagePane — 精密脂三段环分组（外环 / 内环 / 收口）", () => {
  // 领域包 domains/lubricant/README.md §5.1 的环表：17 个工艺步骤 → 19 个 stage
  // （第 13 / 16 步各占两个 stage），所以面板里三段渲染为 8 / 6 / 5 步。
  // 内环是「环体 + 退出判据」：环体 4 步由契约 loop_edges 推导（打「内环」徽章），
  // MODEL_BUILT / NEXT_BATCH_DECIDED 是退出判据 —— 在同一段内，但不是环体。

  const grease = () => workspaceWith({ ...PROJECT, project_type: "PRECISION_GREASE_DEV" });

  const waitForGreaseRoute = () =>
    waitFor(() =>
      expect(screen.getByText(/工件链阶段步骤（19 步独立推进）/)).toBeInTheDocument(),
    );

  /** 步骤区按渲染顺序读出「分组标识 / 步骤 stage」标记。 */
  const renderedMarks = (container: HTMLElement): string[] =>
    [...container.querySelectorAll("[data-ring-segment], [data-stage]")].map(
      (el) => el.getAttribute("data-ring-segment") ?? el.getAttribute("data-stage") ?? "",
    );

  /** 把标记流切成 [{ id, stages }]，用于断言三段的边界与顺序。 */
  const segmentsFrom = (marks: string[]): { id: string; stages: string[] }[] => {
    const segments: { id: string; stages: string[] }[] = [];
    for (const mark of marks) {
      if (mark === "outer" || mark === "inner" || mark === "closing") {
        segments.push({ id: mark, stages: [] });
      } else {
        segments[segments.length - 1].stages.push(mark);
      }
    }
    return segments;
  };

  const cardFor = (container: HTMLElement, stage: string) =>
    container.querySelector(`[data-stage="${stage}"]`) as HTMLElement;

  /** 步骤区（含分组段头之外的所有卡片）里不允许出现滚动容器。 */
  const SCROLLER_SELECTOR =
    '[class~="overflow-y-auto"], [class~="overflow-x-auto"], [class~="overflow-auto"]';

  it("三段分组标识齐备，步数合计 = 面板声明的 19 步", async () => {
    grease();
    const { container } = renderPane();
    await waitForGreaseRoute();

    for (const label of ["外环 · 配方与工艺设计", "内环 · 台架迭代", "收口"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // 每段的 stage 数（8 + 6 + 5）与面板的 19 步自洽
    expect(screen.getByText("8 步")).toBeInTheDocument();
    expect(screen.getByText("6 步")).toBeInTheDocument();
    expect(screen.getByText("5 步")).toBeInTheDocument();
    expect(container.querySelectorAll("[data-ring-segment]")).toHaveLength(3);
    // 分组不改变步骤编号：整条路线仍是 1..19
    for (let n = 1; n <= 19; n += 1) {
      expect(screen.getByText(String(n)), `缺少步骤徽章 ${n}`).toBeInTheDocument();
    }
  });

  it("三段边界逐条对齐领域包 README §5.1 的环表，且不重不漏覆盖整条路由", async () => {
    grease();
    const { container } = renderPane();
    await waitForGreaseRoute();

    const { innerLoopStages, routeFor } = await import("@/lib/lubricantContracts");
    const route = routeFor("PRECISION_GREASE_DEV").map((c) => c.stage);

    const segments = segmentsFrom(renderedMarks(container));
    // 顺序 + 边界 + 不重不漏：三段按顺序拼接就是整条路由
    expect(segments).toEqual([
      {
        id: "outer",
        stages: [
          "PROJECT_DEFINED",
          "DUTY_DEFINED",
          "FAILURE_MECHANISM_DEFINED",
          "REFERENCE_MATERIAL_RESOLVED",
          "TEST_METHODS_QUALIFIED",
          "DESIGN_SPACE_DEFINED",
          "BENCH_RESOURCE_REGISTERED",
          "EXPERIMENT_DESIGNED",
        ],
      },
      {
        id: "inner",
        stages: [
          "BATCH_PRODUCED",
          "SCREENING_PASSED",
          "BENCH_TESTED",
          "VARIANCE_ASSESSED",
          "MODEL_BUILT",
          "NEXT_BATCH_DECIDED",
        ],
      },
      {
        id: "closing",
        stages: [
          "NON_INFERIORITY_PASSED",
          "PROCESS_SCALE_VALIDATED",
          "VERIFIED",
          "APPLIED",
          "KNOWLEDGE_ARCHIVED",
        ],
      },
    ]);
    const [outer, inner, closing] = segments.map((s) => s.stages);
    expect([...outer, ...inner, ...closing]).toEqual(route);

    // 契约 loop_edges 推导的环体（4 步）必须连续地落在「内环」段里；
    // 段内其余两步是环的退出判据，属于内环但不属于环体。
    const loopBody = innerLoopStages("PRECISION_GREASE_DEV") as readonly string[];
    expect(loopBody).toEqual([
      "BATCH_PRODUCED",
      "SCREENING_PASSED",
      "BENCH_TESTED",
      "VARIANCE_ASSESSED",
    ]);
    const indices = loopBody.map((stage) => inner.indexOf(stage));
    expect(indices.every((index) => index >= 0)).toBe(true);
    expect(indices).toEqual(indices.map((_, offset) => indices[0] + offset));
    expect(inner.filter((stage) => !loopBody.includes(stage))).toEqual([
      "MODEL_BUILT",
      "NEXT_BATCH_DECIDED",
    ]);

    // 「内环」徽章只打在环体 4 步上；退出判据两步不带章（环体 ≠ 内环段）
    for (const stage of loopBody) {
      expect(within(cardFor(container, stage)).getByText("内环")).toBeInTheDocument();
    }
    for (const stage of ["MODEL_BUILT", "NEXT_BATCH_DECIDED"]) {
      expect(within(cardFor(container, stage)).queryByText("内环")).not.toBeInTheDocument();
    }
  });

  it("内环段头显示当前轮次：未落盘时明说未开启，落盘后读合并工件 bench.json 的 current_iteration", async () => {
    grease();
    const first = renderPane();
    await waitForGreaseRoute();

    const innerHeader = () =>
      first.container.querySelector('[data-ring-segment="inner"]') as HTMLElement;
    expect(innerHeader().textContent).toContain("轮次未开启");
    expect(innerHeader().textContent).toContain("循环 N 轮");
    expect(innerHeader().textContent).not.toMatch(/第 \d+ 轮/);
    first.unmount();

    const BENCH = {
      schema_version: "0.1.0",
      artifact_type: "bench",
      project_id: "PGD-001",
      stage: "BENCH_RESOURCE_REGISTERED",
      decision_question: "q", hypothesis: "h", uncertainty: "u",
      evidence: [{ evidence_id: "E-1", statement: "s", source: "x", status: "OBSERVED" }],
      decision_rule: "r", result: "res", decision: "GO", next_action: "n",
      current_iteration: 2,
    };
    listDir.mockImplementation(async (dir: string) => {
      if (dir === "") return [entry("project.json"), entry("bench.json")];
      throw new Error("not a directory");
    });
    readArtifact.mockImplementation(async (path: string) => {
      if (path === "project.json") {
        return {
          path, mime: "application/json", encoding: "utf8", size: 10,
          data: JSON.stringify({ ...PROJECT, project_type: "PRECISION_GREASE_DEV" }),
        };
      }
      if (path === "bench.json") {
        return { path, mime: "application/json", encoding: "utf8", data: JSON.stringify(BENCH), size: 10 };
      }
      return null;
    });

    const second = renderPane();
    await waitFor(() => expect(screen.getByText("第 2 轮 / 上限 12")).toBeInTheDocument());
    // 既有的迭代读数行保留：面板顶部卡片里的「第 2 / 12 轮」仍在
    expect(screen.getByText("第 2 / 12 轮")).toBeInTheDocument();
    expect(
      (second.container.querySelector('[data-ring-segment="inner"]') as HTMLElement).textContent,
    ).toContain("第 2 轮 / 上限 12");
  });

  it("油品路线不渲染任何环分组（没有环就不分组，呈现与旧版一致）", async () => {
    const { container } = renderPane();
    await screen.findByText(/工件链阶段步骤（12 步独立推进）/);

    expect(container.querySelectorAll("[data-ring-segment]")).toHaveLength(0);
    for (const label of ["外环 · 配方与工艺设计", "内环 · 台架迭代", "收口"]) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
    expect(screen.queryByText("轮次未开启")).not.toBeInTheDocument();
    expect(container.querySelectorAll("[data-stage]")).toHaveLength(12);
  });

  it("手机宽度：段头可换行、不截断，步骤区不引入嵌套滚动", async () => {
    const oil = renderPane();
    await screen.findByText(/工件链阶段步骤（12 步独立推进）/);
    const oilScrollers = oil.container.querySelectorAll(SCROLLER_SELECTOR).length;
    oil.unmount();

    grease();
    const { container } = renderPane();
    await waitForGreaseRoute();

    const headers = [...container.querySelectorAll("[data-ring-segment]")] as HTMLElement[];
    expect(headers).toHaveLength(3);
    for (const header of headers) {
      // 窄视口下段头换行，而不是把内容顶出横向滚动条
      expect(header.className).toContain("flex-wrap");
      // 分组标识不靠 truncate / nowrap 藏文本（截断 = 手机上读不到）
      expect(header.querySelectorAll(".truncate")).toHaveLength(0);
      expect(header.querySelectorAll(".whitespace-nowrap")).toHaveLength(0);
    }
    // 步骤区自身没有滚动容器（不会出现「列表里再套一个滚动条」）
    const stepsContainer = headers[0].parentElement as HTMLElement;
    expect(stepsContainer.querySelectorAll(SCROLLER_SELECTOR)).toHaveLength(0);
    // 分组没有给面板新增滚动容器：与油品路线（平铺）数量一致
    expect(container.querySelectorAll(SCROLLER_SELECTOR)).toHaveLength(oilScrollers);
  });
});

describe("LubricantStagePane — 门禁提示词使用推导阶段", () => {
  it("门禁按钮注入的是步骤链推导阶段（DUTY_DEFINED），而非 project.json 的常量 stage", async () => {
    // project + duty 两步完成。project.json 的 stage 在领域包契约里恒为
    // PROJECT_DEFINED（charterStage），而推导出的当前阶段应是 DUTY_DEFINED。
    const DUTY = {
      schema_version: "0.1.0",
      artifact_type: "duty",
      project_id: "WGO-001",
      stage: "PROJECT_DEFINED",
      decision_question: "q", hypothesis: "h", uncertainty: "u",
      evidence: [], decision_rule: "r", result: "res", decision: "GO", next_action: "n",
      duty_id: "D-1", project_reference: "P-1", duty: {},
    };
    listDir.mockImplementation(async (dir: string) => {
      if (dir === "") return [entry("project.json"), entry("duty.json")];
      throw new Error("not a directory");
    });
    readArtifact.mockImplementation(async (path: string) => {
      if (path === "project.json") {
        return { path, mime: "application/json", encoding: "utf8", data: JSON.stringify(PROJECT), size: 10 };
      }
      if (path === "duty.json") {
        return { path, mime: "application/json", encoding: "utf8", data: JSON.stringify(DUTY), size: 10 };
      }
      return null;
    });

    renderPane();
    await userEvent.click(await screen.findByRole("button", { name: /在会话中执行门禁终审/ }));

    const draft = useUiStore.getState().composerDraft;
    expect(draft).toContain("当前 project stage = DUTY_DEFINED");
    expect(draft).not.toContain("PROJECT_DEFINED");
  });
});
