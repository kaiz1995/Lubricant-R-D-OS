/* eslint-disable i18next/no-literal-string */
import { useState } from "react";
import {
  CheckCircle2,
  Clock,
  Circle,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  Sparkles,
  FileCode2,
  FileText,
  AlertTriangle,
  Send,
  Layers,
  Check,
  X,
  ArrowRight,
} from "lucide-react";
import { PaneTitlebarInset } from "@/components/inspector/RightPane";
import { cn } from "@/lib/cn";

export type DevType =
  | "forward"
  | "benchmark"
  | "cost_reduction"
  | "substitution"
  | "failure_analysis";

interface StageStep {
  id: number;
  stageName: string;
  title: string;
  file: string;
  status: "completed" | "active" | "pending";
  description: string;
  criteria: string[];
  deliverables: string[];
}

interface DevTypeConfig {
  key: DevType;
  label: string;
  shortLabel: string;
  badge: string;
  totalStages: number;
  completedStages: number;
  currentStageText: string;
  gateStatus: "GO" | "HOLD" | "REVISE";
  gateNote: string;
  steps: StageStep[];
}

const DEV_CONFIGS: Record<DevType, DevTypeConfig> = {
  forward: {
    key: "forward",
    label: "新产品正向开发",
    shortLabel: "正向开发",
    badge: "11阶段全流程",
    totalStages: 11,
    completedStages: 2,
    currentStageText: "Stage 1: 工况与指标定义中",
    gateStatus: "GO",
    gateNote: "Stage 0 准入条件满足，工况关键指标无冲突，准予进入配方设计空间探索。",
    steps: [
      {
        id: 0,
        stageName: "Stage 0",
        title: "立项章程与项目定义",
        file: "project.json",
        status: "completed",
        description: "确定项目代号、应用场景目标、成本上限约束与团队权责。",
        criteria: ["明确应用机型与工况环境", "锁定目标成本上限 (如 <= 22元/kg)", "完成立项评审批准"],
        deliverables: ["project.json (立项信息)", "charter_review.md"],
      },
      {
        id: 1,
        stageName: "Stage 1",
        title: "严苛工况与指标定义",
        file: "duty.json",
        status: "active",
        description: "将机械运转环境转化为润滑油理化与台架指标规格清单。",
        criteria: ["排气/油池工作温度 (如 85℃)", "运动黏度等级 (如 ISO VG 320)", "关键微点蚀等级 FVA 54/7 >= 10级"],
        deliverables: ["duty.json (工况规范)", "standards_comparison.xlsx"],
      },
      {
        id: 2,
        stageName: "Stage 2",
        title: "核心技术挑战梳理",
        file: "challenge.json",
        status: "pending",
        description: "识别配方矛盾与极端工况下的技术难点与机理风险。",
        criteria: ["基础油热氧化与高温抗老矛盾", "极压抗磨与防锈添加剂竞争吸附冲突", "成本红线对全合成基础油比例限制"],
        deliverables: ["challenge.json (7大技术挑战清单)"],
      },
      {
        id: 3,
        stageName: "Stage 3",
        title: "失效模式与CTQ关键质量指标",
        file: "failure_ctq.json",
        status: "pending",
        description: "明确齿轮点蚀、擦伤、起泡、沉积物等失效模式及CTQ阈值。",
        criteria: ["齿面微点蚀保护能力 (FZG/FVA)", "起泡倾向与空气释放值", "抗乳化分水性能"],
        deliverables: ["failure_ctq.json (CTQ矩阵与判定基准)"],
      },
      {
        id: 4,
        stageName: "Stage 4",
        title: "测试与表征方法确认",
        file: "test_method.json",
        status: "pending",
        description: "锁定实验室与第三方台架评估的标准化测试规范。",
        criteria: ["DIN 51517-3 工业齿轮油标准", "FVA 54 微点蚀试验规程", "Flender 齿轮箱相容性测试"],
        deliverables: ["test_method.json (测试协议与试验台架配置)"],
      },
      {
        id: 5,
        stageName: "Stage 5",
        title: "配方原材料与设计空间",
        file: "design_space.json",
        status: "pending",
        description: "确定基础油（PAO/酯类/mPAO）与添加剂候选池及比例上下限。",
        criteria: ["基础油配比边界约束 (60%-85%)", "复合添加剂包加注量窗口 (1.5%-3.5%)", "原材料BOM成本测算模型"],
        deliverables: ["design_space.json (原材料数据库与候选空间)"],
      },
      {
        id: 6,
        stageName: "Stage 6",
        title: "混料DOE实验设计",
        file: "doe_design.json",
        status: "pending",
        description: "运行混料设计算法（D-Optimal/Simplex），生成实验矩阵。",
        criteria: ["多组分混料配比归一化 (Sum=100%)", "覆盖拐点与极值试验点", "控制总实验轮次成本"],
        deliverables: ["doe_design.json (12~16组配方DOE矩阵)"],
      },
      {
        id: 7,
        stageName: "Stage 7",
        title: "实验室调配与台架测试数据",
        file: "experiment.json",
        status: "pending",
        description: "试制调配实样，录入40℃/100℃黏度、抗微点蚀及四球实测值。",
        criteria: ["实测理化数据完整录入", "微点蚀与承载能力台架验证", "异常数据复测标定"],
        deliverables: ["experiment.json (批次实测数据集)"],
      },
      {
        id: 8,
        stageName: "Stage 8",
        title: "响应面模型拟合与统计分析",
        file: "model.json",
        status: "pending",
        description: "建立基础油与添加剂对黏度指数、抗磨、成本的回归方程。",
        criteria: ["R²拟合优度与残差正态分布检验", "因子显著性与交互效应分析", "预测方差膨胀系数VIF核查"],
        deliverables: ["model.json (多项式响应面回归模型)"],
      },
      {
        id: 9,
        stageName: "Stage 9",
        title: "多目标配方Pareto优化",
        file: "optimization.json",
        status: "pending",
        description: "在抗微点蚀性能最大化与成本<=22元/kg约束下求解最佳配方。",
        criteria: ["Pareto最优前沿求解", "鲁棒性与公差敏感度分析", "推荐最优主选配方与候选平替配方"],
        deliverables: ["optimization.json (最优候选配方表与指标预测)"],
      },
      {
        id: 10,
        stageName: "Stage 10",
        title: "门禁终审与配方定型冻结",
        file: "gate.json / design_freeze.json",
        status: "pending",
        description: "综合全链条证据包完成Gate终审放行，正式冻结产品配方。",
        criteria: ["全部CTQ指标100%合格达标", "主机厂认可与试验报告齐套", "生成最终开发报告与技术规格书TDS"],
        deliverables: ["gate.json (终审放行决议)", "design_freeze.json (配方冻结归档)"],
      },
    ],
  },
  benchmark: {
    key: "benchmark",
    label: "竞品对标与逆向工程",
    shortLabel: "竞品对标",
    badge: "7阶段对标流",
    totalStages: 7,
    completedStages: 1,
    currentStageText: "Stage 1: 理化与红外剖析",
    gateStatus: "GO",
    gateNote: "标杆竞品样品已送检入库，进入光谱逆向剖析。",
    steps: [
      {
        id: 0,
        stageName: "Stage 0",
        title: "竞品信息建档与样品入库",
        file: "sample_profile.json",
        status: "completed",
        description: "收集对标品牌油品样品、技术手册TDS及应用背景。",
        criteria: ["竞品批次可追溯", "基础指标与宣称卖点对齐"],
        deliverables: ["sample_profile.json"],
      },
      {
        id: 1,
        stageName: "Stage 1",
        title: "理化指标与红外光谱剖析",
        file: "spectrum_analysis.json",
        status: "active",
        description: "FTIR红外光谱、ICP发射光谱分析元素与特征官能团。",
        criteria: ["P/Zn/Ca/B添加剂元素定性定量", "特征酯键与聚合物吸收峰确认"],
        deliverables: ["spectrum_analysis.json"],
      },
      {
        id: 2,
        stageName: "Stage 2",
        title: "基础油分类与添加剂逆向解析",
        file: "reverse_composition.json",
        status: "pending",
        description: "反推竞品基础油组合类型及添加剂功能包构成。",
        criteria: ["基础油组分判定 (PAO/矿物油/合成酯)", "核心极压抗磨剂类别锁定"],
        deliverables: ["reverse_composition.json"],
      },
      {
        id: 3,
        stageName: "Stage 3",
        title: "全性能对比台架测试",
        file: "benchmark_testing.json",
        status: "pending",
        description: "平行测试自研对标样与竞品样在相同机台的性能差异。",
        criteria: ["抗磨擦伤对齐", "热氧化寿命与分水性能对齐"],
        deliverables: ["benchmark_testing.json"],
      },
      {
        id: 4,
        stageName: "Stage 4",
        title: "替代配方设计空间构建",
        file: "substitute_design.json",
        status: "pending",
        description: "采用国内自主可控原材料寻找替代与超越路径。",
        criteria: ["避开竞品专利阻断", "保障关键物性一致性"],
        deliverables: ["substitute_design.json"],
      },
      {
        id: 5,
        stageName: "Stage 5",
        title: "平替配方台架复验",
        file: "validation.json",
        status: "pending",
        description: "对选定对标自研配方进行严格台架与耐久盲测验证。",
        criteria: ["综合性能指标达到或超越竞品"],
        deliverables: ["validation.json"],
      },
      {
        id: 6,
        stageName: "Stage 6",
        title: "对标定型与量产门禁",
        file: "design_freeze.json",
        status: "pending",
        description: "形成竞品对标分析白皮书并完成配方冻结。",
        criteria: ["对标差异度分析结论明确", "签署量产批准"],
        deliverables: ["design_freeze.json"],
      },
    ],
  },
  cost_reduction: {
    key: "cost_reduction",
    label: "配方降本优化",
    shortLabel: "配方降本",
    badge: "5阶段敏捷流",
    totalStages: 5,
    completedStages: 1,
    currentStageText: "Stage 1: 成本驱动因素审计",
    gateStatus: "GO",
    gateNote: "BOM基线确立，高价添加剂替代方案已建立候选池。",
    steps: [
      {
        id: 0,
        stageName: "Stage 0",
        title: "现有配方BOM基线审计",
        file: "baseline_bom.json",
        status: "completed",
        description: "核算现有在产油品的每公斤原材料成本构成比率。",
        criteria: ["建立精确BOM成本台账", "锁定降本目标幅度 (如降低12%)"],
        deliverables: ["baseline_bom.json"],
      },
      {
        id: 1,
        stageName: "Stage 1",
        title: "高价值组分降本杠杆识别",
        file: "cost_levers.json",
        status: "active",
        description: "识别高单价酯类或过量添加剂加注量的降本空间。",
        criteria: ["评估基础油微调可能性", "评估国产优质平替添加剂加注效率"],
        deliverables: ["cost_levers.json"],
      },
      {
        id: 2,
        stageName: "Stage 2",
        title: "性能无损约束DOE设计",
        file: "cost_doe.json",
        status: "pending",
        description: "以抗微点蚀不降级为硬约束开展降本混料试验。",
        criteria: ["关键CTQ边界硬锁定", "筛选性价比最优组合"],
        deliverables: ["cost_doe.json"],
      },
      {
        id: 3,
        stageName: "Stage 3",
        title: "等效性平行台架验证",
        file: "parity_testing.json",
        status: "pending",
        description: "对比新旧配方在标准台架下的磨耗与油泥指标。",
        criteria: ["性能零劣化 (Parity/Better)", "关键工况数据重现"],
        deliverables: ["parity_testing.json"],
      },
      {
        id: 4,
        stageName: "Stage 4",
        title: "效益核算与变更门禁放行",
        file: "cost_gate.json",
        status: "pending",
        description: "核算年度物料节约总额并完成工程变更审批。",
        criteria: ["年化成本节约达标", "生产车间调配工艺无障碍"],
        deliverables: ["cost_gate.json"],
      },
    ],
  },
  substitution: {
    key: "substitution",
    label: "原材料替代 / 供应链保供",
    shortLabel: "材料替代",
    badge: "4阶段验证流",
    totalStages: 4,
    completedStages: 1,
    currentStageText: "Stage 1: 相容性与理化初筛",
    gateStatus: "GO",
    gateNote: "备选供应商资质合格，进入相容性理化试验。",
    steps: [
      {
        id: 0,
        stageName: "Stage 0",
        title: "替代原料资质与指标比对",
        file: "raw_material_spec.json",
        status: "completed",
        description: "比对二供/新供应商基础油或添加剂规格参数。",
        criteria: ["关键理化指标容差在允许范围内", "保供产能与商务资质合规"],
        deliverables: ["raw_material_spec.json"],
      },
      {
        id: 1,
        stageName: "Stage 1",
        title: "相容性与理化稳定性初筛",
        file: "compatibility.json",
        status: "active",
        description: "高温储存浊点、分层、析出及铜片腐蚀测试。",
        criteria: ["与现存基础油相容无浑浊", "抗乳化与消泡性能不劣化"],
        deliverables: ["compatibility.json"],
      },
      {
        id: 2,
        stageName: "Stage 2",
        title: "台架核心失效指标评估",
        file: "ctq_evaluation.json",
        status: "pending",
        description: "考察微点蚀、承载极压与抗剪切等硬指标。",
        criteria: ["核心性能通过台架考核标准"],
        deliverables: ["ctq_evaluation.json"],
      },
      {
        id: 3,
        stageName: "Stage 3",
        title: "批量试制与二供导入门禁",
        file: "supplier_gate.json",
        status: "pending",
        description: "车间百公斤试制并签署合格供方准入决议。",
        criteria: ["试调批次稳定性达标", "签署供方变更报告"],
        deliverables: ["supplier_gate.json"],
      },
    ],
  },
  failure_analysis: {
    key: "failure_analysis",
    label: "质量故障根因诊断",
    shortLabel: "故障排查",
    badge: "5阶段排查流",
    totalStages: 5,
    completedStages: 1,
    currentStageText: "Stage 1: 理化衰变与磨粒诊断",
    gateStatus: "HOLD",
    gateNote: "现场工况数据采集中，等待铁谱分析报告。",
    steps: [
      {
        id: 0,
        stageName: "Stage 0",
        title: "现场工况与失效样品建档",
        file: "failure_record.json",
        status: "completed",
        description: "采集现场环境温度、载荷波动历史及油样取样点。",
        criteria: ["现场故障照片与运行日志齐备", "取样遵循规范无污染"],
        deliverables: ["failure_record.json"],
      },
      {
        id: 1,
        stageName: "Stage 1",
        title: "在用油理化衰变与铁谱磨粒",
        file: "oil_degradation.json",
        status: "active",
        description: "分析酸值升高、黏度变化、氧化及磨损金属颗粒尺寸。",
        criteria: ["磨损颗粒形貌定性 (切削/疲劳/剥落)", "残余抗氧剂含量衰减率"],
        deliverables: ["oil_degradation.json"],
      },
      {
        id: 2,
        stageName: "Stage 2",
        title: "齿轮微观形貌机理复盘",
        file: "microscopy_analysis.json",
        status: "pending",
        description: "电镜扫描齿面点蚀微裂纹，判定制约机理。",
        criteria: ["判定是否为润滑油油膜破裂导致", "还是机械硬度热处理缺陷"],
        deliverables: ["microscopy_analysis.json"],
      },
      {
        id: 3,
        stageName: "Stage 3",
        title: "根本原因判定与应急措施",
        file: "root_cause.json",
        status: "pending",
        description: "给出故障鱼骨图与临时纠正措施 (ICA)。",
        criteria: ["消除次要干扰因素，锁定核心失效源"],
        deliverables: ["root_cause.json"],
      },
      {
        id: 4,
        stageName: "Stage 4",
        title: "配方防再发永久改进措施 (PCA)",
        file: "preventive_action.json",
        status: "pending",
        description: "升级油品抗微点蚀添加剂或推荐清洗换油规范。",
        criteria: ["改进方案经台架复现验证有效", "闭环质量事故归档"],
        deliverables: ["preventive_action.json"],
      },
    ],
  },
};

