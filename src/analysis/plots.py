"""Per-template comparison figures, one series per engine.

Execution time spans three orders of magnitude across the templates, so the
magnitude comparison is a dot-and-range plot on a log axis rather than bars: a
bar needs a zero baseline, which a log axis does not have.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

import numpy as np

from .config import (FIGURE_DIR, OUTCOME_STATUS, STATUS, THEMES, series_color,
                     series_dash)
from .loading import engine_order, template_order

METRICS = {
    "time_ms": ("Query execution time", "milliseconds (log scale)", True),
    "http_requests": ("HTTP requests issued", "requests (log scale)", True),
    "first_result_ms": ("Time to first result", "milliseconds (log scale)", True),
    "throughput_per_s": ("Result throughput", "results per second (log scale)", True),
}

# Vertical offset between engine series inside one template row.
_ROW_PITCH = 0.62


def _summarise(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Median and interquartile range per (template, engine), successful runs only."""
    ok = df[~df["failed"]].dropna(subset=[metric])
    grouped = ok.groupby(["template", "engine"])[metric]
    return grouped.agg(
        median="median",
        low=lambda s: s.quantile(0.25),
        high=lambda s: s.quantile(0.75),
        n="size",
    ).reset_index()


def plot_metric_by_template(
    df: pd.DataFrame,
    metric: str,
    theme: str = "light",
    out_dir: Path = FIGURE_DIR,
) -> Path:
    """Dot = median across replications and instances; bar = interquartile range."""
    title, xlabel, log_scale = METRICS[metric]
    palette = THEMES[theme]
    engines = engine_order(df)
    templates = template_order(df)
    stats = _summarise(df, metric)

    height = 0.44 * len(templates) + 1.9
    fig, ax = plt.subplots(figsize=(9.2, height), facecolor=palette["surface"])
    ax.set_facecolor(palette["surface"])

    offsets = [(i - (len(engines) - 1) / 2) * (_ROW_PITCH / max(len(engines), 2))
               for i in range(len(engines))]

    for slot, engine in enumerate(engines):
        color = series_color(theme, slot)
        for row_index, template in enumerate(templates):
            cell = stats[(stats["template"] == template) & (stats["engine"] == engine)]
            if cell.empty:
                continue
            cell = cell.iloc[0]
            y = row_index + offsets[slot]
            # 2px range line, then the median marker with a surface ring so
            # overlapping engines stay separable.
            ax.plot([cell["low"], cell["high"]], [y, y], color=color, linewidth=2,
                    solid_capstyle="round", zorder=2)
            ax.plot([cell["median"]], [y], marker="o", markersize=8, color=color,
                    markeredgecolor=palette["surface"], markeredgewidth=1.5,
                    linestyle="none", zorder=3,
                    label=engine if row_index == 0 else None)
            if row_index == 0 and len(engines) <= 4:
                # Direct label on the first row: identity is never colour alone.
                ax.annotate(engine, (cell["high"], y), textcoords="offset points",
                            xytext=(8, 0), va="center", fontsize=8.5, color=color)

    # Templates where nothing completed get a note rather than a silent gap.
    for row_index, template in enumerate(templates):
        if stats[stats["template"] == template].empty:
            ax.text(0.01, row_index, "no successful runs", transform=ax.get_yaxis_transform(),
                    va="center", ha="left", fontsize=8, style="italic",
                    color=palette["text_muted"])

    if log_scale:
        ax.set_xscale("log")
    ax.set_yticks(range(len(templates)))
    ax.set_yticklabels([t.replace("interactive-", "") for t in templates],
                       color=palette["text_secondary"], fontsize=9)
    ax.invert_yaxis()
    ax.set_ylim(len(templates) - 0.5, -0.5)

    ax.set_xlabel(xlabel, color=palette["text_secondary"], fontsize=9)
    # The legend sits in its own band under the title, wrapped to at most three
    # columns: five configuration names on one row are wider than the figure, which
    # clipped the first entry and ran the rest into the title.
    legend_columns = min(len(engines), 3)
    legend_rows = -(-len(engines) // legend_columns)
    ax.set_title(f"{title} per query template", color=palette["text_primary"],
                 fontsize=12, pad=20 + 14 * legend_rows, loc="left")

    ax.grid(axis="x", color=palette["grid"], linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(palette["grid"])
    ax.tick_params(colors=palette["text_secondary"], length=0)

    legend = ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), frameon=False,
                       fontsize=9, ncol=legend_columns, handletextpad=0.4,
                       columnspacing=1.6)
    for text in legend.get_texts():
        text.set_color(palette["text_secondary"])

    fig.text(0.008, 0.008,
             "dot = median, bar = interquartile range; errored runs excluded",
             fontsize=8, color=palette["text_muted"])
    fig.tight_layout(rect=(0, 0.03, 1, 1))

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{metric}-by-template-{theme}.png"
    fig.savefig(path, dpi=200, facecolor=palette["surface"])
    fig.savefig(path.with_suffix(".pdf"), facecolor=palette["surface"])
    plt.close(fig)
    return path


