"""Build the only permitted NEXT_BATCH_DECIDED artifact from preflight-valid input.

Deterministic assembly only. The iteration pair is derived from the campaign carrier (the
merged bench artifact, ``bench.json``, whose ledger holds the inner-loop rounds), the
proposed samples are composed from the declared competing explanations, and the canonical
decision block comes from ``next_batch_policy`` so this builder, the preflight and the
validator cannot disagree.

The builder never invents a sample, a hypothesis, a discrimination or a reason to stop:
every one of those strings is carried through from the input, and an input that does not
declare them is refused by the preflight before this script writes anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from preflight_next_batch import composed_artifact, errors_for, notes_for, read_artifact


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python build_next_batch_artifact.py <input.json> <temporary-file>")
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
    _, campaign = read_artifact(data["campaign_artifact"], input_path, "campaign_artifact")
    _, design = read_artifact(data["experiment_design_artifact"], input_path, "experiment_design_artifact")
    if campaign is None or design is None:
        print("HOLD: the campaign carrier (bench.json) or the round's design cannot be read; no artifact generated")
        return 1
    artifact = composed_artifact(data, campaign, design)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"BUILT: {output_path} stage={artifact['stage']} stop_state={artifact['stop_state']} "
        f"decision={artifact['decision']} from_iteration={artifact['from_iteration']} "
        f"to_iteration={artifact['to_iteration']} bench_slots_required={artifact['bench_slots_required']} "
        f"proposed_samples={len(artifact['proposed_samples'])}")
    for note in notes_for(data, input_path):
        print(f"NOTE: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
