"""End-to-end checks for the WP-09 interface object (interface-definition).

Covers:
1. Schema inventory 19 -> 20 with interface.schema.json present, validate_schemas
   green (the arithmetic assertion itself lives in test_application_bench.py;
   this file re-runs the validator to prove the tree is green with the new
   schema).
2. The PASS verdict is fail-closed: a REAL built PASS interface record passes
   the full preflight -> build -> validate chain; an empty compatibility_evidence
   list forces verdict GAP (PASS with empty evidence is rejected at preflight,
   and the GAP record builds and validates cleanly).
3. Non-PASS / non-OBSERVED compatibility items block a PASS verdict: a FAIL
   observation, an ASSUMED observation, and a GAP evidence chain each keep the
   record at a non-PASS verdict.
4. COMPATIBILITY_PASSED is unsatisfiable without compatibility evidence
   (interface_policy.freeze_compatibility_errors, consumed on REAL built
   artifacts): a valid INTERFACE:<id> citation of a PASS record is clean; a
   non-INTERFACE reference, an unknown interface id, and a non-PASS verdict are
   each rejected with the pass blockers named.
5. failure_ctq.interface_failure_modes is an optional field that cites the
   interface artifact (schema-level positive and negative cases).
6. The skill is registered for install (17 -> 18 keys) and its deployed
   preflight runs standalone; the policy layer (not design_freeze.schema.json)
   owns the COMPATIBILITY_PASSED link while tests/test_r25_contracts.py is
   owned by the parallel WP-12.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]

IF_PREFLIGHT = ROOT / "skills/interface-definition/scripts/preflight_interface_definition.py"
IF_BUILDER = ROOT / "skills/interface-definition/scripts/build_interface_artifact.py"
IF_VALIDATOR = ROOT / "skills/interface-definition/scripts/validate_interface_artifact.py"


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


def interface_input(verdict: str = "PASS", compatibility_evidence: list | None = None) -> dict:
    return {
        "interface": {
            "interface_id": "IF-DLC-001",
            "project_reference": "WGO-001",
            "interface_type": "COATING_SUBSTRATE",
            "counterpart_a": {"role": "COATING", "designation": "DLC", "source": "supplier sheet DS-2026-09"},
            "counterpart_b": {"role": "SUBSTRATE", "designation": "GCr15", "source": "internal spec MS-001"},
            "coating": {
                "coating_system": "DLC",
                "coating_reference": "DLC-PARAM-SHEET-01",
                "supplier": "ACME Coatings",
                "supplier_batch_reference": "B-2026-09-01",
                "source": "supplier sheet DS-2026-09",
            },
            "compatibility_evidence": compatibility_evidence if compatibility_evidence is not None else [
                {
                    "compatibility_id": "CMP-001",
                    "method_reference": "TM-001",
                    "condition": "1.2 GPa contact, 80 C, 72 h grease immersion",
                    "result": "PASS",
                    "evidence_id": "EV-COMPAT-001",
                    "status": "OBSERVED",
                }
            ],
            "verdict": verdict,
            "source": "compatibility lab report CLR-2026-014",
            "evidence_id": "EV-IF-001",
            "evidence_scope": "SYNTHETIC",
            "evidence": [{
                "evidence_id": "EV-IF-001",
                "statement": "Synthetic compatibility record supplied for contract validation only; not a qualified release conclusion.",
                "source": "Synthetic interface fixture",
                "status": "ASSUMED",
            }],
        }
    }


def build_interface(inputs: Path, artifacts: Path, name: str, verdict: str, compatibility_evidence: list | None = None) -> Path:
    """Build a REAL interface artifact through the producing skill."""
    input_path = inputs / f"interface-{name}.json"
    write_json(input_path, interface_input(verdict, compatibility_evidence))
    result = run(IF_PREFLIGHT, input_path)
    assert result.returncode == 0, f"interface-{name}\n{result.stdout}{result.stderr}"
    artifact_path = artifacts / f"interface-{name}.json"
    built = run(IF_BUILDER, input_path, artifact_path)
    assert built.returncode == 0, f"interface-{name}\n{built.stdout}{built.stderr}"
    validated = run(IF_VALIDATOR, artifact_path)
    assert validated.returncode == 0, f"interface-{name}\n{validated.stdout}{validated.stderr}"
    artifact = read_json(artifact_path)
    assert artifact["stage"] == "DRAFT", artifact["stage"]
    assert artifact["verdict"] == verdict, artifact["verdict"]
    return artifact_path


def freeze_errors(policy, condition: dict, interfaces: dict) -> list[str]:
    return policy.freeze_compatibility_errors(condition, interfaces)


def main() -> int:
    # 1. validate_schemas green with the new schema in place (inventory arithmetic
    #    is asserted in test_application_bench.py; 19 -> 20 with interface).
    schema_names = sorted(path.name for path in (ROOT / "schemas").glob("*.schema.json"))
    assert "interface.schema.json" in schema_names, schema_names
    assert len(schema_names) == 20, (len(schema_names), schema_names)
    validated = subprocess.run(
        [sys.executable, "-B", "scripts/validate_schemas.py"], cwd=ROOT, capture_output=True, text=True
    )
    assert validated.returncode == 0, validated.stdout + validated.stderr

    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        inputs, artifacts = workspace / "inputs", workspace / "artifacts"
        inputs.mkdir()
        artifacts.mkdir()

        # 2. Positive case: a fully-provenanced PASS record passes the full chain.
        pass_artifact = build_interface(inputs, artifacts, "pass", "PASS")

        # 3. Fail-closed: empty compatibility evidence forces verdict GAP; PASS is
        #    rejected at preflight with the rule named, and the GAP record builds.
        empty_pass = inputs / "interface-empty-pass.json"
        write_json(empty_pass, interface_input("PASS", []))
        blocked = run(IF_PREFLIGHT, empty_pass)
        assert blocked.returncode != 0 and blocked.stdout.startswith("HOLD:"), blocked.stdout
        assert "verdict must be GAP when compatibility_evidence is empty" in blocked.stdout, blocked.stdout

        gap_artifact = build_interface(inputs, artifacts, "gap", "GAP", [])
        assert read_json(gap_artifact)["verdict"] == "GAP"

        # 4. Non-PASS / non-OBSERVED items block a PASS verdict.
        fail_item = [dict(interface_input()["interface"]["compatibility_evidence"][0], result="FAIL")]
        fail_pass = inputs / "interface-fail-item.json"
        write_json(fail_pass, interface_input("PASS", fail_item))
        blocked_fail = run(IF_PREFLIGHT, fail_pass)
        assert blocked_fail.returncode != 0 and "result must be PASS to claim PASS" in blocked_fail.stdout, blocked_fail.stdout

        assumed_item = [dict(interface_input()["interface"]["compatibility_evidence"][0], status="ASSUMED")]
        assumed_pass = inputs / "interface-assumed-item.json"
        write_json(assumed_pass, interface_input("PASS", assumed_item))
        blocked_assumed = run(IF_PREFLIGHT, assumed_pass)
        assert blocked_assumed.returncode != 0 and "status must be OBSERVED to claim PASS" in blocked_assumed.stdout, blocked_assumed.stdout

        gap_evidence = interface_input("PASS")
        gap_evidence["interface"]["evidence"][0]["status"] = "GAP"
        gap_evidence_path = inputs / "interface-gap-evidence.json"
        write_json(gap_evidence_path, gap_evidence)
        blocked_gap = run(IF_PREFLIGHT, gap_evidence_path)
        assert blocked_gap.returncode != 0 and "a PASS verdict is not allowed" in blocked_gap.stdout, blocked_gap.stdout

        # 5. COMPATIBILITY_PASSED is unsatisfiable without compatibility evidence,
        #    checked on REAL built artifacts (positive + three negatives).
        sys.path.insert(0, str(ROOT / "skills" / "interface-definition" / "scripts"))
        try:
            import interface_policy as policy
        finally:
            sys.path.pop(0)

        registry_interfaces = {
            "IF-DLC-001": read_json(pass_artifact),
            "IF-GAP-001": read_json(gap_artifact),
        }
        condition = lambda reference: {"condition_id": "COMPATIBILITY_PASSED", "evidence_reference": reference}

        clean = freeze_errors(policy, condition("INTERFACE:IF-DLC-001"), registry_interfaces)
        assert clean == [], clean

        bad_reference = freeze_errors(policy, condition("VR-COMPAT-001"), registry_interfaces)
        assert len(bad_reference) == 1 and "must cite an interface artifact as INTERFACE:<interface_id>" in bad_reference[0], bad_reference

        unknown = freeze_errors(policy, condition("INTERFACE:IF-NOPE"), registry_interfaces)
        assert len(unknown) == 1 and "cites unknown interface IF-NOPE" in unknown[0], unknown

        non_pass = freeze_errors(policy, condition("INTERFACE:IF-GAP-001"), registry_interfaces)
        assert any("verdict is 'GAP'" in message for message in non_pass), non_pass
        assert any("compatibility_evidence must be a non-empty array to claim PASS" in message for message in non_pass), non_pass

        missing_fields = freeze_errors(policy, {"condition_id": "COMPATIBILITY_PASSED"}, registry_interfaces)
        assert len(missing_fields) == 1 and "must cite an interface artifact" in missing_fields[0], missing_fields

        other_condition = freeze_errors(policy, {"condition_id": "SEAL_INTEGRITY", "evidence_reference": "whatever"}, registry_interfaces)
        assert other_condition == [], other_condition

        # 6. failure_ctq.interface_failure_modes is optional and cites the
        #    interface artifact (schema-level positive + negative).
        fixture = read_json(ROOT / "fixtures/valid/failure_ctq.json")
        assert "interface_failure_modes" not in fixture  # optional: absent stays valid
        schemas = {name: json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8")) for name in ("common.schema.json", "failure_ctq.schema.json")}
        registry = Registry()
        for schema in schemas.values():
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
        validator = Draft202012Validator(schemas["failure_ctq.schema.json"], registry=registry)
        assert list(validator.iter_errors(fixture)) == []
        cited = dict(fixture, interface_failure_modes=[
            {"interface_reference": "INTERFACE:IF-DLC-001", "failure_mode": "Coating delamination", "mechanism": "Loss of adhesion under cyclic load."}
        ])
        assert list(validator.iter_errors(cited)) == []
        broken = dict(fixture, interface_failure_modes=[{"interface_reference": "INTERFACE:IF-DLC-001"}])
        assert list(validator.iter_errors(broken)) != []  # failure_mode required

        # 7. Installation: 18 keys, real schema set, deployed preflight standalone.
        sys.path.insert(0, str(ROOT))
        try:
            from integrations.open_science import install_skill
            from scripts.install_domain_skill import SKILLS, contracts_for, shared_modules_for

            assert len(SKILLS) == 18, sorted(SKILLS)
            assert SKILLS["interface-definition"] == ("common.schema.json", "interface.schema.json"), SKILLS["interface-definition"]

            deploy_ws = workspace / "deploy"
            deploy_target = deploy_ws / ".opencode" / "skills"
            deploy_target.mkdir(parents=True)
            install_skill(
                ROOT / "skills" / "interface-definition", ROOT / "schemas", SKILLS["interface-definition"],
                deploy_target, workspace_root=deploy_ws,
                shared_modules=shared_modules_for("interface-definition"),
                contract_files=contracts_for("interface-definition"),
            )
            deployed_preflight = deploy_target / "interface-definition" / "scripts" / "preflight_interface_definition.py"
            assert deployed_preflight.is_file(), deployed_preflight
            assert (deploy_target / "interface-definition" / "scripts" / "interface_policy.py").is_file()
            deployed_input = workspace / "deploy-input.json"
            write_json(deployed_input, interface_input("PASS"))
            deployed = run(deployed_preflight, deployed_input)
            assert deployed.returncode == 0 and deployed.stdout.startswith("READY:"), deployed.stdout + deployed.stderr
            probe = workspace / "probe.json"
            write_json(probe, {})
            probe_result = run(deployed_preflight, probe)
            assert probe_result.returncode != 0 and probe_result.stdout.startswith("HOLD:"), probe_result.stdout
            assert "ModuleNotFoundError" not in probe_result.stderr, probe_result.stderr
        finally:
            sys.path.pop(0)

    print("PASS: WP-09 interface object (fail-closed compatibility verdict; COMPATIBILITY_PASSED unsatisfiable without evidence)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
