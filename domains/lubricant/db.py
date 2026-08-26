"""Local data layer for the lubricant domain pack.

SQLite via stdlib only. Every row carries an evidence_scope so synthetic
demo data can never be mistaken for physical evidence at query level.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

TABLES = ("material", "formula", "test_method", "experiment", "benchmark")
SCOPES = ("synthetic", "demo", "physical", "unknown")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    evidence_scope TEXT NOT NULL CHECK (evidence_scope IN ('synthetic','demo','physical','unknown')),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

# ponytail: csv-only export; add openpyxl/xlsx when a real user needs it.


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    for table in TABLES:
        conn.execute(_SCHEMA.format(table=table))
    conn.commit()
    return conn


def upsert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    if table not in TABLES:
        raise ValueError(f"unknown table: {table}")
    if row.get("evidence_scope") not in SCOPES:
        raise ValueError(f"invalid evidence_scope: {row.get('evidence_scope')}")
    conn.execute(
        f"INSERT OR REPLACE INTO {table} (id,name,version,evidence_scope,payload_json) VALUES (?,?,?,?,?)",
        (row["id"], row["name"], int(row.get("version", 1)), row["evidence_scope"], json.dumps(row["payload"], ensure_ascii=False)),
    )
    conn.commit()


def get(conn: sqlite3.Connection, table: str, id_: str) -> dict | None:
    cur = conn.execute(f"SELECT id,name,version,evidence_scope,payload_json FROM {table} WHERE id=?", (id_,))
    row = cur.fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "version": row[2], "evidence_scope": row[3], "payload": json.loads(row[4])}


def list_rows(conn: sqlite3.Connection, table: str, evidence_scope: str | None = None) -> list[dict]:
    sql = f"SELECT id,name,version,evidence_scope,payload_json FROM {table}"
    params: tuple = ()
    if evidence_scope is not None:
        sql += " WHERE evidence_scope=?"
        params = (evidence_scope,)
    return [
        {"id": r[0], "name": r[1], "version": r[2], "evidence_scope": r[3], "payload": json.loads(r[4])}
        for r in conn.execute(sql, params).fetchall()
    ]


def delete(conn: sqlite3.Connection, table: str, id_: str) -> bool:
    cur = conn.execute(f"DELETE FROM {table} WHERE id=?", (id_,))
    conn.commit()
    return cur.rowcount > 0


_CSV_COLS = ("id", "name", "version", "evidence_scope", "payload")


def export_csv(conn: sqlite3.Connection, table: str, path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_COLS)
        writer.writeheader()
        for row in list_rows(conn, table):
            flat = {k: row[k] for k in _CSV_COLS if k != "payload"}
            flat["payload"] = json.dumps(row["payload"], ensure_ascii=False)
            writer.writerow(flat)


def import_csv(conn: sqlite3.Connection, table: str, path: str | Path) -> int:
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            upsert(conn, table, {
                "id": raw["id"],
                "name": raw["name"],
                "version": int(raw["version"]),
                "evidence_scope": raw["evidence_scope"],
                "payload": json.loads(raw["payload"]),
            })
            count += 1
    return count


def export_snapshot(conn: sqlite3.Connection, path: str | Path) -> None:
    snap = {t: list_rows(conn, t) for t in TABLES}
    Path(path).write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
