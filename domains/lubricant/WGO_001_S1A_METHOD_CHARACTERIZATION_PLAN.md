# WGO_001 - S1a Method Characterization Plan

> Status: DRAFT for Review. S1a produces EVIDENCE, not acceptance decisions.
> Its outputs feed the S1b gate defined in WGO_001_S1_BENCH_METHOD_QUALIFICATION_PLAN.md.
> S2 Design Space / DOE Matrix remain HOLD until S1 method qualification passes
> plus G-A cost resolution and Material Admission Gate.

## 0. Why S1a Exists

S1 Gate ruled: parameters without physical evidence must be characterized,
not invented. S1a answers five questions with data:

| WP | question | output artifact |
|----|----------|-----------------|
| WP-1 | What is a real Known Good reference? | KNOWN_GOOD_DOSSIER.md |
| WP-2 | Is the high-S candidate a valid Known Bad? | KNOWN_BAD_DOSSIER.md or UNRESOLVED record |
| WP-3 | What is the blank-reference control band? | CONTROL_BAND_V0.json + rationale |
| WP-4 | What repeatability does this bench actually have? | REPEATABILITY_EVIDENCE.md + SIGMA_MAX proposal |
| WP-5 | Which fixed-timepoint noise reads are stable enough for Q2-B? | Q2B_METRIC_SELECTION.md |

S1a completion = all five artifacts exist and are owner-reviewed. It does NOT
by itself PASS anything; S1b validates independently.

## 1. WP-1 Known Good Reference Ladder (no default to 2% ASA#4)

Selection ladder (first hit wins; each rung requires written evidence):

1. Mature long-term-stable good reference oil already used as a positive
   control on ANY tribology bench, with documented no-failure history;
2. Reference with stable 10h-no-event evidence under BENCH_PROTOCOL_V2 or its
   documented predecessor;
3. Neither available -> KNOWN_GOOD stays UNRESOLVED. Do not fabricate.

2% ASA#4 may only enter as a characterization candidate (see Section 5), never
as an assumed Known Good.

Dossier fields required for freeze: material identity (supplier, product code),
lot/batch, base oil chemistry class, additive system description, water content,
evidence citations (which runs, which bench, which dates), storage/prep SOP.

## 2. WP-2 Known Bad Dossier Requirements

The high-S contamination candidate freezes as KNOWN_BAD only when ALL exist:

1. Exact formulation (contaminant identity, concentration, carrier oil);
2. Preparation SOP (mixing, temperature, hold time, QC check);
3. Historical failure evidence tied to THIS contaminant mechanism
   (not merely "high sulfur is bad in general");
4. Preferably same-bench or near-protocol historical data; cross-era 75 dB data
   is supporting context, not qualification evidence;
5. Safety handling sheet.

If any item is missing -> KNOWN_BAD = UNRESOLVED. S1b then cannot claim full
discrimination evidence (Q1 marked DISCRIMINATION_EVIDENCE_INCOMPLETE) and S1
cannot PASS until resolved by owner decision or new evidence.

## 3. WP-3 Control Band V0 (build now, validate later)

Data sources (priority order):

1. Existing BASELINE-equivalent runs under comparable protocol elements
   (same endpoint rule where known, same current setpoint family);
2. New dedicated blank-reference characterization runs (see Section 5);

Prohibited: using the same batch of data to both establish the band and prove
the band holds.

Band definition (descriptive, deterministic):

- n >= 6 usable blank-reference observations preferred; document actual n;
- metric per run: pre-registered continuous descriptor (e.g. noise@1h, or time
  to fixed dB threshold if estimable);
- provisional band V0 = min..max envelope plus median, recorded explicitly as
  PROVISIONAL_ENGINEERING_BOUND built from characterization batch(es);
- frozen before first S1b batch; S1b validates on independent new batches.

Output: CONTROL_BAND_V0.json containing metric name, unit, n, source run ids,
min/median/max, build date, status=PROVISIONAL.

## 4. WP-4 Repeatability Evidence and SIGMA_MAX Proposal

Sources:

1. Any historical repeat-pair/triplicate data under comparable conditions --
   analyze descriptively (range, d2-based sigma estimate for n=3, sample sd);
2. If none exists: dedicated characterization replicates (Section 5).

Censoring discipline (binding): right-censored 10h observations are NEVER used
as event_time=10h. Continuous repeatability is computed only on:

- uncensored event times; and/or
- pre-registered fixed-timepoint noise values (WP-5 metrics).

Outcome concordance is reported alongside: if replicate event states disagree,
continuous spread is irrelevant -- that configuration FAILS Q2-A at S1b.

SIGMA_MAX derivation (owner-gate input):

    engineering discrimination margin Delta =
      smallest difference between Good and Bad responses that S1 must detect
    SIGMA_MAX proposal <= Delta / k, with k declared (default k=3)

If neither historical nor new characterization data supports a number,
SIGMA_MAX remains TO_BE_CHARACTERIZED and S1b cannot start. Inventing a value
is prohibited.

Output: REPEATABILITY_EVIDENCE.md (data table, computation method, censoring
handling, proposed SIGMA_MAX with derivation chain) + owner sign-off field.

## 5. Dedicated Characterization Runs (only where gaps remain)

Triggered per unresolved WP. Design constraints:

- Deterministic allocation, no randomization theater: fixed run order logged;
- Each arm/candidate: >=3 valid replicates;
- Every run uses the frozen S1 run schema (event_definition, censoring_type,
  method_outcome, business_pass_label=null, UNKNOWN-forbidden stop_reason);
- Candidate doses (e.g. ASA#4 0 / 0.5 / 1 / 2%) may be included as
  characterization arms ONLY IF owner approves them as method-characterization
  materials; their results describe the bench response surface locally and do
  NOT qualify any of them as Known Good;
- Budget cap: characterization is bounded (proposal: max 12 runs total across
  WPs); exceeding requires explicit owner re-gate;
- Stop reasons mandatory; INVALID_RUN replacement policy identical to S1 plan.

## 6. WP-5 Q2-B Metric Selection

Candidate fixed-timepoint noise reads (pick 1-2, freeze before S1b):

- noise_db_at_1h (primary candidate);
- noise_db_at_2h (secondary);
- time-to-fixed-dB-threshold below 65 dB (only if instrument logging supports
  reliable interpolation; else reject).

Selection criterion: metric must show non-degenerate spread across
characterization runs (i.e. not constant), be mechanically stable within-run,
and be cheap to log every run. Final choice recorded in Q2B_METRIC_SELECTION.md
with rationale.

## 7. Sequence and Gates

    WP-1/WP-2 dossier work (document research, owner contact)
        |
    WP-5 metric selection (can proceed in parallel, desk study)
        |
    WP-3/WP-4 gap analysis -> decide whether existing data suffices
        |                    or dedicated runs needed (Section 5)
        v
    All five artifacts complete + owner review
        v
    PARAMETER FREEZE RECORD (SIGMA_MAX, control band V0, Q2-B metric,
    GOOD/BAD references, protocol deltas)
        v
    S1b independent qualification (existing S1 gate, Q1-Q6 incl. Q2-A/Q2-B)

## 8. Explicit Non-Goals

- No S2 design space, no DOE matrix, no optimization;
- No business PASS labels;
- No promotion of 2% ASA#4 to Known Good by assumption;
- No invented numeric thresholds without evidence chains;
- No modification of Phase 3/Phase 4 schemas, engines, or fixtures.
