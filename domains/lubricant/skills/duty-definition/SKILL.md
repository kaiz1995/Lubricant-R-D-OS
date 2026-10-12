---
name: duty-definition
description: Record one evidence-declared lubricant duty profile at DUTY_DEFINED; preflight verifies active upstream Project Charter and all 7 equipment operating conditions before building the artifact. Use when user mentions "duty-definition", "工况定义", "工况剖面", "duty profile", "设备工况", or advancing to Stage 1 in lubricant R&D.
---

# Duty Definition (Stage 1)

Record an evidence-declared lubricant duty profile at `DUTY_DEFINED` for the Lubricant R&D Domain Pack.
Authority schema: `../../schemas/duty.schema.json` (or local `references/duty.schema.json` in deployed bundle).

---

## 1. Prerequisites & Gating

Before requesting duty inputs or assuming a specific equipment type:
- An active Project Charter (`project.json`) MUST exist in the workspace with `stage: "PROJECT_DEFINED"` and `status: "ACTIVE"`.
- If missing, do NOT guess equipment conditions. Direct user to run `project-definition` first.

---

## 2. Input Specification

Input must be a single JSON object containing `project_artifact` and the `duty` specification covering all 7 mandatory conditions:

```json
{
  "project_artifact": "path/to/project.json",
  "duty": {
    "duty_id": "DUTY-WGO-001",
    "equipment": {
      "value": "Vestas V112 3.0MW WTG main gearbox, planetary + helical stages",
      "source": "OEM Technical Manual v2.1",
      "evidence_id": "EV-EQ-001",
      "statement": "Three-stage planetary/helical gearbox design",
      "status": "OBSERVED"
    },
    "operating_conditions": {
      "value": "Continuous variable speed 9-18 rpm main shaft, high torque",
      "source": "SCADA Field Data 2025",
      "evidence_id": "EV-OP-001",
      "statement": "High torque with dynamic gust loads",
      "status": "OBSERVED"
    },
    "maintenance": {
      "value": "Oil change interval 3-5 years, inline filter 10um",
      "source": "Service Protocol SOP-042",
      "evidence_id": "EV-MT-001",
      "statement": "Annual sample analysis, filtration replacement",
      "status": "OBSERVED"
    },
    "temperature": {
      "value": "Normal operating sump 65-80°C, peak contact >110°C, cold start -30°C",
      "source": "Thermal Monitoring Log",
      "evidence_id": "EV-TM-001",
      "statement": "Wide operational temperature range",
      "status": "OBSERVED"
    },
    "load": {
      "value": "Hertzian contact stress 1.4-1.8 GPa, heavy shock loads",
      "source": "Gear Stress FEA Report",
      "evidence_id": "EV-LD-001",
      "statement": "Boundary/elastohydrodynamic lubrication transition regime",
      "status": "OBSERVED"
    },
    "contamination": {
      "value": "Moisture < 200 ppm, ISO 4406 cleanliness 16/14/11",
      "source": "Offshore Environmental Spec",
      "evidence_id": "EV-CN-001",
      "statement": "High salinity and moisture condensation risk",
      "status": "ASSUMED"
    },
    "life": {
      "value": "L10h design life >= 175,000 hrs (20 years)",
      "source": "Reliability Requirement Doc",
      "evidence_id": "EV-LF-001",
      "statement": "Long-life expectation with minimum degradation",
      "status": "OBSERVED"
    }
  }
}
```

### Invariants
- Mandatory 7 items: `equipment`, `operating_conditions`, `maintenance`, `temperature`, `load`, `contamination`, `life` must all be present.
- Evidence integrity: Every item must have non-empty `value`, `source`, `evidence_id`, `statement`, and `status` (`OBSERVED` or `ASSUMED`).
- Status preservation: Preserve declared assumptions; NEVER upgrade `ASSUMED` to `OBSERVED` without physical test verification. Any `GAP` status results in `HOLD`.

---

## 2A. Precision-Gear Grease Route (`project_type: "PRECISION_GREASE_DEV"`)

`schemas/duty.schema.json` keeps the legacy seven in `required` for every route; the shared
contract may only gain optional properties. The grease route therefore gets its own
dimension set from the policy layer (`scripts/duty_definition_policy.py`), which reads the
upstream project's `project_type` and returns the required set. Both sets are enforced for
this route: the legacy seven (so the shared contract is satisfiable) and the grease seven.

### The seven grease dimensions

| Dimension | Records | Why |
|---|---|---|
| `motion_regime` ★ | Oscillation amplitude, frequency, cycle count, bidirectional duty | Drives fretting wear, the core failure mode of a harmonic-drive flexspline |
| `contact_pair` ★ | Flexspline / rigid-wheel materials, DLC coating (presence and film system), seal and plastic-part materials | Determines the interface-compatibility CTQ |
| `temperature_and_heat_source` | Service temperature window plus heat source (servo rise, continuous-duty rise) | Bounds low-temperature start-up torque against high-temperature oil separation |
| `torque_requirement` ★ | Low-temperature start-up torque ceiling, no-load breakaway torque, running torque | Grease hardening shows up as out-of-specification torque; the number-one field complaint |
| `fill_and_assembly` ★ | Fill mass / fill ratio, assembly method | An assembly parameter that determines grease performance: fill quantity drives temperature rise and start-up torque |
| `life_and_maintenance` | Maintenance-free whole-life target, target hours, replenishment possible or not | The grease must outlive the reducer design life with no replenishment |
| `sealing_and_contamination` | Seal class, whether external media are contacted | Retained but simplified to one sealing-integrity dimension |

