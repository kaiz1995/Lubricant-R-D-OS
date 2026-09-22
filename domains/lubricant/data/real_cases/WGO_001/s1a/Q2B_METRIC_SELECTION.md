# WGO_001 S1a / WP-5 — Q2-B Metric Selection

- Artifact: Q2B_METRIC_SELECTION.md
- Basis: WGO_001_S1A_METHOD_CHARACTERIZATION_PLAN.md @ f8ea247, Section 6
- Build date: 2026-08-23
- Primary sources: 台架方案 JP20260301001 p3（定期记录噪声要求）; xlsx 六表全扫
- 性质: EVIDENCE RECORD ONLY。指标选择待 owner 批准后于 S1b 前 freeze。

## 0. 结论

选定:
- PRIMARY: noise_db_at_1h
- SECONDARY: noise_db_at_2h

两者均为 PROSPECTIVE_ONLY — 仅在 S1a 专用表征运行及之后的前瞻记录中有效，
历史数据不可回填。

## 1. 候选评估

### noise_db_at_1h — 选定 primary

- 协议基础: 报告 p3 明确「测试过程中定期记录噪声」— 固定时点读数在协议意图内。
- 时机合理性: JP20260301001 p6 分析指出前 ~2h 噪声主要由油品抗磨性能主导，
  2h 后抗电蚀复合剂效应开始显现 → 1h 读数处于早期平台区，受电蚀级联影响最小，
  机械上最稳定。
- 廉价: 每次运行必读，零额外成本。
- 局限: 对抗电蚀性能本身区分度可能低（早期主要反映基础油抗磨底色）。
  但 Q2-B 目标是重复性（同一处理读数是否稳定），不是区分度——区分度由 Q1 负责。

### noise_db_at_2h — 选定 secondary

- 位于抗磨主导→复合剂主导的过渡点，信息量更大;
- 仍属协议要求的定期记录范围;
- 部分快失效运行（如 1-2h 失效臂）可能在 2h 前已达终点 → 该类运行标记
  METRIC_NOT_ESTIMABLE_AT_2H，Q2-B 计算时剔除并记录计数。

### time-to-fixed-dB-threshold below 65 dB — 否决

- 历史噪声曲线仅有图（PDF 内嵌图），无原始时间序列数据;
- 日志采样间隔未知（散点稀疏程度不明），插值不可靠;
- plan 明确: 「only if instrument logging supports reliable interpolation; else reject」→ reject。
- 前瞻性补救: 若未来记录仪支持 ≥1/min 连续记录，可在参数冻结修订时重新纳入。

### endpoint-dB-at-event — 否决

- 与主响应（是否达 65dB 及何时达）共线，不能提供独立重复性信息。

## 2. 预注册采集规范（供参数冻结用）

- 读取时刻: 通电后第 60min ± 2min（noise@1h）、第 120min ± 2min（noise@2h）;
  注: 方案规定前 30min 不通电，故上述为总运行时长 90min/150min 时刻。
- 读取窗口内取稳定读数; 若窗口内噪声快速爬升，记录整段并标注 UNSTABLE_WINDOW。
- 每次运行必录; 缺失即 INVALID_RUN 替换政策适用（与 S1 计划一致）。
- 单位 dB(A)（与现行台架一致），保留一位小数。
- 与 endpoint 65dB 判定相互独立存储，不做阈值转换。

## 3. 非退化检查计划

表征运行完成后验证: 两指标在表征批次内非恒定（plan Section 6 标准）。
若 noise@1h 在所有表征运行中恒定（例如全部 52.x dB），仍可作为重复性指标使用
（恒定=极稳），但须在冻结记录中注明「区分度贡献为零，仅供 Q2-B」。
若出现仪器级跳变（同日相邻运行差 >10dB 无工况解释），触发方法审查而非静默接受。

## 4. Owner sign-off

- Reviewed by: ____________ Date: ____________
- Decision: FREEZE_1H_2H / MODIFY_TIMING / HOLD
- Notes: ____________________________________________

