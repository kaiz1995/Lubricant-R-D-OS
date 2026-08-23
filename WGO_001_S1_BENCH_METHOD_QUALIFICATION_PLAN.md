# WGO_001 - S1 Bench Method Qualification Plan

> Status: DRAFT for Review (amended per S1 Gate ruling). S1 is a TEST METHOD
> QUALIFICATION GATE. Completing replicates is necessary, never sufficient,
> for PASS.

## 0. Execution Path Selection (Evidence Audit)

S1 has two pre-defined paths:

- PATH 1 -- DIRECT QUALIFICATION: all owner inputs already have reliable
  physical/historical evidence; go straight to S1 execution.
- PATH 2 -- CHARACTERIZE FIRST (S1a -> parameter freeze -> S1b independent
  qualification): one or more critical inputs unresolved.

Audit of the five owner inputs:

| input | status | rationale |
|-------|--------|-----------|
| KNOWN_GOOD | UNRESOLVED | 2% ASA#4 is a historical descriptive local minimum, not an independently bench-qualified good reference |
| KNOWN_BAD | CANDIDATE only | high-S contamination direction documented but identity / prep SOP / failure dossier incomplete |
| SIGMA_MAX | TO_BE_CHARACTERIZED | no historical repeatability data exists; inventing 0.5h/1h prohibited |
| BLANK CONTROL BAND | TO_BE_ESTABLISHED | no stable historical blank-reference distribution; same-batch build-and-validate forbidden |
| ENDPOINT / CENSORING | DATA SEMANTICS FROZEN; business label HOLD | 65 dB = first-reach endpoint partially resolved (G-C); 10h-no-event business PASS deferred to owner |

PATH 2 SELECTED. Separate work package plan:
WGO_001_S1A_METHOD_CHARACTERIZATION_PLAN.md. This document defines the S1b
gate that S1a feeds.

## 1. Purpose and Decision Rule

S1 answers exactly one question:

> Is the electrical-erosion bench, under BENCH_PROTOCOL_V2, a measurement
> instrument whose readings can support non-inferiority decisions?

Decision rule (pre-registered; no post-hoc relaxation):

| gate check | PASS criterion | data source |
|------------|----------------|-------------|
| Q1 discrimination | Known Good vs Known Bad separated with NO overlapping summary intervals; if KNOWN_BAD remains UNRESOLVED after S1a, Q1 marked DISCRIMINATION_EVIDENCE_INCOMPLETE and S1 cannot PASS | G/B run summaries |
| Q2-A outcome concordance | replicate event/censoring states agree within each arm (3x NO_EVENT_WITHIN_10H = concordant; mixed NO_EVENT/EVENT = FAIL regardless of continuous spread) | replicate status records |
| Q2-B continuous repeatability | computed ONLY on estimable continuous quantities: uncensored event times and/or protocol-pre-registered fixed-timepoint noise (e.g. noise@1h); right-censored 10h observations NEVER treated as event_time=10h; result <= owner-set SIGMA_MAX frozen before first S1b run | estimable continuous responses |
| Q3 endpoint semantics | 65 dB = FIRST_REACH_65_DB confirmed in writing by method owner | method sign-off record |
| Q4 censoring semantics | every 10h-no-event recorded as event_occurred=false, event_time=null, ADMINISTRATIVE_RIGHT_CENSOR at 10h, method_outcome=NO_EVENT_WITHIN_10H; business_pass_label=null in raw layer | every run record |
| Q5 stop-reason discipline | stop_reason mandatory enum: COMPLETED / EVENT_OCCURRED / RIGHT_CENSORED / ADMINISTRATIVE_STOP / INVALID_RUN; UNKNOWN forbidden | protocol V2 + run logs |
| Q6 drift control | blank-reference result within FROZEN provisional control band in EVERY batch; band built in S1a from earlier batches, validated in S1b on independent new-batch data; same data never both builds and validates the band | batch control charts |

S1 overall = PASS only if ALL checks pass. Any single FAIL or
DISCRIMINATION_EVIDENCE_INCOMPLETE -> HOLD, protocol revision, re-run.
No partial credit.

## 2. Test Articles

