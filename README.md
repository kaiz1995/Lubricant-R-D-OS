# Lubricant R&D Domain Pack

V0 is a minimal, independently installable proof that an external Lubricant R&D domain pack can be loaded and invoked by Open Science/OpenCode.

## Contents

- `skills/hello-lubricant/SKILL.md` — a load-and-invoke smoke skill only.
- `skills/project-definition/` — Stage 0 Project Charter creation with deployed preflight and schema validation.
- `skills/duty-challenge-analysis/` — one evidence-bound Challenge Map member at `CHALLENGES_DEFINED`.
- `skills/failure-ctq-analysis/` — one evidence-bound Failure/CTQ record at `FAILURE_CTQ_DEFINED`.
- `skills/doe-design/` — one evidence-bound constrained-mixture request at `EXPERIMENT_DESIGNED`; it does not generate DOE points.
- `skills/statistical-analysis/` — one evidence-bound Phase 4 statistical-analysis request at `MODEL_BUILT`; it does not calculate a model.
- `skills/optimization/` — one evidence-bound Phase 4 optimization request at `OPTIMIZED`; it does not calculate candidates or recommendations.
- `skills/gate-review/` — one evidence-bound review Gate at `VERIFIED`; it does not Freeze or Close a project.
- `schemas/` — Draft 2020-12 contracts for Decision-Driven R&D artifacts.
- `fixtures/` — Schema fixtures plus state-machine transition fixtures.
- `scripts/validate_schemas.py` — repeatable JSON Schema validation entry point.
- `contracts/state-machine.json` and `scripts/validate_state_machine.py` — lifecycle/Gate contract and stdlib verifier.

## Schema validation

Run from the pack root:

```powershell
python scripts/validate_schemas.py
python scripts/validate_state_machine.py
```

This validates ten artifact types only: project, duty-derived challenge,
failure/CTQ, test-method qualification, constrained design space, experiment
design request, observed experiment record, statistical-model request, optimization request, and Gate review. The state-machine validator checks Gate/lifecycle transitions,
evidence retention, rollback, Pivot, Kill, and Freeze boundaries. Neither
validator generates formulations or claims product performance.

## Install

Use Open Science's existing skill installation entry with the complete contents of `skills/hello-lubricant/SKILL.md`. Install a structured Skill with `python scripts/install_domain_skill.py project-definition --target <Open Science user-skill directory>` (substitute any other supported Skill name, including `doe-design`, `statistical-analysis`, `optimization`, or `gate-review`); it copies that Skill plus verified deployment copies of only its canonical schemas into the explicit target. `PASS` proves copying only, not catalog loading: reload/restart Open Science, then run the runtime E2E smoke check. Neither Skill belongs in bundled/core skill directories.

## Smoke acceptance

The runtime skill catalog must show `hello-lubricant`, its description, and a user-skill location. A real `$hello-lubricant` invocation in an isolated workspace must create `hello_lubricant_result.json` with `status: "loaded-and-invoked"` and the required confirmation fields.

## Non-goals

The Phase 3 Skills do not generate formulations or calculations. This repository also contains separate deterministic Phase 4 cost, DOE, statistics, and optimization engines; they are not yet exposed through the Open Science Runtime. This V0 pack does not perform lubricant research, make R&D conclusions, or provide a database, MCP server, or UI.
