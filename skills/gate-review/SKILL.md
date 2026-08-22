---
name: gate-review
description: Record one evidence-bound review Gate at VERIFIED; hold GO requests with unresolved conditions or evidence gaps and reject unsupported non-GO dispositions without explicit reason and evidence.
---

# Gate Review

Use `../../schemas/gate.schema.json` as authority when available; installed `references/` are deployment-only.

## Required input

- Supply schema-valid project, challenge, failure/CTQ, qualified method, design space, experiment design, observed experiment, model, and optimization artifacts for one active project, all `decision: GO` and at their required stages.
- `gate` supplies `gate_id`, `scope`, `gate_status`, the four condition/risk lists, `reason`, and `evidence`. `experiment_reference` is derived from the observed experiment.
- A requested `GO` requires empty `unsatisfied_conditions` and `evidence_gaps`, plus no `GAP` evidence. Otherwise the deterministic disposition is `HOLD`. `PIVOT`, `KILL`, and `FREEZE` require an explicit non-empty reason and evidence without GAP; otherwise reject without writing.

## Decision boundary

- This is a review record, not a new calculation, Freeze artifact, or Close action. It cannot advance past `VERIFIED` and never writes `FROZEN` or `CLOSED`.

## Artifact

Run `python scripts/preflight_gate_review.py <input.json>`, `python scripts/build_gate_artifact.py <input.json> <temporary-file>`, then `python scripts/validate_gate_artifact.py <temporary-file>`. Stop at `VERIFIED`.
