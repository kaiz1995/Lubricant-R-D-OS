#!/usr/bin/env python3
"""Negative tests for the migrated cross-artifact guards.

The session guard (2026-10-02-1949/work) was negative-tested against four
fault injections; this file ports those tests so the migrated
``scripts/audit_chain.py`` / ``scripts/check_ctq_method_linkage.py`` cannot
decay into validators that always pass:

  1. stage tampering -- an ADVANCED ``project.json.stage`` (the constant is
     ``PROJECT_DEFINED``; advancing it breaks the preflights that hard-require
     it) AND a wrong artifact stage;
  2. role-D removal -- no QUALIFIED method carries role D or P;
  3. project_id divergence;
  4. dangling method reference;
  5. CTQ bare-id unlinking (the original CTQ-005-B defect class);
  6. positive control -- the healthy fixture must pass (exit 0).

Run:  python tests/test_audit_chain_guards.py   (exit 0 = all caught)
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
AUDIT = SCRIPTS / "audit_chain.py"
LINKAGE = SCRIPTS / "check_ctq_method_linkage.py"

PID = "TEST-NP-001"


def charter(stage="PROJECT_DEFINED"):
    return {
        "schema_version": "0.1.0",
        "artifact_type": "project",
        "project_id": PID,
        "stage": stage,
        "status": "ACTIVE",
        "project_type": "new_product",
        "decision": "GO",
    }


def healthy_workspace(root: Path):
    """A minimal workspace that must pass every chain guard."""
    root.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "project.json": charter(),
        "duty.json": {
            "schema_version": "0.1.0", "artifact_type": "duty",
            "project_id": PID, "stage": "DUTY_DEFINED", "decision": "GO",
        },
        "challenge.json": {
            "schema_version": "0.1.0", "artifact_type": "challenge",
            "project_id": PID, "stage": "CHALLENGES_DEFINED",
            "challenge_id": f"{PID}-CHAL-001", "decision": "GO",
        },
        "failure_ctq.json": {
            "schema_version": "0.1.0", "artifact_type": "failure_ctq",
            "project_id": PID, "stage": "FAILURE_CTQ_DEFINED",
            "failure_id": f"{PID}-FAIL-001",
            "challenge_reference": f"{PID}-CHAL-001",
            "ctqs": [
                {"ctq_id": f"{PID}-CTQ-001-A", "test_references": [f"{PID}-TM-001"]},
                {"ctq_id": f"{PID}-CTQ-001-B", "test_references": [f"{PID}-TM-001"]},
            ],
            "test_chain": [f"{PID}-TM-001"],
            "decision": "GO",
        },
        "test_method.json": {
            "schema_version": "0.1.0", "artifact_type": "test_method",
            "project_id": PID, "stage": "TEST_METHODS_QUALIFIED",
            "method_id": f"{PID}-TM-001",
            "target_failure_reference": f"{PID}-FAIL-001",
            "qualification_status": "QUALIFIED",
            "role": ["D", "P"],
            "decision": "GO",
        },
        "design_space.json": {
            "schema_version": "0.1.0", "artifact_type": "design_space",
            "project_id": PID, "stage": "DESIGN_SPACE_DEFINED",
            "design_space_id": f"{PID}-DS-001",
            "qualified_test_method_references": [f"{PID}-TM-001"],
            "ctq_references": [f"{PID}-CTQ-001-A"],
            "decision": "GO",
        },
        "experiment_design.json": {
            "schema_version": "0.1.0", "artifact_type": "experiment_design",
            "project_id": PID, "stage": "EXPERIMENT_DESIGNED",
            "experiment_design_id": f"{PID}-EXP-001",
            "design_space_reference": f"{PID}-DS-001",
            "decision": "GO",
        },
    }
    for name, data in artifacts.items():
        (root / name).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return artifacts


def run_guard(script, workspace, *extra):
    return subprocess.run(
        [sys.executable, str(script), str(workspace), *extra],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def patch(root: Path, name, mutator):
    data = json.loads((root / name).read_text(encoding="utf-8"))
    mutator(data)
    (root / name).write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    failures = []

    def expect_reject(label, proc, needle):
        if proc.returncode == 0:
            failures.append(f"[{label}] fault was NOT caught (exit 0)")
        elif needle and needle not in (proc.stdout + proc.stderr):
            failures.append(f"[{label}] caught, but without expected detail {needle!r}: {proc.stdout}")
        else:
            print(f"  ok   {label}: caught -> "
                  f"{[l for l in proc.stdout.splitlines() if 'FAIL' in l][0][:110]}")

    def expect_pass(label, proc):
        if proc.returncode != 0:
            failures.append(f"[{label}] healthy fixture rejected: {proc.stdout}{proc.stderr}")
        else:
            print(f"  ok   {label}: passes")

    base = Path(tempfile.mkdtemp(prefix="audit_chain_guards_"))
    try:
        # ---- 0. positive control -----------------------------------------
        healthy = base / "healthy"
        healthy_workspace(healthy)
        expect_pass("positive/audit_chain", run_guard(AUDIT, healthy))
        expect_pass("positive/linkage", run_guard(LINKAGE, healthy))

        # ---- 1a. project.json.stage advanced (constant violated) ----------
        root = base / "f1a"
        healthy_workspace(root)
        patch(root, "project.json", lambda d: d.update(stage="DUTY_DEFINED"))
        expect_reject("stage-tamper/charter-advanced", run_guard(AUDIT, root), "PROJECT_DEFINED")

        # ---- 1b. artifact stage tampered ----------------------------------
        root = base / "f1b"
        healthy_workspace(root)
        patch(root, "design_space.json", lambda d: d.update(stage="PROJECT_DEFINED"))
        expect_reject("stage-tamper/artifact", run_guard(AUDIT, root), "DESIGN_SPACE_DEFINED")

        # ---- 2. role D removed ---------------------------------------------
        root = base / "f2"
        healthy_workspace(root)
        patch(root, "test_method.json", lambda d: d.update(role=["A"]))
        expect_reject("role-D-removed", run_guard(AUDIT, root), "role D or P")

        # ---- 3. project_id divergence --------------------------------------
        root = base / "f3"
        healthy_workspace(root)
        patch(root, "experiment_design.json", lambda d: d.update(project_id="OTHER-NP-999"))
        expect_reject("project_id-divergence", run_guard(AUDIT, root), "project_id not uniform")

        # ---- 4. dangling method reference ----------------------------------
        root = base / "f4"
        healthy_workspace(root)
        patch(root, "design_space.json",
              lambda d: d.update(qualified_test_method_references=[f"{PID}-TM-GHOST"]))
        expect_reject("dangling-method-reference", run_guard(AUDIT, root), "unknown method")

        # ---- 5. CTQ bare-id unlinked (CTQ-005-B defect class) --------------
        root = base / "f5"
        healthy_workspace(root)
        def unlink(data):
            for c in data["ctqs"]:
                if c["ctq_id"].endswith("-A"):
                    c["test_references"] = []
            data["test_chain"] = []
        patch(root, "failure_ctq.json", unlink)
        expect_reject("ctq-bare-id-unlinked/audit_chain", run_guard(AUDIT, root), "not linked")
        expect_reject("ctq-bare-id-unlinked/linkage", run_guard(LINKAGE, root), "not linked")

        # ---- 6. no false positive: standards citations in test_references --
        root = base / "f6"
        healthy_workspace(root)
        def add_citation(data):
            data["ctqs"][0]["test_references"].append("ISO 3744:2025 (半自由场声功率级工程测量法)")
        patch(root, "failure_ctq.json", add_citation)
        expect_pass("no-false-positive/citation-refs", run_guard(LINKAGE, root))

        # ---- 7. dangling bare id hidden among citations is still caught ----
        root = base / "f7"
        healthy_workspace(root)
        patch(root, "failure_ctq.json",
              lambda d: d["ctqs"][0]["test_references"].append(f"{PID}-TM-999"))
        expect_reject("dangling-id-among-citations", run_guard(LINKAGE, root), "unknown method")
    finally:
        shutil.rmtree(base, ignore_errors=True)

    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nall fault injections caught; positive controls pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
