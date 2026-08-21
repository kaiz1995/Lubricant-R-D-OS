"""Install Project Definition with a verified deployment copy of its two schemas."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path


PACK_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PACK_ROOT / "skills" / "project-definition"
CANONICAL = PACK_ROOT / "schemas"
ROAMING_APP_DATA = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
DEFAULT_TARGET = ROAMING_APP_DATA / "com.ai4s.workbench" / "runtime" / "xdg-config" / "opencode" / "skills" / "user"
SCHEMA_NAMES = ("common.schema.json", "project.schema.json")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="OpenCode user-skill directory")
    args = parser.parse_args()
    target = args.target.resolve()
    if not target.is_dir():
        print(f"FAIL: target user-skill directory does not exist: {target}")
        return 1
    destination = target / "project-definition"
    if destination.exists() and not destination.is_dir():
        print(f"FAIL: destination is not a directory: {destination}")
        return 1

    shutil.copytree(SOURCE, destination, dirs_exist_ok=True)
    deployed = destination / "references"
    deployed.mkdir(exist_ok=True)
    for name in SCHEMA_NAMES:
        shutil.copy2(CANONICAL / name, deployed / name)
        if digest(CANONICAL / name) != digest(deployed / name):
            print(f"FAIL: deployed schema hash mismatch: {name}")
            return 1
    print(f"PASS: installed project-definition to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
