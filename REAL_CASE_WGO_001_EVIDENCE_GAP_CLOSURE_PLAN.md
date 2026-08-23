# REAL_CASE_WGO_001 - Evidence-Gap Closure Plan

> Status: DRAFT for Review. This plan answers "what evidence is missing for the
WGO cost-down DECISION", not "what can we squeeze out of history".

## 0. Decision Question (anchor)

ISO VG 320 wind turbine gear oil, cost down 10-20%, non-inferiority on all
critical CTQs vs internal CF-30LS/CF-30 baseline.

Every experiment in this plan must trace to this question.

## 1. CTQ Evidence Coverage Matrix

Evidence strength scale: NONE / DESCRIPTIVE / EXPLORATORY / DISCRIMINATING /
MODEL_ELIGIBLE / CONFIRMATORY.

| # | CTQ | Role | Failure link | Existing dataset | Method/version | Strength | Model eligibility | Required new evidence | Priority |
|---|-----|------|--------------|------------------|----------------|----------|-------------------|-----------------------|----------|
| 1 | Erosion bench endurance | GUARDRAIL (critical) | bearing electrical erosion | ASA#4 dose series n=10 + old-standard ~23 | self-built bench, criteria evolved 75->70->65dB; "time-to-65dB endpoint" defined in project summary appendix A | DESCRIPTIVE | HOLD (no replicates, unknown stop mechanism, bench drift) | stabilized protocol + simultaneous blank/positive controls + replicates | P0 |
| 2 | Cost per kg / batch | OBJECTIVE | cost-down target itself | full unit-price sheet, no dates (E-01), PX3844=0 (E-02) | sheet only | NONE (as VERIFIED engine input) | HOLD (engine ready, data not) | owner-confirmed price baseline date; PX3844 semantics | P0 |
| 3 | Viscosity grade KV40/KV100, VI | GUARDRAIL | grade compliance ISO VG 320 | scattered QC records | GB/T 265 etc. | DESCRIPTIVE | NOT_MODELABLE (scattered) | include in every candidate batch QC | P1 |
| 4 | Wear scar four-ball | GUARDRAIL (critical) | wear protection | ~12 pts narrow | GB/T 3142 family | EXPLORATORY | DATA_LIMITED | include in matrix with replication at corners | P1 |
| 5 | PB/PD extreme pressure | GUARDRAIL | EP reserve | PB ~8 w/ replicate; PD ~6 none | GB/T 3142 | EXPLORATORY / NONE(PD) | PD NOT_MODELABLE; PB DATA_LIMITED | pair with wear scar on same batches | P1 |
| 6 | FZG flank load capacity | GUARDRAIL (critical) | gear surface protection | 1 point | NB/SH/T 0306 | NONE effectively | NOT_MODELABLE | screen top candidates only (cost/time high) | P1 |
| 7 | Foam I/II/III | GUARDRAIL | foaming in service | ~14 pts, antifoam dim present | ASTM D892 | DESCRIPTIVE | DATA_LIMITED | verify winners only | P2 |
| 8 | Demulsibility 82C | GUARDRAIL | water separation | ~8 pts low discrimination | ASTM D140 style | DESCRIPTIVE | DATA_LIMITED | verify winners only | P2 |
| 9 | Cu corrosion | GUARDRAIL | copper compatibility | few pts | ASTM D130 100C3h | DESCRIPTIVE | DATA_LIMITED | verify winners only | P2 |
| 10 | Rust prevention B method | GUARDRAIL | rust | few pass records | ASTM D665B | DESCRIPTIVE | DATA_LIMITED | verify winners only | P2 |
| 11 | Oxidation/hydrolysis stability | GUARDRAIL (long-term) | oxidation life | 3 samples | project-specific aging | NONE effectively | NOT_MODELABLE | defer to phase-2 (long duration) | P3 (defer) |
| 12 | KRL shear stability | GUARDRAIL | viscosity shear loss | insufficient points | KRL 20h | NONE effectively | NOT_MODELABLE | defer; required before design freeze but not before screening | P3 (defer) |
| 13 | Low-temp Brookfield -30C | GUARDRAIL | cold start pumping | few records | ASTMD2983-equivalent | DESCRIPTIVE | DATA_LIMITED | include in batch QC of candidates | P2 |
| 14 | Conductivity (pS/m) | DIAGNOSTIC | erosion mechanism proxy | several pts | internal | DESCRIPTIVE | NOT_MODELABLE | record as covariate, not optimization objective | P2 |
| 15 | ASA#4 solubility/water | DIAGNOSTIC | additive compatibility | 15 conditions grouped by prep | internal | DESCRIPTIVE | descriptive only | prep-condition SOP lock before any new dose study | P2 |

Role legend: GUARDRAIL = non-inferiority must hold; OBJECTIVE = minimized;
DIAGNOSTIC = explains mechanism, never a decision variable.

## 2. Evidence-Gap Priority Register

Priority = Decision Criticality x Current Uncertainty x Decision Impact / Experiment Cost-Time.
P-levels are engineering judgment, documented here, no pseudo-math.

### P0 — blocks the decision itself

