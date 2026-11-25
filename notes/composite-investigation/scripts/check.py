"""usage: python check.py <label> <qid-file-part e.g. q16_0>  -> rows, arrival marks, operators, SPARQL requests by kind"""
import json, sys, collections
label, q = sys.argv[1:3]
dec = json.JSONDecoder()
s = open(f"output/{label}-{q}.json").read()
rows, _ = dec.raw_decode(s, s.index("[", s.index('"bindings"')))
meta, _ = dec.raw_decode(s, s.index("{", s.index('"metadata"')))
ts = meta["adaptiveStats"][0]["timeseries"]
t = [x / 1000 for x in ts["t"]]; tot = sum(ts["results"]); cum = 0; marks = {}
for i, n in enumerate(ts["results"]):
    cum += n
    for f in (1e-9, .5, 1):
        if f not in marks and tot and cum >= f * tot:
            marks[f] = round(t[i], 1)
probes = sum(sum(sum(v["in"]) for v in sel.values()) for j in meta["adaptiveStats"] for sel in j["timeseries"]["selectivity"].values())
print(f"rows={len(rows)} distinct={len({json.dumps(r, sort_keys=True) for r in rows})} first={marks.get(1e-9)} half={marks.get(.5)} last={marks.get(1)} probes={probes}")
for o in ts["operators"]:
    if o.startswith("COMPOSITE"):
        print("  ", o[:150])
qlabel = f"{label}:{q.replace('_', '#')}"
log = [json.loads(l) for l in open("output/proxy-requests.jsonl")]
sp = [r for r in log if r.get("label") == qlabel and r["kind"] == "sparql"]
vals = [r for r in sp if "VALUES" in (r.get("query") or "")]
print("sparql", len(sp), "bound(VALUES)", len(vals), "bytes", sum(r["bytes"] for r in sp),
      collections.Counter((r["publisher"].rstrip("0123456789"), r.get("query_form")) for r in sp))
if vals:
    print("  bound bytes", sum(r["bytes"] for r in vals), "values/request",
          [r["query"].count("<http") for r in vals[:12]])
