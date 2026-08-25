---
name: experiment-import
description: Import one PHYSICAL experiment record with DOE-point and execution provenance; hold without writing when provenance is incomplete.
---

# Experiment Import

Use `../../schemas/experiment.schema.json` as authority when available; installed `references/` are deployment-only.

## Required input

- Supply schema-valid, `decision: GO` project, challenge, failure/CTQ, qualified PHYSICAL test method, design space, and PHYSICAL experiment-design artifacts for one project.
- Supply one raw DOE output file. It must validate as an `OK` DOE output. This Skill records its SHA-256 bytes digest and each selected `run_index`; it does not generate or recalculate DOE points.
- Supply one PHYSICAL execution record with per-run formula reference/version, raw-record reference, timezone-bearing execution timestamp, operator, instrument, calibration, and per-measurement method/qualification references.

## Decision boundary

- This Skill accepts PHYSICAL input only. `SYNTHETIC`, missing provenance, `GAP`, a digest mismatch, a duplicate or absent DOE point, or a broken upstream link is `HOLD`; write nothing.
- `PHYSICAL` is a source declaration only. An imported record is not owner approval, method qualification, product performance, or release approval.
- Do not convert units, calculate statistics, infer performance, or create Freeze, Close, or release artifacts.

## Artifact

Run `python scripts/preflight_experiment_import.py <input.json>`, then `python scripts/build_experiment_artifact.py <input.json> <temporary-file>`, then `python scripts/validate_experiment_artifact.py <temporary-file>`. Stop at `EXPERIMENT_RUNNING`.
