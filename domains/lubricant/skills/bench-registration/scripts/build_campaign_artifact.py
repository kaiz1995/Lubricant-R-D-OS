"""Build the only permitted campaign artifact from preflight-valid input.

Deterministic assembly only. The builder

1. re-runs the preflight checks (including both upstream artifacts),
2. resolves the iteration cap -- the request's value, or the contract's
   published ``max_iterations`` when the request omits it, in which case the
   artifact records that provenance in its ``result`` text and in one appended
   evidence item (the reserved marker),
3. projects the record into the ``schemas/campaign.schema.json`` shape:
   ``stage`` is the constant ``CAMPAIGN_OPENED``, ``project_id`` is the request's
   ``project_reference``, and the decision block comes from the shared policy,

so two callers with the same request get byte-identical artifacts. The builder
computes no capacity: ``available_bench_slots`` belongs to the bench record
(`bench_policy`), and a campaign carries no capacity field at all.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from campaign_policy import (
    CAMPAIGN_STAGE,
    expected_decision_fields,
    max_iterations_evidence_item,
    resolve_cap,
)
from preflight_campaign_registration import errors_for


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_campaign_artifact.py <input.json> <temporary-file>")
        return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data, input_path)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    record = data["campaign"]
    cap, defaulted, cap_errors = resolve_cap(record)
    if cap_errors or cap is None:
        print(f"HOLD: missing or invalid: {', '.join(cap_errors or ['campaign.max_iterations'])}; no artifact generated")
        return 1
    evidence = list(record["evidence"])
    if defaulted:
        evidence.append(max_iterations_evidence_item(cap))
    artifact = {
        "schema_version": "0.1.0",
        # The literal is deliberate: `tests/lubricant_e2e/test_precision_grease_chain.py`
        # fingerprints a producer by this exact string (`has_producer`), so hiding it
        # behind a constant would make a campaign producer invisible to that guard.
        "artifact_type": "campaign",
        "project_id": record["project_reference"],
        "stage": CAMPAIGN_STAGE,
        "evidence_scope": record["evidence_scope"],
        **expected_decision_fields(record, cap, defaulted),
        "evidence": evidence,
        "campaign_id": record["campaign_id"],
        "bench_references": record["bench_references"],
        "max_iterations": cap,
        "current_iteration": record["current_iteration"],
        "iterations": record["iterations"],
        "pairing_design": record["pairing_design"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"BUILT: {output_path} stage={artifact['stage']} campaign_id={artifact['campaign_id']} "
        f"max_iterations={artifact['max_iterations']} defaulted={str(defaulted).lower()} decision={artifact['decision']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
