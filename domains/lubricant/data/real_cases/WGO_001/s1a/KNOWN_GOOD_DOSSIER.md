# WGO_001 S1a / WP-1 — Known Good Reference Dossier

- Artifact: KNOWN_GOOD_DOSSIER.md
- Basis: WGO_001_S1A_METHOD_CHARACTERIZATION_PLAN.md @ f8ea247, Section 1
- Build date: 2026-08-23
- Primary source: Lubemater WT 抗电蚀复合剂开发-20260510.xlsx
  SHA256: 2e22213dfea8f47594dcd21f0d796211c7f627d4de12aa30c322d84c53ce9f74
- Reports: JP20260301001（台架方案）/ JP20260315001（清洗油模拟）/ JP20260327001（在用油）
- 性质: EVIDENCE RECORD ONLY。本文件不做 PASS 决定；S1b 才做独立验证。
- 运行编号约定: ASA4V_X = 工作表「ASA#4验证」X 列；QZ_X = 工作表「前期验证」X 列。

## 0. 结论

KNOWN_GOOD = UNRESOLVED
2% ASA#4 = CHARACTERIZATION_CANDIDATE（仅限 owner 批准后的表征运行，不构成 Known Good）

## 1. Ladder 评估

### Rung 1 — 成熟长期稳定 good reference（任意摩擦学台架有书面无失效史）

NOT MET。三份报告与六张工作表中无任何油品被记录为 positive control，
也无任何材料的跨周期无失效历史。此空缺是证据缺失而非否定存在；
owner 需正面回答是否存在此类材料（Section 5）。

### Rung 2 — V2 或有记录前身协议下的稳定 10h 无事件参考油

| 候选 | 运行溯源 | 协议状态 | 观测 | 判定 |
|------|----------|----------|------|------|
| 美孚空白（Mobil SHC 320 WT 新油） | ASA4V_D，test 251215 | 标准电流族；新组装台架调试期（工作安排!B2 于 20251218 官方记录苛刻度下降） | 10h 未达65dB（末读61dB）；event_occurred=false；ADMINISTRATIVE_RIGHT_CENSOR@10h | n=1 无法证明稳定性，且处调试期。FAIL |
| 美孚空白低电流臂 | ASA4V_X(9A,260401) / Y(6A,260402) / Z(3A,260409) | 非标准电流（标准 13.5A nominal，12-14A 区间） | 5h / 9.5h / 10h+58dB（轴承滑脱，拟合20h） | 排除：非标准电流；Z 为拟合值非实测，禁用 |
| 0.5% / 1% ASA#4 剂量臂 | ASA4V_B(251211,62dB) / C(251212,56.5dB)，均 10h 删失 | 新台架首批运行；B 备注「新组装台架测试条件不如以往苛刻，原因不明」 | 双删失 | 含剂表征臂，非 reference oil。排除 |

结论: NOT MET。标准电流下唯一 10h 无事件观测 n=1 且带调试期混杂。

## 2. 2% ASA#4 characterization candidate 记录

支持证据（为何可作为表征臂，而非 Known Good）：

1. 同期对照: JP20260301001 p6 — 同批空白 M 2.5h 达 65dB（通电 2h），
   加剂 M+ 4.5h（通电 4h）。方向一致、条件配对。
2. 标准电流 2% 重复观测: ASA4V_I(251223)=5h；ASA4V_P(260105，原料脱水预处理)=5h。
   ASA4V_F(251218)=9h 带「7.5h 调试后续测」混杂，仅作背景。
3. 非标准电流臂背景: S(12A)=5h、AA(9A)=8.5h、AB(6A)=8h、AC(6A 重调)=6h。
4. 前期验证 K/L（白色美孚+2%）: 5.5h 与 8h 复测，方向一致但属旧协议期，仅背景。

封 Known Good 的缺口（plan Section 1 字段逐项）:

| 字段 | 状态 | 证据 / 缺口 |
|------|------|-------------|
| material identity | PARTIAL | 正式报告称 AEA#4（JP20260301001 p2-p3），工作表通篇称 ASA#4。日期与数据链高度对应，推定同一物质，但无任何文件显式确认两命名体系同一性；另有照片文件名写 ASA#2 的冲突先例（见 KNOWN_BAD_DOSSIER）。IDENTITY_CONFIRMATION_REQUIRED |
| supplier / product code | PARTIAL | 内部开发品（青岛中科润美），无独立供应商料号 |
| lot / batch | MISSING | 历史各次试验原料批次号均未记录 |
| base oil chemistry class | KNOWN | Mobil SHC 320 WT 等（另试壳牌/嘉实多/CF-30低S/白色美孚） |
| additive system description | PARTIAL | 结构特征有描述（定向吸附磷酸酯端 + 醇醚链段，报告 p2）；具体组分与配比无 |
| water content | CRITICAL GAP | ASA4V_P 备注：ASA#4 原料含水 28%，经 80℃/17d 烘箱脱水至 0.46%。历史多数试验使用未脱水原料。水分是横贯全部历史数据的未控变量 |
| evidence citations | PRESENT | 见上，sheet!cell 级溯源 |
| storage / prep SOP | MISSING | 仅散落制备备注（如 60℃/3d 静置溶解），无正式 SOP |

判定依据: plan Section 5 允许 owner 批准后将 2% ASA#4 作为 method-characterization
材料进入表征运行；结果只描述台架局部响应面，不合格化为 Known Good。

## 3. 对 S1 gate 的影响

- Known Good 缺位时，Q1 区分度只能以 characterization candidate 替代或标记
  DISCRIMINATION_EVIDENCE_INCOMPLETE，由 S1 gate 裁决。
- S1b 启动前必须完成其一: (a) owner 提供 rung-1/rung-2 参考油；
  (b) S1a 专用表征运行产生新参考证据; (c) owner 明确接受 INCOMPLETE 并降级 S1 目标。

## 4. Owner 输入请求

1. 是否存在成熟 long-term-stable good reference（rung 1）？若有，提供身份/批次/历史。
2. 确认 ASA#4 与 AEA#4 物质同一性（一份对照记录即可）。
3. 提供历史试验批次与原料水分记录（尤其 28% 含水原料的使用范围）。
4. 若确认无 Known Good: 批准 2% ASA#4 作为表征臂进入 S1a 专用运行（预算上限见 plan Section 5）。

## 5. Owner sign-off

- Reviewed by: ____________ Date: ____________
- Decision: GO_CHARACTERIZATION_ARM / SUPPLY_REFERENCE / HOLD
- Notes: ____________________________________________

