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

**Runs that did not finish.** Which runs count depends on the metric, because a
timed-out run measures some things correctly and others not at all:

- Its *total time* and *time to last result* are the cutoff, not the query's.
  Those metrics stay completed-only; including them would bias an engine that
  times out more often toward the budget, i.e. toward looking faster.
- Its *time to first result*, results delivered, throughput and request count
  are real measurements of what happened before the cutoff. Those include
  every run, so a template that no engine finishes still shows who made
  progress on it.

Including partial runs has a trap of its own. If engine A finds results on all
five instances of a template while engine B finds none on three, dropping B's
three empty instances leaves B summarised over its two easiest ones -- B is
rewarded for failing. Each metric that counts partial runs deals with that in
the way its values allow:

- **Time to first result** has no value at all where nothing arrived, and none
  is invented. An engine *covers* an instance when more than half of its
  replications produced a result, which is exactly when the median over those
  replications is an observed time (the others are treated as never arriving,
  so they decide whether the median exists without ever entering it as a
  number). Engines are then compared only on the instances every one of them
  covers, and how many each covers is reported beside it (`n_covered`). The
  speed comparison is like-for-like; an engine that found nothing shows up as
  low coverage rather than as an absent or flattered bar.
- **Answer rate** -- throughput adjusted for the size of the answer -- has a
  real zero where nothing arrived. Raw results per second cannot be averaged
  across instances, since one instance returns 66 results and another 1, so
  each run is scaled by its instance's answer size: the fraction of the answer
  delivered per second. Those are comparable across instances, so stage 2 takes
  an equal-weight *arithmetic* mean, in which an instance that delivered
  nothing counts as the 0 it is.

A run that *completed* with no results answered an empty query correctly. It
has no first result, which leaves that instance uncovered for every engine
alike.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .loading import engine_order, template_order

#: Metrics whose value for an unfinished run is the cutoff rather than a
#: measurement. Everything else counts partial runs.
COMPLETION_ONLY_METRICS = frozenset({"time_ms", "last_result_ms"})

#: Metrics compared only on the instances every engine covers, with coverage
#: reported beside them, rather than imputing a value where nothing arrived.
MATCHED_METRICS = frozenset({"first_result_ms"})

#: Metrics where zero is a real outcome, so stage 2 takes an arithmetic mean --
#: the geometric mean cannot hold a 0 and would drop the instance.
ARITHMETIC_METRICS = frozenset({"answer_rate_per_s"})

#: Metrics derived here rather than read from the run frame, because they need
#: other engines' runs to compute (see `_with_answer_rate`).
DERIVED_METRICS = frozenset({"answer_rate_per_s"})


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


