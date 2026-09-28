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

from .aggregate import two_stage
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

    Aggregated in two stages like everything else: median over the replications
    of an instance, then geometric mean over the instances. Restricting to the
    matched set and then pooling all the surviving runs would still let an
    engine with more surviving replications on the easy instance pull the
    summary its way; equal weight per instance is what makes the set "matched".
    """
    engines = engine_order(df)
    baseline = engines[0]
    ok = df[~df["failed"]].dropna(subset=[metric])

    completed = {e: set(map(tuple, ok[ok["engine"] == e][["template", "instance"]].values))
                 for e in engines}
    shared = set.intersection(*completed.values()) if completed else set()

    matched_rows = df[[(t, i) in shared for t, i in zip(df["template"], df["instance"])]]
    stats = (two_stage(matched_rows, metric).set_index(["template", "engine"])
             if len(matched_rows) else None)

    rows = []
    for template, group in df.groupby("template"):
        instances = set(group["instance"])
        usable = {i for i in instances if (template, i) in shared}
        row = {"template": template,
               "instances_used": len(usable),
               "instances_total": len(instances)}
        values = {}
        for engine in engines:
            if stats is None or (template, engine) not in stats.index:
                row[f"geomean::{engine}"] = pd.NA
                row[f"instance_range::{engine}"] = "-"
                continue
            cell = stats.loc[(template, engine)]
            values[engine] = cell["geomean"]
            row[f"geomean::{engine}"] = round(cell["geomean"], 1)
            row[f"instance_range::{engine}"] = f"{cell['low']:.0f}-{cell['high']:.0f}"
        for engine in engines[1:]:
            row[f"vs_{baseline}::{engine}"] = (
                round(values[engine] / values[baseline], 2)
                if values.get(baseline) and engine in values else pd.NA)
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
    """Split each run into reaching the first result, streaming the rest, and
    whatever the engine does after the last result has arrived.

    A fixed setup cost and a faster execution phase cancel into one unremarkable
    end-to-end ratio, which is why the totals alone look like a wash. The split
    separates them, and it is what makes the regression on cheap queries and the
    win on expensive ones the same story rather than two contradictory ones.

    Three phases, because in this dataset the middle one is nearly empty: the
    median gap between the first and the last result is 1ms, so results arrive
    in a burst, and the time that is not spent reaching the first result is
    spent *after* the last one (median 220ms, but up to 177s). An engine can
    therefore deliver every answer early and still finish late, which
    `to_last_result` versus `total` is the only place that shows.

    The phase durations are differences between aggregated absolute times
    rather than aggregates of per-run differences. Both the streaming span and
    the tail are exactly zero on many runs, and a geometric mean cannot take a
    zero -- dropping those runs would systematically delete the fastest ones.

    Matched instances only, so the phases are compared on the same queries.
    """
    engines = engine_order(df)
    baseline = engines[0]
    ok = df[~df["failed"]].dropna(subset=["first_result_ms", "last_result_ms"]).copy()

    completed = {e: set(map(tuple, ok[ok["engine"] == e][["template", "instance"]].values))
                 for e in engines}
    shared = set.intersection(*completed.values()) if completed else set()
    matched = ok[[(t, i) in shared for t, i in zip(ok["template"], ok["instance"])]]
    if matched.empty:
        return pd.DataFrame(columns=["template"])

    phases = {name: two_stage(matched, name).set_index(["template", "engine"])
              for name in ("first_result_ms", "last_result_ms", "time_ms")}

    rows = []
    for template, group in matched.groupby("template"):
        row = {"template": template, "instances_used": group["instance"].nunique()}
        first, last, total = {}, {}, {}
        for engine in engines:
            if (template, engine) not in phases["time_ms"].index:
                continue
            first[engine] = phases["first_result_ms"].loc[(template, engine), "geomean"]
            last[engine] = phases["last_result_ms"].loc[(template, engine), "geomean"]
            total[engine] = phases["time_ms"].loc[(template, engine), "geomean"]
            row[f"to_first_result::{engine}"] = round(first[engine], 1)
            row[f"to_last_result::{engine}"] = round(last[engine], 1)
            row[f"streaming_span::{engine}"] = round(last[engine] - first[engine], 1)
            row[f"after_last_result::{engine}"] = round(total[engine] - last[engine], 1)
        if baseline not in first:
            continue
        for engine in engines[1:]:
            if engine not in first:
                continue
            row[f"startup_delta_ms::{engine}"] = round(first[engine] - first[baseline], 1)
            row[f"to_last_ratio::{engine}"] = (
                round(last[engine] / last[baseline], 2) if last[baseline] else pd.NA)
        rows.append(row)

    return _ordered(pd.DataFrame(rows), df)
