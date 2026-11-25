"""q16: regroup answers by where the review comes from AND where the offer (the price) comes from, known or
discovered vendor, looked up in the generated data: offers whose listing is fs:listingOf the product, with that price."""
import glob, json, re, statistics as S
from collections import defaultdict
G = "/home/ruben-eschauzier/projects/query-derived-resources/benchmark-experiments/fedshop-discovery-full-experiment/generated/benchmark"
pubs = json.load(open(f"{G}/publishers.json"))
known = {k for k, v in pubs.items() if v.get("known")}
endpoint = {k for k, v in pubs.items() if v["kind"] == "producer" and v.get("service")}
LISTING = "<http://fedshop.example.org/vocab#listingOf>"
PRODUCT = "<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/vocabulary/product>"
PRICE = "<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/vocabulary/price>"
listing_of, offer_listing, offer_price = {}, {}, {}
for f in glob.glob(f"{G}/data/*/shops/*.nt"):
    for line in open(f):
        s, p, o = line.split(" ", 2)
        o = o.rstrip(" .\n")
        if p == LISTING: listing_of[s] = o
        elif p == PRODUCT: offer_listing[s] = o
        elif p == PRICE: offer_price[s] = re.match(r'"([^"]*)"', o).group(1)
vendors = defaultdict(set)  # (product, price) -> vendor pods
for offer, listing in offer_listing.items():
    product = listing_of.get(listing)
    if product and offer in offer_price:
        vendors[(product.strip("<>"), offer_price[offer])].add(re.search(r"3000/([^/]+)/", offer).group(1))
pub = lambda v: (re.search(r"3000/([^/]+)/", v) or [None, None])[1]
def group(b):
    vs = vendors.get((b["product"]["value"], b["price"]["value"]), set())
    vendor = "?" if not vs else "known" if vs <= known else "discovered" if not (vs & known) else "both"
    site = "known" if pub(b["review"]["value"]) in known else "discovered"
    return f"offer {vendor:10} review {site}"
CFG = {"FP-P": "pattern-only (filter runs)", "FP-D": "derived full (filter runs)", "DR-pattern": "pattern-only (r1)",
       "DR-derived": "derived full, drained (r1)", "DR-derivedND": "derived full, not drained (r1)"}
res = defaultdict(lambda: defaultdict(list))
for prefix, name in CFG.items():
    files = glob.glob(f"output/{prefix}-r*-q16_0.rows.json") if prefix.startswith("FP") else glob.glob(f"output/{prefix}-r1-q16_0.rows.json")
    for f in files:
        rows = json.load(open(f)); per = defaultdict(list)
        for r in rows: per[group(r["binding"])].append(r["t"])
        for g, ts in per.items(): res[g][name].append((S.median(ts), len(ts)))
for g in sorted(res):
    print(g)
    for name in CFG.values():
        v = res[g].get(name)
        if v: print(f"    {name:32} median {S.median(x[0] for x in v):5.1f} s  (n={v[0][1]}, rounds={len(v)})")
