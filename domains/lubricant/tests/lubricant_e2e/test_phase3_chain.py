"""Smoke the fixed WGO-DOE-001 chain through the three Phase 3 Skills."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
PROJECT_ID = "WGO-DOE-001"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: Path, *arguments: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-B", script.name, *map(str, arguments)],
        cwd=script.parent,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{script.name}\n{result.stdout}{result.stderr}"


def assert_artifact(path: Path, artifact_type: str, stage: str) -> dict:
    artifact = read_json(path)
    assert artifact["artifact_type"] == artifact_type
    assert artifact["project_id"] == PROJECT_ID
    assert artifact["stage"] == stage
    return artifact


def rewrite_upstream(input_value: dict, paths: dict[str, Path]) -> None:
    for key, path in paths.items():
        input_value[key] = str(path)


PROCESS_STEPS = [
    ("P-SAP-TEMP", "saponification temperature", 90, 110, "degC", "SAPONIFICATION"),
    ("P-DEH-TEMP", "dehydration temperature", 100, 130, "degC", "DEHYDRATION"),
    ("P-PHI-TEMP", "phase inversion temperature", 150, 180, "degC", "PHASE_INVERSION"),
    ("P-COOL-RATE", "cooling rate", 1, 5, "degC/min", "DILUTION_COOLING"),
    ("P-MIL-GAP", "mill gap", 0.05, 0.3, "mm", "MILLING"),
    ("P-HOM-PRES", "homogenization pressure", 5, 20, "MPa", "HOMOGENIZATION"),
    ("P-VAC-PRES", "vacuum pressure", 1, 10, "kPa", "VACUUM_DEAERATION"),
    ("P-FILL-TEMP", "filling temperature", 70, 90, "degC", "FILLING"),
]
SIMULATED = "SIMULATED_PHYSICAL_CONTRACT_TEST_NOT_EVIDENCE"


def process_input(design_space_path: Path) -> dict:
    """The DESIGN_SPACE_DEFINED process record for the WGO-DOE-001 chain."""
    steps = [
        {
            "step_id": f"ST-{index + 1:03d}", "step_type": step_type,
            "parameters": [{
                "parameter_id": parameter_id, "parameter_name": name,
                "lower_bound": lower, "upper_bound": upper, "unit": unit,
                "source": SIMULATED, "evidence_id": f"EV-PROC-{index + 1:03d}", "status": "ASSUMED",
            }],
        }
        for index, (parameter_id, name, lower, upper, unit, step_type) in enumerate(PROCESS_STEPS)
    ]
    return {
        "design_space_artifact": str(design_space_path),
        "process": {
            "process_id": "PROC-WGO-DOE-001",
            "project_reference": PROJECT_ID,
            "process_step": steps,
            "batch_scale": {
                "scale_class": "PILOT",
                "batch_size": {
                    "value": 50, "unit": "kg", "source": SIMULATED, "method_version": "scale-v1",
                    "material_batch": "BATCH-SYN-001", "formula_version": "v0.1",
                },
            },
            "amplification_factor": 20.0,
            "process_window": {"window_id": "PW-WGO-DOE-001", "basis": f"{SIMULATED}: pilot window", "validated": False},
            "control_points": [{
                "control_point_id": "CP-001", "parameter_id": "P-PHI-TEMP", "control_type": "IN_PROCESS",
                "criterion": "Hold phase inversion within the supplied window",
                "source": SIMULATED, "evidence_id": "EV-PROC-003",
            }],
            "cpk": {"value": 1.33, "ctq_reference": "CTQ-001", "sample_size": 30},
            "material_batch_reference": "BATCH-SYN-001",
            "factor_role": "SUB_PLOT",
            "evidence_scope": "PHYSICAL",
            "evidence": [{
                "evidence_id": "EV-PROC-001", "statement": f"{SIMULATED}: pilot process bounds",
                "source": SIMULATED, "status": "OBSERVED",
            }],
        },
    }


def scale_up_input(process_path: Path, optimization_path: Path, optimization_id: str) -> dict:
    """The pilot-to-production window fixing input for the WGO-DOE-001 chain."""
    return {
        "process_artifact": str(process_path),
        "optimization_artifact": str(optimization_path),
        "scale_up": {
            "window_id": "PW-WGO-DOE-001-PROD",
            "basis": f"{SIMULATED}: pilot-to-production amplification basis",
            "amplification_factor": 200.0,
            "batch_scale": {
                "scale_class": "PRODUCTION",
                "batch_size": {
                    "value": 500, "unit": "kg", "source": SIMULATED, "method_version": "scale-v2",
                    "material_batch": "BATCH-PROD-001", "formula_version": "v0.2",
                },
            },
            "evidence_scope": "PHYSICAL",
            "evidence": [{
                "evidence_id": "EV-SCALE-001",
                "statement": f"{SIMULATED}: amplification run reproduced the window at production scale.",
                "source": f"{SIMULATED} {optimization_id} + amplification run record AR-001",
                "status": "OBSERVED",
            }],
        },
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        inputs, artifacts = workspace / "inputs", workspace / "artifacts"
        inputs.mkdir()
        artifacts.mkdir()

        # Reuse the existing WGO-DOE-001 artifacts through EXPERIMENT_RUNNING.
        source = FIXTURES / "statistical-analysis"
        upstream_files = {
            "project_artifact": ("project-active.json", "project.json", "project", "PROJECT_DEFINED"),
            "challenge_artifact": ("challenge-defined.json", "challenge.json", "challenge", "CHALLENGES_DEFINED"),
            "failure_ctq_artifact": ("failure-ctq-defined.json", "failure-ctq.json", "failure_ctq", "FAILURE_CTQ_DEFINED"),
            "test_method_artifact": ("test-method-qualified.json", "test-method.json", "test_method", "TEST_METHODS_QUALIFIED"),
            "design_space_artifact": ("design-space-defined.json", "design-space.json", "design_space", "DESIGN_SPACE_DEFINED"),
            "experiment_design_artifact": ("experiment-design.json", "experiment-design.json", "experiment_design", "EXPERIMENT_DESIGNED"),
            "experiment_artifact": ("experiment-running.json", "experiment.json", "experiment", "EXPERIMENT_RUNNING"),
        }
        upstream_paths: dict[str, Path] = {}
        for key, (fixture_name, artifact_name, artifact_type, stage) in upstream_files.items():
            path = artifacts / artifact_name
            shutil.copyfile(source / fixture_name, path)
            assert_artifact(path, artifact_type, stage)
            if artifact_type in {"test_method", "experiment_design", "experiment"}:
                simulated = read_json(path)
                simulated["evidence_scope"] = "PHYSICAL"
                simulated["decision"] = "GO"
                simulated["evidence"][0]["statement"] = "SIMULATED_PHYSICAL_CONTRACT_TEST_NOT_EVIDENCE"
                simulated["evidence"][0]["source"] = "SIMULATED_PHYSICAL_CONTRACT_TEST_NOT_EVIDENCE"
                if artifact_type == "test_method":
                    simulated["qualification_status"] = "QUALIFIED"
                if artifact_type == "experiment":
                    simulated["doe_output_reference"] = {
                        "engine_name": "doe",
                        "engine_version": "simulated-contract-v1",
                        "input_digest": "a" * 64,
                        "output_digest": "a" * 64,
                    }
                    for entry in simulated["runs"]:
                        entry["formula_reference"] = "SIMULATED-FORMULA-001"
                        entry["doe_point_reference"] = {"run_index": 1}
                        entry["execution_provenance"] = {
                            "executed_at": "2026-08-25T09:30:00+08:00",
                            "operator_reference": "SIMULATED_PHYSICAL_CONTRACT_TEST_NOT_EVIDENCE",
                            "instrument_reference": "SIMULATED_PHYSICAL_CONTRACT_TEST_NOT_EVIDENCE",
                            "calibration_reference": "SIMULATED_PHYSICAL_CONTRACT_TEST_NOT_EVIDENCE",
                            "raw_record_reference": "SIMULATED_PHYSICAL_CONTRACT_TEST_NOT_EVIDENCE",
                        }
                        for response in entry["response_measurements"]:
                            response["method_reference"] = {
                                "method_id": "TM-DOE-001",
                                "qualification_reference": "SIMULATED_PHYSICAL_CONTRACT_TEST_NOT_EVIDENCE",
                            }
                write_json(path, simulated)
            upstream_paths[key] = path

        # Design-space companion (WP-01): the process record the window is fixed from.
        process_input_path, process_path = inputs / "process-input.json", artifacts / "process.json"
        write_json(process_input_path, process_input(upstream_paths["design_space_artifact"]))
        run(ROOT / "skills/process-definition/scripts/preflight_process_definition.py", process_input_path)
        run(ROOT / "skills/process-definition/scripts/build_process_artifact.py", process_input_path, process_path)
        run(ROOT / "skills/process-definition/scripts/validate_process_artifact.py", process_path)
        assert_artifact(process_path, "process", "DESIGN_SPACE_DEFINED")

        analysis_input = read_json(FIXTURES / "statistical-analysis" / "valid-input.synthetic.json")
        rewrite_upstream(analysis_input, upstream_paths)
        analysis_input_path, model_path = inputs / "analysis-input.json", artifacts / "model.json"
        write_json(analysis_input_path, analysis_input)
        run(ROOT / "skills/statistical-analysis/scripts/preflight_statistical_analysis.py", analysis_input_path)
        run(ROOT / "skills/statistical-analysis/scripts/build_model_artifact.py", analysis_input_path, model_path)
        model = assert_artifact(model_path, "model", "MODEL_BUILT")
        run(ROOT / "skills/statistical-analysis/scripts/validate_model_artifact.py", model_path)
        assert model["experiment_reference"] == read_json(upstream_paths["experiment_artifact"])["experiment_id"]

        optimization_input = read_json(FIXTURES / "optimization" / "valid-input.synthetic.json")
        rewrite_upstream(optimization_input, upstream_paths)
        optimization_input["model_artifact"] = str(model_path)
        optimization_input_path, optimization_path = inputs / "optimization-input.json", artifacts / "optimization.json"
        write_json(optimization_input_path, optimization_input)
        run(ROOT / "skills/optimization/scripts/preflight_optimization.py", optimization_input_path)
        run(ROOT / "skills/optimization/scripts/build_optimization_artifact.py", optimization_input_path, optimization_path)
        optimization = assert_artifact(optimization_path, "optimization", "OPTIMIZED")
        run(ROOT / "skills/optimization/scripts/validate_optimization_artifact.py", optimization_path)
        assert optimization["model_reference"] == model["model_id"]

        # Process window (WP-02): OPTIMIZED + the process record -> PROCESS_WINDOW_DEFINED.
        window_input_path, window_path = inputs / "scale-up-input.json", artifacts / "process-window.json"
        write_json(window_input_path, scale_up_input(process_path, optimization_path, optimization["optimization_id"]))
        run(ROOT / "skills/process-scale-up/scripts/preflight_process_scale_up.py", window_input_path)
        run(ROOT / "skills/process-scale-up/scripts/build_process_window_artifact.py", window_input_path, window_path)
        window = assert_artifact(window_path, "process", "PROCESS_WINDOW_DEFINED")
        run(ROOT / "skills/process-scale-up/scripts/validate_process_window_artifact.py", window_path)
        assert window["process_window"]["validated"] is True
        assert window["process_window"]["evidence_reference"] == "PROCESS-WINDOW:PW-WGO-DOE-001-PROD"

        gate_input = read_json(FIXTURES / "gate-review" / "valid-input.synthetic.json")
        rewrite_upstream(gate_input, upstream_paths)
        gate_input.update({"model_artifact": str(model_path), "optimization_artifact": str(optimization_path)})
        gate_input_path, gate_path = inputs / "gate-input.json", artifacts / "gate.json"
        write_json(gate_input_path, gate_input)
        run(ROOT / "skills/gate-review/scripts/preflight_gate_review.py", gate_input_path)
        run(ROOT / "skills/gate-review/scripts/build_gate_artifact.py", gate_input_path, gate_path)
        gate = assert_artifact(gate_path, "gate", "VERIFIED")
        run(ROOT / "skills/gate-review/scripts/validate_gate_artifact.py", gate_path)
        assert gate["experiment_reference"] == model["experiment_reference"]

        outputs = [read_json(path) for path in artifacts.glob("*.json")]
        assert {path.name for path in artifacts.glob("*.json")} == {
            "project.json", "challenge.json", "failure-ctq.json", "test-method.json", "design-space.json",
            "process.json", "experiment-design.json", "experiment.json", "model.json", "optimization.json",
            "process-window.json", "gate.json",
        }
        forbidden = {"freeze", "closed"}
        assert not (forbidden & {item["artifact_type"] for item in outputs})
        assert not ({"FROZEN", "CLOSED"} & {item["stage"] for item in outputs})

    print("PASS: WGO-DOE-001 ISO VG 320 chain through VERIFIED (Phase 3, incl. PROCESS_WINDOW_DEFINED)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
