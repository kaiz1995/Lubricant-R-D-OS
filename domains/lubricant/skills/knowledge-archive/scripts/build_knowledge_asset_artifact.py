"""Build the only permitted KNOWLEDGE_ARCHIVED artifact from preflight-valid input.

Deterministic assembly only. Every judgment - the derived asset status, the synthetic
marker, and the canonical decision block - lives in ``knowledge_archive_policy`` so this
builder and the validator cannot disagree.

The builder never invents an asset. The six entries are written exactly as supplied, the
status is the downgrade-only resolution of the caller's claim, and a SYNTHETIC project is
force-marked ``SYNTHETIC_DEMO_ONLY`` and capped at ``DRAFT_KNOWLEDGE``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from knowledge_archive_policy import (
    ASSET_KEYS,
    STAGE,
    SYNTHETIC_MARKER,
    expected_decision_fields,
    resolved_status,
    status_notes,
)
from preflight_knowledge_archive import errors_for, resolved_path, upstream_errors


def build_artifact(data: dict, project: dict) -> dict:
    """Assemble the knowledge archive. Pure function of validated input + charter."""
    knowledge_assets = data["knowledge_assets"]
    evidence_scope = data["evidence_scope"]
    evidence = data["evidence"]
    asset_status = resolved_status(data["asset_status"], knowledge_assets, evidence_scope)
    artifact = {
        "schema_version": "0.1.0",
        "artifact_type": "knowledge_asset",
        "project_id": project["project_id"],
        "stage": STAGE,
        "evidence_scope": evidence_scope,
        **expected_decision_fields(knowledge_assets, evidence_scope, asset_status, evidence),
        "evidence": evidence,
        "asset_status": asset_status,
        "knowledge_assets": {key: dict(knowledge_assets[key]) for key in ASSET_KEYS},
    }
    if evidence_scope == "SYNTHETIC":
        # Forced, never claimed: a synthetic project can never close.
        artifact["synthetic_marker"] = SYNTHETIC_MARKER
    return artifact


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_knowledge_asset_artifact.py <input.json> <temporary-file>")
        return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, input_path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    _, project = upstream_errors(resolved_path(data["project_artifact"], input_path))
    artifact = build_artifact(data, project)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path} stage={STAGE} asset_status={artifact['asset_status']}")
    for line in status_notes(data["asset_status"], data["knowledge_assets"], data["evidence_scope"]):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
