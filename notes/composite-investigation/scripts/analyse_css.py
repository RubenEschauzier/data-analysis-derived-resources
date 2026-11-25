"""Summarise css-workers.sh: per Solid-server setting (W1 one process, W4 four workers), configuration and query,
medians over rounds of: arrival of the first / median / last answer, split by where the answer's product comes from
(a producer with a SPARQL endpoint, or a document-only producer reachable by traversal alone); document wait before
headers (proxy log); Solid server CPU."""
import json, glob, re, statistics as S
from collections import defaultdict
reqs = [json.loads(l) for l in open("output/proxy-requests.jsonl")]
endpoint = {r["publisher"] for r in reqs if r["kind"] == "sparql" and (r["publisher"] or "").startswith("producer")}
docwait = defaultdict(list)
for r in reqs:
    m = re.match(r"(W\d)-([PVB])-r\d:(q\d+)#0", r.get("label") or "")
    if m and r["kind"] != "sparql" and r.get("headers_ms") is not None:
        docwait[m.groups()].append(r["headers_ms"])
runs = defaultdict(list)
for f in glob.glob("output/W?-?-r?-q*_0.rows.json"):
    w, cfg, q = re.match(r".*/(W\d)-([PVB])-r\d-(q\d+)_0\.rows\.json", f).groups()
    rows = json.load(open(f))
    def group(b):
        p = b.get("product", {}).get("value", "")
        m = re.search(r"3000/([^/]+)/", p)
        return "endpoint" if m and m.group(1) in endpoint else "doc-only"
    out = {"n": len(rows)}
    for g in ("all", "endpoint", "doc-only"):
        ts = sorted(r["t"] for r in rows if g == "all" or group(r["binding"]) == g)
        out[g] = (ts[0], ts[len(ts) // 2], ts[-1]) if ts else None
    runs[(w, cfg, q)].append(out)
med = lambda xs: S.median(xs) if xs else None
f1 = lambda v: "-" if v is None else f"{v:5.1f}"
print(f"{'css':3} {'cfg':3} {'q':4} {'rows':>9} | {'all first/med/last':>19} | {'endpoint answers':>19} | {'doc-only answers':>19} | docwait p50")
for key in sorted(runs):
    rs = runs[key]
    cells = []
    for g in ("all", "endpoint", "doc-only"):
        trip = [r[g] for r in rs if r[g]]
        cells.append(" ".join(f1(med([t[i] for t in trip])) for i in range(3)) if trip else "-")
    dw = docwait.get(key, [])
    print(f"{key[0]:3} {key[1]:3} {key[2]:4} {'/'.join(str(r['n']) for r in rs):>9} | {cells[0]:>19} | {cells[1]:>19} | {cells[2]:>19} | "
          f"{(sorted(dw)[len(dw)//2] if dw else '-')}")
# CPU per phase
phase, cpu = None, defaultdict(list)
for line in open("css-cpu.log"):
    if line.startswith("phase"):
        phase = line.split()[1]; continue
    m = re.search(r"fedshop-css=([\d.]+)%", line); e = re.search(r"fedshop-engine=([\d.]+)%", line)
    if phase and m and e:
        cpu[phase].append((float(m.group(1)), float(e.group(1))))
for p, v in cpu.items():
    busy = [x for x in v if x[1] > 10]
    print(p, "while the engine runs: css CPU p50", med([x[0] for x in busy]), "engine CPU p50", med([x[1] for x in busy]))
