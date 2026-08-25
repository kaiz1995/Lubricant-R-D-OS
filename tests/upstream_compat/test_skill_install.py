"""Runnable compatibility check for the explicit Open Science skill target."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from integrations.open_science import digest, install_skill
from scripts.install_domain_skill import ENGINE_ROOT, ENGINE_SKILLS, SKILLS


def cached(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix == ".pyc"


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "explicit-target"
        target.mkdir()
        for skill, schemas in SKILLS.items():
            source = ROOT / "skills" / skill
            engine_root = ENGINE_ROOT if skill in ENGINE_SKILLS else None
            destination = install_skill(source, ROOT / "schemas", schemas, target, engine_root=engine_root)
            for file in source.rglob("*"):
                relative = file.relative_to(source)
                if file.is_file() and not cached(relative):
                    deployed = destination / relative
                    assert deployed.is_file() and digest(file) == digest(deployed), relative
            for schema in schemas:
                assert digest(ROOT / "schemas" / schema) == digest(destination / "references" / schema), schema
            if engine_root is not None:
                deployed_engine = destination / "engine" / ENGINE_ROOT.name
                for file in ENGINE_ROOT.rglob("*"):
                    relative = file.relative_to(ENGINE_ROOT)
                    if file.is_file() and not cached(relative):
                        deployed = deployed_engine / relative
                        assert deployed.is_file() and digest(file) == digest(deployed), relative
            assert not list(destination.rglob("__pycache__"))
            assert not list(destination.rglob("*.pyc"))

        stale_target = Path(temporary) / "stale-target"
        stale_destination = stale_target / "project-definition"
        stale_destination.mkdir(parents=True)
        existing, stale = stale_destination / "SKILL.md", stale_destination / "stale.txt"
        existing.write_text("keep", encoding="utf-8")
        stale.write_text("stale", encoding="utf-8")
        before = (digest(existing), digest(stale))
        try:
            install_skill(ROOT / "skills" / "project-definition", ROOT / "schemas", SKILLS["project-definition"], stale_target)
        except ValueError as error:
            assert "stale/unmanaged" in str(error)
        else:
            raise AssertionError("stale destination was accepted")
        assert before == (digest(existing), digest(stale))

        cli_target = Path(temporary) / "cli-target"
        cli_target.mkdir()
        installed = subprocess.run(
            [sys.executable, "-B", "scripts/install_domain_skill.py", "project-definition", "--target", str(cli_target)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert installed.returncode == 0 and "RELOAD_REQUIRED" in installed.stdout and "loaded" not in installed.stdout.lower()
        missing_target = subprocess.run(
            [sys.executable, "-B", "scripts/install_domain_skill.py", "project-definition"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert missing_target.returncode != 0 and "--target" in missing_target.stderr
    print(f"PASS: explicit-target install compatibility for {len(SKILLS)} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
