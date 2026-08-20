# Lubricant R&D Domain Pack

V0 is a minimal, independently installable proof that an external Lubricant R&D domain pack can be loaded and invoked by Open Science/OpenCode.

## Contents

- `skills/hello-lubricant/SKILL.md` — a load-and-invoke smoke skill only.

## Install

Use Open Science's existing skill installation entry with the complete contents of `skills/hello-lubricant/SKILL.md`. The app installs it under its private OpenCode user-skill profile; it must not be copied into bundled/core skill directories.

## Smoke acceptance

The runtime skill catalog must show `hello-lubricant`, its description, and a user-skill location. A real `$hello-lubricant` invocation in an isolated workspace must create `hello_lubricant_result.json` with `status: "loaded-and-invoked"` and the required confirmation fields.

## Non-goals

This V0 pack does not generate formulations, perform lubricant research, make R&D conclusions, define schemas, provide a database, MCP server, UI, or deterministic calculation engine.
