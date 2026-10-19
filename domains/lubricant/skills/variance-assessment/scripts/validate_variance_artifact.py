"""Validate one deterministic variance-assessment artifact against the contract and the policy.

Two independent checks, both fail-closed:

1. Structural: the artifact validates against ``schemas/variance.schema.json`` with
   the common contract in the registry. That schema fixes the flat
   ``<component>_ci_low`` shape, requires a ``stop_reason`` on every censoring entry,
   and constrains ``computed_by`` to the constant ENGINE.
2. Semantic: the artifact equals what ``variance_assessment_policy`` deterministically
   derives from its own fields -- the engine-provenance evidence item, the frozen
   constant identities (k_ratio = delta / (sigma_total * k), SIGMA_MAX = delta / k),
   the resolution rows recomputed as 4 * sigma / sqrt(n), and the canonical decision
   block. This catches a hand-edited artifact that is schema-legal but not
   policy-legal, for example a record whose verdict was softened from UNDERPOWERED to
   NO_DETECTABLE_DIFFERENCE while its own numbers still say the design was incapable.

The validator never recomputes a statistic: every identity it checks is an algebraic
restatement of two numbers the artifact already carries.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from variance_assessment_policy import policy_errors
from preflight_variance_assessment import SCHEMA_NAMES, schema_dir


def schema_errors(artifact: object) -> list[str]:
    directory = schema_dir()
    loaded = {name: json.loads((directory / name).read_text(encoding="utf-8")) for name in SCHEMA_NAMES}
    registry = Registry()
    for schema in loaded.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator(loaded["variance.schema.json"], registry=registry)
    return [
        f"variance.schema.json: {error.message} (path {list(error.absolute_path) or ['<root>']})"
        for error in validator.iter_errors(artifact)
    ]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python validate_variance_artifact.py <artifact.json>")
        return 1
    try:
        artifact = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    try:
        errors = schema_errors(artifact)
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read artifact or schemas: {error}")
        return 1
    if not isinstance(artifact, dict):
        errors.append("artifact must be a JSON object")
    else:
        errors.extend(policy_errors(artifact))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(
        "PASS: deterministic variance-assessment artifact conforms to the variance contract "
        f"(verdict={artifact.get('verdict')} computed_by={artifact.get('computed_by')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
