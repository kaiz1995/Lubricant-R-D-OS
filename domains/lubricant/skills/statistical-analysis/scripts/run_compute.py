"""Run the statistics engine behind the evidence-scope boundary.

stdin JSON needs top-level evidence_scope in {SYNTHETIC, PHYSICAL}.
stdout: {"evidence_scope", "input_sha256", "result", "usage_constraints"?}
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ENGINE = "statistics"
USAGE_CONSTRAINTS = [
    "SYNTHETIC_DEMO_ONLY",
    "NOT_FOR_PHYSICAL_RELEASE",
    "CANNOT_QUALIFY_METHOD",
]


def _canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _engine_root():
    script = Path(__file__).resolve()
    candidates = [
        script.parents[1] / "engine" / "lubricant",
        script.parents[3] / "domains" / "lubricant",
    ]
    for candidate in candidates:
        if (candidate / "compute" / "__main__.py").is_file():
            return candidate
    return None


def _import_engines(engine_root):
    """Make the engine tree importable, including the optimization absolute import."""
    sys.path.insert(0, str(engine_root.parent))
    sys.path.insert(0, str(engine_root.parents[1]))
    if not (engine_root.parents[1] / "domains").is_dir():
        # Installed layout has no real domains package; alias the engine tree under
        # the domains.* namespace used by the frozen optimization engine import.
        import types

        import lubricant.compute.cost.engine as cost_twin

        domains = types.ModuleType("domains")
        domains.__path__ = []
        sys.modules["domains"] = domains
        sys.modules["domains.lubricant"] = sys.modules["lubricant"]
        sys.modules["domains.lubricant.compute"] = sys.modules["lubricant.compute"]
        sys.modules["domains.lubricant.compute.cost"] = sys.modules["lubricant.compute.cost"]
        sys.modules["domains.lubricant.compute.cost.engine"] = cost_twin
    from lubricant.compute.__main__ import ENGINES  # noqa: E402

    return ENGINES


def main():
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as error:
        print(f"FAIL: input JSON failed: {error}", file=sys.stderr)
        return 1
    if not isinstance(data, dict) or "evidence_scope" not in data:
        print("FAIL: top-level evidence_scope is required", file=sys.stderr)
        return 1
    scope = data["evidence_scope"]
    if scope not in {"SYNTHETIC", "PHYSICAL"}:
        print(f"FAIL: evidence_scope must be SYNTHETIC or PHYSICAL, got {scope!r}", file=sys.stderr)
        return 1
    engine_root = _engine_root()
    if engine_root is None:
        print("FAIL: lubricant engine tree not found", file=sys.stderr)
        return 1
    payload = {key: value for key, value in data.items() if key != "evidence_scope"}
    raw = _canonical(payload)
    try:
        result = _import_engines(engine_root)[ENGINE](payload, raw)
    except Exception as error:
        print(f"FAIL: {ENGINE} engine failed: {error}", file=sys.stderr)
        return 1
    output = {
        "evidence_scope": scope,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "result": result,
    }
    if scope == "SYNTHETIC":
        output["usage_constraints"] = USAGE_CONSTRAINTS
    sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

