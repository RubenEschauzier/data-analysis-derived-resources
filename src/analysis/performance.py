"""Per-template performance summary, with each engine indexed to the baseline."""

from __future__ import annotations

import pandas as pd

from .loading import engine_order, template_order

METRICS = ["time_ms", "http_requests"]


def per_template_performance(df: pd.DataFrame, metric: str = "time_ms") -> pd.DataFrame:
    """Median and IQR per template per engine, plus a ratio against the baseline.

    The baseline is the first engine in `engine_order` (`default` when present).
    Ratios below 1 mean the engine was faster / issued fewer requests.
    """
    engines = engine_order(df)
    baseline = engines[0]
    order = {t: i for i, t in enumerate(template_order(df))}
    ok = df[~df["failed"]].dropna(subset=[metric])

    rows = []
    for template in template_order(df):
        row = {"template": template}
        medians = {}
        for engine in engines:
            values = ok[(ok["template"] == template) & (ok["engine"] == engine)][metric]
            if values.empty:
                row[f"median::{engine}"] = pd.NA
                row[f"iqr::{engine}"] = "-"
                continue
            medians[engine] = values.median()
            row[f"median::{engine}"] = round(values.median(), 1)
            row[f"iqr::{engine}"] = f"{values.quantile(0.25):.0f}-{values.quantile(0.75):.0f}"
        for engine in engines[1:]:
            ratio = pd.NA
            if engine in medians and medians.get(baseline):
                ratio = round(medians[engine] / medians[baseline], 2)
            row[f"vs_{baseline}::{engine}"] = ratio
        rows.append(row)

    table = pd.DataFrame(rows)
    table["_order"] = table["template"].map(order)
    return table.sort_values("_order").drop(columns="_order").reset_index(drop=True)


def _one_line(message: str, width: int = 110) -> str:
    """Engine errors span several lines; keep tables readable."""
    flat = " ".join(str(message).split())
    return flat if len(flat) <= width else flat[: width - 1] + "\u2026"


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
