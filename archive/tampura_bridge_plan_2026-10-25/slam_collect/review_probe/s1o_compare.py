"""Reviewer: S4o (predictive gate) against S1o (look before every commit), the author's files,
paired by seed and repetition on seeds 0 to 19 (3 reps; S1o has no held-out run). Read only; prints only.
Usage: python3 s1o_compare.py > out/s1o_compare.txt
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'probe', 'out')
GAMMA = 0.98


def load(name):
    with open(os.path.join(SRC, name)) as f:
        return {(r['seed'], r['rep']): r for r in json.load(f)}


def stable_first(r):
    """As p2_summarize.py:187-195."""
    w = [e.get('world', False) for e in r['log'] if not e.get('inapplicable')]
    if not w or not w[-1]:
        return None
    n = len(w)
    while n > 0 and w[n - 1]:
        n -= 1
    return n + 1


def wret(r):
    s = stable_first(r)
    return GAMMA ** s if s else 0.0


def mcnemar(a, b):
    n = a + b
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(a, b) + 1)) / 2 ** n)


def diff_stats(d, keys):
    """Mean of the paired differences, its se over episodes, and its se over seeds (clustered)."""
    xs = [d[k] for k in keys]
    m = sum(xs) / len(xs)
    se_ep = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1) / len(xs))
    seeds = sorted({k[0] for k in keys})
    per_seed = [sum(d[k] for k in keys if k[0] == s) / sum(1 for k in keys if k[0] == s) for s in seeds]
    ms = sum(per_seed) / len(per_seed)
    se_seed = math.sqrt(sum((x - ms) ** 2 for x in per_seed) / (len(per_seed) - 1) / len(per_seed))
    return m, se_ep, se_seed


A, B = load('twobelief_S4o.json'), load('twobelief_S1o.json')
keys = sorted(A)
assert sorted(B) == keys
for name, D in (('S4o', A), ('S1o', B)):
    rows = [D[k] for k in keys]
    print(f'{name}: replica {sum(r["replica_success"] for r in rows)}, world end {sum(r["world_success_end"] for r in rows)},'
          f' looks {sum(r["looks"] for r in rows)}, replica return {sum(r["replica_return"] for r in rows) / len(rows):.3f},'
          f' world return (held to the end) {sum(wret(r) for r in rows) / len(rows):.3f}')
for fld in ('world_success_end', 'replica_success'):
    a = sum(1 for k in keys if A[k][fld] and not B[k][fld])
    b = sum(1 for k in keys if B[k][fld] and not A[k][fld])
    print(f'{fld}: S4o only {a}, S1o only {b}, exact McNemar p {mcnemar(a, b):.3f}')
for label, f in (('replica return', lambda r: r['replica_return']), ('world return', wret)):
    d = {k: f(A[k]) - f(B[k]) for k in keys}
    m, se_ep, se_seed = diff_stats(d, keys)
    print(f'{label}, S4o minus S1o: {m:+.3f}, se over 60 episodes {se_ep:.3f}, se over 20 seeds {se_seed:.3f}')
