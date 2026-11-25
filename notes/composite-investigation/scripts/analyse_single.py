"""Summarise compare-single.sh (same layout as analyse_drain.py). Per query and configuration, medians over rounds of the first / median / last row
(exact per-row times, s since the query was sent), and the median row time per provenance group: where the answer's
product comes from (a producer with a SPARQL endpoint, or a document-only producer) and where its review or offer
comes from (one of the 10+10 known vendors / rating sites, or one discovered by traversal). Also SPARQL and bound
(VALUES) requests from the proxy log."""
import glob, json, re, statistics as S
from collections import defaultdict

EXP = "/home/ruben-eschauzier/projects/query-derived-resources/benchmark-experiments/fedshop-discovery-full-experiment"
CFG = {
    "pattern": "pattern-only",
    "derived": "derived full",
    "nosingle": "derived full, no one-pattern composites",
}
pubs = json.load(open(f"{EXP}/generated/benchmark/publishers.json"))
endpoint = {k for k, v in pubs.items() if v["kind"] == "producer" and v.get("service")}
known = {k for k, v in pubs.items() if v.get("known")}

log = defaultdict(lambda: {"sparql": 0, "bound": 0})
for line in open("output/proxy-requests.jsonl"):
    r = json.loads(line)
    m = re.match(r"SB-(\w+)-r(\d):(q\d+)#0", r.get("label") or "")
    if m and r["kind"] == "sparql":
        e = log[m.groups()]
        e["sparql"] += 1
        e["bound"] += "VALUES" in (r.get("query") or "")


def publisher(binding, var):
    m = re.search(r"3000/([^/]+)/", binding.get(var, {}).get("value", ""))
    return m.group(1) if m else None


def group(binding):
    product = "endpoint" if publisher(binding, "product") in endpoint else "doc-only"
    site = publisher(binding, "review") or publisher(binding, "offer")
    return f"{product}/{'known' if site in known else 'discovered'}"


GROUPS = ["endpoint/discovered", "endpoint/known", "doc-only/discovered", "doc-only/known"]
runs = defaultdict(list)
for f in sorted(glob.glob("output/SB-*-r*-q*_0.rows.json")):
    cfg, rnd, q = re.match(r".*/SB-(\w+)-r(\d)-(q\d+)_0\.rows\.json", f).groups()
    rows = json.load(open(f))
    out = {"n": len(rows), **log[(cfg, rnd, q)]}
    ts = sorted(r["t"] for r in rows)
    out["all"] = (ts[0], ts[len(ts) // 2], ts[-1]) if ts else None
    for g in GROUPS:
        gt = sorted(r["t"] for r in rows if group(r["binding"]) == g)
        out[g] = (gt[len(gt) // 2], len(gt)) if gt else None
    runs[(q, cfg)].append(out)

med = lambda xs: S.median(xs) if xs else None
f1 = lambda v: "    -" if v is None else f"{v:5.1f}"
for q in sorted({q for q, _ in runs}):
    print(f"\n{q}  (median over rounds; group cells = median row time, n per round)")
    print(f"  {'configuration':33} {'rows':>10} | {'first':>5} {'median':>6} {'last':>5} | "
          + " | ".join(f"{g:>19}" for g in GROUPS) + f" | {'sparql':>6} {'bound':>5}")
    for cfg in CFG:
        rs = runs.get((q, cfg))
        if not rs:
            continue
        trip = [r["all"] for r in rs if r["all"]]
        cells = [f1(med([t[i] for t in trip])) for i in range(3)]
        groups = []
        for g in GROUPS:
            vals = [r[g] for r in rs if r[g]]
            groups.append(f"{f1(med([v[0] for v in vals]))} (n={vals[0][1] if vals else 0:2})" if vals else f"{'-':>19}")
        print(f"  {CFG[cfg]:33} {'/'.join(str(r['n']) for r in rs):>10} | {cells[0]:>5} {cells[1]:>6} {cells[2]:>5} | "
              + " | ".join(f"{c:>19}" for c in groups)
              + f" | {med([r['sparql'] for r in rs]):6.0f} {med([r['bound'] for r in rs]):5.0f}")
print("\nper round, first / median / last:")
for (q, cfg), rs in sorted(runs.items()):
    print(f"  {q} {CFG[cfg]:33} " + "   ".join(" ".join(f1(x) for x in r["all"]) for r in rs if r["all"]))
