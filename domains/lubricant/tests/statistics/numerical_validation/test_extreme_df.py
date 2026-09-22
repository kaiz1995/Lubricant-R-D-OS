"""Extreme-df stability checks follow Numerical Recipes, section 6.4,
continued-fraction stability properties.
"""
from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from domains.lubricant.compute.statistics.engine import f_cdf


def main():
    for df1, df2 in [(1, 1), (1, 10**6), (10**6, 1), (10**6, 10**6)]:
        values = [f_cdf(x, df1, df2) for x in (1e-6, .01, 1, 100, 1e6)]
        assert all(math.isfinite(v) and 0 <= v <= 1 for v in values)
        assert values == sorted(values)
    print("PASS: extreme degrees of freedom")


if __name__ == "__main__":
    main()
