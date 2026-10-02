"""End-to-end checks for the WP-04a DOE bridge (process axis -> DOE -> artifact).

Acceptance items exercised here (plan §WP-04a):
  2. A PROCESS_ROBUSTNESS-style design space on a process axis flows through
     preflight -> build -> validate into an EXPERIMENT_DESIGNED artifact, and the
     same axis drives a pure-process FACTORIAL_DOE_DESIGN run through the engine.
  5. Bridge counter-examples are rejected by name: a MIXTURE_CLOSED variable
     placed in a factor family (and the converse), plus a stray mixture_total.
  6. Default derivation agrees with WP-01: a design space that carries no
     explicit constraint_role still routes FORMULATION_VARIABLE -> components and
     PROCESS_VARIABLE -> factors, resolved by the *shared* constraint_role module.

The state-machine contract and route_step are deliberately NOT touched here; that
surface belongs to WP-13.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures/doe-design"
SCRIPTS = ROOT / "skills/doe-design/scripts"

PREFLIGHT = SCRIPTS / "preflight_doe_design.py"
BUILDER = SCRIPTS / "build_experiment_design_artifact.py"
VALIDATOR = SCRIPTS / "validate_experiment_design_artifact.py"
RUN_COMPUTE = SCRIPTS / "run_compute.py"
CONSTRAINT_ROLE = ROOT / "scripts/constraint_role.py"

PROJECT_ID = "WGO-DOE-001"
SIMULATED = "SIMULATED_PHYSICAL_CONTRACT_TEST_NOT_EVIDENCE"

# WP-04b: every factor/process/sequential family request must declare the resource
# envelope that bounds its next bench round. The mixture family must not carry one.
RESOURCE_ENVELOPE = {
    "bench_slots": 2, "lot_capacity": 16, "cycle_days": 3.0,
    "cost_cap": 0.0, "external_test_lead_time": 0.0,
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: Path, *arguments: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", script.name, *map(str, arguments)],
        cwd=script.parent, capture_output=True, text=True,
    )


def measurement(value: float, unit: str) -> dict:
    return {
        "value": value, "unit": unit, "source": SIMULATED, "method_version": "design-v1",
        "material_batch": "not_applicable", "formula_version": "not_applicable",
    }


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def process_design_space() -> dict:
    """A design space with a process axis and a mixture variable, role left implicit."""
    base = read_json(FIXTURES / "design-space-defined.json")
    base["scope"] = "Synthetic PROCESS_ROBUSTNESS design space: process axis plus fixed base blend."
    base["result"] = "Synthetic process-axis design space recorded."
    base["variables"] = [
        {
            "variable_id": "PROC-TEMP", "variable_type": "PROCESS_VARIABLE",
            "lower_bound": measurement(90, "degC"), "upper_bound": measurement(110, "degC"),
            "constraint_rationale": "Synthetic saponification temperature window.",
        },
        {
            "variable_id": "PROC-VACUUM", "variable_type": "PROCESS_VARIABLE",
            "lower_bound": measurement(1, "kPa"), "upper_bound": measurement(10, "kPa"),
            "constraint_rationale": "Synthetic vacuum deaeration window.",
        },
        {
            "variable_id": "MIX-BASE", "variable_type": "FORMULATION_VARIABLE",
            "lower_bound": measurement(0.6, "wt%"), "upper_bound": measurement(0.9, "wt%"),
            "constraint_rationale": "Synthetic closed-mixture base share.",
        },
    ]
    return base


def experiment_request(family: str, factor_references: list[str], *, mixture_total: dict | None = None,
                       design_id: str = "DOE-PR-001",
                       resource_envelope: dict | None = None) -> dict:
    request = {
        "experiment_design_id": design_id,
        "factor_references": factor_references,
        "design": {
            "family": family,
            "rationale": "Synthetic PROCESS_ROBUSTNESS planning request.",
            "effects_to_estimate": ["main effect of each varying process factor"],
        },
        "run_plan": {
            "target_count": 8, "replicate_count": 1, "center_point_count": 0,
            "randomized": False, "point_generation": "PHASE4_DETERMINISTIC_ENGINE",
        },
        "responses": [{
            "ctq_reference": "CTQ-DOE-001", "test_method_reference": "TM-DOE-001",
            "role": "OPTIMIZATION_RESPONSE",
        }],
        "guardrails": ["Remain within DS-DOE-001."],
        "expected_information_value": {
            "classification": "RECOMMENDED", "decision_relevance": "Synthetic.",
            "expected_information_gain": "Synthetic.", "cost": "Synthetic.",
            "duration": "Synthetic.", "redundancy": "Synthetic.",
        },
        "evidence": [{
            "evidence_id": "E-ED-901", "statement": "Synthetic supplied planning evidence.",
            "source": "synthetic", "status": "ASSUMED",
        }],
    }
    if mixture_total is not None:
        request["mixture_total"] = mixture_total
    if resource_envelope is not None:
        # WP-04b: a factor-family request must bound its next round; the mixture family
        # must not carry one at all (see the conditional rule in experiment_design.schema.json).
        request["resource_envelope"] = resource_envelope
    return request


def input_envelope(workspace: Path, design_space: Path, request: dict) -> Path:
    payload = {
        "project_artifact": str(workspace / "project-active.json"),
        "challenge_artifact": str(workspace / "challenge-defined.json"),
        "failure_ctq_artifact": str(workspace / "failure-ctq-defined.json"),
        "test_method_artifact": str(workspace / "test-method-qualified.json"),
        "design_space_artifact": str(design_space),
        "experiment_design": request,
    }
    path = workspace / "input.json"
    write_json(path, payload)
    return path


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        for name in ("project-active.json", "challenge-defined.json", "failure-ctq-defined.json", "test-method-qualified.json"):
            shutil.copyfile(FIXTURES / name, workspace / name)

        design_space = workspace / "design-space.json"
        write_json(design_space, process_design_space())

        # --- 6. Default derivation must agree with the shared WP-01 resolver. ---
        _ensure_script_path()
        preflight = load_module(PREFLIGHT, "wp04a_preflight")
        shared = load_module(CONSTRAINT_ROLE, "wp04a_constraint_role")
        roles, role_errors = preflight.resolved_variable_roles(process_design_space())
        assert role_errors == [], role_errors
        assert roles == {"PROC-TEMP": "INDEPENDENT", "PROC-VACUUM": "INDEPENDENT", "MIX-BASE": "MIXTURE_CLOSED"}, roles
        for variable in process_design_space()["variables"]:
            assert roles[variable["variable_id"]] == shared.resolve_constraint_role(variable["variable_type"], None)
        print("PASS: implicit constraint_role derivation agrees with the shared WP-01 resolver")

        # --- 2. Factorial family (process axis) is READY and builds an artifact. ---
        request = experiment_request("FRACTIONAL_FACTORIAL", ["PROC-TEMP", "PROC-VACUUM"],
                                     resource_envelope=RESOURCE_ENVELOPE)
        envelope = input_envelope(workspace, design_space, request)
        preflight_result = run(PREFLIGHT, envelope)
        assert preflight_result.returncode == 0, preflight_result.stdout + preflight_result.stderr
        assert preflight_result.stdout.startswith("READY:"), preflight_result.stdout

        artifact_path = workspace / "experiment-design.json"
        build_result = run(BUILDER, envelope, artifact_path)
        assert build_result.returncode == 0, build_result.stdout + build_result.stderr
        artifact = read_json(artifact_path)
        assert artifact["stage"] == "EXPERIMENT_DESIGNED", artifact["stage"]
        assert artifact["design"]["family"] == "FRACTIONAL_FACTORIAL"
        assert artifact["decision"] == "GO", artifact["decision"]
        assert "mixture_total" not in artifact, "a factor family must not carry a mixture_total"
        validate_result = run(VALIDATOR, artifact_path)
        assert validate_result.returncode == 0, validate_result.stdout + validate_result.stderr
        assert artifact["resource_envelope"] == RESOURCE_ENVELOPE, artifact.get("resource_envelope")
        print("PASS: process-axis design space -> EXPERIMENT_DESIGNED artifact (factor family)")

        # --- WP-04b conditional rule: a factor family without an envelope is refused, while
        #     the mixture family fixtures stay untouched (backward-compatibility decision). ---
        missing = experiment_request("FRACTIONAL_FACTORIAL", ["PROC-TEMP", "PROC-VACUUM"])
        result = run(PREFLIGHT, input_envelope(workspace, design_space, missing))
        assert result.returncode != 0 and "HOLD" in result.stdout, result.stdout
        assert "resource_envelope" in result.stdout, result.stdout
        print("PASS: factor family without a resource envelope is refused by name")

        # --- The combined family carries BOTH the frozen formula and the envelope: the
        #     engine consumes the envelope on the MIXTURE_PROCESS input type as well. ---
        combined = experiment_request(
            "MIXTURE_PROCESS", ["PROC-TEMP", "MIX-BASE"],
            mixture_total={"value": 0.8, "unit": "wt%", "source": SIMULATED, "method_version": "design-v1",
                           "material_batch": "not_applicable", "formula_version": "not_applicable"},
            resource_envelope=RESOURCE_ENVELOPE, design_id="DOE-PR-002",
        )
        envelope = input_envelope(workspace, design_space, combined)
        preflight_result = run(PREFLIGHT, envelope)
        assert preflight_result.returncode == 0 and preflight_result.stdout.startswith("READY:"), preflight_result.stdout
        combined_path = workspace / "experiment-design-combined.json"
        build_result = run(BUILDER, envelope, combined_path)
        assert build_result.returncode == 0, build_result.stdout + build_result.stderr
        combined_artifact = read_json(combined_path)
        assert combined_artifact["design"]["family"] == "MIXTURE_PROCESS"
        assert combined_artifact["mixture_total"]["value"] == 0.8
        assert combined_artifact["resource_envelope"] == RESOURCE_ENVELOPE
        assert run(VALIDATOR, combined_path).returncode == 0
        print("PASS: combined family carries both mixture_total and resource_envelope")

        # --- 1. The same axis drives a pure-process FACTORIAL_DOE_DESIGN engine run. ---
        doe_input = {
            "evidence_scope": "SYNTHETIC",
            "input_type": "FACTORIAL_DOE_DESIGN",
            "design_type": "SPLIT_PLOT",
            "model_order": "LINEAR",
            "target_runs": 0,
            "design_space_reference": "DS-DOE-001",
            "whole_plot_replicates": 2,
            "factors": [
                {"factor_id": "PROC-KETTLE", "factor_type": "DISCRETE", "role": "WHOLE_PLOT", "levels": [1, 2]},
                {"factor_id": "PROC-TEMP", "factor_type": "CONTINUOUS", "role": "SUB_PLOT", "range": {"lower": 90, "upper": 110}, "unit": "degC"},
                {"factor_id": "PROC-VACUUM", "factor_type": "CONTINUOUS", "role": "SUB_PLOT", "range": {"lower": 1, "upper": 10}, "unit": "kPa"},
            ],
            "responses": [{"ctq_reference": "KV40", "test_method_reference": "ASTM D445", "role": "OPTIMIZATION_RESPONSE"}],
            "experiment_card": {
                "decision_question": "Which vessel/setting reproduces KV40?",
                "hypothesis": "Vessel change shifts the temperature/vacuum response.",
                "variables_note": "Process factors only; the formula is frozen separately.",
                "constraints_note": "Independent process bounds, no mixture closure.",
                "responses_note": "KV40 OPTIMIZATION_RESPONSE.",
                "doe_selection_reason": "Split-plot keeps the vessel effect in the whole plot.",
                "expected_information_value": "Whole/sub-plot errors stay separable.",
                "decision_rule": "Pick the reproducible vessel/setting pair.",
            },
        }
        compute_result = subprocess.run(
            [sys.executable, "-B", RUN_COMPUTE.name],
            cwd=RUN_COMPUTE.parent, input=json.dumps(doe_input, ensure_ascii=False), capture_output=True, text=True,
        )
        assert compute_result.returncode == 0, compute_result.stdout + compute_result.stderr
        compute_output = json.loads(compute_result.stdout)
        envelope_engine = compute_output["result"]
        assert envelope_engine["status"] == "OK", envelope_engine.get("rejection_reasons")
        assert envelope_engine["parameters"]["design_space_reference"] == "DS-DOE-001"
        assert all("whole_plot_index" in run_entry for run_entry in envelope_engine["result"]["runs"])
        assert {term["scope"] for term in envelope_engine["result"]["error_terms"]} == {"WHOLE_PLOT", "SUB_PLOT"}
        print("PASS: pure-process split-plot engine run behind the evidence-scope boundary")

        # --- 5a. MIXTURE_CLOSED variable in a factor family is rejected by name. ---
        mixed_request = experiment_request("FRACTIONAL_FACTORIAL", ["PROC-TEMP", "MIX-BASE"],
                                           resource_envelope=RESOURCE_ENVELOPE)
        result = run(PREFLIGHT, input_envelope(workspace, design_space, mixed_request))
        assert result.returncode != 0 and "HOLD" in result.stdout, result.stdout
        assert "MIX-BASE" in result.stdout and "belongs in DOE components" in result.stdout, result.stdout
        print("PASS: MIXTURE_CLOSED variable rejected from a factor family by name")

        # --- 5b. INDEPENDENT variable in a mixture family is rejected by name. ---
        misplaced = experiment_request(
            "CONSTRAINED_MIXTURE", ["PROC-TEMP", "PROC-VACUUM"],
            mixture_total={"value": 1.0, "unit": "wt%", "source": SIMULATED, "method_version": "design-v1",
                           "material_batch": "not_applicable", "formula_version": "not_applicable"},
        )
        result = run(PREFLIGHT, input_envelope(workspace, design_space, misplaced))
        assert result.returncode != 0 and "HOLD" in result.stdout, result.stdout
        assert "PROC-TEMP" in result.stdout and "belongs in DOE factors" in result.stdout, result.stdout
        print("PASS: INDEPENDENT variable rejected from a mixture family by name")

        # --- 5c. A stray mixture_total in a factor-only family is rejected. ---
        stray = experiment_request(
            "FRACTIONAL_FACTORIAL", ["PROC-TEMP", "PROC-VACUUM"],
            mixture_total={"value": 1.0, "unit": "wt%", "source": SIMULATED, "method_version": "design-v1",
                           "material_batch": "not_applicable", "formula_version": "not_applicable"},
            resource_envelope=RESOURCE_ENVELOPE,
        )
        result = run(PREFLIGHT, input_envelope(workspace, design_space, stray))
        assert result.returncode != 0 and "HOLD" in result.stdout, result.stdout
        assert "mixture_total must be absent" in result.stdout, result.stdout
        print("PASS: stray mixture_total rejected for a factor-only family")

        # --- The pre-existing mixture fixture still reads READY (non-regression). ---
        result = run(PREFLIGHT, FIXTURES / "valid-input.synthetic.json")
        assert result.returncode == 0 and result.stdout.startswith("READY:"), result.stdout
        print("PASS: legacy CONSTRAINED_MIXTURE fixture still READY")

    print("ALL PASS: WP-04a DOE bridge end to end")
    return 0


def _ensure_script_path() -> None:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))


if __name__ == "__main__":
    raise SystemExit(main())
