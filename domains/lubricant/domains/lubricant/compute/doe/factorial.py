"""Pure-stdlib two-level factorial design core (WP-04a spike).

No network access and no third-party dependency: the same factor list always
produces the same matrix, byte for byte. Only two-level factors are supported:
the coded level is -1 for the lower setting and +1 for the upper setting, so an
interaction column is simply the element-wise product of its factor columns.

Run the spike demo directly:

    python -m domains.lubricant.compute.doe.factorial
"""

from __future__ import annotations

import itertools
import math
import sys


LOW, HIGH = -1.0, 1.0


def two_level_runs(factor_ids: tuple[str, ...]) -> list[dict[str, float]]:
    """Full 2^k matrix in a fixed (Yates) order: the first factor varies slowest."""
    return [dict(zip(factor_ids, combo)) for combo in itertools.product((LOW, HIGH), repeat=len(factor_ids))]


def interaction_terms(factor_ids: tuple[str, ...], max_order: int = 2) -> list[tuple[str, tuple[str, ...]]]:
    """Deterministic interaction list: all 2..max_order-way products, in factor order."""
    terms: list[tuple[str, tuple[str, ...]]] = []
    for order in range(2, max_order + 1):
        for combo in itertools.combinations(factor_ids, order):
            terms.append(("*".join(combo), combo))
    return terms


def column_values(column_factors: tuple[str, ...], runs: list[dict[str, float]]) -> list[float]:
    """Element-wise product of the coded values of `column_factors` for every run."""
    return [math.prod(run[factor] for factor in column_factors) for run in runs]


def orthogonality_report(columns: dict[str, list[float]]) -> dict[str, object]:
    """Sum and pairwise inner product of every coded column (an orthogonal design sums to zero)."""
    ids = sorted(columns)
    sums = {column_id: math.fsum(columns[column_id]) for column_id in ids}
    pairs = {
        f"{left}x{right}": math.fsum(a * b for a, b in zip(columns[left], columns[right]))
        for left, right in itertools.combinations(ids, 2)
    }
    return {
        "column_count": len(ids),
        "sums": sums,
        "pairwise_inner_products": pairs,
        "orthogonal": all(value == 0.0 for value in sums.values()) and all(value == 0.0 for value in pairs.values()),
    }


def main() -> int:
    factor_ids = ("A", "B", "C")
    runs = two_level_runs(factor_ids)
    columns = {factor: column_values((factor,), runs) for factor in factor_ids}
    terms = interaction_terms(factor_ids, max_order=len(factor_ids))
    for column_id, combo in terms:
        columns[column_id] = column_values(combo, runs)

    order = [*factor_ids, *(column_id for column_id, _ in terms)]
    print(f"SPIKE two-level full factorial: {len(factor_ids)} factors -> {len(runs)} runs, coded levels -1/+1")
    print("run  " + "  ".join(f"{column_id:>6}" for column_id in order))
    for index, run in enumerate(runs, start=1):
        print(f"{index:>3}  " + "  ".join(f"{columns[column_id][index - 1]:>6.0f}" for column_id in order))
    report = orthogonality_report(columns)
    print(f"columns={report['column_count']} orthogonal={report['orthogonal']}")
    print("column sums: " + ", ".join(f"{column_id}={report['sums'][column_id]:.0f}" for column_id in order))
    zero = [key for key, value in report["pairwise_inner_products"].items() if value != 0.0]
    print(f"non-orthogonal pairs: {zero if zero else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
