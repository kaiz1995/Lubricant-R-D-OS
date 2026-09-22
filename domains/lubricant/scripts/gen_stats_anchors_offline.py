"""Offline anchor generation, scipy used here only, tests hardcode results."""
from scipy.stats import f

CASES = [
    (0.01, 1, 2), (0.5, 1, 5), (1.0, 1, 10), (3.0, 1, 20),
    (10.0, 1, 100), (0.1, 2, 5), (1.5, 2, 10), (5.0, 2, 20),
    (0.25, 3, 100), (2.0, 3, 5), (4.0, 5, 10), (8.0, 10, 20),
]

print("F_CDF_ANCHORS = {")
for x, df1, df2 in CASES:
    print(f"    ({x!r}, {df1}, {df2}): {float(f.cdf(x, df1, df2))!r},")
print("}")
