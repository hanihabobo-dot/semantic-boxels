"""BF#63 extra tables from the pulled eval/<job>/ folders: the gates of
every job, per cup count, timeouts, arm O's failure outcomes, arm T's
crashes.  Usage: python -I bf63_tables.py <eval dir> [job glob: 50630* = run 1,
the default; 5084* = run 2 in eval2]"""
import collections, glob, json, math, os, statistics, sys

ev = sys.argv[1]
pat = sys.argv[2] if len(sys.argv) > 2 else '50630*'
jobs = sorted(d for d in glob.glob(os.path.join(ev, pat)) if os.path.isdir(d))
print('== gates and job ends')
for d in jobs:
    j = os.path.basename(d)
    fails = []
    for g in ('gates_before.txt', 'gates_after.txt'):
        t = open(os.path.join(d, g), encoding='utf-8', errors='replace').read()
        fails += [f"{g}: {l[:90]}" for l in t.splitlines() if ' FAIL ' in l]
        if g == 'gates_after.txt' and 'unchanged since' not in t:
            fails.append('gates_after: no "unchanged since"')
    log = open(os.path.join(d, f'p4-gen_{j}.txt'), encoding='utf-8', errors='replace').read()
    host = next((l.split()[1] for l in log.splitlines() if l.startswith('host ')), '?')
    cpu = next((l.split(':', 1)[1].strip() for l in log.splitlines() if l.startswith('model name')), '?')
    print(f"{j} {host} {cpu[:40]:40} harness rc 0: {'harness rc 0' in log}  GEN_DONE: {'GEN_DONE' in log}"
          f"  gate FAILs: {fails or 'none'}")

rows = []
for d in jobs:
    with open(os.path.join(d, 'results.jsonl'), encoding='utf-8') as f:
        rows += [json.loads(l) for l in f if l.strip()]
final = {}
for r in rows:
    k = (r['arm'], r['seed'], r['rep'])
    if k not in final or r['attempt'] >= final[k]['attempt']:
        final[k] = r


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


print('\n== per cup count (counted runs; successes/counted, Wilson 95 %; timeouts)')
cups = sorted({r['n_cups'] for r in final.values()})
for c in cups:
    cells = []
    for arm in ('O', 'T'):
        rs = [r for (a, s, rep), r in final.items() if a == arm and r['n_cups'] == c and r['counts']]
        k = sum(r['success'] for r in rs)
        lo, hi = wilson(k, len(rs)) if rs else (float('nan'),) * 2
        cells.append(f"{arm} {k:2}/{len(rs):2} ({k / len(rs):.2f} [{lo:.2f}, {hi:.2f}]) to {sum(r['timed_out'] for r in rs)}")
    nsc = len({s for (a, s, rep), r in final.items() if r['n_cups'] == c})
    print(f"{c} cups ({nsc} scenes): " + '   '.join(cells))

print('\n== pairs per cup count (both / only O / only T / neither)')
for c in cups:
    keys = sorted({(s, rep) for (a, s, rep), r in final.items() if r['n_cups'] == c})
    pr = [(s, rep) for s, rep in keys if final[('O', s, rep)]['counts'] and final[('T', s, rep)]['counts']]
    b = sum(final[('O', s, r)]['success'] and final[('T', s, r)]['success'] for s, r in pr)
    o = sum(final[('O', s, r)]['success'] and not final[('T', s, r)]['success'] for s, r in pr)
    t = sum(final[('T', s, r)]['success'] and not final[('O', s, r)]['success'] for s, r in pr)
    print(f"{c} cups: {len(pr)} pairs, both {b}, only O {o}, only T {t}, neither {len(pr) - b - o - t}")

print('\n== arm O outcomes of counted failures')
oc = collections.Counter()
for (a, s, rep), r in sorted(final.items()):
    if a == 'O' and r['counts'] and not r['success']:
        m = r['rec'].get('metrics') or {}
        why = 'timeout' if r['timed_out'] else (m.get('outcome') or r['rec'].get('bridge_status'))
        oc[why] += 1
        print(f"  s{s} r{rep} cups {r['n_cups']}: {why}, wall {r['wall_s']}, carries {r['rec'].get('carries')}, losses {r['rec'].get('losses')}")
print('  totals:', dict(oc))

print('\n== arm T: counted failures (timeouts vs other) and crashes')
tf = [r for (a, s, rep), r in final.items() if a == 'T' and r['counts'] and not r['success']]
print(f"  counted failures {len(tf)}: timeouts {sum(r['timed_out'] for r in tf)}, ended below reward 1 {sum(not r['timed_out'] for r in tf)}")
cr = [r for r in rows if r['arm'] == 'T' and not r['counts']]
print(f"  crashed runs {len(cr)} of {sum(r['arm'] == 'T' for r in rows)} T runs: "
      + ', '.join(f"s{r['seed']} r{r['rep']} a{r['attempt']}" for r in cr))
print('\n== walls (counted runs, s): median, min, max')
for arm in ('O', 'T'):
    w = [r['wall_s'] for (a, s, rep), r in final.items() if a == arm and r['counts']]
    ws = [r['wall_s'] for (a, s, rep), r in final.items() if a == arm and r['counts'] and r['success']]
    print(f"  {arm}: all {statistics.median(w):.1f} [{min(w):.1f}, {max(w):.1f}]  successes {statistics.median(ws):.1f} [{min(ws):.1f}, {max(ws):.1f}]")
print('\n== per-scene success agreement across the two reps (counted)')
for arm in ('O', 'T'):
    agree = dis = 0
    for s in sorted({s for (a, s, rep) in final}):
        a0, a1 = final.get((arm, s, 0)), final.get((arm, s, 1))
        if a0 and a1 and a0['counts'] and a1['counts']:
            if a0['success'] == a1['success']:
                agree += 1
            else:
                dis += 1
    print(f"  {arm}: same outcome in both reps {agree} scenes, different {dis}")
