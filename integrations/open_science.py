"""Thin Open Science file-install adapter for Domain Pack skills."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


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


def install_skill(
    source_skill: Path,
    schema_root: Path,
    schema_names: tuple[str, ...],
    target: Path,
    engine_root: Path | None = None,
) -> Path:
    """Copy one skill and its canonical schemas into an explicit target."""
    if target.is_symlink() or not target.is_dir():
        raise ValueError(f"target must be an existing non-symlink directory: {target}")
    if not source_skill.is_dir() or not (source_skill / "SKILL.md").is_file():
        raise ValueError(f"skill source is missing SKILL.md: {source_skill}")

    destination = target / source_skill.name
    if destination.is_symlink() or destination.exists() and not destination.is_dir():
        raise ValueError(f"destination must be a non-symlink directory: {destination}")
    references = destination / "references"
    if references.is_symlink() or references.exists() and not references.is_dir():
        raise ValueError(f"references must be a non-symlink directory: {references}")

    for name in schema_names:
        if not (schema_root / name).is_file():
            raise ValueError(f"canonical schema is missing: {schema_root / name}")

    expected = non_cached_files(source_skill) | {Path("references") / name for name in schema_names}
    engine_target = None
    if engine_root is not None:
        if not engine_root.is_dir() or not (engine_root / "compute" / "__main__.py").is_file():
            raise ValueError(f"engine root is missing the compute package: {engine_root}")
        engine_target = destination / "engine" / engine_root.name
        expected |= {Path("engine") / engine_root.name / relative for relative in non_cached_files(engine_root)}
    if destination.exists():
        stale = non_cached_files(destination) - expected
        if stale:
            raise ValueError(f"destination contains stale/unmanaged files: {', '.join(map(str, sorted(stale)))}")

    shutil.copytree(
        source_skill,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    references.mkdir(exist_ok=True)
    for name in schema_names:
        canonical = schema_root / name
        deployed = references / name
        shutil.copy2(canonical, deployed)
        if digest(canonical) != digest(deployed):
            raise OSError(f"deployed schema hash mismatch: {name}")
    if engine_target is not None and engine_root is not None:
        shutil.copytree(
            engine_root,
            engine_target,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        for relative in non_cached_files(engine_root):
            source, deployed = engine_root / relative, engine_target / relative
            if not deployed.is_file() or digest(source) != digest(deployed):
                raise OSError(f"deployed engine hash mismatch: {relative}")

    if non_cached_files(destination) != expected:
        raise OSError("deployed non-cached file set does not match expected files")
    for relative in non_cached_files(source_skill):
        source, deployed = source_skill / relative, destination / relative
        if not deployed.is_file() or digest(source) != digest(deployed):
            raise OSError(f"deployed skill hash mismatch: {relative}")
    return destination
