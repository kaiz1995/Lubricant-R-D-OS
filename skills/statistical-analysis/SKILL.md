---
name: statistical-analysis
description: Record one evidence-bound statistical-analysis request at MODEL_BUILT; hold without writing when the observed experiment, upstream links, response CTQ/method chain, or evidence are incomplete.
---

# Statistical Analysis

Use `../../schemas/model.schema.json` as authority when available; installed `references/` are deployment-only.

## Required input

- Supply schema-valid, `decision: GO` project, challenge, failure/CTQ, qualified test method, design space, experiment design, and observed experiment artifacts for one project. Their stages must end at `EXPERIMENT_RUNNING`.
- `analysis` supplies only `model_id`, `requested_analyses`, `response_references`, and `evidence`. Each response CTQ must be in the failure record, design space, observed experiment, and linked to the qualified method.
- Preserve evidence. A `GAP`, a missing link, or an incomplete upstream record is `HOLD`; write nothing.

## Decision boundary

- This Skill records a request only. ANOVA, regression, mixture/RSM fitting, residuals, lack-of-fit, intervals, sensitivity, coefficients, adequacy, and conclusions belong exclusively to the Phase 4 deterministic engine.
- A `GO` means only that the supplied request may be handed off; it is not a model result or an optimization decision.

## Artifact

Run `python scripts/preflight_statistical_analysis.py <input.json>`, then `python scripts/build_model_artifact.py <input.json> <temporary-file>`, then `python scripts/validate_model_artifact.py <temporary-file>`. Stop at `MODEL_BUILT`.
