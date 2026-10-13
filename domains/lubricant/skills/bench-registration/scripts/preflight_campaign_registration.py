"""Reject input that cannot open one inner-loop bench campaign.

CAMPAIGN_OPENED is the stage the router hands to this skill on the
PRECISION_GREASE_DEV route. A campaign is the carrier of the inner loop, and it
is gated fail-closed on four things the record cannot be trusted without:

* a bounded cap -- supplied, or read from ``contracts/state-machine.json`` when
  the request omits it (the contract's published figure, never an invented one);
* at least one recorded round whose stop states can authorize the next one
  (only CONTINUE does);
* upstream provenance in the request: the project charter (``project.json``) and
  the registered bench (``bench.json``) the campaign draws its scarce slots from,
  each schema-valid and belonging to the same project id;
* no GAP evidence, and no reserved contract-default marker forged by the caller.

The derived ``available_bench_slots`` of every supplied bench is read through
``bench_policy`` (the single conversion, never re-implemented) and reported; it
is not stored on the campaign artifact, which carries no capacity field.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from bench_policy import available_bench_slots
from campaign_policy import (
    CAMPAIGN_STAGE,
    REQUEST_FIELDS,
    REQUIRED_REQUEST_FIELDS,
    record_errors,
    resolve_cap,
)

SKILL_ROOT = Path(__file__).resolve().parents[1]

# The schemas this preflight loads: the shared contract, the campaign contract
# the built artifact must satisfy, and the two upstream artifact contracts
# (project charter and registered bench).
SCHEMA_NAMES = ("common.schema.json", "campaign.schema.json", "project.schema.json", "bench.schema.json")

INPUT_FIELDS = {"campaign", "project_artifact", "bench_artifacts"}


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMA_NAMES) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def read_artifact(value: object, input_path: Path, schema_name: str, label: str) -> tuple[list[str], dict | None]:
    """Load and schema-validate one upstream artifact (application-validation's shape)."""
    path = resolved_path(value, input_path)
    if path is None:
        return [f"{label} must be a path to a built artifact"], None
    try:
        schemas = {name: json.loads((schema_dir() / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [
        f"{label}: {error.message}"
        for error in Draft202012Validator(schemas[schema_name], registry=registry).iter_errors(artifact)
    ]
    return errors, artifact if not errors else None


def upstream_errors(record: dict, data: dict, input_path: Path) -> list[str]:
    """Both upstreams load, belong to the campaign's project, and are cited.

    The bench check is the load-bearing one: a campaign names the benches it
    takes slots from, so every reference must resolve to a supplied registered
    bench, every supplied bench must be cited (an uncited record is an omission,
    not a silent drop), and a SYNTHETIC bench may never back a PHYSICAL campaign
    (the bench skill's NO Synthetic Closure red line).
    """
    errors: list[str] = []
    project_reference = record.get("project_reference")
    project_errors, project = read_artifact(
        data.get("project_artifact"), input_path, "project.schema.json", "project_artifact"
    )
    errors.extend(project_errors)
    if project is not None and project.get("project_id") != project_reference:
        errors.append(
            f"project_artifact belongs to {project.get('project_id')!r}, not to the campaign's project_reference {project_reference!r}"
        )
    bench_values = data.get("bench_artifacts")
    if not isinstance(bench_values, list) or not bench_values:
        errors.append("bench_artifacts must be a non-empty array of paths to registered bench artifacts")
        return errors
    references = record.get("bench_references") if isinstance(record.get("bench_references"), list) else []
    cited: list[str] = []
    for index, value in enumerate(bench_values):
        label = f"bench_artifacts[{index}]"
        bench_errors, bench = read_artifact(value, input_path, "bench.schema.json", label)
        errors.extend(bench_errors)
        if bench is None:
            continue
        bench_id = bench.get("bench_id")
        if bench_id not in references:
            errors.append(
                f"{label} ({bench_id!r}) is supplied but no campaign.bench_references entry cites it: the campaign "
                "would carry a bench it does not name"
            )
        else:
            cited.append(bench_id)
        if bench.get("project_id") != project_reference:
            errors.append(f"{label} ({bench_id!r}) belongs to {bench.get('project_id')!r}, not to {project_reference!r}")
        if record.get("evidence_scope") == "PHYSICAL" and bench.get("evidence_scope") == "SYNTHETIC":
            errors.append(
                f"{label} ({bench_id!r}) is SYNTHETIC and may not back a PHYSICAL campaign: a synthetic bench "
                "record must never be presented as physical capacity"
            )
    for reference in references:
        if reference not in cited:
            errors.append(
                f"campaign.bench_references entry {reference!r} resolves to no supplied bench artifact: a campaign "
                "draws its slots from registered benches only"
            )
    return errors


def derived_notes(record: dict, data: dict, input_path: Path) -> list[str]:
    """Report each supplied bench's derived slot count; never stored, never booked."""
    notes: list[str] = []
    total = 0
    for index, value in enumerate(data["bench_artifacts"]):
        path = resolved_path(value, input_path)
        try:
            bench = json.loads(path.read_text(encoding="utf-8"))
            slots = available_bench_slots(bench)
        except (OSError, json.JSONDecodeError, AttributeError, ValueError) as error:
            notes.append(f"WARNING: cannot derive slots for bench_artifacts[{index}]: {error}")
            continue
        total += slots
        notes.append(f"DERIVED: bench {bench.get('bench_id')} available_bench_slots={slots}")
    cap = record.get("max_iterations")
    if isinstance(cap, int) and not isinstance(cap, bool) and cap > total:
        notes.append(
            f"NOTE: max_iterations={cap} exceeds the {total} available_bench_slots registered by the supplied "
            "bench artifact(s); a registration records only the availability it was given, so this is reported "
            "and not rejected"
        )
    return notes


def request_errors(record: object) -> list[str]:
    """The request shape and the reserved marker, then the shared record rules."""
    if not isinstance(record, dict):
        return ["campaign must be a JSON object"]
    extra = sorted(set(record) - REQUEST_FIELDS)
    missing = sorted(REQUIRED_REQUEST_FIELDS - set(record))
    if extra or missing:
        return [
            "campaign must contain the campaign-registration request fields"
            f" ({sorted(REQUIRED_REQUEST_FIELDS)} plus optional max_iterations)"
            f"; unexpected={extra or 'none'} missing={missing or 'none'}"
        ]
    cap, _, cap_errors = resolve_cap(record)
    errors: list[str] = list(cap_errors)
    for field in ("project_reference", "source", "evidence_id"):
        if not isinstance(record.get(field), str) or not record.get(field, "").strip():
            errors.append(f"campaign.{field}")
    errors.extend(record_errors(record, cap=cap, forbid_provenance_item=True))
    return errors


def errors_for(data: object, input_path: Path) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != INPUT_FIELDS:
        extra = sorted(set(data) - INPUT_FIELDS)
        missing = sorted(INPUT_FIELDS - set(data))
        return [f"input must contain only {sorted(INPUT_FIELDS)}; unexpected={extra or 'none'} missing={missing or 'none'}"]
    record = data.get("campaign")
    errors = request_errors(record)
    if errors or not isinstance(record, dict):
        return errors
    # Resolve the cap once more so an omitted cap is validated against its contract default.
    cap, _, _ = resolve_cap(record)
    normalized = {**record, "max_iterations": cap}
    return upstream_errors(normalized, data, input_path)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_campaign_registration.py <input.json>")
        return 1
    path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    cap, defaulted, _ = resolve_cap(data["campaign"])
    print(f"READY: input can open one bench campaign at stage {CAMPAIGN_STAGE}")
    if defaulted:
        print(f"NOTE: max_iterations={cap} defaulted from contracts/state-machine.json")
    for note in derived_notes({**data["campaign"], "max_iterations": cap}, data, path):
        print(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
