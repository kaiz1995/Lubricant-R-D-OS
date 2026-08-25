"""Build the only permitted Phase 3 optimization request artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from optimization_policy import expected_decision_fields
from preflight_optimization import errors_for


def main() -> int:
    if len(sys.argv) != 3: print("Usage: python build_optimization_artifact.py <input.json> <temporary-file>"); return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try: data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, input_path)
    if errors: print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    project = json.loads((input_path.parent / data["project_artifact"]).read_text(encoding="utf-8")); model = json.loads((input_path.parent / data["model_artifact"]).read_text(encoding="utf-8")); request = data["optimization"]
    artifact = {"schema_version": "0.1.0", "artifact_type": "optimization", "project_id": project["project_id"], "stage": "OPTIMIZED", "evidence_scope": model["evidence_scope"], **expected_decision_fields(request), "evidence": request["evidence"], "model_reference": model["model_id"], "engine_handoff": "PHASE4_DETERMINISTIC_ENGINE", **{key: request[key] for key in ("optimization_id", "objective_type", "objectives", "methods")}}
    output_path.parent.mkdir(parents=True, exist_ok=True); output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
