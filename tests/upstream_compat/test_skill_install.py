"""Runnable compatibility check for the explicit Open Science skill target."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import integrations.open_science as open_science
from integrations.open_science import digest, install_skill, rollback_skill
from scripts.install_domain_skill import ENGINE_ROOT, ENGINE_SKILLS, SKILLS


def cached(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix == ".pyc"


def create_junction(link: Path, target: Path) -> None:
    created = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"New-Item -ItemType Junction -Path '{link}' -Target '{target}' | Out-Null",
        ],
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0 and link.is_junction(), created.stderr or created.stdout


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary) / "workspace"
        target = workspace / ".opencode" / "skills"
        target.mkdir(parents=True)
        for skill, schemas in SKILLS.items():
            source = ROOT / "skills" / skill
            engine_root = ENGINE_ROOT if skill in ENGINE_SKILLS else None
            destination = install_skill(source, ROOT / "schemas", schemas, target, engine_root=engine_root, workspace_root=workspace)
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

        stale_target = Path(temporary) / "stale-workspace" / ".opencode" / "skills"
        stale_destination = stale_target / "project-definition"
        stale_destination.mkdir(parents=True)
        existing, stale = stale_destination / "SKILL.md", stale_destination / "stale.txt"
        existing.write_text("keep", encoding="utf-8")
        stale.write_text("stale", encoding="utf-8")
        before = (digest(existing), digest(stale))
        try:
            install_skill(ROOT / "skills" / "project-definition", ROOT / "schemas", SKILLS["project-definition"], stale_target, workspace_root=stale_target.parents[1])
        except ValueError as error:
            assert "stale/unmanaged" in str(error)
        else:
            raise AssertionError("stale destination was accepted")
        assert before == (digest(existing), digest(stale))

        cli_workspace = Path(temporary) / "cli-workspace"
        cli_target = cli_workspace / ".opencode" / "skills"
        cli_target.mkdir(parents=True)
        installed = subprocess.run(
            [
                sys.executable,
                "-B",
                "scripts/install_domain_skill.py",
                "project-definition",
                "--target",
                str(cli_target),
                "--workspace-root",
                str(cli_workspace),
            ],
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

        protected_open_science = Path(temporary) / "open-science" / ".opencode" / "skills"
        protected_open_science.mkdir(parents=True)
        protected_core = Path(temporary) / "runtime" / "skills" / "core"
        protected_core.mkdir(parents=True)
        for unsafe_target in (protected_open_science, protected_core):
            try:
                install_skill(
                    ROOT / "skills" / "project-definition",
                    ROOT / "schemas",
                    SKILLS["project-definition"],
                    unsafe_target,
                    workspace_root=unsafe_target.parents[2],
                )
            except ValueError as error:
                assert "protected Core" in str(error)
            else:
                raise AssertionError(f"protected target was accepted: {unsafe_target}")

        junction_real = Path(temporary) / "junction-real"
        (junction_real / ".opencode" / "skills").mkdir(parents=True)
        junction_workspace = Path(temporary) / "junction-workspace"
        create_junction(junction_workspace, junction_real)
        try:
            try:
                install_skill(
                    ROOT / "skills" / "project-definition",
                    ROOT / "schemas",
                    SKILLS["project-definition"],
                    junction_workspace / ".opencode" / "skills",
                    workspace_root=junction_workspace,
                )
            except ValueError as error:
                assert "symlink" in str(error)
            else:
                raise AssertionError("junction workspace was accepted")
        finally:
            if junction_workspace.exists():
                junction_workspace.rmdir()

        ancestor_real = Path(temporary) / "ancestor-real"
        (ancestor_real / "workspace" / ".opencode" / "skills").mkdir(parents=True)
        junction_ancestor = Path(temporary) / "junction-ancestor"
        create_junction(junction_ancestor, ancestor_real)
        try:
            ancestor_workspace = junction_ancestor / "workspace"
            try:
                install_skill(
                    ROOT / "skills" / "project-definition",
                    ROOT / "schemas",
                    SKILLS["project-definition"],
                    ancestor_workspace / ".opencode" / "skills",
                    workspace_root=ancestor_workspace,
                )
            except ValueError as error:
                assert "symlink" in str(error)
            else:
                raise AssertionError("junction ancestor was accepted")
        finally:
            if junction_ancestor.exists():
                junction_ancestor.rmdir()

        failure_workspace = Path(temporary) / "failure-workspace"
        failure_target = failure_workspace / ".opencode" / "skills"
        failure_target.mkdir(parents=True)
        with patch.object(open_science.shutil, "copytree", side_effect=OSError("simulated copy failure")):
            try:
                install_skill(
                    ROOT / "skills" / "project-definition",
                    ROOT / "schemas",
                    SKILLS["project-definition"],
                    failure_target,
                    workspace_root=failure_workspace,
                )
            except OSError as error:
                assert "simulated copy failure" in str(error)
            else:
                raise AssertionError("copy failure was accepted")
        assert not list(failure_target.iterdir()), "copy failure left a partial install or staging directory"

        rollback_workspace = Path(temporary) / "rollback-workspace"
        rollback_target = rollback_workspace / ".opencode" / "skills"
        rollback_target.mkdir(parents=True)
        rollback_source = Path(temporary) / "rollback-skill"
        rollback_source.mkdir()
        (rollback_source / "SKILL.md").write_text("version one", encoding="utf-8")
        rollback_schemas = Path(temporary) / "rollback-schemas"
        rollback_schemas.mkdir()
        (rollback_schemas / "schema.json").write_text("{}", encoding="utf-8")
        install_skill(rollback_source, rollback_schemas, ("schema.json",), rollback_target, workspace_root=rollback_workspace)
        install_skill(rollback_source, rollback_schemas, ("schema.json",), rollback_target, workspace_root=rollback_workspace)
        assert not list(rollback_target.glob(".rollback-skill.backup*")), "identical install created a backup"
        (rollback_source / "SKILL.md").write_text("version two", encoding="utf-8")
        install_skill(rollback_source, rollback_schemas, ("schema.json",), rollback_target, workspace_root=rollback_workspace)
        backup = rollback_target / ".rollback-skill.backup"
        assert backup.is_dir() and (backup / "SKILL.md").read_text(encoding="utf-8") == "version one"
        rollback_skill(rollback_target, "rollback-skill", workspace_root=rollback_workspace)
        assert (rollback_target / "rollback-skill" / "SKILL.md").read_text(encoding="utf-8") == "version one"

        # legacy references/ schemas from older installs must not block refresh
        legacy_workspace = Path(temporary) / "legacy-workspace"
        legacy_target = legacy_workspace / ".opencode" / "skills"
        legacy_target.mkdir(parents=True)
        legacy_skill = legacy_target / "rollback-skill"
        legacy_skill.mkdir()
        (legacy_skill / "SKILL.md").write_text("old", encoding="utf-8")
        (legacy_skill / "references").mkdir()
        (legacy_skill / "references" / "old.schema.json").write_text("{}", encoding="utf-8")
        install_skill(rollback_source, rollback_schemas, ("schema.json",), legacy_target, workspace_root=legacy_workspace)
        assert (legacy_skill / "SKILL.md").read_text(encoding="utf-8") == "version two"
        assert (legacy_skill / "references" / "schema.json").is_file()
        assert not (legacy_skill / "references" / "old.schema.json").exists()
    print(f"PASS: explicit-target install compatibility for {len(SKILLS)} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
