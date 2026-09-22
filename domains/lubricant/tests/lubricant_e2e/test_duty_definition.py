"""Direct-run Duty Definition preflight boundary checks."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "duty-definition" / "scripts"
CHALLENGE_SCRIPT = ROOT / "skills" / "duty-challenge-analysis" / "scripts"
FIXTURES = ROOT / "fixtures" / "duty-definition"


def main() -> None:
    gap = subprocess.run([sys.executable, "preflight_duty_definition.py", str(FIXTURES / "invalid-gap-input.json")], cwd=SCRIPT, capture_output=True, text=True)
    assert gap.returncode != 0 and "HOLD:" in gap.stdout and "GAP requires resolution" in gap.stdout
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "duty.json"
        build = subprocess.run([sys.executable, "build_duty_artifact.py", str(FIXTURES / "invalid-gap-input.json"), str(target)], cwd=SCRIPT, capture_output=True, text=True)
        assert build.returncode != 0 and "HOLD:" in build.stdout and not target.exists()

    with tempfile.TemporaryDirectory() as temporary:
        duty_path = Path(temporary) / "duty.json"
        build = subprocess.run(
            [sys.executable, "build_duty_artifact.py", str(FIXTURES / "valid-input.json"), str(duty_path)],
            cwd=SCRIPT,
            capture_output=True,
            text=True,
        )
        assert build.returncode == 0, build.stdout + build.stderr
        challenge_input = json.loads((ROOT / "fixtures" / "duty-challenge" / "valid-input.json").read_text(encoding="utf-8"))
        challenge_input["duty_artifact"] = str(duty_path)
        challenge_path = Path(temporary) / "challenge-input.json"
        challenge_path.write_text(json.dumps(challenge_input), encoding="utf-8")
        challenge = subprocess.run(
            [sys.executable, "preflight_duty_challenge.py", str(challenge_path)],
            cwd=CHALLENGE_SCRIPT,
            capture_output=True,
            text=True,
        )
        assert challenge.returncode == 0, challenge.stdout + challenge.stderr
        duty = json.loads(duty_path.read_text(encoding="utf-8"))
        assert {item["status"] for item in duty["duty"].values()} == {"ASSUMED"}
    print("PASS: duty GAP holds without artifact")


if __name__ == "__main__":
    main()
