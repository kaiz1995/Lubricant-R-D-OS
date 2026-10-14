"""Install one supported Domain Pack skill with verified deployment schema copies."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PACK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK_ROOT))

from integrations.open_science import install_skill, rollback_skill


SKILLS = {
    "project-definition": ("common.schema.json", "project.schema.json"),
    "duty-definition": ("common.schema.json", "project.schema.json", "duty.schema.json"),
    "duty-challenge-analysis": ("common.schema.json", "project.schema.json", "duty.schema.json", "challenge.schema.json"),
    "failure-ctq-analysis": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json"),
    "test-method-qualification": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json"),
    # 2026-10-14 (I-3): the skill also produces the material records the design
    # space resolves its material_reference against (preflight_material.py /
    # build_material_artifact.py / validate_material_artifact.py), and the
    # validator loads material.schema.json -- so it must be deployed here or the
    # double-list guard (check_double_list.py) turns red with
    # "loaded but NOT deployed".
    "formulation-design": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "material.schema.json"),
    "process-definition": ("common.schema.json", "design_space.schema.json", "process.schema.json"),
    # 2026-10-13: doe-design also owns the sequential next-batch decision
    # (preflight_next_batch.py / validate_next_batch_artifact.py), so the
    # deploy list carries next_batch.schema.json like every other loaded schema.
    "doe-design": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "next_batch.schema.json"),
    # 2026-10-14: the bench path now resolves the screening release it spends a slot
    # on (BENCH_SCHEMA_NAMES loads screening.schema.json), so the deploy list carries
    # it -- the double-list guard requires every script-loaded schema here.
    "experiment-import": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "bench_test.schema.json", "screening.schema.json"),
    # 2026-10-14: the grease modeling entry (step 14) reads the round plan it must
    # trace to (campaign_artifact) -- after the v1.0.0 merge that record is the
    # merged bench.json, so bench.schema.json is loaded here; the double-list
    # guard requires it in the deploy list.
    "statistical-analysis": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json", "batch.schema.json", "screening.schema.json", "bench_test.schema.json", "variance.schema.json", "bench.schema.json"),
    "optimization": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json", "optimization.schema.json", "variance.schema.json"),
    "process-scale-up": ("common.schema.json", "process.schema.json", "optimization.schema.json"),
    "application-definition": ("common.schema.json", "application.schema.json"),
    # 2026-10-14: application-validation's upstream contract is the merged bench
    # record (stage BENCH_RESOURCE_REGISTERED) since the v1.0.0 merge; the
    # deployment list follows the schema its preflight loads.
    "application-validation": ("common.schema.json", "application.schema.json", "bench.schema.json", "bench_test.schema.json"),
    # 2026-10-13: bench-registration also opens the inner-loop round plan; since
    # the v1.0.0 merge that plan lives in the same bench.json record, so the skill
    # loads bench.schema.json (the former campaign.schema.json is gone) and keeps
    # project.schema.json for the project_reference the merged record carries.
    "bench-registration": ("common.schema.json", "project.schema.json", "bench.schema.json"),
    "interface-definition": ("common.schema.json", "interface.schema.json"),
    "external-record-import": ("common.schema.json", "external_record.schema.json"),
    "reference-material": ("common.schema.json", "project.schema.json", "reference.schema.json"),
    "grease-batch": ("common.schema.json", "project.schema.json", "design_space.schema.json", "experiment_design.schema.json", "batch.schema.json", "sample.schema.json"),
    "grease-screening": ("common.schema.json", "project.schema.json", "batch.schema.json", "sample.schema.json", "screening.schema.json"),
    "variance-assessment": ("common.schema.json", "bench_test.schema.json", "variance.schema.json"),
    "knowledge-archive": ("common.schema.json", "project.schema.json", "knowledge_asset.schema.json"),
    "gate-review": ("common.schema.json", "project.schema.json", "challenge.schema.json", "failure_ctq.schema.json", "test_method.schema.json", "design_space.schema.json", "experiment_design.schema.json", "experiment.schema.json", "model.schema.json", "optimization.schema.json", "gate.schema.json", "process.schema.json", "benchmark.schema.json", "evidence_qualification.schema.json", "design_freeze.schema.json"),
    "lubricant-rd-agent": ("common.schema.json", "project.schema.json", "gate.schema.json", "benchmark.schema.json", "evidence_qualification.schema.json", "design_freeze.schema.json", "knowledge_asset.schema.json"),
}
ENGINE_ROOT = PACK_ROOT / "domains" / "lubricant"
ENGINE_SKILLS = {"formulation-design", "doe-design", "statistical-analysis", "optimization"}

# Pack-level shared modules deployed beside a skill's own scripts so the deployed
# preflight resolves them without reaching back into the pack tree. Single source
# of truth lives in PACK_ROOT/scripts; this only declares which skills consume
# which module (WP-04a: both formulation-design and doe-design consume
# constraint_role.py through this one deployment path).
SHARED_MODULE_ROOT = PACK_ROOT / "scripts"
SHARED_MODULES = {
    # WP-11: both Stage 1 and Stage 3 preflights search CLOSED knowledge
    # assets and FROZEN design freezes through the one pack-level retrieval
    # module; it is deployed beside each consuming skill's scripts.
    "duty-definition": ("knowledge_retrieval.py",),
    # WP-06: application-validation imports the producing skill's PASS rule
    # (application_policy.py) as the single source of truth for the APPLIED
    # entry gate; the file is deployed beside this skill's scripts so a
    # deployed preflight resolves it without reaching back into the pack tree.
    "application-validation": (PACK_ROOT / "skills" / "application-definition" / "scripts" / "application_policy.py",),
    # WP-04a: both formulation-design and doe-design consume constraint_role.py
    # through this one deployment path.
    #
    # 2026-10-03: 工件命名校验器。工作台面板按规范名 <type>.json 判定阶段完成
    # （apps/desktop .../lubricantArtifacts.ts 的 probeOne），而本领域包多个技能
    # 的默认输出名与之一致性无强制校验，导致严格按文档执行的 agent 产出面板认不出
    # 的文件名、面板进度落后于真实进度。故把校验器部署到每个会落盘工件的技能旁，
    # 并在各 SKILL.md 的落盘步骤里要求运行。
    "duty-challenge-analysis": ("knowledge_retrieval.py", "check_artifact_naming.py"),
    "failure-ctq-analysis": ("knowledge_retrieval.py", "check_artifact_naming.py"),
    "test-method-qualification": ("check_artifact_naming.py",),
    "formulation-design": ("constraint_role.py", "check_artifact_naming.py"),
    "doe-design": ("constraint_role.py", "check_artifact_naming.py"),
    "gate-review": ("check_artifact_naming.py",),
    "reference-material": ("check_artifact_naming.py",),
    "grease-batch": ("check_artifact_naming.py",),
    "grease-screening": ("check_artifact_naming.py",),
    "variance-assessment": ("check_artifact_naming.py",),
    "knowledge-archive": ("check_artifact_naming.py",),
}

# Pack-level language-agnostic contracts deployed into a skill's references/ so a
# deployed router resolves them without reaching back into the pack tree. Single
# source of truth stays PACK_ROOT/contracts; lubricant-rd-agent's route_step.py
# reads `type_routes` from it (WP-02).
CONTRACT_ROOT = PACK_ROOT / "contracts"
CONTRACTS = {
    "lubricant-rd-agent": ("state-machine.json",),
    # 2026-10-14: the merged bench record defaults max_iterations from the contract
    # (12); carrying it keeps the deployed preflight identical to the pack behavior.
    "bench-registration": ("state-machine.json",),
}


def shared_modules_for(skill: str) -> tuple[Path, ...]:
    return tuple(SHARED_MODULE_ROOT / name for name in SHARED_MODULES.get(skill, ()))


def contracts_for(skill: str) -> tuple[Path, ...]:
    return tuple(CONTRACT_ROOT / name for name in CONTRACTS.get(skill, ()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", choices=sorted(SKILLS), help="supported Domain Pack skill")
    parser.add_argument("--target", type=Path, required=True, help="OpenCode user skills or <workspace>/.opencode/skills")
    parser.add_argument("--workspace-root", type=Path, help="required for an isolated workspace target")
    parser.add_argument("--rollback", action="store_true", help="restore the latest replacement backup for this skill")
    parser.add_argument("--backup", type=Path, help="specific backup directory, only with --rollback")
    args = parser.parse_args()

    try:
        if args.backup is not None and not args.rollback:
            raise ValueError("--backup requires --rollback")
        if args.rollback:
            destination = rollback_skill(args.target, args.skill, workspace_root=args.workspace_root, backup=args.backup)
            print(f"PASS: rolled back {args.skill} at {destination}")
            return 0
        source = PACK_ROOT / "skills" / args.skill
        engine_root = ENGINE_ROOT if args.skill in ENGINE_SKILLS else None
        destination = install_skill(
            source,
            PACK_ROOT / "schemas",
            SKILLS[args.skill],
            args.target,
            engine_root=engine_root,
            workspace_root=args.workspace_root,
            shared_modules=shared_modules_for(args.skill),
            contract_files=contracts_for(args.skill),
        )
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
