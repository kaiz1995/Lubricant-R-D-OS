"""End-to-end checks for the WP-05 application and bench objects.

Covers:
1. The schema inventory grows 17 -> 19 and validate_schemas stays green.
2. The bench availability -> usable-slot conversion is implemented with a single
   rule (multi-window, floor, reserved_days) and a hand-supplied slot count is
   rejected; a built bench artifact recomputes the same value.
3. An application PASS verdict is only admissible with determined OBSERVED
   criteria, a non-empty OBSERVED life-claim boundary, and no counterexamples.
4. Missing criteria are rejected: an empty criteria list forces result = GAP, and
   a GAP criterion can never back a PASS.
5. Both new skills are registered for install (14 -> 16 keys) and their deployed
   preflights run standalone.
6. Merge cross-check (WP-04b x WP-05, formalised by WP-06): the bench-side
   conversion `bench_policy.available_bench_slots` is the single source of
   truth for `doe_input.resource_envelope.bench_slots` — the folded value is
   fed into the DOE engine input and the engine recommends exactly that many
   runs (bounded by the hypothesis count). The conversion is only ever *called*
   here, never re-implemented.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"

BENCH_PREFLIGHT = ROOT / "skills/bench-registration/scripts/preflight_bench_registration.py"
BENCH_BUILDER = ROOT / "skills/bench-registration/scripts/build_bench_artifact.py"
BENCH_VALIDATOR = ROOT / "skills/bench-registration/scripts/validate_bench_artifact.py"
APP_PREFLIGHT = ROOT / "skills/application-definition/scripts/preflight_application_definition.py"
APP_BUILDER = ROOT / "skills/application-definition/scripts/build_application_artifact.py"
APP_VALIDATOR = ROOT / "skills/application-definition/scripts/validate_application_artifact.py"

# Recorded inventory just before WP-05 (17). WP-05 adds application + bench,
# WP-09 adds interface; the arithmetic assertion below still holds.
SCHEMA_COUNT_BEFORE = 17
SCHEMA_COUNT_AFTER = 21
NEW_SCHEMAS = ("application.schema.json", "bench.schema.json", "interface.schema.json", "external_record.schema.json")


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


def validate_against(kind: str, instance: dict) -> list[str]:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema = read_json(path)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    schema = read_json(SCHEMAS / f"{kind}.schema.json")
    return [error.message for error in Draft202012Validator(schema, registry=registry).iter_errors(instance)]


def bench_input(bench_id: str = "BENCH-SZ-01") -> dict:
    return {
        "bench": {
            "bench_id": bench_id,
            "project_reference": "WGO-001",
            "bench_name": "Suzhou grease bench 1",
            "location": "Suzhou",
            "availability_window": [
                {"window_id": "W-1", "start": "2026-01-01", "end": "2026-01-10"},
                {"window_id": "W-2", "start": "2026-02-01", "end": "2026-02-14", "reserved_days": 2},
            ],
            "cycle_days": 3,
            "cost_per_run": {"value": 1200, "unit": "CNY/run", "source": "Synthetic bench quote"},
            "source": "Synthetic bench spec",
            "evidence_id": "EV-BENCH-001",
            "evidence_scope": "SYNTHETIC",
            "evidence": [{
                "evidence_id": "EV-BENCH-001",
                "statement": "Synthetic bench parameters supplied for contract validation only; not a booked or qualified capacity.",
                "source": "Synthetic bench fixture",
                "status": "ASSUMED",
            }],
        }
    }


def application_input(result: str = "PASS", criteria: list[dict] | None = None, boundary: dict | None = None) -> dict:
    if criteria is None:
        criteria = [{
            "criterion_id": "C-1", "statement": "Leakage below limit at rated load.",
            "threshold": 1.0, "operator": "<=", "unit": "mL",
            "source": "Synthetic application spec", "evidence_id": "EV-APP-001", "status": "OBSERVED",
        }]
    if boundary is None:
        boundary = {
            "claim_scope": "10-year service life at rated load", "status": "OBSERVED",
            "validated_conditions": [{
                "condition_id": "LC-1", "parameter": "temperature",
                "lower_bound": 40, "upper_bound": 100, "unit": "degC",
            }],
            "extrapolation_basis": "Synthetic bench extrapolation", "evidence_reference": "EV-APP-001",
        }
    return {
        "application": {
            "application_id": "APP-WGO-001",
            "project_reference": "WGO-001",
            "formula_reference": "FORMULA-WGO-001",
            "process_window_reference": "PROCESS-WINDOW:PW-WGO-001",
            "bench_references": ["BENCH-SZ-01"],
            "acceptance_criteria": criteria,
            "result": result,
            "counterexamples": [],
            "life_claim_boundary": boundary,
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


def resource_envelope_slots(envelope: dict) -> int:
    """Merge-time cross-check placeholder (WP-04b).

    WP-04b defines `doe_input.resource_envelope.bench_slots`. Its documented
    conversion口径 references `bench.availability_window`, i.e. it must equal
    `bench_policy.available_bench_slots(bench_artifact)`. This helper exists so the
    end-to-end assertion is a one-line addition after the two worktrees merge;
    today there is no doe_input.resource_envelope in this tree, so it is unused.
    """
    return envelope["resource_envelope"]["bench_slots"]


def main() -> int:
    # 1. Schema inventory 17 -> 19 and validate_schemas green.
    schema_names = sorted(path.name for path in SCHEMAS.glob("*.schema.json"))
    for name in NEW_SCHEMAS:
        assert name in schema_names, (name, schema_names)
    assert len(schema_names) == SCHEMA_COUNT_AFTER, (len(schema_names), schema_names)
    assert SCHEMA_COUNT_BEFORE == SCHEMA_COUNT_AFTER - len(NEW_SCHEMAS)
    validated = subprocess.run(
        [sys.executable, "-B", "scripts/validate_schemas.py"], cwd=ROOT, capture_output=True, text=True
    )
    assert validated.returncode == 0, validated.stdout + validated.stderr

    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        inputs, artifacts = workspace / "inputs", workspace / "artifacts"
        inputs.mkdir()
        artifacts.mkdir()

        # 2. Bench: the availability -> slot conversion, single rule.
        bench_path = inputs / "bench-input.json"
        write_json(bench_path, bench_input())
        readied = run_ok(BENCH_PREFLIGHT, bench_path)
        # W-1: 10 usable days; W-2: 12 usable days; cycle 3 -> floor(10/3)+floor(12/3)=3+4=7
        assert "DERIVED: available_bench_slots=7" in readied.stdout, readied.stdout
        bench_artifact_path = artifacts / "bench.json"
        run_ok(BENCH_BUILDER, bench_path, bench_artifact_path)
        run_ok(BENCH_VALIDATOR, bench_artifact_path)
        bench = read_json(bench_artifact_path)
        assert bench["artifact_type"] == "bench"
        assert bench["project_id"] == "WGO-001"
        assert bench["available_bench_slots"] == 7, bench["available_bench_slots"]
        assert bench["stage"] == "DRAFT"
        assert validate_against("bench", bench) == [], validate_against("bench", bench)

        # 2b. A hand-supplied derived slot count is rejected, never trusted.
        hand_set = bench_input()
        hand_set["bench"]["available_bench_slots"] = 5
        hand_set_path = inputs / "bench-hand-set.json"
        write_json(hand_set_path, hand_set)
        rejected = run(BENCH_PREFLIGHT, hand_set_path)
        assert rejected.returncode != 0, rejected.stdout
        assert "available_bench_slots is derived" in rejected.stdout, rejected.stdout

        # 2c. A reserved-day count changes the conversion; a bad window is rejected.
        fewer = bench_input()
        fewer["bench"]["availability_window"][0]["reserved_days"] = 4  # 6 usable -> floor(6/3)=2
        fewer_path = inputs / "bench-reserved.json"
        write_json(fewer_path, fewer)
        fewer_result = run_ok(BENCH_PREFLIGHT, fewer_path)
        assert "DERIVED: available_bench_slots=6" in fewer_result.stdout, fewer_result.stdout

        bad_window = bench_input()
        bad_window["bench"]["availability_window"][0]["start"] = "2026-01-10"
        bad_window["bench"]["availability_window"][0]["end"] = "2026-01-01"
        bad_window_path = inputs / "bench-bad-window.json"
        write_json(bad_window_path, bad_window)
        bad_window_result = run(BENCH_PREFLIGHT, bad_window_path)
        assert bad_window_result.returncode != 0, bad_window_result.stdout
        assert "start must be <= end" in bad_window_result.stdout, bad_window_result.stdout

        bad_cycle = bench_input()
        bad_cycle["bench"]["cycle_days"] = 0
        bad_cycle_path = inputs / "bench-bad-cycle.json"
        write_json(bad_cycle_path, bad_cycle)
        bad_cycle_result = run(BENCH_PREFLIGHT, bad_cycle_path)
        assert bad_cycle_result.returncode != 0, bad_cycle_result.stdout
        assert "cycle_days must be a positive number" in bad_cycle_result.stdout, bad_cycle_result.stdout

        # 2d. Bench-side conversion function agrees with the built artifact.
        sys.path.insert(0, str(ROOT / "skills/bench-registration/scripts"))
        from bench_policy import available_bench_slots

        assert available_bench_slots(bench) == bench["available_bench_slots"]
        assert available_bench_slots({
            "availability_window": [{"window_id": "W", "start": "2026-01-01", "end": "2026-01-05"}],
            "cycle_days": 1.5,
        }) == 3  # floor(5 / 1.5) = 3

        # 3. Application: a fully determined record yields a PASS verdict.
        app_path = inputs / "application-pass.json"
        write_json(app_path, application_input())
        run_ok(APP_PREFLIGHT, app_path)
        app_artifact_path = artifacts / "application.json"
        run_ok(APP_BUILDER, app_path, app_artifact_path)
        run_ok(APP_VALIDATOR, app_artifact_path)
        application = read_json(app_artifact_path)
        assert application["artifact_type"] == "application"
        assert application["result"] == "PASS"
        assert application["decision"] == "GO"
        # WP-06: the application record materialises the APPLIED stage token.
        assert application["stage"] == "APPLIED", application["stage"]
        # The interface WP-06 consumes: bench linkage survives into the artifact.
        assert application["bench_references"] == [bench["bench_id"]]
        assert validate_against("application", application) == [], validate_against("application", application)

        # 3b. A GAP criterion can never back a PASS (preflight + schema).
        gap_criterion = {"criterion_id": "C-2", "statement": "10-year life threshold.", "status": "GAP"}
        pass_with_gap = application_input(criteria=[application_input()["application"]["acceptance_criteria"][0], copy.deepcopy(gap_criterion)])
        pass_with_gap_path = inputs / "application-pass-gap.json"
        write_json(pass_with_gap_path, pass_with_gap)
        gap_result = run(APP_PREFLIGHT, pass_with_gap_path)
        assert gap_result.returncode != 0, gap_result.stdout
        assert "criteria with GAP block PASS" in gap_result.stdout, gap_result.stdout

        # 3c. An empty life_claim_boundary can never back a PASS (preflight + schema).
        empty_boundary = {"claim_scope": "10-year service life", "status": "GAP", "validated_conditions": []}
        pass_with_empty_life = application_input(boundary=copy.deepcopy(empty_boundary))
        empty_life_path = inputs / "application-pass-empty-life.json"
        write_json(empty_life_path, pass_with_empty_life)
        empty_life_result = run(APP_PREFLIGHT, empty_life_path)
        assert empty_life_result.returncode != 0, empty_life_result.stdout
        assert "life_claim_boundary must be OBSERVED with at least one validated condition" in empty_life_result.stdout, empty_life_result.stdout

        # 4. Missing criteria are handled without faking a PASS.
        # 4a. An empty criteria list forces result GAP: PASS is rejected at preflight.
        empty_criteria_pass = application_input(result="PASS", criteria=[])
        empty_criteria_pass_path = inputs / "application-empty-criteria-pass.json"
        write_json(empty_criteria_pass_path, empty_criteria_pass)
        empty_pass_result = run(APP_PREFLIGHT, empty_criteria_pass_path)
        assert empty_pass_result.returncode != 0, empty_pass_result.stdout
        assert "must be a non-empty array to claim PASS" in empty_pass_result.stdout, empty_pass_result.stdout

        # 4b. A criterion without a threshold but claiming OBSERVED is rejected.
        silent_criterion = application_input(criteria=[{"criterion_id": "C-1", "statement": "no threshold", "status": "OBSERVED"}])
        silent_path = inputs / "application-silent-criterion.json"
        write_json(silent_path, silent_criterion)
        silent_result = run(APP_PREFLIGHT, silent_path)
        assert silent_result.returncode != 0, silent_result.stdout
        assert "must be GAP when threshold is not determined" in silent_result.stdout, silent_result.stdout

        # 4c. Empty criteria + result GAP builds and validates; decision is HOLD.
        gap_record = application_input(result="GAP", criteria=[], boundary=copy.deepcopy(empty_boundary))
        gap_record_path = inputs / "application-empty-criteria-gap.json"
        write_json(gap_record_path, gap_record)
        run_ok(APP_PREFLIGHT, gap_record_path)
        gap_artifact_path = artifacts / "application-gap.json"
        run_ok(APP_BUILDER, gap_record_path, gap_artifact_path)
        run_ok(APP_VALIDATOR, gap_artifact_path)
        gap_record_artifact = read_json(gap_artifact_path)
        assert gap_record_artifact["result"] == "GAP" and gap_record_artifact["decision"] == "HOLD"
        assert validate_against("application", gap_record_artifact) == []

        # 4d. Empty criteria + a non-GAP verdict is rejected.
        inconclusive = application_input(result="INCONCLUSIVE", criteria=[])
        inconclusive_path = inputs / "application-empty-criteria-inconclusive.json"
        write_json(inconclusive_path, inconclusive)
        inconclusive_result = run(APP_PREFLIGHT, inconclusive_path)
        assert inconclusive_result.returncode != 0, inconclusive_result.stdout
        assert "must be GAP when acceptance_criteria is empty" in inconclusive_result.stdout, inconclusive_result.stdout

        # 4e. Schema-level guard: a PASS with an empty life boundary is invalid JSON Schema too.
        schema_pass_empty_life = read_json(app_artifact_path)
        schema_pass_empty_life["life_claim_boundary"] = copy.deepcopy(empty_boundary)
        assert validate_against("application", schema_pass_empty_life), "schema must reject PASS with empty life boundary"

        # 5. Deployed copies (installed to a temp target, never the user's real
        # skills directory) must run their own preflight standalone.
        sys.path.insert(0, str(ROOT))
        from integrations.open_science import install_skill
        from scripts.install_domain_skill import ENGINE_ROOT, ENGINE_SKILLS, SKILLS, contracts_for, shared_modules_for

        deploy_ws = workspace / "deploy"
        deploy_target = deploy_ws / ".opencode" / "skills"
        deploy_target.mkdir(parents=True)
        for skill in ("application-definition", "bench-registration"):
            install_skill(
                ROOT / "skills" / skill, ROOT / "schemas", SKILLS[skill], deploy_target,
                engine_root=ENGINE_ROOT if skill in ENGINE_SKILLS else None,
                workspace_root=deploy_ws, shared_modules=shared_modules_for(skill),
                contract_files=contracts_for(skill),
            )
        deployed_cases = [
            (deploy_target / "application-definition" / "scripts" / "preflight_application_definition.py", app_path),
            (deploy_target / "bench-registration" / "scripts" / "preflight_bench_registration.py", bench_path),
        ]
        probe = workspace / "probe-input.json"
        probe.write_text("{}", encoding="utf-8")
        for deployed_preflight, valid_input in deployed_cases:
            deployed = run(deployed_preflight, valid_input)
            assert deployed.returncode == 0, deployed.stdout + deployed.stderr
            assert "ImportError" not in deployed.stderr and "Traceback" not in deployed.stderr, deployed.stderr
            probe_result = run(deployed_preflight, probe)
            assert probe_result.returncode != 0 and probe_result.stdout.startswith("HOLD:"), probe_result.stdout
            assert "ModuleNotFoundError" not in probe_result.stderr, probe_result.stderr

        # 6. Merge cross-check (WP-04b x WP-05, formalised by WP-06):
        #    bench availability -> available_bench_slots -> doe_input
        #    resource_envelope.bench_slots -> the engine recommends exactly N runs.
        #    The conversion is only ever CALLED (single source of truth:
        #    bench_policy.available_bench_slots), never re-implemented here.
        from domains.lubricant.compute.doe.engine import generate_doe
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource

        # The nested engine input contract (doe_input.schema.json) carries the
        # resource_envelope; the artifact schemas carry the bench/application.
        doe_registry = Registry()
        for path in sorted(SCHEMAS.glob("*.schema.json")):
            schema = read_json(path)
            doe_registry = doe_registry.with_resource(schema["$id"], Resource.from_contents(schema))
        doe_input_schema = read_json(ROOT / "domains/lubricant/schemas/doe_input.schema.json")
        doe_registry = doe_registry.with_resource(doe_input_schema["$id"], Resource.from_contents(doe_input_schema))

        def validate_against_schema(schema: dict, registry: Registry, instance: dict) -> list[str]:
            return [error.message for error in Draft202012Validator(schema, registry=registry).iter_errors(instance)]

        def make_doe_engine_input(bench_slots: int) -> dict:
            # WP-04b口径提示: engine inputs must declare a split-plot role per
            # changing factor (factors[].role or process_factor_role).
            return {
                "input_type": "FACTORIAL_DOE_DESIGN",
                "design_type": "FULL_FACTORIAL",
                "model_order": "LINEAR",
                "target_runs": 0,
                "design_space_reference": "DS-PROC-BENCH-001",
                "process_factor_role": "WHOLE_PLOT",
                "factors": [
                    {"factor_id": "PROC-TEMP", "factor_type": "CONTINUOUS", "range": {"lower": 90, "upper": 110}, "unit": "degC"},
                    {"factor_id": "PROC-VACUUM", "factor_type": "CONTINUOUS", "range": {"lower": 1, "upper": 10}, "unit": "kPa"},
                ],
                "responses": [{"ctq_reference": "KV40", "test_method_reference": "ASTM D445", "role": "OPTIMIZATION_RESPONSE"}],
                "experiment_card": {
                    "decision_question": "Which process hypothesis gets the folded bench slots?",
                    "hypothesis": "Vessel change shifts the temperature/vacuum response.",
                    "variables_note": "Process factors only.",
                    "constraints_note": "Independent process bounds, no mixture closure.",
                    "responses_note": "KV40 OPTIMIZATION_RESPONSE.",
                    "doe_selection_reason": "Two-level factorial resolves the main effects first.",
                    "expected_information_value": "Orthogonal columns isolate each effect.",
                    "decision_rule": "Spend the folded bench slots on the least-resolved hypothesis.",
                },
                "resource_envelope": {
                    "bench_slots": bench_slots,
                    "lot_capacity": 16,
                    "cycle_days": 3.0,
                    "cost_cap": 0.0,
                    "external_test_lead_time": 0.0,
                },
            }

        def check_folded_slots(bench_artifact: dict) -> int:
            # (a) fold ONLY through the bench_policy function (single source).
            slots = available_bench_slots(bench_artifact)
            assert slots == bench_artifact["available_bench_slots"], (slots, bench_artifact)
            # (b) the folded value fills the DOE input envelope, contract-valid.
            engine_input = make_doe_engine_input(slots)
            assert validate_against_schema(doe_input_schema, doe_registry, engine_input) == [], "doe_input envelope invalid"
            # (c) the engine recommends exactly the folded number of runs
            #     (bounded by the hypothesis count the design can resolve).
            env = generate_doe(engine_input)
            assert env["status"] == "OK", env.get("rejection_reasons")
            result = env["result"]
            hypotheses = len(result["columns"])
            expected_runs = min(slots, hypotheses)
            assert len(result["recommended_next_runs"]) == expected_runs, (slots, hypotheses, result["recommended_next_runs"])
            assert result["resource_feasible"] is True, result["resource_feasible"]
            assert resource_envelope_slots(engine_input) == slots
            return expected_runs

        # Bench A (the fixture bench): 7 usable slots; the 2-factor linear
        # design resolves 3 hypotheses, so exactly min(7, 3) = 3 runs.
        folded_a = check_folded_slots(bench)
        # Bench B: one 6-day window, cycle 3 -> 2 usable slots -> exactly 2 runs
        # (2 hypotheses to resolve), proving the recommendation count tracks the
        # bench fold, not a constant.
        small_bench_path = inputs / "bench-small.json"
        small_bench = bench_input("BENCH-SZ-02")
        small_bench["bench"]["availability_window"] = [
            {"window_id": "W-1", "start": "2026-03-01", "end": "2026-03-06"},
        ]
        write_json(small_bench_path, small_bench)
        small_readied = run_ok(BENCH_PREFLIGHT, small_bench_path)
        assert "DERIVED: available_bench_slots=2" in small_readied.stdout, small_readied.stdout
        small_bench_artifact_path = artifacts / "bench-small.json"
        run_ok(BENCH_BUILDER, small_bench_path, small_bench_artifact_path)
        small_bench_artifact = read_json(small_bench_artifact_path)
        folded_b = check_folded_slots(small_bench_artifact)
        assert folded_a == 3 and folded_b == 2, (folded_a, folded_b)

    # The three application/bench/validation skills are registered for
    # installation with their real schema sets.
    sys.path.insert(0, str(ROOT))
    from scripts.install_domain_skill import SKILLS

    assert len(SKILLS) == 19, sorted(SKILLS)
    assert SKILLS["application-definition"] == ("common.schema.json", "application.schema.json"), SKILLS["application-definition"]
    assert SKILLS["application-validation"] == ("common.schema.json", "application.schema.json"), SKILLS["application-validation"]
    assert SKILLS["bench-registration"] == ("common.schema.json", "bench.schema.json"), SKILLS["bench-registration"]

    print("PASS: WP-05 application + bench objects, fail-closed verdict, and bench slot conversion")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
