#!/usr/bin/env python3
"""Build a local, synthetic-only R5 workspace bundle."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from generate_dashboard import build_html
from load_replay_to_db import REPLAY_RESULT_ARTIFACT_ID, load_replay


SCOPE = "SYNTHETIC_DEMO_ONLY"
FORBIDDEN_CLASSIFICATIONS = {"confidential_formulation", "customer_confidential"}


def _reject_sensitive_or_physical(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "data_classification" and item in FORBIDDEN_CLASSIFICATIONS:
                raise ValueError("refusing confidential bundle: encryption/ACL is unavailable")
            if key in {"evidence_scope", "scope"} and str(item).upper() == "PHYSICAL":
                raise ValueError("refusing physical record or conclusion in synthetic-only bundle")
            _reject_sensitive_or_physical(item)
    elif isinstance(value, list):
        for item in value:
            _reject_sensitive_or_physical(item)


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _reject_sensitive_or_physical(payload)
    return payload


def _replay_result_from_snapshot(snapshot: dict) -> dict:
    for artifact in snapshot.get("artifact", []):
        if artifact.get("id") == REPLAY_RESULT_ARTIFACT_ID:
            result = artifact.get("payload")
            if isinstance(result, dict):
                return result
    raise ValueError("snapshot is missing canonical R5 replay result artifact")


def _assert_empty_output(output_dir: Path) -> None:
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ValueError(f"refusing nonempty output directory: {output_dir}")


def build_bundle(artifact_dir: Path, result_json: Path, output_dir: Path) -> Path:
    """Build and return ``output_dir`` without overwriting an existing bundle."""
    result_scope = json.loads(result_json.read_text(encoding="utf-8")).get("scope")
    if result_scope != SCOPE:
        raise ValueError("refusing bundle without SYNTHETIC_DEMO_ONLY scope")
    _assert_empty_output(output_dir)
    # ponytail: raw text scan is intentionally strict; physical fixture reruns
    # need pre-filtered artifacts, not relaxed checks.
    for path in sorted(artifact_dir.glob("*.json")):
        _read_json(path)

    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "lubricant.db"
    snapshot_path = output_dir / "snapshot.json"
    dashboard_path = output_dir / "dashboard.html"
    load_replay(artifact_dir, result_json, db_path, snapshot_path)
    snapshot = _read_json(snapshot_path)
    result = _replay_result_from_snapshot(snapshot)
    dashboard_path.write_text(
        build_html(result, ["Physical Stage A", "Stage A2 / S1b / S2", "G6 真实数据 Gate", "G7 UI 验收"],
                   len(snapshot.get("artifact", []))),
        encoding="utf-8",
    )

    manifest = {
        "bundle_format_version": "1.0",
        "source_result_filename": result_json.name,
        "scope": SCOPE,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "files": [
            {"name": path.name, "bytes": path.stat().st_size}
            for path in (db_path, snapshot_path, dashboard_path)
        ],
        "table_row_counts": {table: len(rows) for table, rows in snapshot.items()},
        "data_classifications": sorted({
            row["data_classification"]
            for rows in snapshot.values()
            for row in rows
        }),
    }
    manifest_path = output_dir / "bundle-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("result_json", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(f"bundle written: {build_bundle(args.artifact_dir, args.result_json, args.output_dir)}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        sys.exit(str(exc))
