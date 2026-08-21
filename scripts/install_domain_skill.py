"""Install one supported Domain Pack skill with verified deployment schema copies."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path


PACK_ROOT = Path(__file__).resolve().parents[1]
SKILLS = {
    "project-definition": ("common.schema.json", "project.schema.json"),
    "duty-challenge-analysis": ("common.schema.json", "project.schema.json", "challenge.schema.json"),
    "failure-ctq-analysis": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json"),
    "test-method-qualification": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json"),
}
ROAMING_APP_DATA = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
DEFAULT_TARGET = ROAMING_APP_DATA / "com.ai4s.workbench" / "runtime" / "xdg-config" / "opencode" / "skills" / "user"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", choices=sorted(SKILLS), help="supported Domain Pack skill")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="existing OpenCode user-skill directory")
    args = parser.parse_args()

    target = args.target.resolve()
    source = PACK_ROOT / "skills" / args.skill
    if not source.is_dir() or not (source / "SKILL.md").is_file():
        print(f"FAIL: supported skill source is missing: {source}")
        return 1
    if not target.is_dir():
        print(f"FAIL: target user-skill directory does not exist: {target}")
        return 1
    destination = target / args.skill
    if destination.exists() and not destination.is_dir():
        print(f"FAIL: destination is not a directory: {destination}")
        return 1

    shutil.copytree(source, destination, dirs_exist_ok=True)
    deployed = destination / "references"
    deployed.mkdir(exist_ok=True)
    for name in SKILLS[args.skill]:
        canonical = PACK_ROOT / "schemas" / name
        if not canonical.is_file():
            print(f"FAIL: canonical schema is missing: {canonical}")
            return 1
        shutil.copy2(canonical, deployed / name)
        if digest(canonical) != digest(deployed / name):
            print(f"FAIL: deployed schema hash mismatch: {name}")
            return 1
    print(f"PASS: installed {args.skill} to {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
