"""Self CPU time per package in prof/<label>/<pid>-<window>.cpuprofile (window 1 = first 30 s of the query,
2 = the rest). Usage: python3 analyse_prof.py LABEL..."""
import json, re, sys, glob
from collections import Counter
def pkg(url, fn):
    if not url:
        return fn if fn.startswith("(") else "(native/builtin)"
    if url.startswith("node:"):
        return "node:" + url[5:].split("/")[1 if url[5:].startswith("internal") else 0]
    m = re.findall(r"node_modules/((?:@[^/]+/)?[^/]+)", url)
    if m:
        return m[-1]
    return url.split("/")[-1]
def load(f):
    p = json.load(open(f)); nodes = {n["id"]: n for n in p["nodes"]}
    dt = Counter()
    for sid, d in zip(p["samples"], p["timeDeltas"]):
        n = nodes[sid]; dt[pkg(n["callFrame"]["url"], n["callFrame"]["functionName"])] += d / 1e6
    return dt, (p["endTime"] - p["startTime"]) / 1e6
for label in sys.argv[1:]:
    for w in (1, 2):
        f = glob.glob(f"prof/{label}/*-{w}.cpuprofile")[0]
        dt, wall = load(f)
        busy = wall - dt["(idle)"]
        print(f"== {label} window {w}: wall {wall:.1f}s, busy {busy:.1f}s ({100*busy/wall:.0f}%)")
        for k, v in dt.most_common(22):
            if k != "(idle)":
                print(f"   {v:6.2f}s {100*v/busy:5.1f}%  {k}")
