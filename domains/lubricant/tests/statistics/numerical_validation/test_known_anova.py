"""One-way ANOVA verification methodology: Montgomery,
Design and Analysis of Experiments.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from domains.lubricant.compute.statistics.engine import (
    _anova_type1, _build_design_matrix, _ols, f_pvalue,
)


def main():
    # One-way ANOVA for the stated layout. Exact hand values differ from the
    # phase prompt: SS_treatment=841/6 and SS_error=8/3, hence F=841/4.
    y = [10, 11, 10, 20, 21, 19]
    X = [[1.0, 0.0]] * 3 + [[1.0, 1.0]] * 3
    beta, _, sse = _ols(X, y)
    mse = sse / 4
    rows = _anova_type1(X, y, ["INTERCEPT", "TREATMENT"], 4, mse)
    intercept = rows[0]
    treatment = rows[1]
    residual = rows[2]
    total = sum((v - sum(y) / len(y)) ** 2 for v in y)
    assert abs(total - 857 / 6) < 1e-12
    assert abs(intercept["sum_squares"] - 857 / 6) < 1e-12
    assert abs(treatment["sum_squares"] - 841 / 6) < 1e-12
    assert abs(residual["sum_squares"] - 8 / 3) < 1e-12
    assert abs(sse - 8 / 3) < 1e-12
    assert abs(mse - 2 / 3) < 1e-12
    assert abs(treatment["f_value"] - 841 / 4) < 1e-10
    assert abs(treatment["p_value"] - f_pvalue(841 / 4, 1, 4)) < 1e-15

    points = [
        {"proportions": {"A": 1, "B": 0, "C": 0}},
        {"proportions": {"A": 0, "B": 1, "C": 0}},
        {"proportions": {"A": 0, "B": 0, "C": 1}},
        {"proportions": {"A": .5, "B": .5, "C": 0}},
        {"proportions": {"A": .5, "B": 0, "C": .5}},
        {"proportions": {"A": 0, "B": .5, "C": .5}},
    ]
    Xq, terms = _build_design_matrix(points, ["A", "B", "C"], "QUADRATIC")
    expected = [10, 20, 30, 4, -6, 8]
    yq = [sum(row[i] * expected[i] for i in range(6)) for row in Xq]
    got, _, rss = _ols(Xq, yq)
    assert terms == ["x_A", "x_B", "x_C", "x_A*x_B", "x_A*x_C", "x_B*x_C"]
    assert max(abs(a - b) for a, b in zip(got, expected)) < 1e-10
    assert rss < 1e-24
    print("PASS: known ANOVA and quadratic OLS")


if __name__ == "__main__":
    main()
