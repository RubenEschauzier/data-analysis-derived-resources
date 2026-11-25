"""Which requests fail, and whether the failures explain missing rows (q04 rerun of 2026-11-25, vm-q04-errors.sh).

Per run (proxy label): rows returned, failed requests (status 0/none or >= 400) by kind, pod and status, how long
they took, and the engine's warnings about them.

Usage: python analyse_request_errors.py <dir holding output/ (proxy-requests.jsonl, run.log) and engine-*.log>
"""
import collections
import json
import re
import statistics as st
import sys
from pathlib import Path

base = Path(sys.argv[1])
rows = {}
for line in (base / 'output' / 'run.log').read_text().splitlines():
    m = re.match(r'(\S+)\s+(q\d+)#0\s+[\d.]+s .*?(\d+) timed rows', line)
    if m:
        rows[f'{m.group(1)}:{m.group(2)}#0'] = int(m.group(3))

requests = collections.defaultdict(list)
for line in (base / 'output' / 'proxy-requests.jsonl').open():
    r = json.loads(line)
    requests[r['label']].append(r)


def failed(r):
    return not r.get('status') or r['status'] >= 400


print(f"{'run':32} {'rows':>4} {'requests':>8} {'failed':>6}  failed by kind / status / pod")
for label in sorted(requests, key=lambda label: (label.split(':')[1], label)):
    if label not in rows:
        continue
    reqs = requests[label]
    bad = [r for r in reqs if failed(r)]
    kinds = collections.Counter((r['kind'], r.get('status')) for r in bad)
    pods = collections.Counter(r['publisher'] for r in bad)
    print(f"{label:32} {rows[label]:>4} {len(reqs):>8} {len(bad):>6}  "
          f"{dict(kinds)} {dict(pods.most_common(3))}")

print('\nFailed requests, all runs pooled: kind, status, duration (ms) and an example')
bad = [r for reqs in requests.values() for r in reqs if failed(r)]
for (kind, status), group in sorted(collections.Counter((r['kind'], r.get('status')) for r in bad).items(),
                                    key=lambda item: -item[1]):
    sample = [r for r in bad if r['kind'] == kind and r.get('status') == status]
    ms = [r.get('ms') or 0 for r in sample]
    print(f"  {kind:14} status {status}: {group} failed, ms median {st.median(ms):.0f}, max {max(ms):.0f}; "
          f"e.g. {sample[0]['url'][:110]}")

print('\nEngine warnings (first 3 distinct per log)')
for log in sorted(base.glob('engine-*.log')):
    seen = []
    for line in log.read_text(errors='replace').splitlines():
        if re.search(r'warn|error|fail', line, re.I) and 'bound-trace' not in line:
            text = re.sub(r'\d+', '#', line)[:160]
            if text not in seen:
                seen.append(text)
    if seen:
        print(f'  {log.name}: {len(seen)} distinct')
        for text in seen[:3]:
            print(f'    {text}')
