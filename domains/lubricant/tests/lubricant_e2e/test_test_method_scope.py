"""Exercise the scope boundary without creating a lab or release artifact."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "test-method"
SCRIPTS = ROOT / "skills" / "test-method-qualification" / "scripts"


def run(script: str, input_path: Path, output_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    arguments = [sys.executable, script, str(input_path)]
    if output_path is not None:
        arguments.append(str(output_path))
    return subprocess.run(arguments, cwd=SCRIPTS, capture_output=True, text=True)


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def main() -> None:
    rejected = run("preflight_test_method.py", FIXTURES / "invalid-synthetic-qualified.json")
    assert rejected.returncode != 0 and "SYNTHETIC evidence_scope cannot form qualification_status QUALIFIED" in rejected.stdout

    pending = FIXTURES / "valid-input.synthetic.json"
    assert run("preflight_test_method.py", pending).returncode == 0
    with tempfile.TemporaryDirectory() as temporary:
        rejected_output = Path(temporary) / "synthetic-qualified.json"
        rejected_build = run("build_test_method_artifact.py", FIXTURES / "invalid-synthetic-qualified.json", rejected_output)
        assert rejected_build.returncode != 0 and not rejected_output.exists()
        output = Path(temporary) / "synthetic-pending.json"
        built = run("build_test_method_artifact.py", pending, output)
        assert built.returncode == 0, built.stdout + built.stderr
        artifact = read(output)
        assert artifact["evidence_scope"] == "SYNTHETIC"
        assert artifact["qualification_status"] == "PENDING" and artifact["decision"] == "HOLD"
        assert run("validate_test_method_artifact.py", output).returncode == 0

        physical = read(pending)
        physical["evidence_scope"] = "PHYSICAL"
        physical["test_method"]["qualification_evidence_ids"] = []
        physical_path = Path(temporary) / "physical-incomplete.json"
        for key in ("project_artifact", "challenge_artifact", "failure_ctq_artifact"):
            physical[key] = str((FIXTURES / physical[key]).resolve())
        write(physical_path, physical)
        rejected_physical = run("preflight_test_method.py", physical_path)
        assert rejected_physical.returncode != 0 and "qualification_evidence_ids" in rejected_physical.stdout
    print("PASS: synthetic qualification is held; simulated physical contract still needs qualification evidence")


if __name__ == "__main__":
    main()
