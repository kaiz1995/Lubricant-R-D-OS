"""End-to-end checks for the WP-02 process-window segment (PROCESS_WINDOW_DEFINED).

Covers:
1. The router/contract stage PROCESS_WINDOW_DEFINED is reachable and the process
   record plus the OPTIMIZED conclusion fix one window.
2. The built window artifact carries the 工艺窗口 evidence as
   `PROCESS-WINDOW:<window_id>` and retains both evidence sets.
3. Every fail-closed rule rejects: wrong upstream stage, HOLD optimization,
   cross-project, no scale-up, scope upgrade, GAP evidence.
4. design_freeze MANUFACTURABILITY_ACCEPTABLE must cite the fixed window.
5. The deployed copy runs its own preflight standalone.
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

PROCESS_PREFLIGHT = ROOT / "skills/process-definition/scripts/preflight_process_definition.py"
PROCESS_BUILDER = ROOT / "skills/process-definition/scripts/build_process_artifact.py"
PROCESS_VALIDATOR = ROOT / "skills/process-definition/scripts/validate_process_artifact.py"
SCALE_PREFLIGHT = ROOT / "skills/process-scale-up/scripts/preflight_process_scale_up.py"
SCALE_BUILDER = ROOT / "skills/process-scale-up/scripts/build_process_window_artifact.py"
SCALE_VALIDATOR = ROOT / "skills/process-scale-up/scripts/validate_process_window_artifact.py"

PROJECT_ID = "WGO-DOE-001"
SIMULATED = "SIMULATED_PHYSICAL_CONTRACT_TEST_NOT_EVIDENCE"
MEASUREMENT = {
    "value": 500, "unit": "kg", "source": SIMULATED,
    "method_version": "scale-v2", "material_batch": "BATCH-PROD-001", "formula_version": "v0.2",
}
STEPS = [
    ("P-SAP-TEMP", "saponification temperature", 90, 110, "degC", "SAPONIFICATION"),
    ("P-DEH-TEMP", "dehydration temperature", 100, 130, "degC", "DEHYDRATION"),
    ("P-PHI-TEMP", "phase inversion temperature", 150, 180, "degC", "PHASE_INVERSION"),
    ("P-COOL-RATE", "cooling rate", 1, 5, "degC/min", "DILUTION_COOLING"),
    ("P-MIL-GAP", "mill gap", 0.05, 0.3, "mm", "MILLING"),
    ("P-HOM-PRES", "homogenization pressure", 5, 20, "MPa", "HOMOGENIZATION"),
    ("P-VAC-PRES", "vacuum pressure", 1, 10, "kPa", "VACUUM_DEAERATION"),
    ("P-FILL-TEMP", "filling temperature", 70, 90, "degC", "FILLING"),
]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: Path, *arguments: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", script.name, *map(str, arguments)],
        cwd=script.parent, capture_output=True, text=True,
    )


def run_ok(script: Path, *arguments: Path) -> subprocess.CompletedProcess:
    result = run(script, *arguments)
    assert result.returncode == 0, f"{script.name}\n{result.stdout}{result.stderr}"
    return result


def process_input(design_space_path: Path, **overrides) -> dict:
    measurement = {
        "value": 50, "unit": "kg", "source": SIMULATED,
        "method_version": "scale-v1", "material_batch": "BATCH-SYN-001", "formula_version": "v0.1",
    }
    steps = [
        {
            "step_id": f"ST-{index + 1:03d}", "step_type": step_type,
            "parameters": [{
                "parameter_id": parameter_id, "parameter_name": name,
                "lower_bound": lower, "upper_bound": upper, "unit": unit,
                "source": SIMULATED, "evidence_id": f"EV-PROC-{index + 1:03d}", "status": "ASSUMED",
            }],
        }
        for index, (parameter_id, name, lower, upper, unit, step_type) in enumerate(STEPS)
    ]
    process = {
        "process_id": "PROC-WGO-001",
        "project_reference": PROJECT_ID,
        "process_step": steps,
        "batch_scale": {"scale_class": "PILOT", "batch_size": measurement},
        "amplification_factor": 20.0,
        "process_window": {"window_id": "PW-WGO-001", "basis": "Synthetic pilot window supplied for contract validation only", "validated": False},
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
            "evidence_id": "EV-PROC-001",
            "statement": f"{SIMULATED} pilot process bounds; not a qualified process window.",
            "source": SIMULATED, "status": "OBSERVED",
        }],
    }
    process.update(overrides)
    return {"design_space_artifact": str(design_space_path), "process": process}


def optimization_artifact(artifacts: Path) -> Path:
    optimization = read_json(FIXTURES / "optimization" / "optimization.json")
    optimization["decision"] = "GO"
    optimization["evidence_scope"] = "PHYSICAL"
    for item in optimization["evidence"]:
        item["statement"] = SIMULATED
        item["source"] = SIMULATED
    path = artifacts / "optimization.json"
    write_json(path, optimization)
    return path


def scale_up(optimization_id: str, **overrides) -> dict:
    block = {
        "window_id": "PW-WGO-001-PROD",
        "basis": f"{SIMULATED}: pilot-to-production amplification basis",
        "amplification_factor": 200.0,
        "batch_scale": {"scale_class": "PRODUCTION", "batch_size": MEASUREMENT},
        "evidence_scope": "PHYSICAL",
        "evidence": [{
            "evidence_id": "EV-SCALE-001",
            "statement": f"{SIMULATED}: amplification run reproduced the window at production scale.",
            "source": f"{SIMULATED} {optimization_id} + amplification run record AR-001",
            "status": "OBSERVED",
        }],
    }
    block.update(overrides)
    return block


def scale_input(process_path: Path, optimization_path: Path, block: dict) -> dict:
    return {"process_artifact": str(process_path), "optimization_artifact": str(optimization_path), "scale_up": block}


def design_freeze_errors(freeze: dict) -> list[str]:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    schemas = ROOT / "schemas"
    common = read_json(schemas / "common.schema.json")
    schema = read_json(schemas / "design_freeze.schema.json")
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return [error.message for error in Draft202012Validator(schema, registry=registry).iter_errors(freeze)]


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        inputs, artifacts = workspace / "inputs", workspace / "artifacts"
        inputs.mkdir()
        artifacts.mkdir()

        # Upstream 1: the DESIGN_SPACE_DEFINED process record (process-definition).
        design_space_path = artifacts / "design-space.json"
        shutil.copyfile(FIXTURES / "optimization" / "design-space-defined.json", design_space_path)
        process_input_path = inputs / "process-input.json"
        write_json(process_input_path, process_input(design_space_path))
        run_ok(PROCESS_PREFLIGHT, process_input_path)
        process_path = artifacts / "process.json"
        run_ok(PROCESS_BUILDER, process_input_path, process_path)
        run_ok(PROCESS_VALIDATOR, process_path)
        process = read_json(process_path)
        assert process["stage"] == "DESIGN_SPACE_DEFINED" and process["project_id"] == PROJECT_ID

        # Upstream 2: the OPTIMIZED conclusion.
        optimization_path = optimization_artifact(artifacts)
        optimization_id = read_json(optimization_path)["optimization_id"]

        block = scale_up(optimization_id)
        input_path, window_path = inputs / "scale-up-input.json", artifacts / "process-window.json"
        write_json(input_path, scale_input(process_path, optimization_path, block))
        run_ok(SCALE_PREFLIGHT, input_path)
        run_ok(SCALE_BUILDER, input_path, window_path)
        run_ok(SCALE_VALIDATOR, window_path)
        window = read_json(window_path)
        assert window["artifact_type"] == "process"
        assert window["stage"] == "PROCESS_WINDOW_DEFINED"
        assert window["project_id"] == PROJECT_ID
        assert window["evidence_scope"] == "PHYSICAL"
        assert window["decision"] == "GO"
        assert window["process_window"] == {
            "window_id": "PW-WGO-001-PROD",
            "basis": block["basis"],
            "validated": True,
            "evidence_reference": "PROCESS-WINDOW:PW-WGO-001-PROD",
        }, window["process_window"]
        # Scale step applied, everything else carried over unchanged.
        assert window["amplification_factor"] == 200.0 and window["batch_scale"] == block["batch_scale"]
        assert window["process_step"] == process["process_step"]
        assert window["control_points"] == process["control_points"]
        assert window["cpk"] == process["cpk"] and window["factor_role"] == process["factor_role"]
        # Both evidence sets retained, upstream first.
        assert window["evidence"] == [*process["evidence"], *block["evidence"]], window["evidence"]

        def rejected(overrides: dict, fragment: str, label: str) -> None:
            bad = scale_input(process_path, optimization_path, {**block, **overrides})
            bad_path = inputs / f"reject-{label}.json"
            write_json(bad_path, bad)
            result = run(SCALE_PREFLIGHT, bad_path)
            assert result.returncode != 0, f"{label} was accepted: {result.stdout}"
            assert fragment in result.stdout, f"{label}: {result.stdout}"

        # A window that does not scale up is rejected (the amplifier must increase).
        rejected({"amplification_factor": 20.0}, "must exceed the process record amplification_factor", "no-amplification")
        # A batch scale that does not advance is rejected.
        rejected({"batch_scale": {"scale_class": "PILOT", "batch_size": MEASUREMENT}}, "must advance beyond the process record scale class", "no-scale-advance")
        # A scope upgrade mid-chain is rejected.
        rejected({"evidence_scope": "SYNTHETIC"}, "must retain the process record evidence_scope", "scope-upgrade")
        # A GAP in the amplification evidence is rejected.
        rejected({"evidence": [*block["evidence"], {"evidence_id": "EV-SCALE-002", "statement": SIMULATED, "source": SIMULATED, "status": "GAP"}]}, "contains GAP", "gap-evidence")

        # The OPTIMIZED conclusion must be GO, not HOLD.
        hold_optimization = read_json(optimization_path)
        hold_optimization["decision"] = "HOLD"
        hold_path = artifacts / "optimization-hold.json"
        write_json(hold_path, hold_optimization)
        hold_input = inputs / "scale-up-hold-optimization.json"
        write_json(hold_input, scale_input(process_path, hold_path, block))
        hold_result = run(SCALE_PREFLIGHT, hold_input)
        assert hold_result.returncode != 0 and "optimization_artifact must have decision GO" in hold_result.stdout, hold_result.stdout

        # A process record and an OPTIMIZED conclusion from different projects are rejected.
        cross_project = read_json(optimization_path)
        cross_project["project_id"] = "WGO-OTHER-999"
        cross_path = artifacts / "optimization-cross-project.json"
        write_json(cross_path, cross_project)
        cross_input = inputs / "scale-up-cross-project.json"
        write_json(cross_input, scale_input(process_path, cross_path, block))
        cross_result = run(SCALE_PREFLIGHT, cross_input)
        assert cross_result.returncode != 0 and "must belong to the same project_id" in cross_result.stdout, cross_result.stdout

        # A process record that is not DESIGN_SPACE_DEFINED is rejected.
        wrong_stage = read_json(process_path)
        wrong_stage["stage"] = "OPTIMIZED"
        wrong_stage_path = artifacts / "process-wrong-stage.json"
        write_json(wrong_stage_path, wrong_stage)
        wrong_input = inputs / "scale-up-wrong-stage.json"
        write_json(wrong_input, scale_input(wrong_stage_path, optimization_path, block))
        wrong_result = run(SCALE_PREFLIGHT, wrong_input)
        assert wrong_result.returncode != 0 and "process_artifact must be stage DESIGN_SPACE_DEFINED" in wrong_result.stdout, wrong_result.stdout

        # The validator rejects a tampered window (validated flag / citation).
        tampered = read_json(window_path)
        tampered["process_window"]["validated"] = False
        tampered_path = artifacts / "window-tampered.json"
        write_json(tampered_path, tampered)
        tampered_result = run(SCALE_VALIDATOR, tampered_path)
        assert tampered_result.returncode != 0 and "process_window.validated must be true" in tampered_result.stdout, tampered_result.stdout

        # design_freeze MANUFACTURABILITY_ACCEPTABLE must cite the fixed window.
        freeze = read_json(FIXTURES / "valid" / "design_freeze.json")
        assert design_freeze_errors(freeze) == [], design_freeze_errors(freeze)
        for condition in freeze["freeze_record"]["freeze_conditions"]:
            if condition["condition_id"] == "MANUFACTURABILITY_ACCEPTABLE":
                condition["evidence_reference"] = window["process_window"]["evidence_reference"]
        assert design_freeze_errors(freeze) == [], design_freeze_errors(freeze)
        for condition in freeze["freeze_record"]["freeze_conditions"]:
            if condition["condition_id"] == "MANUFACTURABILITY_ACCEPTABLE":
                condition["evidence_reference"] = "VR-MFG-001"
        assert any("PROCESS-WINDOW" in message for message in design_freeze_errors(freeze)), design_freeze_errors(freeze)

        # Deployed copy (installed to a temp target, never the user's real skills
        # directory) must run its own preflight standalone.
        sys.path.insert(0, str(ROOT))
        from integrations.open_science import install_skill
        from scripts.install_domain_skill import ENGINE_ROOT, ENGINE_SKILLS, SKILLS, contracts_for, shared_modules_for

        deploy_ws = workspace / "deploy"
        deploy_target = deploy_ws / ".opencode" / "skills"
        deploy_target.mkdir(parents=True)
        for skill in ("process-definition", "process-scale-up"):
            install_skill(
                ROOT / "skills" / skill, ROOT / "schemas", SKILLS[skill], deploy_target,
                engine_root=ENGINE_ROOT if skill in ENGINE_SKILLS else None,
                workspace_root=deploy_ws, shared_modules=shared_modules_for(skill),
                contract_files=contracts_for(skill),
            )
        deployed_preflight = deploy_target / "process-scale-up" / "scripts" / "preflight_process_scale_up.py"
        deployed = run(deployed_preflight, input_path)
        assert deployed.returncode == 0, deployed.stdout + deployed.stderr
        assert "ImportError" not in deployed.stderr and "Traceback" not in deployed.stderr, deployed.stderr
        deployed_probe = workspace / "probe-input.json"
        deployed_probe.write_text("{}", encoding="utf-8")
        probe = run(deployed_preflight, deployed_probe)
        assert probe.returncode != 0 and probe.stdout.startswith("HOLD:"), probe.stdout
        assert "ImportError" not in probe.stderr and "ModuleNotFoundError" not in probe.stderr, probe.stderr

    # The new skill is registered for installation with its real schema set.
    sys.path.insert(0, str(ROOT))
    from scripts.install_domain_skill import SKILLS

    assert "process-scale-up" in SKILLS, sorted(SKILLS)
    assert SKILLS["process-scale-up"] == ("common.schema.json", "process.schema.json", "optimization.schema.json"), SKILLS["process-scale-up"]

    print("PASS: WP-02 process window at PROCESS_WINDOW_DEFINED, scale-up gating, and design-freeze citation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
