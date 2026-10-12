"""Reject input that cannot gate entry into the WP-06 APPLIED stage.

Fail-closed and asymmetric: the headline rule is that an INCONCLUSIVE
application verdict can never enter APPLIED (an undetermined verdict is not a
validation pass). A FAIL or GAP verdict is likewise blocked; only a PASS that
is admissible under the producing skill's fail-closed rules (determined
OBSERVED criteria, non-empty OBSERVED life-claim boundary, no counterexamples,
no GAP evidence) and that cites at least one registered bench may advance a
VERIFIED project into APPLIED. Missing criteria are rejected the same way —
an empty criteria list can only carry result GAP, and GAP never advances.

ADDITIVE (step 16b, plan section 4.4.3 item 3-7): the precision-grease route adds
the whole-machine criteria chain (``machine_indicators``) and the upstream references
that chain must trace to (``campaign_artifact`` / ``bench_test_artifact``). A record
that declares no ``project_type`` is an oil record and is validated exactly as before.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from application_validation_policy import (
    GREASE_PROJECT_TYPE,
    GREASE_RECORD_FIELDS,
    MACHINE_INDICATORS,
    RECORD_FIELDS,
    applied_entry_blockers,
    grease_route,
    has_text,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ("common.schema.json", "application.schema.json", "campaign.schema.json", "bench_test.schema.json")
GREASE_REQUIRED_RECORD_FIELDS = {"project_type", "machine_indicators"}
GREASE_OPTIONAL_RECORD_FIELDS = {"campaign_artifact", "bench_test_artifact"}
UPSTREAM = (("campaign_artifact", "campaign.schema.json", "CAMPAIGN_OPENED"), ("bench_test_artifact", "bench_test.schema.json", "BENCH_TESTED"))


def schema_dir() -> Path:
    canonical = SKILL_ROOT.parents[1] / "schemas"
    return canonical if all((canonical / name).is_file() for name in SCHEMAS) else SKILL_ROOT / "references"


def resolved_path(value: object, input_path: Path) -> Path | None:
    if not has_text(value):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_path.parent / path


def read_artifact(value: object, input_path: Path, schema_name: str, label: str) -> tuple[list[str], dict | None]:
    """Load and schema-validate one upstream artifact. Additive: only called when supplied."""
    path = resolved_path(value, input_path)
    if path is None:
        return [f"{label} must be a path to a built artifact"], None
    try:
        schemas = {name: json.loads((schema_dir() / name).read_text(encoding="utf-8")) for name in SCHEMAS}
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{label} cannot be read: {error}"], None
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = [f"{label}: {error.message}" for error in Draft202012Validator(schemas[schema_name], registry=registry).iter_errors(artifact)]
    return errors, artifact if not errors else None


def grease_upstream_errors(record: dict, input_path: Path) -> list[str]:
    """The grease route's machine verdict must trace to the campaign and bench run.

    The chain is the point: a whole-machine criterion is only an application verdict when
    the record says which campaign round and which bench run produced it. Both upstreams
    are required on this route and are schema- and stage-checked.
    """
    errors: list[str] = []
    application = record.get("application") if isinstance(record.get("application"), dict) else {}
    benches = application.get("bench_references") if isinstance(application.get("bench_references"), list) else []
    project_reference = record.get("project_reference")
    for key, schema_name, stage in UPSTREAM:
        if not has_text(record.get(key)):
            errors.append(f"{key} is required on the {GREASE_PROJECT_TYPE} route: the machine verdict must trace to the campaign and bench run that produced it")
            continue
        item_errors, artifact = read_artifact(record.get(key), input_path, schema_name, key)
        errors.extend(item_errors)
        if artifact is None:
            continue
        if artifact.get("stage") != stage:
            errors.append(f"{key} must be stage {stage}")
        if artifact.get("project_id") != project_reference:
            errors.append(f"{key} must belong to {project_reference}")
    bench_test = None
    if has_text(record.get("bench_test_artifact")):
        _, bench_test = read_artifact(record.get("bench_test_artifact"), input_path, "bench_test.schema.json", "bench_test_artifact")
    if bench_test is not None and benches and bench_test.get("bench_reference") not in benches:
        errors.append(
            f"bench_test_artifact.bench_reference {bench_test.get('bench_reference')!r} must be cited in "
            "application.bench_references: the machine verdict must come from a bench the application record names"
        )
    return errors


def errors_for(data: object, input_path: Path | None = None) -> list[str]:
    if not isinstance(data, dict):
        return ["input must be a JSON object"]
    if set(data) != {"application_validation"}:
        return ["input must contain only application_validation"]
    record = data["application_validation"]
    if not isinstance(record, dict):
        return [f"application_validation must contain exactly {sorted(RECORD_FIELDS)}"]
    if not grease_route(record):
        # The oil routes are validated exactly as before: an exact field set.
        if set(record) != RECORD_FIELDS:
            extra = sorted(set(record) - RECORD_FIELDS)
            missing = sorted(RECORD_FIELDS - set(record))
            return [f"application_validation must contain exactly {sorted(RECORD_FIELDS)}; unexpected={extra or 'none'} missing={missing or 'none'}"]
        record_errors: list[str] = []
    else:
        allowed = RECORD_FIELDS | GREASE_RECORD_FIELDS
        extra = sorted(set(record) - allowed)
        missing = sorted(GREASE_REQUIRED_RECORD_FIELDS - set(record))
        if extra or missing:
            return [
                f"a {GREASE_PROJECT_TYPE} application_validation record must contain {sorted(RECORD_FIELDS | GREASE_REQUIRED_RECORD_FIELDS)} "
                f"plus the optional {sorted(GREASE_OPTIONAL_RECORD_FIELDS)}; unexpected={extra or 'none'} missing={missing or 'none'}"
            ]
        record_errors = []
    errors: list[str] = list(record_errors)
    if not has_text(record.get("project_reference")):
        errors.append("application_validation.project_reference")
    errors.extend(applied_entry_blockers(record))
    if grease_route(record) and input_path is not None:
        errors.extend(grease_upstream_errors(record, input_path))
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python preflight_application_validation.py <input.json>")
        return 1
    path = Path(sys.argv[1]).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no APPLIED entry")
        return 1
    errors = errors_for(data, path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no APPLIED entry")
        return 1
    print("READY: the application record gates entry into APPLIED")
    if grease_route(data.get("application_validation") if isinstance(data, dict) else None):
        print(f"NOTE: {GREASE_PROJECT_TYPE} route: every whole-machine indicator ({', '.join(MACHINE_INDICATORS)}) is bound to an OBSERVED criterion, and the campaign / bench_test chain is verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
