"""Per-publisher timeline of composite requests, from the proxy's request log.

For every execution and every publisher D that the engine sent a composite to:

    first_doc     first document, container or storage root of D fetched     (proxy log)
    registered    the engine registered D's composite with the eddy           (engine timeseries tick)
    sent          the first composite request to D reached the proxy          (proxy log)
    headers       Virtuoso began to answer it                                 (proxy log, headers_ms)
    ended         its answer ended                                            (proxy log, t + ms)
    rows_after_ended  first composite rows of that operator to reach the eddy at or after D's answer
                  ended (engine, per operator: rows are not counted per publisher)

All in ms since the engine started the query. The gaps tell where a late composite lost its time:

    first_doc -> sent       discovery, proposal and partitioning in the engine
    registered -> sent      a registered composite waiting in the client before its request leaves
    sent -> headers         the server: waiting for a thread, then planning and executing
    headers -> ended        transfer, which the client's reading speed also limits
    ended -> rows           the eddy not reading composite rows it already has (an upper bound when
                            other publishers' rows land in the same tick; ticks are ~0.4 s apart)

A composite request is matched to its operator by its set of triple patterns (`match` = exact), or by
the number of patterns when the request serialises them differently (`match` = count).

Pattern-level requests to the same publisher (CONSTRUCTs) get the same columns, so a composite can be
compared with the requests it competes with. `in_flight` is how many requests were open on the same
Virtuoso container when the composite arrived (it shares 64 HTTP threads with every service there).

The engine's clock and the proxy's are the same host clock: `startedAt` and the log's `t` are both epoch ms.

usage: PYTHONPATH=src python -m analysis.request_timeline --run <combination_dir> --out <dir>
       (the combination directory holds query-results-raw.json and proxy-requests.jsonl)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

DOCUMENT_KINDS = {"document", "container", "storage-root"}
_IRI = re.compile(r"<[^>]*>")
_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')
_PROLOGUE = re.compile(r"^(?:\s|#[^\n]*\n|BASE\s*<[^>]*>|PREFIX\s+[^\s:]*:\s*<[^>]*>)*", re.I)


def pattern_set(query: str | None) -> frozenset[str] | None:
    """The triple patterns in the WHERE clause of a plain BGP query, whitespace-normalised.

    A heuristic, not a parser: it holds for the BGP-only SELECT and CONSTRUCT queries the engine sends
    (no FILTER, no nested groups, no `;`/`,` abbreviations), and `main` prints the (form, patterns)
    breakdown so it can be checked.
    """
    if not isinstance(query, str) or not query:
        return None
    body = _PROLOGUE.sub("", query)
    where = re.search(r"\bWHERE\s*\{(.*)\}", body, re.I | re.S)
    if not where:
        return None
    # Split on statement ends outside IRIs and literals: mask them, split, then cut the original
    masked = _LITERAL.sub(lambda m: "x" * len(m.group()), _IRI.sub(lambda m: "x" * len(m.group()), where.group(1)))
    patterns, start = [], 0
    for end in [m.start() for m in re.finditer(r"\.(?!\d)", masked)] + [len(masked)]:
        text = " ".join(where.group(1)[start:end].split())
        if text:
            patterns.append(text)
        start = end + 1
    return frozenset(patterns)


def count_patterns(query: str | None) -> int | None:
    patterns = pattern_set(query)
    return None if patterns is None else len(patterns)


def load_log(path: Path) -> pd.DataFrame:
    log = pd.read_json(path, lines=True)
    log["end"] = log["t"] + log["ms"]
    if "query" in log:
        log["pattern_set"] = log["query"].map(pattern_set)
        log["patterns"] = log["pattern_set"].map(lambda s: None if s is None else len(s))
    return log


def _publisher(domain: str) -> str:
    """http://fedshop-proxy:3000/producer26/ -> producer26"""
    return domain.rstrip("/").rsplit("/", 1)[-1]


def executions(raw: list[dict]) -> list[dict]:
    """One entry per measured execution with engine stats: its label, window and composites."""
    out = []
    for record in raw:
        for stats in record.get("adaptiveStats") or []:
            ts = stats.get("timeseries") or {}
            if "startedAt" not in ts:
                continue
            ticks = ts["t"]
            composites = []
            for op, registrations in (ts.get("composites") or {}).items():
                arrived = ts["arrived"].get(op, [])
                # Ticks at which this operator received rows, from any publisher
                row_ticks = [ticks[i] for i, n in enumerate(arrived) if n > 0 and i < len(ticks)]
                patterns = pattern_set(ts["operators"][int(op)].removeprefix("COMPOSITE "))
                for reg in registrations:
                    at = reg["at"]
                    composites.append({
                        "operator": int(op),
                        "patterns": patterns,
                        "publisher": _publisher(reg["domain"]),
                        "registered": ticks[at] if at < len(ticks) else None,
                        "row_ticks": row_ticks,
                    })
            out.append({
                "template": record["name"], "instance": record["id"],
                "label": f"{record['name']}#{record['id']}",
                "started_at": ts["startedAt"], "time": record["time"],
                "error": bool(record.get("error")), "composites": composites,
            })
    return out


