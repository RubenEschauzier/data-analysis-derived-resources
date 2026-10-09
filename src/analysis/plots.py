"""Per-template comparison figures, one series per engine.

Bars, vertically, in two layouts -- pick with `layout`:

- `facets`  one small-multiple panel per template, each on its own *linear*
  axis. This is the honest bar chart: a bar encodes magnitude as length from
  zero, and per-panel scaling is what makes that possible when the workload
  spans 200ms to 180s. The cost is that magnitudes cannot be compared across
  panels by eye -- read the axis, not the bar.
- `single`  every template on one shared *log* axis. Comparable at a glance and
  compact, but bar length is no longer proportional to the value: on a log axis
  the baseline is arbitrary, so the bars are a positional encoding wearing a
  bar's clothes. The figure says so on its face.

Both draw the same numbers: the two-stage aggregate from `aggregate.py` (median
over replications, then geometric mean over instances), with the whisker
spanning the slowest and fastest *instance* rather than a quantile over runs --
on several templates that spread is two orders of magnitude and is the most
important thing on the chart.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np
import pandas as pd

from .aggregate import (MATCHED_METRICS, estimator_label, per_instance,
                        per_instance_all_runs, two_stage)
from .config import (FIGURE_DIR, OUTCOME_STATUS, STATUS, THEMES, series_color,
                     series_dash)
from .heterogeneity import variance_decomposition
from .loading import engine_order, template_order

METRICS = {
    "time_ms": ("Query execution time", "milliseconds"),
    "http_requests": ("HTTP requests issued", "requests"),
    "first_result_ms": ("Time to first result", "milliseconds"),
    "last_result_ms": ("Time to last result", "milliseconds"),
    "throughput_per_s": ("Result throughput", "results per second"),
    "answer_rate_per_s": ("Answer delivery rate", "fraction of the answer per second"),
    "delivered": ("Results delivered", "results"),
}

# Per-template bars. `delivered` is left out: over completed runs it is just the
# result count, which the agreement tables already cover.
# Per-template throughput is the answer rate: raw results per second cannot be
# averaged across instances whose answers differ in size by orders of magnitude.
TEMPLATE_METRICS = ("time_ms", "http_requests", "first_result_ms", "last_result_ms",
                    "answer_rate_per_s")

# Per-instance figures. `True` draws every run, failed ones included: for the
# progress metrics a timed-out run's partial output is real, and a template no
# engine ever completes is otherwise invisible. Execution time stays
# completed-only -- a timeout's wall time is the budget, not a measurement.
INSTANCE_METRICS = {
    "time_ms": False,
    "delivered": True,
    "throughput_per_s": True,
    "first_result_ms": True,
}

# Figures are grouped into one subdirectory per kind of question.
GROUPS = {
    "per_template": "per-template",
    "per_instance": "per-instance",
    "completion": "completion",
    "heterogeneity": "heterogeneity",
}

LAYOUTS = ("facets", "single")

# Time axis of the arrival curves. `log` shares one axis over the whole run budget;
# `linear` zooms each panel onto the window in which that template's results arrive.
ARRIVAL_SCALES = ("log", "linear")


def _short(template: str) -> str:
    return template.replace("interactive-", "")


def _fmt(value: float) -> str:
    """Compact bar label: 1.8k rather than 1834.2."""
    if not np.isfinite(value):
        return "-"
    if value >= 10_000:
        return f"{value / 1000:.0f}k"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    if value >= 10:
        return f"{value:.0f}"
    return f"{value:.2g}"


def _style_axes(ax, palette, grid_axis: str = "y") -> None:
    ax.set_facecolor(palette["surface"])
    ax.grid(axis=grid_axis, color=palette["grid"], linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(palette["grid"])
    ax.tick_params(colors=palette["text_secondary"], length=0)


def legend_rows(engines, max_columns: int = 3) -> int:
    """How many rows `_engine_legend` will take, so callers can leave room for it."""
    return -(-len(engines) // min(len(engines), max_columns))


def _engine_legend(fig_or_ax, engines, theme, palette, *, dashed: bool = False,
                   max_columns: int = 3, **kwargs):
    """A legend keyed by engine, wrapped so it cannot outgrow the figure.

    Capped at three columns: configuration names here are long, and five on one row
    is wider than the figure, which clipped the first entry and ran the rest into the
    title. `dashed` mirrors the line styles used by the arrival curves, where dash is
    the secondary encoding that keeps non-adjacent series apart.
    """
    handles = [plt.Line2D([], [], marker="none" if dashed else "s",
                          linestyle=series_dash(slot) if dashed else "none",
                          linewidth=1.8, markersize=9,
                          color=series_color(theme, slot), label=engine)
               for slot, engine in enumerate(engines)]
    legend = fig_or_ax.legend(handles=handles, frameon=False, fontsize=9,
                              ncol=min(len(engines), max_columns), handletextpad=0.6,
                              columnspacing=1.6, **kwargs)
    for text in legend.get_texts():
        text.set_color(palette["text_secondary"])
    return legend


def _save(fig, palette, out_dir: Path, name: str, theme: str) -> Path:
    """Vector PDF only. Light is the unsuffixed default; other themes are tagged."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = name if theme == "light" else f"{name}-{theme}"
    path = out_dir / f"{stem}.pdf"
    fig.savefig(path, facecolor=palette["surface"])
    plt.close(fig)
    return path


