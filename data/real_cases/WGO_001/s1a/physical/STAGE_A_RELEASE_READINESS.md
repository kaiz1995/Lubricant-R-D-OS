# Stage A Release Readiness — WGO_001 / S1a

**Execution Package Draft Gate:** `PASS_FREEZE`

**Package status:** `DRAFT_NOT_RELEASED`

**Stage A Physical Execution:** `HOLD`

**Synthetic demo inputs:** `CONFIRMED`

The values below exercise the case flow only. They do not approve physical
parameters and do not authorize a run.

## 1. Reference identity freeze

Good and Bad remain characterization candidates; identity freeze does not
promote either to `KNOWN_GOOD` or `KNOWN_BAD`.

| reference role | sample/formula identity | material/batch basis | preparation/source reference | Owner | approved_at |
|---|---|---|---|---|---|
| `GOOD_CHARACTERIZATION_CANDIDATE` | `WGO001-S1A-GCC-20260401`; 1540 ester 98% + ASA4 active 2% | internal demo identifiers; source batches unavailable | 60 C / 60 min / 60 rpm / oil then additive / no rest | 张凯 | 2026-05-06 |
| `BAD_CHARACTERIZATION_CANDIDATE` | `WGO001-S1A-BCC-DEMO-001`; 1540 97.8% + ASA4 2.0% + demo high-S contaminant 0.2% | `DEMO-HS-001`; synthetic assumption | 60 C / 60 min / 60 rpm / oil then ASA4 then contaminant | 张凯 | 2026-05-06 |
| `BENCH_REFERENCE_BLANK` | `WGO001-S1A-BRB-20260506`; Mobil SHC 320 WT new oil | `WGO001-MOBILBLANK-20260506-01` | no additive / no intentional contamination | 张凯 | 2026-05-06 |

## 2. Event Detection Rule V1 freeze

Already fixed: `threshold_db=65.0` and
`comparator=GREATER_THAN_OR_EQUAL`.

Confirmed for synthetic demo:

- `signal_source=SELF_BUILT_ANALOG_POINTER_DISPLAY`
- `sampling_interval=CONTINUOUS_VISUAL_OBSERVATION`
- `instrument_resolution=1 dB`
- `rounding_rule=POINTER_SCALE_NO_ADDITIONAL_ROUNDING`
- `filtering_rule=NONE`; `weighting=NONE`
- `persistence_rule=continuous >=65 dB for 5 s`
- `missing_sample_rule=possible crossing not observed -> INVALID_RUN`

No raw trace is available. Event time is manually recorded to the nearest
minute. These assumptions are not valid physical-release evidence.

Demo Owner: 张凯; approved_at: 2026-05-06; physical approval: `null`.

## 3. Q2-B checkpoint freeze

Current candidates: `[1, 2] h`. Owner must either approve them or provide other
pre-registered `q2b_checkpoints_h` before release.

Synthetic demo `q2b_checkpoints_h`: `[1, 2]`

Status: `FROZEN_FOR_SYNTHETIC_DEMO`; physical approval: `null`.

Raw trace remains primary evidence. Checkpoints are derived metrics. Post-hoc
selection of a favorable formal checkpoint is prohibited.

## 4. Stage A execution-order freeze

Confirmed synthetic demo order for the existing `3 blocks × 3 roles` matrix:

| field | value |
|---|---|
| order method | `DETERMINISTIC_BALANCED_ORDER_V1` |
| randomization seed, if applicable | `NOT_APPLICABLE` |
| generated_at | `2026-08-24` |
| frozen_by | 张凯 |
| planned orders written to run matrix | `true` |

Block orders are R-G-B, B-R-G, and G-B-R. Actual order remains unfilled. This
demo order does not release physical execution.

## 5. Release finalization order

This A–I sequence is binding:

1. **A** — Owner parameters frozen.
2. **B** — Final execution order generated.
3. **C** — Execution artifacts updated.
4. **D** — JSON and semantic validation completed.
5. **E** — SHA-256 calculated.
6. **F** — Release Manifest populated.
7. **G** — Hashes verified.
8. **H** — Owner final authorization recorded.
9. **I** — `release_status=RELEASED_FOR_EXECUTION`.

Steps must not be reordered.

## 6. Release Gate

All 13 checklist conditions must simultaneously pass, plus Owner authorization.
`AGENT_WAIVER`, `PARTIAL_RELEASE`, and `SILENT_EXCEPTION` are prohibited.

If a deviation is proposed, create an Owner-approved `RELEASE_DEVIATION` with:

- `deviation_id`
- `affected_requirement`
- `reason`
- `risk`
- `owner`
- `approval`

No deviation currently exists. No deviation instance is created by this draft.

Owner final authorization: `null`; approved_at: `null`;
release status: `DRAFT_NOT_RELEASED`.
