# Lubricant R&D Domain Pack

V0 is a minimal, independently installable proof that an external Lubricant R&D domain pack can be loaded and invoked by Open Science/OpenCode.

## Contents

- `skills/hello-lubricant/SKILL.md` — a load-and-invoke smoke skill only.
- `skills/project-definition/` — Stage 0 Project Charter creation with deployed preflight and schema validation.
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

This validates seven artifact types only: project, duty-derived challenge,
failure/CTQ, test-method qualification, constrained design space, experiment,
and Gate review. The state-machine validator checks Gate/lifecycle transitions,
evidence retention, rollback, Pivot, Kill, and Freeze boundaries. Neither
validator generates formulations or claims product performance.

## Install

Use Open Science's existing skill installation entry with the complete contents of `skills/hello-lubricant/SKILL.md`. Install Project Definition with `python scripts/install_project_definition_skill.py`; it copies the Skill plus verified deployment copies of its two canonical schemas into the private OpenCode user-skill profile. Neither Skill belongs in bundled/core skill directories.

## Smoke acceptance

The runtime skill catalog must show `hello-lubricant`, its description, and a user-skill location. A real `$hello-lubricant` invocation in an isolated workspace must create `hello_lubricant_result.json` with `status: "loaded-and-invoked"` and the required confirmation fields.

## Non-goals

This V0 pack does not generate formulations, perform lubricant research, make R&D conclusions, provide a database, MCP server, UI, or deterministic calculation engine.
