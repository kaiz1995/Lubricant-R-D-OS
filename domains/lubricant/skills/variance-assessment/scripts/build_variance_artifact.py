"""Build the only permitted VARIANCE_ASSESSED artifact from preflight-valid input.

Deterministic assembly only, and every number comes from the engine. The builder

1. re-runs the preflight checks,
2. calls the frozen statistics engine over the supplied engine input,
3. refuses to write anything when the engine rejects the input, and
4. projects the engine envelope plus the canonical decision block into the
   ``schemas/variance.schema.json`` shape.

The skill never computes a statistic and never accepts a hand-entered figure: the
pack's red line is that the LLM does no deterministic computation, so a request
carrying a pre-computed number has nowhere to put it. ``computed_by`` is the
constant ENGINE, and the four verdicts pass through exactly as the engine decided
them -- UNDERPOWERED included, never folded into NO_DETECTABLE_DIFFERENCE.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from variance_assessment_policy import (
    expected_decision_fields,
    engine_evidence_item,
    input_notes,
    project_engine_result,
    stop_state,
)
from variance_engine_bridge import run_engine
from preflight_variance_assessment import errors_for, load_bench_records


def build_artifact(data: dict, engine_envelope: dict, project_id: str) -> tuple[dict, list[str]]:
    """Assemble the variance artifact. Pure function of validated input + engine output.

    ``project_id`` is inherited from the supplied step-11 bench-test records: a
    variance assessment belongs to the project whose runs it assesses, and the
    preflight has already proven that those records agree on exactly one.
    """
    engine_input = data["engine_input"]
    engine_result = engine_envelope["result"]
    projected, errors = project_engine_result(engine_input, engine_result)
    stop = stop_state(engine_input, engine_result, data.get("model_prediction_interval"))
    evidence = [*data["evidence"], engine_evidence_item(engine_envelope, data["variance_id"])]
    artifact = {
        "schema_version": "0.1.0",
        "artifact_type": "variance",
        "project_id": project_id,
        "stage": "VARIANCE_ASSESSED",
        "evidence_scope": data["evidence_scope"],
        **expected_decision_fields(
            data["variance_id"], data["campaign_reference"], data["iteration"], data["evidence_scope"],
            projected["verdict"], projected["components"].get("sigma_total"), projected["power"],
            projected["k_ratio"], projected["sigma_max_requirement"], projected.get("preregistered_delta"),
            projected["effect_size"], evidence, stop,
        ),
        "evidence": evidence,
        "variance_id": data["variance_id"],
        "campaign_reference": data["campaign_reference"],
        "iteration": data["iteration"],
        "replicate_structure": projected["replicate_structure"],
        "censoring": projected["censoring"],
        "intervention_events": projected["intervention_events"],
        "components": projected["components"],
        "effect_size": projected["effect_size"],
        "power": projected["power"],
        "k_ratio": projected["k_ratio"],
        "sigma_max_requirement": projected["sigma_max_requirement"],
        "resolution_table": projected["resolution_table"],
        "verdict": projected["verdict"],
        "computed_by": "ENGINE",
    }
    if "frozen_sigma_reference" in projected:
        artifact["frozen_sigma_reference"] = projected["frozen_sigma_reference"]
    if "preregistered_delta" in projected:
        artifact["preregistered_delta"] = projected["preregistered_delta"]
    return artifact, errors


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_variance_artifact.py <input.json> <temporary-file>")
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
    _, records = load_bench_records(data, input_path)
    engine_envelope, digest, failure = run_engine(data["engine_input"])
    if failure is not None:
        print(f"HOLD: {failure}; no artifact generated")
        return 1
    project_ids = {record.get("project_id") for record in records}
    project_id = next(iter(project_ids)) if len(project_ids) == 1 else None
    artifact, projection_errors = build_artifact(data, engine_envelope, project_id)
    if projection_errors:
        print(f"HOLD: {', '.join(projection_errors)}; no artifact generated")
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"BUILT: {output_path} stage={artifact['stage']} verdict={artifact['verdict']} "
        f"decision={artifact['decision']} computed_by={artifact['computed_by']} engine_input_digest={digest}"
    )
    for line in input_notes(data):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
