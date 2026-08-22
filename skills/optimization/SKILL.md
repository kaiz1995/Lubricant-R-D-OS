---
name: optimization
description: Record one evidence-bound optimization request at OPTIMIZED; hold without writing when its model chain, objectives, supported method, or evidence are incomplete.
---

# Optimization

Use `../../schemas/optimization.schema.json` as authority when available; installed `references/` are deployment-only.

## Required input

- Supply the schema-valid, `decision: GO` chain from project through observed experiment and a `MODEL_BUILT` model for one active project.
- `optimization` supplies only `optimization_id`, `objective_type`, `objectives`, `methods`, and `evidence`. Every objective response must be recorded in the model.
- Supported methods are `PARETO`, `DESIRABILITY`, and `NON_INFERIORITY`. Bayesian Optimization is deliberately unsupported in Phase 3 and is `HOLD`; write nothing.

## Decision boundary

- This Skill records a request only. It does not calculate candidates, Pareto fronts, desirability, non-inferiority, constraints, trade-offs, or a formulation recommendation. Those deterministic calculations belong to Phase 4.

## Artifact

Run `python scripts/preflight_optimization.py <input.json>`, `python scripts/build_optimization_artifact.py <input.json> <temporary-file>`, then `python scripts/validate_optimization_artifact.py <temporary-file>`. Stop at `OPTIMIZED`.
