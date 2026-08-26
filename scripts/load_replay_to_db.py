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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("result_json", type=Path)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("snapshot_path", type=Path)
    args = parser.parse_args()

    result = json.loads(args.result_json.read_text(encoding="utf-8"))
    if result.get("scope") != "SYNTHETIC_DEMO_ONLY":
        raise SystemExit("refusing to load replay without SYNTHETIC_DEMO_ONLY scope")

    args.db_path.parent.mkdir(parents=True, exist_ok=True)
    args.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(args.db_path)
    loaded = 0
    try:
        for path in sorted(args.artifact_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"warning: skipped {path.name}: {exc}", file=sys.stderr)
                continue
            upsert(conn, "artifact", {
                "id": path.stem,
                "name": path.stem,
                "evidence_scope": "synthetic",
                "payload": payload,
            })
            loaded += 1
        export_snapshot(conn, args.snapshot_path)
        print(f"artifacts loaded: {loaded}")
        print(f"artifacts in db: {len(list_rows(conn, 'artifact'))}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
