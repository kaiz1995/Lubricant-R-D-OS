---
name: hello-lubricant
description: Use only to verify that the external Lubricant R&D Domain Pack is loaded and invoked by Open Science/OpenCode. Do not use it for formulation work, lubricant research, or R&D conclusions.
---

# Hello Lubricant

This is a smoke-test skill for the external Lubricant R&D Domain Pack. It exists only to prove that the skill was loaded and that a real invocation can write an artifact in the current workspace.

When invoked, do all of the following:

1. State a concise, structured confirmation containing the skill name, pack name, status, artifact path, and the fact that this is a smoke test.
2. Create `hello_lubricant_result.json` in the current workspace. Write valid UTF-8 JSON, overwriting only that exact smoke artifact if it already exists.
3. Use this exact top-level shape, with `status` exactly `loaded-and-invoked`:

```json
{
  "schema_version": "0.1",
  "pack": "lubricant-rd-domain-pack",
  "skill": "hello-lubricant",
  "status": "loaded-and-invoked",
  "decision_question": "Can the external Lubricant R&D Domain Pack skill be loaded and invoked?",
  "evidence": [
    "The runtime loaded and invoked hello-lubricant.",
    "This artifact was written in the current workspace."
  ],
  "next_action": "Proceed to the next independently verified Phase 1 step."
}
```

Do not generate a lubricant formulation, calculate lubricant performance, perform research, or make any R&D/product conclusion. If the artifact cannot be written, report the exact error and do not claim `loaded-and-invoked`.