def runs_for_metric(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """The runs that measure `metric`, with the policy for unfinished runs applied.

    The single place that decides which runs count -- see the module docstring.
    Every summary of a metric draws from here, so that two numbers set side by
    side (a two-stage geomean and a pooled median, say) are computed over the
    same runs rather than quietly over different ones.
    """
    if metric in DERIVED_METRICS:
        df = _with_answer_rate(df)
    runs = df.assign(**{metric: pd.to_numeric(df[metric], errors="coerce")})
    if metric in COMPLETION_ONLY_METRICS:
        runs = runs[~runs["failed"]]
    elif metric in MATCHED_METRICS:
        # Kept, as never-arriving: they decide whether a median exists at all
        # (`per_instance_for_metric`) without ever entering it as a value.
        return runs.assign(**{metric: runs[metric].fillna(np.inf)})
    return runs.dropna(subset=[metric])


def _with_answer_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Adds `answer_rate_per_s`: the fraction of the instance's answer delivered per second.

    The answer size is the largest result count of any completed run of that
    instance, by any engine, falling back to the most any run delivered where none
    completed. It is shared by every engine on the instance, so within an instance
    the rate orders engines exactly as raw throughput does; what it changes is
    that instances become comparable, so they can be averaged.

    Taking the largest count rather than each engine's own treats more results as
    a more complete answer. Where engines disagree on the answer -- `short-5`,
    where one returns 1 and another 4 -- that charges the smaller one as
    incomplete, which is only right if the larger answer is the correct one.
    """
    completed = df[~df["failed"]].groupby(["template", "instance"])["delivered"].max()
    anything = df.groupby(["template", "instance"])["delivered"].max()
    answer = completed.reindex(anything.index).fillna(anything)
    sizes = df.set_index(["template", "instance"]).index.map(answer).to_numpy(dtype=float)
    seconds = df["time_ms"].to_numpy(dtype=float) / 1000
    with np.errstate(divide="ignore", invalid="ignore"):
        # No known answer (nothing ever delivered) leaves the rate undefined
        rate = np.where(sizes > 0, df["delivered"].to_numpy(dtype=float) / sizes / seconds, np.nan)
    return df.assign(answer_rate_per_s=rate)


def per_instance_for_metric(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Stage 1 with the run policy that fits `metric` -- see the module docstring.

    Always returns `value`, `runs`, `completed` and `with_result`, plus
    `covered`: whether the instance has an observed value. For time to first
    result that needs more than half the replications to have produced a result,
    since only then is their median an observed time; elsewhere it is simply
    whether any replication measured the metric.
    """
    runs = runs_for_metric(df, metric)
    stage1 = runs.groupby(["engine", "template", "instance"])[metric].agg(
        value="median", runs="size").reset_index()
    stage1 = stage1.merge(_instance_counts(df), on=["engine", "template", "instance"],
                          how="left")
    stage1["covered"] = np.isfinite(stage1["value"].astype(float))
    return stage1


def _instance_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Per instance: replications that completed, and that delivered anything."""
    return df.groupby(["engine", "template", "instance"]).agg(
        completed=("failed", lambda f: int((~f).sum())),
        with_result=("delivered", lambda d: int((d > 0).sum())),
    ).reset_index()


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


def _matched(stage1: pd.DataFrame) -> set[tuple[str, str]]:
    """(template, instance) pairs covered by every engine that ran the template."""
    covering = stage1[stage1["covered"]].groupby(["template", "instance"])["engine"].nunique()
    running = stage1.groupby("template")["engine"].nunique()
    return {key for key, n in covering.items() if n == running[key[0]]}


def matched_instances(df: pd.DataFrame, metric: str) -> set[tuple[str, str]]:
    """The instances a matched metric is compared on -- see `two_stage`.

    Public so that anything set beside a matched summary (a pooled median, say)
    can be restricted to the same instances rather than recomputing the rule.
    """
    return _matched(per_instance_for_metric(df, metric))


def two_stage(df: pd.DataFrame, metric: str, match_instances: bool | None = None) -> pd.DataFrame:
    """Stage 2: one row per (template, engine), summarised over instances.

    `summary` is the value to report: a geometric mean over instances, or for
    `ARITHMETIC_METRICS` an arithmetic mean, where a 0 is a real outcome the
    geometric mean would drop. `geomean` is always the geometric mean, kept for
    callers that want it by name.

    `low` / `high` are the smallest and largest *instance* medians, not a
    quantile over runs: the error bar answers "how differently do the instances
    of this template behave", which is the spread that actually moves the
    summary. `geo_sd` is the same spread as a single factor, for geometric
    metrics only.

    With `match_instances` (the default for `MATCHED_METRICS`), each template is
    summarised only over the instances that every engine running it covers, so
    the engines are compared on the same instances. `n_matched` is how many that
    is, and `n_covered` / `n_ran` how many this engine covers out of how many it
    ran: an engine that found nothing on an instance shows up as lower coverage,
    never as a flattered summary.
    """
    if match_instances is None:
        match_instances = metric in MATCHED_METRICS
    arithmetic = metric in ARITHMETIC_METRICS
    stage1 = per_instance_for_metric(df, metric)
    matched = _matched(stage1)

    # Instances each engine actually ran, whatever the metric: a metric undefined
    # on an instance (an answer rate where nobody ever delivered) leaves it out of
    # stage 1, but the engine still ran it, and coverage should say so.
    ran = df.groupby(["template", "engine"])["instance"].nunique()

    rows = []
    for (template, engine), group in stage1.groupby(["template", "engine"]):
        used = group[group["covered"]]
        if match_instances:
            # A boolean array, not a list: an empty list indexes zero *columns*
            in_matched = np.array([(template, i) in matched for i in used["instance"]], dtype=bool)
            used = used.loc[in_matched]
        values = used["value"].astype(float)
        if arithmetic:
            usable = values[np.isfinite(values)]
            summary = float(usable.mean()) if len(usable) else np.nan
        else:
            usable = values[np.isfinite(values) & (values > 0)]
            summary = geomean(values)
        rows.append({
            "template": template,
            "engine": engine,
            "summary": summary,
            "estimator": "mean" if arithmetic else "geomean",
            "geomean": geomean(values),
            "median_of_instances": float(usable.median()) if len(usable) else np.nan,
            "low": float(usable.min()) if len(usable) else np.nan,
            "high": float(usable.max()) if len(usable) else np.nan,
            "geo_sd": np.nan if arithmetic else geo_sd(values),
            "n_instances": int(len(usable)),
            "n_runs": int(used["runs"].sum()),
            "n_dropped": int(len(values) - len(usable)),
            "n_covered": int(group["covered"].sum()),
            "n_ran": int(ran.get((template, engine), len(group))),
            "n_matched": int(sum(1 for t, _ in matched if t == template)) if match_instances else np.nan,
            "n_completed": int((group["completed"] > 0).sum()),
            "n_with_result": int((group["with_result"] > 0).sum()),
        })
    return pd.DataFrame(rows)


def two_stage_table(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """`two_stage` widened to one row per template, one column group per engine.

    `vs_<baseline>` is the ratio of the summaries. For a geometric metric that
    is the ratio of geometric means, which -- because the geomean is
    multiplicative -- is also the geometric mean of the per-instance ratios, so
    the two ways of asking give the same number. For an arithmetic metric it is
    only the ratio of means.

    The value column is named for its estimator (`geomean::` or `mean::`), so a
    table never labels an arithmetic mean as a geometric one. `covered::` is
    `covered/ran` instances; for a matched metric the summary is taken over the
    instances every engine covers.
    """
    engines = engine_order(df)
    baseline = engines[0]
    stats = two_stage(df, metric).set_index(["template", "engine"])
    label = estimator_label(metric)
    decimals, range_fmt = table_precision(metric)

    rows = []
    for template in template_order(df):
        row = {"template": template}
        values = {}
        for engine in engines:
            if (template, engine) not in stats.index:
                row[f"{label}::{engine}"] = pd.NA
                row[f"instance_range::{engine}"] = "-"
                row[f"geo_sd::{engine}"] = pd.NA
                row[f"covered::{engine}"] = "-"
                continue
            cell = stats.loc[(template, engine)]
            if pd.notna(cell["summary"]):
                values[engine] = cell["summary"]
            row[f"{label}::{engine}"] = (round(cell["summary"], decimals)
                                         if pd.notna(cell["summary"]) else pd.NA)
            row[f"instance_range::{engine}"] = (f"{cell['low']:{range_fmt}}-{cell['high']:{range_fmt}}"
                                                if pd.notna(cell["low"]) else "-")
            row[f"geo_sd::{engine}"] = round(cell["geo_sd"], 2) if pd.notna(cell["geo_sd"]) else pd.NA
            row[f"instances::{engine}"] = cell["n_instances"]
            row[f"covered::{engine}"] = f"{cell['n_covered']}/{cell['n_ran']}"
        for engine in engines[1:]:
            row[f"vs_{baseline}::{engine}"] = (
                round(values[engine] / values[baseline], 2)
                if values.get(baseline) and engine in values else pd.NA)
        rows.append(row)
    return pd.DataFrame(rows)


def estimator_label(metric: str) -> str:
    """What a metric's summary is, for column names and captions."""
    return "mean" if metric in ARITHMETIC_METRICS else "geomean"


def table_precision(metric: str) -> tuple[int, str]:
    """(decimals, range format) for printing a metric's values in a table.

    Timings and counts read best as whole numbers. An answer rate is a fraction
    of an answer per second, typically far below 1, and would round to zero.
    """
    return (4, ".4g") if metric in ARITHMETIC_METRICS else (1, ".0f")
