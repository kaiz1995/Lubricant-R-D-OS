---
name: duty-challenge-analysis
description: Convert one validated lubricant duty profile into one traceable Challenge Map member at CHALLENGES_DEFINED; hold without writing when the duty profile or challenge judgments are incomplete.
---

# Duty Challenge Analysis

Create exactly one duty-derived Challenge Map member. This is not a failure mechanism, CTQ, test plan, formulation, or performance conclusion.

Use `../../schemas/challenge.schema.json` as source-pack authority when available. The installed copy in `references/` is deployment-only.

## Required input

Provide one JSON input with:

- `duty_artifact`: path to a schema-valid `duty` artifact with `stage: "DUTY_DEFINED"` and `decision: "GO"`.
- `challenge`: non-empty `duty_reference`, `challenge_id`, `category`, `description`, `severity`, `exposure`, `lubricant_sensitivity`, `evidence_gap`, and `priority`. Use the canonical Challenge schema enum values.
- Non-empty `challenge_evidence`; each item needs `evidence_id`, `statement`, `source`, and `status: "OBSERVED"`.

Run `python scripts/preflight_duty_challenge.py <input.json>` first. The input must explicitly supply temperature, load, contamination, life, and all three challenge levels. Never infer these values or grades from product category, typical service, or a missing record.

## HOLD rule

If the Duty artifact is invalid, not `DUTY_DEFINED`/`GO`, any challenge judgment is absent/invalid, or challenge evidence is incomplete, report `HOLD` and create no artifact. Do not write a partial map member or convert evidence gaps into conclusions.

## Artifact

For valid input, write one UTF-8 JSON file to the requested path, or `challenge-<project_id>-<challenge_id>.json` in the current workspace. Before overwrite, read the target: overwrite only a JSON `artifact_type: "challenge"` with the same `project_id` and `challenge_id`; otherwise report the exact conflict.

The output uses only canonical schema keys:

- `artifact_type: "challenge"`, `schema_version: "0.1.0"`, `project_id` from the validated Project Charter, and `stage: "CHALLENGES_DEFINED"`.
- Challenge fields copied from `challenge` without regrading.
- `evidence` retains the supplied duty evidence and `challenge_evidence` as evidence items only.
- `decision_question`, `hypothesis`, `uncertainty`, `decision_rule`, `result`, `decision`, and `next_action`. Record only the supplied duty-to-challenge decision; `decision` is `"GO"`; `next_action` is `"Define failure and CTQ relationships."`.

Write a temporary sibling JSON file. Run `python scripts/validate_duty_challenge_artifact.py <temporary-file>`; only on `PASS` atomically replace the target. If preflight or validation fails, leave the existing target unchanged and report the actual errors.

Stop at `CHALLENGES_DEFINED`. Do not create Failure/CTQ, test, design-space, experiment, formulation, performance, gate, or freeze artifacts.
