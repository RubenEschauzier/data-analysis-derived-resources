"""SteMs timelines of q16 (STEMS_TIMESERIES_LOG=1, engine-TS-<config>-r<n>.log): per base operator (one pattern),
when its tuples reached the join: the time (s since the join started) by which 10% / 50% / 90% / 100% of its final
count had arrived, and how many arrived, were filtered (authoritative source) and, for composites, pruned. Then the
same for composite operators together, and for results."""
import json, glob, re, sys
from collections import defaultdict


def load(f):
    comps = []
    for line in open(f, errors="replace"):
        if line.startswith("[stems-timeseries] "):
            try:
                comps.append(json.loads(line[len("[stems-timeseries] "):]))
            except json.JSONDecodeError:
                print(f"   ({f}: a timeline line is interleaved with other output, skipped)")
    return comps


def reach(t, counts, frac):
    total = sum(counts)
    if total == 0:
        return None
    acc = 0
    for ti, c in zip(t, counts):
        acc += c
        if acc >= frac * total:
            return ti / 1000
    return t[-1] / 1000


def short(sparql):
    s = re.sub(r"<http://www4\.wiwiss\.fu-berlin\.de/bizer/bsbm/v01/vocabulary/([^>]+)>", r"bsbm:\1", sparql)
    s = re.sub(r"<http://fedshop\.example\.org/vocab#([^>]+)>", r"fs:\1", s)
    s = re.sub(r"<http://purl\.org/dc/elements/1\.1/([^>]+)>", r"dc:\1", s)
    s = re.sub(r"<http://www\.w3\.org/1999/02/22-rdf-syntax-ns#type>", "a", s)
    s = re.sub(r"<http://fedshop-proxy:3000/taxonomy/([^>]+)>", r"tax:\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    m = re.search(r"\{(.*)\}", s)
    return (m.group(1) if m else s).strip()[:60]


for f in sorted(glob.glob("engine-TS-*.log")):
    label = re.match(r"engine-TS-(.*)\.log", f).group(1)
    for ci, comp in enumerate(load(f)):
        ts = comp["timeseries"]
        t = ts["t"]
        n = len(t)
        print(f"\n== {label} component {ci}: {len(ts['operators'])} operators, {len(t)} intervals, last at {t[-1] / 1000:.1f} s")
        print(f"   {'operator':62} {'10%':>5} {'50%':>5} {'90%':>5} {'100%':>5} {'arrived':>8} {'filtered':>8}")
        comp_arr = [0] * n
        ncomp = 0
        for idx, desc in enumerate(ts["operators"]):
            if desc is None:
                continue
            arr = ts["arrived"].get(str(idx), [])
            arr = arr + [0] * (n - len(arr))
            filt = sum(ts["filtered"].get(str(idx), []))
            if desc.startswith("COMPOSITE"):
                ncomp += 1
                comp_arr = [a + b for a, b in zip(comp_arr, arr)]
                continue
            cells = [reach(t, arr, x) for x in (.1, .5, .9, 1)]
            print(f"   {short(desc):62} " + " ".join(f"{c:5.1f}" if c is not None else "    -" for c in cells)
                  + f" {sum(arr):8d} {filt:8d}")
        if ncomp:
            cells = [reach(t, comp_arr, x) for x in (.1, .5, .9, 1)]
            pruned = sum(sum(v) for v in ts["pruned"].values())
            print(f"   {f'{ncomp} composite operators together':62} " + " ".join(f"{c:5.1f}" if c is not None else "    -" for c in cells)
                  + f" {sum(comp_arr):8d}   pruned {pruned}")
        res = ts["results"]
        cells = [reach(t, res, x) for x in (.1, .5, .9, 1)]
        print(f"   {'results (before DISTINCT)':62} " + " ".join(f"{c:5.1f}" if c is not None else "    -" for c in cells)
              + f" {sum(res):8d}")
