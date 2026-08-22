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
            upstream_paths[key] = path

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
            "experiment-design.json", "experiment.json", "model.json", "optimization.json", "gate.json",
        }
        forbidden = {"freeze", "closed"}
        assert not (forbidden & {item["artifact_type"] for item in outputs})
        assert not ({"FROZEN", "CLOSED"} & {item["stage"] for item in outputs})

    print("PASS: WGO-DOE-001 ISO VG 320 chain through VERIFIED (Phase 3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
