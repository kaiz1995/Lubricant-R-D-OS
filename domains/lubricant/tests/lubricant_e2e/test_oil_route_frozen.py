"""Freeze the six oil-project stage routes against a byte-for-byte literal.

The six oil routes (NEW_PRODUCT, IMPROVEMENT, COST_DOWN, CUSTOMIZATION,
EXPLORATION, PROCESS_ROBUSTNESS) were reviewed by hand against the tag
``contract-v0.7.0-pregate`` batch after batch. That is a manual regression
ritual, and it is exactly the kind of invariant a machine should hold: the
route each oil project type walks must not change silently.

This test turns that ritual into an assertion. It pins the six sequences as
literals (taken verbatim from
``git show contract-v0.7.0-pregate:domains/lubricant/contracts/state-machine.json``)
and checks that BOTH consumers agree with the frozen text:

  1) ``contracts/state-machine.json`` -> ``type_routes`` for the six oil types
     equals the frozen literal, element by element and in order;
  2) the router ``route_step.py --list-stages <TYPE>`` prints the same literal
     (all six types queried);
  3) ``PRECISION_GREASE_DEV`` (the precision-gear grease workflow, published
     later alongside the six oil routes) appears in none of the six oil route
     sequences — the grease route is a separate route, never folded into an oil
     route.

The frozen snapshot's lengths are NEW_PRODUCT 12, IMPROVEMENT 10, COST_DOWN 8,
CUSTOMIZATION 8, EXPLORATION 7, PROCESS_ROBUSTNESS 8.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTE_SCRIPT = ROOT / "skills/lubricant-rd-agent/scripts/route_step.py"
CONTRACT_PATH = ROOT / "contracts" / "state-machine.json"

# The six oil routes, frozen verbatim from tag contract-v0.7.0-pregate
# (`git show contract-v0.7.0-pregate:domains/lubricant/contracts/state-machine.json`).
FROZEN_OIL_ROUTES: dict[str, tuple[str, ...]] = {
    "NEW_PRODUCT": (
        "PROJECT_DEFINED",
        "DUTY_DEFINED",
        "CHALLENGES_DEFINED",
        "FAILURE_CTQ_DEFINED",
        "TEST_METHODS_QUALIFIED",
        "DESIGN_SPACE_DEFINED",
        "EXPERIMENT_DESIGNED",
        "EXPERIMENT_RUNNING",
        "MODEL_BUILT",
        "OPTIMIZED",
        "VERIFIED",
        "APPLIED",
    ),
    "IMPROVEMENT": (
        "PROJECT_DEFINED",
        "FAILURE_CTQ_DEFINED",
        "TEST_METHODS_QUALIFIED",
        "DESIGN_SPACE_DEFINED",
        "EXPERIMENT_DESIGNED",
        "EXPERIMENT_RUNNING",
        "MODEL_BUILT",
        "OPTIMIZED",
        "VERIFIED",
        "APPLIED",
    ),
    "COST_DOWN": (
        "PROJECT_DEFINED",
        "FAILURE_CTQ_DEFINED",
        "DESIGN_SPACE_DEFINED",
        "EXPERIMENT_DESIGNED",
        "EXPERIMENT_RUNNING",
        "OPTIMIZED",
        "VERIFIED",
        "APPLIED",
    ),
    "CUSTOMIZATION": (
        "PROJECT_DEFINED",
        "FAILURE_CTQ_DEFINED",
        "TEST_METHODS_QUALIFIED",
        "DESIGN_SPACE_DEFINED",
        "EXPERIMENT_DESIGNED",
        "EXPERIMENT_RUNNING",
        "VERIFIED",
        "APPLIED",
    ),
    "EXPLORATION": (
        "PROJECT_DEFINED",
        "DESIGN_SPACE_DEFINED",
        "EXPERIMENT_DESIGNED",
        "EXPERIMENT_RUNNING",
        "MODEL_BUILT",
        "VERIFIED",
        "APPLIED",
    ),
    "PROCESS_ROBUSTNESS": (
        "PROJECT_DEFINED",
        "FAILURE_CTQ_DEFINED",
        "TEST_METHODS_QUALIFIED",
        "DESIGN_SPACE_DEFINED",
        "EXPERIMENT_DESIGNED",
        "EXPERIMENT_RUNNING",
        "MODEL_BUILT",
        "APPLIED",
    ),
}

# The frozen stage counts, so a swapped-in sequence of the right length still
# fails rather than passing on length coincidence.
FROZEN_OIL_ROUTE_LENGTHS = {
    "NEW_PRODUCT": 12,
    "IMPROVEMENT": 10,
    "COST_DOWN": 8,
    "CUSTOMIZATION": 8,
    "EXPLORATION": 7,
    "PROCESS_ROBUSTNESS": 8,
}

# The precision-gear grease workflow type. It has its own route and must never
# appear inside an oil route's stage sequence.
GREASE_TYPE = "PRECISION_GREASE_DEV"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_route(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(ROUTE_SCRIPT), *arguments],
        cwd=ROUTE_SCRIPT.parent,
        capture_output=True,
        text=True,
    )


def main() -> int:
    contract = read_json(CONTRACT_PATH)
    routes = contract["type_routes"]

    assert len(FROZEN_OIL_ROUTE_LENGTHS) == 6, "the frozen snapshot is six oil routes"
    for project_type, frozen in FROZEN_OIL_ROUTES.items():
        assert len(frozen) == FROZEN_OIL_ROUTE_LENGTHS[project_type], (project_type, len(frozen))

    # (1) Contract: each oil route equals the frozen literal, element by element
    #     and in order. Compared as ordered tuples, never as sets.
    for project_type, frozen in FROZEN_OIL_ROUTES.items():
        assert project_type in routes, (project_type, sorted(routes))
        actual = tuple(routes[project_type])
        assert actual == frozen, (project_type, actual, frozen)
        assert len(actual) == FROZEN_OIL_ROUTE_LENGTHS[project_type], (project_type, len(actual))

    # (2) Router: --list-stages prints the same literal for all six types.
    for project_type, frozen in FROZEN_OIL_ROUTES.items():
        listed = run_route("--list-stages", project_type)
        assert listed.returncode == 0, (project_type, listed.stdout, listed.stderr)
        assert tuple(listed.stdout.splitlines()) == frozen, (project_type, listed.stdout, frozen)

    # (3) The grease workflow type is a separate route and must not appear in any
    #     oil route sequence. Checked against BOTH the contract and the router.
    for project_type in FROZEN_OIL_ROUTES:
        assert GREASE_TYPE not in tuple(routes[project_type]), (project_type, routes[project_type])
        listed = run_route("--list-stages", project_type)
        assert listed.returncode == 0, (project_type, listed.stdout, listed.stderr)
        assert GREASE_TYPE not in listed.stdout.splitlines(), (project_type, listed.stdout)

    print(
        "PASS: six oil routes byte-identical to the contract-v0.7.0-pregate frozen snapshot "
        "(contract type_routes + route_step --list-stages); PRECISION_GREASE_DEV in no oil route"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
