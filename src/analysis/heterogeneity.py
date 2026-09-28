"""Do different instantiations of one template behave like one query, or many?

A template is a query *shape*; each instance binds it to different constants.
If the instances of a template behaved alike, a template-level summary would be
a fair description of them and the replications would be the only source of
spread. They do not. These three views quantify that, and each answers a
question the template-level tables cannot:

- `variance_decomposition`  how much of the spread is *between* instances rather
  than run-to-run noise, per engine per template.
- `instance_ratio_spread`   whether the engine comparison itself holds per
  instance, or whether the template-level ratio is an average over instances
  that disagree about the direction.
- `winner_by_instance`      which engine is fastest on each individual instance.

All three work on log-transformed values. Timings are ratio-scaled, so "twice as
slow" is the natural unit of difference, and a variance computed on raw
milliseconds would be dominated by whichever instance is slowest in absolute
terms rather than by the one that is most out of line.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .aggregate import geomean, per_instance
from .loading import engine_order, template_order


def _ordered(table: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    order = {t: i for i, t in enumerate(template_order(df))}
    table = table.copy()
    table["_order"] = table["template"].map(order)
    return (table.sort_values(["_order", "template"])
            .drop(columns="_order").reset_index(drop=True))


def variance_decomposition(df: pd.DataFrame, metric: str = "time_ms") -> pd.DataFrame:
    """Split log-scale spread into a between-instance and a within-instance part.

    `instance_share` is the fraction of total variance that lies between
    instances -- an intraclass correlation. Near 0, the instances of the
    template are interchangeable and the pooled summary is honest. Near 1, the
    template is really several different queries wearing one name, and *any*
    single number for it, median or geometric mean, is a summary of a mixture.

    `spread_factor` is the same thing in readable units: the ratio between the
    slowest and fastest instance median. `run_noise_factor` is the typical
    multiplicative spread *within* one instance, for comparison -- when
    `spread_factor` dwarfs it, re-running the benchmark more times cannot
    narrow the uncertainty, because the uncertainty is not noise.
    """
    ok = df[~df["failed"]].dropna(subset=[metric])
    ok = ok[ok[metric].astype(float) > 0]

    rows = []
    for (engine, template), group in ok.groupby(["engine", "template"]):
        logs = np.log(group[metric].astype(float))
        by_instance = logs.groupby(group["instance"])
        means = by_instance.mean()
        if len(means) < 2:
            continue
        # Between: variance of the per-instance means. Within: pooled variance
        # of the replications around their own instance mean.
        between = float(means.var(ddof=1))
        counts = by_instance.size()
        variances = by_instance.var(ddof=1)
        usable = counts[counts > 1].index
        within = (float((variances[usable] * (counts[usable] - 1)).sum()
                        / (counts[usable] - 1).sum()) if len(usable) else np.nan)
        total = between + (within if np.isfinite(within) else 0.0)

        instance_medians = group.groupby("instance")[metric].median().astype(float)
        rows.append({
            "template": template,
            "engine": engine,
            "instances": int(len(means)),
            "instance_share": round(between / total, 3) if total > 0 else np.nan,
            "spread_factor": round(float(instance_medians.max() / instance_medians.min()), 2),
            "run_noise_factor": (round(float(np.exp(np.sqrt(within))), 2)
                                 if np.isfinite(within) else pd.NA),
            "slowest_instance": str(instance_medians.idxmax()),
            "fastest_instance": str(instance_medians.idxmin()),
        })

    table = pd.DataFrame(rows)
    if table.empty:
        return table
    engines = {e: i for i, e in enumerate(engine_order(df))}
    table["_e"] = table["engine"].map(engines)
    table = table.sort_values("_e").drop(columns="_e")
    return _ordered(table, df)


def instance_ratio_spread(df: pd.DataFrame, metric: str = "time_ms") -> pd.DataFrame:
    """The engine comparison recomputed per instance, then summarised.

    `ratio_geomean` is the template-level speedup; `ratio_min` and `ratio_max`
    are the best and worst it looks on an individual instance. A row whose range
    straddles 1.0 is a template where the engines trade wins instance by
    instance, and reporting only the geomean would state a direction the data
    does not support -- `direction_agrees` counts how many instances point the
    same way as the summary.

    Matched instances only: an instance counts only where both engines produced
    a value, so the ratio is never taken across different queries.
    """
    engines = engine_order(df)
    baseline = engines[0]
    stage1 = per_instance(df, metric)
    wide = stage1.pivot_table(index=["template", "instance"], columns="engine",
                              values="value")

    rows = []
    for template in template_order(df):
        if template not in wide.index.get_level_values("template"):
            continue
        block = wide.loc[template]
        if baseline not in block.columns:
            continue
        for engine in engines[1:]:
            if engine not in block.columns:
                continue
            pair = block[[baseline, engine]].dropna()
            pair = pair[(pair[baseline] > 0) & (pair[engine] > 0)]
            if pair.empty:
                continue
            ratios = (pair[engine] / pair[baseline]).astype(float)
            summary = geomean(ratios)
            faster = summary < 1
            agree = int(((ratios < 1) == faster).sum())
            rows.append({
                "template": template,
                "engine": engine,
                "instances": len(ratios),
                "ratio_geomean": round(summary, 2),
                "ratio_min": round(float(ratios.min()), 2),
                "ratio_max": round(float(ratios.max()), 2),
                "direction_agrees": f"{agree}/{len(ratios)}",
                "straddles_break_even": "yes" if ratios.min() < 1 < ratios.max() else "no",
            })
    table = pd.DataFrame(rows)
    return _ordered(table, df) if not table.empty else table


def winner_by_instance(df: pd.DataFrame, metric: str = "time_ms") -> pd.DataFrame:
    """Which engine is fastest on each individual instance of each template.

    The template-level tables report one winner per template. This says whether
    that winner won every instance or merely most of them -- and on the
    templates where instances disagree, the per-template ranking is an artefact
    of which instances happened to be in the workload.
    """
    engines = engine_order(df)
    stage1 = per_instance(df, metric)
    wide = stage1.pivot_table(index=["template", "instance"], columns="engine",
                              values="value")
    present = [e for e in engines if e in wide.columns]
    complete = wide[present].dropna()

    rows = []
    for template, block in complete.groupby(level="template"):
        winners = block.idxmin(axis=1)
        counts = winners.value_counts()
        row = {"template": template, "instances_compared": len(block)}
        for engine in present:
            row[f"wins::{engine}"] = int(counts.get(engine, 0))
        row["unanimous"] = "yes" if len(counts) == 1 else "no"
        row["per_instance_winner"] = ", ".join(
            f"{instance}:{winner}" for (_, instance), winner in winners.items())
        rows.append(row)
    table = pd.DataFrame(rows)
    return _ordered(table, df) if not table.empty else table
