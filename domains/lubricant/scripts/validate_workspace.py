#!/usr/bin/env python3
"""validate_workspace.py -- unified workspace validation entry for the pack.

Migrated from the validated session driver (OpenScience session
2026-10-02-1949/work/validate_all.py): the session hardcoded the deployed
skill base under AppData and the workspace as the script's grandparent; both
are resolved from this script's location now. The artifact naming contract
check (check_artifact_naming.py) runs first -- it is the entry the gate-review
preflight semantics rely on, so a mangled name fails here before anything else.

Checks, in order:
  1. canonical-name contract + ``project.json.stage`` constant
     (scripts/check_artifact_naming.py);
  2. per-artifact schema validators (skills/*/scripts/validate_*.py), matched
     by exact canonical name or filename prefix;
  3. cross-artifact chain audit incl. CTQ<->method bare-id linkage
     (scripts/audit_chain.py, which delegates to check_ctq_method_linkage.py).

Usage::

    python validate_workspace.py <workspace_dir>

Exit 0 = all checks hold; exit 1 = at least one failure. Pure standard library.
"""

import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
SKILLS = PACK / "skills"

VALIDATORS = [
    ("^project\\.json$", "project-definition/scripts/validate_project_artifact.py"),
    ("^duty\\.json$", "duty-definition/scripts/validate_duty_artifact.py"),
    ("^challenge\\.json$", "duty-challenge-analysis/scripts/validate_duty_challenge_artifact.py"),
    ("^challenge-", "duty-challenge-analysis/scripts/validate_duty_challenge_artifact.py"),
    ("^failure_ctq\\.json$", "failure-ctq-analysis/scripts/validate_failure_ctq_artifact.py"),
    ("^failure_ctq-", "failure-ctq-analysis/scripts/validate_failure_ctq_artifact.py"),
    ("^test_method\\.json$", "test-method-qualification/scripts/validate_test_method_artifact.py"),
    ("^test_method-", "test-method-qualification/scripts/validate_test_method_artifact.py"),
    ("^design_space\\.json$", "formulation-design/scripts/validate_design_space_artifact.py"),
    ("^design_space-", "formulation-design/scripts/validate_design_space_artifact.py"),
    ("^experiment_design\\.json$", "doe-design/scripts/validate_experiment_design_artifact.py"),
    ("^experiment_design-", "doe-design/scripts/validate_experiment_design_artifact.py"),
]


def validator_for(name):
    for pattern, rel in VALIDATORS:
        if re.search(pattern, name):
            return rel
    return None


def run(script, *args):
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def naming_check(workspace) -> list[str]:
    sys.path.insert(0, str(HERE))
    try:
        import check_artifact_naming
    except ImportError as exc:
        return [f"check_artifact_naming.py cannot be imported: {exc}"]
    if not (Path(workspace) / "project.json").is_file():
        return ["project.json: missing (mandatory charter; naming check aborted)"]
    try:
        _, violations = check_artifact_naming.check_workspace(str(workspace))
    except OSError as exc:
        return [f"naming check crashed: {exc}"]
    return violations


def main(argv):
    if len(argv) != 2:
        print("Usage: python validate_workspace.py <workspace_dir>")
        return 2
    workspace = Path(argv[1])
    if not workspace.is_dir():
        print(f"FAIL: workspace_dir '{workspace}' is not a directory")
        return 2

    failures = []

    # ---- 1. naming contract ------------------------------------------------
    naming = naming_check(workspace)
    if naming:
        print("naming contract: FAIL")
        for v in naming:
            print(f"  {v}")
        failures.append("artifact naming contract violated (see check_artifact_naming.py)")
    else:
        print("naming contract: PASS")

    # ---- 2. per-artifact schema validators ---------------------------------
    rows, unchecked = [], []
    for path in sorted(workspace.glob("*.json")):
        rel = validator_for(path.name)
        if rel is None:
            unchecked.append(path.name)
            rows.append((path.name, "NO-VALIDATOR", ""))
            continue
        script = SKILLS / rel
        if not script.is_file():
            failures.append(f"{path.name}: validator script missing -> {script}")
            rows.append((path.name, "SCRIPT-MISSING", str(script)))
            continue
        proc = run(script, str(path))
        out = (proc.stdout + proc.stderr).strip()
        ok = proc.returncode == 0 and "PASS" in out
        # A "Usage:" reply means the argument never reached the validator.
        if "Usage:" in out:
            ok = False
        rows.append((path.name, "PASS" if ok else "FAIL", out.splitlines()[-1] if out else ""))
        if not ok:
            failures.append(f"{path.name}: {out}")

    width = max((len(r[0]) for r in rows), default=0)
    for name, status, detail in rows:
        print(f"{name:<{width}}  {status:<13} {detail[:60]}")

    print()
    print(
        f"artifacts={len(rows)}  pass={sum(1 for r in rows if r[1] == 'PASS')}  "
        f"unchecked={len(unchecked)}  fail={sum(1 for r in rows if r[1] == 'FAIL')}"
    )
    if unchecked:
        print(f"note: {len(unchecked)} json files have no validator mapped in this pack")

    # ---- 3. cross-artifact chain audit (includes CTQ <-> method linkage) ---
    audit = HERE / "audit_chain.py"
    if audit.is_file():
        proc = run(audit, str(workspace))
        print(proc.stdout.strip())
        if proc.returncode != 0:
            failures.append("cross-artifact chain audit failed; see audit_chain.py output above")
    else:
        failures.append(f"audit_chain.py missing -> {audit}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nall mapped artifacts conform to their stage contract, and cross-file linkage holds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
