"""Do the engines return the same answers?

Only runs that completed without an error are compared: an errored run reports
whatever partial result set it had reached, so its hash says nothing about
correctness. Errors are reported separately as a completion rate.

Agreement is a strict comparison of the set of values each engine produced over
its replications. That comparison is confounded when an engine is not
deterministic across its own replications (an unordered LIMIT, say), so
within-engine stability is reported in its own column rather than folded into
the verdict.
"""

from __future__ import annotations

import pandas as pd

from .loading import engine_order, template_order

MATCH = "match"
MISMATCH = "MISMATCH"
NO_DATA = "no data"

# Ranked worst-first, so a per-template roll-up can take the max.
_SEVERITY = {MATCH: 0, NO_DATA: 1, MISMATCH: 2}


def _short(values: set[str], width: int = 8) -> str:
    """Render a set of values compactly, deterministically ordered."""
    if not values:
        return "-"
    shown = sorted(str(v)[:width] for v in values)
    return shown[0] if len(shown) == 1 else " / ".join(shown)


def _compare(per_engine: dict[str, set], engines: list[str]) -> str:
    if any(not per_engine[e] for e in engines):
        return NO_DATA
    if len({frozenset(per_engine[e]) for e in engines}) > 1:
        return MISMATCH
    return MATCH


def _worst(*verdicts: str) -> str:
    return max(verdicts, key=lambda s: _SEVERITY[s])


def per_query_agreement(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (template, instance) comparing result count and result hash."""
    engines = engine_order(df)
    order = {t: i for i, t in enumerate(template_order(df))}
    ok = df[~df["failed"]]

    rows = []
    for (template, instance), group in df.groupby(["template", "instance"]):
        good = ok[(ok["template"] == template) & (ok["instance"] == instance)]
        hashes = {e: set(good[good["engine"] == e]["hash"]) for e in engines}
        counts = {e: set(good[good["engine"] == e]["results"]) for e in engines}

        row = {"template": template, "instance": instance}
        for engine in engines:
            runs = group[group["engine"] == engine]
            row[f"runs_ok::{engine}"] = f"{len(runs) - int(runs['failed'].sum())}/{len(runs)}"
            row[f"results::{engine}"] = _short(counts[engine])
            row[f"hash::{engine}"] = _short(hashes[engine])

        wobbly = [e for e in engines if len(hashes[e]) > 1 or len(counts[e]) > 1]
        row["results_agreement"] = _compare(counts, engines)
        row["hash_agreement"] = _compare(hashes, engines)
        row["nondeterministic"] = ", ".join(wobbly) if wobbly else "-"
        row["status"] = _worst(row["results_agreement"], row["hash_agreement"])
        rows.append(row)

    table = pd.DataFrame(rows)
    table["_order"] = table["template"].map(order)
    table = table.sort_values(["_order", "instance"]).drop(columns="_order")
    return table.reset_index(drop=True)


def per_template_agreement(per_query: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Roll the per-instance verdicts up to one row per template."""
    engines = engine_order(df)
    order = {t: i for i, t in enumerate(template_order(df))}

    rows = []
    for template, group in per_query.groupby("template"):
        runs = df[df["template"] == template]
        row = {"template": template, "instances": len(group)}
        for engine in engines:
            sub = runs[runs["engine"] == engine]
            row[f"runs_ok::{engine}"] = f"{len(sub) - int(sub['failed'].sum())}/{len(sub)}"
        row["results_mismatch"] = int((group["results_agreement"] == MISMATCH).sum())
        row["hash_mismatch"] = int((group["hash_agreement"] == MISMATCH).sum())
        row["nondeterministic"] = int((group["nondeterministic"] != "-").sum())
        row["no_data"] = int((group["status"] == NO_DATA).sum())
        row["status"] = _worst(*group["status"])
        rows.append(row)

    table = pd.DataFrame(rows)
    table["_order"] = table["template"].map(order)
    return table.sort_values("_order").drop(columns="_order").reset_index(drop=True)


def to_markdown(table: pd.DataFrame) -> str:
    """Markdown rendering with the engine name split off the column role."""
    pretty = table.rename(columns=lambda c: c.replace("::", " "))
    return pretty.to_markdown(index=False)
