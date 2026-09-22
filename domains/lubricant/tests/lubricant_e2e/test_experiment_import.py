"""Exercise PHYSICAL experiment import with temporary contract-test inputs only."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
SCRIPTS = ROOT / "skills" / "experiment-import" / "scripts"
MARKER = "SIMULATED_PHYSICAL_CONTRACT_TEST_NOT_EVIDENCE"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: str, input_path: Path, output_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-B", script, str(input_path)]
    if output_path is not None: command.append(str(output_path))
    return subprocess.run(command, cwd=SCRIPTS, capture_output=True, text=True)


def imported_input(workspace: Path, design_scope: str = "PHYSICAL") -> dict:
    source, artifacts = FIXTURES / "statistical-analysis", workspace / "artifacts"
    artifacts.mkdir(parents=True)
    names = {"project_artifact": "project-active.json", "challenge_artifact": "challenge-defined.json", "failure_ctq_artifact": "failure-ctq-defined.json", "test_method_artifact": "test-method-qualified.json", "design_space_artifact": "design-space-defined.json", "experiment_design_artifact": "experiment-design.json"}
    result: dict[str, str] = {}
    for key, name in names.items():
        target = artifacts / name; shutil.copyfile(source / name, target); result[key] = str(target)
    method = read(artifacts / names["test_method_artifact"]); method.update({"evidence_scope": "PHYSICAL", "decision": "GO", "qualification_status": "QUALIFIED"}); method["evidence"][0].update({"statement": MARKER, "source": MARKER}); write(artifacts / names["test_method_artifact"], method)
    design = read(artifacts / names["experiment_design_artifact"]); design.update({"evidence_scope": design_scope, "decision": "GO"}); design["evidence"][0].update({"statement": MARKER, "source": MARKER}); write(artifacts / names["experiment_design_artifact"], design)
    doe_path = workspace / "doe-output.json"; shutil.copyfile(FIXTURES / "compute" / "doe-gold-output.json", doe_path)
    result.update({"doe_output_artifact": str(doe_path), "doe_output_digest": hashlib.sha256(doe_path.read_bytes()).hexdigest()})
    result["experiment"] = {
        "experiment_id": "EXP-PHYSICAL-CONTRACT-001",
        "evidence": [{"evidence_id": "E-IMPORT-001", "statement": MARKER, "source": MARKER, "status": "OBSERVED"}],
        "runs": [{
            "run_id": "RUN-PHYSICAL-CONTRACT-001", "material_batch": "SIMULATED-BATCH-001", "formula_reference": "SIMULATED-FORMULA-001", "formula_version": "SIMULATED-FORMULA-V1",
            "doe_point_reference": {"run_index": 1},
            "execution_provenance": {"executed_at": "2026-08-25T09:30:00+08:00", "operator_reference": MARKER, "instrument_reference": MARKER, "calibration_reference": MARKER, "raw_record_reference": MARKER},
            "response_measurements": [{"ctq_reference": "CTQ-DOE-001", "method_reference": {"method_id": "TM-DOE-001", "qualification_reference": MARKER}, "measurement": {"value": 42.5, "unit": "min", "source": MARKER, "method_version": "SIMULATED-METHOD-V1", "material_batch": "SIMULATED-BATCH-001", "formula_version": "SIMULATED-FORMULA-V1"}}]
        }]
    }
    return result


def expect_hold(workspace: Path, name: str, data: dict) -> None:
    path, output = workspace / f"{name}.json", workspace / f"{name}-output.json"
    write(path, data); result = run("build_experiment_artifact.py", path, output)
    assert result.returncode != 0 and "HOLD:" in result.stdout and not output.exists(), result.stdout + result.stderr


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        good = imported_input(workspace)
        input_path, output_path = workspace / "good.json", workspace / "experiment.json"; write(input_path, good)
        assert run("preflight_experiment_import.py", input_path).returncode == 0
        built = run("build_experiment_artifact.py", input_path, output_path)
        assert built.returncode == 0, built.stdout + built.stderr
        artifact = read(output_path)
        assert artifact["evidence_scope"] == "PHYSICAL" and artifact["doe_output_reference"]["output_digest"] == good["doe_output_digest"]
        assert run("validate_experiment_artifact.py", output_path).returncode == 0

        missing = imported_input(workspace / "missing"); del missing["experiment"]["runs"][0]["execution_provenance"]["raw_record_reference"]; expect_hold(workspace, "missing", missing)
        bad_digest = imported_input(workspace / "digest"); bad_digest["doe_output_digest"] = "0" * 64; expect_hold(workspace, "digest", bad_digest)
        bad_index = imported_input(workspace / "index"); bad_index["experiment"]["runs"][0]["doe_point_reference"]["run_index"] = 999; expect_hold(workspace, "index", bad_index)
        bad_method = imported_input(workspace / "method"); bad_method["experiment"]["runs"][0]["response_measurements"][0]["method_reference"]["method_id"] = "TM-WRONG"; expect_hold(workspace, "method", bad_method)
        bad_chain = imported_input(workspace / "chain"); design_path = Path(bad_chain["experiment_design_artifact"]); design = read(design_path); design["design_space_reference"] = "DS-WRONG"; write(design_path, design); expect_hold(workspace, "chain", bad_chain)
        synthetic = imported_input(workspace / "synthetic", "SYNTHETIC"); expect_hold(workspace, "synthetic", synthetic)
    print("PASS: PHYSICAL experiment import provenance contract and HOLD boundaries")


if __name__ == "__main__": main()
