# REAL_CASE_WGO_001 - Case Definition

## Project

| Field | Value |
|-------|-------|
| case_id | WGO_001 |
| project | Wind Turbine Gear Oil ISO VG 320 Cost-down |
| project_type | COST_DOWN |
| objective | Cost reduction 10-20% |
| primary_principle | Non-inferiority |
| product_grade | ISO VG 320 |
| base_oil_change | Allowed |
| additive_change | Allowed |
| benchmark | CF-30LS/CF-30 internal + Mobil/Shell/Castrol external |

## Critical CTQ / Guardrail

| CTQ | Direction | Source | Quality |
|-----|-----------|--------|---------|
| Erosion bench noise <=65dB @10h | Lower-is-better | Bench plan 20251218 | VERIFIED |
| Wear scar dia <=0.35mm four-ball | Lower-is-better | Init sheet + test reports | VERIFIED |
| PB/N >=1050N | Higher-is-better | Init sheet | VERIFIED |
| PD/N >=2450N | Higher-is-better | Init sheet | VERIFIED |
| FZG >12 stages | Higher-is-better | Init sheet | VERIFIED |
| Cu corrosion 100C/3h <=1a | Ordinal | Init sheet | PARTIALLY_VERIFIED |
| Demulsibility 82C <=60min | Lower-is-better | Init sheet | UNVERIFIED(low discrimination) |
| Foam I/II/III <=50/0mL | Lower-is-better | Init sheet | VERIFIED |
| KRL shear loss 20h | Lower-is-better | Init sheet | UNVERIFIED(insufficient pts) |
| Brookfield viscosity -30C <=150000 | Lower-is-better | Init sheet | VERIFIED |
| Viscosity index >=150 | Higher-is-better | Init sheet | VERIFIED |

## Data Sources

Primary:
1. Lubemater CF-30C 320 (SHA256: 7f19e2e0...3899a) - formula validation, cost, physicochemical, erosion bench, precipitation, oxidation/hydrolysis, antifoam/demulsifier
2. Lubemater WT (SHA256: 2e22213d...9f74) - ASA#1-5 screening, dosage-solubility, multi-brand compatibility, erosion bench

Secondary: QRC QC PDFs(33), CF-30 third-party lab report, CF-20 FE8/FZG/micropitting/SRV, in-service monitoring archives

## Scope Boundary

In Scope: CF-30LS conductive oil formulation data, ASA#4 dose-erosion-solubility relationship, cost composition, benchmarks

Out of Scope: CF-20 product line, in-service trend analysis, new DOE design or new experiments

## Validation Mode

PARTIAL REPLAY - Map existing real data into Phase 4 Pipeline. No new DOE. No Optimization. No Confirmation Experiment (no model-recommended candidate exists). Verify system can correctly understand past data and identify Evidence Gaps.

## Gate Status (Real Case Data Audit Gate)

PASS / PARTIAL REPLAY / HOLD

Core conclusion: current historical data mainly covers the anti-electrical-erosion / conductivity specialty of WGO development. It does NOT represent the complete WGO cost-down design space or comprehensive CTQ system. Full Closed Loop is NOT claimable from this data.

Eligibility rulings:

- Cost Engine: HOLD (E-01 all prices lack effective_date; E-02 PX3844=0 unresolved). Sheet costs may be quoted as nominal evidence only, never as verified engine cost artifacts.
- Statistics: only ASA#4 dose descriptive/exploratory analysis approved; output must be tagged DESCRIPTIVE/EXPLORATORY, never MODEL_BUILT.
- Optimization: HOLD.
- Normalized formula views (E-06): allowed as DERIVED_UNVERIFIED only; raw formulas preserved; no silent normalization; no invented rounding tolerance.
- Next stage after replay: EVIDENCE_GAP_CLOSURE_PLAN / PROSPECTIVE_EXPERIMENT_PLAN.

## Acceptance Criteria

1. Data Audit complete with quality tags
2. Model Eligibility Matrix established
3. Evidence Gap list complete
4. HOLD conditions clear
5. No modification to frozen Phase 3/4 schema/engine/fixture
