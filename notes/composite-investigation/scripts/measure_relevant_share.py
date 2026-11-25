"""How much of the data a FedShop query makes the engine ingest is relevant to it (2026-11-25).

A triple is relevant to a query when it matches at least one of the query's triple patterns (constants equal,
variables anything); every other triple of a fetched document is parsed and indexed all the same. The share of
relevant triples sets how much irrelevant ("bogus") data the synthetic micro-benchmark data needs to be realistic.

Two measures:
* fetched: per run in the proxy log (every document request of that run), relevant ÷ all triples of the fetched
  documents. Only the queries in the log (q12, q13, q14, q16 of the bound experiment).
* static, every query: over the documents holding at least one relevant triple (the documents traversal has a reason
  to fetch), relevant ÷ all their triples; and over all documents.

Usage: python measure_relevant_share.py <web dir> <queries.txt> <proxy-requests.jsonl>
"""
import collections
import json
import re
import statistics as st
import sys
from pathlib import Path
from urllib.parse import urlparse

from rdflib.plugins.sparql import prepareQuery
from rdflib.term import Variable

web, queries_file, proxy_log = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
PREFIXES = """PREFIX bsbm: <http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/vocabulary/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX fs: <http://fedshop.example.org/vocab#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rev: <http://purl.org/stuff/rev#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

# The triple patterns of every query (in BGPs anywhere: OPTIONAL, UNION, ...), as N-Triples strings or None for a
# variable
queries = {}
for block in queries_file.read_text().split('### ')[1:]:
    name, _, text = block.partition('\n')
    body = '\n'.join(line for line in text.splitlines() if not line.startswith('#'))
    patterns = set()

    def walk(node):
        if isinstance(node, dict) or hasattr(node, 'items'):
            if 'triples' in node:
                for s, p, o in node['triples']:
                    if not hasattr(p, 'n3'):
                        continue  # A property path: left out
                    patterns.add(tuple(None if isinstance(t, Variable) else t.n3() for t in (s, p, o)))
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)

    walk(prepareQuery(PREFIXES + body).algebra)
    queries[name.strip()] = patterns
by_predicate = collections.defaultdict(list)  # predicate (or None) -> [(query, subject, object)]
for name, patterns in queries.items():
    for s, p, o in patterns:
        by_predicate[p].append((name, s, o))

TERM = re.compile(r'<[^>]*>|_:\S+|"(?:[^"\\]|\\.)*"(?:\^\^<[^>]*>|@[\w-]+)?')

# Per document: all triples, and per query its relevant ones
documents = {}
for path in web.rglob('*.nq'):
    total = 0
    relevant = collections.Counter()
    for line in path.open(encoding='utf-8'):
        terms = TERM.findall(line)
        if len(terms) < 3:
            continue
        total += 1
        s, p, o = terms[0], terms[1], terms[2]
        hit = set()
        for name, ps, po in by_predicate.get(p, []) + by_predicate.get(None, []):
            if (ps is None or ps == s) and (po is None or po == o):
                hit.add(name)
        for name in hit:
            relevant[name] += 1
    documents[str(path.relative_to(web))[:-3]] = (total, relevant)
print(f'{len(documents)} documents, {sum(t for t, _ in documents.values())} triples\n')

# Fetched: per run of the proxy log
runs = collections.defaultdict(set)
for line in proxy_log.open():
    request = json.loads(line)
    if request['kind'] == 'document':
        runs[request['label']].add(urlparse(request['url']).path.strip('/'))
fetched = collections.defaultdict(list)
for label, paths in runs.items():
    query = label.split(':', 1)[1].split('#')[0]
    found = [documents[p] for p in paths if p in documents]
    total = sum(t for t, _ in found)
    relevant = sum(r[query] for _, r in found)
    if total:
        fetched[query].append((len(paths), len(found), total, relevant))

print('Fetched documents, per query: median over runs')
print(f"{'query':6} {'runs':>4} {'documents':>9} {'triples':>9} {'relevant':>9} {'share':>6}")
for query, values in sorted(fetched.items()):
    med = lambda i: st.median(v[i] for v in values)
    print(f"{query:6} {len(values):>4} {med(0):>9.0f} {med(2):>9.0f} {med(3):>9.0f} "
          f"{st.median(v[3] / v[2] for v in values):>6.1%}")

print('\nStatic, every query: documents holding a relevant triple, and all documents')
print(f"{'query':6} {'patterns':>8} {'documents':>9} {'triples':>9} {'relevant':>9} {'share':>6} {'of all':>7}")
all_triples = sum(t for t, _ in documents.values())
shares = []
for query in sorted(queries):
    hit = [(t, r[query]) for t, r in documents.values() if r[query]]
    total = sum(t for t, _ in hit)
    relevant = sum(r for _, r in hit)
    shares.append(relevant / total if total else 0)
    print(f"{query:6} {len(queries[query]):>8} {len(hit):>9} {total:>9} {relevant:>9} "
          f"{relevant / total if total else 0:>6.1%} {relevant / all_triples:>7.2%}")
print(f"\nmedian share over the queries (static): {st.median(shares):.1%}")

# The irrelevant triples of the fetched documents, split by subject: those of a subject that has a relevant triple
# (extra properties of an entity the query touches) and those of a subject without one (entities it never touches)
print('\nIrrelevant triples of the fetched documents, by subject (all runs of a query pooled, each document once)')
print(f"{'query':6} {'irrelevant':>10} {'same subject':>12} {'other subjects':>14}")
for query in sorted(fetched):
    paths = set().union(*(paths for label, paths in runs.items() if label.split(':', 1)[1].split('#')[0] == query))
    same = other = 0
    for path in paths:
        file = web / f'{path}.nq'
        if not file.exists():
            continue
        triples = [TERM.findall(line)[:3] for line in file.open(encoding='utf-8')]
        triples = [t for t in triples if len(t) == 3]
        relevant_subjects, irrelevant = set(), []
        for s, p, o in triples:
            if any((ps is None or ps == s) and (po is None or po == o)
                   for name, ps, po in by_predicate.get(p, []) + by_predicate.get(None, []) if name == query):
                relevant_subjects.add(s)
            else:
                irrelevant.append(s)
        same += sum(1 for s in irrelevant if s in relevant_subjects)
        other += sum(1 for s in irrelevant if s not in relevant_subjects)
    print(f"{query:6} {same + other:>10} {same / (same + other):>12.1%} {other / (same + other):>14.1%}")

# Fetched documents without any relevant triple: fetched for their links (or by container listings) only
print('\nFetched documents without a relevant triple (median over runs)')
print(f"{'query':6} {'documents':>9} {'of fetched':>10} {'their triples':>13} {'of fetched triples':>18}")
for query in sorted(fetched):
    rows = []
    for label, paths in runs.items():
        if label.split(':', 1)[1].split('#')[0] != query:
            continue
        found = [documents[p] for p in paths if p in documents]
        empty = [t for t, r in found if not r[query]]
        rows.append((len(empty), len(empty) / len(found), sum(empty), sum(empty) / sum(t for t, _ in found)))
    med = lambda i: st.median(r[i] for r in rows)
    print(f"{query:6} {med(0):>9.0f} {med(1):>10.1%} {med(2):>13.0f} {med(3):>18.1%}")
