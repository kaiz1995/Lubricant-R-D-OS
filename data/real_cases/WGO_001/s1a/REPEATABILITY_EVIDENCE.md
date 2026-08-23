# WGO_001 S1a / WP-4 — Repeatability Evidence and SIGMA_MAX Proposal

- Artifact: REPEATABILITY_EVIDENCE.md
- Basis: WGO_001_S1A_METHOD_CHARACTERIZATION_PLAN.md @ f8ea247, Section 4
- Build date: 2026-08-23
- Primary source: Lubemater WT 抗电蚀复合剂开发-20260510.xlsx
  SHA256: 2e22213dfea8f47594dcd21f0d796211c7f627d4de12aa30c322d84c53ce9f74
- 性质: EVIDENCE RECORD ONLY。SIGMA_MAX 提案是 owner-gate 输入，非最终冻结值。

## 0. 结论摘要

- 实测能力层: SIGMA_MAX = TO_BE_CHARACTERIZED（历史无干净可估重复组）
- 工程需求层: SIGMA_MAX_REQUIREMENT = 0.5h（推导链见 Section 3；k=3, Δ=1.5h）
- 右删失 10h 永不作为 event_time=10h 使用（binding rule）

## 1. 历史重复性数据盘点（穷举）

筛选条件: 同配方、同电流族、无中途设备干预。逐列扫描 ASA#4验证 + 前期验证全部 42 列。

### 1.1 干净重复对

| 对 | 运行 | 条件 | 观测 | 差异 | 判定 |
|----|------|------|------|------|------|
| P1（唯一干净对） | ASA4V_R(260119) / T(260128) | 嘉实多+2%ASA#4，标准电流 | 2.5h / 2.5h，结局一致（外圈电蚀内圈磨损） | Δ=0 | 一致 |
| P2 | ASA4V_AB(260415) / AC(260420) | 美孚+2%ASA#4 @6A | 8h / 6h | Δ=2h | CONFOUNDED: AC 备注「重调复测」「设备问题?」，中间有设备重调 |

P1 provenance caveat: R/T 的测试照片文件名写 ASA#2（260119/260128），
工作表写 ASA#4。剂名冲突未解决前该对的材料身份存疑（见 KNOWN_BAD_DOSSIER Section 1）。

### 1.2 结局一致性对（非重复）

AE/AF（260507/260509）: 浑浊5%样 2h vs 澄清1%样 5h — 不同样品，仅说明不同结局可复现方向，不进入重复性计算。

## 2. 可估计连续响应的重复性评估

主响应 time-to-first-reach-65dB:

- 干净未删失重复观测: 仅 P1 = {2.5, 2.5}。
- n=2 样本 sd = 0（数学事实），但统计上不可估 σ；
  且 P1 材料身份带 provenance caveat。故能力层结论: TO_BE_CHARACTERIZED。
- P2 若强行使用: range=2h → d2(n=2)=1.128 → sigma_hat≈1.77h，
  但设备重调混杂使该值无解释力。记录备查，不采信。

删失纪律核查:
- D(251215) 与 AD(260421) 为 10h 删失运行（AD 含滑脱+拟合21h，禁用）;
  本文件任何计算均未将其作为 event_time=10h。

固定时点噪声: 历史日志粒度不足以回填 noise@1h/@2h（见 Q2B 文件），无法回溯评估。

## 3. SIGMA_MAX 推导链

工程需求层（plan Section 4 公式: proposal ≤ Δ/k）:

- Δ 定义: S1 必须区分的最小 Good-Bad 响应差。
- 历史锚点: 同期对照 JP20260301001 p6 — 加剂 M+ 4.5h vs 空白 M 2.5h → Δ=1.5h。
- k=3（默认）。
- SIGMA_MAX_REQUIREMENT = Δ/k = 0.5 h。

注意: 这是「方法需要达到的精度要求」，不是台架实际能力的证明。
能力层必须由 S1a 专用表征运行补齐（Section 5 plan）:
每臂 ≥3 有效重复，d2-based 或样本 sd 估计，且 Q2-A 结局一致为前置。

Δ 锚点敏感性: Δ 来自单对同期对照（n=1 pair）。若 owner 认为需区分更小差异
（如 1h），SIGMA_MAX_REQUIREMENT 相应收紧至 ~0.33h。此为 owner 裁决项。

## 4. S1b 启动条件绑定

按 plan: 能力层数值缺失时 S1b 不能启动。解冻路径:

1. S1a 专用表征运行: Good-candidate 臂 ≥3 重复 + Bad 臂 ≥3 重复;
2. 每臂先过 Q2-A（事件状态一致），再以未删失 event_time 或预注册固定时点噪声算 Q2-B;
3. 能力层 sigma ≤ 需求层 0.5h → 方法重复性证据成立;
4. 全链由 owner sign-off 冻结。

## 5. Owner sign-off

- Reviewed by: ____________ Date: ____________
- Decision: ACCEPT_DELTA_ANCHOR / PROVIDE_NEW_DELTA / HOLD
- Notes: ____________________________________________

