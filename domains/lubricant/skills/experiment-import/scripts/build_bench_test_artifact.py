"""Build one provenance-bound BENCH_TESTED observation from preflight-valid input.

Deterministic assembly only. Every judgement - the identity requirement, the censoring
discipline, and the canonical decision block - lives in ``bench_test_policy`` so this
builder, the preflight and the validator cannot disagree about the same run.

The builder never invents an event, an event time, a stop reason, a setpoint or an
environment reading. A run that produced no event is written with ``event_time: null`` and
its declared ``stop_reason``; the observation window length is never written into
``event_time`` (red line 3 of the development guide: 删失不得当终点). An uncensored run
that carries no ``stop_reason`` gets an explicit ``null``, which states "no reason
recorded" rather than leaving the field to guesswork.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bench_test_policy import bench_test_artifact, is_bench_request
from preflight_experiment_import import bench_errors_for, resolve


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_bench_test_artifact.py <input.json> <temporary-file>"); return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try: data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    if not is_bench_request(data):
        print(
            "HOLD: this is not a bench-test import request (it carries no bench_test record, or it carries "
            "an experiment record and belongs to build_experiment_artifact.py); no artifact generated"
        ); return 1
    errors = bench_errors_for(data, input_path)
    if errors: print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    project = json.loads(resolve(data["project_artifact"], input_path).read_text(encoding="utf-8"))
    artifact = bench_test_artifact(data["bench_test"], project, data["evidence_scope"], data["evidence"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path} stage={artifact['stage']} run_id={artifact['run_id']}")
    print(
        f"OBSERVATION: censoring_type={artifact['censoring_type']} event_occurred={artifact['event_occurred']} "
        f"event_time={artifact['event_time']} stop_reason={artifact['stop_reason']}"
    )
    return 0


if __name__ == "__main__": raise SystemExit(main())
