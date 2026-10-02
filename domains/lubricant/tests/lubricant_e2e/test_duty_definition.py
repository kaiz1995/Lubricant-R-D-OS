"""Direct-run Duty Definition preflight boundary checks."""

from __future__ import annotations

import json
import shutil
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

    # WP-11: a closed history produces a hit summary; an empty history stays
    # silent and must not block the preflight (the only fail-open in the plan).
    with tempfile.TemporaryDirectory() as temporary:
        workspace = Path(temporary)
        history = workspace / "history"
        history.mkdir()
        knowledge = json.loads((ROOT / "fixtures" / "valid" / "knowledge_asset.json").read_text(encoding="utf-8"))
        knowledge["decision_question"] = (
            "Which closed-project knowledge applies to a wind turbine gearbox duty with variable-speed service?"
        )
        (history / "knowledge_asset.json").write_text(json.dumps(knowledge, ensure_ascii=False), encoding="utf-8")
        shutil.copyfile(ROOT / "fixtures" / "valid" / "design_freeze.json", history / "design_freeze.json")

        payload = json.loads((FIXTURES / "valid-input.json").read_text(encoding="utf-8"))
        # The payload moves into a temp workspace, so the fixture's relative
        # upstream reference must be repointed at the canonical artifact.
        payload["project_artifact"] = str(ROOT / "fixtures" / "duty-challenge" / "project-active.json")
        payload["history_roots"] = [str(history)]
        input_path = workspace / "duty-input.json"
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        hit = subprocess.run(
            [sys.executable, "preflight_duty_definition.py", str(input_path)],
            cwd=SCRIPT,
            capture_output=True,
            text=True,
        )
        assert hit.returncode == 0, hit.stdout + hit.stderr
        assert "READY:" in hit.stdout
        assert "history_hits=" in hit.stdout and "HISTORY_HIT[" in hit.stdout
        assert "backend=local_bm25" in hit.stdout
        assert "artifact_type=knowledge_asset" in hit.stdout or "artifact_type=design_freeze" in hit.stdout

        empty_history = workspace / "empty-history"
        empty_history.mkdir()
        payload["history_roots"] = [str(empty_history)]
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        empty = subprocess.run(
            [sys.executable, "preflight_duty_definition.py", str(input_path)],
            cwd=SCRIPT,
            capture_output=True,
            text=True,
        )
        assert empty.returncode == 0, empty.stdout + empty.stderr
        assert "READY:" in empty.stdout
        assert "history_hits" not in empty.stdout and "HISTORY_HIT" not in empty.stdout

    print("PASS: duty GAP holds without artifact")


if __name__ == "__main__":
    main()
