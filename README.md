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

## Figures

Execution time spans roughly three orders of magnitude across templates, so the
comparison is a dot-and-range plot on a log axis (dot = median, bar = IQR)
rather than bars — a bar encodes magnitude from a zero baseline, which a log
axis does not have.
