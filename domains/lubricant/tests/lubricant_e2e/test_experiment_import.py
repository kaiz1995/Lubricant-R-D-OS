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


def non_doe_input(workspace: Path, evidence_class: str, **record_overrides) -> dict:
    """A WP-07 non-DOE import: same upstream chain, no DOE output at all."""
    data = imported_input(workspace)
    del data["doe_output_artifact"], data["doe_output_digest"]
    run = data["experiment"]["runs"][0]
    del run["doe_point_reference"]
    data["experiment"].update({"evidence_class": evidence_class, **record_overrides})
    return data


def statistical_input(workspace: Path, experiment_artifact: Path) -> dict:
    """A statistical-analysis request whose experiment artifact is supplied."""
    input_path = FIXTURES / "statistical-analysis" / "valid-input.synthetic.json"
    data = read(input_path)
    source = FIXTURES / "statistical-analysis"
    artifacts = workspace / "stat-artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    for key in ("project_artifact", "challenge_artifact", "failure_ctq_artifact", "test_method_artifact", "design_space_artifact", "experiment_design_artifact"):
        target = artifacts / Path(data[key]).name
        shutil.copyfile(source / Path(data[key]).name, target)
        value = read(target)
        if key == "test_method_artifact":
            value.update({"evidence_scope": "PHYSICAL", "decision": "GO", "qualification_status": "QUALIFIED"})
        elif key == "experiment_design_artifact":
            value.update({"evidence_scope": "PHYSICAL", "decision": "GO"})
        else:
            value.update({"decision": "GO"})
        value["evidence"][0].update({"statement": MARKER, "source": MARKER})
        write(target, value)
        data[key] = str(target)
    data["experiment_artifact"] = str(experiment_artifact)
    return data


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

        # --- WP-07: non-DOE evidence classes can be imported (fail-closed) ------
        statistical_scripts = ROOT / "skills" / "statistical-analysis" / "scripts"

        def run_preflight(script: Path, path: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.run([sys.executable, "-B", str(script), str(path)], cwd=script.parent, capture_output=True, text=True)

        # 1. APPLICATION_FIELD positive: no DOE output, no DOE points; method and
        #    execution provenance stay mandatory; the artifact carries the class.
        application_field = non_doe_input(workspace / "app-field", "APPLICATION_FIELD")
        path, output = workspace / "app-field.json", workspace / "app-field-experiment.json"
        write(path, application_field)
        preflight = run("preflight_experiment_import.py", path)
        assert preflight.returncode == 0, preflight.stdout + preflight.stderr
        built = run("build_experiment_artifact.py", path, output)
        assert built.returncode == 0, built.stdout + built.stderr
        artifact = read(output)
        assert artifact["evidence_class"] == "APPLICATION_FIELD" and "doe_output_reference" not in artifact, sorted(artifact)
        assert artifact["runs"][0].get("doe_point_reference") is None
        assert run("validate_experiment_artifact.py", output).returncode == 0

        # 2. CONFIRMATORY_NON_DOE positive with a bench anchor.
        confirmatory = non_doe_input(workspace / "confirm", "CONFIRMATORY_NON_DOE", bench_reference="BENCH-SZ-01")
        path, output = workspace / "confirm.json", workspace / "confirm-experiment.json"
        write(path, confirmatory)
        assert run("preflight_experiment_import.py", path).returncode == 0
        assert run("build_experiment_artifact.py", path, output).returncode == 0
        assert read(output)["bench_reference"] == "BENCH-SZ-01"

        # 3. A CONFIRMATORY_NON_DOE record without an anchor is rejected.
        no_anchor = non_doe_input(workspace / "no-anchor", "CONFIRMATORY_NON_DOE")
        path = workspace / "no-anchor.json"; write(path, no_anchor)
        result = run("build_experiment_artifact.py", path, workspace / "no-anchor-output.json")
        assert result.returncode != 0 and "must cite an application_reference or bench_reference anchor" in result.stdout, result.stdout

        # 4. A non-DOE import that still hands over a DOE output is rejected.
        stray_doe = non_doe_input(workspace / "stray-doe", "APPLICATION_FIELD")
        doe_path = workspace / "stray-doe" / "doe-output.json"
        stray_doe.update({"doe_output_artifact": str(doe_path), "doe_output_digest": hashlib.sha256(doe_path.read_bytes()).hexdigest()})
        path = workspace / "stray-doe.json"; write(path, stray_doe)
        result = run("build_experiment_artifact.py", path, workspace / "stray-doe-output.json")
        assert result.returncode != 0 and "do not consume a DOE output" in result.stdout, result.stdout

        # 5. A non-DOE run that carries a DOE point is rejected (no silent mixing).
        stray_point = non_doe_input(workspace / "stray-point", "APPLICATION_FIELD")
        stray_point["experiment"]["runs"][0]["doe_point_reference"] = {"run_index": 1}
        path = workspace / "stray-point.json"; write(path, stray_point)
        result = run("build_experiment_artifact.py", path, workspace / "stray-point-output.json")
        assert result.returncode != 0 and "only DOE_POINT records consume DOE points" in result.stdout, result.stdout

        # 6. An unknown evidence_class is rejected, never defaulted.
        unknown_class = non_doe_input(workspace / "bad-class", "FIELD_NOTE")
        path = workspace / "bad-class.json"; write(path, unknown_class)
        result = run("build_experiment_artifact.py", path, workspace / "bad-class-output.json")
        assert result.returncode != 0 and "evidence_class must be one of" in result.stdout, result.stdout

        # 7. The modeling entry stays DOE-only: an APPLICATION_FIELD experiment
        #    artifact is explicitly excluded, naming the record and the reason.
        stat_path = workspace / "stat-app-field.json"
        write(stat_path, statistical_input(workspace / "stat", workspace / "app-field-experiment.json"))
        result = run_preflight(statistical_scripts / "preflight_statistical_analysis.py", stat_path)
        assert result.returncode != 0, result.stdout + result.stderr
        assert "EXP-PHYSICAL-CONTRACT-001" in result.stdout and "excluded from the modeling entry" in result.stdout, result.stdout

        # 8. The same request with the default (no explicit evidence_class ->
        #    DOE_POINT) experiment artifact is NOT blocked by the exclusion rule.
        stat_path = workspace / "stat-doe-point.json"
        write(stat_path, statistical_input(workspace / "stat-doe", workspace / "experiment.json"))
        result = run_preflight(statistical_scripts / "preflight_statistical_analysis.py", stat_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "excluded from the modeling entry" not in result.stdout, result.stdout
    print("PASS: PHYSICAL experiment import provenance contract and HOLD boundaries")


if __name__ == "__main__": main()
