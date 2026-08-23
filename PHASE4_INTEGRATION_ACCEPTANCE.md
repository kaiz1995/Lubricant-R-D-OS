# Phase 4 Integration Acceptance — Synthetic Closed Loop

## Result

**PASS (9/9)** for the deterministic ISO VG 320 wind-turbine gear-oil synthetic closed loop.

- Baseline: PAO_BASE 70%, ESTER 25%, ANTIWEAR_ADDITIVE 5%.
- Material prices: 60, 25, and 60 CNY/kg respectively; 100 kg baseline batch cost = **5,125 CNY**.
- Accepted recommendation: PAO_BASE 52.6316%, ESTER 42.1053%, ANTIWEAR_ADDITIVE 5.2632%.
- Recommended batch cost: **4,526.32 CNY**; reduction: **11.6816%** (inside the 10–20% target).
- All three fitted models have R² > 0.95 (acceptance run: 1.0 after result serialization).
- Statistics validation: eligible for optimization.
- Optimization validation: eligible for downstream use. It reports the engine's documented `DOMAIN_SCREENED_APPROX` warning; independent assertions verify every recommendation against the actual component bounds and all hard constraints.
- Full gate artifact SHA-256 from the acceptance run: `6ce62fa7324f68ea5a492600db50719ba4b639e0a38f3fcdc2f631b38d86fbff`.

## Scenario and known truth

The test uses a deterministic Scheffé quadratic polynomial for each CTQ. Terms are ordered as the three linear mixture terms followed by the three pair interactions. No random number generator is used.

| CTQ | Additive | Ester | PAO | Additive×Ester | Additive×PAO | Ester×PAO |
|---|---:|---:|---:|---:|---:|---:|
| VISCOSITY_INDEX | 130 | 145 | 152 | 10 | 15 | 20 |
| OXIDATION_STABILITY | 65 | 72 | 85 | 15 | 20 | 30 |
| ACID_NUMBER | 1.0 | 0.5 | 0.3 | -0.1 | -0.2 | -0.3 |

At the baseline, the truth function gives approximately VI 153.3, oxidation stability 86.9 h, and acid number 0.324 mgKOH/g. Synthetic measurement variation is a fixed repeating multiplier pattern of -0.10%, +0.05%, +0.10%, -0.05%, and 0%; there is no noise or randomness.

The optimization domain retains additive at 3–20%, ester at 10–60%, and PAO at 30–80%. Guardrails permit at most 2% degradation in VI and oxidation stability and 10% degradation in acid number. Two cost constraints enforce both ends of the 10–20% reduction band.

## Engine chain

1. Project constants define the scenario, baseline, bounds, costs, CTQs, and decision rule.
2. The real DOE engine generates the quadratic D-optimal mixture design.
3. The real cost engine calculates the baseline cost.
4. The known truth function creates observations at the real DOE points with fixed perturbations.
5. The real statistics engine is called once per CTQ and fits three quadratic models.
6. The real validation engine validates every statistics artifact with the DOE artifact and its actual digest as context.
7. Only after those validations pass, the real optimization engine consumes content-matched copies of all three validated models. Its provenance metadata binds all three statistics artifact digests and the cost artifact digest.
8. The real validation engine validates the optimization artifact with all three statistics result envelopes and the cost result envelope in `chain_context`.
9. The gate summary records the real execution-order digest ledger. Independent assertions verify model content linkage, validation context digests, and each candidate cost evaluation digest.

## Assertion results

| # | Acceptance question | Result |
|---:|---|---|
| 1 | DOE points are valid and inside the design space | PASS |
| 2 | Synthetic observations entered Statistics successfully | PASS |
| 3 | All three models have R² > 0.95 | PASS |
| 4 | Statistics validation allows optimization | PASS |
| 5 | Optimization recommendations are in the feasible region | PASS |
| 6 | Independently recomputed guardrails and non-inferiority pass | PASS |
| 7 | Cost reduction is 10–20% | PASS (11.6816%) |
| 8 | Upstream model, candidate-cost, and validation-context digests match | PASS |
| 9 | Identical rerun produces identical final artifact hash | PASS |

## Run

```powershell
python tests/lubricant_e2e/test_synthetic_closed_loop.py
```

The test is direct-run style and writes no runtime artifact files. JSON used for engine input and gate hashing is encoded as deterministic UTF-8 bytes with sorted keys and fixed separators.