def _style_axes(ax, palette, grid_axis: str = "x") -> None:
    ax.set_facecolor(palette["surface"])
    ax.grid(axis=grid_axis, color=palette["grid"], linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(palette["grid"])
    ax.tick_params(colors=palette["text_secondary"], length=0)


def plot_completion(df: pd.DataFrame, theme: str = "light",
                    out_dir: Path = FIGURE_DIR) -> Path:
    """How every run ended, per template per engine.

    Answers directly whether one engine finishes more of the workload than
    another, which the timing figures cannot show because they plot only the
    runs that finished.
    """
    palette = THEMES[theme]
    engines = engine_order(df)
    templates = template_order(df)
    kinds = ["ok", "timeout", "crash", "unsupported"]

    # One row per template per engine. The pitch tightens once there are many rows so
    # the figure stays a readable page rather than a strip metres long; with two or
    # three engines it is unchanged.
    total_rows = len(templates) * len(engines)
    row_height = min(0.34, 14.0 / total_rows)
    label_size = 8 if row_height > 0.24 else 6.5
    fig, ax = plt.subplots(figsize=(9.2, row_height * total_rows + 2.2),
                           facecolor=palette["surface"])

    labels, positions, row = [], [], 0.0
    for template in templates:
        for slot, engine in enumerate(engines):
            runs = df[(df["template"] == template) & (df["engine"] == engine)]
            left = 0
            for kind in kinds:
                width = int((runs["failure_kind"] == kind).sum())
                if not width:
                    continue
                ax.barh(row, width, left=left, height=0.78, color=OUTCOME_STATUS[kind],
                        edgecolor=palette["surface"], linewidth=1.5, zorder=2)
                if width >= 4:
                    # Label inside the segment: status colour never stands alone.
                    ax.text(left + width / 2, row, str(width), ha="center", va="center",
                            fontsize=min(7.5, label_size + 0.5), color="#ffffff", zorder=3)
                left += width
            labels.append(f"{template.replace('interactive-', '')}  ·  {engine}")
            positions.append(row)
            row += 1
        row += 0.5

    ax.set_yticks(positions)
    ax.set_yticklabels(labels, color=palette["text_secondary"], fontsize=label_size)
    ax.invert_yaxis()
    ax.set_xlabel("runs", color=palette["text_secondary"], fontsize=9)
    ax.set_title("How each run ended, per template and engine",
                 color=palette["text_primary"], fontsize=12, pad=38, loc="left")
    _style_axes(ax, palette)

    handles = [plt.Line2D([], [], marker="s", linestyle="none", markersize=9,
                          color=OUTCOME_STATUS[k], label=k) for k in kinds]
    legend = ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.005),
                       frameon=False, fontsize=9, ncol=len(kinds), handletextpad=0.4,
                       columnspacing=1.6)
    for text in legend.get_texts():
        text.set_color(palette["text_secondary"])

    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"completion-by-template-{theme}.png"
    fig.savefig(path, dpi=200, facecolor=palette["surface"])
    fig.savefig(path.with_suffix(".pdf"), facecolor=palette["surface"])
    plt.close(fig)
    return path


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


