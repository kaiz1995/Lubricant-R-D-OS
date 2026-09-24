// The pane used to treat "批准放行" as a numeric threshold check (cost ≤ 22
// CNY/kg, micropitting ≥ 10). Three authoritative sources say otherwise:
// gate.schema.json, gate_review_policy.final_status, and preflight_gate_review.
// The gate contract only looks at evidence_scope, unresolved conditions/gaps,
// and GAP evidence. These tests pin the mirror to that contract — the artifact
// it builds was diffed field-for-field against the real build_gate_artifact.py
// (21 keys, 0 mismatches).
import { beforeEach, describe, expect, it, vi } from "vitest";

const readArtifact = vi.fn();
const writeWorkspaceFile = vi.fn();

vi.mock("./artifactFile", () => ({
  readArtifact: (...a: unknown[]) => readArtifact(...a),
  writeWorkspaceFile: (...a: unknown[]) => writeWorkspaceFile(...a),
}));

const {
  GATE_UPSTREAM,
  buildGateArtifact,
  evaluateGate,
  finalStatus,
  hasGap,
  nextGateId,
  suggestGateSubmission,
  writeGateArtifact,
} = await import("./lubricantGate");
const { emptySnapshot } = await import("./lubricantArtifacts");
type ArtifactProbe = import("./lubricantArtifacts").ArtifactProbe;
type WorkspaceSnapshot = import("./lubricantArtifacts").WorkspaceSnapshot;

const COMMON = {
  schema_version: "0.1.0",
  project_id: "WGO-001",
  decision_question: "q", hypothesis: "h", uncertainty: "u",
  evidence: [{ evidence_id: "E-1", statement: "s", source: "x", status: "OBSERVED" }],
  decision_rule: "r", result: "res", decision: "GO", next_action: "n",
};

const ARTIFACTS: Record<string, Record<string, unknown>> = {
  project: { ...COMMON, artifact_type: "project", stage: "PROJECT_DEFINED", status: "ACTIVE" },
  challenge: { ...COMMON, artifact_type: "challenge", stage: "CHALLENGES_DEFINED", challenge_id: "CH-001" },
  failure_ctq: {
    ...COMMON, artifact_type: "failure_ctq", stage: "FAILURE_CTQ_DEFINED",
    failure_id: "FM-001", challenge_reference: "CH-001",
  },
  test_method: {
    ...COMMON, artifact_type: "test_method", stage: "TEST_METHODS_QUALIFIED",
    evidence_scope: "PHYSICAL", method_id: "TM-001",
    target_failure_reference: "FM-001", qualification_status: "QUALIFIED",
  },
  design_space: {
    ...COMMON, artifact_type: "design_space", stage: "DESIGN_SPACE_DEFINED",
    design_space_id: "DS-001", qualified_test_method_references: ["TM-001"],
  },
  experiment_design: {
    ...COMMON, artifact_type: "experiment_design", stage: "EXPERIMENT_DESIGNED",
    evidence_scope: "PHYSICAL", experiment_design_id: "ED-001", design_space_reference: "DS-001",
  },
  experiment: {
    ...COMMON, artifact_type: "experiment", stage: "EXPERIMENT_RUNNING",
    evidence_scope: "PHYSICAL", experiment_id: "EXP-001", experiment_design_reference: "ED-001",
  },
  model: {
    ...COMMON, artifact_type: "model", stage: "MODEL_BUILT",
    evidence_scope: "PHYSICAL", model_id: "MODEL-001", experiment_reference: "EXP-001",
  },
  optimization: {
    ...COMMON, artifact_type: "optimization", stage: "OPTIMIZED",
    evidence_scope: "PHYSICAL", optimization_id: "OPT-001", model_reference: "MODEL-001",
  },
};

