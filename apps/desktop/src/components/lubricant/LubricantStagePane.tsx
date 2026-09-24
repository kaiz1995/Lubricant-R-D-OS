/* eslint-disable i18next/no-literal-string */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Clock,
  FileCode2,
  FolderOpen,
  Layers,
  Lock,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  WifiOff,
  X,
} from "lucide-react";
import { PaneTitlebarInset } from "@/components/inspector/RightPane";
import { cn } from "@/lib/cn";
import { useRuntimeStore } from "@/lib/runtime";
import { useUiStore } from "@/lib/store";
import {
  GATE_STATUSES,
  PROJECT_TYPES,
  isGateStatus,
  routeFor,
  type GateStatus,
  type ProjectType,
} from "@/lib/lubricantContracts";
import {
  buildGatePrompt,
  buildStepPrompt,
  deriveSteps,
  probeWorkspace,
  type WorkspaceSnapshot,
} from "@/lib/lubricantArtifacts";
import {
  buildGateArtifact,
  evaluateGate,
  nextGateId,
  suggestGateSubmission,
  writeGateArtifact,
} from "@/lib/lubricantGate";

/** 轻量轮询间隔；仅在文档处于 visible 时执行。 */
const POLL_MS = 3000;

const TYPE_META: Record<ProjectType, { label: string; shortLabel: string }> = {
  NEW_PRODUCT: { label: "新产品正向开发", shortLabel: "正向开发" },
  IMPROVEMENT: { label: "已有产品性能优化", shortLabel: "性能优化" },
  COST_DOWN: { label: "降本替代", shortLabel: "配方降本" },
  CUSTOMIZATION: { label: "客户定制", shortLabel: "客户定制" },
  EXPLORATION: { label: "机理 / 平台型探索", shortLabel: "机理探索" },
};

const GATE_TONE: Record<GateStatus, string> = {
  GO: "border-emerald-500/30 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  HOLD: "border-amber-500/30 bg-amber-500/15 text-amber-600 dark:text-amber-400",
  PIVOT: "border-sky-500/30 bg-sky-500/15 text-sky-600 dark:text-sky-400",
  KILL: "border-red-500/30 bg-red-500/15 text-red-600 dark:text-red-400",
  FREEZE: "border-violet-500/30 bg-violet-500/15 text-violet-600 dark:text-violet-400",
};

function formatAge(probedAt: number, now: number): string {
  const seconds = Math.max(0, Math.round((now - probedAt) / 1000));
  if (seconds < 5) return "刚刚";
  if (seconds < 60) return `${seconds} 秒前`;
  return `${Math.round(seconds / 60)} 分钟前`;
}

