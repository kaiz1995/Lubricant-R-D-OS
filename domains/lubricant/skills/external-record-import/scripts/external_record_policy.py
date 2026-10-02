"""Deterministic external-record-import policy: the fail-closed usage-rights rules.

One external record binds a batch of data obtained outside the project boundary
(outsourced test 外检, outsourced service 外协, or vendor datasheet) to its
provider and to the mandatory data-usage-rights anchor. The plan acceptance is
explicit: an external test record MUST carry a data_usage_rights_reference —
external data without a usage-rights anchor never enters the project evidence
base, so a missing or empty reference is rejected, never defaulted.

Provenance alignment with WP-12 claim_class: evidence items carried on an
external record are naturally THIRD_PARTY_LAB or MANUFACTURER_DATASHEET (never
INTERNAL_TEST — own controlled measurements are recorded by their producing
skills) and stay ungraded when omitted.

This module also owns the citation form: downstream consumers (experiment,
interface) cite this artifact as `EXTERNAL:<external_id>`.
"""

from __future__ import annotations

INPUT_FIELDS = {
    "external_id", "project_reference", "record_type", "provider",
    "data_usage_rights_reference", "source", "evidence_id",
    "evidence_scope", "evidence",
}
ARTIFACT_FIELDS = (
    "external_id", "project_reference", "record_type", "provider",
    "data_usage_rights_reference",
)
ALLOWED_FIELDS = INPUT_FIELDS | {"external_reference"}
RECORD_TYPES = ("EXTERNAL_TEST", "EXTERNAL_SERVICE", "MANUFACTURER_DATASHEET")
EVIDENCE_SCOPES = ("SYNTHETIC", "PHYSICAL")
EXTERNAL_REFERENCE_PREFIX = "EXTERNAL:"


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def has_gap(record: dict) -> bool:
    evidence = record.get("evidence")
    return isinstance(evidence, list) and any(
        isinstance(item, dict) and item.get("status") == "GAP" for item in evidence
    )


def evidence_errors(items: object) -> list[str]:
    if not isinstance(items, list) or not items:
        return ["external_record.evidence"]
    errors: list[str] = []
    for index, item in enumerate(items):
        label = f"external_record.evidence[{index}]"
        if not isinstance(item, dict) or not set(item) <= {"evidence_id", "statement", "source", "status", "claim_class"}:
            errors.append(label)
            continue
        for field in ("evidence_id", "statement", "source"):
            if not has_text(item.get(field)):
                errors.append(f"{label}.{field}")
        if item.get("status") not in {"OBSERVED", "ASSUMED", "GAP"}:
            errors.append(f"{label}.status")
        if "claim_class" in item and item.get("claim_class") not in {
            "MANUFACTURER_DATASHEET", "THIRD_PARTY_LAB", "INTERNAL_TEST", "REGULATORY_OR_STANDARD",
        }:
            errors.append(f"{label}.claim_class")
    return errors


def import_blockers(record: dict) -> list[str]:
    """Every reason the external record cannot be imported. Empty list = importable."""
    reasons: list[str] = []
    if not has_text(record.get("data_usage_rights_reference")):
        reasons.append(
            "data_usage_rights_reference is mandatory for external collaboration data "
            "(plan WP-10: an external test record must carry a data-usage-rights reference); "
            "obtain and reference the usage agreement before importing"
        )
    if has_gap(record):
        reasons.append("external_record.evidence contains GAP; resolve the recorded gap before importing")
    return reasons


def expected_decision_fields(record: dict) -> dict[str, str]:
    external_id = record.get("external_id", "")
    importable = not import_blockers(record)
    return {
        "decision_question": f"Can the supplied external data be imported as record {external_id}?",
        "hypothesis": f"{external_id} records its provider, record type, and the data-usage-rights anchor authorising internal use.",
        "uncertainty": "The external party's method qualification is not visible to this project; external data stays third-party or vendor-published until independently cross-checked, and this record does not by itself establish a release conclusion.",
        "decision_rule": "Import the record only when provider, record_type, and a non-empty data_usage_rights_reference are supplied and the evidence carries no GAP; evidence items on an external record are naturally THIRD_PARTY_LAB or MANUFACTURER_DATASHEET.",
        "result": f"{external_id} is {'importable' if importable else 'not importable'}: usage rights {'are' if has_text(record.get('data_usage_rights_reference')) else 'are not'} anchored.",
        "decision": "GO" if importable else "HOLD",
        "next_action": f"Retain {external_id} as an external record; downstream consumers cite it as EXTERNAL:{external_id}." if importable else "Retain the supplied evidence and resolve the recorded blockers before importing this record.",
    }


def external_record_reference(external_id: object) -> str:
    """The canonical downstream citation form for one external record."""
    return f"{EXTERNAL_REFERENCE_PREFIX}{external_id}"
