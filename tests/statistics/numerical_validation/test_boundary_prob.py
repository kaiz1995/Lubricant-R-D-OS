"""Checks the standard identity I_x(a,b) + I_(1-x)(b,a) = 1."""
from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from domains.lubricant.compute.statistics.engine import _regularized_beta, f_cdf


def main():
    for df1, df2 in [(1, 1), (2, 10), (10, 100)]:
        assert f_cdf(0, df1, df2) == 0
        assert f_cdf(math.inf, df1, df2) == 1
        values = [f_cdf(x, df1, df2) for x in (0, .001, .1, 1, 10, 1000)]
        assert values == sorted(values)
    for x, a, b in [(.1, .5, 5), (.5, 2, 3), (.9, 10, .5)]:
        assert abs(_regularized_beta(x, a, b) + _regularized_beta(1-x, b, a) - 1) < 1e-12
    print("PASS: probability boundaries, symmetry, monotonicity")


if __name__ == "__main__":
    main()
