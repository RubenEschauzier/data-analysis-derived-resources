import json, sys
from collections import defaultdict
D = sys.argv[1]
for c in ("c0", "c1", "c2", "c3"):
    raw = json.load(open(f"{D}/{c}/query-results-raw.json"))
    log = [json.loads(l) for l in open(f"{D}/{c}/proxy-requests.jsonl")]
    for q in ("q12#0", "q16#0"):
        reqs = sorted((r for r in log if r["label"] == q), key=lambda r: r["t"])
        # split executions on gaps of more than 3 s between request starts
        execs, cur = [], [reqs[0]]
        for a, b in zip(reqs, reqs[1:]):
            if b["t"] - a["t"] > 8000:
                execs.append(cur); cur = []
            cur.append(b)
        execs.append(cur)
        results = [r["timestamps"] for r in raw if r["name"] == q.split("#")[0]]
        # the runner records warmup separately? align the last len(results) executions
        execs = execs[-len(results):]
        for ex, ts in zip(execs, results):
            t0 = ex[0]["t"]
            rel = lambda v: (v - t0) / 1000
            docs = [r for r in ex if r["kind"] != "sparql"]
            sp = [r for r in ex if r["kind"] == "sparql"]
            disc = [r for r in sp if r["source"] == "discovered"]
            line = (f"{c} {q} first_result={ts[0]/1000:5.1f}s last_result={ts[-1]/1000:5.1f}s | "
                    f"docs {len(docs)} done by {rel(max(r['t']+r['ms'] for r in docs)):5.1f}s (50% started by {rel(sorted(r['t'] for r in docs)[len(docs)//2]):5.1f}s) | "
                    f"sparql {len(sp)}: discovered first {rel(min(r['t'] for r in disc)):5.1f}s, all ended {rel(max(r['t']+r['ms'] for r in disc)):5.1f}s, "
                    f"median {sorted(r['ms'] for r in disc)[len(disc)//2]}ms max {max(r['ms'] for r in disc)}ms")
            print(line)
            if q == "q12#0":
                p = [r for r in ex if r["publisher"] == "producer64"]
                pd = [r for r in p if r["kind"] != "sparql"]; ps = [r for r in p if r["kind"] == "sparql"]
                print(f"      producer64: first doc {rel(min(r['t'] for r in pd)):5.1f}s, "
                      f"product doc ended {rel(max((r['t']+r['ms'] for r in pd if '2002-08' in r['url']), default=t0)):5.1f}s, "
                      f"sparql {len(ps)} sent {rel(min(r['t'] for r in ps)) if ps else None}s ended {rel(max(r['t']+r['ms'] for r in ps)) if ps else None}s")
