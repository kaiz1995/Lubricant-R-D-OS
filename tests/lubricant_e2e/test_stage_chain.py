"""Smoke the fixed ISO VG 320 wind gear-oil chain through design space only."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"


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
    assert artifact["project_id"] == "WGO-001"
    assert artifact["stage"] == stage
    return artifact


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        inputs, artifacts = workspace / "inputs", workspace / "artifacts"
        inputs.mkdir()
        artifacts.mkdir()

        project_input = read_json(FIXTURES / "project-definition" / "valid-input.json")
        project_input["business_objective"] = "Synthetic E2E scope: evaluate a supplied 10-20% approved-product cost-reduction range."
        project_input["hard_constraints"].append("Synthetic E2E scope is limited to the supplied 10-20% cost-reduction range.")
        project_input["source_evidence"].append({
            "evidence_id": "E-P-SMOKE-001",
            "statement": "Synthetic E2E scope supplies a 10-20% cost-reduction range for chain validation only.",
            "source": "synthetic smoke-test requirement",
            "status": "OBSERVED",
        })
        project_input_path = inputs / "project-input.json"
        write_json(project_input_path, project_input)
        run(ROOT / "skills/project-definition/scripts/preflight_project_definition.py", project_input_path)

        # Stages 0 and 2 intentionally expose preflight/validation, not builders. Reuse their canonical valid artifacts.
        project_path = artifacts / "project.json"
        project = read_json(FIXTURES / "duty-challenge" / "project-active.json")
        project["business_objective"] = project_input["business_objective"]
        project["hard_constraints"] = project_input["hard_constraints"]
        project["evidence"].append(project_input["source_evidence"][-1])
        write_json(project_path, project)
        run(ROOT / "skills/project-definition/scripts/validate_project_artifact.py", project_path)
        project = assert_artifact(project_path, "project", "PROJECT_DEFINED")
        assert project["product_family"] == "ISO VG 320 wind gear oil"
        assert "10-20%" in project["business_objective"]
        assert any("10-20%" in constraint for constraint in project["hard_constraints"])

        duty_definition_input = read_json(FIXTURES / "duty-definition" / "valid-input.json")
        duty_definition_input["project_artifact"] = str(project_path)
        duty_definition_input_path, duty_path = inputs / "duty-definition-input.json", artifacts / "duty.json"
        write_json(duty_definition_input_path, duty_definition_input)
        run(ROOT / "skills/duty-definition/scripts/preflight_duty_definition.py", duty_definition_input_path)
        run(ROOT / "skills/duty-definition/scripts/build_duty_artifact.py", duty_definition_input_path, duty_path)
        run(ROOT / "skills/duty-definition/scripts/validate_duty_artifact.py", duty_path)
        duty = assert_artifact(duty_path, "duty", "DUTY_DEFINED")
        assert duty["project_reference"] == project["project_id"]

        duty_input = read_json(FIXTURES / "duty-challenge" / "valid-input.json")
        duty_input["duty_artifact"] = str(duty_path)
        duty_input_path = inputs / "duty-input.json"
        write_json(duty_input_path, duty_input)
        run(ROOT / "skills/duty-challenge-analysis/scripts/preflight_duty_challenge.py", duty_input_path)
        challenge_path = artifacts / "challenge.json"
        shutil.copyfile(FIXTURES / "duty-challenge" / "valid-artifact.json", challenge_path)
        run(ROOT / "skills/duty-challenge-analysis/scripts/validate_duty_challenge_artifact.py", challenge_path)
        challenge = assert_artifact(challenge_path, "challenge", "CHALLENGES_DEFINED")

        failure_input = read_json(FIXTURES / "failure-ctq" / "valid-input.json")
        failure_input["project_artifact"] = str(project_path)
        failure_input["challenge_artifact"] = str(challenge_path)
        failure_input_path = inputs / "failure-input.json"
        write_json(failure_input_path, failure_input)
        run(ROOT / "skills/failure-ctq-analysis/scripts/preflight_failure_ctq.py", failure_input_path)
        failure_path = artifacts / "failure-ctq.json"
        shutil.copyfile(FIXTURES / "failure-ctq" / "valid-artifact.json", failure_path)
        run(ROOT / "skills/failure-ctq-analysis/scripts/validate_failure_ctq_artifact.py", failure_path)
        failure = assert_artifact(failure_path, "failure_ctq", "FAILURE_CTQ_DEFINED")
        assert failure["challenge_reference"] == challenge["challenge_id"]

        method_input = read_json(FIXTURES / "test-method" / "valid-input.synthetic.json")
        method_input.update({
            "project_artifact": str(project_path),
            "challenge_artifact": str(challenge_path),
            "failure_ctq_artifact": str(failure_path),
            "evidence_scope": "PHYSICAL",
        })
        method_input["test_method"]["qualification_status"] = "QUALIFIED"
        for evidence in method_input["evidence"]:
            evidence["statement"] = "Simulated physical contract test only; not a lab record or release evidence."
            evidence["source"] = "Simulated physical contract test only"
        method_input["test_method"]["qualification_basis"] = ["simulated physical contract test only"]
        method_input["test_method"]["qualification_metrics"][0]["measurement"]["source"] = "Simulated physical contract test only"
        method_input_path, method_path = inputs / "method-input.json", artifacts / "test-method.json"
        write_json(method_input_path, method_input)
        run(ROOT / "skills/test-method-qualification/scripts/preflight_test_method.py", method_input_path)
        run(ROOT / "skills/test-method-qualification/scripts/build_test_method_artifact.py", method_input_path, method_path)
        run(ROOT / "skills/test-method-qualification/scripts/validate_test_method_artifact.py", method_path)
        method = assert_artifact(method_path, "test_method", "TEST_METHODS_QUALIFIED")
        assert method["target_failure_reference"] == failure["failure_id"]
        assert method["evidence_scope"] == "PHYSICAL"
        assert method["decision"] == "GO"

        design_input = read_json(FIXTURES / "formulation-design" / "valid-input.synthetic.json")
        design_input.update({
            "project_artifact": str(project_path),
            "challenge_artifact": str(challenge_path),
            "failure_ctq_artifact": str(failure_path),
            "test_method_artifact": str(method_path),
        })
        design_input_path, design_path = inputs / "design-input.json", artifacts / "design-space.json"
        write_json(design_input_path, design_input)
        run(ROOT / "skills/formulation-design/scripts/preflight_formulation_design.py", design_input_path)
        run(ROOT / "skills/formulation-design/scripts/build_design_space_artifact.py", design_input_path, design_path)
        run(ROOT / "skills/formulation-design/scripts/validate_design_space_artifact.py", design_path)
        design = assert_artifact(design_path, "design_space", "DESIGN_SPACE_DEFINED")
        assert design["ctq_references"] == [failure["ctqs"][0]["ctq_id"]]
        assert design["qualified_test_method_references"] == [method["method_id"]]

        outputs = [read_json(path) for path in artifacts.glob("*.json")]
        assert {path.name for path in artifacts.glob("*.json")} == {
            "project.json", "duty.json", "challenge.json", "failure-ctq.json", "test-method.json", "design-space.json",
        }
        forbidden = {"doe", "experiment_design", "experiment", "statistical_analysis", "gate", "freeze"}
        assert not (forbidden & {item["artifact_type"] for item in outputs})
        assert not ({"EXPERIMENT_DESIGNED", "EXPERIMENT_RUNNING", "MODEL_BUILT", "OPTIMIZED", "VERIFIED", "FROZEN"}
                    & {item["stage"] for item in outputs})

    print("PASS: WGO-001 ISO VG 320 chain through DESIGN_SPACE_DEFINED")
    print("full_e2e_status=BLOCKED_NOT_IMPLEMENTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
