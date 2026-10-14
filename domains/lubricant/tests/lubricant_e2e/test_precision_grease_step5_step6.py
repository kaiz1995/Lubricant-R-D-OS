"""End-to-end checks for outer-loop steps 5-6 on the PRECISION_GREASE_DEV route.

Covers:
1. Step 5 (test-method qualification): the three sub-steps are SERIAL, the two
   computable metrics must be ENGINE-computed, and the independent new batch
   check must pass. The plan's negative cases N2 / N3 / N4 are asserted by their
   exact HOLD text, plus an extra case for the fresh-batch rule.
2. Step 6 (design space): material references resolve to material objects, the
   baseline process is declared, every material-bearing variable carries its
   material role, and the in-situ reaction semantics reject a generated product
   marked as a charged input (the plan's negative case N6).
3. The grease process step vocabulary accepts the four appended steps and still
   rejects an unknown one.
4. The six oil routes are untouched: the same fixtures and policy entry points
   produce exactly their previous outcome.
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
FIXTURES = ROOT / "fixtures" / "precision-grease"
GREASE_PROJECT_TYPE = "PRECISION_GREASE_DEV"

TM_SCRIPTS = ROOT / "skills/test-method-qualification/scripts"
FD_SCRIPTS = ROOT / "skills/formulation-design/scripts"
PD_SCRIPTS = ROOT / "skills/process-definition/scripts"
CONSTRAINT_ROLE = ROOT / "scripts/constraint_role.py"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
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


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_method_preflight() -> Path:
    return TM_SCRIPTS / "preflight_test_method.py"


def test_method_builder() -> Path:
    return TM_SCRIPTS / "build_test_method_artifact.py"


def test_method_validator() -> Path:
    return TM_SCRIPTS / "validate_test_method_artifact.py"


def formulation_preflight() -> Path:
    return FD_SCRIPTS / "preflight_formulation_design.py"


def formulation_builder() -> Path:
    return FD_SCRIPTS / "build_design_space_artifact.py"


def formulation_validator() -> Path:
    return FD_SCRIPTS / "validate_design_space_artifact.py"


def process_preflight() -> Path:
    return PD_SCRIPTS / "preflight_process_definition.py"


def step5_checks() -> None:
    """Step 5: the serial qualification pipeline and the engine requirement."""
    valid = FIXTURES / "test-method-valid-input.json"
    run_ok(test_method_preflight(), valid)

    # N2: role D with DISCRIMINATION but no REPEATABILITY -> HOLD.
    n2 = run(test_method_preflight(), FIXTURES / "test-method-invalid-no-repeatability.json")
    assert n2.returncode == 1, n2.stdout
    assert "role D requires REPEATABILITY" in n2.stdout, n2.stdout

    # N3: discrimination recorded while repeatability has not passed -> HOLD.
    n3 = run(test_method_preflight(), FIXTURES / "test-method-invalid-discrimination-before-repeatability.json")
    assert n3.returncode == 1, n3.stdout
    assert "repeatability must pass before discrimination" in n3.stdout, n3.stdout

    # N4: a hand-entered discrimination figure -> HOLD.
    n4 = run(test_method_preflight(), FIXTURES / "test-method-invalid-manual-discrimination.json")
    assert n4.returncode == 1, n4.stdout
    assert "discrimination must be computed by the engine" in n4.stdout, n4.stdout

    # The independent new batch check may not be skipped or failed.
    n5 = run(test_method_preflight(), FIXTURES / "test-method-invalid-independent-batch-not-pass.json")
    assert n5.returncode == 1, n5.stdout
    assert "independent_batch must be PASS" in n5.stdout, n5.stdout

    # The whole pipeline is mandatory on this route.
    n6 = run(test_method_preflight(), FIXTURES / "test-method-invalid-missing-pipeline.json")
    assert n6.returncode == 1, n6.stdout
    assert "qualification_pipeline is required on the PRECISION_GREASE_DEV route" in n6.stdout, n6.stdout

    # I-1 (E3=B): the dossier path is a HARD requirement, not an optional extra.
    # A bare reference id with no readable dossier beside the input is exactly the
    # no-Known-Bad case this step must refuse, so a workspace holding every other
    # upstream artifact but NOT reference-material.json is held at the dossier rule
    # (not at an earlier missing-input rule).
    with tempfile.TemporaryDirectory() as temporary:
        bare = Path(temporary)
        for name in (
            "project-active.json", "challenge-defined.json", "failure-ctq-defined.json",
            "test-method-valid-input.json",
        ):
            shutil.copyfile(FIXTURES / name, bare / name)
        missing_dossier = run(test_method_preflight(), bare / "test-method-valid-input.json")
        assert missing_dossier.returncode == 1, missing_dossier.stdout
        assert (
            "reference_material_artifact is required on the PRECISION_GREASE_DEV route"
            in missing_dossier.stdout
        ), missing_dossier.stdout

    # The valid grease input builds and validates, and carries the pipeline through.
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        for name in (
            "project-active.json", "challenge-defined.json", "failure-ctq-defined.json",
            "test-method-valid-input.json", "test-method-valid-input-with-dossier.json",
            "test-method-invalid-unresolved-reference.json", "reference-material.json",
            "reference-material-unresolved.json",
        ):
            shutil.copyfile(FIXTURES / name, workspace / name)

        # A supplied dossier is read and checked against the recorded reference id.
        dossier_run = run(test_method_preflight(), workspace / "test-method-valid-input-with-dossier.json")
        assert dossier_run.returncode == 0, dossier_run.stdout

        # A dossier whose Known Bad is not RESOLVED may not serve as the ruler: the
        # discrimination evidence is incomplete and that state must travel onward.
        unresolved_run = run(test_method_preflight(), workspace / "test-method-invalid-unresolved-reference.json")
        assert unresolved_run.returncode == 1, unresolved_run.stdout
        assert "DISCRIMINATION_EVIDENCE_INCOMPLETE" in unresolved_run.stdout, unresolved_run.stdout

        output = workspace / "test_method.json"
        run_ok(test_method_builder(), workspace / "test-method-valid-input.json", output)
        run_ok(test_method_validator(), output)
        artifact = read_json(output)
        assert artifact["stage"] == "TEST_METHODS_QUALIFIED"
        assert artifact["decision"] == "GO", artifact["decision"]
        assert artifact["qualification_pipeline"]["repeatability"]["status"] == "PASS"
        assert artifact["reference_material_reference"] == "REF-PGD-001"
        assert artifact["qualification_metrics"][0]["computed_by"] == "ENGINE"

        # The validator re-checks the serial order on the built artifact itself.
        broken = read_json(output)
        broken["qualification_pipeline"]["repeatability"]["status"] = "FAIL"
        broken_path = workspace / "test-method-broken.json"
        write_json(broken_path, broken)
        rejected = run(test_method_validator(), broken_path)
        assert rejected.returncode == 1, rejected.stdout
        assert "repeatability must pass before discrimination" in rejected.stdout, rejected.stdout
    print("PASS: step 5 pipeline is serial, engine-computed, and re-verified on a fresh batch")


def step6_checks() -> None:
    """Step 6: material references, baseline process, and in-situ semantics."""
    valid = FIXTURES / "design-space-valid-input.json"
    run_ok(formulation_preflight(), valid)

    # N6: the thickener feedstock marked as a charged input is rejected.
    n6 = run(formulation_preflight(), FIXTURES / "design-space-invalid-reaction-product-as-input.json")
    assert n6.returncode == 1, n6.stdout
    assert "generated in situ by saponification" in n6.stdout, n6.stdout
    assert "REACTION_PRODUCT" in n6.stdout, n6.stdout

    # A bare name string is not a material record.
    bare = run(formulation_preflight(), FIXTURES / "design-space-invalid-material-name-string.json")
    assert bare.returncode == 1, bare.stdout
    assert "a bare name string is not a material record" in bare.stdout, bare.stdout

    # The referenced material_id must exist.
    unresolved = run(formulation_preflight(), FIXTURES / "design-space-invalid-unresolved-material.json")
    assert unresolved.returncode == 1, unresolved.stdout
    assert "does not resolve to a readable material record" in unresolved.stdout, unresolved.stdout

    # The fixed process baseline is mandatory: a changed process makes formula
    # comparison invalid.
    baseline = run(formulation_preflight(), FIXTURES / "design-space-invalid-missing-baseline-process.json")
    assert baseline.returncode == 1, baseline.stdout
    assert "baseline_process_reference is required on the PRECISION_GREASE_DEV route" in baseline.stdout, baseline.stdout

    # Every material-bearing variable declares whether it is a charge or a product.
    role = run(formulation_preflight(), FIXTURES / "design-space-invalid-missing-material-role.json")
    assert role.returncode == 1, role.stdout
    assert "role is required on the PRECISION_GREASE_DEV route" in role.stdout, role.stdout

    # Both the legacy string form and the object form of constraints are accepted.
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        for name in (
            "project-active.json", "challenge-defined.json", "failure-ctq-defined.json",
            "test-method-qualified.json", "material-base-oil.json", "material-thickener-raw.json",
            "design-space-valid-input.json",
        ):
            shutil.copyfile(FIXTURES / name, workspace / name)
        output = workspace / "design_space.json"
        run_ok(formulation_builder(), workspace / "design-space-valid-input.json", output)
        run_ok(formulation_validator(), output)
        artifact = read_json(output)
        assert artifact["stage"] == "DESIGN_SPACE_DEFINED"
        assert artifact["baseline_process_reference"] == "PROC-PG-B1-001"
        assert len(artifact["feasibility_regions"]) == 2
        assert isinstance(artifact["constraints"][0], dict) and artifact["constraints"][-1] == "Use only the supplied variable bounds."
        roles = {v["variable_id"]: v.get("role") for v in artifact["variables"]}
        assert roles["VAR-SOAP-CONCENTRATION"] == "REACTION_PRODUCT", roles
        assert roles["VAR-BASE-OIL-FRACTION"] == "INPUT_MATERIAL", roles
        # A PROCESS_VARIABLE ranges over the kettle, not a material, so it is exempt
        # from the material-reference and material-role requirements.
        assert roles["VAR-SOAP-HOLD-TIME"] is None, roles
        # The validator re-checks material resolution against the artifact's own
        # directory, so a workspace holding the records validates.
        unresolved_artifact = read_json(output)
        unresolved_artifact["variables"][0]["material_reference"] = "MAT-PG-MISSING"
        unresolved_path = workspace / "design-space-unresolved.json"
        write_json(unresolved_path, unresolved_artifact)
        rejected = run(formulation_validator(), unresolved_path)
        assert rejected.returncode == 1, rejected.stdout
        assert "does not resolve to a readable material record" in rejected.stdout, rejected.stdout
    print("PASS: step 6 material references, baseline process, and in-situ reaction semantics enforced")


def constraint_role_checks() -> None:
    """The shared resolver: the three original derivations and the new product rule."""
    shared = load_module(CONSTRAINT_ROLE, "pg_constraint_role")
    for variable_type, expected in (
        ("FORMULATION_VARIABLE", "MIXTURE_CLOSED"),
        ("MATERIAL_FAMILY", "INDEPENDENT"),
        ("PROCESS_VARIABLE", "INDEPENDENT"),
    ):
        assert shared.derive_constraint_role(variable_type) == expected
        assert shared.resolve_constraint_role(variable_type) == expected
        assert shared.derive_variable_constraint_role(variable_type) == expected
        assert shared.resolve_variable_constraint_role(variable_type) == expected

    # A reaction product never enters the mixture closure: the derived role is
    # INDEPENDENT, and an explicit MIXTURE_CLOSED declaration is refused.
    for variable_type in ("FORMULATION_VARIABLE", "MATERIAL_FAMILY", "PROCESS_VARIABLE"):
        derived = shared.resolve_variable_constraint_role(variable_type, None, "REACTION_PRODUCT")
        assert derived != "MIXTURE_CLOSED", (variable_type, derived)
        assert derived == "INDEPENDENT", (variable_type, derived)
    try:
        shared.resolve_variable_constraint_role("FORMULATION_VARIABLE", "MIXTURE_CLOSED", "REACTION_PRODUCT")
    except shared.ConstraintRoleError as error:
        assert "REACTION_PRODUCT" in str(error), error
    else:
        raise AssertionError("REACTION_PRODUCT accepted an explicit MIXTURE_CLOSED declaration")

    # A charge keeps the type-derived role.
    assert shared.resolve_variable_constraint_role("FORMULATION_VARIABLE", None, "INPUT_MATERIAL") == "MIXTURE_CLOSED"
    assert shared.resolve_variable_constraint_role("FORMULATION_VARIABLE", "MIXTURE_CLOSED", "INPUT_MATERIAL") == "MIXTURE_CLOSED"

    # The original contradiction rule is unchanged.
    try:
        shared.resolve_constraint_role("MATERIAL_FAMILY", "MIXTURE_CLOSED")
    except shared.ConstraintRoleError as error:
        assert "contradicts variable_type MATERIAL_FAMILY" in str(error), error
    else:
        raise AssertionError("a contradictory declaration was accepted")
    print("PASS: shared constraint_role resolver keeps its three derivations and never closes a reaction product")


def process_checks() -> None:
    """Step 6 / step 15: the appended grease step types are accepted."""
    valid = FIXTURES / "process-valid-input.json"
    run_ok(process_preflight(), valid)
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        for name in ("design-space-artifact.json", "process-valid-input.json"):
            shutil.copyfile(FIXTURES / name, workspace / name)
        output = workspace / "process.json"
        run_ok(PD_SCRIPTS / "build_process_artifact.py", workspace / "process-valid-input.json", output)
        run_ok(PD_SCRIPTS / "validate_process_artifact.py", output)
        artifact = read_json(output)
        step_types = [step["step_type"] for step in artifact["process_step"]]
        for appended in ("SOAP_HOLD", "DILUTION_CURVE", "RIPENING", "FILLING_TEMPERATURE"):
            assert appended in step_types, step_types
        assert len(step_types) == 12

        # An unknown step type is still rejected, and so is an existing one that is
        # merely misspelt - the appended values did not loosen the vocabulary.
        broken = read_json(output)
        broken["process_step"][1]["step_type"] = "SOAK"
        broken_path = workspace / "process-unknown-step.json"
        write_json(broken_path, broken)
        rejected = run(PD_SCRIPTS / "validate_process_artifact.py", broken_path)
        assert rejected.returncode == 1, rejected.stdout
        assert "step_type" in rejected.stdout, rejected.stdout
    print("PASS: grease step vocabulary accepts the four appended steps and still rejects an unknown one")


def oil_route_checks() -> None:
    """The six oil routes keep today's behaviour: the new rules are gated."""
    policy = load_module(TM_SCRIPTS / "qualification_policy.py", "pg_qualification_policy")

    # The exact pre-change rule set, evaluated without a grease project type.
    oil_method = {
        "role": ["D"],
        "qualification_metrics": [{"metric": "DISCRIMINATION", "measurement": {}}],
    }
    assert policy.role_metric_errors(oil_method, None) == [], policy.role_metric_errors(oil_method, None)
    assert policy.role_metric_errors(oil_method, "COST_DOWN") == []
    # REPEATABILITY becomes mandatory only for the grease route.
    assert policy.role_metric_errors(oil_method, GREASE_PROJECT_TYPE) == ["role D requires REPEATABILITY"]
    # The serial pipeline and the ENGINE requirement are grease-only.
    assert policy.grease_qualification_errors({"role": ["D"], "qualification_metrics": []}) != []
    assert policy.pipeline_errors({"qualification_pipeline": {}}) != []
    assert policy.is_grease_route("COST_DOWN") is False and policy.is_grease_route(None) is False
    assert policy.required_fields_for("COST_DOWN") == ()

    # The oil-route role rules are unchanged for C / D / P.
    assert policy.role_metric_errors({"role": ["P"], "qualification_metrics": []}, None) == [
        "role P requires MECHANISM_RELEVANCE",
        "role P requires FIELD_RELEVANCE or BENCHMARK_RANKING",
    ]
    assert policy.role_metric_errors({"role": ["X"], "qualification_metrics": []}, GREASE_PROJECT_TYPE) == ["role is invalid"]

    # The oil-route fixtures keep their recorded exit codes. Two of them are
    # artifact-shaped (they lack the input wrapper), so a preflight rejection is
    # their expected outcome both before and after this change.
    oil_fixtures = ROOT / "fixtures" / "test-method"
    for name, expected in (
        ("valid-input.synthetic.json", 0),
        ("valid-unverified-provenance.synthetic.json", 0),
        ("invalid-synthetic-qualified.json", 1),
        ("invalid-c-only-qualified.json", 1),
        ("invalid-pending-go.json", 1),
        ("invalid-role-x.json", 1),
        ("invalid-missing-source.json", 1),
        ("invalid-cross-stage-decision.json", 1),
    ):
        result = run(test_method_preflight(), oil_fixtures / name)
        assert result.returncode == expected, f"{name}: {result.returncode}\n{result.stdout}"

    # The oil-route formulation fixtures keep their recorded HOLD text.
    oil_formulation = ROOT / "fixtures" / "formulation-design"
    result = run(formulation_preflight(), oil_formulation / "valid-input.synthetic.json")
    assert result.returncode == 1, result.stdout
    hold_lines = [line for line in result.stdout.splitlines() if line.startswith("HOLD:")]
    assert hold_lines == [
        "HOLD: missing or invalid: test_method_artifact must have decision GO, "
        "test_method_artifact must have qualification_status QUALIFIED; no artifact generated"
    ], hold_lines
    # No grease note leaks into an oil-route run.
    assert not any("MIXTURE_CLOSURE_INPUTS" in line for line in result.stdout.splitlines()), result.stdout
    print("PASS: oil routes keep their pre-change qualification and design-space behaviour")


def main() -> int:
    step5_checks()
    step6_checks()
    constraint_role_checks()
    process_checks()
    oil_route_checks()
    print("PASS: PRECISION_GREASE_DEV steps 5-6 (qualification pipeline + design space) end to end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
