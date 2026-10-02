"""End-to-end checks for the WP-10 external collaboration record (external-record-import).

Covers:
1. Schema inventory 20 -> 21 with external_record.schema.json present and
   validate_schemas green (including the new invalid fixture
   external_record--missing-usage-rights.json).
2. The plan WP-10 acceptance is fail-closed: an external test record WITHOUT a
   data_usage_rights_reference is rejected by preflight with the rule named
   (missing field and blank value are two distinct negatives); a record WITH
   the anchor passes the full preflight -> build -> validate chain as a REAL
   built artifact (stage DRAFT).
3. GAP evidence blocks the import (fail-closed).
4. The optional references exist and validate: a REAL experiment artifact form
   (fixtures/valid/experiment.json + external_record_reference) and a REAL
   interface record form both cite the external artifact as
   EXTERNAL:<external_id>; the fields are optional so existing forms without
   them stay valid.
5. claim_class semantics aligned with WP-12: the external record carries a
   THIRD_PARTY_LAB evidence item and the schema description names the natural
   provenance classes.
6. The skill is registered for install (18 -> 19 keys) and its deployed
   preflight runs standalone.
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

ER_PREFLIGHT = ROOT / "skills/external-record-import/scripts/preflight_external_record_import.py"
ER_BUILDER = ROOT / "skills/external-record-import/scripts/build_external_record_artifact.py"
ER_VALIDATOR = ROOT / "skills/external-record-import/scripts/validate_external_record_artifact.py"


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


def external_input(**overrides) -> dict:
    record = {
        "external_id": "EXT-001",
        "project_reference": "WGO-001",
        "record_type": "EXTERNAL_TEST",
        "provider": "National tribology test center",
        "data_usage_rights_reference": "DUA-2026-014",
        "source": "External lab report EXT-2026-014",
        "evidence_id": "E-EXT-001",
        "evidence_scope": "SYNTHETIC",
        "evidence": [{
            "evidence_id": "E-EXT-001",
            "statement": "Outsourced four-ball wear test report received for contract validation only.",
            "source": "External lab report EXT-2026-014",
            "status": "ASSUMED",
            "claim_class": "THIRD_PARTY_LAB",
        }],
    }
    record.update(overrides)
    return {"external_record": record}


def build_external(inputs: Path, artifacts: Path, name: str) -> Path:
    """Build a REAL external-record artifact through the producing skill."""
    input_path = inputs / f"external-{name}.json"
    write_json(input_path, external_input())
    pre = run(ER_PREFLIGHT, input_path)
    assert pre.returncode == 0, f"external-{name}\n{pre.stdout}{pre.stderr}"
    artifact_path = artifacts / f"external-{name}.json"
    built = run(ER_BUILDER, input_path, artifact_path)
    assert built.returncode == 0, f"external-{name}\n{built.stdout}{built.stderr}"
    validated = run(ER_VALIDATOR, artifact_path)
    assert validated.returncode == 0, f"external-{name}\n{validated.stdout}{validated.stderr}"
    artifact = read_json(artifact_path)
    assert artifact["stage"] == "DRAFT", artifact["stage"]
    assert artifact["data_usage_rights_reference"] == "DUA-2026-014"
    return artifact_path


def schema_validator(*names: str) -> Draft202012Validator:
    schemas_dir = ROOT / "schemas"
    registry = Registry()
    loaded = {}
    for name in ("common.schema.json", *names):
        schema = read_json(schemas_dir / name)
        loaded[name] = schema
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(loaded[names[-1]], registry=registry)


def main() -> int:
    # 1. Schema inventory 20 -> 21 and validate_schemas green.
    schema_names = sorted(path.name for path in (ROOT / "schemas").glob("*.schema.json"))
    assert "external_record.schema.json" in schema_names, schema_names
    assert len(schema_names) == 21, (len(schema_names), schema_names)
    validated = subprocess.run(
        [sys.executable, "-B", "scripts/validate_schemas.py"], cwd=ROOT, capture_output=True, text=True
    )
    assert validated.returncode == 0, validated.stdout + validated.stderr

    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        inputs, artifacts = workspace / "inputs", workspace / "artifacts"
        inputs.mkdir()
        artifacts.mkdir()

        # 2a. Negative: the usage-rights anchor is missing entirely.
        missing = inputs / "external-missing-rights.json"
        payload = external_input()
        del payload["external_record"]["data_usage_rights_reference"]
        write_json(missing, payload)
        blocked = run(ER_PREFLIGHT, missing)
        assert blocked.returncode != 0 and blocked.stdout.startswith("HOLD:"), blocked.stdout
        assert "missing=['data_usage_rights_reference']" in blocked.stdout, blocked.stdout

        # 2b. Negative: the anchor is present but blank.
        blank = inputs / "external-blank-rights.json"
        write_json(blank, external_input(data_usage_rights_reference="   "))
        blocked_blank = run(ER_PREFLIGHT, blank)
        assert blocked_blank.returncode != 0 and "data_usage_rights_reference is mandatory for external collaboration data" in blocked_blank.stdout, blocked_blank.stdout

        # 2c. Positive: the anchored record passes the full chain.
        external_artifact = build_external(inputs, artifacts, "ok")

        # 3. GAP evidence blocks the import.
        gap = dict(external_input()["external_record"])
        gap["evidence"] = [dict(gap["evidence"][0], status="GAP")]
        gap_path = inputs / "external-gap.json"
        write_json(gap_path, {"external_record": gap})
        blocked_gap = run(ER_PREFLIGHT, gap_path)
        assert blocked_gap.returncode != 0 and "contains GAP" in blocked_gap.stdout, blocked_gap.stdout

        # 4. Optional references (WP-10): experiment and interface may cite the
        #    external record as EXTERNAL:<external_id>; absence stays valid.
        experiment_validator = schema_validator("experiment.schema.json")
        experiment_form = read_json(ROOT / "fixtures/valid/experiment.json")
        assert "external_record_reference" not in experiment_form  # optional: absent stays valid
        assert list(experiment_validator.iter_errors(experiment_form)) == []
        cited_experiment = dict(experiment_form, external_record_reference="EXTERNAL:EXT-001")
        assert list(experiment_validator.iter_errors(cited_experiment)) == []

        interface_validator = schema_validator("interface.schema.json")
        interface_form = {
            "schema_version": "0.1.0", "artifact_type": "interface", "project_id": "WGO-001", "stage": "DRAFT",
            "decision_question": "Does the supplied evidence justify compatibility for interface IF-DLC-001?",
            "hypothesis": "IF-DLC-001 records its counterparts, optional coating system, and per-condition compatibility observations.",
            "uncertainty": "Supplied observations are not independently verified; recorded ASSUMED evidence remains assumed.",
            "decision_rule": "Record the supplied verdict as-is; a PASS is only admissible with non-empty all-OBSERVED all-PASS compatibility evidence and no GAP evidence.",
            "result": "IF-DLC-001 is supported by the supplied compatibility evidence.",
            "decision": "GO", "next_action": "Retain IF-DLC-001 as an interface record with verdict PASS.",
            "evidence": [{"evidence_id": "EV-IF-001", "statement": "compat run", "source": "compat-lab", "status": "OBSERVED"}],
            "interface_id": "IF-DLC-001", "project_reference": "WGO-001", "interface_type": "COATING_SUBSTRATE",
            "counterpart_a": {"role": "COATING", "designation": "DLC", "source": "supplier sheet"},
            "counterpart_b": {"role": "SUBSTRATE", "designation": "GCr15", "source": "internal spec"},
            "coating": None,
            "compatibility_evidence": [{
                "compatibility_id": "CMP-001", "method_reference": "TM-001",
                "condition": "1.2 GPa, 80 C, 72 h", "result": "PASS",
                "evidence_id": "EV-COMPAT-001", "status": "OBSERVED",
            }],
            "verdict": "PASS", "source": "compat-lab", "evidence_id": "EV-IF-001",
        }
        assert list(interface_validator.iter_errors(interface_form)) == []
        cited_interface = dict(interface_form, external_record_reference="EXTERNAL:EXT-001")
        assert list(interface_validator.iter_errors(cited_interface)) == []

        # 5. claim_class semantics aligned with WP-12: the natural provenance
        #    classes are named in the schema description and the built artifact
        #    keeps its THIRD_PARTY_LAB grading.
        description = read_json(ROOT / "schemas/external_record.schema.json")["description"]
        assert "THIRD_PARTY_LAB" in description and "MANUFACTURER_DATASHEET" in description, description
        artifact = read_json(external_artifact)
        assert artifact["evidence"][0]["claim_class"] == "THIRD_PARTY_LAB", artifact["evidence"]

        # 6. Installation: 19 keys, real schema set, deployed preflight standalone.
        sys.path.insert(0, str(ROOT))
        try:
            from integrations.open_science import install_skill
            from scripts.install_domain_skill import SKILLS, contracts_for, shared_modules_for

            assert len(SKILLS) == 19, sorted(SKILLS)
            assert SKILLS["external-record-import"] == ("common.schema.json", "external_record.schema.json"), SKILLS["external-record-import"]

            deploy_ws = workspace / "deploy"
            deploy_target = deploy_ws / ".opencode" / "skills"
            deploy_target.mkdir(parents=True)
            install_skill(
                ROOT / "skills" / "external-record-import", ROOT / "schemas", SKILLS["external-record-import"],
                deploy_target, workspace_root=deploy_ws,
                shared_modules=shared_modules_for("external-record-import"),
                contract_files=contracts_for("external-record-import"),
            )
            deployed_preflight = deploy_target / "external-record-import" / "scripts" / "preflight_external_record_import.py"
            assert deployed_preflight.is_file(), deployed_preflight
            deployed_input = workspace / "deploy-input.json"
            write_json(deployed_input, external_input())
            deployed = run(deployed_preflight, deployed_input)
            assert deployed.returncode == 0 and deployed.stdout.startswith("READY:"), deployed.stdout + deployed.stderr
            probe = workspace / "probe.json"
            write_json(probe, {})
            probe_result = run(deployed_preflight, probe)
            assert probe_result.returncode != 0 and probe_result.stdout.startswith("HOLD:"), probe_result.stdout
            assert "ModuleNotFoundError" not in probe_result.stderr, probe_result.stderr
        finally:
            sys.path.pop(0)

    print("PASS: WP-10 external record (usage-rights anchor is fail-closed; EXTERNAL:<id> citations validate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
