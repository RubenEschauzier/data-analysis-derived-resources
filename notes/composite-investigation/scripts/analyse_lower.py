"""Summarise compare-lower.sh: per query and configuration (lowering on/off), medians over rounds of the first /
median / last row (s since the query was sent), q16's answers whose offer and review come from known members, total
requests, documents from pods with an endpoint (count, MB), and lowering's own CPU time (ms, from the engine log)."""
import glob, json, re, statistics as S
from collections import defaultdict

exec(open("analyse_offer.py").read().split("CFG = ")[0])  # group(): offer / review provenance of a q16 answer
NAMES = {"pattern-off": "pattern-only", "pattern-on": "pattern-only, lowering",
         "derived-off": "derived full", "derived-on": "derived full, lowering"}

log = defaultdict(lambda: {"requests": 0, "endpoint_docs": 0, "endpoint_mb": 0.0})
by_label = defaultdict(list)
for line in open("output/proxy-requests.jsonl"):
    if '"label":"LP-' in line:
        r = json.loads(line)
        by_label[r["label"]].append(r)
for label, rs in by_label.items():
    m = re.match(r"LP-(\w+-\w+)-r(\d):(q\d+)#0", label)
    if not m:
        continue
    endpoint_pods = {r["publisher"] for r in rs if r["kind"] == "sparql"}
    e = log[m.groups()]
    e["requests"] = len(rs)
    docs = [r for r in rs if r["kind"] == "document" and r["publisher"] in endpoint_pods]
    e["endpoint_docs"] = len(docs)
    e["endpoint_mb"] = sum(r["bytes"] for r in docs) / 1e6

lower_ms = {}
for f in glob.glob("engine-LP-*-on-r*.log"):
    cfg, rnd = re.match(r"engine-LP-(\w+-on)-r(\d)\.log", f).groups()
    stats = [json.loads(l[l.index("{"):]) for l in open(f, errors="replace") if l.startswith("[lower] http")]
    # One queue per query, its counters start afresh: q16 runs first, then q14 (compare-lower.sh)
    segments, last = [[]], 0
    for st in stats:
        if st["datasets"] < last:
            segments.append([])
        segments[-1].append(st)
        last = st["datasets"]
    for q, seg in zip(("q16", "q14"), segments):
        lower_ms[(cfg, rnd, q)] = seg[-1]["ms"] if seg else None

runs = defaultdict(list)
for f in sorted(glob.glob("output/LP-*-r*-q*_0.rows.json")):
    cfg, rnd, q = re.match(r".*/LP-(\w+-\w+)-r(\d)-(q\d+)_0\.rows\.json", f).groups()
    rows = json.load(open(f))
    ts = sorted(r["t"] for r in rows)
    kk = [r["t"] for r in rows if q == "q16" and group(r["binding"]) == "offer known      review known"]
    runs[(q, cfg)].append({"n": len(rows), "all": (ts[0], ts[len(ts) // 2], ts[-1]), "kk": S.median(kk) if kk else None,
                           **log[(cfg, rnd, q)], "ms": lower_ms.get((cfg, rnd, q))})

med = lambda xs: S.median(xs) if xs else None
f1 = lambda v: "    -" if v is None else f"{v:5.1f}"
for q in sorted({q for q, _ in runs}):
    print(f"\n{q} (median over rounds)")
    print(f"  {'configuration':26} {'rows':>9} | {'first':>5} {'median':>6} {'last':>5} | {'known/known':>11} | "
          f"{'requests':>8} {'endpoint-pod pages':>18} | {'lowering CPU ms':>15}")
    for cfg in NAMES:
        rs = runs.get((q, cfg))
        if not rs:
            continue
        cells = [f1(med([r["all"][i] for r in rs])) for i in range(3)]
        kk = med([r["kk"] for r in rs if r["kk"] is not None])
        ms = [r["ms"] for r in rs if r["ms"] is not None]
        print(f"  {NAMES[cfg]:26} {'/'.join(str(r['n']) for r in rs):>9} | {cells[0]:>5} {cells[1]:>6} {cells[2]:>5} | "
              f"{f1(kk):>11} | {med([r['requests'] for r in rs]):8.0f} "
              f"{med([r['endpoint_docs'] for r in rs]):8.0f} ({med([r['endpoint_mb'] for r in rs]):4.1f} MB) | "
              f"{(f'{med(ms):.0f}' if ms else '-'):>15}")
print("\nper round, first / median / last:")
for (q, cfg), rs in sorted(runs.items()):
    print(f"  {q} {NAMES[cfg]:26} " + "   ".join(" ".join(f1(x) for x in r["all"]) for r in rs))