export function LubricantStagePane({
  sessionId: _sessionId,
  onClose,
  controls,
}: {
  sessionId?: string;
  onClose: () => void;
  controls?: React.ReactNode;
}) {
  const [selectedType, setSelectedType] = useState<DevType>("forward");
  const [expandedStep, setExpandedStep] = useState<number | null>(1); // default expand current active step
  const [gateDecision, setGateDecision] = useState<"GO" | "HOLD" | "REVISE">("GO");

  const currentConfig = DEV_CONFIGS[selectedType];
  const percent = Math.round((currentConfig.completedStages / currentConfig.totalStages) * 100);

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

      {/* Development Type Selection Bar */}
      <div className="border-b border-border bg-surface-2/40 px-3 py-2 shrink-0">
        <div className="mb-1.5 flex items-center justify-between text-[11px] text-muted">
          <span className="font-medium">研发开发类型:</span>
          <span className="rounded bg-primary/10 px-1.5 py-0.2 text-[10px] font-semibold text-primary">
            {currentConfig.badge}
          </span>
        </div>
        <div className="flex gap-1 overflow-x-auto pb-0.5 no-scrollbar">
          {(Object.keys(DEV_CONFIGS) as DevType[]).map((typeKey) => {
            const cfg = DEV_CONFIGS[typeKey];
            const isSelected = selectedType === typeKey;
            return (
              <button
                key={typeKey}
                onClick={() => {
                  setSelectedType(typeKey);
                  setExpandedStep(cfg.steps.find((s) => s.status === "active")?.id ?? 0);
                  setGateDecision(cfg.gateStatus);
                }}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium whitespace-nowrap transition-all",
                  isSelected
                    ? "bg-primary text-white shadow-sm"
                    : "bg-surface text-muted hover:bg-surface-2 hover:text-text border border-border/60",
                )}
              >
                {cfg.shortLabel}
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Scrollable Content */}
      <div className="flex-1 overflow-y-auto px-3.5 py-3 space-y-4 text-xs">
        {/* Overall Progress Summary Card */}
        <div className="rounded-xl border border-border bg-surface-2/60 p-3 shadow-xs space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <div className="text-[11px] text-muted">当前工序状态</div>
              <div className="text-xs font-bold text-text flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <span>{currentConfig.currentStageText}</span>
              </div>
            </div>
            <div className="text-right space-y-0.5">
              <div className="text-[11px] text-muted">整体完成度</div>
              <div className="font-mono text-sm font-extrabold text-primary">
                {currentConfig.completedStages} / {currentConfig.totalStages}{" "}
                <span className="text-xs font-normal text-muted">({percent}%)</span>
              </div>
            </div>
          </div>

          {/* Progress Visual Bar */}
          <div className="space-y-1">
            <div className="h-2 w-full overflow-hidden rounded-full bg-border/80 flex">
              <div
                className="h-full bg-gradient-to-r from-emerald-500 to-primary transition-all duration-500"
                style={{ width: `${percent}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-muted">
              <span>起步: 立项与定义</span>
              <span>终点: 验证与定型</span>
            </div>
          </div>
        </div>

        {/* Gate Decision Banner */}
        <div className="rounded-xl border border-border bg-surface-2/40 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 font-semibold text-text text-xs">
              <ShieldCheck size={14} className="text-emerald-500" />
              <span>最新门禁决议 (Gate Review)</span>
            </div>
            <div className="flex items-center gap-1">
              <span
                className={cn(
                  "rounded-full px-2 py-0.5 text-[10px] font-extrabold tracking-wide",
                  gateDecision === "GO"
                    ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30"
                    : gateDecision === "HOLD"
                      ? "bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30"
                      : "bg-red-500/15 text-red-600 dark:text-red-400 border border-red-500/30",
                )}
              >
                {gateDecision} 放行
              </span>
            </div>
          </div>
          <p className="text-[11px] leading-relaxed text-muted bg-surface/60 rounded-md p-2 border border-border/40">
            {currentConfig.gateNote}
          </p>
          <div className="flex items-center justify-end gap-1.5 pt-1">
            <button
              onClick={() => setGateDecision("GO")}
              className={cn(
                "rounded px-2 py-0.5 text-[10px] font-medium transition-colors",
                gateDecision === "GO" ? "bg-emerald-600 text-white" : "bg-surface hover:bg-surface-2 text-muted",
              )}
            >
              批准放行
            </button>
            <button
              onClick={() => setGateDecision("HOLD")}
              className={cn(
                "rounded px-2 py-0.5 text-[10px] font-medium transition-colors",
                gateDecision === "HOLD" ? "bg-amber-600 text-white" : "bg-surface hover:bg-surface-2 text-muted",
              )}
            >
              暂停待补
            </button>
          </div>
        </div>

        {/* Dedicated Steps Section */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-xs tracking-tight text-text">
              工件链阶段步骤 ({currentConfig.steps.length} 步独立推进)
            </span>
            <span className="text-[11px] text-muted">点击展开步骤细则</span>
          </div>

          <div className="space-y-2">
            {currentConfig.steps.map((step) => {
              const isExpanded = expandedStep === step.id;
              const isCompleted = step.status === "completed";
              const isActive = step.status === "active";

              return (
                <div
                  key={step.id}
                  className={cn(
                    "rounded-xl border transition-all duration-150 overflow-hidden",
                    isActive
                      ? "border-primary/60 bg-primary/5 shadow-xs"
                      : isCompleted
                        ? "border-emerald-500/30 bg-surface/90"
                        : "border-border/60 bg-surface/50 opacity-80 hover:opacity-100",
                  )}
                >
                  {/* Step Card Header */}
                  <div
                    onClick={() => setExpandedStep(isExpanded ? null : step.id)}
                    className="flex cursor-pointer items-center justify-between p-2.5 select-none hover:bg-surface-2/40"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      {/* Step Indicator Icon */}
                      <div className="shrink-0">
                        {isCompleted ? (
                          <CheckCircle2 size={16} className="text-emerald-500" />
                        ) : isActive ? (
                          <div className="relative flex h-4 w-4 items-center justify-center">
                            <span className="absolute h-full w-full rounded-full bg-primary/20 animate-ping" />
                            <Clock size={15} className="text-primary relative z-10" />
                          </div>
                        ) : (
                          <Circle size={15} className="text-muted/60" />
                        )}
                      </div>

                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={cn(
                              "rounded px-1 py-0.2 text-[10px] font-mono font-bold",
                              isActive
                                ? "bg-primary text-white"
                                : isCompleted
                                  ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                                  : "bg-surface-2 text-muted",
                            )}
                          >
                            {step.stageName}
                          </span>
                          <span className="font-semibold text-xs text-text truncate">
                            {step.title}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 text-[11px] text-muted mt-0.5">
                          <FileCode2 size={11} className="text-primary/70 shrink-0" />
                          <span className="font-mono text-[10px] truncate">{step.file}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0 ml-2">
                      <span
                        className={cn(
                          "text-[10px] font-medium px-1.5 py-0.2 rounded-full",
                          isCompleted
                            ? "text-emerald-600 bg-emerald-500/10"
                            : isActive
                              ? "text-primary bg-primary/10 font-bold"
                              : "text-muted bg-surface-2",
                        )}
                      >
                        {isCompleted ? "已完成" : isActive ? "进行中" : "待推进"}
                      </span>
                      {isExpanded ? <ChevronDown size={14} className="text-muted" /> : <ChevronRight size={14} className="text-muted" />}
                    </div>
                  </div>

                  {/* Expanded Step Details */}
                  {isExpanded && (
                    <div className="border-t border-border/50 bg-surface-2/20 p-3 space-y-2.5 text-xs">
                      <div>
                        <div className="text-[11px] font-medium text-muted">阶段目标:</div>
                        <div className="text-text leading-relaxed mt-0.5 text-[11px]">
                          {step.description}
                        </div>
                      </div>

                      <div>
                        <div className="text-[11px] font-medium text-muted">准入考核标准 (Criteria):</div>
                        <ul className="mt-1 space-y-1">
                          {step.criteria.map((c, idx) => (
                            <li key={idx} className="flex items-start gap-1.5 text-[11px] text-text/90">
                              <span className="text-emerald-500 font-bold">✓</span>
                              <span>{c}</span>
                            </li>
                          ))}
                        </ul>
                      </div>

                      <div>
                        <div className="text-[11px] font-medium text-muted">关联交付工件:</div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {step.deliverables.map((d, idx) => (
                            <span
                              key={idx}
                              className="rounded bg-surface px-1.5 py-0.5 font-mono text-[10px] text-primary border border-border"
                            >
                              📄 {d}
                            </span>
                          ))}
                        </div>
                      </div>
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