def _facet_grid(n_panels: int, palette, cols: int = 3, panel_height: float = 2.45):
    rows = -(-n_panels // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(11.5, panel_height * rows),
                             facecolor=palette["surface"], squeeze=False)
    flat = [axes[i // cols][i % cols] for i in range(rows * cols)]
    for ax in flat[n_panels:]:
        ax.set_visible(False)
    return fig, flat


def _coverage(stats: pd.DataFrame, template: str, engines) -> tuple[list[str], str, str]:
    """Per engine, `covered/ran` instances; a status for the template; and a note.

    The status says why a panel may have nothing to draw: `nobody` when no engine
    has an observed value on any instance (an unsupported query, say), `no_common`
    when engines cover instances but no single instance is covered by all of them
    -- a matched metric then has nothing to compare -- and `ok` otherwise. The
    note says what a matched comparison rests on when that is fewer instances
    than were run.
    """
    labels, any_covered, matched, ran = [], False, None, None
    for engine in engines:
        cell = stats[(stats["template"] == template) & (stats["engine"] == engine)]
        if cell.empty:
            labels.append("")
            continue
        row = cell.iloc[0]
        labels.append(f"{int(row['n_covered'])}/{int(row['n_ran'])}")
        any_covered = any_covered or int(row["n_covered"]) > 0
        ran = int(row["n_ran"]) if ran is None else max(ran, int(row["n_ran"]))
        if pd.notna(row.get("n_matched", np.nan)):
            matched = int(row["n_matched"])
    if not any_covered:
        return labels, "nobody", ""
    if matched is not None and matched == 0:
        return labels, "no_common", ""
    note = f"compared on {matched} of {ran} instances" if matched is not None and matched < ran else ""
    # Coverage labels only earn their space where some engine falls short
    if all(label.split("/")[0] == label.split("/")[-1] for label in labels if label):
        labels = ["" for _ in labels]
    return labels, "ok", note


def _caption(metric: str) -> str:
    """What a per-template bar is, for this metric."""
    estimator = "mean" if estimator_label(metric) == "mean" else "geometric mean"
    over = (", over the instances every engine covers" if metric in MATCHED_METRICS
            else "")
    return (f"bar = {estimator} of the per-instance medians{over}; "
            "whisker = slowest to fastest instance.")


def _bars_facets(df, metric, theme, palette, engines, templates, stats, out_dir) -> Path:
    """One panel per template, linear axis, grouped bars with an instance range."""
    title, unit = METRICS[metric]
    fig, axes = _facet_grid(len(templates), palette)

    for index, template in enumerate(templates):
        ax = axes[index]
        cells = [stats[(stats["template"] == template) & (stats["engine"] == e)]
                 for e in engines]
        positions = np.arange(len(engines))
        heights, lows, highs = [], [], []
        for cell in cells:
            if cell.empty or not np.isfinite(cell.iloc[0]["summary"]):
                heights.append(np.nan)
                lows.append(np.nan)
                highs.append(np.nan)
            else:
                row = cell.iloc[0]
                heights.append(row["summary"])
                lows.append(row["low"])
                highs.append(row["high"])

        coverage, status, note = _coverage(stats, template, engines)
        drawn = False
        for slot, (x, height) in enumerate(zip(positions, heights)):
            if not np.isfinite(height) or status != "ok":
                continue
            drawn = True
            color = series_color(theme, slot)
            ax.bar(x, height, width=0.66, color=color, zorder=2)
            # Whisker = slowest and fastest instance, so the bar is never read
            # as a property of the template when it is an average over
            # instances that disagree.
            ax.plot([x, x], [lows[slot], highs[slot]], color=palette["text_secondary"],
                    linewidth=1.3, zorder=4, solid_capstyle="butt")
            for end in (lows[slot], highs[slot]):
                ax.plot([x - 0.14, x + 0.14], [end, end],
                        color=palette["text_secondary"], linewidth=1.3, zorder=4)
            # Above the whisker, not the bar: on a template whose instances
            # disagree the whisker top is far above the bar, and a label pinned
            # to the bar lands on top of the whisker line.
            ax.annotate(_fmt(height), (x, max(height, highs[slot])),
                        textcoords="offset points", xytext=(0, 4), ha="center",
                        fontsize=7.5, color=palette["text_secondary"], zorder=5)

        if not drawn:
            message = {"nobody": "no engine produced a value",
                       "no_common": "no instance every engine covered"}.get(status,
                                                                         "no successful runs")
            ax.text(0.5, 0.5, message, transform=ax.transAxes,
                    ha="center", va="center", fontsize=9, style="italic",
                    color=palette["text_muted"])
            ax.set_yticks([])
        else:
            top = np.nanmax(highs + heights)
            ax.set_ylim(0, top * 1.18)

        # Engines are identified by the shared legend, in this fixed left-to-right
        # order; the names themselves are too long to set under five bars.
        ax.set_xticks(positions)
        # Coverage sits where engine names would: `covered/ran` instances, shown
        # where some engine falls short, so a bar is never read without it.
        ax.set_xticklabels(coverage, fontsize=7, color=palette["text_muted"])
        ax.set_xlim(-0.65, len(engines) - 0.35)
        ax.set_title(_short(template), fontsize=9.5, color=palette["text_primary"],
                     loc="left", pad=6)
        if note:
            ax.set_title(note, fontsize=7, color=palette["text_muted"], loc="right", pad=6)
        _style_axes(ax, palette)
        ax.tick_params(axis="y", labelsize=7.5)

    fig.suptitle(f"{title} per query template", color=palette["text_primary"],
                 fontsize=12, x=0.012, ha="left", y=0.995)
    fig.supylabel(unit, color=palette["text_secondary"], fontsize=9)
    _engine_legend(fig, engines, theme, palette, loc="upper left",
                   bbox_to_anchor=(0.012, 0.978))
    fig.text(0.012, 0.004,
             f"{_caption(metric)} Each panel has its own scale.\n"
             "Under a bar: instances the engine has a value on / instances it ran, "
             "shown where an engine falls short.",
             fontsize=8, color=palette["text_muted"])
    # Leave the legend its own band under the title, however many rows it wraps to
    fig.tight_layout(rect=(0.012, 0.036, 1, 0.99 - 0.021 * legend_rows(engines)))
    return _save(fig, palette, out_dir, f"{metric}-by-template-facets", theme)


def _bars_single(df, metric, theme, palette, engines, templates, stats, out_dir) -> Path:
    """Every template on one log axis: comparable at a glance, bar length unfaithful."""
    title, unit = METRICS[metric]
    fig, ax = plt.subplots(figsize=(max(9.5, 0.78 * len(templates)), 5.4),
                           facecolor=palette["surface"])

    width = 0.8 / len(engines)
    positive = stats["summary"][stats["summary"] > 0]
    floor = float(positive.min()) / 3 if len(positive) else 1.0

    status = {t: _coverage(stats, t, engines)[1] for t in templates}
    zeros = []
    for slot, engine in enumerate(engines):
        color = series_color(theme, slot)
        xs, heights, lows, highs = [], [], [], []
        for index, template in enumerate(templates):
            if status[template] != "ok":
                continue
            cell = stats[(stats["template"] == template) & (stats["engine"] == engine)]
            if cell.empty or not np.isfinite(cell.iloc[0]["summary"]):
                continue
            row = cell.iloc[0]
            x = index + (slot - (len(engines) - 1) / 2) * width
            # A log axis has no place for 0, which for an answer rate is a real
            # outcome (nothing delivered); marked at the floor instead of dropped.
            if row["summary"] <= 0:
                zeros.append((x, color))
                continue
            xs.append(x)
            heights.append(row["summary"])
            lows.append(max(row["low"], floor))
            highs.append(row["high"])
        if xs:
            ax.bar(xs, heights, width=width * 0.9, bottom=floor, color=color, zorder=2,
                   label=engine)
            ax.vlines(xs, lows, highs, color=palette["text_secondary"], linewidth=1.1,
                      zorder=4)

    ax.set_yscale("log")
    ax.set_ylim(bottom=floor)
    for x, color in zeros:
        ax.annotate("0", (x, floor), textcoords="offset points", xytext=(0, 3),
                    ha="center", fontsize=7, fontweight="bold", color=color)
    ax.set_xticks(range(len(templates)))
    ax.set_xticklabels([_short(t) for t in templates], rotation=45, ha="right",
                       fontsize=8, color=palette["text_secondary"])
    ax.set_xlim(-0.7, len(templates) - 0.3)
    ax.set_ylabel(f"{unit} (log scale)", color=palette["text_secondary"], fontsize=9)
    ax.set_title(f"{title} per query template", color=palette["text_primary"],
                 fontsize=12, pad=24, loc="left")
    _style_axes(ax, palette)

    messages = {"nobody": "no values", "no_common": "no common instance"}
    for index, template in enumerate(templates):
        message = messages.get(status[template])
        if message is None and stats[stats["template"] == template]["summary"].dropna().empty:
            message = "no runs"
        if message:
            ax.annotate(message, (index, floor), textcoords="offset points",
                        xytext=(0, 6), ha="center", rotation=90, fontsize=7,
                        style="italic", color=palette["text_muted"])

    _engine_legend(ax, engines, theme, palette, loc="lower right",
                   bbox_to_anchor=(1, 1.005))
    fig.text(0.008, 0.008,
             f"{_caption(metric)} Log axis: bar *length* is not proportional to the "
             "value -- read the top edge.\nCoverage per engine is in the per-template "
             "table and the facet figure.",
             fontsize=8, color=palette["text_muted"])
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    return _save(fig, palette, out_dir, f"{metric}-by-template-single", theme)


def plot_metric_by_template(df: pd.DataFrame, metric: str, theme: str = "light",
                            layout: str = "facets",
                            out_dir: Path = FIGURE_DIR) -> Path:
    """Grouped bars per template. `layout` is `facets` (linear) or `single` (log)."""
    if layout not in LAYOUTS:
        raise ValueError(f"layout must be one of {LAYOUTS}, got {layout!r}")
    palette = THEMES[theme]
    engines = engine_order(df)
    templates = template_order(df)
    stats = two_stage(df, metric)
    draw = _bars_facets if layout == "facets" else _bars_single
    return draw(df, metric, theme, palette, engines, templates, stats, out_dir)


def plot_instance_spread(df: pd.DataFrame, metric: str = "time_ms",
                         theme: str = "light", out_dir: Path = FIGURE_DIR,
                         include_failed: bool = False) -> Path:
    """Every instance drawn separately, so the template-level bar can be checked.

    This is the figure the aggregation question is really about. Where the five
    bars of one colour are the same height, the template summary describes its
    instances. Where they are not -- `discover-6`, where two instances run two
    orders of magnitude slower than the other three -- the summary is a
    statement about a mixture, and which mode it lands on is decided by the
    workload's choice of constants rather than by the engine.

    `include_failed` takes the median over every replication rather than the
    completed ones. That is what surfaces a template like `short-3`, which no
    engine ever finishes but on which one engine delivers half the partial
    output of another: the completed-only view has nothing to draw there. A
    bar is hatched when none of its replications completed, so partial
    progress is never read as a finished run; an `x` on the baseline marks an
    engine that ran the instance but has no positive value to draw.
    """
    palette = THEMES[theme]
    engines = engine_order(df)
    templates = template_order(df)
    stage1 = (per_instance_all_runs(df, metric) if include_failed
              else per_instance(df, metric))
    title, unit = METRICS[metric]
    ran = df[["engine", "template", "instance"]].drop_duplicates()

    fig, axes = _facet_grid(len(templates), palette)
    for index, template in enumerate(templates):
        ax = axes[index]
        block = stage1[stage1["template"] == template]
        instances = sorted(ran[ran["template"] == template]["instance"].unique(), key=str)
        width = 0.8 / max(len(engines), 1)
        drawn = False
        for slot, engine in enumerate(engines):
            color = series_color(theme, slot)
            for position, instance in enumerate(instances):
                x = position + (slot - (len(engines) - 1) / 2) * width
                cell = block[(block["engine"] == engine) & (block["instance"] == instance)]
                value = float(cell.iloc[0]["value"]) if not cell.empty else np.nan
                if not (np.isfinite(value) and value > 0):
                    if include_failed:
                        ax.plot(x, 0, marker="x", markersize=3.5, markeredgewidth=1,
                                color=color, clip_on=False, zorder=3)
                    continue
                drawn = True
                unfinished = include_failed and int(cell.iloc[0]["completed"]) == 0
                ax.bar(x, value, width=width * 0.9, color=color, zorder=2,
                       hatch="//////" if unfinished else None,
                       edgecolor=palette["surface"] if unfinished else color,
                       linewidth=0)
        if not drawn:
            ax.text(0.5, 0.5, "no runs delivered anything" if include_failed
                    else "no successful runs", transform=ax.transAxes,
                    ha="center", va="center", fontsize=9, style="italic",
                    color=palette["text_muted"])
            ax.set_yticks([])
        ax.set_ylim(bottom=0)
        ax.set_xticks(range(len(instances)))
        ax.set_xticklabels([str(i) for i in instances], fontsize=7.5,
                           color=palette["text_secondary"])
        ax.set_title(_short(template), fontsize=9.5, color=palette["text_primary"],
                     loc="left", pad=6)
        _style_axes(ax, palette)
        ax.tick_params(axis="y", labelsize=7.5)

    scope = "all runs, failures included" if include_failed else "completed runs only"
    fig.suptitle(f"Per-instance {title[0].lower() + title[1:]} "
                 f"(median over replications, {scope})",
                 color=palette["text_primary"], fontsize=12, x=0.012, ha="left", y=0.995)
    fig.supxlabel("instance", color=palette["text_secondary"], fontsize=9)
    fig.supylabel(unit, color=palette["text_secondary"], fontsize=9)
    _engine_legend(fig, engines, theme, palette, loc="upper left",
                   bbox_to_anchor=(0.012, 0.978))
    note = ("one bar per instance; a template whose bars differ is not summarised "
            "faithfully by a single number")
    if include_failed:
        note += ". Hatched = no replication completed (partial output); x = nothing to draw"
    fig.text(0.012, 0.003, note, fontsize=8, color=palette["text_muted"])
    fig.tight_layout(rect=(0.012, 0.038, 1, 0.99 - 0.021 * legend_rows(engines)))
    return _save(fig, palette, out_dir, f"instance-spread-{metric}", theme)


def plot_variance_share(df: pd.DataFrame, metric: str = "time_ms",
                        theme: str = "light", out_dir: Path = FIGURE_DIR) -> Path:
    """Share of log-scale variance that lies between instances, per template.

    A proportion on a fixed 0-1 scale, which is exactly what a bar chart is for.
    High bars mark the templates where more replications buy nothing: the
    spread is between the queries, not between the runs.
    """
    palette = THEMES[theme]
    engines = engine_order(df)
    table = variance_decomposition(df, metric)
    if table.empty:
        raise ValueError("no template has two comparable instances")
    templates = [t for t in template_order(df) if t in set(table["template"])]

    fig, ax = plt.subplots(figsize=(max(9.0, 0.78 * len(templates)), 4.6),
                           facecolor=palette["surface"])
    width = 0.8 / len(engines)
    for slot, engine in enumerate(engines):
        xs, heights = [], []
        for index, template in enumerate(templates):
            cell = table[(table["template"] == template) & (table["engine"] == engine)]
            if cell.empty or not np.isfinite(cell.iloc[0]["instance_share"]):
                continue
            xs.append(index + (slot - (len(engines) - 1) / 2) * width)
            heights.append(float(cell.iloc[0]["instance_share"]))
        if xs:
            ax.bar(xs, heights, width=width * 0.9, color=series_color(theme, slot),
                   zorder=2)

    ax.axhline(0.5, color=palette["text_muted"], linewidth=1, linestyle=(0, (4, 3)),
               zorder=3)
    # Bars reach the reference line almost everywhere, so the note needs an
    # opaque backing rather than a clear patch of chart to sit in.
    ax.annotate("half the spread is between instances", (0.004, 0.5),
                xycoords=("axes fraction", "data"), fontsize=8,
                color=palette["text_muted"], va="center", zorder=5,
                bbox=dict(facecolor=palette["surface"], edgecolor="none", pad=1.5))
    ax.set_ylim(0, 1)
    ax.set_xticks(range(len(templates)))
    ax.set_xticklabels([_short(t) for t in templates], rotation=45, ha="right",
                       fontsize=8, color=palette["text_secondary"])
    ax.set_xlim(-0.7, len(templates) - 0.3)
    ax.set_ylabel("between-instance share of variance",
                  color=palette["text_secondary"], fontsize=9)
    ax.set_title("How much of the spread is the query, not the run",
                 color=palette["text_primary"], fontsize=12, pad=24, loc="left")
    _style_axes(ax, palette)
    _engine_legend(ax, engines, theme, palette, loc="lower right",
                   bbox_to_anchor=(1, 1.005))
    fig.text(0.008, 0.008,
             "variance of log execution time, split between instances of a template "
             "and replications of one instance",
             fontsize=8, color=palette["text_muted"])
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return _save(fig, palette, out_dir, "instance-variance-share", theme)


def plot_completion(df: pd.DataFrame, theme: str = "light",
                    out_dir: Path = FIGURE_DIR) -> Path:
    """How every run ended, per template per engine, as stacked vertical bars.

    Answers directly whether one engine finishes more of the workload than
    another, which the timing figures cannot show because they plot only the
    runs that finished.
    """
    palette = THEMES[theme]
    engines = engine_order(df)
    templates = template_order(df)
    kinds = ["ok", "timeout", "crash", "unsupported"]

    fig, ax = plt.subplots(figsize=(max(9.5, 0.78 * len(templates)), 5.2),
                           facecolor=palette["surface"])

    width = 0.84 / len(engines)
    ticks, labels = [], []
    for index, template in enumerate(templates):
        for slot, engine in enumerate(engines):
            runs = df[(df["template"] == template) & (df["engine"] == engine)]
            x = index + (slot - (len(engines) - 1) / 2) * width
            bottom = 0
            for kind in kinds:
                height = int((runs["failure_kind"] == kind).sum())
                if not height:
                    continue
                ax.bar(x, height, width=width * 0.92, bottom=bottom,
                       color=OUTCOME_STATUS[kind], edgecolor=palette["surface"],
                       linewidth=0.8, zorder=2)
                bottom += height
        ticks.append(index)
        labels.append(_short(template))

    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8,
                       color=palette["text_secondary"])
    ax.set_xlim(-0.7, len(templates) - 0.3)
    ax.set_ylabel("runs", color=palette["text_secondary"], fontsize=9)
    ax.set_title("How each run ended, per template and engine",
                 color=palette["text_primary"], fontsize=12, pad=24, loc="left")
    _style_axes(ax, palette)

    handles = [plt.Line2D([], [], marker="s", linestyle="none", markersize=9,
                          color=OUTCOME_STATUS[k], label=k) for k in kinds]
    legend = ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.005),
                       frameon=False, fontsize=9, ncol=len(kinds), handletextpad=0.4,
                       columnspacing=1.6)
    for text in legend.get_texts():
        text.set_color(palette["text_secondary"])

    fig.text(0.008, 0.008,
             f"bars within a template group are engines, in order: {', '.join(engines)}",
             fontsize=8, color=palette["text_muted"])
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return _save(fig, palette, out_dir, "completion-by-template", theme)


