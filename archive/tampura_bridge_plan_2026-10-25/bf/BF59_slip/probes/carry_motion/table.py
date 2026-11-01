"""One table over a batch: python table.py <prefix> (e.g. out/b5_)
Rows: delta, rule, executor -> held/carries, move steps median (time),
peak hand linear acceleration median, |dq7| median (deg), median peak
rotation of the die in the hand, losses by tilt."""
import glob
import json
import math
import sys


def med(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else float('nan')


rows = []
for f in sorted(glob.glob(sys.argv[1] + '*.json')):
    d = json.load(open(f))
    s = d['summary']
    rs = [r for r in d['rows'] if r.get('grip')]
    if not rs:
        continue
    by_tilt = {}
    for r in rs:
        t = by_tilt.setdefault(r['tilt'], [0, 0])
        t[0] += r['held']
        t[1] += 1
    rows.append((s.get('payload', 'dice') + ('/' + s['path'] if s['path'] != 'linear' else '') + ('/after' if 'after' in f else ''),
                 s.get('delta_deg', 0.0), s.get('grasp_rule', '?'), s['executor'],
                 sum(r['held'] for r in rs), len(rs), med([r['move_steps'] for r in rs]),
                 med([r['la_peak'] for r in rs]), med([abs(math.degrees(r['dq7'])) for r in rs]),
                 med([r['rot_peak'] for r in rs]), med([r['half_mm'] for r in rs]),
                 ' '.join(f"t{k:g}:{v[0]}/{v[1]}" for k, v in sorted(by_tilt.items()))))
rows.sort()
print('| body/path | delta deg | rule | executor | held | % | move steps | peak EE acc m/s^2 | abs dq7 deg | die rot peak deg | half mm | by tilt |')
print('|---|---|---|---|---|---|---|---|---|---|---|---|')
for b, d, rule, ex, h, n, ms, la, dq7, rot, half, bt in rows:
    print(f'| {b} | {d:g} | {rule} | {ex} | {h}/{n} | {100 * h / n:.0f} | {ms:.0f} | {la:.1f} | {dq7:.0f} | {rot:.1f} | {half:.2f} | {bt} |')
