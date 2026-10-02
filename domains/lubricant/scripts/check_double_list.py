#!/usr/bin/env python3
"""Cross-check the installer SKILLS registry against each skill's preflight.

Plan §9.5 leftover item. The load-bearing invariant is one-directional and
fail-closed: every ``*.schema.json`` referenced by a skill's Python scripts
(the schemas a deployed preflight/validator would actually try to load) must
be present in that skill's ``SKILLS`` deployment list from
``scripts/install_domain_skill.py``. A schema that is loaded but not shipped
means the deployed bundle crashes at runtime.

The reverse direction (shipped but never referenced by scripts) is reported
as information only: deployed authority schemas are also consumed through
SKILL.md prose and references/, so "shipped ⊇ referenced" — not set
equality — is the contract. Drifts of this kind are listed for review.

Run standalone from the pack root::

    python scripts/check_double_list.py    # exit 0 = consistent

or programmatically via :func:`run_check` (wired into release_preflight).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.install_domain_skill import SKILLS  # noqa: E402

# Router-only meta-skill: intentionally has no artifact preflight; its
# deployment list feeds the SKILL.md contract, not a Python loader.
NO_PREFLIGHT_SKILLS = frozenset({"lubricant-rd-agent"})

_SCHEMA_NAME = re.compile(r"^[a-z][a-z0-9_]*\.schema\.json$")


def referenced_schemas(skill_dir: Path) -> set[str]:
    """Collect every ``*.schema.json`` string literal in the skill's scripts."""
    refs: set[str] = set()
    scripts = skill_dir / "scripts"
    if not scripts.is_dir():
        return refs
    for path in sorted(scripts.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _SCHEMA_NAME.match(node.value):
                refs.add(node.value)
    return refs


def run_check(pack_root: Path = ROOT) -> dict:
    """Compare SKILLS against script-level schema references. Never raises."""
    problems: list[dict] = []
    notes: list[dict] = []
    checked = 0
    for skill, installed in sorted(SKILLS.items()):
        skill_dir = pack_root / "skills" / skill
        refs = referenced_schemas(skill_dir)
        entry: dict = {"skill": skill, "installed": len(installed), "referenced": len(refs)}
        missing = sorted(refs - set(installed))          # loaded but not shipped: breaks at runtime
        unref = sorted(set(installed) - refs)            # shipped but not loaded by scripts: info only
        if missing:
            entry["status"] = "FAIL"
            entry["detail"] = f"loaded but NOT deployed: {missing}"
            problems.append(entry)
            continue
        if unref:
            entry["status"] = "INFO"
            entry["detail"] = f"deployed but not referenced by scripts (SKILL.md/references consumers): {unref}"
            notes.append(entry)
        if not (skill_dir / "scripts").glob("preflight_*.py") and skill not in NO_PREFLIGHT_SKILLS:
            entry = {**entry, "status": "FAIL", "detail": "no preflight_*.py under scripts/"}
            problems.append(entry)
            continue
        if not missing:
            checked += 1
    return {
        "check": "double_list",
        "skills_total": len(SKILLS),
        "skills_consistent": checked,
        "status": "PASS" if not problems else "FAIL",
        "problems": problems,
        "notes": notes,
    }


def main() -> int:
    report = run_check()
    print(f"double-list check: {report['status']} "
          f"(consistent={report['skills_consistent']}/{report['skills_total']})")
    for problem in report["problems"]:
        print(f"  DRIFT  {problem['skill']}: {problem['detail']}")
    for note in report["notes"]:
        print(f"  INFO   {note['skill']}: {note['detail']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
