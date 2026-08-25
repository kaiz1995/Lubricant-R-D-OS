---
name: duty-definition
description: Record one evidence-declared lubricant duty profile at DUTY_DEFINED; hold without writing when the Project Charter or any required duty condition is incomplete.
---

# Duty Definition

Use `../../schemas/duty.schema.json` as authority when available; installed `references/` are deployment-only.

## Required input

- Supply `project_artifact`: a schema-valid Project Charter at `PROJECT_DEFINED` with `status: "ACTIVE"`.
- Supply non-empty `duty_id` and all of `duty.equipment`, `operating_conditions`, `maintenance`, `temperature`, `load`, `contamination`, and `life`.
- Every duty item needs non-empty `value`, `source`, `evidence_id`, and `statement`, with `status: "OBSERVED"` or `"ASSUMED"`. Preserve declared assumptions; never upgrade `ASSUMED` to `OBSERVED`.

Run `python scripts/preflight_duty_definition.py <input.json>` first. A missing item or `GAP` is `HOLD` and writes nothing. Do not derive a Challenge, Failure/CTQ, test method, formulation, experiment, calculation, or performance conclusion.

## Artifact

Run `python scripts/build_duty_artifact.py <input.json> <temporary-file>` after preflight. The builder creates the canonical `duty` artifact at `DUTY_DEFINED`, retaining the source Project Charter reference and supplied duty evidence statuses only.

Run `python scripts/validate_duty_artifact.py <temporary-file>`, then atomically replace only a matching `artifact_type`/`project_id`/`duty_id` target after `PASS`. Stop at `DUTY_DEFINED`; the next Skill may record a supplied duty-derived Challenge.
