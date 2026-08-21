---
name: formulation-design
description: Define one evidence-bound, testable design space at DESIGN_SPACE_DEFINED; hold without writing when upstream linkage, qualified method, variables, bounds, constraints, or evidence are incomplete.
---

# Formulation Design

Use `../../schemas/design_space.schema.json` as authority when available; installed `references/` are deployment-only.

## Required input

- Preflight requires schema-valid, `decision: GO` `project_artifact` (`PROJECT_DEFINED`/`ACTIVE`), `challenge_artifact` (`CHALLENGES_DEFINED`), `failure_ctq_artifact` (`FAILURE_CTQ_DEFINED`), and `test_method_artifact` (`TEST_METHODS_QUALIFIED`/`QUALIFIED`). All share `project_id`.
- `design_space` requires only `design_space_id`, `scope`, `variables`, `ctq_references`, `qualified_test_method_references`, `constraints`, and `evidence`. Variables use the deployed schema fields exactly. Bounds need complete measurement metadata, matching units, and `lower_bound.value <= upper_bound.value`; variable IDs cannot repeat.
- Every referenced CTQ must exist in the failure record and link to the qualified method through its `test_references` or the failure record's `test_chain`. The sole qualified method reference must equal the supplied method ID and target the supplied failure ID.
- Preserve supplied evidence statuses. `ASSUMED` bounds are allowed; any `GAP` means `HOLD`. Do not infer sources, bounds, constraints, materials, formulas, DOE, results, costs, or optimization.

Run `python scripts/preflight_formulation_design.py <input.json>` first. On error report `HOLD`, write nothing, and do not generate a formulation, candidate ratio, DOE, experiment, statistic, performance, cost, optimization, Freeze, or downstream artifact.

## Artifact

Run `python scripts/build_design_space_artifact.py <input.json> <temporary-file>` only after preflight. The builder creates one canonical `design_space` JSON whose seven deterministic decision fields answer only whether the supplied input is sufficient to define a testable design space.

Run `python scripts/validate_design_space_artifact.py <temporary-file>`, then atomically replace only a matching `artifact_type`/`project_id`/`design_space_id` target after `PASS`. On failure leave it unchanged. Stop at `DESIGN_SPACE_DEFINED`.