export function LubricantStagePane({
  sessionId,
  sessionDir,
  onClose,
  controls,
}: {
  sessionId?: string;
  sessionDir?: string;
  onClose: () => void;
  controls?: React.ReactNode;
}) {
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null);
  const [probing, setProbing] = useState(false);
  const [selectedType, setSelectedType] = useState<ProjectType>("NEW_PRODUCT");
  const [expandedStep, setExpandedStep] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  // 门禁签发表单
  const [showChecks, setShowChecks] = useState(false);
  const [gateDraftStatus, setGateDraftStatus] = useState<GateStatus>("GO");
  const [gateDraftReason, setGateDraftReason] = useState("");
  const [gateDraftRisks, setGateDraftRisks] = useState("");
  const [signing, setSigning] = useState(false);
  const [gateSignResult, setGateSignResult] = useState<{ ok: boolean; message: string } | null>(
    null,
  );

  const running = useRuntimeStore((s) => !!(sessionId && s.runningSessions[sessionId]));

  const generation = useRef(0);
  const wasRunning = useRef(false);

  const refresh = useCallback(async () => {
    const gen = ++generation.current;
    setProbing(true);
    try {
      const next = await probeWorkspace();
      if (gen === generation.current) setSnapshot(next);
    } finally {
      if (gen === generation.current) {
        setProbing(false);
        setNow(Date.now());
      }
    }
  }, []);

  // 首次探测 + 轻量轮询 + 工作区切换时重探。后台标签页不轮询，避免空转。
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      void refresh();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh, sessionDir]);

  // 会话回合结束时立即补一次探测，不必等下一个轮询周期。
  useEffect(() => {
    if (wasRunning.current && !running) void refresh();
    wasRunning.current = running;
  }, [running, refresh]);

  const live = snapshot?.live ?? false;

  // project.json 存在时其 project_type 是权威，锁定类型选择器。
  const lockedType = snapshot?.projectType ?? null;
  const lockedProjectType = useMemo<ProjectType | null>(() => {
    if (!lockedType) return null;
    return (PROJECT_TYPES as string[]).includes(lockedType) ? (lockedType as ProjectType) : null;
  }, [lockedType]);

  const effectiveType = lockedProjectType ?? selectedType;
  const steps = useMemo(() => deriveSteps(effectiveType, snapshot), [effectiveType, snapshot]);

  const totalStages = routeFor(effectiveType).length;
  const completedCount = steps.filter((s) => s.status === "completed").length;
  const percent = totalStages ? Math.round((completedCount / totalStages) * 100) : 0;
  const activeStep = steps.find((s) => s.status === "active") ?? null;

  const gateStatus: GateStatus | null = isGateStatus(snapshot?.gateStatus)
    ? snapshot.gateStatus
    : null;
  const gateProbe = snapshot?.probes.gate ?? null;

  const openGaps = useMemo(
    () =>
      steps
        .filter((s) => s.status !== "completed")
        .map((s) => `${s.file} 未就绪`)
        .slice(0, 5),
    [steps],
  );

  // 首次拿到进行中的步骤时自动展开一次；只做一次，之后不与用户的折叠操作抢。
  const autoExpanded = useRef(false);
  useEffect(() => {
    if (autoExpanded.current || !activeStep) return;
    autoExpanded.current = true;
    setExpandedStep(activeStep.chainIndex);
  }, [activeStep]);

  /* ---- 门禁：前置校验 + 签发 ---- */

  const evaluation = useMemo(() => evaluateGate(snapshot), [snapshot]);

  // 已存在的 gate_id 即使结构不合规也读出来，避免复用同一个编号静默覆盖。
  const existingGateId = (() => {
    const value = snapshot?.probes.gate?.data?.gate_id;
    return typeof value === "string" && value.length > 0 ? value : null;
  })();
  const gateIdDraft = useMemo(
    () => nextGateId(evaluation.projectId, existingGateId),
    [evaluation.projectId, existingGateId],
  );

  const needsReason = gateDraftStatus !== "GO" && gateDraftStatus !== "HOLD";
  const gateSignBlocked = !live
    ? "需在桌面版中执行"
    : gateDraftStatus === "GO" && !evaluation.canGo
      ? "存在阻塞项，无法签发 GO；可改选 HOLD 记录未解条件"
      : needsReason && !gateDraftReason.trim()
        ? `${gateDraftStatus} 必须填写决议理由`
        : null;

  const handleSignGate = useCallback(async () => {
    if (!snapshot?.live) return;
    setSigning(true);
    setGateSignResult(null);
    try {
      const submission = suggestGateSubmission(snapshot, evaluation, {
        gateId: gateIdDraft,
        scope: `Stage Gate verification for ${evaluation.projectId ?? "project"}`,
        gateStatus: gateDraftStatus,
        reason: gateDraftReason,
        risksText: gateDraftRisks,
      });
      const artifact = buildGateArtifact(evaluation, submission);
      const result = await writeGateArtifact(artifact, {
        operator: "研发项目组",
        signedAt: new Date().toISOString(),
        note: gateDraftReason || undefined,
      });
      setGateSignResult({
        ok: true,
        message:
          `已写入 ${result.path}（gate_status = ${result.gateStatus}）` +
          (result.historyPath
            ? `，签名记录追加到 ${result.historyPath}`
            : "；但签名记录写入失败，请检查 docs/ 目录权限"),
      });
      setGateDraftReason("");
      await refresh();
    } catch (error) {
      setGateSignResult({
        ok: false,
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setSigning(false);
    }
  }, [
    snapshot,
    evaluation,
    gateIdDraft,
    gateDraftStatus,
    gateDraftReason,
    gateDraftRisks,
    refresh,
  ]);

  const injectPrompt = useCallback((prompt: string) => {
    useUiStore.getState().setComposerDraft(prompt);
  }, []);

  return (
    <div className="flex h-full w-full flex-col border-l border-border bg-surface text-text select-none overflow-hidden">
      {/* Native Inspector Header */}
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-3 bg-surface">
        <div className="flex items-center gap-2 min-w-0">
          <PaneTitlebarInset />
          <Layers size={15} strokeWidth={1.75} className="shrink-0 text-amber-500" />
          <span className="truncate text-sm font-semibold tracking-tight text-text">
            研发阶段与门禁
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={() => void refresh()}
            aria-label="重新扫描工件"
            title={live ? "重新扫描工作区工件" : "浏览器环境无磁盘访问"}
            className="rounded p-1 text-muted transition-colors hover:bg-surface-2 hover:text-text"
          >
            <RefreshCw size={13} className={probing ? "animate-spin" : undefined} />
          </button>
          {controls}
          <button
            onClick={onClose}
            aria-label="关闭面板"
            className="rounded p-1 text-muted hover:bg-surface-2 hover:text-text transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Data source strip: live workspace / still scanning / browser mock */}
      <div className="shrink-0 border-b border-border bg-surface-2/40 px-3 py-1.5">
        {snapshot === null ? (
          <div className="flex items-center gap-1.5 text-[11px] text-muted">
            <RefreshCw size={11} className="shrink-0 animate-spin" />
            <span>扫描工作区工件…</span>
          </div>
        ) : live ? (
          <div className="flex items-center gap-1.5 text-[11px] text-muted">
            <FolderOpen size={11} className="shrink-0 text-emerald-500" />
            <span className="truncate font-mono" title={sessionDir ?? undefined}>
              {sessionDir ?? "当前工作区"}
            </span>
            <span className="ml-auto shrink-0 tabular-nums">
              {formatAge(snapshot.probedAt, now)}
            </span>
          </div>
        ) : (
          <div
            className="flex items-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-700 dark:text-amber-400"
            title="磁盘探测仅在桌面版可用。请在 pnpm tauri dev 中查看真实工件状态。"
          >
            <WifiOff size={11} className="shrink-0" />
            <span className="font-medium">离线预览 · Mock 数据</span>
            <span className="truncate opacity-80">需在桌面版查看真实工件</span>
          </div>
        )}
      </div>

      {/* Development Type Selection Bar */}
      <div className="border-b border-border bg-surface-2/40 px-3 py-2 shrink-0">
        <div className="mb-1.5 flex items-center justify-between text-[11px] text-muted">
          <span className="flex items-center gap-1 font-medium">
            研发开发类型
            {lockedProjectType && <Lock size={10} className="text-emerald-500" />}
          </span>
          <span className="rounded bg-accent/10 px-1.5 py-0.2 text-[10px] font-semibold text-accent">
            {totalStages} 阶段
          </span>
        </div>
        <div className="flex gap-1 overflow-x-auto pb-0.5 no-scrollbar">
          {PROJECT_TYPES.map((typeKey) => {
            const isSelected = effectiveType === typeKey;
            const isLockedOut = lockedProjectType !== null && lockedProjectType !== typeKey;
            return (
              <button
                key={typeKey}
                disabled={isLockedOut}
                title={
                  isLockedOut
                    ? `已由 project.json 锁定为 ${TYPE_META[lockedProjectType].label}`
                    : TYPE_META[typeKey].label
                }
                onClick={() => {
                  setSelectedType(typeKey);
                  setExpandedStep(null);
                }}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium whitespace-nowrap transition-all",
                  isSelected
                    ? "bg-accent text-accent-fg shadow-sm"
                    : "border border-border/60 bg-surface text-muted hover:bg-surface-2 hover:text-text",
                  isLockedOut && "cursor-not-allowed opacity-40 hover:bg-surface",
                )}
              >
                {TYPE_META[typeKey].shortLabel}
              </button>
            );
          })}
        </div>
        {lockedProjectType && (
          <div className="mt-1.5 text-[10px] text-muted">
            类型由 project.json 的 project_type 锁定，切换需先修改该工件。
          </div>
        )}
      </div>

      {/* Main Scrollable Content */}
      <div className="flex-1 overflow-y-auto px-3.5 py-3 space-y-4 text-xs">
        {/* Overall Progress Summary Card */}
        <div className="rounded-xl border border-border bg-surface-2/60 p-3 shadow-xs space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <div className="text-[11px] text-muted">当前工序状态</div>
              <div className="text-xs font-bold text-text flex items-center gap-1.5">
                <span
                  className={cn(
                    "h-2 w-2 rounded-full",
                    activeStep ? "bg-emerald-500 animate-pulse" : "bg-muted/50",
                  )}
                />
                <span>
                  {snapshot === null
                    ? "扫描工作区中…"
                    : activeStep
                      ? `${activeStep.stage}：${activeStep.titleZh}`
                      : `工件链已全部就绪（${totalStages}/${totalStages}）`}
                </span>
              </div>
            </div>
            <div className="text-right space-y-0.5">
              <div className="text-[11px] text-muted">整体完成度</div>
              <div className="font-mono text-sm font-extrabold text-accent">
                {completedCount} / {totalStages}{" "}
                <span className="text-xs font-normal text-muted">({percent}%)</span>
              </div>
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex h-2 w-full overflow-hidden rounded-full bg-border/80">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 to-accent transition-all duration-500"
                style={{ width: `${percent}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-muted">
              <span>起步：立项与定义</span>
              <span>终点：门禁终审</span>
            </div>
          </div>

          {!live && (
            <p className="rounded-md border border-border/40 bg-surface/60 p-2 text-[10px] leading-relaxed text-muted">
              当前为离线预览：进度与状态为内置示例数据，不代表工作区真实工件。
            </p>
          )}
        </div>

        {/* Gate Decision Banner — 判定与签发 */}
        <div className="rounded-xl border border-border bg-surface-2/40 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 font-semibold text-text text-xs">
              <ShieldCheck size={14} className={gateStatus ? "text-emerald-500" : "text-muted"} />
              <span>门禁决议（Gate Review）</span>
            </div>
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] font-extrabold tracking-wide",
                gateStatus ? GATE_TONE[gateStatus] : "border-border bg-surface text-muted",
              )}
            >
              {gateStatus ?? "未签署"}
            </span>
          </div>

          {gateStatus && (
            <p className="rounded-md border border-border/40 bg-surface/60 p-2 text-[11px] leading-relaxed text-muted">
              gate.json 已落盘，gate_status = {gateStatus}
              {gateProbe?.resolvedPath ? `（${gateProbe.resolvedPath}）` : ""}。
            </p>
          )}

          {gateProbe?.exists && !gateProbe.valid && (
            <ul className="space-y-0.5 rounded-md border border-red-500/30 bg-red-500/5 p-2">
              {gateProbe.errors.slice(0, 3).map((e) => (
                <li
                  key={e}
                  className="flex items-start gap-1 text-[10px] text-red-600 dark:text-red-400"
                >
                  <AlertCircle size={10} className="mt-0.5 shrink-0" />
                  <span>{e}</span>
                </li>
              ))}
            </ul>
          )}

          {/* 前置校验结果 */}
          <div className="space-y-1">
            <button
              onClick={() => setShowChecks((v) => !v)}
              className="flex w-full items-center justify-between rounded-md border border-border/50 bg-surface/60 px-2 py-1.5 text-[11px] transition-colors hover:bg-surface-2"
            >
              <span className="flex items-center gap-1.5">
                {evaluation.canGo ? (
                  <CheckCircle2 size={12} className="text-emerald-500" />
                ) : (
                  <AlertCircle size={12} className="text-amber-500" />
                )}
                <span className="font-medium text-text">
                  放行前检查：{evaluation.checks.filter((c) => c.ok).length} /{" "}
                  {evaluation.checks.length} 项通过
                </span>
              </span>
              {showChecks ? (
                <ChevronDown size={13} className="text-muted" />
              ) : (
                <ChevronRight size={13} className="text-muted" />
              )}
            </button>

            {showChecks && (
              <ul className="space-y-1 rounded-md border border-border/40 bg-surface/40 p-2">
                {evaluation.checks.map((check) => (
                  <li key={check.id} className="flex items-start gap-1.5 text-[10px]">
                    {check.ok ? (
                      <CheckCircle2 size={11} className="mt-0.5 shrink-0 text-emerald-500" />
                    ) : (
                      <AlertCircle size={11} className="mt-0.5 shrink-0 text-red-500" />
                    )}
                    <span className="text-text/90">
                      <span className="font-medium">{check.label}</span>
                      <span className="text-muted"> — {check.detail}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {!live ? (
            <p className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-[10px] leading-relaxed text-amber-700 dark:text-amber-400">
              磁盘写入仅在桌面版可用，浏览器下无法签发门禁决议。
            </p>
          ) : (
            <div className="space-y-2 rounded-md border border-border/50 bg-surface/60 p-2">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-muted">决议</span>
                <select
                  value={gateDraftStatus}
                  onChange={(e) => setGateDraftStatus(e.target.value as GateStatus)}
                  className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[11px] text-text"
                >
                  {GATE_STATUSES.map((status) => (
                    <option key={status} value={status}>
                      {status}
                    </option>
                  ))}
                </select>
                <span className="ml-auto font-mono text-[10px] text-muted">{gateIdDraft}</span>
              </div>

              <input
                value={gateDraftReason}
                onChange={(e) => setGateDraftReason(e.target.value)}
                placeholder="决议理由（PIVOT / KILL / FREEZE 必填）"
                className="w-full rounded border border-border bg-surface px-2 py-1 text-[11px] text-text placeholder:text-muted"
              />

              <textarea
                value={gateDraftRisks}
                onChange={(e) => setGateDraftRisks(e.target.value)}
                rows={2}
                placeholder="残余风险，每行一条（留空则汇总上游工件的 risks）"
                className="w-full resize-y rounded border border-border bg-surface px-2 py-1 text-[11px] text-text placeholder:text-muted"
              />

              <button
                onClick={() => void handleSignGate()}
                disabled={signing || gateSignBlocked !== null}
                title={gateSignBlocked ?? "写入 gate.json 并把签名追加到 docs/gate-history.jsonl"}
                className="flex w-full items-center justify-center gap-1.5 rounded-md bg-accent px-2.5 py-1.5 text-xs font-medium text-accent-fg transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {signing ? (
                  <RefreshCw size={12} className="animate-spin" />
                ) : (
                  <ShieldCheck size={12} />
                )}
                <span>签发门禁决议</span>
              </button>

              {gateSignBlocked && (
                <p className="text-[10px] leading-relaxed text-amber-600 dark:text-amber-400">
                  {gateSignBlocked}
                </p>
              )}
            </div>
          )}

          {gateSignResult && (
            <p
              className={cn(
                "rounded-md border p-2 text-[10px] leading-relaxed",
                gateSignResult.ok
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                  : "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400",
              )}
            >
              {gateSignResult.message}
            </p>
          )}

          <div className="flex items-center justify-end gap-1.5">
            <button
              onClick={() =>
                injectPrompt(buildGatePrompt(snapshot?.projectStage ?? null, openGaps))
              }
              className="flex items-center gap-1 rounded bg-surface px-2 py-0.5 text-[10px] font-medium text-accent transition-colors hover:bg-surface-2"
            >
              <Sparkles size={10} />
              <span>在会话中执行门禁终审</span>
            </button>
          </div>
        </div>

        {/* Dedicated Steps Section */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-xs tracking-tight text-text">
              工件链阶段步骤（{steps.length} 步独立推进）
            </span>
            <span className="text-[11px] text-muted">点击展开步骤细则</span>
          </div>

          <div className="space-y-2">
            {steps.map((step) => {
              const isExpanded = expandedStep === step.chainIndex;
              const isCompleted = step.status === "completed";
              const isActive = step.status === "active";
              const invalid = !!step.probe?.exists && !step.probe.valid;

              return (
                <div
                  key={step.chainIndex}
                  className={cn(
                    "overflow-hidden rounded-xl border transition-all duration-150",
                    isActive
                      ? "border-accent/60 bg-accent/5 shadow-xs"
                      : isCompleted
                        ? "border-emerald-500/30 bg-surface/90"
                        : "border-border/60 bg-surface/50 opacity-80 hover:opacity-100",
                  )}
                >
                  <div
                    onClick={() => setExpandedStep(isExpanded ? null : step.chainIndex)}
                    className="flex cursor-pointer select-none items-center justify-between p-2.5 hover:bg-surface-2/40"
                  >
                    <div className="flex min-w-0 items-center gap-2.5">
                      <div className="shrink-0">
                        {invalid ? (
                          <AlertCircle size={16} className="text-red-500" />
                        ) : isCompleted ? (
                          <CheckCircle2 size={16} className="text-emerald-500" />
                        ) : isActive ? (
                          <div className="relative flex h-4 w-4 items-center justify-center">
                            <span className="absolute h-full w-full rounded-full bg-accent/20 animate-ping" />
                            <Clock size={15} className="relative z-10 text-accent" />
                          </div>
                        ) : (
                          <Circle size={15} className="text-muted/60" />
                        )}
                      </div>

                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={cn(
                              "rounded px-1 py-0.2 font-mono text-[10px] font-bold",
                              isActive
                                ? "bg-accent text-accent-fg"
                                : isCompleted
                                  ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                                  : "bg-surface-2 text-muted",
                            )}
                          >
                            {step.chainIndex}
                          </span>
                          <span className="truncate text-xs font-semibold text-text">
                            {step.titleZh}
                          </span>
                        </div>
                        <div className="mt-0.5 flex items-center gap-1 text-[11px] text-muted">
                          <FileCode2 size={11} className="shrink-0 text-accent/70" />
                          <span className="truncate font-mono text-[10px]">{step.file}</span>
                        </div>
                      </div>
                    </div>

                    <div className="ml-2 flex shrink-0 items-center gap-1.5">
                      <span
                        className={cn(
                          "rounded-full px-1.5 py-0.2 text-[10px] font-medium",
                          invalid
                            ? "bg-red-500/10 text-red-600 dark:text-red-400"
                            : isCompleted
                              ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                              : isActive
                                ? "bg-accent/10 font-bold text-accent"
                                : "bg-surface-2 text-muted",
                        )}
                      >
                        {invalid
                          ? "不合规"
                          : isCompleted
                            ? "已完成"
                            : isActive
                              ? "进行中"
                              : "待推进"}
                      </span>
                      {isExpanded ? (
                        <ChevronDown size={14} className="text-muted" />
                      ) : (
                        <ChevronRight size={14} className="text-muted" />
                      )}
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="space-y-2.5 border-t border-border/50 bg-surface-2/20 p-3 text-xs">
                      <div>
                        <div className="text-[11px] font-medium text-muted">阶段目标：</div>
                        <div className="mt-0.5 text-[11px] leading-relaxed text-text">
                          {step.description}
                        </div>
                      </div>

                      <div>
                        <div className="text-[11px] font-medium text-muted">
                          准入考核标准（Criteria）：
                        </div>
                        <ul className="mt-1 space-y-1">
                          {step.criteria.map((c) => (
                            <li
                              key={c}
                              className="flex items-start gap-1.5 text-[11px] text-text/90"
                            >
                              <span className="font-bold text-emerald-500">✓</span>
                              <span>{c}</span>
                            </li>
                          ))}
                        </ul>
                      </div>

                      <div>
                        <div className="text-[11px] font-medium text-muted">关联交付工件：</div>
                        <div className="mt-1 flex flex-wrap items-center gap-1">
                          <span className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[10px] text-accent">
                            {step.file}
                          </span>
                          {step.probe && (
                            <span
                              className={cn(
                                "rounded px-1.5 py-0.5 font-mono text-[10px]",
                                step.probe.valid
                                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                  : step.probe.exists
                                    ? "bg-red-500/10 text-red-600 dark:text-red-400"
                                    : "bg-surface-2 text-muted",
                              )}
                            >
                              {step.probe.valid
                                ? "已校验通过"
                                : step.probe.exists
                                  ? "结构不合规"
                                  : "未找到"}
                            </span>
                          )}
                        </div>
                      </div>

                      {invalid && step.probe && (
                        <ul className="space-y-0.5 rounded-md border border-red-500/30 bg-red-500/5 p-2">
                          {step.probe.errors.slice(0, 4).map((e) => (
                            <li
                              key={e}
                              className="flex items-start gap-1 text-[10px] text-red-600 dark:text-red-400"
                            >
                              <AlertCircle size={10} className="mt-0.5 shrink-0" />
                              <span>{e}</span>
                            </li>
                          ))}
                        </ul>
                      )}

                      <button
                        onClick={() => injectPrompt(buildStepPrompt(step))}
                        title="将提示词追加到会话输入框（不自动发送）"
                        className="flex items-center gap-1.5 rounded-md bg-accent px-2.5 py-1 text-xs text-accent-fg transition-colors hover:bg-accent/90"
                      >
                        <Sparkles size={12} />
                        <span>在会话中推进此步骤（{step.file}）</span>
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