def _delivery_curve(runs: pd.DataFrame, grid: "np.ndarray") -> "np.ndarray":
    """Mean results delivered by time t, across every run including failures.

    Each run contributes a step function that counts its result timestamps up to
    t and then stays flat once the run ended - a timed-out run keeps whatever it
    delivered rather than dropping out. That keeps the curve free of the
    survivorship bias a "successful runs only" version would carry.

    The mean, not the median: partial progress is often confined to a minority
    of runs (24 results spread over 30 runs on short-6), and a median reports
    that as a flat zero - erasing the very thing the curve exists to show.
    """
    if runs.empty:
        return np.zeros_like(grid)
    counts = np.vstack([np.searchsorted(np.sort(ts), grid, side="right")
                        for ts in runs["timestamps"]])
    return counts.mean(axis=0)


def _arrival_window(runs: pd.DataFrame) -> tuple[float, float]:
    """The span of time over which `runs` deliver results, padded a little.

    Before the first result every curve sits at zero and after the last one it is
    flat, so this is the only stretch of a linear axis with anything to read. A
    template that never delivered anything falls back to its whole run time.
    """
    stamps = [t for ts in runs["timestamps"] for t in ts]
    if not stamps:
        return 0.0, max(float(runs["time_ms"].max()), 1.0)
    first, last = float(min(stamps)), float(max(stamps))
    pad = max(0.05 * (last - first), 0.01 * last, 1.0)
    return max(first - pad, 0.0), last + pad


