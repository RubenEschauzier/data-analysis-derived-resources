"""Completion, progress and survivorship-free timing comparisons.

Comparing medians over successful runs only is biased whenever the engines
complete different subsets of the workload: the engine that gives up on the hard
queries looks fast, because its hard queries are missing from its own median.
Three separate views avoid reading that artefact as a result.

- `completion_summary`  how often each engine finished at all, and how it failed
- `par_scores`          timing with failures penalised rather than dropped
- `matched_timing`      timing restricted to what every engine completed
- `progress_summary`    results delivered including partial output from timeouts
"""

from __future__ import annotations

import pandas as pd

from .config import TIMEOUT_MS
from .loading import engine_order, template_order

FAILURE_KINDS = ["ok", "timeout", "crash", "unsupported"]


def _ordered(table: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    order = {t: i for i, t in enumerate(template_order(df))}
    table = table.copy()
    table["_order"] = table["template"].map(order)
    return table.sort_values(["_order", "template"]).drop(columns="_order").reset_index(drop=True)


def completion_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per template, how each engine's runs ended."""
    engines = engine_order(df)
    rows = []
    for template, group in df.groupby("template"):
        row = {"template": template}
        for engine in engines:
            sub = group[group["engine"] == engine]
            row[f"completed::{engine}"] = f"{int((sub['failure_kind'] == 'ok').sum())}/{len(sub)}"
            for kind in FAILURE_KINDS[1:]:
                row[f"{kind}::{engine}"] = int((sub["failure_kind"] == kind).sum())
        rows.append(row)
    return _ordered(pd.DataFrame(rows), df)


def par_scores(df: pd.DataFrame, factor: int = 2) -> pd.DataFrame:
    """Penalised average runtime: a run that never finished counts as
    `factor * TIMEOUT_MS` instead of being dropped.

    PAR-2 is the usual convention in solver competitions. It keeps failures in
    the comparison, so an engine cannot look fast by failing more often. The
    penalty is a convention, not a measurement -- read it alongside the
    completion rate, never on its own.
    """
    engines = engine_order(df)
    penalty = factor * TIMEOUT_MS
    scored = df.copy()
    scored["par"] = scored["time_ms"].where(~scored["failed"], penalty)

    baseline = engines[0]
    rows = []
    for template, group in scored.groupby("template"):
        row = {"template": template}
        means = {}
        for engine in engines:
            values = group[group["engine"] == engine]["par"]
            means[engine] = values.mean()
            row[f"par{factor}::{engine}"] = round(values.mean(), 1)
        for engine in engines[1:]:
            row[f"vs_{baseline}::{engine}"] = (
                round(means[engine] / means[baseline], 2) if means[baseline] else pd.NA)
        rows.append(row)
    return _ordered(pd.DataFrame(rows), df)


def matched_timing(df: pd.DataFrame, metric: str = "time_ms") -> pd.DataFrame:
    """Timing over only the (template, instance) pairs every engine completed.

    Removes the survivorship bias at query granularity. `instances_used` versus
    `instances_total` says how much of the workload the comparison rests on -- a
    ratio computed over half the instances is not a workload-level claim.
    """
    engines = engine_order(df)
    baseline = engines[0]
    ok = df[~df["failed"]].dropna(subset=[metric])

    completed = {e: set(map(tuple, ok[ok["engine"] == e][["template", "instance"]].values))
                 for e in engines}
    shared = set.intersection(*completed.values()) if completed else set()

    rows = []
    for template, group in df.groupby("template"):
        instances = set(group["instance"])
        usable = {i for i in instances if (template, i) in shared}
        row = {"template": template,
               "instances_used": len(usable),
               "instances_total": len(instances)}
        medians = {}
        if usable:
            subset = ok[(ok["template"] == template) & (ok["instance"].isin(usable))]
            for engine in engines:
                values = subset[subset["engine"] == engine][metric]
                medians[engine] = values.median()
                row[f"median::{engine}"] = round(values.median(), 1)
        else:
            for engine in engines:
                row[f"median::{engine}"] = pd.NA
        for engine in engines[1:]:
            row[f"vs_{baseline}::{engine}"] = (
                round(medians[engine] / medians[baseline], 2)
                if medians.get(baseline) else pd.NA)
        rows.append(row)
    return _ordered(pd.DataFrame(rows), df)


def progress_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Results delivered per template, counting partial output from failed runs.

    A timed-out run still streamed results before it was cut off, and on some
    templates that is the only signal there is: an engine that delivers 17
    results before the budget expires is not equivalent to one that delivers 0.
    """
    engines = engine_order(df)
    rows = []
    for template, group in df.groupby("template"):
        row = {"template": template}
        for engine in engines:
            sub = group[group["engine"] == engine]
            done = sub[~sub["failed"]]
            partial = sub[sub["failed"]]
            row[f"median_delivered::{engine}"] = sub["delivered"].median()
            row[f"from_failed_runs::{engine}"] = (
                f"{int(partial['delivered'].sum())} over {len(partial)} runs"
                if len(partial) else "-")
            row[f"median_throughput_per_s::{engine}"] = (
                round(done["throughput_per_s"].median(), 2) if len(done) else pd.NA)
        rows.append(row)
    return _ordered(pd.DataFrame(rows), df)


def startup_decomposition(df: pd.DataFrame) -> pd.DataFrame:
    """Split each query into reaching the first result, then streaming the rest.

    A fixed setup cost and a faster execution phase cancel into one unremarkable
    end-to-end ratio, which is why the totals alone look like a wash. Splitting
    the run at its first result separates the two, and the split is what makes
    the regression on cheap queries and the win on expensive ones the same
    story rather than two contradictory ones.

    Matched instances only, so the phases are compared on the same queries.
    """
    engines = engine_order(df)
    baseline = engines[0]
    ok = df[~df["failed"]].dropna(subset=["first_result_ms"]).copy()
    ok["first_result_ms"] = ok["first_result_ms"].astype(float)
    ok["after_first_ms"] = ok["time_ms"] - ok["first_result_ms"]

    completed = {e: set(map(tuple, ok[ok["engine"] == e][["template", "instance"]].values))
                 for e in engines}
    shared = set.intersection(*completed.values()) if completed else set()

    rows = []
    for template, group in ok.groupby("template"):
        usable = {i for i in set(group["instance"]) if (template, i) in shared}
        if not usable:
            continue
        subset = group[group["instance"].isin(usable)]
        row = {"template": template, "instances_used": len(usable)}
        first, after = {}, {}
        for engine in engines:
            values = subset[subset["engine"] == engine]
            first[engine] = values["first_result_ms"].median()
            after[engine] = values["after_first_ms"].median()
            row[f"to_first_result::{engine}"] = round(first[engine], 1)
            row[f"after_first_result::{engine}"] = round(after[engine], 1)
        for engine in engines[1:]:
            row[f"startup_delta_ms::{engine}"] = round(first[engine] - first[baseline], 1)
            row[f"after_first_ratio::{engine}"] = (
                round(after[engine] / after[baseline], 2) if after[baseline] else pd.NA)
        rows.append(row)

    return _ordered(pd.DataFrame(rows), df)
