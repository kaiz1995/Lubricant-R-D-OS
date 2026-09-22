"""Build one provenance-bound PHYSICAL EXPERIMENT_RUNNING artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from preflight_experiment_import import candidate, doe_output, errors_for, resolve


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_experiment_artifact.py <input.json> <temporary-file>"); return 1
    input_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    try: data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error: print(f"HOLD: cannot read input: {error}; no artifact generated"); return 1
    errors = errors_for(data, input_path)
    if errors: print(f"HOLD: missing or invalid: {', '.join(errors)}; no artifact generated"); return 1
    project = json.loads(resolve(data["project_artifact"], input_path).read_text(encoding="utf-8"))
    method = json.loads(resolve(data["test_method_artifact"], input_path).read_text(encoding="utf-8"))
    design_space = json.loads(resolve(data["design_space_artifact"], input_path).read_text(encoding="utf-8"))
    design = json.loads(resolve(data["experiment_design_artifact"], input_path).read_text(encoding="utf-8"))
    _, doe, output_digest = doe_output(resolve(data["doe_output_artifact"], input_path))
    assert doe is not None and output_digest is not None
    artifact = candidate(data, project, method, design_space, design, doe, output_digest)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"BUILT: {output_path}"); return 0


if __name__ == "__main__": raise SystemExit(main())
