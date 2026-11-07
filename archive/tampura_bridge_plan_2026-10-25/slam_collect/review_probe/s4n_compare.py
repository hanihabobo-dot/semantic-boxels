"""Reviewer: S4o (the author's files) against S4n (S4o without the clearance clause, review run),
paired by seed and repetition, on seeds 0 to 19 (3 reps) and 100 to 119 (2 reps). Read only; prints only.
Usage: python3 s4n_compare.py > out/s4n_compare.txt
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GAMMA = 0.98


def load(path):
    with open(path) as f:
        return json.load(f)


def stable_first(r):
    """As p2_summarize.py:187-195: first step (1-based) from which the world test holds to the end."""
    w = [e.get('world', False) for e in r['log'] if not e.get('inapplicable')]
    if not w or not w[-1]:
        return None
    n = len(w)
    while n > 0 and w[n - 1]:
        n -= 1
    return n + 1


def mse(xs):
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))
    return f'{m:.3f} +- {sd / math.sqrt(len(xs)):.3f}'


def mcnemar(a_only, b_only):
    n = a_only + b_only
    if n == 0:
        return 1.0
    k = min(a_only, b_only)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


for tag in ('', '_seeds100'):
    if not os.path.exists(os.path.join(HERE, 'out', f'twobelief_S4n{tag}.json')):
        print(f'twobelief_S4n{tag}.json not written yet')
        continue
    A = {(r['seed'], r['rep']): r for r in load(os.path.join(HERE, '..', 'probe', 'out', f'twobelief_S4o{tag}.json'))}
    B = {(r['seed'], r['rep']): r for r in load(os.path.join(HERE, 'out', f'twobelief_S4n{tag}.json'))}
    keys = sorted(A)
    assert sorted(B) == keys, 'episode sets differ'
    print(f'=== seeds {"0 to 19" if not tag else "100 to 119"}, n = {len(keys)} ===')
    for name, D in (('S4o', A), ('S4n', B)):
        rows = [D[k] for k in keys]
        sf = [stable_first(r) for r in rows]
        print(f'{name}: replica success {sum(r["replica_success"] for r in rows)}, return {mse([r["replica_return"] for r in rows])}'
              f' | world end {sum(r["world_success_end"] for r in rows)}, world return (held to the end)'
              f' {mse([GAMMA ** s if s else 0.0 for s in sf])} | true collisions {sum(r["world_collision"] for r in rows)}'
              f' | looks {sum(r["looks"] for r in rows)} | errors {sum(1 for r in rows if r.get("error"))}')
    same = [k for k in keys if [e['action'] for e in A[k]['log']] == [e['action'] for e in B[k]['log']]]
    print(f'identical action sequences {len(same)} of {len(keys)}')
    for fld in ('world_success_end', 'replica_success'):
        a_only = sum(1 for k in keys if A[k][fld] and not B[k][fld])
        b_only = sum(1 for k in keys if B[k][fld] and not A[k][fld])
        print(f'{fld}: S4o only {a_only}, S4n only {b_only}, exact McNemar p {mcnemar(a_only, b_only):.3f}')
    for label, f in (('replica return', lambda r: r['replica_return']),
                     ('world return', lambda r: GAMMA ** stable_first(r) if stable_first(r) else 0.0)):
        d = [f(A[k]) - f(B[k]) for k in keys]
        m = sum(d) / len(d)
        se = math.sqrt(sum((x - m) ** 2 for x in d) / (len(d) - 1) / len(d))
        seeds = sorted({k[0] for k in keys})
        ps = [sum(f(A[k]) - f(B[k]) for k in keys if k[0] == s) / sum(1 for k in keys if k[0] == s) for s in seeds]
        mps = sum(ps) / len(ps)
        se_s = math.sqrt(sum((x - mps) ** 2 for x in ps) / (len(ps) - 1) / len(ps))
        print(f'{label}, S4o minus S4n: {m:+.3f}, se over {len(d)} episodes {se:.3f}, se over {len(seeds)} seeds {se_s:.3f}')
    print('episodes whose actions differ: (seed, rep) S4o world/replica/looks/true collision -> S4n the same')
    for k in keys:
        if k in same:
            continue
        a, b = A[k], B[k]
        print('  ', k, a['world_success_end'], a['replica_success'], a['looks'], a['world_collision'], '->',
              b['world_success_end'], b['replica_success'], b['looks'], b['world_collision'])
    print()
