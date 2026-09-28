"""Run the full analysis: tidy data -> agreement tables + per-template figures."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from analysis.config import FIGURE_DIR, OUTPUT_DIR, TABLE_DIR
from analysis.completion import (completion_summary, matched_timing, par_scores,
                                 progress_summary, startup_decomposition)
from analysis.correctness import per_query_agreement, per_template_agreement, to_markdown
from analysis.heterogeneity import (instance_ratio_spread, variance_decomposition,
                                    winner_by_instance)
from analysis.aggregate import per_instance
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

    variance = variance_decomposition(df)
    ratio_spread = instance_ratio_spread(df)
    winners = winner_by_instance(df)
    _write(variance, "instance_variance")
    _write(ratio_spread, "instance_ratio_spread")
    _write(winners, "winner_by_instance")
    _write(per_instance(df, "time_ms"), "per_instance_time")

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
        "## How the numbers are aggregated",
        "",
        "Every summary below collapses the runs in two stages: the median over "
        "the replications of one instance, then the geometric mean over the "
        "instances of a template. Replications differ by run noise, which a "
        "median absorbs; instances differ by orders of magnitude, and a "
        "geometric mean weighs a 10x-slower instance as 10x rather than letting "
        "it dominate the way an arithmetic mean would. Equal weight per instance "
        "means an engine cannot move a template's summary by failing more often "
        "on the hard instance.",
        "",
        "Read the next section before trusting any template-level number.",
        "",
        "## Do the instances of a template behave alike?",
        "",
        "Mostly not. `instance_share` is the fraction of log-scale spread that "
        "lies between the instances of a template rather than between "
        "replications of one instance; `spread_factor` is the slowest instance "
        "median over the fastest, and `run_noise_factor` the same spread within "
        "one instance. Where the first dwarfs the second, more replications buy "
        "nothing -- the uncertainty is in which constants the template was bound "
        "to, not in the measurement.",
        "",
        to_markdown(variance),
        "",
        "### Does the engine comparison survive per instance?",
        "",
        "The template-level ratio recomputed on each instance separately. A row "
        "marked `straddles_break_even` is one where the engines trade wins "
        "instance by instance, so the single ratio is an average over a "
        "disagreement, not a direction.",
        "",
        to_markdown(ratio_spread) if len(ratio_spread) else "_None._",
        "",
        "### Which engine wins each individual instance",
        "",
        to_markdown(winners) if len(winners) else "_None._",
        "",
        "## Per-template performance (completed runs only -- survivorship-biased)",
        "",
        "`geomean` is the two-stage aggregate, `pooled_median` the single-stage "
        "median over all runs at once. Where the two disagree, the template is a "
        "mixture of instances and the table above says by how much.",
        "",
        to_markdown(per_template_performance(df, "time_ms")),
        "",
        "## Time to last result",
        "",
        to_markdown(per_template_performance(df, "last_result_ms")),
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
        "## Setup cost, streaming, and the tail",
        "",
        "Each run split into three phases: reaching the first result, streaming "
        "the rest, and whatever happens after the last result has arrived. The "
        "middle phase is nearly empty in this dataset -- results arrive in a "
        "burst -- so `after_last_result` is where the time that is not startup "
        "actually goes, and an engine can deliver every answer early and still "
        "finish late.",
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
