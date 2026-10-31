import json, statistics, collections, sys
path = sys.argv[1]
recs = [json.loads(l) for l in open(path, encoding='utf-8') if l.strip()]
arms = ['base', '1', '2', '12', '3', '123', '4', '1234']
by = {(r['arm'], r['seed']): r for r in recs}
seeds = sorted({r['seed'] for r in recs})
def outcome(r):
    if r.get('timed_out'): return 'timeout'
    m = r.get('metrics') or {}
    return m.get('outcome') or ('rc%d' % r['rc'])
def ok(r): return outcome(r) == 'success'
def closed(r): return bool((r.get('metrics') or {}).get('wall_s') is not None)
print('OUTCOMES per arm')
for a in arms:
    c = collections.Counter(outcome(by[(a, s)]) for s in seeds if (a, s) in by)
    print(f"  {a:5} " + ', '.join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda kv: -kv[1])))
def med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None
def f(v): return '   -' if v is None else f"{v:6.1f}"
print()
print('MEDIANS per arm (wall / planning / planning_first), over: all closed episodes of the arm | the successes of the arm | the 18 seeds every arm closed')
allclosed = [s for s in seeds if all(closed(by[(a, s)]) for a in arms)]
for a in arms:
    rs = [by[(a, s)] for s in seeds]
    c1 = [r['metrics'] for r in rs if closed(r)]
    c2 = [r['metrics'] for r in rs if ok(r)]
    c3 = [by[(a, s)]['metrics'] for s in allclosed]
    print(f"  {a:5} closed n={len(c1):2} wall {f(med(m['wall_s'] for m in c1))} plan {f(med(m['planning_s'] for m in c1))} first {f(med(m['planning_first_s'] for m in c1))}"
          f" | success n={len(c2):2} wall {f(med(m['wall_s'] for m in c2))} plan {f(med(m['planning_s'] for m in c2))}"
          f" | all-closed n={len(c3):2} wall {f(med(m['wall_s'] for m in c3))} plan {f(med(m['planning_s'] for m in c3))}")
print()
print('PER FIX, pairwise: seeds where BOTH arms succeeded (the working seeds of the pair): n, median wall a -> b, median planning a -> b, per-seed wall ratio median; and over seeds both closed')
pairs = [('fix 1 alone', 'base', '1'), ('fix 2 alone', 'base', '2'), ('fix 2 added', '1', '12'), ('fix 3 alone', 'base', '3'), ('fix 3 added', '12', '123'),
         ('fix 4 alone', 'base', '4'), ('fix 4 added', '123', '1234'), ('all four', 'base', '1234'), ('1+2+3 vs base', 'base', '123'), ('fix 4 added to 1', '1', '14?')]
for name, a, b in pairs:
    if b not in arms: continue
    both_ok = [s for s in seeds if ok(by[(a, s)]) and ok(by[(b, s)])]
    both_cl = [s for s in seeds if closed(by[(a, s)]) and closed(by[(b, s)])]
    def stats(sel):
        wa = [by[(a, s)]['metrics']['wall_s'] for s in sel]; wb = [by[(b, s)]['metrics']['wall_s'] for s in sel]
        pa = [by[(a, s)]['metrics']['planning_s'] for s in sel]; pb = [by[(b, s)]['metrics']['planning_s'] for s in sel]
        ratios = [by[(b, s)]['metrics']['wall_s'] / by[(a, s)]['metrics']['wall_s'] for s in sel]
        faster = sum(1 for r in ratios if r < 0.9); slower = sum(1 for r in ratios if r > 1.1)
        return f"n={len(sel):2} wall {f(med(wa))} -> {f(med(wb))}  plan {f(med(pa))} -> {f(med(pb))}  ratio med {med(ratios):.2f} (faster {faster}, slower {slower})"
    print(f"  {name:18} {a:4}->{b:4}  both-success: {stats(both_ok)}")
    print(f"  {'':18} {'':4}  {'':4}  both-closed:  {stats(both_cl)}   success {sum(ok(by[(a,s)]) for s in seeds)} -> {sum(ok(by[(b,s)]) for s in seeds)}")
print()
print('PER SEED outcome (S success, P physics_mismatch, L planner_failed, T timeout, o other) and wall')
print('  seed ' + ' '.join(f"{a:>9}" for a in arms))
code = {'success': 'S', 'physics_mismatch': 'P', 'planner_failed': 'L', 'timeout': 'T'}
for s in seeds:
    row = []
    for a in arms:
        r = by[(a, s)]; o = outcome(r); w = (r.get('metrics') or {}).get('wall_s')
        row.append(f"{code.get(o, 'o')}{(f'{w:7.1f}' if w is not None else '      -')}")
    print(f"  {s:4} " + ' '.join(f"{x:>9}" for x in row))
print()
print('OTHER outcomes spelled out:')
for a in arms:
    for s in seeds:
        o = outcome(by[(a, s)])
        if o not in code: print(f"  {a} seed {s}: {o}, rc {by[(a,s)]['rc']}, bridge {by[(a,s)].get('bridge_status')}")
print()
print('seed 6 and 19 details (plan_calls / steps / senses / observes / wall):')
for s in (6, 19, 20, 10, 17):
    print(f"  seed {s}: " + ' | '.join(f"{a}: " + (f"{m['plan_calls']}/{m['steps']}/{m['senses']}/{m['observes']}/{m['wall_s']:.0f} {outcome(by[(a,s)])[:7]}" if (m := by[(a, s)].get('metrics')) and m.get('wall_s') is not None else outcome(by[(a,s)])) for a in arms))