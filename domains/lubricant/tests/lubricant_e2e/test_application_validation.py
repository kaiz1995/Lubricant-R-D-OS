"""End-to-end checks for the WP-06 APPLIED entry gate (application-validation).

Covers:
1. The APPLIED entry gate is fail-closed and asymmetric: only a fail-closed
   admissible PASS application record at stage VERIFIED gates entry into
   APPLIED; INCONCLUSIVE can never enter APPLIED (the headline rule), nor can
   FAIL or GAP.
2. Missing criteria are rejected: a GAP record (empty criteria) never advances.
3. Stage gating: a project at any stage other than VERIFIED is rejected.
4. Identity: the record's project_reference must match the gating request.
5. The gate consumes REAL built application artifacts (application-definition
   builder output), not hand-crafted stand-ins.
6. The skill is registered for install (now 18 keys), its deployed preflight
   runs standalone, and the single-source PASS rule (application_policy.py) is
   deployed beside it rather than re-implemented.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

APP_PREFLIGHT = ROOT / "skills/application-definition/scripts/preflight_application_definition.py"
APP_BUILDER = ROOT / "skills/application-definition/scripts/build_application_artifact.py"
GATE_PREFLIGHT = ROOT / "skills/application-validation/scripts/preflight_application_validation.py"


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


def gate_record(application_path: Path, project_reference: str = "WGO-001", current_stage: str = "VERIFIED") -> dict:
    return {
        "application_validation": {
            "project_reference": project_reference,
            "current_stage": current_stage,
            "application": read_json(application_path),
        }
    }


def gate(application_path: Path, **overrides) -> subprocess.CompletedProcess:
    """Run the deployed-or-pack preflight on one gating request."""
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "gate-input.json"
        write_json(path, gate_record(application_path, **overrides))
        return run(GATE_PREFLIGHT, path)


def application_input(result: str = "PASS") -> dict:
    return {
        "application": {
            "application_id": "APP-WGO-001",
            "project_reference": "WGO-001",
            "formula_reference": "FORMULA-WGO-001",
            "process_window_reference": "PROCESS-WINDOW:PW-WGO-001",
            "bench_references": ["BENCH-SZ-01"],
            "acceptance_criteria": [{
                "criterion_id": "C-1", "statement": "Leakage below limit at rated load.",
                "threshold": 1.0, "operator": "<=", "unit": "mL",
                "source": "Synthetic application spec", "evidence_id": "EV-APP-001", "status": "OBSERVED",
            }],
            "result": result,
            "counterexamples": [],
            "life_claim_boundary": {
                "claim_scope": "10-year service life at rated load", "status": "OBSERVED",
                "validated_conditions": [{
                    "condition_id": "LC-1", "parameter": "temperature",
                    "lower_bound": 40, "upper_bound": 100, "unit": "degC",
                }],
                "extrapolation_basis": "Synthetic bench extrapolation", "evidence_reference": "EV-APP-001",
            },
            "source": "Synthetic application spec",
            "evidence_id": "EV-APP-001",
            "evidence_scope": "SYNTHETIC",
            "evidence": [{
                "evidence_id": "EV-APP-001",
                "statement": "Synthetic application criteria supplied for contract validation only; not a field, life, or release conclusion.",
                "source": "Synthetic application fixture",
                "status": "ASSUMED",
            }],
        }
    }


def build_application(inputs: Path, artifacts: Path, name: str, result: str) -> Path:
    """Build a REAL application artifact through the producing skill."""
    input_path = inputs / f"application-{name}.json"
    write_json(input_path, application_input(result))
    run_ok(APP_PREFLIGHT, input_path)
    artifact_path = artifacts / f"application-{name}.json"
    run_ok(APP_BUILDER, input_path, artifact_path)
    assert read_json(artifact_path)["stage"] == "APPLIED", read_json(artifact_path)["stage"]
    return artifact_path


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        inputs, artifacts = workspace / "inputs", workspace / "artifacts"
        inputs.mkdir()
        artifacts.mkdir()

        pass_artifact = build_application(inputs, artifacts, "pass", "PASS")
        inconclusive_artifact = build_application(inputs, artifacts, "inconclusive", "INCONCLUSIVE")
        fail_artifact = build_application(inputs, artifacts, "fail", "FAIL")
        gap_artifact = build_application(inputs, artifacts, "gap", "GAP")

        # 1. A PASS record at VERIFIED gates entry into APPLIED.
        allowed = gate(pass_artifact)
        assert allowed.returncode == 0, allowed.stdout + allowed.stderr
        assert allowed.stdout.startswith("READY:"), allowed.stdout
        assert "APPLIED" in allowed.stdout, allowed.stdout

        # 2. The headline rule: INCONCLUSIVE 不得进入 APPLIED.
        blocked_inconclusive = gate(inconclusive_artifact)
        assert blocked_inconclusive.returncode != 0, blocked_inconclusive.stdout
        assert "INCONCLUSIVE cannot enter APPLIED" in blocked_inconclusive.stdout, blocked_inconclusive.stdout

        # 3. FAIL and GAP verdicts are blocked as well.
        blocked_fail = gate(fail_artifact)
        assert blocked_fail.returncode != 0 and "must be PASS to enter APPLIED (got FAIL)" in blocked_fail.stdout, blocked_fail.stdout
        blocked_gap = gate(gap_artifact)
        assert blocked_gap.returncode != 0 and "must be PASS to enter APPLIED (got GAP)" in blocked_gap.stdout, blocked_gap.stdout

        # 4. Stage gating: only VERIFIED may be applied.
        wrong_stage = gate(pass_artifact, current_stage="OPTIMIZED")
        assert wrong_stage.returncode != 0 and "current_stage must be VERIFIED" in wrong_stage.stdout, wrong_stage.stdout
        wrong_stage_applied = gate(pass_artifact, current_stage="APPLIED")
        assert wrong_stage_applied.returncode != 0 and "current_stage must be VERIFIED" in wrong_stage_applied.stdout, wrong_stage_applied.stdout

        # 5. Identity: the record must belong to the gated project.
        mismatched = gate(pass_artifact, project_reference="WGO-999")
        assert mismatched.returncode != 0 and "must match the gated project_reference" in mismatched.stdout, mismatched.stdout

        # 6. Fail-closed on missing criteria: an empty criteria list can only carry
        #    result GAP (rejected at the producing skill otherwise), and a GAP
        #    record never advances (already proven by 3's blocked_gap).
        gap_record = read_json(gap_artifact)
        assert gap_record["result"] == "GAP"
        empty_criteria = application_input(result="PASS")
        empty_criteria["application"]["acceptance_criteria"] = []
        empty_criteria["application"]["result"] = "GAP"
        empty_criteria_path = inputs / "application-empty-criteria.json"
        write_json(empty_criteria_path, empty_criteria)
        run_ok(APP_PREFLIGHT, empty_criteria_path)
        empty_artifact = artifacts / "application-empty-criteria.json"
        run_ok(APP_BUILDER, empty_criteria_path, empty_artifact)
        blocked_empty = gate(empty_artifact)
        assert blocked_empty.returncode != 0 and "must be PASS to enter APPLIED (got GAP)" in blocked_empty.stdout, blocked_empty.stdout

        # 7. Installation: 18 keys, real schema set, deployed preflight standalone,
        #    and the single-source PASS rule is deployed beside the scripts.
        sys.path.insert(0, str(ROOT))
        from integrations.open_science import install_skill
        from scripts.install_domain_skill import SKILLS, contracts_for, shared_modules_for

        assert len(SKILLS) == 19, sorted(SKILLS)
        assert SKILLS["application-validation"] == ("common.schema.json", "application.schema.json"), SKILLS["application-validation"]

        deploy_ws = workspace / "deploy"
        deploy_target = deploy_ws / ".opencode" / "skills"
        deploy_target.mkdir(parents=True)
        install_skill(
            ROOT / "skills" / "application-validation", ROOT / "schemas", SKILLS["application-validation"],
            deploy_target, workspace_root=deploy_ws,
            shared_modules=shared_modules_for("application-validation"),
            contract_files=contracts_for("application-validation"),
        )
        deployed_policy = deploy_target / "application-validation" / "scripts" / "application_policy.py"
        assert deployed_policy.is_file(), deployed_policy
        deployed_preflight = deploy_target / "application-validation" / "scripts" / "preflight_application_validation.py"
        deployed = run(deployed_preflight, pass_artifact)
        assert deployed.returncode != 0, deployed.stdout + deployed.stderr  # standalone preflight needs the gate wrapper...
        assert "Traceback" not in deployed.stderr and "ImportError" not in deployed.stderr and "ModuleNotFoundError" not in deployed.stderr, deployed.stderr
        with tempfile.TemporaryDirectory() as wrap:
            wrapped = Path(wrap) / "gate-input.json"
            write_json(wrapped, gate_record(pass_artifact))
            deployed_ok = run(deployed_preflight, wrapped)
            assert deployed_ok.returncode == 0 and deployed_ok.stdout.startswith("READY:"), deployed_ok.stdout + deployed_ok.stderr
            probe = Path(wrap) / "probe.json"
            write_json(probe, {})
            probe_result = run(deployed_preflight, probe)
            assert probe_result.returncode != 0 and probe_result.stdout.startswith("HOLD:"), probe_result.stdout
            assert "ModuleNotFoundError" not in probe_result.stderr, probe_result.stderr

        # 8. State-machine coherence of the gate output: the READY verdict
        #    corresponds to exactly the legal GO step VERIFIED -> APPLIED and the
        #    only FREEZE entry APPLIED -> FROZEN.
        import importlib.util
        spec = importlib.util.spec_from_file_location("vsm", ROOT / "scripts/validate_state_machine.py")
        vsm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vsm)

        def state(stage: str, **overrides) -> dict:
            value = {
                "project_id": "WGO-001", "stage": stage, "status": "ACTIVE", "version": 5,
                "decision_question": "Does application validation confirm the verified result?",
                "evidence_scope": "PHYSICAL", "evidence": ["E-APP-001"],
            }
            value.update(overrides)
            return value

        go = {"kind": "GO", "gate_status": "GO", "project_type": "NEW_PRODUCT", "before": state("VERIFIED"), "after": state("APPLIED")}
        assert vsm.validate(go) is None, vsm.validate(go)
        freeze = {
            "kind": "FREEZE", "gate_status": "FREEZE",
            # WP-08: freezing also requires a named technical_reviewer on the after state.
            "before": state("APPLIED"), "after": state("FROZEN", status="FROZEN", technical_reviewer="Lead tribologist"),
            "freeze_record": {"reason": "applied", "evidence_package": ["E-APP-001"]},
        }
        assert vsm.validate(freeze) is None, vsm.validate(freeze)
        skipped = {
            "kind": "FREEZE", "gate_status": "FREEZE",
            "before": state("VERIFIED"), "after": state("FROZEN", status="FROZEN"),
            "freeze_record": {"reason": "verified only", "evidence_package": ["E-APP-001"]},
        }
        assert vsm.validate(skipped) == "FREEZE requires APPLIED to FROZEN", vsm.validate(skipped)

    print("PASS: WP-06 APPLIED entry gate (INCONCLUSIVE never advances; fail-closed PASS rule)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
