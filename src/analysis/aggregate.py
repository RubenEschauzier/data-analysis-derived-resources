"""Two-stage aggregation: median over replications, geometric mean over instances.

Pooling all runs of a template into one median treats a replication of an easy
instance and a replication of a hard one as interchangeable observations. They
are not. On `interactive-discover-6` the five instance medians for `adaptive`
are roughly 116s, 1.9s, 1.7s, 113s, 2.0s -- a bimodal mixture whose pooled
median lands on whichever mode happens to hold three of the five instances, and
moves by two orders of magnitude if one instance flips side.

So the collapse happens in two stages, each with the estimator that fits what
it is summarising:

1. **Replications -> one value per instance.** A median: replications of the
   same query differ only by run-to-run noise, and the median is robust to the
   occasional stalled run.
2. **Instances -> one value per template.** A geometric mean: timings are
   ratio-scaled and right-skewed, so the arithmetic mean is dragged by the
   slowest instance, and a second median would discard the slow instances
   entirely rather than weigh them. The geometric mean is also the only mean
   under which "engine A is 2x engine B" survives aggregation -- the geomean of
   the ratios equals the ratio of the geomeans, so the summary and the per-query
   speedups cannot disagree.

Every instance gets equal weight at stage 2 regardless of how many replications
survived, which is the point: an engine cannot shift a template's summary by
failing more often on the hard instance.

Geometric means need strictly positive values. Non-positive observations (a
throughput of zero, from a run that delivered nothing) are dropped and counted
in `n_dropped` rather than silently coerced.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .loading import engine_order, template_order


def geomean(values: "pd.Series | np.ndarray") -> float:
    """Geometric mean of the strictly positive entries; NaN if none remain."""
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size == 0:
        return float("nan")
    return float(np.exp(np.log(arr).mean()))


def geo_sd(values: "pd.Series | np.ndarray") -> float:
    """Multiplicative (geometric) standard deviation -- a factor, not an offset.

    1.0 means every instance agreed exactly; 3.0 means the typical instance sits
    within a factor of three of the geometric mean.
    """
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr) & (arr > 0)]
    if arr.size < 2:
        return float("nan")
    return float(np.exp(np.log(arr).std(ddof=1)))


def per_instance(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Stage 1: one row per (engine, template, instance), median over replications.

    Successful runs only. This frame is the unit of every comparison downstream,
    and is worth looking at directly when a template's summary looks strange.
    """
    ok = df[~df["failed"]].dropna(subset=[metric])
    stage1 = ok.groupby(["engine", "template", "instance"])[metric].agg(
        value="median", runs="size").reset_index()
    return stage1


def per_instance_all_runs(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """`per_instance` over every run, failed ones included.

    For the progress metrics -- results delivered, throughput, time to first
    result -- a timed-out run's partial output is a real measurement, and a
    template that no engine ever completes is exactly where an engine can
    regress unseen by the completed-only view. `completed` counts the
    replications that finished, so a caller can tell the two cases apart.
    """
    runs = df.assign(**{metric: pd.to_numeric(df[metric], errors="coerce")})
    runs = runs.dropna(subset=[metric])
    stage1 = runs.groupby(["engine", "template", "instance"]).agg(
        value=(metric, "median"), runs=(metric, "size"),
        completed=("failed", lambda f: int((~f).sum()))).reset_index()
    return stage1


def two_stage(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Stage 2: one row per (template, engine), geometric mean over instances.

    `low` / `high` are the smallest and largest *instance* medians, not a
    quantile over runs: the error bar answers "how differently do the instances
    of this template behave", which is the spread that actually moves the
    summary. `geo_sd` is the same spread as a single factor.
    """
    stage1 = per_instance(df, metric)
    rows = []
    for (template, engine), group in stage1.groupby(["template", "engine"]):
        values = group["value"].astype(float)
        positive = values[np.isfinite(values) & (values > 0)]
        rows.append({
            "template": template,
            "engine": engine,
            "geomean": geomean(values),
            "median_of_instances": float(positive.median()) if len(positive) else np.nan,
            "low": float(positive.min()) if len(positive) else np.nan,
            "high": float(positive.max()) if len(positive) else np.nan,
            "geo_sd": geo_sd(values),
            "n_instances": int(len(positive)),
            "n_runs": int(group["runs"].sum()),
            "n_dropped": int(len(values) - len(positive)),
        })
    return pd.DataFrame(rows)


def two_stage_table(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """`two_stage` widened to one row per template, one column group per engine.

    `vs_<baseline>` is the ratio of geometric means, which -- because the
    geomean is multiplicative -- is also the geometric mean of the per-instance
    ratios. The two ways of asking the question give the same number here.
    """
    engines = engine_order(df)
    baseline = engines[0]
    stats = two_stage(df, metric).set_index(["template", "engine"])

    rows = []
    for template in template_order(df):
        row = {"template": template}
        values = {}
        for engine in engines:
            if (template, engine) not in stats.index:
                row[f"geomean::{engine}"] = pd.NA
                row[f"instance_range::{engine}"] = "-"
                row[f"geo_sd::{engine}"] = pd.NA
                continue
            cell = stats.loc[(template, engine)]
            values[engine] = cell["geomean"]
            row[f"geomean::{engine}"] = round(cell["geomean"], 1)
            row[f"instance_range::{engine}"] = f"{cell['low']:.0f}-{cell['high']:.0f}"
            row[f"geo_sd::{engine}"] = round(cell["geo_sd"], 2) if pd.notna(cell["geo_sd"]) else pd.NA
            row[f"instances::{engine}"] = cell["n_instances"]
        for engine in engines[1:]:
            row[f"vs_{baseline}::{engine}"] = (
                round(values[engine] / values[baseline], 2)
                if values.get(baseline) and engine in values else pd.NA)
        rows.append(row)
    return pd.DataFrame(rows)
