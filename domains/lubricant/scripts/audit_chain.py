#!/usr/bin/env python3
"""audit_chain.py -- cross-artifact chain guard for the Lubricant domain pack.

Migrated from the validated session guard (OpenScience session
2026-10-02-1949/work/audit_chain.py) with the session-specific assumptions
removed. The per-artifact schema validators cannot see anything that spans
files; this script folds every such rule into one place:

  1. every stage artifact carries the stage constant its consumers require
     (``project.json.stage`` is the CONSTANT ``PROJECT_DEFINED`` -- it is the
     marker "this is the charter", NOT a progress field. Advancing it breaks
     the preflight scripts that hard-require the constant, so it is reported
     as a violation, never as progress);
  2. ``decision: GO`` wherever a QUALIFIED method is consumed;
  3. one ``project_id`` across the whole chain;
  4. cross-references (challenge / failure / method ids) resolve;
  5. DOE precondition: at least one QUALIFIED method carries role D or P;
  6. every design space references exactly one QUALIFIED method plus CTQs;
  7. CTQ <-> method bare-id linkage (delegated to check_ctq_method_linkage.py).

Negative-tested in tests/test_audit_chain_guards.py: stage tampering (both an
advanced ``project.json.stage`` and a wrong artifact stage), role-D removal,
project_id divergence and a dangling method reference must ALL be caught.

Usage::

    python audit_chain.py <workspace_dir> [args forwarded to check_ctq_method_linkage.py]

Exit 0 = chain intact, exit 1 = violations found. Pure standard library.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Exact canonical name or filename prefix -> (required stage, artifact kind).
# Both the canonical ``<type>.json`` name and the legal suffixed
# ``<type>-<project_id>-<id>.json`` form map to the same stage constant, so a
# first record cannot escape the audit by occupying the canonical name.
KINDS = {
    "project.json": ("PROJECT_DEFINED", "project"),
    "duty.json": ("DUTY_DEFINED", "duty"),
    "challenge.json": ("CHALLENGES_DEFINED", "challenge"),
    "challenge-": ("CHALLENGES_DEFINED", "challenge"),
    "failure_ctq.json": ("FAILURE_CTQ_DEFINED", "failure"),
    "failure_ctq-": ("FAILURE_CTQ_DEFINED", "failure"),
    "test_method.json": ("TEST_METHODS_QUALIFIED", "method"),
    "test_method-": ("TEST_METHODS_QUALIFIED", "method"),
    "design_space.json": ("DESIGN_SPACE_DEFINED", "space"),
    "design_space-": ("DESIGN_SPACE_DEFINED", "space"),
    "experiment_design.json": ("EXPERIMENT_DESIGNED", "design"),
    "experiment_design-": ("EXPERIMENT_DESIGNED", "design"),
    "experiment.json": ("EXPERIMENT_RUNNING", "experiment"),
    "experiment-": ("EXPERIMENT_RUNNING", "experiment"),
    "model.json": ("MODEL_BUILT", "model"),
    "model-": ("MODEL_BUILT", "model"),
    "optimization.json": ("OPTIMIZED", "optimization"),
    "optimization-": ("OPTIMIZED", "optimization"),
    "gate.json": ("VERIFIED", "gate"),
    "gate-": ("VERIFIED", "gate"),
}

# Free-text fields may embed a method id ("...record: HDG-TM-012"). The bare-id
# linkage check is an exact string match downstream, so a prose mention that
# looks like a method id but does not resolve is worth flagging.
METHOD_ID_RE = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)*-TM-\d+")
CHALLENGE_ID_PREFIX_RE = re.compile(r"^[A-Z0-9]+-CHAL")


def load_all(workspace_dir):
    """Parse every root-level ``*.json``; unparseable files become problems."""
    arts, problems = {}, []
    for path in sorted(Path(workspace_dir).glob("*.json")):
        try:
            arts[path.name] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{path.name}: cannot be parsed as JSON ({exc})")
    return arts, problems


def kind_of(name):
    for pref, (stage, kind) in KINDS.items():
        if name == pref or name.startswith(pref):
            return stage, kind
    return None, None


def main(argv):
    if len(argv) < 2:
        print("Usage: python audit_chain.py <workspace_dir> [args for check_ctq_method_linkage.py]")
        return 2
    workspace = Path(argv[1])
    if not workspace.is_dir():
        print(f"FAIL: workspace_dir '{workspace}' is not a directory")
        return 2

    arts, problems = load_all(workspace)
    notes = []
    recognized = {}

    for name, artifact in arts.items():
        stage, kind = kind_of(name)
        if stage is None:
            # Not a stage artifact (input file, scratch json, ...). Naming
            # violations of this kind are check_artifact_naming's job.
            notes.append(f"  skip {name}: not a stage artifact")
            continue
        if not isinstance(artifact, dict):
            problems.append(f"{name}: artifact is not a JSON object")
            continue
        recognized[name] = artifact

        # ---- 1. every artifact carries the stage constant its consumers expect
        # project.json.stage is the CONSTANT PROJECT_DEFINED (charter marker);
        # advancing it breaks the preflights that hard-require the constant.
        if artifact.get("stage") != stage:
            problems.append(
                f"{name}: stage is {artifact.get('stage')!r}, consumers require {stage!r}"
            )

    if not recognized:
        print(f"chain audit over 0 artifacts in {workspace}")
        print("  FAIL no stage artifacts found; is this a workspace root?")
        return 1

    # ---- 2. decision GO where a GO is required ---------------------------
    # PENDING methods legitimately carry HOLD; that is the builder's own output.
    holds = [
        name
        for name, a in recognized.items()
        if a.get("decision") == "HOLD"
    ]
    if holds:
        notes.append(
            f"  ok   {len(holds)} artifacts carry decision HOLD "
            "(expected for PENDING methods): " + ", ".join(sorted(holds))
        )
    for name, a in recognized.items():
        if (
            kind_of(name)[1] == "method"
            and a.get("qualification_status") == "QUALIFIED"
            and a.get("decision") != "GO"
        ):
            problems.append(
                f"{name}: QUALIFIED but decision={a.get('decision')!r}, preflight needs GO"
            )

    # ---- 3. project_id identical across the whole chain -------------------
    pids = {a.get("project_id") for a in recognized.values()}
    if len(pids) != 1 or None in pids:
        problems.append(
            f"project_id not uniform across artifacts: {sorted(str(p) for p in pids)}"
        )
    else:
        notes.append(f"  ok   project_id uniform: {pids.pop()}  (n={len(recognized)})")

    proj = next((a for a in recognized.values() if a.get("artifact_type") == "project"), None)
    if proj is None:
        problems.append("no artifact with artifact_type == 'project' found")
    elif proj.get("status") != "ACTIVE":
        problems.append(f"project.status={proj.get('status')!r}, every preflight requires ACTIVE")

    # ---- 4. cross-references resolve --------------------------------------
    challenge_ids = {a["challenge_id"] for a in recognized.values() if "challenge_id" in a}
    failure_ids = {a["failure_id"] for a in recognized.values() if "failure_id" in a}
    method_ids = {a["method_id"] for a in recognized.values() if "method_id" in a}

    for name, a in recognized.items():
        ref = a.get("challenge_reference")
        if ref and ref not in challenge_ids:
            problems.append(f"{name}: challenge_reference {ref!r} does not exist")
        ref = a.get("challenge")
        if (
            isinstance(ref, str)
            and CHALLENGE_ID_PREFIX_RE.match(ref)
            and ref not in challenge_ids
        ):
            problems.append(f"{name}: challenge {ref!r} does not exist")
        ref = a.get("target_failure_reference")
        if ref and ref not in failure_ids:
            problems.append(f"{name}: target_failure_reference {ref!r} does not exist")
        for mid in METHOD_ID_RE.findall(str(a.get("test_method_artifact", ""))):
            if mid not in method_ids:
                problems.append(f"{name}: test_method_artifact references unknown {mid}")

    # ---- 5. DOE precondition: at least one QUALIFIED D or P method --------
    dp = [
        a["method_id"]
        for a in recognized.values()
        if a.get("qualification_status") == "QUALIFIED"
        and ({"D", "P"} & set(a.get("role", [])))
    ]
    if not dp:
        problems.append(
            "no QUALIFIED method carries role D or P; doe-design preflight would reject any DOE"
        )
    else:
        notes.append(f"  ok   DOE response-capable methods: {', '.join(sorted(dp))}")

    # ---- 6. one CTQ per design space, method matched ----------------------
    for name, a in recognized.items():
        if kind_of(name)[1] != "space":
            continue
        refs = a.get("qualified_test_method_references") or []
        if len(refs) != 1:
            problems.append(f"{name}: expected exactly one qualified method, has {refs}")
        for mid in refs:
            if mid not in method_ids:
                problems.append(f"{name}: references unknown method {mid}")
            else:
                st = next(x for x in recognized.values() if x.get("method_id") == mid)
                if st.get("qualification_status") != "QUALIFIED":
                    problems.append(
                        f"{name}: references {mid} which is {st.get('qualification_status')!r}"
                    )
        if not a.get("ctq_references"):
            problems.append(f"{name}: no ctq_references")

    # ---- 7. CTQ <-> method linkage (delegated) ---------------------------
    linkage = HERE / "check_ctq_method_linkage.py"
    if linkage.is_file():
        proc = subprocess.run(
            [sys.executable, str(linkage), str(workspace), *argv[2:]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            tail = proc.stdout.strip().splitlines() or [proc.stderr.strip()]
            problems.append("CTQ <-> method linkage violated: " + (tail[-1] if tail else ""))
    else:
        notes.append("  skip check_ctq_method_linkage.py not found beside audit_chain.py")

    # ---- report -----------------------------------------------------------
    print(f"chain audit over {len(recognized)} artifacts in {workspace}")
    for line in notes:
        print(line)
    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        for p in problems:
            print(f"  FAIL {p}")
        return 1
    print("\n  all stage / decision / project_id / cross-reference / DOE preconditions hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
