"""Where the engine's CPU goes, per 5 s window of q16, pattern-only vs derived full (profile_windows.py runs
PW-<config>-r<n>). Self time grouped into kinds of work; inclusive time for a few components (a sample counts for
a component if any frame on its stack belongs to it). Medians over rounds, seconds of CPU per window."""
import json, re, glob, statistics as S
from collections import Counter, defaultdict

WINDOWS = ["0-5", "5-10", "10-15", "15-20", "20-25", "25-30", "30-end"]
EDGES = [5, 10, 15, 20, 25, 30]
KIND = [  # (kind, package regex), first match wins
    ("garbage collection", r"^\(garbage collector\)$"),
    ("RDF document parsing", r"^(n3|jsonld-streaming-parser|jsonld-context-parser|rdf-object|relative-to-absolute-iri|@rdfjs/.*|rdfa-streaming-parser|microdata-rdf-streaming-parser)$"),
    ("aggregated store", r"^(rdf-streaming-store|@comunica/actor-factory-aggregated-store-memory|rdf-stores)$"),
    ("SteMs join", r"^@comunica/actor-rdf-join-inner-multi-stems$"),
    ("SPARQL query parse/serialise", r"^(@traqula/.*|sparqljs|fetch-sparql-endpoint)$"),
    ("SPARQL results parsing", r"^(@bergos/jsonparse|sparqljson-parse|sparqlxml-parse)$"),
    ("link extraction", r"^@comunica/actor-extract-links-.*$"),
    ("derived-resource actors", r"^@comunica/(actor|bus)-derived-resource-.*$"),
    ("stream plumbing", r"^(asynciterator|readable-stream|node:streams|node:events|node:webstreams|immutable)$"),
    ("HTTP / network", r"^(undici|node:net|node:buffer|node:deps|@comunica/actor-http-.*|@comunica/bus-http)$"),
]
INCL = {
    "SteMs join": r"^@comunica/actor-rdf-join-inner-multi-stems$",
    "derived-resource actors": r"^@comunica/(actor|bus)-derived-resource-",
    "SPARQL source (incl. its parsing)": r"^@comunica/actor-query-source-identify-hypermedia-sparql$",
    "link extraction": r"^@comunica/actor-extract-links-",
    "aggregated store": r"^(rdf-streaming-store|@comunica/actor-factory-aggregated-store-memory)$",
}


def pkg(url, fn):
    if not url:
        return fn if fn.startswith("(") else "(native/builtin)"
    if url.startswith("node:"):
        return "node:" + url[5:].split("/")[1 if url[5:].startswith("internal") else 0]
    m = re.findall(r"node_modules/((?:@[^/]+/)?[^/]+)", url)
    return m[-1] if m else url.split("/")[-1]


def kind(p):
    for k, rx in KIND:
        if re.match(rx, p):
            return k
    return "other"


def load(f, sent_ms):
    """Per window index (1..), self time per kind and inclusive time per component."""
    p = json.load(open(f))
    nodes = {n["id"]: n for n in p["nodes"]}
    parent = {c: n["id"] for n in p["nodes"] for c in n.get("children", [])}
    stacks = {}
    def stack(i):
        if i not in stacks:
            n = nodes[i]
            stacks[i] = ({pkg(n["callFrame"]["url"], n["callFrame"]["functionName"])} |
                         (stack(parent[i]) if i in parent else set()))
        return stacks[i]
    out = defaultdict(Counter)
    t = p["startTime"]
    for sid, d in zip(p["samples"], p["timeDeltas"]):
        t += d
        since = (p["startWallMs"] + (t - p["startTime"]) / 1000 - sent_ms) / 1000
        if since < 0:
            continue
        w = 1 + sum(since >= e for e in EDGES)
        self_t = incl_t = out[w]
        n = nodes[sid]; s = d / 1e6
        own = pkg(n["callFrame"]["url"], n["callFrame"]["functionName"])
        if own == "(idle)":
            continue
        self_t[kind(own)] += s; self_t["busy"] += s
        st = stack(sid)
        for name, rx in INCL.items():
            if any(re.match(rx, x) for x in st):
                incl_t["incl " + name] += s
    return out


data = defaultdict(lambda: defaultdict(list))  # (cfg, window) -> key -> [per round]
for d in sorted(glob.glob("prof/PW-*-*")):
    cfg = re.match(r".*/PW-(\w+)-\w+", d).group(1)
    per_w = defaultdict(Counter)
    sent_ms = json.load(open(f"{d}/sent.json"))["ms"]
    for f in glob.glob(f"{d}/*.cpuprofile"):
        for w, c in load(f, sent_ms).items():
            per_w[w].update(c)
    for w, c in per_w.items():
        keys = set(c) | {k for k, _ in KIND} | {"other"} | {"incl " + k for k in INCL}
        for k in keys:
            data[(cfg, w)][k].append(c.get(k, 0.0))

med = lambda v: S.median(v) if v else 0.0
rows = ["busy"] + [k for k, _ in KIND] + ["other"] + ["incl " + k for k in INCL]
names = {"pattern": "pattern-only", "derived": "derived full"}
print(f"{'CPU s per window':38}" + "".join(f"{w:>14}" for w in WINDOWS))
print(f"{'':38}" + "".join(f"{'pat / der':>14}" for _ in WINDOWS))
for k in rows:
    cells = []
    for wi in range(1, len(WINDOWS) + 1):
        a, b = med(data[("pattern", wi)].get(k, [])), med(data[("derived", wi)].get(k, []))
        cells.append(f"{a:5.2f} /{b:5.2f}")
    print(f"{k:38}" + "".join(f"{c:>14}" for c in cells))
print("\ncumulative to 15 s and 20 s (derived minus pattern-only):")
for k in rows:
    for upto in (3, 4):
        a = sum(med(data[("pattern", w)].get(k, [])) for w in range(1, upto + 1))
        b = sum(med(data[("derived", w)].get(k, [])) for w in range(1, upto + 1))
        print(f"  {k:36} to {upto * 5:2d} s: pattern {a:5.2f}  derived {b:5.2f}  diff {b - a:+5.2f}")
