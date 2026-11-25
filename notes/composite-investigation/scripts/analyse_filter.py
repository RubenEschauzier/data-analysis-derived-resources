"""Summarise compare-filter.sh: per query, P (pattern-only) vs D (derived, FILTER pushdown). Medians over rounds of
the first / median / last row (exact per-row times, seconds since the query was sent), split by where the answer's
product comes from (a producer with a SPARQL endpoint, or a document-only producer); rows per round; SPARQL requests,
bytes, and requests carrying a FILTER (proxy log)."""
import glob, json, re, statistics as S, urllib.parse
from collections import defaultdict

reqs = [json.loads(line) for line in open("output/proxy-requests.jsonl")]
endpoint = {r["publisher"] for r in reqs if r["kind"] == "sparql" and (r["publisher"] or "").startswith("producer")}
log = defaultdict(lambda: {"sparql": 0, "bytes": 0, "filtered": 0, "filtered_bytes": 0})
for r in reqs:
    m = re.match(r"FP-([PD])-r(\d):(q\d+)#0", r.get("label") or "")
    if not m or r["kind"] != "sparql":
        continue
    e = log[m.groups()]
    q = r.get("query") or urllib.parse.unquote_plus(r["url"].split("query=", 1)[-1])
    e["sparql"] += 1
    e["bytes"] += r["bytes"]
    if "FILTER" in q.upper():
        e["filtered"] += 1
        e["filtered_bytes"] += r["bytes"]

runs = defaultdict(list)
for f in sorted(glob.glob("output/FP-[PD]-r*-q*_0.rows.json")):
    cfg, rnd, q = re.match(r".*/FP-([PD])-r(\d)-(q\d+)_0\.rows\.json", f).groups()
    rows = json.load(open(f))
    def group(b):
        m = re.search(r"3000/([^/]+)/", b.get("product", {}).get("value", ""))
        return "E" if m and m.group(1) in endpoint else "D"
    out = {"n": len(rows), **log[(cfg, rnd, q)]}
    for g in ("all", "E", "D"):
        ts = sorted(r["t"] for r in rows if g == "all" or group(r["binding"]) == g)
        out[g] = (ts[0], ts[len(ts) // 2], ts[-1]) if ts else None
    runs[(q, cfg)].append(out)

med = lambda xs: S.median(xs) if xs else None
f1 = lambda v: "   -" if v is None else f"{v:5.1f}"
print(f"{'q':4} cfg {'rows/round':>14} | {'all first/med/last':>17} | {'endpoint answers':>17} | {'doc-only answers':>17} | "
      f"{'sparql':>6} {'MB':>5} {'FILTER':>6}")
for q, cfg in sorted(runs, key=lambda k: (k[0], k[1] != "P")):
    rs = runs[(q, cfg)]
    cells = []
    for g in ("all", "E", "D"):
        trip = [r[g] for r in rs if r[g]]
        cells.append(" ".join(f1(med([t[i] for t in trip])) for i in range(3)) if trip else "-")
    print(f"{q:4} {cfg:3} {'/'.join(str(r['n']) for r in rs):>14} | {cells[0]:>17} | {cells[1]:>17} | {cells[2]:>17} | "
          f"{med([r['sparql'] for r in rs]):6.0f} {med([r['bytes'] for r in rs]) / 1e6:5.1f} {med([r['filtered'] for r in rs]):6.0f}")
print()
print("per round, all rows (first / median / last):")
for q, cfg in sorted(runs, key=lambda k: (k[0], k[1] != "P")):
    print(f"  {q} {cfg}: " + "  ".join(" ".join(f1(x) for x in r["all"]) if r["all"] else "-" for r in runs[(q, cfg)]))
