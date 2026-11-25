"""Bound-composite experiment of 2026-11-25 (vm-bound-experiment.sh): answer arrival per configuration, and from the
bound trace (DERIVED_BOUND_TRACE=1) how long bound targets wait for seed values and how the seed values trickle in.

Usage: python analyse_bound_policy.py <experiment dir holding output/ and engine-<config>-r<n>.log>
"""
import collections
import json
import re
import statistics as st
import sys
from pathlib import Path

base = Path(sys.argv[1])
CONFIGS = {
    'derived': 'derived full',
    'extended': 'derived full + extended blocks',
    'bound-all': 'bound composites, every seed',
    'bound-oneshot': 'bound composites, one-shot seeds only',
}
EXPECTED = {'q12': 1, 'q13': 99, 'q14': 36, 'q16': 58}
med = lambda xs: st.median(xs) if xs else float('nan')

# Requests per run, from the runner's log lines
requests = {}
for line in (base / 'output' / 'run.log').read_text().splitlines():
    m = re.match(r'(\S+)\s+(q\d+)#0\s+[\d.]+s .*requests=(\d+) sparql=(\d+)', line)
    if m:
        requests[(m.group(1), m.group(2))] = (int(m.group(3)), int(m.group(4)))

# Trace events per engine log, assigned to queries by their wall-time window
runs = collections.defaultdict(dict)  # (config, round) -> query -> data
for meta_file in sorted((base / 'output').glob('*.meta.json')):
    meta = json.loads(meta_file.read_text())
    label, query = meta['label'], meta['query'].split('#')[0]
    config, rnd = label.rsplit('-r', 1)
    rows_file = meta_file.with_name(meta_file.name.replace('.meta.json', '.rows.json'))
    rows = json.loads(rows_file.read_text()) if rows_file.exists() else []
    distinct = len({json.dumps(r['binding'], sort_keys=True) for r in rows})
    runs[(config, rnd)][query] = {'meta': meta, 'times': [r['t'] for r in rows], 'distinct': distinct,
                                  'requests': requests.get((label, query)), 'events': []}
for (config, rnd), queries in runs.items():
    log = base / f'engine-{config}-r{rnd}.log'
    if not log.exists():
        continue
    for line in log.read_text(errors='replace').splitlines():
        if '[bound-trace] ' not in line:
            continue
        event = json.loads(line.split('[bound-trace] ', 1)[1])
        # The query sent last before the event; the engine runs one query at a time
        started = [d for d in queries.values() if d['meta']['began_ms'] <= event['t']]
        if started:
            data = max(started, key=lambda d: d['meta']['began_ms'])
            event['s'] = (event['t'] - data['meta']['began_ms']) / 1000
            data['events'].append(event)

print('Answer arrival, median over rounds (s); rows = distinct rows (expected in brackets); requests median\n')
print(f"{'query':5} {'configuration':40} {'runs':>4} {'rows':>9} {'first':>6} {'median':>6} {'last':>6} {'end':>6} {'requests':>9} {'sparql':>7}")
for query in EXPECTED:
    for config, name in CONFIGS.items():
        data = [qs[query] for (c, _), qs in runs.items() if c == config and query in qs]
        if not data:
            continue
        times = [d['times'] for d in data if d['times']]
        print(f"{query:5} {name:40} {len(data):>4} {med([d['distinct'] for d in data]):>5.0f} ({EXPECTED[query]:>2})"
              f" {med([t[0] for t in times]):>6.1f} {med([t[len(t) // 2] for t in times]):>6.1f} {med([t[-1] for t in times]):>6.1f}"
              f" {med([(d['meta']['ended_ms'] - d['meta']['began_ms']) / 1000 for d in data]):>6.1f}"
              f" {med([d['requests'][0] for d in data if d['requests']]):>9.0f} {med([d['requests'][1] for d in data if d['requests']]):>7.0f}")
    print()

