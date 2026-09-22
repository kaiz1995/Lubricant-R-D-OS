"""Run one deterministic lubricant compute engine from JSON stdin."""

from __future__ import annotations

import argparse
import json
import sys

from .cost.engine import calculate_cost
from .doe.engine import generate_doe
from .optimization.engine import optimize
from .statistics.engine import analyze_statistics


ENGINES = {
    "cost": calculate_cost,
    "doe": generate_doe,
    "statistics": analyze_statistics,
    "optimization": optimize,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, choices=ENGINES)
    args = parser.parse_args()
    raw = sys.stdin.buffer.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"input JSON failed: {error}", file=sys.stderr)
        return 1
    try:
        result = ENGINES[args.engine](data, raw)
    except Exception as error:
        print(f"{args.engine} engine failed: {error}", file=sys.stderr)
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