/** A live snapshot over the 9 upstream artifacts, with optional overrides. */
function snapshotWith(
  overrides: Record<string, Record<string, unknown>> = {},
  invalidTypes: readonly string[] = [],
): WorkspaceSnapshot {
  const probes: Record<string, ArtifactProbe> = {};
  for (const item of GATE_UPSTREAM) {
    const base = ARTIFACTS[item.artifactType];
    const data = { ...base, ...(overrides[item.artifactType] ?? {}) };
    probes[item.artifactType] = {
      artifactType: item.artifactType,
      file: `${item.artifactType}.json`,
      exists: true,
      valid: !invalidTypes.includes(item.artifactType),
      errors: [],
      data,
      resolvedPath: `${item.artifactType}.json`,
    };
  }
  return {
    live: true,
    probedAt: Date.now(),
    probes,
    projectType: "NEW_PRODUCT",
    projectStage: "PROJECT_DEFINED",
    gateStatus: null,
  };
}

/**
 * 零工件快照：9 个 probe 全部 exists:false / valid:false / data:null，
 * 等价于工作区里一个工件都没探测到（dataOf 只认 valid 的 probe）。
 */
function snapshotWithNoArtifacts(): WorkspaceSnapshot {
  const probes: Record<string, ArtifactProbe> = {};
  for (const item of GATE_UPSTREAM) {
    probes[item.artifactType] = {
      artifactType: item.artifactType,
      file: `${item.artifactType}.json`,
      exists: false,
      valid: false,
      errors: [],
      data: null,
      resolvedPath: null,
    };
  }
  return {
    live: true,
    probedAt: Date.now(),
    probes,
    projectType: null,
    projectStage: null,
    gateStatus: null,
  };
}

const submission = {
  gateId: "GATE-WGO-001-001",
  scope: "Stage Gate verification.",
  gateStatus: "GO" as const,
  reason: "All supplied conditions are satisfied.",
  satisfiedConditions: ["All upstream artifacts present."],
  unsatisfiedConditions: [] as string[],
  evidenceGaps: [] as string[],
  risks: ["Single-batch validation."],
  evidence: [
    { evidence_id: "E-G-001", statement: "Chain present.", source: "workspace", status: "OBSERVED" as const },
  ],
};

beforeEach(() => {
  readArtifact.mockReset();
  writeWorkspaceFile.mockReset();
  readArtifact.mockResolvedValue(null);
  writeWorkspaceFile.mockResolvedValue(undefined);
});

describe("finalStatus（镜像 gate_review_policy.final_status）", () => {
  it("SYNTHETIC 一律 HOLD，即使请求 GO 且无缺口", () => {
    expect(finalStatus(submission, "SYNTHETIC")).toBe("HOLD");
  });

  it("GO 遇到未解条件 / 缺口 / GAP 证据一律降级为 HOLD", () => {
    expect(finalStatus({ ...submission, unsatisfiedConditions: ["x"] }, "PHYSICAL")).toBe("HOLD");
    expect(finalStatus({ ...submission, evidenceGaps: ["x"] }, "PHYSICAL")).toBe("HOLD");
    expect(
      finalStatus(
        { ...submission, evidence: [{ evidence_id: "E", statement: "s", source: "x", status: "GAP" }] },
        "PHYSICAL",
      ),
    ).toBe("HOLD");
  });

  it("PHYSICAL 且无缺口时保留请求的决议", () => {
    expect(finalStatus(submission, "PHYSICAL")).toBe("GO");
    expect(finalStatus({ ...submission, gateStatus: "FREEZE" }, "PHYSICAL")).toBe("FREEZE");
  });

  it("hasGap 只认 status === GAP", () => {
    expect(hasGap([{ evidence_id: "E", statement: "s", source: "x", status: "OBSERVED" }])).toBe(false);
    expect(hasGap([{ evidence_id: "E", statement: "s", source: "x", status: "GAP" }])).toBe(true);
  });
});

