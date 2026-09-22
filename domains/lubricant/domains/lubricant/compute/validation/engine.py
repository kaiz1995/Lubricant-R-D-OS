from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from .chain import validate_chain
from .common import canonical_digest, check, ordered, schema_errors, validate_contract, validate_provenance
from .registry import REGISTRY

ENGINE_VERSION = "0.1.0"
METHOD = "VALIDATION_FRAMEWORK_V1"


def validate_request(request, input_bytes=None):
    request_errors = schema_errors(request, "validation_input.schema.json")
    artifact = request.get("artifact", {}) if isinstance(request, dict) else {}
    artifact_type = artifact.get("artifact_type", "unknown")
    data = artifact.get("data", {})
    context = request.get("chain_context", []) if isinstance(request, dict) else []
    checks = []
    if request_errors:
        checks.append(check("contract.validation_input", "CONTRACT", "FATAL", "validation request schema failed: " + request_errors[0]))
    engine_name = data.get("engine_name", "cost")
    entry = REGISTRY.get(engine_name)
    expected_type = engine_name + "_result"
    if entry is None:
        checks.append(check("contract.registry.engine", "CONTRACT", "ERROR", "unknown engine_name: " + str(engine_name)))
    else:
        if data.get("engine_version") not in entry["supported_versions"]:
            checks.append(check("contract.registry.version", "CONTRACT", "ERROR", "unsupported engine version: " + str(data.get("engine_version"))))
        if artifact_type != expected_type:
            checks.append(check("contract.registry.artifact_type", "CONTRACT", "ERROR", "artifact_type does not match engine_name"))
        checks.extend(validate_contract(expected_type, data))
        present = {x.get("artifact_type") for x in context}
        for required in entry["required_upstream"]:
            if required not in present:
                checks.append(check("provenance.required." + required, "PROVENANCE", "FATAL", "required upstream artifact missing: " + required))
        checks.extend(validate_provenance(context))
        checks.extend(entry["validator"](data, context))
    chain_checks, consistency = validate_chain(data, artifact_type, context)
    checks.extend(chain_checks)
    if data.get("engine_name") == "optimization" and "DOMAIN_SCREENED_APPROX" in data.get("result", {}).get("method_summary", {}).get("effective_domain_note", ""):
        checks.append(check("numerical.domain_screened_approx", "NUMERICAL", "WARNING", "optimization domain uses bounding-box approximation"))
    checks = ordered(checks)
    severities = {x["severity"] for x in checks}
    if severities & {"ERROR", "FATAL"}: overall = "REJECTED"
    elif "WARNING" in severities: overall = "VALID_WITH_WARNINGS"
    else: overall = "VALID"
    errors = sorted(x["message"] for x in checks if x["severity"] in {"ERROR", "FATAL"})
    warnings = sorted(x["message"] for x in checks if x["severity"] == "WARNING")
    result = {"overall_status": overall, "artifact_type": artifact_type, "artifact_digest": canonical_digest(data),
              "checks": checks, "errors": errors, "warnings": warnings, "upstream_consistency": consistency,
              "eligible_for_downstream": overall != "REJECTED"}
    raw = input_bytes if input_bytes is not None else json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"schema_version": "0.1.0", "engine_name": engine_name if engine_name in REGISTRY else "cost", "engine_version": ENGINE_VERSION,
            "method": METHOD, "parameters": {"artifact_digest_contract": "ARTIFACT_DIGEST_V1"},
            "input_digest": hashlib.sha256(raw).hexdigest(), "status": "OK" if overall != "REJECTED" else "REJECTED",
            "rejection_reasons": errors, "result": result,
            "evidence": [{"evidence_id": "validation-framework", "statement": "four-layer deterministic validation completed", "source": "VALIDATION_FRAMEWORK_V1", "status": "OBSERVED"}]}


def _write(path, envelope):
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((json.dumps(envelope, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def main():
    if len(sys.argv) != 3:
        print("Usage: python -m domains.lubricant.compute.validation.engine <input.json> <output.json>", file=sys.stderr); return 2
    try:
        raw = Path(sys.argv[1]).read_bytes(); request = json.loads(raw.decode("utf-8")); envelope = validate_request(request, raw)
    except Exception as exc:
        request = {}; raw = raw if "raw" in locals() else b""
        envelope = validate_request(request, raw)
        envelope["rejection_reasons"] = ["input read/parse failed: " + str(exc)]
        envelope["status"] = "REJECTED"
    _write(sys.argv[2], envelope); return 0


if __name__ == "__main__":
    raise SystemExit(main())
