"""End-to-end checks for the WP-01 process object and design-space constraint roles.

Covers:
1. A mixed design space (formulation + process variables) with explicit,
   consistent `constraint_role` values validates.
2. A design space without declared roles derives them by `variable_type` and
   reports each derivation explicitly (never silent).
3. The 11 existing `fixtures/formulation-design/` fixtures keep their behaviour.
4. The process-definition preflight rejects a parameter missing `source` or
   `evidence_id`.
5. A synthetic process artifact can be built and validated.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"

# Behaviour baseline for the 11 formulation-design fixtures, recorded before the
# WP-01 change. Lines added by WP-01 (the explicit CONSTRAINT_ROLE report) are
# filtered out before comparison, so this asserts the decision outcome is
# unchanged rather than the exact byte stream.
FIXTURE_HOLD_BASELINE = {
    "invalid-cross-project-and-reference.json": "HOLD: missing or invalid: test_method_artifact must have decision GO, project, challenge, failure_ctq, and test_method project_id values must match, test_method_artifact must have qualification_status QUALIFIED, design_space.qualified_test_method_references must equal the supplied qualified method_id, design_space.ctq_references: CTQ-404 does not exist; no artifact generated",
    "invalid-formulation-or-doe-file.json": "HOLD: missing or invalid: input must contain only required Stage 4 artifact paths and design_space, test_method_artifact must have decision GO, test_method_artifact must have qualification_status QUALIFIED; no artifact generated",
    "invalid-gap-evidence.json": "HOLD: missing or invalid: test_method_artifact must have decision GO, test_method_artifact must have qualification_status QUALIFIED, design_space.evidence contains GAP; current input is insufficient; no artifact generated",
    "invalid-lower-greater-than-upper.json": "HOLD: missing or invalid: test_method_artifact must have decision GO, test_method_artifact must have qualification_status QUALIFIED, design_space.variables[0].lower_bound.value must be <= upper_bound.value; no artifact generated",
    "invalid-missing-constraints.json": "HOLD: missing or invalid: test_method_artifact must have decision GO, test_method_artifact must have qualification_status QUALIFIED, design_space must contain only the Stage 4 input fields; no artifact generated",
    "invalid-missing-measurement-metadata.json": "HOLD: missing or invalid: test_method_artifact must have decision GO, test_method_artifact must have qualification_status QUALIFIED, design_space.variables[0].lower_bound; no artifact generated",
    "invalid-nonfinite-measurement.json": "HOLD: missing or invalid: test_method_artifact must have decision GO, test_method_artifact must have qualification_status QUALIFIED, design_space.variables[0].lower_bound.value, design_space.variables[0].upper_bound.value; no artifact generated",
    "invalid-upstream-decision-hold.json": "HOLD: missing or invalid: test_method_artifact must have decision GO, test_method_artifact must have qualification_status QUALIFIED; no artifact generated",
    "project-active-cross-project.json": "HOLD: missing or invalid: input must contain only required Stage 4 artifact paths and design_space, project_artifact, challenge_artifact, failure_ctq_artifact, test_method_artifact, design_space must contain only the Stage 4 input fields; no artifact generated",
    "test-method-decision-hold.json": "HOLD: missing or invalid: input must contain only required Stage 4 artifact paths and design_space, project_artifact, challenge_artifact, failure_ctq_artifact, test_method_artifact, design_space must contain only the Stage 4 input fields; no artifact generated",
    "valid-input.synthetic.json": "HOLD: missing or invalid: test_method_artifact must have decision GO, test_method_artifact must have qualification_status QUALIFIED; no artifact generated",
}

FORMULATION_PREFLIGHT = ROOT / "skills/formulation-design/scripts/preflight_formulation_design.py"
PROCESS_PREFLIGHT = ROOT / "skills/process-definition/scripts/preflight_process_definition.py"
PROCESS_BUILDER = ROOT / "skills/process-definition/scripts/build_process_artifact.py"
PROCESS_VALIDATOR = ROOT / "skills/process-definition/scripts/validate_process_artifact.py"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: Path, *arguments: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", script.name, *map(str, arguments)],
        cwd=script.parent,
        capture_output=True,
        text=True,
    )


def run_ok(script: Path, *arguments: Path) -> subprocess.CompletedProcess:
    result = run(script, *arguments)
    assert result.returncode == 0, f"{script.name}\n{result.stdout}{result.stderr}"
    return result


def assert_artifact(path: Path, artifact_type: str, stage: str) -> dict:
    artifact = read_json(path)
    assert artifact["artifact_type"] == artifact_type
    assert artifact["project_id"] == "WGO-001"
    assert artifact["stage"] == stage
    return artifact


def build_upstream(workspace: Path, inputs: Path, artifacts: Path) -> None:
    """Build the WGO-001 chain through TEST_METHODS_QUALIFIED (mirrors test_stage_chain)."""
    project_input = read_json(FIXTURES / "project-definition" / "valid-input.json")
    project_input["business_objective"] = "Synthetic WP-01 scope: define a grease process companion to a supplied design space."
    project_input["hard_constraints"].append("Synthetic WP-01 scope is limited to process-contract validation.")
    project_input["source_evidence"].append({
        "evidence_id": "E-P-WP01-001",
        "statement": "Synthetic WP-01 scope supplies a process-definition boundary for contract validation only.",
        "source": "synthetic WP-01 requirement",
        "status": "OBSERVED",
    })
    project_input_path = inputs / "project-input.json"
    write_json(project_input_path, project_input)
    run_ok(ROOT / "skills/project-definition/scripts/preflight_project_definition.py", project_input_path)

    project_path = artifacts / "project.json"
    project = read_json(FIXTURES / "duty-challenge" / "project-active.json")
    project["business_objective"] = project_input["business_objective"]
    project["hard_constraints"] = project_input["hard_constraints"]
    project["evidence"].append(project_input["source_evidence"][-1])
    write_json(project_path, project)
    run_ok(ROOT / "skills/project-definition/scripts/validate_project_artifact.py", project_path)
    assert_artifact(project_path, "project", "PROJECT_DEFINED")

    duty_definition_input = read_json(FIXTURES / "duty-definition" / "valid-input.json")
    duty_definition_input["project_artifact"] = str(project_path)
    duty_definition_input_path, duty_path = inputs / "duty-definition-input.json", artifacts / "duty.json"
    write_json(duty_definition_input_path, duty_definition_input)
    run_ok(ROOT / "skills/duty-definition/scripts/preflight_duty_definition.py", duty_definition_input_path)
    run_ok(ROOT / "skills/duty-definition/scripts/build_duty_artifact.py", duty_definition_input_path, duty_path)
    run_ok(ROOT / "skills/duty-definition/scripts/validate_duty_artifact.py", duty_path)
    assert_artifact(duty_path, "duty", "DUTY_DEFINED")

    duty_input = read_json(FIXTURES / "duty-challenge" / "valid-input.json")
    duty_input["duty_artifact"] = str(duty_path)
    duty_input_path = inputs / "duty-input.json"
    write_json(duty_input_path, duty_input)
    run_ok(ROOT / "skills/duty-challenge-analysis/scripts/preflight_duty_challenge.py", duty_input_path)
    challenge_path = artifacts / "challenge.json"
    shutil.copyfile(FIXTURES / "duty-challenge" / "valid-artifact.json", challenge_path)
    run_ok(ROOT / "skills/duty-challenge-analysis/scripts/validate_duty_challenge_artifact.py", challenge_path)
    challenge = assert_artifact(challenge_path, "challenge", "CHALLENGES_DEFINED")

    failure_input = read_json(FIXTURES / "failure-ctq" / "valid-input.json")
    failure_input["project_artifact"] = str(project_path)
    failure_input["challenge_artifact"] = str(challenge_path)
    failure_input_path = inputs / "failure-input.json"
    write_json(failure_input_path, failure_input)
    run_ok(ROOT / "skills/failure-ctq-analysis/scripts/preflight_failure_ctq.py", failure_input_path)
    failure_path = artifacts / "failure-ctq.json"
    shutil.copyfile(FIXTURES / "failure-ctq" / "valid-artifact.json", failure_path)
    run_ok(ROOT / "skills/failure-ctq-analysis/scripts/validate_failure_ctq_artifact.py", failure_path)
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
    run_ok(ROOT / "skills/test-method-qualification/scripts/preflight_test_method.py", method_input_path)
    run_ok(ROOT / "skills/test-method-qualification/scripts/build_test_method_artifact.py", method_input_path, method_path)
    run_ok(ROOT / "skills/test-method-qualification/scripts/validate_test_method_artifact.py", method_path)
    assert_artifact(method_path, "test_method", "TEST_METHODS_QUALIFIED")


def formulation_input(upstream: dict[str, Path]) -> dict:
    design_input = read_json(FIXTURES / "formulation-design" / "valid-input.synthetic.json")
    design_input.update({key: str(path) for key, path in upstream.items()})
    return design_input


def process_input(design_space_path: Path) -> dict:
    measurement = {
        "value": 50, "unit": "kg", "source": "Synthetic WP-01 process spec",
        "method_version": "scale-v1", "material_batch": "BATCH-SYN-001", "formula_version": "v0.1",
    }
    parameters = [
        ("P-SAP-TEMP", "saponification temperature", 90, 110, "degC"),
        ("P-DEH-TEMP", "dehydration temperature", 100, 130, "degC"),
        ("P-PHI-TEMP", "phase inversion temperature", 150, 180, "degC"),
        ("P-COOL-RATE", "cooling rate", 1, 5, "degC/min"),
        ("P-MIL-GAP", "mill gap", 0.05, 0.3, "mm"),
        ("P-HOM-PRES", "homogenization pressure", 5, 20, "MPa"),
        ("P-VAC-PRES", "vacuum pressure", 1, 10, "kPa"),
        ("P-FILL-TEMP", "filling temperature", 70, 90, "degC"),
    ]
    step_types = [
        "SAPONIFICATION", "DEHYDRATION", "PHASE_INVERSION", "DILUTION_COOLING",
        "MILLING", "HOMOGENIZATION", "VACUUM_DEAERATION", "FILLING",
    ]
    steps = []
    for index, (parameter_id, name, lower, upper, unit) in enumerate(parameters):
        steps.append({
            "step_id": f"ST-{index + 1:03d}",
            "step_type": step_types[index],
            "parameters": [{
                "parameter_id": parameter_id, "parameter_name": name,
                "lower_bound": lower, "upper_bound": upper, "unit": unit,
                "source": "Synthetic WP-01 process spec",
                "evidence_id": f"EV-PROC-{index + 1:03d}",
                "status": "ASSUMED",
            }],
        })
    return {
        "design_space_artifact": str(design_space_path),
        "process": {
            "process_id": "PROC-WGO-001",
            "project_reference": "WGO-001",
            "process_step": steps,
            "batch_scale": {"scale_class": "PILOT", "batch_size": measurement},
            "amplification_factor": 20.0,
            "process_window": {"window_id": "PW-WGO-001", "basis": "Synthetic WP-01 window supplied for contract validation only", "validated": False},
            "control_points": [{
                "control_point_id": "CP-001", "parameter_id": "P-PHI-TEMP", "control_type": "IN_PROCESS",
                "criterion": "Hold phase inversion within the supplied window",
                "source": "Synthetic WP-01 process spec", "evidence_id": "EV-PROC-003",
            }],
            "cpk": {"value": 1.33, "ctq_reference": "CTQ-001", "sample_size": 30},
            "material_batch_reference": "BATCH-SYN-001",
            "factor_role": "SUB_PLOT",
            "evidence_scope": "SYNTHETIC",
            "evidence": [{
                "evidence_id": "EV-PROC-001",
                "statement": "Synthetic process bounds supplied for contract validation only; not a qualified process window.",
                "source": "Synthetic WP-01 process fixture",
                "status": "ASSUMED",
            }],
        },
    }


def validate_process_schema(artifact: dict) -> list[str]:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    schemas = ROOT / "schemas"
    common = read_json(schemas / "common.schema.json")
    process = read_json(schemas / "process.schema.json")
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    registry = registry.with_resource(process["$id"], Resource.from_contents(process))
    return [error.message for error in Draft202012Validator(process, registry=registry).iter_errors(artifact)]


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        inputs, artifacts = workspace / "inputs", workspace / "artifacts"
        inputs.mkdir()
        artifacts.mkdir()

        build_upstream(workspace, inputs, artifacts)
        upstream = {
            "project_artifact": artifacts / "project.json",
            "challenge_artifact": artifacts / "challenge.json",
            "failure_ctq_artifact": artifacts / "failure-ctq.json",
            "test_method_artifact": artifacts / "test-method.json",
        }

        # Case A: mixed design space with explicit, consistent constraint_role values.
        explicit_input = formulation_input(upstream)
        explicit_input["design_space"]["variables"][0]["constraint_role"] = "MIXTURE_CLOSED"
        explicit_input["design_space"]["variables"][1]["constraint_role"] = "INDEPENDENT"
        explicit_path, design_path = inputs / "design-explicit.json", artifacts / "design-space.json"
        write_json(explicit_path, explicit_input)
        explicit_result = run_ok(FORMULATION_PREFLIGHT, explicit_path)
        assert "FORMULATION_VARIABLE_A: CONSTRAINT_ROLE declared MIXTURE_CLOSED" in explicit_result.stdout, explicit_result.stdout
        assert "BLEND_TEMPERATURE: CONSTRAINT_ROLE declared INDEPENDENT" in explicit_result.stdout, explicit_result.stdout
        run_ok(ROOT / "skills/formulation-design/scripts/build_design_space_artifact.py", explicit_path, design_path)
        run_ok(ROOT / "skills/formulation-design/scripts/validate_design_space_artifact.py", design_path)
        design = assert_artifact(design_path, "design_space", "DESIGN_SPACE_DEFINED")
        roles = {variable["variable_id"]: variable["constraint_role"] for variable in design["variables"]}
        assert roles == {"FORMULATION_VARIABLE_A": "MIXTURE_CLOSED", "BLEND_TEMPERATURE": "INDEPENDENT"}, roles

        # Case B: no declared role -> derived by variable_type and reported explicitly.
        derived_input = formulation_input(upstream)
        for variable in derived_input["design_space"]["variables"]:
            variable.pop("constraint_role", None)
        derived_path = inputs / "design-derivation.json"
        write_json(derived_path, derived_input)
        derived_result = run_ok(FORMULATION_PREFLIGHT, derived_path)
        assert "FORMULATION_VARIABLE_A: CONSTRAINT_ROLE derived MIXTURE_CLOSED from FORMULATION_VARIABLE" in derived_result.stdout, derived_result.stdout
        assert "BLEND_TEMPERATURE: CONSTRAINT_ROLE derived INDEPENDENT from PROCESS_VARIABLE" in derived_result.stdout, derived_result.stdout

        # Case C: a declared role that contradicts the variable type is rejected.
        contradiction_input = formulation_input(upstream)
        contradiction_input["design_space"]["variables"][1]["variable_type"] = "MATERIAL_FAMILY"
        contradiction_input["design_space"]["variables"][1]["constraint_role"] = "MIXTURE_CLOSED"
        contradiction_path = inputs / "design-contradiction.json"
        write_json(contradiction_path, contradiction_input)
        contradiction = run(FORMULATION_PREFLIGHT, contradiction_path)
        assert contradiction.returncode != 0, contradiction.stdout
        assert "contradicts variable_type MATERIAL_FAMILY" in contradiction.stdout, contradiction.stdout

        # Case D: an out-of-enum declared role is rejected.
        invalid_enum_input = formulation_input(upstream)
        invalid_enum_input["design_space"]["variables"][0]["constraint_role"] = "CLOSED"
        invalid_enum_path = inputs / "design-invalid-role.json"
        write_json(invalid_enum_path, invalid_enum_input)
        invalid_enum = run(FORMULATION_PREFLIGHT, invalid_enum_path)
        assert invalid_enum.returncode != 0, invalid_enum.stdout
        assert "is not one of" in invalid_enum.stdout, invalid_enum.stdout

        # Process object: a synthetic but complete artifact builds and validates.
        valid_process_input = process_input(design_path)
        valid_process_path, process_path = inputs / "process-input.json", artifacts / "process.json"
        write_json(valid_process_path, valid_process_input)
        run_ok(PROCESS_PREFLIGHT, valid_process_path)
        run_ok(PROCESS_BUILDER, valid_process_path, process_path)
        run_ok(PROCESS_VALIDATOR, process_path)
        process = read_json(process_path)
        assert process["artifact_type"] == "process"
        assert process["project_id"] == "WGO-001"
        assert process["project_reference"] == "WGO-001"
        assert process["factor_role"] == "SUB_PLOT"
        assert process["evidence_scope"] == "SYNTHETIC"
        assert process["decision"] == "GO"
        assert len(process["process_step"]) == 8
        assert validate_process_schema(process) == [], validate_process_schema(process)

        # Process object: a parameter missing source is rejected, per parameter.
        missing_source = process_input(design_path)
        del missing_source["process"]["process_step"][0]["parameters"][0]["source"]
        missing_source_path = inputs / "process-missing-source.json"
        write_json(missing_source_path, missing_source)
        source_result = run(PROCESS_PREFLIGHT, missing_source_path)
        assert source_result.returncode != 0, source_result.stdout
        assert "parameters[0].source is required for every process parameter" in source_result.stdout, source_result.stdout

        # Process object: a parameter missing evidence_id is rejected, per parameter.
        missing_evidence = process_input(design_path)
        del missing_evidence["process"]["process_step"][2]["parameters"][0]["evidence_id"]
        missing_evidence_path = inputs / "process-missing-evidence.json"
        write_json(missing_evidence_path, missing_evidence)
        evidence_result = run(PROCESS_PREFLIGHT, missing_evidence_path)
        assert evidence_result.returncode != 0, evidence_result.stdout
        assert "parameters[0].evidence_id is required for every process parameter" in evidence_result.stdout, evidence_result.stdout

        # Process object: an upstream design space that is not GO is rejected.
        not_go_design = read_json(design_path)
        not_go_design["decision"] = "HOLD"
        not_go_path = artifacts / "design-hold.json"
        write_json(not_go_path, not_go_design)
        hold_process_path = inputs / "process-hold-upstream.json"
        write_json(hold_process_path, process_input(not_go_path))
        hold_result = run(PROCESS_PREFLIGHT, hold_process_path)
        assert hold_result.returncode != 0, hold_result.stdout
        assert "design_space_artifact must have decision GO" in hold_result.stdout, hold_result.stdout

        # Deployed copies (installed to a temp target, never the user's real skills
        # directory) must run their preflight standalone against a valid input.
        sys.path.insert(0, str(ROOT))
        from integrations.open_science import install_skill
        from scripts.install_domain_skill import ENGINE_ROOT, ENGINE_SKILLS, SKILLS, shared_modules_for

        deploy_ws = workspace / "deploy"
        deploy_target = deploy_ws / ".opencode" / "skills"
        deploy_target.mkdir(parents=True)
        for skill in ("formulation-design", "process-definition"):
            install_skill(
                ROOT / "skills" / skill, ROOT / "schemas", SKILLS[skill], deploy_target,
                engine_root=ENGINE_ROOT if skill in ENGINE_SKILLS else None,
                workspace_root=deploy_ws, shared_modules=shared_modules_for(skill),
            )
        deployed_formulation = deploy_target / "formulation-design"
        deployed_process = deploy_target / "process-definition"
        assert (deployed_formulation / "scripts" / "constraint_role.py").is_file()
        deployed_design = run(deployed_formulation / "scripts" / "preflight_formulation_design.py", explicit_path)
        assert deployed_design.returncode == 0, deployed_design.stdout + deployed_design.stderr
        deployed_process_result = run(deployed_process / "scripts" / "preflight_process_definition.py", valid_process_path)
        assert deployed_process_result.returncode == 0, deployed_process_result.stdout + deployed_process_result.stderr

    # Continuous regression: the 11 existing formulation-design fixtures are unchanged.
    fixture_dir = FIXTURES / "formulation-design"
    fixture_names = sorted(path.name for path in fixture_dir.glob("*.json"))
    assert fixture_names == sorted(FIXTURE_HOLD_BASELINE), fixture_names
    for name in fixture_names:
        result = run(FORMULATION_PREFLIGHT, fixture_dir / name)
        hold_lines = [line for line in result.stdout.splitlines() if "CONSTRAINT_ROLE" not in line]
        assert result.returncode == 1, f"{name} exit code changed: {result.returncode}"
        assert hold_lines == [FIXTURE_HOLD_BASELINE[name]], f"{name}: {hold_lines}"

    # The new skill is registered for installation.
    sys.path.insert(0, str(ROOT))
    from scripts.install_domain_skill import SKILLS

    assert "process-definition" in SKILLS, sorted(SKILLS)
    assert SKILLS["process-definition"] == ("common.schema.json", "design_space.schema.json", "process.schema.json"), SKILLS["process-definition"]

    print("PASS: WP-01 process object, constraint_role derivation, and fixture regression")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
