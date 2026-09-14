/* eslint-disable i18next/no-literal-string */
import { useState, useRef, useEffect } from "react";
import {
  Folder,
  FolderOpen,
  FileText,
  FileCode,
  Send,
  ChevronRight,
  ChevronDown,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";

interface FileItem {
  name: string;
  type: "json" | "doc";
  stage: string;
  content?: string;
}

const MOCK_FILES: FileItem[] = [
  {
    name: "project.json",
    type: "json",
    stage: "Stage 0",
    content: JSON.stringify(
      {
        project_id: "V600-GEAR-001",
        name: "V600风电主齿轮箱专用齿轮油",
        type: "新产品正向开发",
        lead_researcher: "研发团队",
        target_cost_rmb_kg: 22.0,
        status: "APPROVED_STAGE_0",
      },
      null,
      2,
    ),
  },
  {
    name: "duty.json",
    type: "json",
    stage: "Stage 1",
    content: JSON.stringify(
      {
        equipment: "金风3MW风电机组主齿轮箱",
        operating_temp_c: 85,
        viscosity_grade: "ISO VG 320",
        micropitting_requirement: "FVA 54/7 >= 10级 (High)",
        flank_scuffing: "FZG >= 14",
        pour_point_c: -35,
      },
      null,
      2,
    ),
  },
  {
    name: "challenge.json",
    type: "json",
    stage: "Stage 2",
    content: JSON.stringify(
      {
        challenges: [
          "高温排气 (85℃) 导致基础油极易热氧化，需优选 PAO / 高性能酯类平衡抗老与抗微点蚀",
          "抗微点蚀与防锈防腐添加剂竞争吸附冲突",
          "22元/kg 严苛成本红线对全合成比例的强约束",
        ],
      },
      null,
      2,
    ),
  },
  {
    name: "doe_design.json",
    type: "json",
    stage: "Stage 6",
    content: JSON.stringify(
      {
        design_type: "D-Optimal Mixture Design",
        factors: ["PAO6", "PAO40", "Ester-A", "Anti-Wear Pack", "Friction Modifier"],
        runs: 12,
      },
      null,
      2,
    ),
  },
  {
    name: "experiment.json",
    type: "json",
    stage: "Stage 7",
    content: JSON.stringify(
      {
        batch_id: "BATCH-20260907-01",
        measured_kv40: 318.5,
        measured_kv100: 34.2,
        fz_stage: 14,
        micropitting_fail_stage: 10,
      },
      null,
      2,
    ),
  },
];

interface Message {
  id: string;
  role: "user" | "copilot";
  content: string;
  time: string;
  badge?: string;
}

export function LubricantWorkbenchPage() {
  const [activeFile, setActiveFile] = useState<FileItem | null>(null);
  const [folderOpen, setFolderOpen] = useState(true);
  const [docsOpen, setDocsOpen] = useState(true);
  const [inputVal, setInputVal] = useState("");
  const [gateStatus, setGateStatus] = useState<"GO" | "HOLD" | "REVISE">("GO");
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "m-1",
      role: "user",
      content:
        "针对金风3MW主齿轮箱，排气温度85℃，做一款抗微点蚀优异的齿轮油，成本控制在22元/kg以内。",
      time: "10:14",
      badge: "研发员",
    },
    {
      id: "m-2",
      role: "copilot",
      content:
        "已识别为【新产品正向开发】！正在建立 Stage 0 立项章程，并自动梳理该工况下的 7 大核心挑战...",
      time: "10:15",
      badge: "副驾驶",
    },
  ]);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    if (!inputVal.trim()) return;
    const userText = inputVal.trim();
    setInputVal("");
    const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const userMsg: Message = {
      id: "msg-" + Date.now(),
      role: "user",
      content: userText,
      time: now,
      badge: "研发员",
    };
    setMessages((prev) => [...prev, userMsg]);

    setTimeout(() => {
      const copilotMsg: Message = {
        id: "msg-c-" + Date.now(),
        role: "copilot",
        content: "收到研发指令：" + userText + "。已关联当前 Stage 1 工况定义工件链。正在进行物性约束与配方空间初筛，最新门禁评审状态保持：[" + gateStatus + " 放行]。",
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        badge: "副驾驶",
      };
      setMessages((prev) => [...prev, copilotMsg]);
    }, 600);
  };

  return (
    <div className="flex h-full w-full flex-col bg-[#0f172a] text-[#e2e8f0] font-sans antialiased select-none">
      {/* Window Title Bar */}
      <div className="flex h-10 items-center justify-between border-b border-[#334155] px-4 bg-[#1e293b]/60 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-full bg-[#ef4444]" />
            <span className="h-3 w-3 rounded-full bg-[#eab308]" />
            <span className="h-3 w-3 rounded-full bg-[#22c55e]" />
          </div>
          <span className="text-xs font-medium tracking-wide text-[#cbd5e1]">
            Open Science Desktop — Lubricant R&D Copilot
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded bg-[#0284c7]/20 px-2 py-0.5 text-[11px] font-medium text-[#38bdf8] border border-[#0284c7]/40">
            极简路径验证模式 (Stage 1 Active)
          </span>
        </div>
      </div>

      {/* Three-Column Workbench Layout */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left Column: 工作区与项目文件 */}
        <div className="flex w-64 flex-col border-r border-[#334155] bg-[#1e293b]/30 p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-[#94a3b8] uppercase tracking-wider">
            <Folder size={14} className="text-[#f59e0b]" />
            <span>工作区与项目文件</span>
          </div>

          <div className="flex-1 overflow-y-auto pr-1 text-xs">
            {/* Project Root Folder */}
            <div className="mb-1">
              <div
                onClick={() => setFolderOpen(!folderOpen)}
                className="flex cursor-pointer items-center gap-1.5 rounded px-2 py-1.5 text-[#f1f5f9] hover:bg-[#334155]/50"
              >
                {folderOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <FolderOpen size={14} className="text-[#f59e0b]" />
                <span className="font-semibold text-sm">projects/V600齿轮油/</span>
              </div>

              {folderOpen && (
                <div className="ml-4 mt-1 flex flex-col gap-0.5 border-l border-[#334155] pl-2">
                  {MOCK_FILES.map((file) => (
                    <button
                      key={file.name}
                      onClick={() => setActiveFile(file)}
                      className={cn(
                        "flex items-center justify-between rounded px-2 py-1.5 text-left text-[12px] transition-colors",
                        activeFile?.name === file.name
                          ? "bg-[#2563eb] text-white"
                          : "text-[#cbd5e1] hover:bg-[#334155]/40 hover:text-white",
                      )}
                    >
                      <div className="flex items-center gap-1.5 truncate">
                        <FileCode size={13} className="shrink-0 text-[#38bdf8]" />
                        <span className="truncate">{file.name}</span>
                      </div>
                      <span className="text-[10px] text-[#94a3b8]">{file.stage}</span>
                    </button>
                  ))}

                  {/* Docs subfolder */}
                  <div className="mt-1">
                    <div
                      onClick={() => setDocsOpen(!docsOpen)}
                      className="flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 text-[#cbd5e1] hover:bg-[#334155]/40"
                    >
                      {docsOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      <Folder size={12} className="text-[#f59e0b]" />
                      <span className="font-medium">docs/</span>
                    </div>
                    {docsOpen && (
                      <div className="ml-3 mt-0.5 border-l border-[#334155] pl-2">
                        <button
                          onClick={() =>
                            setActiveFile({
                              name: "2026-0907-开发报告 v0.1.md",
                              type: "doc",
                              stage: "Live Doc",
                              content:
                                "# V600齿轮油研发进展报告 v0.1\n\n- **当前阶段**：Stage 1 工况定义中\n- **目标成本**：<= 22.0 元/kg\n- **关键指标**：抗微点蚀 FVA 54/7 >= 10级\n- **决议**：Stage 0 Gate [GO 放行]",
                            })
                          }
                          className="flex items-center gap-1.5 rounded px-2 py-1 text-[11px] text-[#cbd5e1] hover:bg-[#334155]/40 hover:text-white"
                        >
                          <FileText size={12} className="text-[#a855f7]" />
                          <span className="truncate">2026-0907-开发报告 v0.1.md</span>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Middle Column: 副驾驶会话交互区（研发主阵地） */}
        <div className="flex flex-1 flex-col border-r border-[#334155] bg-[#0b1329]">
          {/* Header */}
          <div className="flex h-11 items-center justify-between border-b border-[#334155] px-4 bg-[#1e293b]/40">
            <div className="flex items-center gap-2">
              <span className="text-base">💬</span>
              <span className="font-semibold text-sm text-[#f8fafc]">
                副驾驶会话交互区（研发主阵地）
              </span>
            </div>
            <span className="text-[11px] text-[#64748b]">模型接入：DeepSeek-V3 / OpenCode Agent</span>
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((m) => (
              <div
                key={m.id}
                className={cn(
                  "flex flex-col gap-1 max-w-[85%] rounded-xl p-3.5 shadow-sm text-xs leading-relaxed",
                  m.role === "user"
                    ? "ml-auto bg-[#1e293b] border border-[#334155] text-[#f1f5f9]"
                    : "mr-auto bg-[#1e3a8a]/40 border border-[#1d4ed8]/50 text-[#e0e7ff]",
                )}
              >
                <div className="flex items-center justify-between gap-2 border-b border-white/10 pb-1 mb-1">
                  <span
                    className={cn(
                      "font-semibold text-[11px]",
                      m.role === "user" ? "text-[#a855f7]" : "text-[#60a5fa]",
                    )}
                  >
                    {m.role === "user" ? "👤 " : "🤖 "} {m.badge}
                  </span>
                  <span className="text-[10px] text-[#94a3b8]">{m.time}</span>
                </div>
                <div className="whitespace-pre-wrap">{m.content}</div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* Quick Action Chips */}
          <div className="flex items-center gap-2 px-4 py-2 border-t border-[#1e293b] bg-[#0f172a]">
            <span className="text-[11px] text-[#64748b]">快捷指令:</span>
            <button
              onClick={() => setInputVal("启动金风3MW微点蚀工况分析并对比工业齿轮油标准")}
              className="rounded-full bg-[#1e293b] border border-[#334155] px-2.5 py-1 text-[11px] text-[#94a3b8] hover:text-white hover:border-[#60a5fa] transition-colors"
            >
              ⚡ 工况标准对比
            </button>
            <button
              onClick={() => setInputVal("检查 Stage 1 工况参数，确认是否符合 Stage 1 Gate 准入条件")}
              className="rounded-full bg-[#1e293b] border border-[#334155] px-2.5 py-1 text-[11px] text-[#94a3b8] hover:text-white hover:border-[#60a5fa] transition-colors"
            >
              🛡️ 门禁合规自检
            </button>
          </div>

          {/* Input Bar */}
          <div className="border-t border-[#334155] p-3 bg-[#1e293b]/50">
            <div className="flex items-center gap-2 rounded-lg bg-[#0f172a] border border-[#334155] px-3 py-2 focus-within:border-[#38bdf8]">
              <span className="text-base text-[#64748b]">⌨</span>
              <input
                type="text"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="在此用纯自然语言输入工况、材料、实验测试数据..."
                className="flex-1 bg-transparent text-xs text-white placeholder-[#64748b] outline-none"
              />
              <button
                onClick={handleSend}
                className="rounded-md bg-[#2563eb] p-1.5 text-white hover:bg-[#1d4ed8] transition-colors"
              >
                <Send size={14} />
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: 状态、门禁与活报告预览 */}
        <div className="flex w-80 flex-col bg-[#1e293b]/40 p-4 space-y-5 overflow-y-auto">
          <div className="flex items-center gap-2 text-xs font-semibold text-[#94a3b8] uppercase tracking-wider">
            <span className="text-base">📊</span>
            <span>状态、门禁与活报告预览</span>
          </div>

          {/* Current Stage */}
          <div className="rounded-lg bg-[#0f172a] border border-[#334155] p-3">
            <div className="text-[11px] text-[#94a3b8]">当前研发阶段:</div>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-sm font-semibold text-[#38bdf8]">Stage 1: 工况定义中</span>
              <span className="flex h-2 w-2 rounded-full bg-[#38bdf8] animate-pulse" />
            </div>
          </div>

          {/* Artifact Chain Progress */}
          <div className="rounded-lg bg-[#0f172a] border border-[#334155] p-3">
            <div className="flex items-center justify-between text-[11px] text-[#94a3b8]">
              <span>工件链推进:</span>
              <span className="font-mono text-[#22c55e]">2 / 11</span>
            </div>
            {/* Progress Blocks */}
            <div className="mt-2 flex gap-1 items-center">
              <span className="h-3 w-3 rounded-sm bg-[#22c55e]" title="Stage 0: 立项章程 (完成)" />
              <span className="h-3 w-3 rounded-sm bg-[#22c55e]" title="Stage 1: 工况定义 (完成/审核中)" />
              {Array.from({ length: 9 }).map((_, i) => (
                <span key={i} className="h-3 w-3 rounded-sm bg-[#334155]" title={"Stage " + (i + 2) + ": 待推进"} />
              ))}
            </div>
            <div className="mt-2 text-[10px] text-[#64748b]">已生成: project.json, duty.json</div>
          </div>

          {/* Gate Decision */}
          <div className="rounded-lg bg-[#0f172a] border border-[#334155] p-3">
            <div className="text-[11px] text-[#94a3b8]">最新门禁决议:</div>
            <div className="mt-2 flex items-center justify-between">
              <div
                className={cn(
                  "rounded px-3 py-1 text-xs font-bold tracking-wider",
                  gateStatus === "GO" ? "bg-[#16a34a] text-white" : "bg-[#dc2626] text-white",
                )}
              >
                {gateStatus} 放行
              </div>
              <div className="flex gap-1 text-[10px]">
                <button
                  onClick={() => setGateStatus("GO")}
                  className="rounded bg-[#334155] px-2 py-0.5 hover:bg-[#475569]"
                >
                  放行
                </button>
                <button
                  onClick={() => setGateStatus("HOLD")}
                  className="rounded bg-[#334155] px-2 py-0.5 hover:bg-[#475569]"
                >
                  暂停
                </button>
              </div>
            </div>
            <div className="mt-2.5 text-[11px] text-[#94a3b8] leading-relaxed border-t border-[#334155] pt-2">
              ✅ 成本指标校验通过 (22元/kg 红线以内)<br />
              ✅ 微点蚀工况要求已规范化并存入 duty.json
            </div>
          </div>

          {/* Active File Inspector Card */}
          {activeFile && (
            <div className="rounded-lg bg-[#0f172a] border border-[#38bdf8]/40 p-3">
              <div className="flex items-center justify-between border-b border-[#334155] pb-1.5 mb-2">
                <span className="text-xs font-semibold text-[#38bdf8] truncate">
                  📄 {activeFile.name}
                </span>
                <button
                  onClick={() => setActiveFile(null)}
                  className="text-[#94a3b8] hover:text-white"
                >
                  <X size={12} />
                </button>
              </div>
              <pre className="max-h-48 overflow-auto text-[10px] font-mono text-[#cbd5e1] p-1 bg-[#1e293b]/60 rounded">
                {activeFile.content}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

