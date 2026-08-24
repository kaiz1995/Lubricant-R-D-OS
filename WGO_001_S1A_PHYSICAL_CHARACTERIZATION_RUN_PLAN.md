# WGO_001 - S1a Physical Characterization Run Plan

> Document status: **DRAFT_NOT_RELEASED**
>
> Execution Package Authoring: **PASS/FREEZE**
>
> Execution Package Draft Gate: **PASS/FREEZE**
>
> Release Readiness Demo: **PASS/FREEZE**
>
> Stage A Physical Run Release: **HOLD**
>
> Owner sign-off: **NOT COMPLETE**
>
> Input scope: **SYNTHETIC_DEMO_ONLY** — these entries are demonstration
> inputs, not real-experiment qualification or physical-run authorization.
> Evidence status: **SYNTHETIC_DEMO_ASSUMPTION**; physical method authority:
> **NONE**.

## 1. Purpose and boundaries

This package defines the physical-run sequence that may be released only after
the checklist in Section 12 is complete. It creates characterization evidence;
it makes no business PASS decision and does not release S1b, S2, Phase 3, or
Phase 4.

Roles are intentionally separate:

| role | material | permitted use |
|---|---|---|
| `BENCH_REFERENCE_BLANK` | `WGO001-S1A-BRB-20260506`; Mobil SHC 320 WT; new; no additive; no intentional contamination; container `WGO001-MOBILBLANK-20260506-01` | Synthetic demo input only |
| `PROJECT_BASELINE_WGO` | current formal WGO baseline | later S2 / non-inferiority baseline only |
| `GOOD_CHARACTERIZATION_CANDIDATE` | `WGO001-S1A-GCC-20260401`; 1540 ester 98 wt% + ASA4 active 2 wt%; water 1%; 60 C/60 min/60 rpm; oil then additive; no rest | Synthetic demo input only |
| `BAD_CHARACTERIZATION_CANDIDATE` | `WGO001-S1A-BCC-DEMO-001`; 1540 97.8 wt% + ASA4 2.0 wt% + `DEMO_HIGH_S_CONTAMINANT` 0.2 wt%; contaminant `DEMO-HS-001`; 60 C/60 min/60 rpm; oil then ASA4 then contaminant | Synthetic demo input only |

`BENCH_REFERENCE_BLANK` is not `PROJECT_BASELINE_WGO`; their evidence and
decision roles must not be substituted or pooled.

## 2. Binding endpoint and censoring semantics

- Event definition: `FIRST_REACH_65_DB` (first reach of 65 dB).
- A run with no event by 10 h is an administrative right-censor at 10 h:
  `event_occurred=false`, `event_time_h=null`,
  `censoring_type=ADMINISTRATIVE_RIGHT_CENSOR`, and
  `method_outcome=NO_EVENT_WITHIN_10H`.
- `NO_EVENT_WITHIN_10H` must never map to business `PASS`.
- The 10 h endpoint is `ADMINISTRATIVE_10H_END`, not an event.

## 3. Stage A1 release package (nine runs / three blocks)

Stage A1 contains exactly the following planned valid runs:

| arm | valid replicates | planned count |
|---|---:|---:|
| `GOOD_CHARACTERIZATION_CANDIDATE` | 3 | 3 |
| `BAD_CHARACTERIZATION_CANDIDATE` | 3 | 3 |
| `BENCH_REFERENCE_BLANK` | 3 | 3 |
| **total** |  | **9** |

A1 is divided into exactly three blocks. Each block contains exactly one
`GOOD_CHARACTERIZATION_CANDIDATE`, one `BAD_CHARACTERIZATION_CANDIDATE`, and
one `BENCH_REFERENCE_BLANK`. The package must not be executed as three GOOD,
then three BAD, then three BLANK runs. The released planned order is not yet
frozen: `planned_run_order=null` until owner approval. `actual_run_order` stays
null until execution and then records the observed sequence. Any change after
release is an execution-order deviation and requires a documented deviation
reason. Before release, Owner must first freeze all required parameters; only
then may the within-block order be generated and its method, seed (when
applicable), generation time, and approver recorded with the frozen order.