print('Bound targets per query (all rounds pooled; times in s since the query was sent)\n')
for query in EXPECTED:
    for config in ('bound-all', 'bound-oneshot'):
        data = [qs[query] for (c, _), qs in runs.items() if c == config and query in qs]
        events = [e for d in data for e in d['events']]
        if not events:
            continue
        n_runs = len(data)
        decisions = collections.Counter((e['decision'], e.get('reason') or e.get('kind')) for e in events if e['e'] == 'target')
        plan = next((e['plan'] for e in events if e['e'] == 'plan'), [])
        print(f"{query} · {CONFIGS[config]}  plan: {', '.join(f'?{p['v']} {p['kind']}' + (f' (via ?{p['from']})' if p.get('from') else '') for p in plan)}")
        print('   decisions per run: ' + ', '.join(f'{d} {r}: {n / n_runs:.0f}' for (d, r), n in sorted(decisions.items())))
        # Per run and target pod: when it was found, when its first bound request went out, rows answered
        waits, known, rows_bound, reqs, answer_ms = [], [], [], [], []
        for d in data:
            found = {e['pod']: e for e in d['events'] if e['e'] == 'target' and e['decision'] == 'bound'}
            answers = collections.defaultdict(list)
            for e in d['events']:
                if e['e'] == 'answer':
                    answers[e['pod']].append(e)
            for pod, target in found.items():
                known.append(target['known'])
                sent = [a['s'] - a['ms'] / 1000 for a in answers.get(pod, [])]
                if sent:
                    waits.append(min(sent) - target['s'])
                reqs.append(len(answers.get(pod, [])))
                rows_bound.append(sum(a['rows'] or 0 for a in answers.get(pod, [])))
                answer_ms.extend(a['ms'] for a in answers.get(pod, []))
        if known:
            never = sum(1 for r in reqs if r == 0)
            print(f"   bound targets: {len(known) / n_runs:.0f}/run; values known at decision median {med(known):.0f}; "
                  f"never sent {never / n_runs:.0f}/run; wait for first request median {med(waits):.1f} s, p90 "
                  f"{sorted(waits)[int(0.9 * len(waits))] if waits else float('nan'):.1f} s; requests per target median {med(reqs):.0f}, "
                  f"max {max(reqs)}; read time median {med(answer_ms) / 1000:.1f} s; rows from bound requests {sum(rows_bound) / n_runs:.0f}/run")
        # How the seed values trickle in, per variable
        for variable in sorted({e['v'] for e in events if e['e'] == 'value'}):
            per_run = []
            for d in data:
                times = sorted(e['s'] for e in d['events'] if e['e'] == 'value' and e['v'] == variable)
                if times:
                    per_run.append((len(times), times[0], times[len(times) // 2], times[int(0.9 * (len(times) - 1))], times[-1]))
            if per_run:
                print(f"   seed ?{variable}: values {med([p[0] for p in per_run]):.0f}; first {med([p[1] for p in per_run]):.1f}, "
                      f"half {med([p[2] for p in per_run]):.1f}, 90% {med([p[3] for p in per_run]):.1f}, last {med([p[4] for p in per_run]):.1f} s")
        print()

print('Composite rows per run: blocks requested whole (by number of patterns), and bound requests\n')
for query in EXPECTED:
    line = []
    for config in CONFIGS:
        data = [qs[query] for (c, _), qs in runs.items() if c == config and query in qs]
        if not data:
            continue
        whole = collections.Counter()
        for d in data:
            for e in d['events']:
                if e['e'] == 'whole':
                    whole[e['ops']] += e['rows']
        bound = sum(e['rows'] or 0 for d in data for e in d['events'] if e['e'] == 'answer')
        parts = [f'{ops} patterns: {rows / len(data):.0f}' for ops, rows in sorted(whole.items())]
        if bound:
            parts.append(f'bound: {bound / len(data):.0f}')
        line.append(f"{config}: {'; '.join(parts) or '-'}")
    print(f"{query}  " + '\n      '.join(line))
