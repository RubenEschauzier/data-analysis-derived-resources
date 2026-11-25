"""Compare derived full, and derived full + extended blocks + bound composites, with pattern-only on instance 0 of
every FedShop template (VM full run of 2026-11-25: the three configurations on the same mounted code).

Usage: python analyse_instance0.py <data dir holding pattern-only/, derived-full/ and derived-extended-bound/>
Prints medians over the replications per template."""
import csv, statistics as st, sys
from pathlib import Path

csv.field_size_limit(10**9)
base = Path(sys.argv[1])
configs = {'pattern-only': 'pattern-only', 'derived full': 'derived-full', '+ ext + bound': 'derived-extended-bound'}

def load(sub):
    rows = {}
    with open(base / sub / 'query-executions.csv') as f:
        for r in csv.DictReader(f, delimiter=';'):
            rows.setdefault(r['name'], []).append(r)
    return rows

def summary(execs):
    med = lambda xs: st.median(xs) if xs else float('nan')
    ts = [[int(x) for x in e['timestamps'].split()] for e in execs if e['timestamps'].strip()]
    return {
        'n': len(execs),
        'errors': sum(e['error'] == 'true' for e in execs),
        'complete': sum(e['complete'] == 'true' for e in execs),
        'rows': med([int(e['results']) for e in execs]),
        'recall': med([float(e['recall']) for e in execs if e['recall'] not in ('', 'NaN')]),
        'first': med([t[0] for t in ts]) / 1000 if ts else float('nan'),
        'median': med([t[len(t) // 2] for t in ts]) / 1000 if ts else float('nan'),
        'last': med([t[-1] for t in ts]) / 1000 if ts else float('nan'),
        'total': med([int(e['time']) for e in execs]) / 1000,
        'requests': med([int(e['httpRequests']) for e in execs]),
        'cpu': med([float(e['proxyCpuSeconds']) for e in execs if e['proxyCpuSeconds']]),
    }

data = {name: load(sub) for name, sub in configs.items()}
templates = sorted(set().union(*data.values()))
cols = ['first', 'median', 'last', 'total']
print('Seconds, median over replications. "<config>/pattern" < 1 means that configuration is faster than pattern-only.\n')
print(f"{'tmpl':5} {'config':13} {'n':>2} {'err':>3} {'cmpl':>4} {'rows':>6} {'recall':>6} "
      + ' '.join(f'{c:>7}' for c in cols) + f" {'requests':>9}")
for t in templates:
    s = {name: summary(data[name].get(t, [])) for name in configs}
    for name in configs:
        v = s[name]
        print(f"{t:5} {name:13} {v['n']:>2} {v['errors']:>3} {v['complete']:>4} {v['rows']:>6.0f} {v['recall']:>6.2f} "
              + ' '.join(f'{v[c]:>7.1f}' for c in cols) + f" {v['requests']:>9.0f}")
    b = s['pattern-only']
    for name in ('derived full', '+ ext + bound'):
        a = s[name]
        ratio = lambda c: a[c] / b[c] if b[c] else float('nan')
        print(f"{'':5} {name[:7] + '/pattern':13} {'':>2} {'':>3} {'':>4} {'':>6} {'':>6} "
              + ' '.join(f'{ratio(c):>7.2f}' for c in cols) + f" {ratio('requests'):>9.2f}")
    print()
