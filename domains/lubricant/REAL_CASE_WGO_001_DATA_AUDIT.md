# REAL_CASE_WGO_001_DATA_AUDIT

> Audit Gate: PASS / PARTIAL REPLAY. Core finding: history covers the anti-electrical-erosion specialty, not the full WGO cost-down design space. Cost Engine = HOLD (E-01/E-02). Only ASA#4 dose descriptive/exploratory analysis approved. See sections B/G/H/I/J/K.

## A. Formula Data

### CF-30LS Conductive Oil System (~16 validation schemes V0-V16)

Base structure: 1540A/B 99% + PAO6 1% + L57 0.5% + CDP 0.3% + Hitec059 0.2% + Hitec4313 0.05% + IRGAMET39 0.1% + PX3846/3844/AW319 etc 0.1-0.3% + PX3864 0.2% + T747 0.05% + antifoam 0.02-0.1% + optional conductor 10%(90/10 ratio).

Quality: PARTIALLY_VERIFIED (sample dates mostly recorded, batches partially traceable, "retune"/"retain"/"pilot-modified" suffix semantics pending confirmation)

### ASA#4 Composite System

Mobil/Shell/Castrol base oils x ASA#4 dosage 0.5%-10%, ~30 experiment points.

Quality: VERIFIED (dosage clear, test dates complete)

## B. Material Data - Unit Prices

Source: cost sheet. All unit prices lack effective_date.

| material_id | price CNY/kg | quality |
|------------|-------------:|---------|
| 1540B | 25 | UNVERIFIED |
| PAO6 | 18.7 | UNVERIFIED |
| L57 | 29.5 | UNVERIFIED |
| CDP | 40 | UNVERIFIED |
| Hitec059 | 235(later)/MISSING(early) | UNVERIFIED |
| Hitec4313 | 143 | UNVERIFIED |
| IRGAMET39 | 300 | UNVERIFIED |
| PX3846/PX3844 | 300 / 0 | UNVERIFIED(PX3844=0 reason unclear) |
| PX3864 | 100 | UNVERIFIED |
| T747 | 23 | UNVERIFIED |
| 2148 | 36 | UNVERIFIED |
| LiTFSI | 780 | UNVERIFIED |
| 155 antifoam | 180 | UNVERIFIED |
| T10100/AMH2 | 31.5 / 170 | UNVERIFIED |

Ruling (Gate): all prices stay UNVERIFIED with effective_date=MISSING. Fabricating dates (today or file date) is forbidden. These rows are mapping evidence only; Cost Engine eligibility remains HOLD until a data-owner-confirmed price baseline date exists. Sheet totals may be quoted as nominal costs only.

PX3844 ruling (Gate): price=0 remains UNRESOLVED. Frozen rule price>0 stands; 0 must not be interpreted as free material. Any cost result depending on PX3844 is HOLD pending owner confirmation.

## C. Experiment Data

### Erosion Bench (Core Response)

~35 bench experiments. Critical: pass standard changed from old >75dB to new >65dB; bench conditions adjusted multiple times. Old/new NOT COMPARABLE - must split datasets.

New-standard modelable subset: ASA#4 dose series (Mobil base oil, ~12 points, dosage 0.5%-10%).

### Test Method Consistency

| CTQ | Method | Comparable? |
|-----|--------|-------------|
| Erosion noise | Version switch(75->65) | NO - split required |
| Wear scar | Four-ball machine | YES |
| PB/N PD/N | GB/T 3142 | YES |
| FZG | NB/SH/T 0306 | YES |
| Cu corrosion | 100C 3h | YES |
| Demulsibility | 82C to 3mL | YES(low discrimination) |
| Foam | ASTM D892 | YES |
| KRL | 20h | YES(insufficient pts) |

Other data: oxidation/hydrolysis(3 samples), precipitation(11 schemes), antifoam(7), demulsifier(8), ASA4 solubility(15 conditions), ICP(multiple) - all VERIFIED.

## D. Benchmark Data

| benchmark_id | brand | quality |
|-------------|-------|---------|
| BASELINE_CF30LS | Internal CF-30LS | VERIFIED |
| BASELINE_CF30 | Internal CF-30 | VERIFIED |
| EXT_MOBIL_SHC | Mobil(white) | PARTIALLY_VERIFIED(no specific grade confirmed) |
| EXT_SHELL_OMALA | Shell | PARTIALLY_VERIFIED |
| EXT_CASTROL | Castrol | PARTIALLY_VERIFIED |

## E. Provenance

Traceable: source file SHA256 / sheet name + row range / sample date YYYYMMDD / remarks with anomaly notes.

NOT traceable: Hitec059 price change timing/reason, PX3844=0 reason, bench current/bearing/operator params, "retune"/"retain"/"pilot-modified" exact semantics.

## F. Data Quality Summary

| Category | Count |
|----------|------:|
| complete_records | ~15 |
| missing_records | ~8 |
| duplicate_records | 2 |
| unit_conflicts | 1(standard 75->65) |
| method_conflicts | 1(bench version change) |
| batch_conflicts | 1(1540A vs 1540B) |
| unresolved_material_ids | 2 |
| unresolved_formula_versions | 3 |

## G. Model Eligibility Matrix

