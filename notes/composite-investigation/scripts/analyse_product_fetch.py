"""q16: for each answer, when the engine first fetched its product's data: the product document (doc-only producer)
or the first SPARQL request to its producer's endpoint; compared with when the answer arrived. Per configuration."""
import glob, json, re, statistics as S
from collections import defaultdict
G = "/home/ruben-eschauzier/projects/query-derived-resources/benchmark-experiments/fedshop-discovery-full-experiment/generated/benchmark"
pubs = json.load(open(f"{G}/publishers.json"))
endpoint = {k for k, v in pubs.items() if v["kind"] == "producer" and v.get("service")}
LABELS = {"FP-P": "pattern-only", "FP-D": "derived full"}
reqs = defaultdict(list)
for line in open("output/proxy-requests.jsonl"):
    r = json.loads(line)
    m = re.match(r"(FP-[PD])-r(\d):q16#0", r.get("label") or "")
    if m: reqs[m.groups()].append(r)
out = defaultdict(lambda: defaultdict(list))
kinds = defaultdict(lambda: defaultdict(list))
for (cfg, rnd), rs in reqs.items():
    t0 = min(r["t"] for r in rs)
    first_doc, first_sparql, first_any = {}, {}, {}
    for r in sorted(rs, key=lambda r: r["t"]):
        t = (r["t"] - t0) / 1000
        url = r["url"].split("#")[0].split("?")[0]
        first_doc.setdefault(url, t)
        if r["kind"] == "sparql": first_sparql.setdefault(r["publisher"], t)
        first_any.setdefault(r["publisher"], t)
        kinds[cfg][r["kind"]].append(t)
    rows = json.load(open(f"output/{cfg}-r{rnd}-q16_0.rows.json"))
    for row in rows:
        prod = row["binding"]["product"]["value"]
        producer = re.search(r"3000/([^/]+)/", prod).group(1)
        kind = "endpoint" if producer in endpoint else "doc-only"
        fetched = first_sparql.get(producer) if kind == "endpoint" else first_doc.get(prod.split("#")[0])
        out[kind][cfg].append((first_any.get(producer), fetched, row["t"]))
for kind in out:
    print(f"answers with a {kind} product")
    for cfg in ("FP-P", "FP-D"):
        v = out[kind][cfg]
        f = lambda i: S.median(x[i] for x in v if x[i] is not None)
        print(f"   {LABELS[cfg]:13} producer first contacted {f(0):5.1f} s | product data fetched {f(1):5.1f} s | answer {f(2):5.1f} s   (n={len(v)})")
print("\nall requests: median / p90 send time, s")
for cfg in ("FP-P", "FP-D"):
    print("  ", LABELS[cfg], {k: (round(S.median(v), 1), round(sorted(v)[int(.9 * len(v))], 1), len(v) // 4) for k, v in kinds[cfg].items()})
