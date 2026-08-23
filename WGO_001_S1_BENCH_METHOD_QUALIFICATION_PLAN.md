# WGO_001 - S1 Bench Method Qualification Plan

> Status: DRAFT for Review. S1 is a TEST METHOD QUALIFICATION GATE.
> Completing replicates is necessary, never sufficient, for PASS.

## 1. Purpose and Decision Rule

S1 answers exactly one question:

> Is the electrical-erosion bench, under BENCH_PROTOCOL_V2, a measurement
> instrument whose readings can support non-inferiority decisions?

Decision rule (pre-registered; no post-hoc relaxation):

| gate check | PASS criterion | data source |
|------------|----------------|-------------|
| Q1 discrimination | Known Good vs Known Bad separated with NO overlapping summary intervals | G/B run summaries |
| Q2 repeatability | per-arm sigma <= SIGMA_MAX pre-set by method owner before first run | replicate spread within arms |
| Q3 endpoint semantics | 65 dB = event endpoint (per project summary appendix A) confirmed in writing by method owner | method sign-off record |
| Q4 censoring semantics | 10h-no-event recorded as event_occurred=false + ADMINISTRATIVE_RIGHT_CENSOR at 10h; business PASS label deferred to owner | every run record |
| Q5 stop-reason discipline | stop_reason mandatory enum: COMPLETED / EVENT_OCCURRED / RIGHT_CENSORED / ADMINISTRATIVE_STOP / INVALID_RUN / UNKNOWN-forbidden | protocol V2 + run logs |
| Q6 drift control | blank-reference result within its historical control band in EVERY batch | batch control charts |

S1 overall = PASS only if ALL six checks pass. Any single FAIL -> HOLD,
protocol revision, re-run S1. No partial credit.

## 2. Test Articles

| arm | identity | role |
|-----|----------|------|
| BASELINE | Mobil low-S PAO new oil, no additive | primary reference |
| KNOWN_GOOD | BASELINE + ASA#4 at the dose the owner designates as reference (2% historically strongest signal) | positive control |
| KNOWN_BAD | BASELINE contaminated with high-S material (the documented performance-killing condition) | negative control |

Identity requirements for all three: supplier lot, batch number, water content,
preparation SOP logged. No anonymous materials.

Replication: >=3 valid runs per arm. A run is INVALID_RUN (excluded, replaced)
only for pre-defined equipment-fault conditions, logged with stop_reason;
never discarded for unwelcome results.

## 3. BENCH_PROTOCOL_V2 Fixed Elements

Fixed and logged per run: current setpoint, bearing lot, load, temperature,
run-in period, noise sampling rate, microphone position, endpoint rule
(65 dB sustained per appendix-A definition), hard time cap 10 h.

Pre-registration: this document plus final parameter values are frozen BEFORE
the first qualification run. Changes afterwards require a new protocol version
and full S1 restart.

## 4. Data Schema per Run (replay-compatible)

```json
{
  "run_id": "S1R-###",
  "arm": "BASELINE|KNOWN_GOOD|KNOWN_BAD",
  "replicate_index": 1,
  "event_occurred": false,
  "observation_time_h": 10.0,
  "endpoint_noise_db": null,
  "censoring_status": "ADMINISTRATIVE_RIGHT_CENSOR",
  "stop_reason": "COMPLETED|EVENT_OCCURRED|RIGHT_CENSORED|ADMINISTRATIVE_STOP|INVALID_RUN",
  "batch_reference": "...",
  "operator": "...",
  "bench_parameters": {"current_a": null, "bearing_lot": null}
}
```

UNKNOWN is NOT an allowed value of stop_reason. If information is missing at
run time, the run is INVALID_RUN by definition -- this kills E-10 recurrence
at the source.

## 5. Acceptance Statistics (descriptive, deterministic)

- Per arm: median, min, max of observation_time_h; event count.
- Q1 separation: KNOWN_BAD event times must be shorter than KNOWN_GOOD times
  beyond the combined replicate spread (no overlap of arm min/max envelopes);
- Q2 sigma estimate: range-based sigma (d2 method, n=3) or sample sd as
  pre-declared; compared against owner-set SIGMA_MAX;
- No p-values, no modeling: S1 is method qualification, not dose response.

SIGMA_MAX and the control band for Q6 are OWNER INPUTS required before first run.

## 6. Outputs

1. S1_QUALIFICATION_REPORT.md (six-check table, raw run table, verdict);
2. machine-readable S1_RESULTS.json with the run schema above;
3. BENCH_PROTOCOL_V2 signed;
4. go/no-go recommendation for S2 including the ASA#4 lower-bound decision input
   (0 / 0.5 / 1%) and whether ASA#4 remains an S2 factor at all.

## 7. Explicit Non-Goals

- No optimization, no DOE matrix, no candidate ranking in S1.
- No cross-era comparison with 75 dB or adjustment-period data.
- No claim about WGO cost-down feasibility.

## 8. Owner Inputs Required Before First Run

1. Reference dose for KNOWN_GOOD arm (default proposal: 2%);
2. High-S contamination recipe for KNOWN_BAD arm;
3. SIGMA_MAX acceptance value;
4. Blank-reference control band for Q6;
5. Written confirmation of endpoint/censoring semantics (Q3/Q4).
