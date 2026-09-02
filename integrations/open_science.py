"""Thin Open Science file-install adapter for Domain Pack skills."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path


USER_OPENCODE_SKILLS = Path.home() / ".config" / "opencode" / "skills"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_cached(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix == ".pyc"


def non_cached_files(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and not is_cached(path.relative_to(root))
    }


def has_symlink(path: Path) -> bool:
    return any(_is_link_or_reparse(part) for part in (path, *path.parents))


def has_symlink_descendant(root: Path) -> bool:
    return _is_link_or_reparse(root) or any(_is_link_or_reparse(path) for path in root.rglob("*"))


def _is_link_or_reparse(path: Path) -> bool:
    """Reject symlinks and Windows reparse points, including directory junctions."""
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        attributes = 0
    return path.is_symlink() or path.is_junction() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def is_protected_path(path: Path) -> bool:
    parts = tuple(part.lower() for part in path.parts)
    return "open-science" in parts or any(parts[index : index + 3] == ("runtime", "skills", "core") for index in range(len(parts) - 2))


def validate_install_target(target: Path, workspace_root: Path | None = None) -> Path:
    """Return one approved user or isolated-workspace OpenCode skills directory."""
    target = Path(target)
    if has_symlink(target):
        raise ValueError(f"target or ancestor must not be a symlink: {target}")
    resolved = target.resolve()
    if is_protected_path(target) or is_protected_path(resolved):
        raise ValueError(f"target is a protected Core path: {target}")
    if not resolved.is_dir():
        raise ValueError(f"target must be an existing directory: {target}")

    user_skills = USER_OPENCODE_SKILLS.resolve()
    if resolved == user_skills:
        return resolved
    if workspace_root is None:
        raise ValueError("target must be the user OpenCode skills directory or an explicit workspace .opencode/skills directory")

    workspace_root = Path(workspace_root)
    if has_symlink(workspace_root):
        raise ValueError(f"workspace root or ancestor must not be a symlink: {workspace_root}")
    workspace_root = workspace_root.resolve()
    if is_protected_path(workspace_root) or not workspace_root.is_dir():
        raise ValueError(f"workspace root must be an existing non-Core directory: {workspace_root}")
    if resolved != (workspace_root / ".opencode" / "skills").resolve():
        raise ValueError("target must equal <workspace-root>/.opencode/skills")
    return resolved


def _verify_tree(source: Path, deployed: Path, label: str) -> None:
    if has_symlink_descendant(deployed):
        raise OSError(f"deployed {label} contains a symlink")
    for relative in non_cached_files(source):
        source_file, deployed_file = source / relative, deployed / relative
        if not deployed_file.is_file() or digest(source_file) != digest(deployed_file):
            raise OSError(f"deployed {label} hash mismatch: {relative}")


def _matching_tree(left: Path, right: Path) -> bool:
    left_files, right_files = non_cached_files(left), non_cached_files(right)
    return left_files == right_files and all(digest(left / relative) == digest(right / relative) for relative in left_files)


def _backup_path(destination: Path, suffix: str = "backup") -> Path:
    prefix = f".{destination.name}.{suffix}"
    candidate = destination.parent / prefix
    index = 1
    while candidate.exists() or candidate.is_symlink():
        candidate = destination.parent / f"{prefix}-{index}"
        index += 1
    return candidate


def _build_staging_tree(
    source_skill: Path,
    schema_root: Path,
    schema_names: tuple[str, ...],
    target: Path,
    engine_root: Path | None,
) -> tuple[Path, set[Path]]:
    staging = Path(tempfile.mkdtemp(prefix=f".{source_skill.name}.staging-", dir=target))
    expected = non_cached_files(source_skill) | {Path("references") / name for name in schema_names}
    try:
        shutil.copytree(source_skill, staging, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        references = staging / "references"
        references.mkdir(exist_ok=True)
        for name in schema_names:
            canonical, deployed = schema_root / name, references / name
            shutil.copy2(canonical, deployed)
            if digest(canonical) != digest(deployed):
                raise OSError(f"deployed schema hash mismatch: {name}")
        if engine_root is not None:
            engine_target = staging / "engine" / engine_root.name
            shutil.copytree(engine_root, engine_target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            expected |= {Path("engine") / engine_root.name / relative for relative in non_cached_files(engine_root)}
            _verify_tree(engine_root, engine_target, "engine")
        if non_cached_files(staging) != expected:
            raise OSError("deployed non-cached file set does not match expected files")
        _verify_tree(source_skill, staging, "skill")
        return staging, expected
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def install_skill(
    source_skill: Path,
    schema_root: Path,
    schema_names: tuple[str, ...],
    target: Path,
    engine_root: Path | None = None,
    workspace_root: Path | None = None,
) -> Path:
    """Copy one skill and its canonical schemas into an explicit target."""
    target = validate_install_target(target, workspace_root)
    if not source_skill.is_dir() or not (source_skill / "SKILL.md").is_file():
        raise ValueError(f"skill source is missing SKILL.md: {source_skill}")

    destination = target / source_skill.name
    if _is_link_or_reparse(destination) or destination.exists() and not destination.is_dir():
        raise ValueError(f"destination must be a non-symlink directory: {destination}")

    for name in schema_names:
        if not (schema_root / name).is_file():
            raise ValueError(f"canonical schema is missing: {schema_root / name}")

    if engine_root is not None:
        if not engine_root.is_dir() or not (engine_root / "compute" / "__main__.py").is_file():
            raise ValueError(f"engine root is missing the compute package: {engine_root}")

    staging, expected = _build_staging_tree(source_skill, schema_root, schema_names, target, engine_root)
    if destination.exists():
        if has_symlink_descendant(destination):
            shutil.rmtree(staging, ignore_errors=True)
            raise ValueError(f"destination contains a symlink: {destination}")
        stale = non_cached_files(destination) - expected
        # ponytail: legacy references/ schemas predate per-skill schema lists;
        # remove once every real deployment is refreshed (targeted 2026-08). 
        stale = {
            path for path in stale
            if not (path.parts[0] == "references" and path.suffix == ".json")
        }
        if stale:
            shutil.rmtree(staging, ignore_errors=True)
            raise ValueError(f"destination contains stale/unmanaged files: {', '.join(map(str, sorted(stale)))}")
        if _matching_tree(destination, staging):
            shutil.rmtree(staging)
            return destination

    try:
        if destination.exists():
            backup = _backup_path(destination)
            os.replace(destination, backup)
            try:
                os.replace(staging, destination)
            except BaseException:
                os.replace(backup, destination)
                raise
        else:
            os.replace(staging, destination)
        return destination
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def rollback_skill(target: Path, skill: str, workspace_root: Path | None = None, backup: Path | None = None) -> Path:
    """Atomically restore one verified replacement backup."""
    target = validate_install_target(target, workspace_root)
    destination = target / skill
    if not destination.is_dir() or _is_link_or_reparse(destination) or has_symlink_descendant(destination):
        raise ValueError(f"destination must be a non-symlink skill directory: {destination}")
    if backup is None:
        backups = sorted(target.glob(f".{skill}.backup*"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not backups:
            raise ValueError(f"no backup found for skill: {skill}")
        backup = backups[0]
    backup = Path(backup)
    if backup.parent.resolve() != target or not backup.is_dir() or _is_link_or_reparse(backup) or has_symlink_descendant(backup):
        raise ValueError(f"backup must be a non-symlink sibling directory: {backup}")
    if not (backup / "SKILL.md").is_file():
        raise ValueError(f"backup is not a skill directory: {backup}")

    replaced = _backup_path(destination, "rollback")
    os.replace(destination, replaced)
    try:
        os.replace(backup, destination)
    except BaseException:
        os.replace(replaced, destination)
        raise
    return destination
