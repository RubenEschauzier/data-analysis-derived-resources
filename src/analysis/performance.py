"""Per-template performance summary, with each engine indexed to the baseline."""

from __future__ import annotations

import pandas as pd

import numpy as np

from .aggregate import (MATCHED_METRICS, estimator_label, matched_instances,
                        runs_for_metric, table_precision, two_stage)
from .loading import engine_order, template_order

METRICS = ["time_ms", "http_requests", "first_result_ms", "last_result_ms",
           "answer_rate_per_s"]


def per_template_performance(df: pd.DataFrame, metric: str = "time_ms") -> pd.DataFrame:
    """Two-stage aggregate per template per engine, plus a ratio to the baseline.

    The summary is the headline: median over replications, then a geometric
    mean over instances (an arithmetic mean for metrics where zero is real; the
    column is named for whichever applies). `pooled_median` is the old
    single-stage number -- the median over all runs of the template at once --
    kept beside it because the gap between the two is diagnostic. They agree
    when the instances of a template behave alike; where they diverge by more
    than a little, the template is a mixture and
    `output/tables/instance_variance.md` says by how much.

    `instance_range` is the slowest and fastest instance median, and `geo_sd`
    the same spread as one multiplicative factor. `covered` is how many
    instances the engine has an observed value on, out of how many it ran; for
    a matched metric the summary is over the instances every engine covers, so
    an engine that found nothing shows as low coverage rather than a flattered
    number. The baseline is the first engine in `engine_order` (`default` when
    present); ratios below 1 mean the engine was faster / issued fewer requests.
    """
    engines = engine_order(df)
    baseline = engines[0]
    label = estimator_label(metric)
    decimals, range_fmt = table_precision(metric)
    # The same runs and instances the summary uses, so the two are compared over
    # one population rather than quietly over different ones.
    ok = runs_for_metric(df, metric)
    if metric in MATCHED_METRICS:
        keep = matched_instances(df, metric)
        ok = ok[[(t, i) in keep for t, i in zip(ok["template"], ok["instance"])]]
    stats = two_stage(df, metric).set_index(["template", "engine"])

    rows = []
    for template in template_order(df):
        row = {"template": template}
        values = {}
        for engine in engines:
            if (template, engine) not in stats.index:
                row[f"{label}::{engine}"] = pd.NA
                row[f"pooled_median::{engine}"] = pd.NA
                row[f"instance_range::{engine}"] = "-"
                row[f"geo_sd::{engine}"] = pd.NA
                row[f"covered::{engine}"] = "-"
                continue
            cell = stats.loc[(template, engine)]
            # Coverage is written even when there is no value: on a template where
            # one engine found nothing, coverage is the whole of the comparison.
            row[f"covered::{engine}"] = f"{cell['n_covered']}/{cell['n_ran']}"
            if pd.isna(cell["summary"]):
                row[f"{label}::{engine}"] = pd.NA
                row[f"pooled_median::{engine}"] = pd.NA
                row[f"instance_range::{engine}"] = "-"
                row[f"geo_sd::{engine}"] = pd.NA
                continue
            pooled = ok[(ok["template"] == template) & (ok["engine"] == engine)][metric]
            pooled_median = float(pooled.median()) if len(pooled) else np.nan
            values[engine] = cell["summary"]
            row[f"{label}::{engine}"] = round(cell["summary"], decimals)
            row[f"pooled_median::{engine}"] = (round(pooled_median, decimals)
                                               if np.isfinite(pooled_median) else pd.NA)
            row[f"instance_range::{engine}"] = f"{cell['low']:{range_fmt}}-{cell['high']:{range_fmt}}"
            row[f"geo_sd::{engine}"] = (round(cell["geo_sd"], 2)
                                        if pd.notna(cell["geo_sd"]) else pd.NA)
        for engine in engines[1:]:
            row[f"vs_{baseline}::{engine}"] = (
                round(values[engine] / values[baseline], 2)
                if values.get(baseline) and engine in values else pd.NA)
        rows.append(row)

    order = {t: i for i, t in enumerate(template_order(df))}
    table = pd.DataFrame(rows)
    table["_order"] = table["template"].map(order)
    return table.sort_values("_order").drop(columns="_order").reset_index(drop=True)


def _one_line(message: str, width: int = 110) -> str:
    """Engine errors span several lines; keep tables readable."""
    flat = " ".join(str(message).split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


def error_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Which errors occurred, how often, per engine."""
    failed = df[df["failed"]].copy()
    if failed.empty:
        return pd.DataFrame(columns=["engine", "error", "runs", "templates"])
    failed["error"] = failed["error"].map(_one_line)
    grouped = failed.groupby(["engine", "error"]).agg(
        runs=("template", "size"),
        templates=("template", lambda s: ", ".join(sorted({t.replace("interactive-", "") for t in s}))),
    ).reset_index()
    return grouped.sort_values(["engine", "runs"], ascending=[True, False]).reset_index(drop=True)
