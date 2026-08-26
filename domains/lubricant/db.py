"""Local data layer for the lubricant domain pack.

SQLite via stdlib only. Every row carries an evidence_scope so synthetic
demo data can never be mistaken for physical evidence at query level.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

TABLES = ("material", "formula", "test_method", "experiment", "benchmark", "artifact")
SCOPES = ("synthetic", "demo", "physical", "unknown")
CLASSIFICATIONS = ("public", "internal", "confidential_formulation", "customer_confidential")
SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    evidence_scope TEXT NOT NULL CHECK (evidence_scope IN ('synthetic','demo','physical','unknown')),
    data_classification TEXT NOT NULL DEFAULT 'internal' CHECK (data_classification IN ('public','internal','confidential_formulation','customer_confidential')),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    for table in TABLES:
        conn.execute(_SCHEMA.format(table=table))
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "data_classification" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN data_classification TEXT NOT NULL DEFAULT 'internal' "
                "CHECK (data_classification IN ('public','internal','confidential_formulation','customer_confidential'))"
            )
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def upsert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    if table not in TABLES:
        raise ValueError(f"unknown table: {table}")
    if row.get("evidence_scope") not in SCOPES:
        raise ValueError(f"invalid evidence_scope: {row.get('evidence_scope')}")
    classification = row.get("data_classification", "internal")
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"invalid data_classification: {classification}")
    conn.execute(
        f"INSERT OR REPLACE INTO {table} (id,name,version,evidence_scope,data_classification,payload_json) VALUES (?,?,?,?,?,?)",
        (row["id"], row["name"], int(row.get("version", 1)), row["evidence_scope"], classification, json.dumps(row["payload"], ensure_ascii=False)),
    )
    conn.commit()


def get(conn: sqlite3.Connection, table: str, id_: str) -> dict | None:
    cur = conn.execute(f"SELECT id,name,version,evidence_scope,data_classification,payload_json FROM {table} WHERE id=?", (id_,))
    row = cur.fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "version": row[2], "evidence_scope": row[3], "data_classification": row[4], "payload": json.loads(row[5])}


def list_rows(conn: sqlite3.Connection, table: str, evidence_scope: str | None = None) -> list[dict]:
    sql = f"SELECT id,name,version,evidence_scope,data_classification,payload_json FROM {table}"
    params: tuple = ()
    if evidence_scope is not None:
        sql += " WHERE evidence_scope=?"
        params = (evidence_scope,)
    return [
        {"id": r[0], "name": r[1], "version": r[2], "evidence_scope": r[3], "data_classification": r[4], "payload": json.loads(r[5])}
        for r in conn.execute(sql, params).fetchall()
    ]


def delete(conn: sqlite3.Connection, table: str, id_: str) -> bool:
    cur = conn.execute(f"DELETE FROM {table} WHERE id=?", (id_,))
    conn.commit()
    return cur.rowcount > 0


_CSV_COLS = ("id", "name", "version", "evidence_scope", "data_classification", "payload")


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
                "data_classification": raw.get("data_classification") or "internal",
                "payload": json.loads(raw["payload"]),
            })
            count += 1
    return count


def export_snapshot(conn: sqlite3.Connection, path: str | Path) -> None:
    snap = {t: list_rows(conn, t) for t in TABLES}
    Path(path).write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")


def backup(conn: sqlite3.Connection, target_path: str | Path) -> None:
    target = sqlite3.connect(str(target_path))
    try:
        conn.backup(target)
    finally:
        target.close()


def restore(source_path: str | Path, target_path: str | Path) -> None:
    target_path = Path(target_path)
    if target_path.exists():
        raise ValueError(f"target already exists: {target_path}")
    source = sqlite3.connect(str(source_path))
    target = sqlite3.connect(str(target_path))
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()


def _openpyxl():
    try:
        from openpyxl import Workbook, load_workbook
    except ImportError as exc:
        raise RuntimeError("XLSX requires openpyxl; install it explicitly to enable XLSX I/O") from exc
    return Workbook, load_workbook


def export_xlsx(conn: sqlite3.Connection, table: str, path: str | Path) -> None:
    Workbook, _ = _openpyxl()
    book = Workbook()
    sheet = book.active
    sheet.title = table
    sheet.append(_CSV_COLS)
    for row in list_rows(conn, table):
        sheet.append([json.dumps(row["payload"], ensure_ascii=False) if col == "payload" else row[col] for col in _CSV_COLS])
    book.save(path)


def import_xlsx(conn: sqlite3.Connection, table: str, path: str | Path) -> int:
    _, load_workbook = _openpyxl()
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = book.active
        headers = [cell.value for cell in next(sheet.iter_rows())]
        count = 0
        for values in sheet.iter_rows(min_row=2, values_only=True):
            raw = dict(zip(headers, values))
            if not any(value is not None for value in values):
                continue
            upsert(conn, table, {"id": raw["id"], "name": raw["name"], "version": int(raw["version"]),
                                 "evidence_scope": raw["evidence_scope"], "data_classification": raw.get("data_classification") or "internal",
                                 "payload": json.loads(raw["payload"])})
            count += 1
        return count
    finally:
        book.close()
