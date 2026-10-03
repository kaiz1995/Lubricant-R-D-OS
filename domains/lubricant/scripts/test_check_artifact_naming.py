#!/usr/bin/env python3
"""Self-test for check_artifact_naming.py.

Pure standard library (no pytest -- this repo does not ship it).
Run directly::

    python test_check_artifact_naming.py

Exit code 0 = all cases pass, 1 = at least one case failed.
Each case builds an isolated tempfile.TemporaryDirectory() which is cleaned
up automatically; no temp files are left in the repository.

Cases:
    T1  Compliant workspace (project/duty/challenge canonical + suffix) -> exit 0
    T2  Missing canonical name but legal suffixed name present -> exit 0
        (the suffix name is legal; the script must NOT flag it as a violation)
    T3  Mangled name (challenge_x.json) -> exit 1
    T4  experiment / experiment_design prefix disambiguation:
        experiment_design-P-001.json must NOT be counted as an `experiment` record
    T5  project.json.stage advanced away from the constant -> exit 1 with reason
    T6  project.json missing -> exit 1
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(HERE, "check_artifact_naming.py")


def run_checker(workspace_dir):
    proc = subprocess.run(
        [sys.executable, CHECKER, workspace_dir],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.returncode, proc.stdout + proc.stderr


def write_json(workspace_dir, filename, payload):
    with open(os.path.join(workspace_dir, filename), "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


def project_payload(stage="PROJECT_DEFINED"):
    return {"project_id": "P-001", "stage": stage, "decision": "GO"}


def stats_line(output, stage_type):
    """Extract the per-type statistics line, e.g. 'experiment: canonical=no, records=0'."""
    for line in output.splitlines():
        if line.startswith(stage_type + ":"):
            return line
    return None


failures = []


def check(name, condition, detail=""):
    if condition:
        print("PASS  {} {}".format(name, detail))
    else:
        print("FAIL  {} {}".format(name, detail))
        failures.append(name)


def case_t1():
    with tempfile.TemporaryDirectory() as ws:
        write_json(ws, "project.json", project_payload())
        write_json(ws, "duty.json", {"duty_id": "DUTY-P-001"})
        write_json(ws, "challenge.json", {"challenge_id": "CHG-001"})
        write_json(ws, "challenge-P-002.json", {"challenge_id": "CHG-002"})
        code, out = run_checker(ws)
        check("T1", code == 0, "compliant workspace exits 0 (got {})\n{}".format(code, out))


def case_t2():
    # No challenge.json, only the legal suffixed name. A minimal project.json
    # is included so that the only variable under test is the challenge naming.
    with tempfile.TemporaryDirectory() as ws:
        write_json(ws, "project.json", project_payload())
        write_json(ws, "challenge-P-001.json", {"challenge_id": "CHG-001"})
        code, out = run_checker(ws)
        check(
            "T2",
            code == 0,
            "suffixed name without canonical name is legal, exits 0 (got {})\n{}".format(code, out),
        )
        line = stats_line(out, "challenge")
        check(
            "T2b",
            line is not None and "records=1" in line and "canonical=no" in line,
            "challenge counted as 1 record, canonical=no -> {!r}".format(line),
        )


def case_t3():
    with tempfile.TemporaryDirectory() as ws:
        write_json(ws, "project.json", project_payload())
        write_json(ws, "challenge_x.json", {"challenge_id": "CHG-001"})
        code, out = run_checker(ws)
        check("T3", code == 1, "mangled name challenge_x.json exits 1 (got {})".format(code))
        check("T3b", "challenge_x.json" in out, "output names the offending file")


def case_t4():
    # Only experiment_design-P-001.json. project.json is absent, so the script
    # exits 1 for that reason -- the assertions below target the statistics:
    # the file must be counted under experiment_design, NOT experiment.
    with tempfile.TemporaryDirectory() as ws:
        write_json(ws, "experiment_design-P-001.json", {"experiment_design_id": "ED-001"})
        code, out = run_checker(ws)
        exp_line = stats_line(out, "experiment")
        ed_line = stats_line(out, "experiment_design")
        check(
            "T4",
            exp_line is not None and "records=0" in exp_line,
            "experiment records must be 0 -> {!r}".format(exp_line),
        )
        check(
            "T4b",
            ed_line is not None and "records=1" in ed_line,
            "experiment_design records must be 1 -> {!r}".format(ed_line),
        )
        check(
            "T4c",
            code == 1 and "project.json" in out and "mangled" not in out,
            "exit 1 comes from missing project.json, NOT from a naming violation (got {})".format(code),
        )


def case_t5():
    with tempfile.TemporaryDirectory() as ws:
        write_json(ws, "project.json", project_payload(stage="EXPERIMENT_DESIGNED"))
        code, out = run_checker(ws)
        check("T5", code == 1, "advanced stage field exits 1 (got {})".format(code))
        check(
            "T5b",
            "PROJECT_DEFINED" in out and "constant" in out,
            "output explains the stage-is-a-constant invariant",
        )


def case_t6():
    with tempfile.TemporaryDirectory() as ws:
        code, out = run_checker(ws)
        check("T6", code == 1, "missing project.json exits 1 (got {})".format(code))
        check("T6b", "project.json" in out, "output names the missing file")


def main():
    case_t1()
    case_t2()
    case_t3()
    case_t4()
    case_t5()
    case_t6()
    if failures:
        print("SELFTEST FAIL: {} case(s) failed: {}".format(len(failures), ", ".join(failures)))
        return 1
    print("SELFTEST PASS: 6 cases (T1-T6) all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
