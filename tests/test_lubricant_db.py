"""Direct-run tests for the lubricant local data layer."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "domains"))

from lubricant.db import connect, upsert, get, list_rows, delete, export_csv, import_csv, export_snapshot  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "lubricant.db"
        conn = connect(db_path)

        # upsert + get roundtrip
        mat = {"id": "m1", "name": "PAO 1540", "evidence_scope": "synthetic", "payload": {"kv40": 100}}
        upsert(conn, "material", mat)
        got = get(conn, "material", "m1")
        assert got == {**mat, "version": 1}, got

        # scope filter
        upsert(conn, "material", {"id": "m2", "name": "Real oil", "evidence_scope": "physical", "payload": {}})
        synth = list_rows(conn, "material", evidence_scope="synthetic")
        assert [r["id"] for r in synth] == ["m1"]
        all_rows = list_rows(conn, "material")
        assert len(all_rows) == 2

        # invalid scope rejected
        try:
            upsert(conn, "material", {"id": "x", "name": "x", "evidence_scope": "known_good", "payload": {}})
            raise AssertionError("invalid scope accepted")
        except ValueError:
            pass

        # unknown table rejected
        try:
            upsert(conn, "nope", mat)
            raise AssertionError("unknown table accepted")
        except ValueError:
            pass

        # delete
        assert delete(conn, "material", "m2") is True
        assert get(conn, "material", "m2") is None
        assert delete(conn, "material", "ghost") is False

        # csv roundtrip
        csv_path = Path(tmp) / "material.csv"
        export_csv(conn, "material", csv_path)
        conn2 = connect(Path(tmp) / "copy.db")
        try:
            n = import_csv(conn2, "material", csv_path)
            assert n == 1 and get(conn2, "material", "m1")["payload"] == {"kv40": 100}
        finally:
            conn2.close()

        # snapshot covers all five tables
        snap_path = Path(tmp) / "snap.json"
        export_snapshot(conn, snap_path)
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        assert set(snap.keys()) == {"material", "formula", "test_method", "experiment", "benchmark"}
        assert snap["benchmark"] == []
        conn.close()

    print("test_lubricant_db: ALL PASS")


if __name__ == "__main__":
    main()