| Response | Points | Replicates | Coverage | Eligibility |
|----------|-------:|-----------:|----------|-------------|
| Erosion noise(new >65 std) | ~12 | few | dose wide/formulation narrow | DATA_LIMITED |
| Erosion noise(old >75 std) | ~23 | very few | wide but not comparable | NOT_MODELABLE |
| Wear scar dia | ~12 | none | narrow | DATA_LIMITED |
| PB/N | ~8 | has replicate | narrow | DATA_LIMITED |
| PD/N | ~6 | none | narrow | NOT_MODELABLE |
| FZG | 1 | none | single point | NOT_MODELABLE |
| Demulsibility | ~8 | none | narrow | DATA_LIMITED |
| Foam characteristics | ~14 | none | antifoam dimension present | DATA_LIMITED |
| Oxidation/hydrolysis rate | 3 | none | extremely narrow | NOT_MODELABLE |
| ASA4 solubility/moisture | ~15 | partial time series | dose sufficient | DATA_SUFFICIENT(descriptive only) |
| Cost-formulation relation | 2x10 | N/A | 2 points | NOT_MODELABLE |

Note (Gate): DATA_SUFFICIENT(descriptive only) outputs must be tagged DESCRIPTIVE evidence strength. Descriptive analysis must not be labeled MODEL_BUILT and must not feed Optimization. DATA_LIMITED permits exploratory analysis only, never optimization eligibility.

## H. Evidence Gap

| gap_id | Description | Impact | Recommendation |
|--------|------------|--------|----------------|
| E-01 | All material prices lack effective_date | Cost engine cannot determine price timeliness | Add dates or tag UNVERIFIED |
| E-02 | PX3844 price = 0 | Free sample or omission? | Confirm with data owner |
| E-03 | External benchmark no specific grade | Non-inferiority comparison ambiguous | Confirm product model |
| E-04 | Bench method version change no formal record | Old/new data incomparable | Establish change log |
| E-05 | Most responses lack replicates | Cannot estimate experimental error | Future DOE include replicates |
| E-06 | Fraction sum != 100% in formula sheet | Schema mapping needs normalization policy | Clarify normalization rule |
| E-07 | "Retune"/"retain"/"pilot-modified" semantics unclear | Affects sample independence judgment | Confirm with R&D staff |
| E-08 | Bench current/bearing/operator incomplete | Affects covariate modeling | Supplement run parameters |
| E-09 | Hitec059 price change no date | Price change untraceable | Confirm timing |

### Gap Dispositions (Gate)

| gap_id | disposition |
|--------|-------------|
| E-01 | OWNER_CONFIRMATION_REQUIRED (price baseline date) |
| E-02 | OWNER_CONFIRMATION_REQUIRED (PX3844 price semantics) |
| E-03 | OWNER_CONFIRMATION_REQUIRED (external benchmark grade) |
| E-04 | OWNER_CONFIRMATION_REQUIRED (bench method change record) |
| E-05 | PROSPECTIVE (replicates required in future DOE) |
| E-06 | POLICY_SET (derived normalization view allowed as DERIVED_UNVERIFIED; upgrade to DERIVED_VERIFIED requires owner confirmation that sheet composition is complete) |
| E-07 | OWNER_CONFIRMATION_REQUIRED |
| E-08 | OWNER_CONFIRMATION_REQUIRED |
| E-09 | OWNER_CONFIRMATION_REQUIRED |

Full resolution is NOT required at this gate.

## I. System Capability Assessment

| Engine | Available? | Notes |
|--------|-----------|-------|
| Cost Engine | HOLD | E-01 dates missing + E-02 PX3844 unresolved; sheet costs are nominal evidence only, not engine artifacts |
| Mixture DOE | N/A | Replay mode generates no DOE |
| Statistics | Descriptive-only GO | ASA#4 dose descriptive/exploratory approved (tag DESCRIPTIVE, not MODEL_BUILT); all regression/ANOVA HOLD |
| Optimization | No | Replay mode prohibits recommendation candidates |
| Validation | Yes | Validate any produced artifacts |

## J. HOLD Conditions

1. Cost Engine: HOLD until price baseline date confirmed (E-01) and PX3844 resolved (E-02); no fabricated dates
2. Statistics Engine: all regression/ANOVA HOLD; only ASA#4 dose descriptive/exploratory GO
3. Optimization Engine: fully HOLD
4. Formula normalization: DERIVED_UNVERIFIED only; raw preserved; no silent normalization; no invented rounding tolerance
5. Bench data: old/new standards strictly split; no cross-version merged model
6. Confirmation Experiment: not applicable (no optimization candidate exists)

## K. Next Step After Review

A -> B -> C:
A. Data Resolution / Mapping (classify E-01..E-09 as RESOLVED / UNRESOLVED / OWNER_CONFIRMATION_REQUIRED; full resolution not required)
B. Partial Replay - ASA#4 dose descriptive/exploratory analysis (DESCRIPTIVE evidence strength only)
C. EVIDENCE_GAP_CLOSURE_PLAN / PROSPECTIVE_EXPERIMENT_PLAN (renamed from "Confirmation plan": design the experiments needed to move WGO_001 from HOLD toward modelable/optimizable)

Pause for review after each step.