def plot_arrival_curves(df: pd.DataFrame, theme: str = "light",
                        out_dir: Path = FIGURE_DIR) -> Path:
    """Small multiples: results delivered over elapsed time, one panel per template.

    This is throughput as a shape rather than a single number - a steep early
    curve that plateaus reads differently from a slow linear one, and both
    average to the same results-per-second.
    """
    palette = THEMES[theme]
    engines = engine_order(df)
    # Lines are an adjacent form, and the palette clears its gates on that pairlist for
    # all eight slots. Beyond three a reader may still compare two non-adjacent lines,
    # where hue alone is not enough, so each series also carries its own dash pattern.
    if len(engines) > len(THEMES[theme]["series"]):
        raise ValueError(
            f"{len(engines)} series requested but only {len(THEMES[theme]['series'])} "
            "categorical slots exist; facet rather than cycling hues")
    templates = template_order(df)
    grid = np.logspace(1, np.log10(df["time_ms"].max()), 250)

    cols = 3
    rows = -(-len(templates) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(11.5, 2.5 * rows),
                             facecolor=palette["surface"], squeeze=False)

    for index, template in enumerate(templates):
        ax = axes[index // cols][index % cols]
        for slot, engine in enumerate(engines):
            runs = df[(df["template"] == template) & (df["engine"] == engine)]
            ax.plot(grid, _delivery_curve(runs, grid), color=series_color(theme, slot),
                    linewidth=1.8, linestyle=series_dash(slot), solid_joinstyle="round",
                    dash_capstyle="round", label=engine if index == 0 else None, zorder=2)
        ax.set_xscale("log")
        ax.set_ylim(bottom=0)
        if ax.get_ylim()[1] < 1:
            # A panel where nothing was ever delivered still reads as 0..1,
            # not as a fractional axis around zero.
            ax.set_ylim(0, 1)
        ax.set_title(template.replace("interactive-", ""), fontsize=9.5,
                     color=palette["text_primary"], loc="left", pad=6)
        _style_axes(ax, palette, grid_axis="both")
        ax.tick_params(labelsize=7.5)

    for index in range(len(templates), rows * cols):
        axes[index // cols][index % cols].set_visible(False)

    fig.suptitle("Results delivered over elapsed time (mean across all runs)",
                 color=palette["text_primary"], fontsize=12, x=0.012, ha="left", y=0.998)
    handles, labels = axes[0][0].get_legend_handles_labels()
    # Its own band under the title: with five configuration names a single row spans
    # the figure and would run into the title.
    legend = fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.012, 0.978),
                        frameon=False, fontsize=9, ncol=min(len(engines), 3),
                        handlelength=2.6, columnspacing=1.8)
    for text in legend.get_texts():
        text.set_color(palette["text_secondary"])

    fig.supxlabel("elapsed milliseconds (log scale)", color=palette["text_secondary"],
                  fontsize=9)
    fig.supylabel("results delivered", color=palette["text_secondary"], fontsize=9)
    fig.text(0.012, 0.002, "partial output from timed-out runs is included",
             fontsize=8, color=palette["text_muted"])
    fig.tight_layout(rect=(0.012, 0.022, 1, 0.995 - 0.022 * (1 + (len(engines) - 1) // 3)))

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"result-arrival-curves-{theme}.png"
    fig.savefig(path, dpi=200, facecolor=palette["surface"])
    fig.savefig(path.with_suffix(".pdf"), facecolor=palette["surface"])
    plt.close(fig)
    return path


def plot_crossover(df: pd.DataFrame, theme: str = "light",
                   out_dir: Path = FIGURE_DIR) -> Path:
    """Speedup against how expensive the query is for the baseline engine.

    One mark per template, so this is an all-pairs form: a single series, direct
    labelled, no categorical palette needed. The break-even line at 1.0 is the
    point of the figure - which side a template lands on is predicted by how
    long the baseline took, not by anything about the template itself.
    """
    from .completion import matched_timing

    palette = THEMES[theme]
    engines = engine_order(df)
    baseline, others = engines[0], engines[1:]
    if not others:
        raise ValueError("the crossover view needs at least one engine to compare")
    # A scatter is an all-pairs form, so the categorical palette caps at three.
    if len(others) > 3:
        raise ValueError("at most 3 engines can be compared against the baseline; "
                         "facet instead of seating a 4th hue")

    matched = matched_timing(df, "time_ms")

    fig, ax = plt.subplots(figsize=(9.2, 5.6), facecolor=palette["surface"])
    top = max(matched[f"vs_{baseline}::{e}"].dropna().astype(float).max() for e in others)
    ax.axhspan(1, max(top * 1.6, 2), color=palette["grid"], alpha=0.45, zorder=0)
    ax.axhline(1, color=palette["text_muted"], linewidth=1, linestyle=(0, (4, 3)), zorder=1)

    # One comparison engine: colour each mark by which side of break-even it
    # lands on. Several: colour carries engine identity instead, and the shaded
    # region plus the break-even line carry the win/lose reading.
    points = []
    for slot, engine in enumerate(others):
        col = matched[[f"median::{baseline}", f"vs_{baseline}::{engine}"]].dropna()
        xs = col[f"median::{baseline}"].astype(float)
        ys = col[f"vs_{baseline}::{engine}"].astype(float)
        if len(others) == 1:
            for mask, role in ((ys < 1, "good"), (ys >= 1, "critical")):
                ax.scatter(xs[mask], ys[mask], s=70, color=STATUS[role],
                           edgecolor=palette["surface"], linewidth=1.5, zorder=3)
        else:
            ax.scatter(xs, ys, s=70, color=series_color(theme, slot), label=engine,
                       edgecolor=palette["surface"], linewidth=1.5, zorder=3)
        points.extend(zip(xs, ys, matched.loc[col.index, "template"]))
    if not points:
        raise ValueError("no template was completed by every engine, so there is "
                         "nothing to compare")

    ax.set_xscale("log")
    ax.set_yscale("log")
    # Widen the x range before placing labels so the rightmost one has somewhere
    # to sit; matplotlib's autoscale does not account for annotation extents.
    xs_all = [px for px, _, _ in points]
    ax.set_xlim(min(xs_all) * 0.55, max(xs_all) * 2.4)

    # Greedy de-collision: labels sit right of their mark, flipping left near the
    # edge, and alternate vertically when two marks land close together.
    # With several comparison engines the marks for one template share an x, so
    # the template is labelled once, at its topmost mark; hue carries the engine.
    if len(others) == 1:
        to_label = points
    else:
        best = {}
        for px, py, name in points:
            if name not in best or py > best[name][1]:
                best[name] = (px, py, name)
        to_label = list(best.values())

    placed, flip = [], False
    for xi, yi, name in sorted(to_label, key=lambda p: p[0]):
        near = any(abs(np.log10(xi) - np.log10(px)) < 0.12
                   and abs(np.log10(yi) - np.log10(py)) < 0.12 for px, py in placed)
        flip = not flip if near else False
        right_edge = xi > max(xs_all) * 0.5
        ax.annotate(name.replace("interactive-", ""), (xi, yi),
                    textcoords="offset points",
                    xytext=(-10 if right_edge else 10, 9 if flip else -3.5),
                    ha="right" if right_edge else "left",
                    fontsize=8.5, color=palette["text_secondary"])
        placed.append((xi, yi))
    ax.set_xlabel(f"median execution time for {baseline} (ms, log scale)",
                  color=palette["text_secondary"], fontsize=9)
    label = others[0] if len(others) == 1 else "engine"
    ax.set_ylabel(f"{label} / {baseline}  (log scale)",
                  color=palette["text_secondary"], fontsize=9)
    ax.set_title(f"Speedup against how expensive the query is for {baseline}",
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

    fig.text(0.008, 0.012, "matched instances only; dashed line is break-even",
             fontsize=8, color=palette["text_muted"])
    fig.tight_layout(rect=(0, 0.035, 1, 1))

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"speedup-vs-query-cost-{theme}.png"
    fig.savefig(path, dpi=200, facecolor=palette["surface"])
    fig.savefig(path.with_suffix(".pdf"), facecolor=palette["surface"])
    plt.close(fig)
    return path


def plot_all(df: pd.DataFrame, out_dir: Path = FIGURE_DIR) -> list[Path]:
    figures = [plot_metric_by_template(df, metric, theme, out_dir)
               for metric in METRICS for theme in ("light", "dark")]
    for theme in ("light", "dark"):
        figures.append(plot_completion(df, theme, out_dir))
        figures.append(plot_arrival_curves(df, theme, out_dir))
        if 1 < len(engine_order(df)) <= 4:
            figures.append(plot_crossover(df, theme, out_dir))
    return figures
