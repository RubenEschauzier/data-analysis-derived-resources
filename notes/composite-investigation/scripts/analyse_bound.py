"""Summarise compare-bound.sh: per query and configuration, medians over rounds of result arrival (s since the
engine started), probe work, SPARQL bytes and bound requests (from the proxy log, by run label)."""
import glob, json, re, statistics as S
from collections import defaultdict
dec = json.JSONDecoder()
CFG = {"P": "pattern-only", "V": "virtual", "X": "virtual+extended", "B": "virtual+extended+bound"}
log = defaultdict(lambda: {"bytes": 0, "sparql": 0, "bound": 0, "bound_bytes": 0, "requests": 0})
for line in open("output/proxy-requests.jsonl"):
    r = json.loads(line)
    m = re.match(r"([PVXB])-r(\d):(q\d+)#0", r.get("label") or "")
    if not m:
        continue
    e = log[m.groups()]
    e["requests"] += 1
    if r["kind"] == "sparql":
        e["sparql"] += 1
        e["bytes"] += r["bytes"]
        if "VALUES" in (r.get("query") or ""):
            e["bound"] += 1
            e["bound_bytes"] += r["bytes"]
runs = defaultdict(list)
for f in sorted(glob.glob("output/[PVXB]-r[0-9]-q*_0.json")):
    cfg, rnd, q = re.match(r".*/([PVXB])-r(\d)-(q\d+)_0\.json", f).groups()
    s = open(f).read()
    try:
        rows, _ = dec.raw_decode(s, s.index("[", s.index('"bindings"')))
        meta, _ = dec.raw_decode(s, s.index("{", s.index('"metadata"')))
    except ValueError:
        runs[(q, cfg)].append({"failed": True}); continue
    stats = meta["adaptiveStats"]
    probes = sum(sum(sum(v["in"]) for v in sel.values()) for j in stats for sel in j["timeseries"]["selectivity"].values())
    ts = stats[0]["timeseries"]; t = [x / 1000 for x in ts["t"]]; tot = sum(ts["results"]); cum = 0; marks = {}
    for i, n in enumerate(ts["results"]):
        cum += n
        for frac in (1e-9, .5, 1.0):
            if frac not in marks and tot and cum >= frac * tot:
                marks[frac] = t[i]
    e = log[(cfg, rnd, q)]
    runs[(q, cfg)].append({"rows": len(rows), "first": marks.get(1e-9), "half": marks.get(.5), "last": marks.get(1.0),
                           "probes": probes, "mb": e["bytes"] / 1e6, "bound": e["bound"], "bound_kb": e["bound_bytes"] / 1e3,
                           "requests": e["requests"]})
med = lambda xs: S.median(xs) if xs else None
fmt = lambda v, d=1: "-" if v is None else f"{v:.{d}f}"
print(f"{'query':6} {'cfg':24} {'rows':>9} {'first':>6} {'half':>6} {'last':>6} {'probes':>8} {'sparqlMB':>8} {'bound':>6} {'boundKB':>8} {'reqs':>6}")
for q in sorted({k[0] for k in runs}):
    for cfg in "PVXB":
        rs = [r for r in runs.get((q, cfg), []) if not r.get("failed")]
        if not rs:
            continue
        g = lambda k: med([r[k] for r in rs if r[k] is not None])
        print(f"{q:6} {cfg} {CFG[cfg]:22} {'/'.join(str(r['rows']) for r in rs):>9} {fmt(g('first')):>6} {fmt(g('half')):>6} {fmt(g('last')):>6} "
              f"{fmt(g('probes') / 1000, 0) + 'k':>8} {fmt(g('mb')):>8} {fmt(g('bound'), 0):>6} {fmt(g('bound_kb'), 0):>8} {fmt(g('requests'), 0):>6}")
