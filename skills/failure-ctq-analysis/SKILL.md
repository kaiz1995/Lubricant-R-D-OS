---
name: failure-ctq-analysis
description: Convert one validated lubricant Challenge Map member into one evidence-bound Failure/CTQ record at FAILURE_CTQ_DEFINED; hold without writing when diagnosis, hypotheses, contribution uncertainty, CTQ limits, or evidence are incomplete.
---

# Failure CTQ Analysis

Use `../../schemas/failure_ctq.schema.json` as authority when available; `references/` contains installed copies.

## Required input

Provide one JSON input. Preflight validates schema-valid `project_artifact` (`PROJECT_DEFINED`/`ACTIVE`), schema-valid `challenge_artifact` (`CHALLENGES_DEFINED`), matching project/challenge references, and all required failure, CTQ, test-chain, and evidence fields. Evidence status is only `OBSERVED`, `ASSUMED`, or `GAP`.

Every root-cause item starts with `Hypothesis:` or `假设:`, has content after the prefix, and makes no confirmed-cause claim. `lubricant_contribution` must remain explicitly possible or pending verification.

Each CTQ needs classification `CTQ`, `DEGRADATION_INDICATOR`, or `FUNCTIONAL_SYMPTOM`, plus observable, test references, evidence required, and complete limits. `specification_limit` is the compliance line; `engineering_risk_limit` is the engineering-risk line. Never conflate them.

Run `python scripts/preflight_failure_ctq.py <input.json>` first. Never infer a failure diagnosis, a root cause, a lubricant cause, a CTQ, a test, or a limit from product type or a field observation.

## HOLD rule

On any preflight error, report `HOLD`, create no artifact, write no partial record, and never upgrade an evidence gap to a conclusion.

## Artifact

Write one UTF-8 `failure_ctq` JSON at `FAILURE_CTQ_DEFINED`. Before overwrite, require the same `artifact_type`, `project_id`, and `failure_id`; otherwise report the conflict.

Use only schema keys. Preserve input hypotheses and uncertainty without upgrading them; copy only supplied evidence. Set `decision: "GO"` and `next_action: "Qualify the proposed test method."` with all schema-required decision fields.

Write a temporary sibling JSON file. Run `python scripts/validate_failure_ctq_artifact.py <temporary-file>`; only on `PASS` atomically replace the target. If preflight or validation fails, leave the existing target unchanged and report the actual errors.

Stop at `FAILURE_CTQ_DEFINED`; do not create test qualification, formulation, performance, or any downstream artifact.