| arm | identity | role |
|-----|----------|------|
| BASELINE | Mobil low-S PAO new oil, no additive | primary reference + blank control source |
| KNOWN_GOOD | selected via ladder in S1a WP-1 (NOT defaulted to 2% ASA#4) | positive control |
| KNOWN_BAD | frozen only if full dossier exists (identity, prep SOP, historical failure evidence); otherwise stays UNRESOLVED | negative control |

Identity requirements for all three: supplier lot, batch number, water content,
preparation SOP logged. No anonymous materials.

Replication: >=3 valid runs per arm. A run is INVALID_RUN (excluded, replaced)
only for pre-defined equipment-fault conditions, logged with stop_reason;
never discarded for unwelcome results.

## 3. BENCH_PROTOCOL_V2 Fixed Elements

Fixed and logged per run: current setpoint, bearing lot, load, temperature,
run-in period, noise sampling rate, microphone position, endpoint rule
(FIRST_REACH_65_DB), hard time cap 10 h, plus any fixed-timepoint noise reads
pre-registered for Q2-B (e.g. noise@1h).

Pre-registration: this document plus S1a-frozen parameter values are frozen
BEFORE the first qualification run. Changes afterwards require a new protocol
version and full S1 restart.

## 4. Data Schema per Run (replay-compatible)

    {
      "run_id": "S1R-###",
      "arm": "BASELINE|KNOWN_GOOD|KNOWN_BAD",
      "replicate_index": 1,
      "event_definition": "FIRST_REACH_65_DB",
      "event_occurred": false,
      "event_time_h": null,
      "observation_time_h": 10.0,
      "endpoint_noise_db": null,
      "fixed_timepoint_noise": {"noise_db_at_1h": null},
      "censoring_type": "ADMINISTRATIVE_RIGHT_CENSOR",
      "censor_time_h": 10.0,
      "method_outcome": "EVENT_OCCURRED|NO_EVENT_WITHIN_10H",
      "business_pass_label": null,
      "stop_reason": "COMPLETED|EVENT_OCCURRED|RIGHT_CENSORED|ADMINISTRATIVE_STOP|INVALID_RUN",
      "batch_reference": "...",
      "operator": "...",
      "bench_parameters": {"current_a": null, "bearing_lot": null}
    }

UNKNOWN is NOT an allowed value of stop_reason. If information is missing at
run time, the run is INVALID_RUN by definition -- this kills E-10 recurrence
at the source. The raw layer never writes PASS; business interpretation is a
separate later layer.

## 5. Acceptance Statistics (descriptive, deterministic)

- Per arm: event/censoring state list, event count, median/min/max of
  uncensored event times only;
- Q2-A: exact concordance of event states across replicates;
- Q2-B: range-based sigma (d2, n=3) or sample sd as pre-declared, computed on
  uncensored event times and/or fixed-timepoint noise; compared against
  owner-set SIGMA_MAX;
- No p-values, no modeling: S1 is method qualification, not dose response.

SIGMA_MAX and the frozen control band for Q6 come from S1a artifacts; they are
OWNER-GATE inputs required before the first S1b run.

## 6. Outputs

1. S1_QUALIFICATION_REPORT.md (check table incl. Q2-A/Q2-B split, raw run
   table, verdict);
2. machine-readable S1_RESULTS.json with the run schema above;
3. BENCH_PROTOCOL_V2 signed with frozen parameters from S1a;
4. go/no-go recommendation for S2 including ASA#4 lower-bound decision input
   (0 / 0.5 / 1%) and whether ASA#4 remains an S2 factor at all.

## 7. Explicit Non-Goals

- No optimization, no DOE matrix, no candidate ranking in S1.
- No cross-era comparison with 75 dB or adjustment-period data.
- No claim about WGO cost-down feasibility.
- No business PASS labels written into raw data.

## 8. Input Status Register (supersedes flat owner-input list)

| input | current status | route |
|-------|----------------|-------|
| KNOWN_GOOD reference | UNRESOLVED | S1a WP-1 ladder; 2% ASA#4 NOT auto-approved |
| KNOWN_BAD dossier | CANDIDATE, incomplete | S1a WP-2; freeze requires full dossier else UNRESOLVED |
| SIGMA_MAX | TO_BE_CHARACTERIZED | S1a WP-4 evidence package; must bind to engineering discrimination margin |
| Blank control band | NOT ESTABLISHED | S1a WP-3 builds provisional band V0 from batch data; S1b validates independently |
| Endpoint/censoring sign-off | data semantics frozen; business label HOLD | Q3/Q4 written confirmation still required before S1b |
