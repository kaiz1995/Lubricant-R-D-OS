"""Pure-stdlib two-level factorial design core (WP-04a).

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


def half_fraction_runs(factor_ids: tuple[str, ...]) -> list[dict[str, float]]:
    """2^(k-1) half fraction: the last factor is the product of the first k-1.

    The defining generator is therefore the highest-order interaction, which is
    reported back through the aliasing groups so the design is never silently
    presented as a full factorial.
    """
    base, defined = factor_ids[:-1], factor_ids[-1]
    return [{**run, defined: math.prod(run[factor] for factor in base)} for run in two_level_runs(base)]


def split_plot_runs(whole_ids: tuple[str, ...], sub_ids: tuple[str, ...], replicates: int) -> list[tuple[int, dict[str, float]]]:
    """W x S x r runs as (whole_plot_index, settings).

    One whole-plot unit is a (replicate, whole-plot setting) pair; every sub-plot
    combination runs inside it consecutively, which is what makes the whole-plot
    error estimable.
    """
    whole_runs = two_level_runs(whole_ids) if whole_ids else [{}]
    sub_runs = two_level_runs(sub_ids) if sub_ids else [{}]
    runs: list[tuple[int, dict[str, float]]] = []
    whole_plot_index = 0
    for _replicate in range(replicates):
        for whole in whole_runs:
            whole_plot_index += 1
            for sub in sub_runs:
                runs.append((whole_plot_index, {**whole, **sub}))
    return runs


def effect_names(factor_ids: tuple[str, ...], max_order: int | None = None) -> list[tuple[str, ...]]:
    """All effect names: main effects first, then higher-order interactions in factor order."""
    if max_order is None:
        max_order = len(factor_ids)
    names: list[tuple[str, ...]] = []
    for order in range(1, max_order + 1):
        names.extend(itertools.combinations(factor_ids, order))
    return names


def interaction_terms(factor_ids: tuple[str, ...], max_order: int = 2) -> list[tuple[str, tuple[str, ...]]]:
    """Deterministic interaction list: all 2..max_order-way products, in factor order."""
    return [("*".join(combo), combo) for order in range(2, max_order + 1) for combo in itertools.combinations(factor_ids, order)]


def column_values(column_factors: tuple[str, ...], runs: list[dict[str, float]]) -> list[float]:
    """Element-wise product of the coded values of `column_factors` for every run."""
    return [math.prod(run[factor] for factor in column_factors) for run in runs]


def effect_columns(factor_ids: tuple[str, ...], runs: list[dict[str, float]]) -> list[dict[str, object]]:
    """One entry per distinct contrast vector; effects that are aliased share an entry.

    A full factorial yields one entry per effect (no aliases). A half fraction merges
    each effect with its aliases, and the primary name prefers the shortest (main
    effect) member, so aliasing can never be hidden from the caller.
    """
    buckets: dict[tuple[float, ...], list[tuple[str, ...]]] = {}
    for name in effect_names(factor_ids):
        buckets.setdefault(tuple(column_values(name, runs)), []).append(name)
    columns: list[dict[str, object]] = []
    for _key, members in sorted(buckets.items(), key=lambda item: (len(item[1][0]), item[1][0])):
        members = sorted(members, key=lambda name: (len(name), name))
        primary = members[0]
        columns.append({
            "column_id": "*".join(primary),
            "kind": "MAIN_EFFECT" if len(primary) == 1 else "INTERACTION",
            "factors": list(primary),
            "coded_levels": [int(value) for value in column_values(primary, runs)],
            **({"aliases": ["*".join(member) for member in members[1:]]} if len(members) > 1 else {}),
        })
    return columns


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


def _zero_df_pooling(scope: str) -> str:
    if scope == "WHOLE_PLOT":
        return "0 df: whole-plot effects are not separable from the whole-plot error at this replicate count; replicate the whole-plot units or pool the whole-plot error explicitly."
    if scope == "SUB_PLOT":
        return "0 df: sub-plot effects must be pooled with the whole-plot x sub-plot interaction (assumed negligible) or replicated."
    return "0 df: the model is saturated; add replicates or drop non-estimable effects before reading an error term."


def split_plot_error_terms(whole_count: int, sub_count: int, replicates: int, remaining: int) -> list[dict[str, object]]:
    """Classical split-plot error split: whole-plot residual then sub-plot residual.

    `remaining` is total - replicate - model; the whole-plot error keeps at most its
    classical (r-1)(W-1) degrees of freedom and the rest belongs to the sub-plot
    error, which is where unestimated (pooled) interactions land.
    """
    whole_df = min((replicates - 1) * (whole_count - 1), remaining)
    sub_df = remaining - whole_df
    terms = [
        {"term_id": "WHOLE_PLOT_ERROR", "scope": "WHOLE_PLOT", "degrees_of_freedom": whole_df, "source": "RESIDUAL"},
        {"term_id": "SUB_PLOT_ERROR", "scope": "SUB_PLOT", "degrees_of_freedom": sub_df, "source": "RESIDUAL"},
    ]
    for term in terms:
        if term["degrees_of_freedom"] == 0:
            term["pooling"] = _zero_df_pooling(str(term["scope"]))
    return terms


def plot_error_term(remaining: int) -> list[dict[str, object]]:
    """Residual of a plain (non-split) factorial: a single plot-scope error term."""
    term: dict[str, object] = {"term_id": "PLOT_ERROR", "scope": "PLOT", "degrees_of_freedom": remaining, "source": "RESIDUAL"}
    if remaining == 0:
        term["pooling"] = _zero_df_pooling("PLOT")
    return [term]


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
