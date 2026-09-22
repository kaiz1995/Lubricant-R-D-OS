// The step and gate buttons hand a prepared prompt to the middle pane's
// composer rather than sending it — the same handoff ProvenancePanel's
// "Reproduce" uses. These checks pin that: the draft reaches the store, it
// carries the domain pack's real skill path and file name, and nothing is
// sent behind the researcher's back.
import { render, screen, waitFor } from "@testing-library/react";
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

    // duty-definition 的第一条 criteria
    expect(useUiStore.getState().composerDraft).toContain("七类 duty_item 齐备");
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

describe("LubricantStagePane — 契约驱动渲染", () => {
  it("类型选择器是 5 个 domain pack 里的 project_type", async () => {
    renderPane();
    for (const label of ["正向开发", "性能优化", "配方降本", "客户定制", "机理探索"]) {
      expect(await screen.findByRole("button", { name: label })).toBeInTheDocument();
    }
    // 旧版的两个虚构流程不应出现
    expect(screen.queryByRole("button", { name: "竞品对标" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "故障排查" })).not.toBeInTheDocument();
  });

  it("project.json 存在时锁定类型选择器为 NEW_PRODUCT", async () => {
    renderPane();
    // NEW_PRODUCT 的 11 步
    await waitFor(() =>
      expect(screen.getByText(/工件链阶段步骤（11 步独立推进）/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/类型由 project\.json 的 project_type 锁定/)).toBeInTheDocument();
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
});
