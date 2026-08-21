"""Install one supported Domain Pack skill with verified deployment schema copies."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PACK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK_ROOT))

from integrations.open_science import install_skill


SKILLS = {
    "project-definition": ("common.schema.json", "project.schema.json"),
    "duty-challenge-analysis": ("common.schema.json", "project.schema.json", "challenge.schema.json"),
    "failure-ctq-analysis": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json"),
    "test-method-qualification": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json"),
    "formulation-design": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json"),
    "doe-design": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", choices=sorted(SKILLS), help="supported Domain Pack skill")
    parser.add_argument("--target", type=Path, required=True, help="existing Open Science user-skill directory")
    args = parser.parse_args()

    source = PACK_ROOT / "skills" / args.skill
    try:
        destination = install_skill(source, PACK_ROOT / "schemas", SKILLS[args.skill], args.target)
    except (ValueError, OSError) as error:
        print(f"FAIL: {error}")
        return 1
    print(f"PASS: copied {args.skill} to {destination}")
    print("RELOAD_REQUIRED: reload/restart Open Science before catalog acceptance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
