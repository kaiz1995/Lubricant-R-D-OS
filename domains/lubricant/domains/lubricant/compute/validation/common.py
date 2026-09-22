from __future__ import annotations

import hashlib
import json
from pathlib import Path

# jsonschema/referencing are existing project dev-dependencies used by the other
# compute engines; the validation logic itself otherwise uses only the stdlib.

LAYERS = {"CONTRACT": 0, "PROVENANCE": 1, "NUMERICAL": 2, "CROSS_STAGE": 3}


def canonical_digest(obj):
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def check(check_id, layer, severity, message, evidence_reference=""):
    status = "PASS" if severity == "INFO" else "WARNING" if severity == "WARNING" else "ERROR"
    return {"check_id": check_id, "layer": layer, "status": status, "severity": severity,
            "message": message, "evidence_reference": evidence_reference}


def schema_errors(data, schema_name):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    root = Path(__file__).resolve().parents[2] / "schemas"
    schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in root.glob("*.json")}
    registry = Registry()
    for schema in schemas.values():
        if "$id" in schema:
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    schema = schemas.get(schema_name)
    if schema is None:
        return [schema_name + " not found"]
    errors = sorted(Draft202012Validator(schema, registry=registry).iter_errors(data), key=lambda e: (list(e.path), e.message))
    return [e.message for e in errors]


def validate_contract(artifact_type, data):
    errors = schema_errors(data, artifact_type + "_schema.json")
    if errors:
        return [check("contract.schema", "CONTRACT", "ERROR", "schema validation failed: " + errors[0], artifact_type + "_schema.json")]
    return [check("contract.schema", "CONTRACT", "INFO", "artifact matches frozen schema", artifact_type + "_schema.json")]


def validate_provenance(context):
    out = []
    for item in sorted(context, key=lambda x: (x.get("artifact_type", ""), x.get("digest", ""))):
        artifact_type = item.get("artifact_type", "")
        expected_engine = artifact_type.removesuffix("_result").removesuffix("_input")
        actual_engine = item.get("data", {}).get("engine_name")
        out.append(check("provenance.type_engine." + artifact_type, "PROVENANCE",
                         "INFO" if actual_engine == expected_engine else "ERROR",
                         "context artifact_type matches engine_name" if actual_engine == expected_engine else "context artifact_type does not match engine_name",
                         artifact_type))
        actual = canonical_digest(item.get("data", {}))
        severity = "INFO" if actual == item.get("digest") else "FATAL"
        out.append(check("provenance.digest." + item.get("artifact_type", "unknown"), "PROVENANCE", severity,
                         "declared digest matches canonical artifact" if severity == "INFO" else "declared digest does not match canonical artifact",
                         item.get("digest", "")))
    return out


def ordered(checks):
    return sorted(checks, key=lambda x: (LAYERS[x["layer"]], x["check_id"], x["message"]))
