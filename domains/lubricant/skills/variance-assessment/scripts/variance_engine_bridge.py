"""Import and call the frozen statistics engine from inside this skill.

The engine owns every number this skill records; this module is the only place the
skill reaches it. Two layouts are probed, exactly like the existing compute
wrappers, so the same code works in the repository tree and in a deployed bundle:

    repository:  skills/variance-assessment/scripts/  ->  domains/lubricant/
    deployed:    <skill>/scripts/                     ->  <skill>/engine/lubricant/

If neither layout holds the engine the builder stops with a HOLD. It never
substitutes a local calculation: a hand-computed statistic in this artifact would
be exactly the defect the pack forbids.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ENGINE_NAME = "statistics"
ENGINE_METHOD = "NESTED_VARIANCE_V1"


def _engine_root() -> Path | None:
    """The importable engine tree root, or None when it cannot be found."""
    script = Path(__file__).resolve()
    candidates = [
        script.parents[1] / "engine" / "lubricant",
        script.parents[3] / "domains" / "lubricant",
        script.parents[2] / "domains" / "lubricant",
    ]
    for candidate in candidates:
        if (candidate / "compute" / "statistics" / "engine.py").is_file():
            return candidate
    return None


def load_engine():
    """Return (analyze_statistics, engine_root) or (None, None) when unavailable."""
    root = _engine_root()
    if root is None:
        return None, None
    for entry in (root.parent, root.parents[1]):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    try:
        from lubricant.compute.statistics.engine import analyze_statistics  # noqa: E402
    except ImportError:
        try:
            from domains.lubricant.compute.statistics.engine import analyze_statistics  # noqa: E402
        except ImportError:
            return None, root
    return analyze_statistics, root


def canonical_bytes(payload: dict) -> bytes:
    """Canonical engine input bytes, byte-identical to the compute wrapper's digest."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def run_engine(engine_input: dict) -> tuple[dict | None, str | None, str | None]:
    """Run the engine over one variance input.

    Returns (envelope, digest, failure_reason). The digest is the SHA256 the engine
    itself computed over the canonical input bytes, so the artifact points back at
    exactly the bytes that produced its numbers. A rejection is an envelope with
    status REJECTED and reasons, never an exception; a raised exception is turned
    into a failure reason so the caller can report it instead of crashing.
    """
    import hashlib

    analyze_statistics, _ = load_engine()
    if analyze_statistics is None:
        return None, None, (
            "the statistics engine tree was not found from this skill's location; "
            "the engine must be present (repository layout: domains/lubricant/compute/statistics/engine.py)")
    raw = canonical_bytes(engine_input)
    digest = hashlib.sha256(raw).hexdigest()
    try:
        envelope = analyze_statistics(engine_input, raw)
    except Exception as error:  # noqa: BLE001 - report, never crash the build
        return None, digest, f"the statistics engine raised {type(error).__name__}: {error}"
    if not isinstance(envelope, dict):
        return None, digest, "the statistics engine returned no envelope"
    if envelope.get("status") != "OK":
        reasons = envelope.get("rejection_reasons") or ["the engine rejected the input without a reason"]
        return envelope, digest, "the statistics engine rejected the input: " + "; ".join(str(reason) for reason in reasons)
    if envelope.get("engine_name") != ENGINE_NAME:
        return envelope, digest, f"the engine reported engine_name {envelope.get('engine_name')!r}, not {ENGINE_NAME!r}"
    if envelope.get("method") != ENGINE_METHOD:
        return envelope, digest, f"the engine reported method {envelope.get('method')!r}, not {ENGINE_METHOD!r}"
    return envelope, digest, None
