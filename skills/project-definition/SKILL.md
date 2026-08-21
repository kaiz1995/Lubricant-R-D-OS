---
name: project-definition
description: Turn a complete lubricant R&D project brief into a traceable Project Charter at PROJECT_DEFINED; hold without writing an artifact when required inputs are missing.
---

# Project Definition

Create only the Stage 0 Project Charter. This is a decision record, not a formulation, performance claim, Challenge Map, or downstream-stage artifact.

Use `../../schemas/project.schema.json` as the source-pack authority when it is available. The installed deployment includes an identical `references/project.schema.json` and `references/common.schema.json` copy for validation; it is a deployment copy, not a second maintained schema.

## Required input

Require all of these before creating an artifact:

- `project_id` (letters, digits, `.`, `_`, `-` only), `project_name`, `project_type` (`NEW_PRODUCT`, `COST_DOWN`, `IMPROVEMENT`, or `CORRECTIVE_ACTION`), and `product_family`.
- `business_objective`, `technical_objective`, non-empty `hard_constraints`, and non-empty `success_criteria`.
- `target_cost` with `value`, `unit`, `source`, `method_version`, `material_batch`, and `formula_version`.
- Non-empty `benchmark_products`, `risk_class` (`LOW`, `MEDIUM`, `HIGH`, or `STRATEGIC`), and `owner`.
- Non-empty `source_evidence`; every item must include `evidence_id`, `statement`, `source`, and `status: OBSERVED`. The statement and source must identify the supplied requirement, brief, or record.

Run `python scripts/preflight_project_definition.py <input.json>` first. Do not treat a plausible product assumption as a supplied input.

## HOLD rule

If any required input is absent, blank, invalid, or lacks source evidence, report `HOLD`, list each missing or invalid field, and state that no Project Charter was created. Do not write a partial artifact, infer a target cost, invent a benchmark, or turn a gap into a conclusion.

## Artifact

For valid input, write valid UTF-8 JSON to the user-specified output path, or `project.json` in the current workspace when no path is specified. Before overwriting an existing file, read it: overwrite only if it is JSON with `artifact_type: "project"` and the same `project_id`; otherwise report the exact conflict and do not write.

Create one artifact that conforms to the project schema with:

- `artifact_type: "project"`, `schema_version: "0.1.0"`, `stage: "PROJECT_DEFINED"`, and `status: "ACTIVE"`.
- The supplied project fields and `source_evidence` copied into `evidence` without invented evidence.
- Public decision fields with these exact keys: `decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`, `decision`, and `next_action`. Do not use `gate_0_question`, `charter_scoping_hypothesis`, or `rule` as aliases or substitutes. The question concerns proceeding to duty definition; the hypothesis scopes the charter; uncertainty states that duty/operating conditions are not yet defined; the rule requires recorded goals, constraints, and success criteria; the result only records the charter; `decision` is `"GO"`; `next_action` is `"Define duty conditions."`.

Write the candidate to a temporary sibling JSON file first. Run `python scripts/validate_project_artifact.py <temporary-file>`; only on `PASS` atomically replace the intended output. If preflight or validation fails, delete no existing output, report the actual errors, and do not claim completion.

Do not state that a formula or performance target has been achieved, and do not create any Challenge, CTQ, test, design-space, experiment, optimization, gate-review, or freeze artifact.
