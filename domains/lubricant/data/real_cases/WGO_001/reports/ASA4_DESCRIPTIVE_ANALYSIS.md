# WGO_001 - ASA#4 Dose Descriptive Analysis (PARTIAL REPLAY)

> Evidence strength: **DESCRIPTIVE**. No model built. No optimization input.

| dose | n | noise dB(min/max/mean) | duration h(min/max) | stop statuses |
|------|--:|------------------------|---------------------|---------------|
| 0.005 | 2 | 62.0/65.0/63.5 | 4.5/10.0 | {"FULL_10H_PASS": 1, "EARLY_STOP_AT_THRESHOLD": 1} |
| 0.01 | 2 | 56.5/66.5/61.5 | 4.0/10.0 | {"FULL_10H_PASS": 1, "EARLY_STOP_AT_THRESHOLD": 1} |
| 0.02 | 2 | 64.0/65.0/64.5 | 5.0/9.0 | {"AMBIGUOUS_STOP_BELOW_LIMIT(E-07/E-08)": 1, "EARLY_STOP_AT_THRESHOLD": 1} |
| 0.03 | 1 | 66.0/66.0/66.0 | 3.0/3.0 | {"EARLY_STOP_AT_THRESHOLD": 1} |
| 0.05 | 1 | 63.0/63.0/63.0 | 1.0/1.0 | {"AMBIGUOUS_STOP_BELOW_LIMIT(E-07/E-08)": 1} |
| 0.08 | 1 | 65.0/65.0/65.0 | 2.3/2.3 | {"EARLY_STOP_AT_THRESHOLD": 1} |
| 0.1 | 1 | 65.0/65.0/65.0 | 1.75/1.75 | {"EARLY_STOP_AT_THRESHOLD": 1} |

## Findings
- 2/10 runs completed 10h with noise <=65dB (WGO001-ASA4-B @0.005, WGO001-ASA4-C @0.01).
- Stops at/above 65dB (boundary reading is TEMPORARY_INTERPRETATION per E-11) occurred at doses [0.005, 0.01, 0.02, 0.03, 0.08, 0.1]. The dose-vs-runtime negative association is EXPLORATORY_ASSOCIATION only: recorded runtime embeds an unknown stopping mechanism (E-10), so no endurance conclusion is drawn.
- Ambiguous early stops below limit: ['WGO001-ASA4-F', 'WGO001-ASA4-M'] - HOLD from any performance conclusion.
- Solubility proxy (identical prep OPEN_DRY_60C_3D): water content [257, 170, 81, 112] ppm at doses [0.005, 0.01, 0.02, 0.03]; 2% shows the observed local minimum among tested doses (DESCRIPTIVE_LOCAL_MINIMUM, not OPTIMUM); 2%-vs-3% difference not verified against method repeatability.

## Quality flags
- noise values compared across different durations conflate dose with stopping time
- E-10 CRITICAL: 6/10 records stopped below 65dB before 10h with UNKNOWN reason; OWNER_CONFIRMATION_REQUIRED
- E-07/E-08: bench operating parameters and retune semantics unresolved; confound interpretation
- no replicates (E-05): dispersion within dose is confounded with time/bench drift
- bench method version change lacks formal record (E-04); new-standard subset only
- 65.0 dB counted as threshold hit is TEMPORARY_INTERPRETATION; method document must confirm boundary semantics (E-11)

## Contract boundary
- Frozen statistics engine not invoked: schema requires >=3 mixture components +
  validation requires doe_result upstream; historical OFAT dose series satisfies neither.
- This is the correct system behavior: real imperfect data -> DESCRIPTIVE evidence, not MODEL_BUILT.
