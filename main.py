"""Run the full analysis: tidy data -> agreement tables + per-template figures."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from analysis.config import FIGURE_DIR, OUTPUT_DIR, TABLE_DIR
from analysis.completion import (completion_summary, matched_timing, par_scores,
                                 progress_summary, startup_decomposition)
from analysis.correctness import per_query_agreement, per_template_agreement, to_markdown
from analysis.loading import discover_datasets, engine_order, load_runs
from analysis.performance import METRICS, error_summary, per_template_performance
from analysis.plots import plot_all


def _write(table, name: str) -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(TABLE_DIR / f"{name}.csv", index=False)
    (TABLE_DIR / f"{name}.md").write_text(to_markdown(table) + "\n")


def main() -> None:
    df = load_runs()
    engines = engine_order(df)
    print(f"loaded {len(df)} runs from {len(discover_datasets())} engines: {', '.join(engines)}")

    per_query = per_query_agreement(df)
    per_template = per_template_agreement(per_query, df)
    errors = error_summary(df)

    _write(df.drop(columns=["timestamps"]), "runs")
    _write(per_query, "agreement_per_query")
    _write(per_template, "agreement_per_template")
    _write(errors, "errors")
    for metric in METRICS:
        _write(per_template_performance(df, metric), f"performance_per_template_{metric}")

    completion = completion_summary(df)
    matched = matched_timing(df)
    par = par_scores(df)
    progress = progress_summary(df)
    _write(completion, "completion_per_template")
    _write(matched, "timing_matched_per_template")
    _write(par, "par2_per_template")
    _write(progress, "progress_and_throughput_per_template")
    startup = startup_decomposition(df)
    _write(startup, "startup_decomposition")

    figures = plot_all(df)

    mismatches = per_query[per_query["status"] == "MISMATCH"]
    report = [
        "# Derived-resource benchmark analysis",
        "",
        f"Engines compared: {', '.join(f'`{e}`' for e in engines)}. "
        f"{len(df)} runs over {df['template'].nunique()} templates "
        f"x {df['instance'].nunique()} instances x {df['replication'].nunique()} replications.",
        "",
        "## Result agreement per template",
        "",
        to_markdown(per_template),
        "",
        f"## Query instances that disagree ({len(mismatches)})",
        "",
        to_markdown(mismatches) if len(mismatches) else "_None._",
        "",
        "## Completion",
        "",
        "How every run ended. Timing tables that drop failed runs are biased by "
        "whatever is in this table, so read it first.",
        "",
        to_markdown(completion),
        "",
        "## Per-template performance (completed runs only -- survivorship-biased)",
        "",
        to_markdown(per_template_performance(df, "time_ms")),
        "",
        "## Per-template timing, matched instances only",
        "",
        "Restricted to the (template, instance) pairs every engine completed, so "
        "the engines are compared on the same queries. `instances_used` versus "
        "`instances_total` says how much of the workload each row rests on.",
        "",
        to_markdown(matched),
        "",
        "## PAR-2 (failures penalised, not dropped)",
        "",
        "A run that never finished counts as 2x the 300s budget. An engine cannot "
        "look fast here by failing more often. Read alongside completion.",
        "",
        to_markdown(par),
        "",
        "## Setup cost vs streaming speed",
        "",
        "Each run split at its first result. A fixed setup cost and a faster "
        "execution phase cancel into one unremarkable end-to-end ratio; split "
        "apart, they are the same story rather than two contradictory ones.",
        "",
        to_markdown(startup),
        "",
        "## Progress and throughput",
        "",
        "`median_delivered` and `from_failed_runs` count partial output from runs "
        "that timed out or crashed; throughput is over completed runs only.",
        "",
        to_markdown(progress),
        "",
        "## Errors",
        "",
        to_markdown(errors) if len(errors) else "_None._",
        "",
        "## Figures",
        "",
        *[f"- `{p.relative_to(OUTPUT_DIR.parent)}`" for p in figures],
        "",
    ]
    (OUTPUT_DIR / "report.md").write_text("\n".join(report))

    print(f"tables  -> {TABLE_DIR}")
    print(f"figures -> {FIGURE_DIR}")
    print(f"report  -> {OUTPUT_DIR / 'report.md'}")
    print(f"\n{len(mismatches)} of {len(per_query)} query instances disagree between engines.")


if __name__ == "__main__":
    main()