def plot_arrival_curves(df: pd.DataFrame, theme: str = "light",
                        out_dir: Path = FIGURE_DIR, scale: str = "log") -> Path:
    """Small multiples: results delivered over elapsed time, one panel per template.

    This is throughput as a shape rather than a single number - a steep early
    curve that plateaus reads differently from a slow linear one, and both
    average to the same results-per-second.

    `scale="log"` puts every panel on one log time axis over the full run budget.
    `scale="linear"` gives each panel its own linear axis, zoomed onto the window
    in which that template's results arrive (see `_arrival_window`): the shape of
    delivery is honest there, but panels no longer share a time axis.
    """
    if scale not in ARRIVAL_SCALES:
        raise ValueError(f"scale must be one of {ARRIVAL_SCALES}, got {scale!r}")
    palette = THEMES[theme]
    engines = engine_order(df)
    # Lines are an adjacent form, and the palette clears its gates on that pairlist for
    # all eight slots. Beyond three a reader may still compare two non-adjacent lines,
    # where hue alone is not enough (magenta vs orange measures 12.9 normal-vision,
    # below the 15 floor), so each series also carries its own dash pattern.
    if len(engines) > len(THEMES[theme]["series"]):
        raise ValueError(
            f"{len(engines)} series requested but only {len(THEMES[theme]['series'])} "
            "categorical slots exist; facet rather than cycling hues")
    templates = template_order(df)
    log_grid = np.logspace(1, np.log10(df["time_ms"].max()), 250)

    fig, axes = _facet_grid(len(templates), palette, panel_height=2.5)
    for index, template in enumerate(templates):
        ax = axes[index]
        if scale == "log":
            grid = log_grid
        else:
            # Denser than the log grid: steps are drawn at grid resolution, and
            # the zoomed window makes each one wide enough to see.
            grid = np.linspace(*_arrival_window(df[df["template"] == template]), 600)
        for slot, engine in enumerate(engines):
            runs = df[(df["template"] == template) & (df["engine"] == engine)]
            ax.plot(grid, _delivery_curve(runs, grid), color=series_color(theme, slot),
                    linestyle=series_dash(slot), dash_capstyle="round",
                    linewidth=2, solid_joinstyle="round", zorder=2)
        if scale == "log":
            ax.set_xscale("log")
        else:
            ax.set_xlim(grid[0], grid[-1])
            ax.xaxis.set_major_locator(MaxNLocator(4))
            ax.xaxis.set_major_formatter(
                FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.set_ylim(bottom=0)
        if ax.get_ylim()[1] < 1:
            # A panel where nothing was ever delivered still reads as 0..1,
            # not as a fractional axis around zero.
            ax.set_ylim(0, 1)
        ax.set_title(_short(template), fontsize=9.5, color=palette["text_primary"],
                     loc="left", pad=6)
        _style_axes(ax, palette, grid_axis="both")
        ax.tick_params(labelsize=7.5)

    fig.suptitle("Results delivered over elapsed time (mean across all runs)",
                 color=palette["text_primary"], fontsize=12, x=0.012, ha="left", y=0.995)
    _engine_legend(fig, engines, theme, palette, dashed=True, loc="upper left",
                   bbox_to_anchor=(0.012, 0.978))
    xlabel = ("elapsed milliseconds (log scale)" if scale == "log" else
              "elapsed milliseconds (linear, zoomed per panel)")
    fig.supxlabel(xlabel, color=palette["text_secondary"], fontsize=9)
    fig.supylabel("results delivered", color=palette["text_secondary"], fontsize=9)
    note = "partial output from timed-out runs is included"
    if scale == "linear":
        note += ("; each panel spans only the window in which results arrive, "
                 "so time axes differ between panels")
    fig.text(0.012, 0.002, note, fontsize=8, color=palette["text_muted"])
    # Leave the legend its own band under the title, however many rows it wraps to
    fig.tight_layout(rect=(0.012, 0.022, 1, 0.99 - 0.021 * legend_rows(engines)))
    name = "result-arrival-curves" if scale == "log" else "result-arrival-curves-linear"
    return _save(fig, palette, out_dir, name, theme)


def plot_crossover(df: pd.DataFrame, theme: str = "light",
                   out_dir: Path = FIGURE_DIR) -> Path:
    """Speedup against how expensive the query is for the baseline engine.

    One mark per (template, instance), so this is an all-pairs form: a single
    series, no categorical palette needed. It is drawn per instance rather than
    per template deliberately -- the instances of one template can land on
    opposite sides of break-even, and a per-template mark would hide exactly
    that.
    """
    from .aggregate import per_instance as _per_instance

    palette = THEMES[theme]
    engines = engine_order(df)
    baseline, others = engines[0], engines[1:]
    if not others:
        raise ValueError("the crossover view needs at least one engine to compare")
    # A scatter is an all-pairs form, so the categorical palette caps at three.
    if len(others) > 3:
        raise ValueError("at most 3 engines can be compared against the baseline; "
                         "facet instead of seating a 4th hue")

    wide = _per_instance(df, "time_ms").pivot_table(
        index=["template", "instance"], columns="engine", values="value")
    if baseline not in wide.columns:
        raise ValueError(f"no successful runs for the baseline engine {baseline}")

    fig, ax = plt.subplots(figsize=(9.2, 5.6), facecolor=palette["surface"])

    points = []
    for slot, engine in enumerate(others):
        if engine not in wide.columns:
            continue
        pair = wide[[baseline, engine]].dropna()
        pair = pair[(pair[baseline] > 0) & (pair[engine] > 0)]
        if pair.empty:
            continue
        xs = pair[baseline].astype(float)
        ys = (pair[engine] / pair[baseline]).astype(float)
        if len(others) == 1:
            for mask, role in ((ys < 1, "good"), (ys >= 1, "critical")):
                ax.scatter(xs[mask], ys[mask], s=55, color=STATUS[role],
                           edgecolor=palette["surface"], linewidth=1.2, zorder=3)
        else:
            ax.scatter(xs, ys, s=55, color=series_color(theme, slot), label=engine,
                       edgecolor=palette["surface"], linewidth=1.2, zorder=3)
        points.extend(zip(xs, ys))
    if not points:
        raise ValueError("no instance was completed by the baseline and another "
                         "engine, so there is nothing to compare")

    top = max(py for _, py in points)
    ax.axhspan(1, max(top * 1.6, 2), color=palette["grid"], alpha=0.45, zorder=0)
    ax.axhline(1, color=palette["text_muted"], linewidth=1, linestyle=(0, (4, 3)),
               zorder=1)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(f"execution time for {baseline} on that instance (ms, log scale)",
                  color=palette["text_secondary"], fontsize=9)
    label = others[0] if len(others) == 1 else "engine"
    ax.set_ylabel(f"{label} / {baseline}  (log scale)",
                  color=palette["text_secondary"], fontsize=9)
    ax.set_title(f"Per-instance speedup against how expensive the query is for {baseline}",
                 color=palette["text_primary"], fontsize=12, pad=16, loc="left")
    _style_axes(ax, palette, grid_axis="both")

    ax.annotate(f"slower than {baseline}", (0.012, 0.95), xycoords="axes fraction",
                fontsize=8.5, color=palette["text_muted"], va="top")
    ax.annotate(f"faster than {baseline}", (0.012, 0.05), xycoords="axes fraction",
                fontsize=8.5, color=palette["text_muted"], va="bottom")

    if len(others) > 1:
        legend = ax.legend(loc="lower right", bbox_to_anchor=(1, 1.01), frameon=False,
                           fontsize=9, ncol=len(others), handletextpad=0.4)
        for text in legend.get_texts():
            text.set_color(palette["text_secondary"])

    fig.text(0.008, 0.012,
             "one mark per (template, instance) both engines completed; "
             "dashed line is break-even",
             fontsize=8, color=palette["text_muted"])
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    return _save(fig, palette, out_dir, "speedup-vs-query-cost", theme)


def plot_all(df: pd.DataFrame, out_dir: Path = FIGURE_DIR,
             layouts: tuple[str, ...] = LAYOUTS, theme: str = "light",
             arrival_scales: tuple[str, ...] = ARRIVAL_SCALES) -> list[Path]:
    """Every figure in one theme, one subdirectory per group in `GROUPS`."""
    dirs = {key: out_dir / name for key, name in GROUPS.items()}
    figures = [plot_metric_by_template(df, metric, theme, layout, dirs["per_template"])
               for metric in TEMPLATE_METRICS for layout in layouts]
    figures += [plot_instance_spread(df, metric, theme, dirs["per_instance"],
                                     include_failed=include_failed)
                for metric, include_failed in INSTANCE_METRICS.items()]
    figures.append(plot_completion(df, theme, dirs["completion"]))
    figures += [plot_arrival_curves(df, theme, dirs["completion"], scale)
                for scale in arrival_scales]
    figures.append(plot_variance_share(df, "time_ms", theme, dirs["heterogeneity"]))
    if 1 < len(engine_order(df)) <= 4:
        figures.append(plot_crossover(df, theme, dirs["heterogeneity"]))
    return figures
