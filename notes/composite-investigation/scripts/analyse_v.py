"""Summarise compare-v.sh: per template and configuration, medians over replications of when the join
produced its results (s since the engine started the query) and how much probe work it did."""
import glob
import json
import re
import statistics as S
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = {"A": "pattern-only", "B": "derived", "V": "derived, virtual composites"}
dec = json.JSONDecoder()

runs = defaultdict(list)
for f in sorted(glob.glob(str(HERE / "output" / "[ABV]-r*-q*_0.json"))):
    cfg, q = re.match(r".*/([ABV])-r\d-(q\d+)_0\.json", f).groups()
    s = open(f).read()
    try:
        rows, _ = dec.raw_decode(s, s.index("[", s.index('"bindings"')))
        meta, _ = dec.raw_decode(s, s.index("{", s.index('"metadata"')))
    except ValueError:
        runs[(q, cfg)].append({"failed": True})
        continue
    stats = meta["adaptiveStats"]
    # Every adaptive join of the query: results over time, from the one producing the final answers last
    marks, probes, total = {}, 0, 0
    for join in stats:
        ts = join["timeseries"]
        probes += sum(sum(sum(v["in"]) for v in sel.values()) for sel in ts["selectivity"].values())
    ts = stats[0]["timeseries"]
    t = [x / 1000 for x in ts["t"]]
    total = sum(ts["results"])
    cum = 0
    for i, n in enumerate(ts["results"]):
        cum += n
        for frac in (1e-9, 0.25, 0.5, 1.0):
            if frac not in marks and total and cum >= frac * total:
                marks[frac] = t[i]
    runs[(q, cfg)].append({"rows": len(rows), "first": marks.get(1e-9), "q25": marks.get(0.25),
                           "q50": marks.get(0.5), "last": marks.get(1.0), "probes": probes, "joins": len(stats)})

med = lambda xs: S.median(x for x in xs if x is not None) if any(x is not None for x in xs) else None
fmt = lambda x: "    -" if x is None else f"{x:5.1f}"
print(f"{'q':4} {'configuration':28} {'rows':>9} | {'1st':>5} {'25%':>5} {'50%':>5} {'last':>5} | {'probes':>8}  50% range")
for q in sorted({k[0] for k in runs}):
    for cfg in "ABV":
        rs = [r for r in runs.get((q, cfg), []) if not r.get("failed")]
        failed = len(runs.get((q, cfg), [])) - len(rs)
        if not rs:
            continue
        q50 = [r["q50"] for r in rs if r["q50"] is not None]
        print(f"{q:4} {NAMES[cfg]:28} {'/'.join(str(r['rows']) for r in rs):>9} | "
              + " ".join(fmt(med([r[k] for r in rs])) for k in ("first", "q25", "q50", "last"))
              + f" | {med([r['probes'] for r in rs]):8.0f}  {min(q50):.1f}-{max(q50):.1f}"
              + (f"  ({failed} failed)" if failed else ""))
    print()