| gap | what | why blocking | action | owner |
|-----|------|--------------|--------|-------|
| G-A | E-01 price dates + E-02 PX3844=0 | cost objective has no verified basis; frozen engine correctly rejects | owner confirms price baseline date and PX3844 semantics | data owner |
| G-B | bench protocol instability (E-04/E-05/E-07/E-08 + E-10 CRITICAL) | guardrail CTQ unmeasurable without stable ruler | write BENCH_PROTOCOL_V2: fixed current/bearing lot/load/temp; every run carries blank+positive reference; stop-reason field mandatory (COMPLETED/EVENT_OCCURRED/RIGHT_CENSORED/ADMINISTRATIVE_STOP/INVALID_RUN); >=2 replicates per formula point | R&D + test owner |
| G-C | E-11 boundary semantics | pass/fail rule ambiguity corrupts every future run classification | PARTIALLY RESOLVED: project summary appendix A defines time-to-65dB endpoint; remaining: confirm whether any sample passing 10h under 65dB is graded PASS vs censored | method owner |

### P1 — needed to model the design space

| gap | what | why | action |
|-----|------|-----|--------|
| G-D | formulation completeness (E-06 normalization policy) | any DOE needs exact fractions | owner confirms sheets are complete compositions; then DERIVED_VERIFIED allowed |
| G-E | material identity (1540A/B, PX3844/3846, supplier grades) | DOE reproducibility collapses if raw material identity drifts | material register with supplier/TDS/batch policy |
| G-F | external benchmark grade (E-03) | non-inferiority needs a real comparator | confirm Mobil SHC/Shell Omala actual products used |

### P2 — quality gates for winners

verify-on-winner strategy: foam/demuls/rust/Cu/low-temp/conductivity ride along
on candidate batches; no dedicated DOE axis spent on them.

### P3 — deferred by cost/time

oxidation/hydrolysis, KRL: required before DESIGN FREEZE, deferred until
screening narrows candidates.

## 3. Proposed Experiment Strategy (candidate, not yet a DOE matrix)

Strategy shape: one shared formulation matrix serving three questions.

### Stage S1 — bench stabilization pilot (P0, small)

- purpose: prove the ruler before measuring anything else;
- content: baseline oil + one known-good ASA#4 reference + one known-bad
  reference (high-S contaminated), each >=3 replicates, fixed protocol V2,
  blank/positive control every batch;
- output: repeatability sigma, stop-reason taxonomy validated, go/no-go for
  modeling the bench response;
- this directly implements the project summary's own priority-one recommendation.

### Stage S2 — cost-down mixture DOE (the core)

- variables: base-oil blend ratio (PAO/ester or alternative cheaper base),
  ASA#4 dose restricted to 1-3% window (history shows 5-10% adds nothing but
  risk; 0.5% marginal), additive package swap candidates (cheaper alternatives
  for expensive components);
- constraints: VI>=150, KV40 in VG320 band, PB/PD floors from baseline;
- responses: cost (primary), bench endurance (guardrail), four-ball/PB (guardrail);
- design engine: Phase 4.2 simplex-lattice/D-optimal over confirmed component list,
  WITH center-point replicates for pure error;
- precondition: G-A, G-B(S1 passed), G-D, G-E resolved.

### Stage S3 — winner verification

- top 2-3 candidates + baseline re-test: full guardrail panel (FZG, foam,
  demuls, rust, Cu, low-temp) + bench confirmation with replicates;
- predicted-vs-observed check feeds Validation Engine severity policy.

## 4. DOE Engine Eligibility Checklist (gate before invoking Phase 4.2)

| condition | status |
|-----------|--------|
| decision question explicit | YES (section 0) |
| CTQ roles assigned | YES (matrix section 1) |
| test methods comparable + versioned | NO -> blocked by G-B/G-C completion |
| variables + bounds confirmed | PARTIAL (needs owner confirm base-oil swap options) |
| material identities registered | NO -> blocked by G-E |
| formula completeness policy | NO -> blocked by G-D |
| price basis verified | NO -> blocked by G-A |

DOE invocation = HOLD until all rows YES.

## 5. Unresolved Owner Questions (consolidated)

1. Price baseline date + PX3844 semantics (E-01/E-02).
2. Stop reasons for the 6 ambiguous runs (E-10) - classify into the 6-way taxonomy.
3. 10h-pass-under-threshold grading rule (E-11 remainder).
4. Formula sheet completeness for normalization upgrade (E-06).
5. External benchmark product grades (E-03).
6. Material identity register (1540A/B, PX series).
7. Base-oil swap legal/supply scope for cost-down (which cheaper bases are allowed?).

## 6. Next Gate Criteria

EVIDENCE_GAP_CLOSURE_GATE passes when:

1. G-A resolved: prices have owner-confirmed baseline date; PX3844 classified;
2. G-B resolved: BENCH_PROTOCOL_V2 written + S1 pilot executed with repeatability
   estimate accepted by method owner;
3. G-D/G-E/G-F resolved;
4. CTQ matrix reviewed and signed;
5. THEN DOE eligibility checklist goes all-YES and Phase 4.2 may be invoked for S2.

Until then: no DOE matrix generation, no statistics regression, no optimization.

## 7. What This Plan Does NOT Claim

- No optimum dose claim (2% is a local minimum among 4 tested doses only).
- No endurance claim from rho=-0.773 (exploratory association with recorded
  runtime under unknown stopping mechanism).
- No cost-down feasibility claim (cost engine still HOLD on E-01/E-02).
- The historical data answers an anti-erosion specialty question; the WGO
  cost-down design space remains largely unmapped. That mapping is exactly
  what stages S1-S3 are for.
