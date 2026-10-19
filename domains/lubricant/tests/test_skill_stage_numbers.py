"""I-6 guard: SKILL.md CHECKPOINT hand-offs must speak stage constants, not bare "Stage N".

The pack runs THREE number systems at once: README's "17 个工艺步骤", the
contract's 20-stage PRECISION_GREASE_DEV sequence, and a stale oil-only
numbering (formulation-design "Stage 4", doe-design "Stage 5", ...). A
CHECKPOINT line that says "Pass to Stage 2 (duty-challenge-analysis)" is
ambiguous across all three, and on the grease route it is simply wrong
(DUTY_DEFINED's grease-route successor is FAILURE_MECHANISM_DEFINED).

Scope (the plan's L9 revision: "guard first narrow"):
  * GREEN judgement covers CHECKPOINT blocks ONLY. A block is the line
    carrying the ``🔴 CHECKPOINT`` marker plus the contiguous ``#`` comment
    lines that follow it (the hand-off sentence often spans two or three
    lines).
  * The full-file "Stage N" sweep is printed as INFO only and never turns the
    run red; cleaning that list is the separately scheduled optional item.

Rules checked inside every CHECKPOINT block:
  1. no bare ``Stage <number>`` token (e.g. "Stage 5", "Stage 3.5");
  2. at least one stage constant from ``contracts/state-machine.json`` must
     appear; skills that produce no workbench stage (the environment smoke
     skill and the router Meta-Skill) are exempt;
  3. every stage constant named in the block must be legal for the producing
     skill: one of the stages it produces (``route_step.py`` ROUTE_TABLE +
     PRODUCER_SKILL_FOR_STAGE, plus the DRAFT/companion records listed below)
     or a legal successor of those stages (``type_routes`` adjacency +
     ``loop_edges`` + ``on_demand_stages.next_stage``);
  4. a bare step ordinal (``第 N 步`` / ``step N``) must be route-qualified in
     the same block and reproduce via that route's ``--list-stages`` sequence
     (the plan's rule: ordinals only as "<ROUTE> 第 N 步", and N must be the
     stage ordinal -- never README's 17-step ordinal).

Both the producing-skill map and the successor map are derived from the
contract and the router at run time; the only hand-kept knowledge here is the
two exemptions and the record-stage constants noted above.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"
CONTRACT_PATH = ROOT / "contracts" / "state-machine.json"
ROUTE_SCRIPT = SKILLS_ROOT / "lubricant-rd-agent" / "scripts" / "route_step.py"

CHECKPOINT_MARKER = "🔴 CHECKPOINT"
STAGE_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9_]{3,}\b")
BARE_STAGE_RE = re.compile(r"\bStage\s+[0-9]", re.IGNORECASE)
BARE_STEP_RE = re.compile(r"第\s*(\d+)\s*步|\bstep\s+(\d+)\b", re.IGNORECASE)

# Skills that produce no workbench stage: hello-lubricant is the environment
# smoke check, lubricant-rd-agent the router Meta-Skill (README §7 declares
# both roles). Their CHECKPOINT blocks carry no stage constant by nature.
STAGE_FREE_SKILLS = frozenset({"hello-lubricant", "lubricant-rd-agent"})

# Records that carry a stage constant on their artifact without occupying a
# route stage. Source of truth is each skill's own builder:
#   build_bench_artifact.py / build_interface_artifact.py /
#   build_external_record_artifact.py write "stage": "DRAFT";
#   build_process_artifact.py writes "stage": "DESIGN_SPACE_DEFINED" (the
#   record is a companion of the design space, not an advance).
EXTRA_STAGE_PRODUCERS = {
    "bench-registration": {"DRAFT"},
    "interface-definition": {"DRAFT"},
    "external-record-import": {"DRAFT"},
    "process-definition": {"DESIGN_SPACE_DEFINED"},
}


def load_route_module():
    """Load route_step.py by path (it is not an importable package)."""
    spec = importlib.util.spec_from_file_location("route_step_under_test", ROUTE_SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover - broken checkout
        raise SystemExit(f"cannot load router module from {ROUTE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_successor_map(contract: dict) -> dict[str, set[str]]:
    """Legal successor stage -> set, from every published consumer fact."""
    result: dict[str, set[str]] = {}
    for sequence in contract["type_routes"].values():
        for current, following in zip(sequence, sequence[1:]):
            result.setdefault(current, set()).add(following)
    for edge in contract.get("loop_edges", ()):
        result.setdefault(edge["from"], set()).add(edge["to"])
    for stage, spec in contract.get("on_demand_stages", {}).items():
        result.setdefault(stage, set()).add(spec["next_stage"])
    return result


def build_producing_map(route_module) -> dict[str, set[str]]:
    """Skill -> stages it materialises (router table + producer registry + records)."""
    result: dict[str, set[str]] = {}
    for skill, stage in route_module.ROUTE_TABLE:
        result.setdefault(skill, set()).add(stage)
    for stage, skill in route_module.PRODUCER_SKILL_FOR_STAGE.items():
        result.setdefault(skill, set()).add(stage)
    for skill, stages in EXTRA_STAGE_PRODUCERS.items():
        result.setdefault(skill, set()).update(stages)
    return result


def allowed_stages(skill: str, producing: dict[str, set[str]], successors: dict[str, set[str]]) -> set[str]:
    """A skill's legal vocabulary: what it produces plus where those stages may go."""
    allowed: set[str] = set()
    for stage in producing.get(skill, set()):
        allowed.add(stage)
        allowed |= successors.get(stage, set())
    return allowed


