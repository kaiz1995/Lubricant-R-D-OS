"""Tests for check_measurement_sentinels.py (stdlib unittest only)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_measurement_sentinels as cms


def measurement(value, status=None, unit="CNY/kg", source="user-2026-10-02", **extra):
    obj = {
        "value": value,
        "unit": unit,
        "source": source,
        "method_version": "v1",
        "material_batch": "B001",
        "formula_version": "F001",
    }
    if status is not None:
        obj["status"] = status
    obj.update(extra)
    return obj


def write_json(directory: Path, name: str, data) -> Path:
    path = directory / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class SentinelScanTests(unittest.TestCase):
    def run_scan(self, data_by_file):
        """Run scan_workspace over a temp dir; return (last_line, all_lines)."""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            for name, data in data_by_file.items():
                write_json(workspace, name, data)
            lines = cms.scan_workspace(workspace)
        return lines[-1], lines

    # --- R1: explicit non-SET status + numeric value ---

    def test_numeric_value_with_deferred_is_violation(self):
        last, lines = self.run_scan(
            {"a.json": {"target_cost": measurement(120, status="DEFERRED")}}
        )
        self.assertTrue(last.startswith("HOLD:"))
        self.assertIn(
            "value=120 is numeric but status='DEFERRED'", "\n".join(lines)
        )

    def test_numeric_value_with_pending_client_is_violation(self):
        last, _ = self.run_scan(
            {"a.json": {"target_cost": measurement(120, status="PENDING_CLIENT")}}
        )
        self.assertTrue(last.startswith("HOLD:"))

    def test_numeric_value_with_set_status_passes(self):
        last, _ = self.run_scan(
            {"a.json": {"target_cost": measurement(120, status="SET")}}
        )
        self.assertTrue(last.startswith("PASS:"))

    # --- R3: numeric + no status is backward compatible OK ---

    def test_numeric_value_without_status_is_ok(self):
        last, _ = self.run_scan({"a.json": {"target_cost": measurement(120)}})
        self.assertTrue(last.startswith("PASS:"))

    def test_zero_value_without_status_is_ok(self):
        # Regression: 0 is a legitimate physical quantity (e.g. additive
        # percentage lower bound); bare numbers must never be flagged.
        last, _ = self.run_scan({"a.json": {"lb": measurement(0)}})
        self.assertTrue(last.startswith("PASS:"))

    def test_negative_one_without_status_and_plain_unit_is_ok(self):
        # Regression: bare -1 cannot be distinguished from a legitimate
        # negative quantity; hardcoded numeric sentinel lists are removed.
        last, _ = self.run_scan({"a.json": {"target_cost": measurement(-1)}})
        self.assertTrue(last.startswith("PASS:"))

    def test_null_value_with_deferred_passes(self):
        last, _ = self.run_scan(
            {"a.json": {"target_cost": measurement(None, status="DEFERRED")}}
        )
        self.assertTrue(last.startswith("PASS:"))

    def test_null_value_without_status_not_script_scope(self):
        # value=null without status is rejected by the schema itself (allOf
        # if/then), so the script deliberately reports nothing here.
        last, _ = self.run_scan({"a.json": {"target_cost": measurement(None)}})
        self.assertTrue(last.startswith("PASS:"))

    # --- R2: sentinel marker in unit/source (case-insensitive) ---

    def test_sentinel_unit_marker_is_violation(self):
        last, lines = self.run_scan(
            {"a.json": {"target_cost": measurement(
                -1, unit="SENTINEL-UNSET-CNY/kg")}}
        )
        self.assertTrue(last.startswith("HOLD:"))
        self.assertIn("sentinel marker", "\n".join(lines))
        self.assertIn("'unit'", "\n".join(lines))

    def test_sentinel_source_marker_is_violation(self):
        last, lines = self.run_scan(
            {"a.json": {"target_cost": measurement(
                120, source="UNSET: user deferred this target")}}
        )
        self.assertTrue(last.startswith("HOLD:"))
        self.assertIn("'source'", "\n".join(lines))

    def test_sentinel_marker_case_insensitive(self):
        last, _ = self.run_scan(
            {"a.json": {"target_cost": measurement(5, unit="sentinel-unset")}}
        )
        self.assertTrue(last.startswith("HOLD:"))

    def test_sentinel_marker_with_set_status_still_violation(self):
        # Rule R2 fires regardless of value or status.
        last, _ = self.run_scan(
            {"a.json": {"target_cost": measurement(
                -1, status="SET", unit="SENTINEL-UNSET-CNY/kg")}}
        )
        self.assertTrue(last.startswith("HOLD:"))

    # --- structural detection ---

    def test_nested_measurement_inside_array_is_found(self):
        data = {"items": [{"nested": {"deep": measurement(
            -1, unit="SENTINEL-UNSET")}}]}
        last, lines = self.run_scan({"a.json": data})
        self.assertTrue(last.startswith("HOLD:"))
        joined = "\n".join(lines)
        self.assertIn("a.json#items[0].nested.deep", joined)

    def test_non_measurement_object_ignored(self):
        data = {
            "value": 0,
            "unit": "kg",
            "some_other": {"value": -1, "unit": "x"},
            "full_but_fine": measurement(None, status="PENDING_CLIENT"),
        }
        last, _ = self.run_scan({"a.json": data})
        self.assertTrue(last.startswith("PASS:"))

    def test_unreadable_json_reports_warn_and_holds(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "bad.json").write_text("{not json", encoding="utf-8")
            lines = cms.scan_workspace(workspace)
        self.assertTrue(lines[-1].startswith("HOLD:"))
        self.assertTrue(any(line.startswith("WARN: bad.json:") for line in lines))
        self.assertIn("0 violation(s)", lines[-1])

    # --- unit-level ---

    def test_check_object_unit(self):
        self.assertIsNone(cms.check_object(measurement(120, status="SET")))
        self.assertIsNone(cms.check_object(measurement(120)))
        self.assertIsNone(cms.check_object(measurement(0)))
        self.assertIsNone(cms.check_object(measurement(-1)))
        self.assertIsNone(cms.check_object(measurement(None, status="DEFERRED")))
        self.assertIsNone(cms.check_object(measurement(None, status="PENDING_CLIENT")))
        self.assertIsNone(cms.check_object(measurement(None)))
        self.assertIsNotNone(cms.check_object(measurement(120, status="DEFERRED")))
        self.assertIsNotNone(cms.check_object(measurement(120, status="PENDING_CLIENT")))
        self.assertIsNotNone(cms.check_object(measurement(-1, unit="SENTINEL-UNSET-CNY/kg")))
        self.assertIsNotNone(cms.check_object(measurement(120, source="unset target")))
        # bool must not count as a numeric value for R1
        self.assertIsNone(cms.check_object(measurement(True, status="DEFERRED")))


if __name__ == "__main__":
    unittest.main()
