"""Direct-run checks for the synthetic-only workspace bundle."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_workspace_bundle import build_bundle  # noqa: E402


def result(scope: str = "SYNTHETIC_DEMO_ONLY") -> dict:
    return {
        "scope": scope,
        "gate": "G4",
        "date": "2026-08-28",
        "conclusion": "WORKFLOW_VALIDATED",
        "chain": [
            {"step": 1, "skill": "duty-definition", "status": "PASS", "stage": "DUTY_DEFINED"},
            {"step": 2, "skill": "gate-review", "status": "HOLD", "stage": "VERIFIED"},
        ],
        "gaps": ["Synthetic workflow evidence only."],
    }


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def rejects(action, expected: str) -> None:
    try:
        action()
        raise AssertionError("expected rejection")
    except ValueError as exc:
        assert expected in str(exc), exc


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifacts = root / "artifacts"
        artifacts.mkdir()
        write_json(artifacts / "duty.json", {"artifact_type": "duty", "scope": "SYNTHETIC", "data_classification": "public"})
        write_json(artifacts / "gate.json", {"artifact_type": "gate", "scope": "SYNTHETIC"})
        result_path = root / "r5-result.json"
        write_json(result_path, result())

        output = root / "bundle"
        build_bundle(artifacts, result_path, output)
        expected = {"lubricant.db", "snapshot.json", "dashboard.html", "bundle-manifest.json"}
        assert {path.name for path in output.iterdir()} == expected
        manifest = json.loads((output / "bundle-manifest.json").read_text(encoding="utf-8"))
        assert manifest["source_result_filename"] == "r5-result.json"
        assert manifest["scope"] == "SYNTHETIC_DEMO_ONLY"
        assert manifest["generated_at"].endswith("Z")
        datetime.fromisoformat(manifest["generated_at"].replace("Z", "+00:00"))
        assert manifest["table_row_counts"]["artifact"] == 3
        assert manifest["data_classifications"] == ["internal", "public"]
        assert {item["name"] for item in manifest["files"]} == expected - {"bundle-manifest.json"}
        assert all((output / item["name"]).stat().st_size == item["bytes"] for item in manifest["files"])
        snapshot = json.loads((output / "snapshot.json").read_text(encoding="utf-8"))
        assert len(snapshot["artifact"]) == 3
        replay = next(row for row in snapshot["artifact"] if row["id"] == "r5-replay-result")
        assert replay["name"] == "r5-replay-result" and replay["payload"] == result()
        dashboard = (output / "dashboard.html").read_text(encoding="utf-8")
        assert "SYNTHETIC DEMO ONLY" in dashboard and "Stage Navigator" in dashboard and "Gate HOLD" in dashboard

        nonempty = root / "nonempty"
        nonempty.mkdir()
        (nonempty / "keep.txt").write_text("keep", encoding="utf-8")
        rejects(lambda: build_bundle(artifacts, result_path, nonempty), "nonempty output")

        physical_result = root / "physical-result.json"
        write_json(physical_result, result("PHYSICAL"))
        rejects(lambda: build_bundle(artifacts, physical_result, root / "physical-bundle"), "SYNTHETIC_DEMO_ONLY")

        confidential = root / "confidential"
        confidential.mkdir()
        write_json(confidential / "secret.json", {"data_classification": "confidential_formulation"})
        rejects(lambda: build_bundle(confidential, result_path, root / "confidential-bundle"), "encryption/ACL")

        nested_physical = root / "nested-physical"
        nested_physical.mkdir()
        write_json(nested_physical / "record.json", {"metadata": {"evidence_scope": "PHYSICAL"}})
        rejects(lambda: build_bundle(nested_physical, result_path, root / "nested-physical-bundle"), "physical record")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result_path = root / "r5-result.json"
        write_json(result_path, result("PHYSICAL"))
        try:
            build_bundle(root, result_path, root / "bundle")
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "SYNTHETIC_DEMO_ONLY" in str(exc), exc
        assert not (root / "bundle").exists()

    print("test_workspace_bundle: ALL PASS")


if __name__ == "__main__":
    main()