def timeline(log: pd.DataFrame, runs: list[dict], slack_ms: int = 2000) -> pd.DataFrame:
    """One row per (execution, publisher with a composite), times in ms since the engine started."""
    rows = []
    for replication, run in enumerate(runs):
        lo, hi = run["started_at"] - slack_ms, run["started_at"] + run["time"] + slack_ms
        window = log[(log["label"] == run["label"]) & (log["t"] >= lo) & (log["t"] <= hi)]
        rel = lambda v: None if pd.isna(v) else float(v - run["started_at"])  # noqa: E731
        by_publisher = dict(tuple(window.groupby("publisher")))
        for c in run["composites"]:
            mine = by_publisher.get(c["publisher"], window.iloc[0:0])
            docs = mine[mine["kind"].isin(DOCUMENT_KINDS)]
            sparql = mine[mine["kind"] == "sparql"]
            # A composite is a SELECT; the pattern-level requests are CONSTRUCTs of one pattern. Of the
            # SELECTs, this operator's are those with its patterns; failing that, as many patterns
            selects = sparql[sparql["query_form"] == "SELECT"].sort_values("t")
            comp, match = selects[selects["pattern_set"] == c["patterns"]], "exact"
            if comp.empty and c["patterns"] is not None:
                comp, match = selects[selects["patterns"] == len(c["patterns"])], "count"
            if comp.empty:
                match = None
            patt = sparql[sparql["query_form"] == "CONSTRUCT"].sort_values("t")
            first = comp.iloc[0] if len(comp) else None
            ended = rel(first["end"]) if first is not None else None
            rows_after = [t for t in c["row_ticks"] if ended is not None and t >= ended]
            rows.append({
                "template": run["template"], "instance": run["instance"], "run": replication,
                "operator": c["operator"], "publisher": c["publisher"], "match": match,
                "composite_requests": len(comp), "pattern_requests": len(patt),
                "first_doc": rel(docs["t"].min()) if len(docs) else None,
                "registered": c["registered"],
                "sent": rel(first["t"]) if first is not None else None,
                "headers": rel(first["t"] + first["headers_ms"]) if first is not None and pd.notna(first["headers_ms"]) else None,
                "ended": ended,
                "status": int(first["status"]) if first is not None else None,
                "bytes": int(first["bytes"]) if first is not None else None,
                "in_flight": int(first["in_flight"]) if first is not None else None,
                "rows_after_ended": rows_after[0] if rows_after else None,
                "pattern_first_sent": rel(patt["t"].min()) if len(patt) else None,
                "pattern_median_wait": float((patt["headers_ms"]).median()) if len(patt) else None,
                "pattern_last_ended": rel(patt["end"].max()) if len(patt) else None,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["doc_to_sent"] = df["sent"] - df["first_doc"]
    df["registered_to_sent"] = df["sent"] - df["registered"]
    df["server_wait"] = df["headers"] - df["sent"]
    df["transfer"] = df["ended"] - df["headers"]
    df["ended_to_rows"] = df["rows_after_ended"] - df["ended"]
    return df


def summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per template: medians over (run, publisher) of every gap, and of the moments themselves."""
    cols = ["first_doc", "registered", "sent", "headers", "ended",
            "doc_to_sent", "registered_to_sent", "server_wait", "transfer", "ended_to_rows",
            "in_flight", "pattern_median_wait"]
    out = df.groupby("template")[cols].median().round(0)
    out.insert(0, "publishers_x_runs", df.groupby("template").size())
    out.insert(1, "never_sent", df.groupby("template")["sent"].apply(lambda s: int(s.isna().sum())))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, required=True, help="a combination_* directory")
    parser.add_argument("--out", type=Path, required=True, help="directory for the CSVs")
    args = parser.parse_args()

    log = load_log(args.run / "proxy-requests.jsonl")
    if "headers_ms" not in log or "query_form" not in log:
        raise SystemExit("this request log predates headers_ms/query_form: rebuild the generator image "
                         "with the current proxy.js and run again")
    runs = executions(json.loads((args.run / "query-results-raw.json").read_text()))

    sparql = log[log["kind"] == "sparql"]
    print("SPARQL requests by form and pattern count (check the composite/pattern split here):")
    print(sparql.groupby(["query_form", "patterns"], dropna=False).size().to_string(), "\n")

    df = timeline(log, runs)
    args.out.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out / "composite_timeline.csv", index=False)
    if df.empty:
        print("no composites in these runs")
        return
    table = summary(df)
    table.to_csv(args.out / "composite_timeline_summary.csv")
    print("Median ms since query start per template (gaps are medians of per-publisher gaps):")
    print(table.to_string())
    print(f"\nwrote {args.out / 'composite_timeline.csv'} and composite_timeline_summary.csv")


if __name__ == "__main__":
    main()
