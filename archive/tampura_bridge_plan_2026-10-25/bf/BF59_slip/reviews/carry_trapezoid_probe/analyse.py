"""Tables of the carry_trapezoid real-pick check: held per delta and in all
(Wilson 95 % intervals), paired on (cell, k90, delta) with the exact
McNemar test, carry steps and the minimum pad force.
  python analyse.py hy180_pipeline.json hy180_trapezoid.json"""
import json
import math
import sys

import numpy as np


def wilson(k, n, z=1.96):
    if n == 0:
        return (float('nan'), float('nan'))
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def load(path):
    rows = json.load(open(path))['rows']
    return {(tuple(r['cell']), r['k90'], r['delta_deg']): r for r in rows}


A, B = load(sys.argv[1]), load(sys.argv[2])
names = ('pipeline', 'trapezoid')
keys = sorted(set(A) & set(B))
gk = [k for k in keys if A[k].get('grip') and B[k].get('grip')]
print(f"trials {len(keys)}, gripped in both {len(gk)}; gripped: "
      f"pipeline {sum(bool(A[k].get('grip')) for k in keys)}, "
      f"trapezoid {sum(bool(B[k].get('grip')) for k in keys)}")
for d in sorted({k[2] for k in gk}) + ['all']:
    ks = [k for k in gk if d == 'all' or k[2] == d]
    line = [f"delta {d!s:>4}:"]
    for nm, S in zip(names, (A, B)):
        h = sum(bool(S[k]['held']) for k in ks)
        lo, hi = wilson(h, len(ks))
        line.append(f"{nm} {h}/{len(ks)} [{100*lo:.0f}, {100*hi:.0f} %]")
    b = sum(bool(A[k]['held']) and not B[k]['held'] for k in ks)
    c = sum(B[k]['held'] and not A[k]['held'] for k in ks)
    line.append(f"discordant pipe-only {b} trap-only {c}, McNemar p {mcnemar(b, c):.3g}")
    print('  '.join(line))
for nm, S in zip(names, (A, B)):
    rs = [S[k] for k in gk]
    lost = [r['lost']['phase'] for r in rs if not r['held'] and r.get('lost')]
    print(f"{nm}: steps from the lift to home (lift + carry + settle) median "
          f"{np.median([r['carry_steps'] for r in rs]):.0f} "
          f"[{min(r['carry_steps'] for r in rs)}, {max(r['carry_steps'] for r in rs)}]; "
          f"min summed pad force median {np.median([r['nf_min'] for r in rs]):.2f} N; "
          f"half-width median {np.median([r['close']['half_mm'] for r in rs]):.2f} mm; "
          f"loss phases {dict((p, lost.count(p)) for p in set(lost))}")