### The two lifeline (命门) dimensions
`motion_regime` and `torque_requirement` are mandatory for this route and are reported with
their own error wording when absent:
`HOLD: ... duty.motion_regime is a required lifeline (命门) dimension for PRECISION_GREASE_DEV`.
Every grease dimension must carry `source` and `evidence_id`; a provenance-free dimension is
a hard reject (`NO Provenance-Free Parameters`), never a warning.

### What the oil routes see
Unchanged. For any of the six oil project types the policy returns the legacy seven, in the
legacy order, with the legacy error strings; the grease dimensions are simply omitted.

---

## 3. Deterministic Execution Workflow

All scripts reside in `skills/duty-definition/scripts/` (or relative `scripts/` from the skill directory).

### Step 1: Preflight Verification
```bash
python skills/duty-definition/scripts/preflight_duty_definition.py <input.json>
```
- Expected output on success: `READY: input can form one DUTY_DEFINED record only` (exit code 0).
- If preflight fails: Outputs `HOLD: ...` and exits code 1.
- The preflight reads the upstream `project.json` (it already validates it) and passes its
  `project_type` into the policy layer, which selects the required dimension set.

### Step 2: Build Deterministic Artifact
```bash
python skills/duty-definition/scripts/build_duty_artifact.py <input.json> <temporary-file.json>
```
- The builder records the dimensions the policy selects for this route: the legacy seven for
  the oil routes, the legacy seven plus the grease seven for `PRECISION_GREASE_DEV`.

### Step 3: Validate Artifact
```bash
python skills/duty-definition/scripts/validate_duty_artifact.py <temporary-file.json>
```
- Expected output on success: `PASS: duty artifact conforms to the Stage 1 contract` (exit code 0).
- The validator re-runs the same policy check over the artifact. It sees no project type, so a
  grease-shaped artifact (one recording a grease dimension) is enforced as the grease route and
  an oil artifact resolves to the legacy set.

### Step 4: Atomic Commit & Checkpoint
Atomically copy/move `<temporary-file.json>` to `<output.json>` (defaults to `duty.json`) only after Step 3 passes.
```bash
# 🔴 CHECKPOINT · STOP: Stage 1 stops here at DUTY_DEFINED. Pass to Stage 2 (duty-challenge-analysis).
```

---

## 4. Failure Modes & Fallback Recovery (Fail-Closed)

| Failure Symptom | Root Cause | Fallback Recovery Action |
|---|---|---|
| `HOLD: project_artifact is missing or not active` | 缺少有效的 Project Charter | **STOP**。提示用户先运行 `project-definition` 完成立项并获取 `project_id`。 |
| `HOLD: missing duty condition [field]` | 7 项工况剖面存在遗漏 | **STOP**。明确告知具体遗漏的条件项（如缺少 contamination 或 life），等待用户补齐。 |
| `HOLD: ... duty.motion_regime is a required lifeline (命门) dimension for PRECISION_GREASE_DEV` | 精密脂路线缺少运动制度或力矩要求 | **STOP**。这是谐波脂的两个命门维度（微振磨损 / 低温启动扭矩）；不得用 ASSUMED 之外的猜测填充，须由客户工况输入补齐或显式记 ASSUMED + 来源。 |
| `HOLD: missing duty condition <grease dimension>` | 精密脂路线缺少七维之一 | **STOP**。列出缺失的脂维度（`contact_pair` / `temperature_and_heat_source` / `fill_and_assembly` / `life_and_maintenance` / `sealing_and_contamination`）等待补齐。 |
| `HOLD: ... duty.<dimension>.source / .evidence_id` | 维度缺来源或凭据（`NO Provenance-Free Parameters`） | **STOP**。这是硬拒绝不是警告；要求提供可核来源与 evidence_id。 |
| `HOLD: evidence contains GAP` | 工况指标未定义且处于未知缺口 | **STOP**。输出缺口报告并保持 HOLD，禁止猜测默认环境数值。 |
| `FAIL: cannot read artifact or schemas` | 输入损坏或 Schema 不可达 | 检查输入文件与 `../../schemas/duty.schema.json` 路径。 |

---

## 5. Strict Blacklist (Prohibitions)

1. **NO Status Upgrading**: DO NOT upgrade `ASSUMED` evidence to `OBSERVED` without documented empirical logs.
2. **NO Hallucinated Conditions**: DO NOT invent operating temperature, speeds, or contact stresses when unspecified.
3. **NO Downstream Spillover**: DO NOT derive Challenge Maps, CTQs, formulation recipes, or DOE matrices in this skill.
4. **NO Dirty Overwrites**: DO NOT overwrite existing duty files with mismatched `project_id` or `duty_id`.
5. **NO Provenance-Free Parameters**: For the grease route, a grease dimension lacking `source` or `evidence_id` is a hard reject, not a warning. The two lifeline dimensions (`motion_regime`, `torque_requirement`) may be recorded `ASSUMED` with an explicit source, but never dropped and never filled with an invented value.