describe("evaluateGate", () => {
  it("浏览器下不可签发", () => {
    const result = evaluateGate(emptySnapshot());
    expect(result.canGo).toBe(false);
    expect(result.blockers[0]).toContain("无磁盘访问");
  });

  it("完整的 9 工件 PHYSICAL 链可签发 GO", () => {
    const result = evaluateGate(snapshotWith());
    expect(result.blockers).toEqual([]);
    expect(result.canGo).toBe(true);
    expect(result.evidenceScope).toBe("PHYSICAL");
    expect(result.projectId).toBe("WGO-001");
    expect(result.experimentId).toBe("EXP-001");
    expect(result.checks.every((c) => c.ok)).toBe(true);
  });

  it("零工件时不得假通过：全部检查为 fail", () => {
    const result = evaluateGate(snapshotWithNoArtifacts());
    expect(result.checks).toHaveLength(8);
    expect(result.checks.every((c) => !c.ok)).toBe(true);
    // 空集通道必须堵死：这三项曾经靠「没有反例」假通过
    const byId = new Map(result.checks.map((c) => [c.id, c]));
    for (const id of ["upstream-stage", "upstream-decision", "chain-links"]) {
      expect(byId.get(id)?.ok).toBe(false);
    }
  });

  it("零工件时 canGo 为 false 且阻塞项覆盖 8 项", () => {
    const result = evaluateGate(snapshotWithNoArtifacts());
    expect(result.canGo).toBe(false);
    expect(result.blockers).toHaveLength(8);
  });

  it("交付物不齐时追溯关系不得判为完整", () => {
    // 只留前 5 份（缺 DOE 设计 / 实验数据 / 统计模型 / 配方优化）→ 仅 3 条引用可核对。
    // 只比对一部分就打绿勾会误导：没核对上的那几条不能算「完整」。
    const result = evaluateGate(
      snapshotWith({}, ["experiment_design", "experiment", "model", "optimization"]),
    );
    const chain = result.checks.find((c) => c.id === "chain-links");
    expect(chain?.ok).toBe(false);
    expect(chain?.detail).toContain("3 / 7 条引用可核对");
  });

  it("SYNTHETIC 链不可签发 GO", () => {
    const result = evaluateGate(
      snapshotWith({
        test_method: { evidence_scope: "SYNTHETIC" },
        experiment_design: { evidence_scope: "SYNTHETIC" },
        experiment: { evidence_scope: "SYNTHETIC" },
        model: { evidence_scope: "SYNTHETIC" },
        optimization: { evidence_scope: "SYNTHETIC" },
      }),
    );
    expect(result.evidenceScope).toBe("SYNTHETIC");
    expect(result.canGo).toBe(false);
  });

  it("上游 decision 非 GO 时被拦下", () => {
    const result = evaluateGate(snapshotWith({ model: { decision: "HOLD" } }));
    expect(result.canGo).toBe(false);
    expect(result.blockers.some((b) => b.includes("统计模型（decision = HOLD）"))).toBe(true);
  });

  it("stage 错位时被拦下", () => {
    const result = evaluateGate(snapshotWith({ experiment: { stage: "EXPERIMENT_DESIGNED" } }));
    expect(result.blockers.some((b) => b.includes("实验数据（应为 EXPERIMENT_RUNNING）"))).toBe(true);
  });

  it("project 非 ACTIVE 时被拦下", () => {
    const result = evaluateGate(snapshotWith({ project: { status: "FROZEN" } }));
    expect(result.blockers.some((b) => b.includes("已冻结（FROZEN）"))).toBe(true);
  });

  it("evidence_scope 不一致时被拦下", () => {
    const result = evaluateGate(snapshotWith({ optimization: { evidence_scope: "SYNTHETIC" } }));
    expect(result.evidenceScope).toBeNull();
    expect(result.blockers.some((b) => b.includes("全部结论基于同一批实验数据"))).toBe(true);
  });

  it("method 未资格确认时被拦下", () => {
    const result = evaluateGate(snapshotWith({ test_method: { qualification_status: "PENDING" } }));
    expect(result.blockers.some((b) => b.includes("尚未通过资格确认"))).toBe(true);
    expect(result.blockers.some((b) => b.includes("qualification_status = PENDING"))).toBe(true);
  });

  it("链路断裂时被拦下", () => {
    const result = evaluateGate(snapshotWith({ model: { experiment_reference: "EXP-999" } }));
    expect(result.blockers.some((b) => b.includes("交付物之间的追溯关系完整"))).toBe(true);
    expect(result.blockers.some((b) => b.includes("统计模型的引用与实验数据不一致"))).toBe(true);
  });

  it("阻塞项带上检查名，可直接作为未解条件", () => {
    const result = evaluateGate(snapshotWith({ project: { status: "FROZEN" } }));
    expect(result.blockers.some((b) => b.startsWith("项目处于进行中状态："))).toBe(true);
  });

  it("结构不合规的工件等同于缺失", () => {
    const result = evaluateGate(snapshotWith({}, ["optimization"]));
    expect(result.blockers.some((b) => b.includes("未就绪：配方优化"))).toBe(true);
  });
});