Every run records material identity, lot/batch, preparation SOP, operator,
bench parameters, batch reference, event/censoring fields, stop reason, and
legacy provenance where applicable. Replacement runs are permitted only for
validly documented `INVALID_RUN` records; a replacement does not erase the
original record.

## 4. Stop-reason and invalid-run discipline

`STOP_REASON_V1` is the only allowed stop-reason enum:

    EVENT_REACHED
    ADMINISTRATIVE_10H_END
    EQUIPMENT_FAULT
    POWER_INTERRUPTION
    OPERATOR_ABORT
    SAMPLE_ANOMALY
    OTHER_DOCUMENTED

`UNKNOWN` is prohibited. `OTHER_DOCUMENTED` requires a non-empty `detail`.
If the observed stop cannot be legally classified, set `run_status=INVALID_RUN`,
write a deviation-log entry, preserve all available raw evidence, and exclude
the run from Q1 and Q2. It cannot be silently recoded or discarded.

## 5. Legacy-value compatibility

Legacy values remain preserved as provenance, not rewritten as if they were
native `STOP_REASON_V1` records:

| legacy value | allowed mapping context |
|---|---|
| `COMPLETED` | maps only with evidence of ordinary completion; classify event versus administrative censoring from endpoint/censoring evidence |
| `EVENT_OCCURRED` | maps to `EVENT_REACHED` only with first-reach event evidence |
| `RIGHT_CENSORED` | maps to `ADMINISTRATIVE_10H_END` only with 10 h administrative-censor evidence |
| `ADMINISTRATIVE_STOP` | maps only when the recorded administrative cause supports the target value |
| `INVALID_RUN` | remains invalid; retain supporting deviation evidence |

Ambiguous legacy values must not be automatically mapped. Retain the original
value and provenance, record the ambiguity, and exclude the record from Q1/Q2
until owner resolution.

## 6. Stage A2 conditional bridge (not released)

`PROJECT_BASELINE_BRIDGE` consists of three valid replicates of
`PROJECT_BASELINE_WGO`. It is permitted only after A1 is judged
`PROMISING` by the owner under the released review record. A2 is currently
**NOT RELEASED**; no physical A2 run is authorized by this document.

## 7. Q2-B observation rule

The 1 h and 2 h observations are only
`PROVISIONAL_CANDIDATE_CHECKPOINTS`. For synthetic demonstration only, their
selection is `FROZEN_FOR_SYNTHETIC_DEMO`; this is not physical release approval
and does not make either checkpoint an acceptance input.

    q2b_checkpoint_candidates_h: [1, 2]
    checkpoint_status: FROZEN_FOR_SYNTHETIC_DEMO
    observation_method: MANUAL_POINTER_1_DB
    post_hoc_selection: PROHIBITED

Physical execution still requires owner sign-off and a formally released set.

### 7.1 Raw-signal preservation

When the instrument can export a complete time series, preserve that immutable
raw trace and record `raw_signal_reference` plus `raw_signal_sha256`. Q2-B
checkpoints are pre-registered derived metrics; they do not replace raw evidence.
Post-hoc selection of a favorable checkpoint is prohibited.

## 8. Event-detection method freeze

The event threshold is `threshold_db=65.0` with
`comparator=GREATER_THAN_OR_EQUAL`. For synthetic demonstration only, the method
is `FROZEN_FOR_SYNTHETIC_DEMO`: `SELF_BUILT_ANALOG_POINTER_DISPLAY`; continuous
visual observation; 1 dB resolution; no weighting or filter; pointer-scale
reading without additional rounding; continuous >=65 dB for 5 s; missing
observation around a crossing makes event time not estimable and the run
`INVALID_RUN`; manual timestamps use the nearest minute; raw trace is
unavailable. These values do not satisfy the physical release gate.

## 9. Stage A1 characterization gate

