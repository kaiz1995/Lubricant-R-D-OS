"""Anchor values generated offline via scipy.stats.f.cdf v1.17.1.

See scripts/gen_stats_anchors_offline.py.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from domains.lubricant.compute.statistics.engine import f_cdf
from anchors import F_CDF_ANCHORS


def main():
    for (x, df1, df2), expected in F_CDF_ANCHORS.items():
        assert abs(f_cdf(x, df1, df2) - expected) <= 1e-12
    assert abs(f_cdf(1.0, 1, 1) - 0.5) <= 1e-6
    assert abs(f_cdf(4.964602743730712, 1, 10) - 0.95) <= 1e-6
    assert abs(f_cdf(3.3258345304130104, 5, 10) - 0.95) <= 1e-6
    print("PASS: known F CDF and p-value anchors")


if __name__ == "__main__":
    main()