describe("buildGateArtifact", () => {
  it("字段来源与 build_gate_artifact.py 一致", () => {
    const evaluation = evaluateGate(snapshotWith());
    const artifact = buildGateArtifact(evaluation, submission);
    expect(artifact.artifact_type).toBe("gate");
    expect(artifact.schema_version).toBe("0.1.0");
    expect(artifact.stage).toBe("VERIFIED");
    expect(artifact.project_id).toBe("WGO-001");
    expect(artifact.evidence_scope).toBe("PHYSICAL");
    // experiment_reference 取自 experiment.json 的 experiment_id
    expect(artifact.experiment_reference).toBe("EXP-001");
    expect(artifact.gate_status).toBe("GO");
    expect(artifact.decision).toBe("GO");
    expect(artifact.risks).toEqual(["Single-batch validation."]);
  });

  it("决议措辞使用 gate_review_policy 的模板", () => {
    const artifact = buildGateArtifact(evaluateGate(snapshotWith()), submission);
    expect(artifact.decision_question).toBe(
      "Does review Gate GATE-WGO-001-001 have sufficient supplied conditions and evidence?",
    );
    expect(artifact.hypothesis).toBe(
      "GATE-WGO-001-001 records supplied review conditions without creating a Freeze or Close artifact.",
    );
    expect(artifact.result).toBe(
      "GATE-WGO-001-001 has deterministic gate disposition GO from the supplied review conditions and evidence.",
    );
    expect(artifact.next_action).toBe(
      "Advance only under the state-machine action authorized by this recorded Gate.",
    );
  });

  it("SYNTHETIC 时措辞与决议都被改成 HOLD 语义", () => {
    const snap = snapshotWith({
      test_method: { evidence_scope: "SYNTHETIC" },
      experiment_design: { evidence_scope: "SYNTHETIC" },
      experiment: { evidence_scope: "SYNTHETIC" },
      model: { evidence_scope: "SYNTHETIC" },
      optimization: { evidence_scope: "SYNTHETIC" },
    });
    const artifact = buildGateArtifact(evaluateGate(snap), submission);
    expect(artifact.gate_status).toBe("HOLD");
    expect(artifact.result).toContain("WORKFLOW_VALIDATED");
    expect(artifact.next_action).toContain("without state transition");
  });

  it("请求 GO 但有未解条件时落为 HOLD", () => {
    const artifact = buildGateArtifact(evaluateGate(snapshotWith()), {
      ...submission,
      unsatisfiedConditions: ["成本证据缺失"],
    });
    expect(artifact.gate_status).toBe("HOLD");
    expect(artifact.unsatisfied_conditions).toEqual(["成本证据缺失"]);
  });

  it("不产生 gate.schema.json 禁止的额外字段", () => {
    const artifact = buildGateArtifact(evaluateGate(snapshotWith()), submission);
    const allowed = new Set([
      "schema_version", "artifact_type", "project_id", "stage", "evidence_scope",
      "decision_question", "hypothesis", "uncertainty", "evidence", "decision_rule",
      "result", "decision", "next_action", "gate_id", "experiment_reference", "scope",
      "satisfied_conditions", "unsatisfied_conditions", "evidence_gaps", "risks", "gate_status",
    ]);
    for (const key of Object.keys(artifact)) expect(allowed.has(key)).toBe(true);
    // 签名与时间戳不能出现在工件里（unevaluatedProperties: false 会拒）
    expect(artifact).not.toHaveProperty("sign_off_by");
    expect(artifact).not.toHaveProperty("signed_at");
    expect(artifact).not.toHaveProperty("version");
  });
});

