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
    "duty-definition": ("common.schema.json", "project.schema.json", "duty.schema.json"),
    "duty-challenge-analysis": ("common.schema.json", "project.schema.json", "duty.schema.json", "challenge.schema.json"),
    "failure-ctq-analysis": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json"),
    "test-method-qualification": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json"),
    "formulation-design": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json"),
    "doe-design": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json"),
    "experiment-import": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json"),
    "statistical-analysis": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json"),
    "optimization": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json", "optimization.schema.json"),
    "gate-review": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json", "optimization.schema.json", "gate.schema.json", "benchmark.schema.json", "evidence_qualification.schema.json", "design_freeze.schema.json"),
    "lubricant-rd-agent": ("common.schema.json", "project.schema.json", "gate.schema.json", "benchmark.schema.json", "evidence_qualification.schema.json", "design_freeze.schema.json", "knowledge_asset.schema.json"),
}
ENGINE_ROOT = PACK_ROOT / "domains" / "lubricant"
ENGINE_SKILLS = {"formulation-design", "doe-design", "statistical-analysis", "optimization"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", choices=sorted(SKILLS), help="supported Domain Pack skill")
    parser.add_argument("--target", type=Path, required=True, help="existing Open Science user-skill directory")
    args = parser.parse_args()

    source = PACK_ROOT / "skills" / args.skill
    try:
        engine_root = ENGINE_ROOT if args.skill in ENGINE_SKILLS else None
        destination = install_skill(source, PACK_ROOT / "schemas", SKILLS[args.skill], args.target, engine_root=engine_root)
    except (ValueError, OSError) as error:
        print(f"FAIL: {error}")
        return 1
    print(f"PASS: copied {args.skill} to {destination}")
    if engine_root is not None:
        print(f"PASS: bundled engine tree at {destination / 'engine' / engine_root.name}")
    print("RELOAD_REQUIRED: reload/restart Open Science before catalog acceptance")
    return 0


if __name__ == "__main__":
    sys.exit(main())