def checkpoint_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """Return [start, end) index pairs: marker line + contiguous '#' lines."""
    blocks: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        if CHECKPOINT_MARKER in lines[index]:
            end = index + 1
            while end < len(lines) and lines[end].lstrip().startswith("#"):
                end += 1
            blocks.append((index, end))
            index = end
        else:
            index += 1
    return blocks


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    known_stages = set(contract["stages"])
    route_sequences = {ptype: tuple(seq) for ptype, seq in contract["type_routes"].items()}
    route_module = load_route_module()
    successors = build_successor_map(contract)
    producing = build_producing_map(route_module)

    skill_files = sorted(SKILLS_ROOT.glob("*/SKILL.md"))
    if not skill_files:
        raise SystemExit(f"no SKILL.md found under {SKILLS_ROOT}")

    violations: list[str] = []
    info_lines: list[str] = []
    info_total = 0
    info_without_constant = 0
    checked_blocks = 0

    for path in skill_files:
        skill = path.parent.name
        rel = path.relative_to(ROOT).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        blocks = checkpoint_blocks(lines)
        if not blocks:
            violations.append(f"{rel}: no CHECKPOINT block found")
            continue

        block_lines: set[int] = set()
        for start, end in blocks:
            block_lines.update(range(start, end))
            checked_blocks += 1
            text = "\n".join(lines[start:end])
            found = set(STAGE_TOKEN_RE.findall(text)) & known_stages

            # (1) no bare "Stage N" inside the hand-off block.
            for offset, line in enumerate(lines[start:end]):
                if BARE_STAGE_RE.search(line):
                    violations.append(
                        f"{rel}:{start + offset + 1}: bare 'Stage N' inside CHECKPOINT block: {line.strip()}"
                    )

            if skill in STAGE_FREE_SKILLS:
                continue

            # (2) the block must name at least one stage constant.
            if not found:
                violations.append(
                    f"{rel}:{start + 1}: CHECKPOINT block names no stage constant: {lines[start].strip()}"
                )
                continue

            # (3) every named stage constant must be legal for this skill.
            allowed = allowed_stages(skill, producing, successors)
            illegal = sorted(found - allowed)
            if illegal:
                violations.append(
                    f"{rel}:{start + 1}: stage constant(s) outside {skill}'s producing/successor set: "
                    f"{illegal}; allowed={sorted(allowed)}"
                )

            # (4) bare step ordinals must be route-qualified and reproducible.
            for match in BARE_STEP_RE.finditer(text):
                ordinal = int(match.group(1) or match.group(2))
                qualified = [ptype for ptype in route_sequences if ptype in text]
                reproduced = any(
                    1 <= ordinal <= len(route_sequences[ptype])
                    and route_sequences[ptype][ordinal - 1] in found
                    for ptype in qualified
                )
                if not reproduced:
                    violations.append(
                        f"{rel}:{start + 1}: bare step ordinal {match.group(0)!r} is not reproducibly "
                        f"route-qualified (use '<ROUTE> 第 N 步' with N a --list-stages ordinal, or drop the ordinal)"
                    )

        # INFO (never red): full-file "Stage N" sweep outside CHECKPOINT blocks.
        for number, line in enumerate(lines):
            if number in block_lines or not BARE_STAGE_RE.search(line):
                continue
            info_total += 1
            if not (set(STAGE_TOKEN_RE.findall(line)) & known_stages):
                info_without_constant += 1
            info_lines.append(f"INFO: {rel}:{number + 1}: {line.strip()}")

    for line in info_lines:
        print(line)
    print(
        f"INFO: {info_total} residual bare 'Stage N' line(s) outside CHECKPOINT blocks "
        f"({info_without_constant} of them name no stage constant) -- tracked by the optional follow-up sweep"
    )

    if violations:
        print(f"FAIL: {len(violations)} CHECKPOINT violation(s):")
        for item in violations:
            print(f"  - {item}")
        return 1

    print(
        f"PASS: {checked_blocks} CHECKPOINT block(s) across {len(skill_files)} SKILL.md files "
        "name stage constants with legal successors; no bare 'Stage N' inside CHECKPOINT blocks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
