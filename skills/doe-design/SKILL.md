---
name: doe-design
description: Record one evidence-bound constrained-mixture experiment-design request at EXPERIMENT_DESIGNED; hold without writing when upstream links, qualified D/P method, factors, bounds, mixture feasibility, or evidence are incomplete.
---

# DOE Design

Use `../../schemas/experiment_design.schema.json` as authority when available; installed `references/` are deployment-only.

## Required input

- Supply only `project_artifact`, `challenge_artifact`, `failure_ctq_artifact`, `test_method_artifact`, `design_space_artifact`, and `experiment_design`.
- The five artifacts must be schema-valid, `decision: GO`, linked to one active project, and at `PROJECT_DEFINED`, `CHALLENGES_DEFINED`, `FAILURE_CTQ_DEFINED`, `TEST_METHODS_QUALIFIED`, and `DESIGN_SPACE_DEFINED`. The method must be `QUALIFIED` and have role `D` or `P`.
- `experiment_design` supplies only its listed request fields. Factors must be two or more unique formulation variables in the design space; bounds and `mixture_total` must have complete compatible measurement metadata and form a feasible total.
- Only `CONSTRAINED_MIXTURE` is currently eligible for `GO`. Other families, including Bayesian sequential design, are `HOLD`; supplied `ASSUMED` evidence remains assumed and any `GAP` is `HOLD`.

## Decision boundary

- `target_count`, replicates, center points, randomization, effects, responses, guardrails, and information value are supplied planning inputs. They are not a statistical-power or model-adequacy conclusion.
- `mixture_total` is a supplied design constraint. It must be positive, use the selected-factor unit, and lie within their lower/upper-bound sums.
- A `GO` means only that the request may be handed to Phase 4. It does not authorize a lab run, advance to results, or claim feasibility beyond this structural check.
- Use `HOLD` for an unsupported family, C-only method, missing link, infeasible total, incomplete metadata, or GAP. Retain the supplied evidence wording and do not manufacture a replacement.

## Output boundary

- Emit exactly one `experiment_design` artifact at `EXPERIMENT_DESIGNED` after a successful preflight.
- Derive `design_space_reference` and `test_method_references` from the linked upstream artifacts; do not accept them as request inputs.
- Never add `runs`, formula points, candidate formulations, `measurement`, observed responses, statistics, cost, performance, optimization, Freeze, or downstream artifacts.

Run `python scripts/preflight_doe_design.py <input.json>` first. On error report `HOLD`, write nothing. Do not infer constraints, factors, statistical sufficiency, run points, formulas, measurements, results, cost, performance, optimization, or downstream decisions.

## Artifact

Run `python scripts/build_experiment_design_artifact.py <input.json> <temporary-file>` only after preflight. It records supplied planning inputs, derives design-space and method references, and marks only handoff eligibility to the Phase 4 deterministic engine.

Run `python scripts/validate_experiment_design_artifact.py <temporary-file>`, then atomically replace only a matching `artifact_type`/`project_id`/`experiment_design_id` target after `PASS`. Stop at `EXPERIMENT_DESIGNED`; Phase 4 alone generates deterministic DOE points.
