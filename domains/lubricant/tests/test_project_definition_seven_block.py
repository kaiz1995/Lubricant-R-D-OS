"""The seven-block charter refactor (2026-10-15), asserted rather than described.

The refactor made three things true that used to be false, and each one is a claim a
later reader would otherwise have to take on trust:

1. **A benchmark is optional background.** Before it, a charter that named no competitive
   benchmark was a HOLD unless it also carried ``benchmark_waiver_reason``. The user's own
   precision-gear grease project could not satisfy that: the names that had been typed into
   it during testing were not a real comparator, and the comparator that matters is the
   physical dossier built at step 4. A charter with no benchmark at all must now open.
2. **The reducer model and hardware carrier can be recorded.** A grease project starts
   from the machine it goes into -- frame size, structure form, friction-pair materials --
   and a half-declared carrier is refused rather than completed by the next step.
3. **Success criteria may be PROVISIONAL.** A grease project often starts before the
   customer fixes the machine-level thresholds; recording that honestly is better than
   inventing a number, and the status travels onto the charter.

The oil routes must be unaffected: their charters set ``target_cost`` and name a benchmark,
and every message for them is unchanged. The last case here asserts exactly that.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "project-definition" / "scripts"
PREFLIGHT = SCRIPTS / "preflight_project_definition.py"
BUILDER = SCRIPTS / "build_project_artifact.py"
VALIDATOR = SCRIPTS / "validate_project_artifact.py"
FIXTURES = ROOT / "fixtures" / "project-definition"
GREASE_SEVEN_BLOCK = FIXTURES / "valid-input.grease-seven-block.json"
OIL_INPUT = FIXTURES / "valid-input.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: Path, *arguments: object) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", script.name, *map(str, arguments)],
        cwd=script.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def output(result: subprocess.CompletedProcess) -> str:
    return (result.stdout or "") + (result.stderr or "")


def drive(request_path: Path, artifact_path: Path) -> dict:
    """preflight -> build -> validate, returning the built charter."""
    ready = run(PREFLIGHT, request_path)
    assert ready.returncode == 0, output(ready)
    built = run(BUILDER, request_path, artifact_path)
    assert built.returncode == 0, output(built)
    validated = run(VALIDATOR, artifact_path)
    assert validated.returncode == 0, output(validated)
    return read_json(artifact_path)


def case_no_benchmark_opens(workspace: Path) -> None:
    """(1) A charter that names NO benchmark opens, with no waiver reason either."""
    source = read_json(GREASE_SEVEN_BLOCK)
    assert "benchmark_products" not in source, source
    assert "benchmark_waiver_reason" not in source, source
    request = workspace / "no-benchmark.json"
    write_json(request, source)
    charter = drive(request, workspace / "charter.json")
    assert charter["decision"] == "GO", charter["decision"]
    # Neither field is fabricated onto the record: an absent benchmark stays absent.
    assert "benchmark_products" not in charter, charter
    assert "benchmark_waiver_reason" not in charter, charter
    print("(1) a grease charter with NO benchmark (and no waiver) opens: decision=GO")

    # The legacy waiver field still travels when a charter already carries it, so charters
    # written before the refactor keep validating unchanged.
    legacy = {**source, "benchmark_waiver_reason": "no comparable product on the market"}
    legacy_request = workspace / "legacy-waiver.json"
    write_json(legacy_request, legacy)
    legacy_charter = drive(legacy_request, workspace / "legacy-charter.json")
    assert legacy_charter.get("benchmark_waiver_reason") == "no comparable product on the market", legacy_charter
    print("(1) a legacy charter carrying benchmark_waiver_reason still validates and keeps the field")


def case_reducer_model(workspace: Path) -> None:
    """(2) Block 2 is recorded when supplied, and a partial carrier is refused."""
    request = workspace / "carrier.json"
    write_json(request, read_json(GREASE_SEVEN_BLOCK))
    charter = drive(request, workspace / "charter.json")
    carrier = charter["reducer_model"]
    assert carrier["model_size"] == "20" and carrier["structure_form"] == "HAT", carrier
    assert carrier["reduction_ratio"] == "100:1", carrier
    assert len(carrier["friction_pair_materials"]) == 2, carrier
    print(f"(2) the reducer model is recorded: size {carrier['model_size']}, {carrier['structure_form']}, "
          f"{len(carrier['friction_pair_materials'])} friction-pair materials")

    # A carrier that names its frame size but no friction pair would let the duty step
    # invent the rest, so it is refused rather than completed.
    partial = read_json(GREASE_SEVEN_BLOCK)
    del partial["reducer_model"]["friction_pair_materials"]
    partial_request = workspace / "partial-carrier.json"
    write_json(partial_request, partial)
    refused = run(PREFLIGHT, partial_request)
    assert refused.returncode != 0, output(refused)
    assert "reducer_model.friction_pair_materials" in output(refused), output(refused)
    print("(2) a half-declared carrier is refused: " + output(refused).strip()[:110])

    # An unknown frame size is refused by name, not silently accepted.
    bad_size = read_json(GREASE_SEVEN_BLOCK)
    bad_size["reducer_model"]["model_size"] = "99"
    bad_request = workspace / "bad-size.json"
    write_json(bad_request, bad_size)
    refused = run(PREFLIGHT, bad_request)
    assert refused.returncode != 0 and "reducer_model.model_size is invalid" in output(refused), output(refused)
    print("(2) an out-of-range frame size is refused by name")


def case_provisional_criteria(workspace: Path) -> None:
    """(3) PROVISIONAL success criteria are legal and travel onto the charter."""
    request = workspace / "provisional.json"
    write_json(request, read_json(GREASE_SEVEN_BLOCK))
    charter = drive(request, workspace / "charter.json")
    assert charter["success_criteria_status"] == "PROVISIONAL", charter.get("success_criteria_status")
    assert charter["cost_position"] == "CEILING", charter.get("cost_position")
    assert charter["application_scenario"] == "COBOT", charter.get("application_scenario")
    assert charter["delivery_form"] == "LAB", charter.get("delivery_form")
    print("(3) PROVISIONAL criteria and cost CEILING recorded; scenario COBOT, delivery LAB")

    # A status outside the enum is refused rather than coerced.
    bad = read_json(GREASE_SEVEN_BLOCK)
    bad["success_criteria_status"] = "MAYBE"
    bad_request = workspace / "bad-status.json"
    write_json(bad_request, bad)
    refused = run(PREFLIGHT, bad_request)
    assert refused.returncode != 0 and "success_criteria_status must be" in output(refused), output(refused)
    print("(3) an unknown criteria status is refused")

    # A cost POSTURE other than CEILING is refused: this charter never carries a
    # reduction target, so a charter claiming otherwise contradicts its own block 6.
    wrong_posture = read_json(GREASE_SEVEN_BLOCK)
    wrong_posture["cost_position"] = "REDUCTION_TARGET"
    wrong_request = workspace / "wrong-posture.json"
    write_json(wrong_request, wrong_posture)
    refused = run(PREFLIGHT, wrong_request)
    assert refused.returncode != 0 and "cost_position must be CEILING" in output(refused), output(refused)
    print("(3) a non-CEILING cost posture is refused")


def case_oil_route_unchanged(workspace: Path) -> None:
    """(4) An oil charter still works exactly as before, and still needs its cost basis."""
    request = workspace / "oil.json"
    oil = read_json(OIL_INPUT)
    write_json(request, oil)
    charter = drive(request, workspace / "oil-charter.json")
    assert charter["decision"] == "GO", charter["decision"]
    assert charter["target_cost"]["value"] == 9000, charter["target_cost"]
    assert charter["benchmark_products"] == ["Mobilgear SHC Gear 320 WT"], charter
    print("(4) an oil charter is unaffected: target_cost and benchmark_products intact")

    # The cost rule that predates the refactor still holds: no target_cost without a reason.
    no_cost = {key: value for key, value in oil.items() if key != "target_cost"}
    no_cost_request = workspace / "oil-no-cost.json"
    write_json(no_cost_request, no_cost)
    refused = run(PREFLIGHT, no_cost_request)
    assert refused.returncode != 0, output(refused)
    assert "cost_basis_reason" in output(refused), output(refused)
    print("(4) the pre-existing cost rule is intact: " + output(refused).strip()[:100])


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        case_no_benchmark_opens(workspace / "a")
        case_reducer_model(workspace / "b")
        case_provisional_criteria(workspace / "c")
        case_oil_route_unchanged(workspace / "d")
    print("PASS: the seven-block charter -- a benchmark is optional background (no waiver needed), the "
          "reducer model and hardware carrier are recorded and a partial one is refused, PROVISIONAL "
          "criteria and a CEILING cost posture travel onto the charter, and every oil charter behaves "
          "exactly as it did before")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
