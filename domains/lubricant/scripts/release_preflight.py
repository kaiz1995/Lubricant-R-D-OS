#!/usr/bin/env python3
"""Release preflight for the lubricant domain pack.

Software pre-gate only. PASS means the domain-pack software bundle satisfies
scope/classification/install/preflight boundaries; it never asserts physical,
commercial, or real-data readiness (G5/G6/G7/G8 stay HOLD elsewhere).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integrations.open_science import install_skill  # noqa: E402
from scripts.install_domain_skill import ENGINE_ROOT, ENGINE_SKILLS, SKILLS  # noqa: E402


FORBIDDEN_CONCLUSIONS = ("METHOD_QUALIFIED", "KNOWN_GOOD", "KNOWN_BAD", "PHYSICAL_RELEASE_APPROVED")


def _fail(checks: list[dict], name: str, reason: str) -> None:
    checks.append({"check": name, "status": "FAIL", "detail": reason})


def run_preflight(pack_root: Path = ROOT) -> dict:
    checks: list[dict] = []

    for test in ("tests/test_workspace_bundle.py", "tests/test_lubricant_db.py", "tests/upstream_compat/test_skill_install.py"):
        result = subprocess.run(
            [sys.executable, "-B", str(pack_root / test)],
            cwd=pack_root, capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            _fail(checks, f"test:{test}", (result.stderr.strip() or result.stdout.strip())[-300:])
        else:
            checks.append({"check": f"test:{test}", "status": "PASS", "detail": result.stdout.strip().splitlines()[-1]})

    required_files = ["LICENSE", *(f"schemas/{name}" for name in sorted({s for schemas in SKILLS.values() for s in schemas}))]
    for relative in required_files:
        if (pack_root / relative).is_file():
            checks.append({"check": f"file:{relative}", "status": "PASS", "detail": "present"})
        else:
            _fail(checks, f"file:{relative}", "missing")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        artifacts = tmp_path / "artifacts"
        artifacts.mkdir()
        (artifacts / "duty.json").write_text(json.dumps({"artifact_type": "duty", "scope": "SYNTHETIC", "data_classification": "public"}), encoding="utf-8")
        result_path = tmp_path / "result.json"
        result_path.write_text(json.dumps({"scope": "SYNTHETIC_DEMO_ONLY", "gate": "preflight", "date": "2026-08-28", "conclusion": "WORKFLOW_VALIDATED", "chain": [], "gaps": []}), encoding="utf-8")
        from scripts.build_workspace_bundle import build_bundle
        try:
            build_bundle(artifacts, result_path, tmp_path / "bundle")
            checks.append({"check": "bundle:synthetic-only", "status": "PASS", "detail": "built"})
        except ValueError as exc:
            _fail(checks, "bundle:synthetic-only", str(exc))
        bad_path = result_path.with_name("bad-result.json")
        bad_path.write_text(result_path.read_text(encoding="utf-8").replace("SYNTHETIC_DEMO_ONLY", "PHYSICAL"), encoding="utf-8")
        try:
            build_bundle(artifacts, bad_path, tmp_path / "bad-bundle")
            _fail(checks, "bundle:rejects-physical", "physical scope accepted")
        except ValueError:
            checks.append({"check": "bundle:rejects-physical", "status": "PASS", "detail": "rejected"})

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "workspace"
        target = workspace / ".opencode" / "skills"
        target.mkdir(parents=True)
        try:
            for skill, schemas in SKILLS.items():
                install_skill(
                    pack_root / "skills" / skill,
                    pack_root / "schemas",
                    schemas,
                    target,
                    engine_root=ENGINE_ROOT if skill in ENGINE_SKILLS else None,
                    workspace_root=workspace,
                )
            checks.append({"check": "install:all-skills", "status": "PASS", "detail": f"{len(SKILLS)} skills"})
        except (ValueError, OSError) as exc:
            _fail(checks, "install:all-skills", str(exc))

    status = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    return {"preflight_version": "1.0", "status": status, "checks": checks,
            "hold_gates": ["G5_REAL_VALUE", "G6_RELEASE", "G7_UI_ACCEPTANCE", "G8_DESKTOP_PROVENANCE"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-root", type=Path, default=ROOT, help="domain pack root (default: script repo)")
    parser.add_argument("--json", type=Path, help="also write the report here")
    args = parser.parse_args()
    report = run_preflight(args.pack_root)
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
