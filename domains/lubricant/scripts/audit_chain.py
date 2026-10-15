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
    "application.json": ("APPLIED", "application"),
    "application-": ("APPLIED", "application"),
    "reference.json": ("REFERENCE_MATERIAL_RESOLVED", "reference"),
    "reference-": ("REFERENCE_MATERIAL_RESOLVED", "reference"),
    # Deliberately NOT in KINDS: bench.json -- contract v1.0.0 merged the former
    # bench-registration + campaign-opening pair into this one record, and
    # its own validator (validate_bench_artifact.py, mapped in
    # validate_workspace.py) already checks its stage constant end to end, so this
    # cross-file walk does not duplicate that check. Same for interface-*.json and
    # external_record*.json: resource objects whose own ``stage`` is the
    # placeholder ``DRAFT`` (their builders write it; the stage they mark lives on
    # the project, not on the record). ``process`` has two legal shapes at two
    # different stages (process-baseline.json at DESIGN_SPACE_DEFINED, process.json
    # at PROCESS_WINDOW_DEFINED / PROCESS_SCALE_VALIDATED), so a single expected
    # constant would be wrong. Those stay out of KINDS deliberately; naming is
    # check_artifact_naming's job.
    "batch.json": ("BATCH_PRODUCED", "batch"),
    "batch-": ("BATCH_PRODUCED", "batch"),
    "screening.json": ("SCREENING_PASSED", "screening"),
    "screening-": ("SCREENING_PASSED", "screening"),
    "variance.json": ("VARIANCE_ASSESSED", "variance"),
    "variance-": ("VARIANCE_ASSESSED", "variance"),
    "bench_test.json": ("BENCH_TESTED", "bench_test"),
    "bench_test-": ("BENCH_TESTED", "bench_test"),
    "next_batch.json": ("NEXT_BATCH_DECIDED", "next_batch"),
    "next_batch-": ("NEXT_BATCH_DECIDED", "next_batch"),
    "knowledge_asset.json": ("KNOWLEDGE_ARCHIVED", "knowledge_asset"),
    "knowledge_asset-": ("KNOWLEDGE_ARCHIVED", "knowledge_asset"),
}

# WP-14 (2026-10-13): the precision-grease route's step-14 optimization artifact
# legally lands at NON_INFERIORITY_PASSED instead of OPTIMIZED
# (schemas/optimization.schema.json enumerates both). One artifact kind's stage
# expectation is therefore dispatched on the charter's project_type, which the
# audit can read because it sees the whole workspace. Every other kind, every
# other project type and a workspace with no readable project artifact keep the
# original constant, so the six oil routes audit byte for byte as before.
GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"
GREASE_STAGE_BY_KIND = {"optimization": "NON_INFERIORITY_PASSED"}


def expected_stage(stage, kind, project_type):
    """Stage constant an artifact of ``kind`` must carry in this workspace."""
    if project_type == GREASE_PROJECT_TYPE and kind in GREASE_STAGE_BY_KIND:
        return GREASE_STAGE_BY_KIND[kind]
    return stage


# Free-text fields may embed a method id ("...record: HDG-TM-012"). The bare-id
# linkage check is an exact string match downstream, so a prose mention that
# looks like a method id but does not resolve is worth flagging.
METHOD_ID_RE = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)*-TM-\d+")
CHALLENGE_ID_PREFIX_RE = re.compile(r"^[A-Z0-9]+-CHAL")
# The recorded CHALLENGES_DEFINED gap of a route that carries no challenge step. The
# stage sits on no type_route, so the grease route records the Challenge Map link as
# ``UNROUTED:<project_id>`` instead of fabricating an out-of-route artifact: that is a
# NOTE, not a dangling reference. Recognised by prefix and required to name the
# workspace's own project_id, so the marker can never point at another project's chain.
UNROUTED_PREFIX = "UNROUTED:"


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

    # WP-14: the stage expectation for one kind is dispatched on the charter's
    # project_type. The charter is the canonical project.json; without one -- or
    # without a readable project_type -- every expectation keeps its original
    # constant.
    #
    # The canonical name is what decides, not "whichever file sorts first": an
    # extra non-canonical json declaring artifact_type "project" used to win the
    # lookup by filename order and silently flip this dispatch (and with it the
    # route-dependent stage expectations). Such a file is not a stage artifact,
    # so nothing else here would have noticed it. Two charters is an ambiguous
    # workspace and is reported rather than resolved by luck.
    charters = [
        (name, artifact)
        for name, artifact in arts.items()
        if isinstance(artifact, dict) and artifact.get("artifact_type") == "project"
    ]
    canonical = [pair for pair in charters if pair[0] == "project.json"]
    if len(charters) > 1:
        problems.append(
            "more than one artifact declares artifact_type 'project' "
            f"({', '.join(name for name, _ in charters)}); the charter must be project.json"
        )
    project_type = (canonical[0][1] if canonical else (charters[0][1] if charters else {})).get("project_type")

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
        required = expected_stage(stage, kind, project_type)
        if artifact.get("stage") != required:
            problems.append(
                f"{name}: stage is {artifact.get('stage')!r}, consumers require {required!r}"
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
    chain_project_id = pids.pop() if len(pids) == 1 and None not in pids else None
    if chain_project_id is None:
        problems.append(
            f"project_id not uniform across artifacts: {sorted(str(p) for p in pids)}"
        )
    else:
        notes.append(f"  ok   project_id uniform: {chain_project_id}  (n={len(recognized)})")

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
        if isinstance(ref, str) and ref.startswith(UNROUTED_PREFIX):
            # The route's recorded CHALLENGES_DEFINED gap. It is a NOTE rather than a
            # problem only when it names the workspace's own project_id: an UNROUTED
            # marker pointing anywhere else is still a dangling reference.
            if ref == f"{UNROUTED_PREFIX}{chain_project_id}":
                notes.append(
                    f"  note {name}: challenge_reference {ref} records the CHALLENGES_DEFINED gap "
                    "of a route that carries no challenge step"
                )
            else:
                problems.append(
                    f"{name}: challenge_reference {ref!r} records an UNROUTED gap for a project "
                    f"other than this workspace's own ({chain_project_id!r})"
                )
        elif ref and ref not in challenge_ids:
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
