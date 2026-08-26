"""Direct-run tests for the lubricant local data layer."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "domains"))

from lubricant.db import (  # noqa: E402
    backup, connect, delete, export_csv, export_snapshot, export_xlsx, get, import_csv,
    import_xlsx, list_rows, restore, schema_version, upsert,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        legacy_path = Path(tmp) / "legacy.db"
        legacy = sqlite3.connect(legacy_path)
        legacy.execute("CREATE TABLE material (id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL, evidence_scope TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)")
        legacy.execute("INSERT INTO material VALUES ('legacy','old',1,'synthetic','{}',CURRENT_TIMESTAMP)")
        legacy.commit()
        legacy.close()
        migrated = connect(legacy_path)
        assert schema_version(migrated) == 2
        assert get(migrated, "material", "legacy")["data_classification"] == "internal"
        migrated.close()

        db_path = Path(tmp) / "lubricant.db"
        conn = connect(db_path)
        assert schema_version(conn) == 2

        # upsert + get roundtrip
        mat = {"id": "m1", "name": "PAO 1540", "evidence_scope": "synthetic", "payload": {"kv40": 100}}
        upsert(conn, "material", mat)
        got = get(conn, "material", "m1")
        assert got == {**mat, "version": 1, "data_classification": "internal"}, got

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

        upsert(conn, "material", {**mat, "id": "classified", "data_classification": "customer_confidential"})
        assert get(conn, "material", "classified")["data_classification"] == "customer_confidential"
        try:
            upsert(conn, "material", {**mat, "data_classification": "secret"})
            raise AssertionError("invalid classification accepted")
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
            assert n == 2 and get(conn2, "material", "m1")["payload"] == {"kv40": 100}
        finally:
            conn2.close()

        # artifact table roundtrip
        artifact = {"id": "duty", "name": "duty", "evidence_scope": "synthetic", "payload": {"kind": "duty"}}
        upsert(conn, "artifact", artifact)
        assert get(conn, "artifact", "duty") == {**artifact, "version": 1, "data_classification": "internal"}
        assert [r["id"] for r in list_rows(conn, "artifact")] == ["duty"]

        # snapshot covers all six tables
        snap_path = Path(tmp) / "snap.json"
        export_snapshot(conn, snap_path)
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        assert set(snap.keys()) == {"material", "formula", "test_method", "experiment", "benchmark", "artifact"}
        assert snap["material"][0]["data_classification"] == "internal"
        assert snap["benchmark"] == []
        conn.close()

        # backup/restore and no-overwrite
        source = connect(Path(tmp) / "source.db")
        upsert(source, "material", {"id": "b1", "name": "backup", "evidence_scope": "synthetic", "payload": {}})
        backup_path = Path(tmp) / "backup.db"
        backup(source, backup_path)
        source.close()
        restored_path = Path(tmp) / "restored.db"
        restore(backup_path, restored_path)
        restored = connect(restored_path)
        assert get(restored, "material", "b1")["name"] == "backup"
        restored.close()
        try:
            restore(backup_path, restored_path)
            raise AssertionError("restore overwrote target")
        except ValueError:
            pass

        # xlsx roundtrip
        xlsx_path = Path(tmp) / "material.xlsx"
        xlsx_copy = Path(tmp) / "xlsx-copy.db"
        xlsx_source = connect(Path(tmp) / "xlsx-source.db")
        upsert(xlsx_source, "material", {"id": "x1", "name": "xlsx", "evidence_scope": "physical",
                                          "data_classification": "confidential_formulation", "payload": {"a": 1}})
        export_xlsx(xlsx_source, "material", xlsx_path)
        xlsx_target = connect(xlsx_copy)
        assert import_xlsx(xlsx_target, "material", xlsx_path) == 1
        assert get(xlsx_target, "material", "x1")["data_classification"] == "confidential_formulation"
        xlsx_target.close()
        xlsx_source.close()

    print("test_lubricant_db: ALL PASS")


if __name__ == "__main__":
    main()