After nine released, valid A1 runs are complete, the review answers:

1. Do the reference roles show gross discrimination?
2. Are replicate event/censoring states concordant within each role?
3. Were any runs invalid, and do their deviations undermine interpretation?
4. Does `BENCH_REFERENCE_BLANK` indicate material bench drift?
5. Was `FIRST_REACH_65_DB` executed consistently?
6. Is an estimable continuous Q2-B response available?
7. Should each candidate reference be retained?

Only these decisions are allowed:

- `PROMISING`: evidence justifies Stage A2 and further characterization;
- `REVISE`: revise protocol/reference, then repeat Stage A1;
- `FAIL`: Test Method Qualification remains HOLD.

This gate must never output `METHOD_QUALIFIED`. S1b remains the independent
qualification gate.

## 10. Q6 control-band status

`CONTROL_BAND_V0` is `PROVISIONAL`, `CONFOUNDED`, and
`INFORMATIONAL_REFERENCE_ONLY`. It must not be used for formal `PASS`/`FAIL`,
process capability, or a final control limit. A blank anomaly is only a
`DRIFT_SIGNAL` requiring investigation; engineering review then routes the A1
review to `PROMISING` or `REVISE`. Stage B may establish a
`CONTROL_BAND_V1` candidate.

## 11. Release Manifest and immutability

`S1A_STAGE_A_RELEASE_MANIFEST.json` is currently a draft template. At release,
it must contain the approved identities, protocol, Q2-B checkpoints,
event-detection rule version, and verified SHA-256 values for all five execution
artifacts. Draft manifests retain `sha256=null`; hashes are not calculated until
the release set is frozen. Released artifacts are immutable for that release version. A later
change requires a new release whose manifest marks the prior version
`SUPERSEDED` or `VOID`; approved artifacts are never overwritten in place.

## 12. Release checklist (all conditions required)

| # | release condition | current status |
|---|---|---|
| 1 | `GOOD_CHARACTERIZATION_CANDIDATE` identity frozen | HOLD — synthetic demo input only; not physical release evidence |
| 2 | `BAD_CHARACTERIZATION_CANDIDATE` identity frozen | HOLD — synthetic demo input only; not physical release evidence |
| 3 | `BENCH_REFERENCE_BLANK` identity frozen | HOLD — synthetic demo input only; not physical release evidence |
| 4 | `STOP_REASON_V1` frozen | MET — frozen by this package |
| 5 | Q2-B checkpoints owner-approved | HOLD |
| 6 | protocol version frozen | HOLD |
| 7 | 65 dB event endpoint owner-confirmed and frozen | HOLD |
| 8 | 10 h censoring semantics owner-confirmed and frozen | HOLD |
| 9 | operator/equipment record fields ready | MET — template fields present |
| 10 | Owner release sign-off complete | HOLD |
| 11 | Stage A blocking and execution order frozen, with generation provenance | HOLD |
| 12 | Event signal source, sampling interval, resolution, rounding, filtering, persistence, and missing-sample rules frozen | HOLD |
| 13 | Release Manifest generated and all listed artifact hashes verified | HOLD |

All 13 conditions must be simultaneously `PASS` plus Owner authorization before
`RELEASED_FOR_EXECUTION` is permitted. `AGENT_WAIVER`, `PARTIAL_RELEASE`, and
`SILENT_EXCEPTION` are prohibited. Any deviation requires an Owner-approved
`RELEASE_DEVIATION`; it does not create a 14th condition. Failure or absence of
any condition leaves Stage A release as HOLD.

## 13. Downstream status

| item | status |
|---|---|
| S1b independent qualification | HOLD / no change |
| S2 design space and non-inferiority work | HOLD / no change |
| Phase 3/4 frozen schemas, engines, fixtures | NO CHANGE |

## 14. Release readiness entry

The Execution Package Draft Gate is `PASS/FREEZE`. Synthetic demo inputs and a
balanced demo order are confirmed. They do not release physical runs; physical
Release Readiness and Manifest finalization remain HOLD.
