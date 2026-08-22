"""Direct-run functional tests for the Phase 4.3 statistics engine."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from domains.lubricant.compute.statistics.engine import analyze_statistics

POINTS = [
    (1, 0, 0), (0, 1, 0), (0, 0, 1),
    (.5, .5, 0), (.5, 0, .5), (0, .5, .5),
]
COEFFS = [10, 20, 30, 4, -6, 8]


def response(point):
    a, b, c = point
    row = [a, b, c, a*b, a*c, b*c]
    return sum(x*y for x, y in zip(row, COEFFS))


def make_input(points=POINTS, noise=None, model="QUADRATIC"):
    if noise is None:
        noise = [0.0] * len(points)
    return {
        "input_type": "STATISTICAL_ANALYSIS",
        "components": [{"component_id": x} for x in "ABC"],
        "model_order": model,
        "response_ctq": "KV40",
        "design_points": [
            {"run_reference": f"R{i+1:02d}", "proportions": dict(zip("ABC", p))}
            for i, p in enumerate(points)
        ],
        "observations": [
            {"run_reference": f"R{i+1:02d}", "ctq_reference": "KV40",
             "value": response(p) + noise[i]}
            for i, p in enumerate(points)
        ],
        "requested_analyses": ["ANOVA", "REGRESSION", "RESIDUAL", "LACK_OF_FIT"],
    }


def run(data):
    raw = (json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    return analyze_statistics(data, raw)


def rejected(data):
    env = run(data)
    assert env["status"] == "REJECTED", env
    assert env["rejection_reasons"]


def main():
    replicated = POINTS + POINTS
    noise = [1e-10] * 6 + [-1e-10] * 6
    env = run(make_input(replicated, noise))
    assert env["status"] == "OK", env
    estimates = [row["estimate"] for row in env["result"]["coefficients"]]
    assert max(abs(a-b) for a, b in zip(estimates, COEFFS)) < 1e-9
    assert env["result"]["fit_statistics"]["r_squared"] > .999999999
    assert env["result"]["anova_table"]
    assert env["result"]["lack_of_fit"]["status"] == "COMPUTED"

    perfect = run(make_input())
    assert perfect["status"] == "OK"
    assert perfect["result"]["fit_statistics"]["r_squared"] == 1.0
    assert perfect["result"]["lack_of_fit"]["status"] == "NOT_APPLICABLE"

    rejected(make_input([(1, 0, 0)] * 6))
    rejected(make_input(POINTS[:5]))
    bad_sum = make_input()
    bad_sum["design_points"][0]["proportions"]["A"] = .9
    rejected(bad_sum)
    missing = make_input()
    missing["observations"][0]["run_reference"] = "MISSING"
    rejected(missing)
    duplicate = make_input()
    duplicate["observations"].append(copy.deepcopy(duplicate["observations"][0]))
    rejected(duplicate)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        inp, out1, out2 = td / "in.json", td / "a.json", td / "b.json"
        inp.write_bytes((json.dumps(make_input(), ensure_ascii=False, sort_keys=True) + "\n").encode())
        cmd = [sys.executable, "-m", "domains.lubricant.compute.statistics.engine", str(inp)]
        subprocess.run(cmd + [str(out1)], cwd=ROOT, check=True)
        subprocess.run(cmd + [str(out2)], cwd=ROOT, check=True)
        assert out1.read_bytes() == out2.read_bytes()

    fixture_dir = ROOT / "fixtures" / "compute"
    expected_hashes = {
        "statistics-gold-input.json": "d17cba69c8f1c61e04a7ec755d23b8da7559d6633b50e18118accae13e0b1512",
        "statistics-gold-output.json": "4bab7b2c494a08dca061daef916cc04730851606ab2cfa63e5c8e46d9ba62bf4",
    }
    for name, expected in expected_hashes.items():
        assert hashlib.sha256((fixture_dir / name).read_bytes()).hexdigest() == expected
    print("PASS: statistics engine functional, rejection, determinism, golden hashes")


if __name__ == "__main__":
    main()