describe("nextGateId", () => {
  it("无既有工件时从 001 起", () => {
    expect(nextGateId("WGO-001", null)).toBe("GATE-WGO-001-001");
  });

  it("已存在同前缀时递增，避免静默覆盖", () => {
    expect(nextGateId("WGO-001", "GATE-WGO-001-001")).toBe("GATE-WGO-001-002");
    expect(nextGateId("WGO-001", "GATE-WGO-001-009")).toBe("GATE-WGO-001-010");
  });

  it("前缀不匹配时另起 001", () => {
    expect(nextGateId("WGO-002", "GATE-WGO-001-007")).toBe("GATE-WGO-002-001");
  });
});

describe("writeGateArtifact", () => {
  /** 内存文件系统：写入后必须能回读，否则自检逻辑测不到真实路径。 */
  let files: Map<string, string>;

  beforeEach(() => {
    files = new Map();
    readArtifact.mockImplementation(async (path: string) => {
      const data = files.get(path);
      if (data === undefined) return null;
      return { path, mime: "application/json", encoding: "utf8", data, size: data.length };
    });
    writeWorkspaceFile.mockImplementation(async (path: string, content: string) => {
      files.set(path, content);
    });
  });

  const goodArtifact = () =>
    buildGateArtifact(evaluateGate(snapshotWith()), submission) as Record<string, unknown>;

  it("拒绝写入不合规工件，且不触盘", async () => {
    await expect(
      writeGateArtifact({ artifact_type: "gate" }, { operator: "op", signedAt: "t" }),
    ).rejects.toThrow(/拒绝写入不合规/);
    expect(writeWorkspaceFile).not.toHaveBeenCalled();
  });

  it("写入 gate.json，并把签名与时间戳追加到 docs/gate-history.jsonl", async () => {
    files.set("docs/gate-history.jsonl", '{"gate_id":"GATE-WGO-001-000"}\n');

    const result = await writeGateArtifact(goodArtifact(), {
      operator: "研发项目组",
      signedAt: "2026-09-15T02:00:00Z",
    });

    expect(result.path).toBe("gate.json");
    expect(result.gateStatus).toBe("GO");
    expect(result.historyPath).toBe("docs/gate-history.jsonl");
    expect(writeWorkspaceFile.mock.calls.map((c) => c[0])).toEqual([
      "gate.json",
      "docs/gate-history.jsonl",
    ]);

    const written = JSON.parse(files.get("gate.json") as string) as Record<string, unknown>;
    expect(written.gate_status).toBe("GO");
    // 签名与时间戳不进 gate.json（schema 会拒）
    expect(written).not.toHaveProperty("sign_off_by");
    expect(written).not.toHaveProperty("signed_at");

    const history = files.get("docs/gate-history.jsonl") as string;
    expect(history).toContain('"gate_id":"GATE-WGO-001-000"'); // 旧行保留
    expect(history).toContain('"operator":"研发项目组"');
    expect(history).toContain('"signed_at":"2026-09-15T02:00:00Z"');
  });

  it("首次落盘时新建历史文件", async () => {
    await writeGateArtifact(goodArtifact(), { operator: "op", signedAt: "t" });
    const history = files.get("docs/gate-history.jsonl") as string;
    expect(history.trimEnd().split("\n")).toHaveLength(1);
  });

  it("回读自检失败时回滚到原文", async () => {
    const previous = '{"artifact_type":"gate","schema_version":"0.1.0"}';
    files.set("gate.json", previous);

    // 第一次写盘写入坏内容，模拟落盘被截断；回滚那次正常写
    let gateWrites = 0;
    writeWorkspaceFile.mockImplementation(async (path: string, content: string) => {
      if (path !== "gate.json") {
        files.set(path, content);
        return;
      }
      gateWrites += 1;
      files.set(path, gateWrites === 1 ? "{}" : content);
    });

    await expect(
      writeGateArtifact(goodArtifact(), { operator: "op", signedAt: "t" }),
    ).rejects.toThrow(/回读自检失败/);

    expect(gateWrites).toBe(2);
    expect(files.get("gate.json")).toBe(previous);
  });

  it("历史记录写失败不影响 gate.json 已落盘", async () => {
    writeWorkspaceFile.mockImplementation(async (path: string, content: string) => {
      if (path === "docs/gate-history.jsonl") throw new Error("disk full");
      files.set(path, content);
    });
    const result = await writeGateArtifact(goodArtifact(), { operator: "op", signedAt: "t" });
    expect(result.path).toBe("gate.json");
    expect(result.historyPath).toBeNull();
    expect(files.has("gate.json")).toBe(true);
  });
});

