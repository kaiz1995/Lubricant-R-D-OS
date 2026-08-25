"""Direct-run tests for the unified compute dispatcher."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "compute"


def run(engine: str, payload: bytes) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "domains.lubricant.compute", "--engine", engine],
        cwd=ROOT,
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def main() -> None:
    for engine in ("cost", "doe", "statistics", "optimization"):
        payload = (FIXTURES / f"{engine}-gold-input.json").read_bytes()
        completed = run(engine, payload)
        assert completed.returncode == 0, completed.stderr.decode()
        result = json.loads(completed.stdout)
        assert result["status"] == "OK", result
        assert result["engine_name"] == engine
        assert result["input_digest"] == hashlib.sha256(payload).hexdigest()

    unknown = subprocess.run(
        [sys.executable, "-m", "domains.lubricant.compute", "--engine", "unknown"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert unknown.returncode != 0
    assert b"invalid choice" in unknown.stderr

    bad_json = run("cost", b"{")
    assert bad_json.returncode != 0
    assert b"input JSON failed" in bad_json.stderr
    assert not bad_json.stdout
    print("PASS: compute dispatcher")


if __name__ == "__main__":
    main()
