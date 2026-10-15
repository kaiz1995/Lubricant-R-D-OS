"""Build the only permitted merged bench artifact from preflight-valid input.

Deterministic assembly only. The builder

1. re-runs the preflight checks (both blocks and the cross-block rules),
2. resolves the iteration cap -- the request's value, or the contract's published
   ``max_iterations`` when the request omits it, in which case the artifact
   records that provenance in one appended evidence item (the reserved marker),
3. projects the two blocks into the ``schemas/bench.schema.json`` shape: ``stage``
   is the constant ``BENCH_RESOURCE_REGISTERED``, ``project_id`` is the bench
   block's ``project_reference``, the artifact-level ``source`` / ``evidence_id`` /
   ``evidence_scope`` are the bench block's (it is the main record the plan hangs
   off), the evidence array is ``bench.evidence`` + ``campaign.evidence`` (bench
   first) plus the appended provenance item, and the decision block comes from the
   shared policy,

so two callers with the same request get byte-identical artifacts. The builder
computes no capacity of its own: ``available_bench_slots`` is the single
conversion in ``bench_policy``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bench_policy import (
    BENCH_ARTIFACT_FIELDS,
    BENCH_STAGE,
    expected_decision_fields,
    available_bench_slots,
    max_iterations_evidence_item,
    resolve_cap,
)
from preflight_bench_registration import errors_for


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_bench_artifact.py <input.json> <temporary-file>")
        return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"HOLD: cannot read input: {error}; no artifact generated")
        return 1
    errors = errors_for(data)
    if errors:
        print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated")
        return 1
    bench, record = data["bench"], data["campaign"]
    slots = available_bench_slots(bench)
    cap, defaulted, cap_errors = resolve_cap(record)
    if cap_errors or cap is None:
        print(f"HOLD: missing or invalid: {', '.join(cap_errors or ['campaign.max_iterations'])}; no artifact generated")
        return 1
    evidence = list(bench["evidence"]) + list(record["evidence"])
    if defaulted:
        evidence.append(max_iterations_evidence_item(cap))
    normalized = {**record, "max_iterations": cap, "evidence": evidence}
    artifact = {
        "schema_version": "0.1.0",
        # The literal artifact_type is deliberate: `tests/lubricant_e2e/test_precision_grease_chain.py`
        # fingerprints a producer by this exact string (`has_producer`), so hiding it
        # behind a constant would make the merged producer invisible to that guard.
        "artifact_type": "bench",
        "project_id": bench["project_reference"],
        "stage": BENCH_STAGE,
        "evidence_scope": bench["evidence_scope"],
        "source": bench["source"],
        "evidence_id": bench["evidence_id"],
        **expected_decision_fields(bench, normalized, slots, defaulted=defaulted),
        "evidence": evidence,
        "available_bench_slots": slots,
        **{field: bench[field] for field in BENCH_ARTIFACT_FIELDS},
        "campaign_id": record["campaign_id"],
        "max_iterations": cap,
        "current_iteration": record["current_iteration"],
        "iterations": record["iterations"],
        "pairing_design": record["pairing_design"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"BUILT: {output_path} stage={artifact['stage']} bench_id={artifact['bench_id']} "
        f"campaign_id={artifact['campaign_id']} max_iterations={artifact['max_iterations']} "
        f"defaulted={str(defaulted).lower()} decision={artifact['decision']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