describe("suggestGateSubmission", () => {
  const draft = {
    gateId: "GATE-WGO-001-001",
    scope: "Stage Gate verification.",
    gateStatus: "GO" as const,
    reason: "ok",
    risksText: "",
  };

  it("已满足条件来自通过的检查，缺口来自上游工件", () => {
    const snap = snapshotWith();
    const evaluation = evaluateGate(snap);
    const result = suggestGateSubmission(snap, evaluation, draft);

    expect(result.satisfiedConditions).toHaveLength(evaluation.checks.length);
    expect(result.satisfiedConditions[0]).toContain("：");
    expect(result.unsatisfiedConditions).toEqual([]);
    expect(result.evidenceGaps).toEqual([]);
  });

  it("每个就绪的上游工件都进证据包", () => {
    const snap = snapshotWith();
    const result = suggestGateSubmission(snap, evaluateGate(snap), draft);
    expect(result.evidence).toHaveLength(GATE_UPSTREAM.length);
    expect(result.evidence[0].status).toBe("OBSERVED");
    expect(result.evidence[0].source).toBe("project.json");
  });

  it("非 GO 决议把阻塞项原样记为未解条件", () => {
    const snap = snapshotWith({ project: { status: "FROZEN" } });
    const result = suggestGateSubmission(snap, evaluateGate(snap), {
      ...draft,
      gateStatus: "HOLD",
    });
    expect(result.unsatisfiedConditions.length).toBeGreaterThan(0);
    expect(result.unsatisfiedConditions[0]).toContain("项目处于进行中状态");
  });

  it("留空风险时如实写「未记录残余风险」，不编造内容", () => {
    const snap = snapshotWith();
    const auto = suggestGateSubmission(snap, evaluateGate(snap), draft);
    expect(auto.risks).toEqual(["未记录残余风险"]);
  });

  it("手填风险按行切分并去空白", () => {
    const snap = snapshotWith();
    const typed = suggestGateSubmission(snap, evaluateGate(snap), {
      ...draft,
      risksText: "风险甲\n\n  风险乙  \n",
    });
    expect(typed.risks).toEqual(["风险甲", "风险乙"]);
  });

  it("上游 evidence_gaps 进证据缺口（会强制 HOLD）", () => {
    const snap = snapshotWith({ model: { evidence_gaps: ["缺少长期耐久证据"] } });
    const evaluation = evaluateGate(snap);
    const result = suggestGateSubmission(snap, evaluation, draft);
    expect(result.evidenceGaps).toEqual(["model: 缺少长期耐久证据"]);
    expect(finalStatus(result, "PHYSICAL")).toBe("HOLD");
  });
});
