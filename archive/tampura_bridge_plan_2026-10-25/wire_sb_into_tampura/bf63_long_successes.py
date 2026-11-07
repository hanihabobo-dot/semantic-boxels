"""Read-only: the arm O rows of BF#63 run 2 for given (seed, rep) pairs, the
fields that say why a success took many primitives (pick tries, carries,
losses, the metrics), from eval2/5084*/results.jsonl (final attempt).
Usage: python -I -B bf63_long_successes.py <eval2 dir> 101:1 139:1
"""
import glob
import json
import os
import sys

ev = sys.argv[1]
want = {tuple(int(x) for x in a.split(':')) for a in sys.argv[2:]}
rows = []
for d in sorted(glob.glob(os.path.join(ev, '5084*'))):
    with open(os.path.join(d, 'results.jsonl'), encoding='utf-8') as f:
        rows += [json.loads(l) for l in f if l.strip()]
final = {}
for r in rows:
    k = (r['arm'], r['seed'], r['rep'])
    if k not in final or r['attempt'] >= final[k]['attempt']:
        final[k] = r
for (arm, s, rep), r in sorted(final.items()):
    if arm == 'O' and (s, rep) in want:
        rec = r['rec']
        m = rec.get('metrics') or {}
        print(f"s{s} r{rep}: success {r['success']}, cups {r['n_cups']}, wall {r['wall_s']}")
        print(f"  pick_tries {rec.get('pick_tries')}, carries {rec.get('carries')}, losses {rec.get('losses')}")
        print("  metrics:", json.dumps(m, sort_keys=True))
