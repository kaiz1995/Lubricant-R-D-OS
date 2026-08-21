---
name: test-method-qualification
description: Qualify one evidence-bound lubricant test method at TEST_METHODS_QUALIFIED; hold without writing when upstream linkage, method provenance, role metrics, or qualification evidence is incomplete.
---

# Test Method Qualification

Use `../../schemas/test_method.schema.json` as authority when available; installed `references/` are deployment-only.

## Required input

- Preflight requires schema-valid `project_artifact` (`PROJECT_DEFINED`/`ACTIVE`), `challenge_artifact` (`CHALLENGES_DEFINED`), and `failure_ctq_artifact` (`FAILURE_CTQ_DEFINED`).
- All must share `project_id`; input `challenge_reference` and `target_failure_reference` must match their records.
- `test_method` needs non-empty ID/name/standard/references, unique `C`/`D`/`P` roles, complete measurement metrics, basis/status, and source/qualification evidence IDs.
- Evidence must be supplied and the method-source and qualification pointers must resolve to `OBSERVED` items; supplied provenance is not independently verified.
- `D` requires `DISCRIMINATION`; `P` requires `MECHANISM_RELEVANCE` plus `FIELD_RELEVANCE` or `BENCHMARK_RANKING`; C-only remains compliance-only.
- `QUALIFIED` needs role metrics, observed evidence, and basis. `PENDING`/`NOT_QUALIFIED` receive `HOLD`; `MONITOR` is wording only.

Run `python scripts/preflight_test_method.py <input.json>` first. On error report `HOLD`, write nothing, and do not infer method provenance, metrics, or results.

## Artifact

Run `python scripts/build_test_method_artifact.py <input.json> <temporary-file>` after preflight. The builder alone creates the canonical JSON and its seven deterministic decision fields answer only whether this method is qualified to measure the target failure/CTQ.

Run `python scripts/validate_test_method_artifact.py <temporary-file>`, then atomically replace only a matching `artifact_type`/`project_id`/`method_id` target after `PASS`. On failure leave it unchanged. Stop at `TEST_METHODS_QUALIFIED`; do not create formulation, DOE, statistics, performance, or downstream artifacts.
