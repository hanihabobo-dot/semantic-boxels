"""Compare executors trial by trial: python compare.py out/b1_pipe.json out/b1_trap8.json ..."""
import json
import sys
from collections import Counter, defaultdict

runs = {}
for f in sys.argv[1:]:
    d = json.load(open(f))
    name = f.split('/')[-1].replace('.json', '')
    runs[name] = {r['trial']: r for r in d['rows'] if r.get('grip')}
names = list(runs)
trials = sorted(set.intersection(*[set(v) for v in runs.values()]))
pattern = Counter()
by_yaw = defaultdict(lambda: defaultdict(int))
by_tilt = defaultdict(lambda: defaultdict(int))
for t in trials:
    key = ''.join('H' if runs[n][t]['held'] else '.' for n in names)
    pattern[key] += 1
    r0 = runs[names[0]][t]
    for n in names:
        if not runs[n][t]['held']:
            by_yaw[r0['yaw']][n] += 1
            by_tilt[r0['tilt']][n] += 1
print('order:', names)
print('patterns (H held, . lost):', dict(pattern.most_common()))
print('losses by yaw:', {y: dict(v) for y, v in sorted(by_yaw.items())})
print('losses by tilt:', {y: dict(v) for y, v in sorted(by_tilt.items())})
# what the lost trials look like at the pick
for n in names:
    rs = [runs[n][t] for t in trials]
    lost = [r for r in rs if not r['held']]
    held = [r for r in rs if r['held']]
    def med(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2] if xs else None
    print(f"{n}: held {len(held)}/{len(rs)}; f0 sum median held {med([sum(r['f0']) for r in held])} "
          f"lost {med([sum(r['f0']) for r in lost])}; half held {med([r['half_mm'] for r in held])} "
          f"lost {med([r['half_mm'] for r in lost])}; rot_peak held {med([r['rot_peak'] for r in held])} "
          f"lost {med([r['rot_peak'] for r in lost])}; appr_peak held {med([r['appr_peak'] for r in held])} "
          f"lost {med([r['appr_peak'] for r in lost])}")
    print('   lost home_f', [r['home_f'] for r in lost][:12])
