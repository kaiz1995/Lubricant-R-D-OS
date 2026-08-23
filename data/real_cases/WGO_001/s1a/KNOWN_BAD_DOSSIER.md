# WGO_001 S1a / WP-2 — Known Bad Dossier

- Artifact: KNOWN_BAD_DOSSIER.md
- Basis: WGO_001_S1A_METHOD_CHARACTERIZATION_PLAN.md @ f8ea247, Section 2
- Build date: 2026-08-23
- Primary source: Lubemater WT 抗电蚀复合剂开发-20260510.xlsx
  SHA256: 2e22213dfea8f47594dcd21f0d796211c7f627d4de12aa30c322d84c53ce9f74
- Reports: JP20260301001 / JP20260315001 / JP20260327001
- 性质: EVIDENCE RECORD ONLY。本文件不做 PASS 决定。

## 0. 结论

KNOWN_BAD = UNRESOLVED（CONDITIONAL_CANDIDATE 记录在案）
按 plan Section 2: 五项要求任一缺失即不得冻结。当前第 2、5 项缺失，第 1 项部分缺失。

## 1. 候选定义

高硫污染配方家族（全部含 2% ASA#4）:

| 候选 | 体系 | S 含量 | 结果 | 溯源 |
|------|------|--------|------|------|
| 主候选 V | 美孚/壳牌S5 = 9:1（质量比，模拟冲洗油残留 10%）+ 2% | 试验前 297 → 试验后 298 ppm | 3h 失效（内外电蚀） | JP20260315001 表1 + ASA4V_V(260306) |
| 主候选 W | 美孚在用油（冲洗油残留约 5-10%，含 S 体系）+ 2% | 247 → 249 ppm | 3h 失效 | JP20260327001 表1 + ASA4V_W(260324) |
| 次级佐证 R/T | 嘉实多 + 2%（备注「同为高S产品(H307方案?)」） | 未测 S | 复测 2.5h / 2.5h 一致 | ASA4V_R(260119) / T(260128)。Provenance caveat: 测试照片文件名写 ASA#2，与工作表 ASA#4 冲突未解决 |

对照组锚点: 清洁美孚 + 2% 有效（JP20260301001 p6: 加剂 4.5h vs 空白 2.5h），
同一加剂在高硫体系失效 — 构成「本污染物机制相关」的失效证据链核心。

## 2. 五项 gate 核查

| # | 要求 | 状态 | 说明 |
|---|------|------|------|
| 1 | Exact formulation | PARTIAL | V/W 配比、污染物身份（壳牌S5 / 冲洗油残留）、残留比例有报告级记录；批次号缺失 |
| 2 | Preparation SOP | MISSING | 仅「质量比 9:1」级描述；混兑温度/时间/均质方式/混兑后 QC 无正式记录 |
| 3 | Historical failure evidence tied to THIS mechanism | PRESENT | 三报告链: 清洁体系有效 → 含S体系失效（V、W 均 3h，电蚀纹路明显，报告图3）。「竞争吸附」机理为报告自述假说，不影响「该体系下加剂失效」事实成立 |
| 4 | Same-bench data | PRESENT | 全部同一台架、65dB 终点时代 |
| 5 | Safety handling sheet | MISSING | 证据包未见 |

## 3. 设计缺陷警示（新增发现，须 owner 裁决）

所有历史 Bad 臂均含 2% ASA#4，不存在「污染油不加剂」臂。
现有证据无法区分:
- H1: 高硫使基础体系本身变差;
- H2: 高硫使 ASA#4 失效（报告假说: 含S抗磨剂与磷酸酯端竞争吸附，JP20260315001 p4）。

Known Bad 用于方法区分度验证时两种定义语义不同:
- 定义 A「污染油不加剂」: 更简单的 Bad 参考，但偏离真实应用（真实场景是污染+加剂）;
- 定义 B「污染油 + 2% ASA#4」: 匹配应用场景，但把添加剂交互并入方法验证。

Owner 必须二选一，或双臂并行（预算 +runs，见 plan Section 5 上限）。

## 4. 解冻所需 owner 动作

1. 补正式制备 SOP（混兑比例、温度、时间、均质、QC）。
2. 补安全操作说明。
3. 批次可追溯记录。
4. 裁决 Bad 定义 A / B / 双臂。
5. 澄清 R/T 剂名冲突（ASA#2 照片名 vs ASA#4 工作表）及「H307方案?」指代。

## 5. Owner sign-off

- Reviewed by: ____________ Date: ____________
- Decision: FREEZE_AS_KNOWN_BAD（附补件清单）/ ADOPT_DEFINITION_A / ADOPT_DEFINITION_B / HOLD
- Notes: ____________________________________________

