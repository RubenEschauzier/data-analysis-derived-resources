# Derived-resource benchmark analysis

Compares SPARQL query-execution runs from two or more engine configurations over
the same set of query templates: does each configuration return the *same
answers*, and how fast does it get there?

## Layout

```
data/                              raw benchmark output, one file per engine
  query-results-raw-<engine>.json    <engine> is taken from the filename
src/analysis/
  config.py                        paths + the validated chart palette
  loading.py                       raw JSON -> one tidy row per query run
  aggregate.py                     two-stage collapse: median over replications,
                                   geometric mean over instances
  heterogeneity.py                 do the instances of a template behave alike?
  correctness.py                   result-count and result-hash agreement
  completion.py                    completion rates, PAR-2, matched timing,
                                   progress, setup-vs-streaming decomposition
  performance.py                   per-template timing summary + error breakdown
  plots.py                         per-template comparison figures
main.py                            runs everything, writes output/
output/
  tables/*.csv, *.md               every table, machine- and human-readable
  figures/*.png, *.pdf             light and dark rendering of each figure
  report.md                        all tables + figure paths in one document
```

## Running

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

## Adding an engine

Drop another `data/query-results-raw-<engine>.json` in place and re-run. Engines
are discovered from the filenames, the tables grow a column group per engine,
and the figures grow a series. `default` is the baseline for every ratio column
when present, otherwise the alphabetically first engine. Verified end to end on
three engines.

Two caps, both of which raise rather than degrade quietly. Categorical hues come
from a fixed eight-slot order and are never cycled, so the per-metric figures
take up to 8 engines. The all-pairs forms - the arrival-curve small multiples
and the speedup scatter - cap at 3 series, because past three the palette cannot
hold separation under colour-vision deficiency; facet instead of seating a
fourth hue.

One thing to watch when a third engine arrives: `matched_timing` and
`startup_decomposition` intersect over *every* engine, so a template only counts
if all of them completed it. Adding an engine that fails somewhere new shrinks
the matched set for the comparisons that were already there - which is correct,
but it means a ratio can move without either of the original engines changing.
`instances_used` / `instances_total` is what tells you that happened.

## How agreement is decided

- **Errored runs are excluded from the comparison.** A run that errors still
  reports the partial result set it had reached, so its hash says nothing about
  correctness. Error rates are reported separately as `runs_ok` and in
  `output/tables/errors.md`.
- For each (template, instance) the *set* of result counts and the *set* of
  result hashes each engine produced across its replications are compared. Sets
  differ -> `MISMATCH`. An engine with no successful run -> `no data`.
- The `nondeterministic` column flags instances where an engine disagreed with
  *itself* across replications. A `MISMATCH` on such a row is not evidence that
  the engines compute different answers — an unordered `LIMIT` produces it too.
  Read those rows with the stable mismatches held apart.

## How the numbers are aggregated

The workload is 15 templates x 5 instances x 6 replications per engine. Those
two nestings are not the same kind of variation, so they are not collapsed the
same way. Every summary is **two-stage**:

1. **Median over the replications** of one instance. Replications of the same
   query differ by run-to-run noise, which a median absorbs.
2. **Geometric mean over the instances** of a template. Timings are
   ratio-scaled and right-skewed: an arithmetic mean is dragged by the slowest
   instance, and a second median would discard the slow instances rather than
   weigh them. The geometric mean is also the only mean that commutes with
   ratios — the geomean of the per-instance speedups equals the ratio of the
   geomeans — so the headline number and the per-query speedups cannot
   contradict each other.

Equal weight per instance at stage 2 is the point: an engine cannot shift a
template's summary by failing more often on the hard instance.

`per_template_performance` keeps the old single-stage `pooled_median` beside the
`geomean` on purpose. Where the two disagree, the template is a mixture of
instances rather than one query, and the heterogeneity tables say by how much.

## Instances of one template are not interchangeable

This is worth knowing before reading any template-level number. On
`interactive-discover-6` the five instance medians for `adaptive` are roughly
116s, 1.9s, 1.7s, 113s, 2.0s — a 66x range — and *which* instances are slow
differs per engine. Three views quantify it, in `heterogeneity.py`:

- `instance_variance.md` — `instance_share` is the fraction of log-scale
  variance lying between instances rather than between replications of one
  instance. Its median over the 33 (template, engine) pairs here is 0.85, and
  the between-instance spread exceeds the within-instance noise on 31 of them:
  more replications cannot narrow the uncertainty, because the uncertainty is
  not measurement noise.
  `spread_factor` (slowest / fastest instance) versus `run_noise_factor` (the
  spread within one instance) says the same thing in readable units.
- `instance_ratio_spread.md` — the engine comparison recomputed per instance.
  `straddles_break_even` marks the templates where the engines trade wins
  instance by instance — 12 of the 22 engine-template comparisons here — so the
  single ratio averages over a disagreement rather than reporting a direction.
- `winner_by_instance.md` — which engine is fastest on each individual
  instance, and whether the template's winner was unanimous. It is unanimous on
  2 of the 11 templates with a complete comparison.

`per_instance_time.csv` is the stage-1 frame itself, one row per
(engine, template, instance), for when a summary looks wrong and you want the
input.

## Figures

The per-metric comparisons are vertical grouped bar charts, written in two
layouts — `plot_all(df, layouts=...)` selects which are produced, both by
default:

- **`facets`** — one small-multiple panel per template, each on its own
  *linear* axis. This is the faithful bar chart: length encodes magnitude from
  zero, and per-panel scaling is what makes that possible when the workload
  spans 200ms to 180s. Magnitudes cannot be compared across panels by eye.
- **`single`** — every template on one shared *log* axis. Compact and directly
  comparable, but on a log axis the baseline is arbitrary, so bar *length* is
  not proportional to the value. Read the top edge; the figure says so on its
  face.

In both, the bar is the two-stage aggregate and the whisker spans the slowest
and fastest *instance* — not a quantile over runs. On several templates that
whisker is two orders of magnitude long, which is the most important thing on
the chart.

Two figures exist only for the heterogeneity question:
`instance-spread-time_ms-*` draws every instance separately, and
`instance-variance-share-*` bars the between-instance share of variance per
template (a proportion on a fixed 0-1 scale, which is what a bar chart is for).

## Timing metrics

`time_ms` is wall time for the whole run. It decomposes into three phases, in
`startup_decomposition`:

| phase | column |
| --- | --- |
| start to first result | `to_first_result` |
| first to last result | `streaming_span` |
| last result to run end | `after_last_result` |

The middle phase is nearly empty in this dataset — the median gap between the
first and the last result is 1ms, so results arrive in a burst — and the time
that is not startup is spent *after* the last result (median 220ms, up to 177s).
An engine can therefore deliver every answer early and still finish late, which
`to_last_result` against the total is the only place that shows.

The phase durations are differences between aggregated absolute times rather
than aggregates of per-run differences: both the streaming span and the tail are
exactly zero on many runs, and a geometric mean cannot take a zero — dropping
those runs would systematically delete the fastest ones.
