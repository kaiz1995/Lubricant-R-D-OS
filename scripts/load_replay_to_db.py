#!/usr/bin/env python3
"""Load parsed R5 replay artifacts into the local synthetic-only database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "domains"))

from lubricant.db import connect, export_snapshot, list_rows, upsert  # noqa: E402


def load_replay(artifact_dir: Path, result_json: Path, db_path: Path, snapshot_path: Path) -> int:
    """Load one synthetic R5 replay and return the number of parsed artifacts."""
    result = json.loads(result_json.read_text(encoding="utf-8"))
    if result.get("scope") != "SYNTHETIC_DEMO_ONLY":
        raise SystemExit("refusing to load replay without SYNTHETIC_DEMO_ONLY scope")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    loaded = 0
    try:
        for path in sorted(artifact_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"warning: skipped {path.name}: {exc}", file=sys.stderr)
                continue
            upsert(conn, "artifact", {
                "id": path.stem,
                "name": path.stem,
                "evidence_scope": "synthetic",
                "data_classification": payload.get("data_classification", "internal"),
                "payload": payload,
            })
            loaded += 1
        export_snapshot(conn, snapshot_path)
        return loaded
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("result_json", type=Path)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("snapshot_path", type=Path)
    args = parser.parse_args()

    loaded = load_replay(args.artifact_dir, args.result_json, args.db_path, args.snapshot_path)
    print(f"artifacts loaded: {loaded}")
    conn = connect(args.db_path)
    try:
        print(f"artifacts in db: {len(list_rows(conn, 'artifact'))}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
