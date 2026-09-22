"""Direct-run checks for the release preflight report."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from release_preflight import FORBIDDEN_CONCLUSIONS, run_preflight  # noqa: E402


def main() -> None:
    report = run_preflight(ROOT)
    assert report["status"] == "PASS", json.dumps(report, ensure_ascii=False)
    names = [check["check"] for check in report["checks"]]
    assert "bundle:rejects-physical" in names
    assert "install:all-skills" in names
    assert "file:LICENSE" in names
    assert report["hold_gates"] == ["G5_REAL_VALUE", "G6_RELEASE", "G7_UI_ACCEPTANCE", "G8_DESKTOP_PROVENANCE"]
    assert not any(word in json.dumps(report) for word in FORBIDDEN_CONCLUSIONS)
    print("test_release_preflight: ALL PASS")


if __name__ == "__main__":
    main()
