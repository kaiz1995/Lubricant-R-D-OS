"""Direct-run tests for the evidence-scope compute wrappers."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "compute"
SKILLS = {
    "formulation-design": "cost",
    "doe-design": "doe",
    "statistical-analysis": "statistics",
    "optimization": "optimization",
}


def run_wrapper(skill: str, payload: dict) -> subprocess.CompletedProcess:
    script = ROOT / "skills" / skill / "scripts" / "run_compute.py"
    return subprocess.run(
        [sys.executable, "-B", str(script)],
        cwd=ROOT,
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def main() -> None:
    for skill, engine in SKILLS.items():
        fixture = FIXTURES / f"{engine}-gold-input.json"
        payload = json.loads(fixture.read_text(encoding="utf-8"))

        missing = run_wrapper(skill, {key: value for key, value in payload.items() if key != "evidence_scope"})
        assert missing.returncode != 0, skill
        assert b"evidence_scope" in missing.stderr, missing.stderr

        physical = run_wrapper(skill, {**payload, "evidence_scope": "PHYSICAL"})
        assert physical.returncode == 0, (skill, physical.stderr.decode())
        physical_out = json.loads(physical.stdout)
        assert physical_out["evidence_scope"] == "PHYSICAL"
        assert physical_out["result"]["status"] == "OK", physical_out["result"]
        assert physical_out["result"]["engine_name"] == engine
        assert physical_out["input_sha256"] == hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        synthetic = run_wrapper(skill, {**payload, "evidence_scope": "SYNTHETIC"})
        assert synthetic.returncode == 0, (skill, synthetic.stderr.decode())
        synthetic_out = json.loads(synthetic.stdout)
        assert synthetic_out["evidence_scope"] == "SYNTHETIC"
        assert synthetic_out["usage_constraints"] == [
            "SYNTHETIC_DEMO_ONLY",
            "NOT_FOR_PHYSICAL_RELEASE",
            "CANNOT_QUALIFY_METHOD",
        ]
        assert synthetic_out["input_sha256"] == physical_out["input_sha256"]
        assert synthetic_out["result"] == physical_out["result"]

        bad_scope = run_wrapper(skill, {**payload, "evidence_scope": "LAB"})
        assert bad_scope.returncode != 0, skill
        assert b"SYNTHETIC or PHYSICAL" in bad_scope.stderr, bad_scope.stderr

    print(f"PASS: evidence-scope compute wrappers for {len(SKILLS)} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

