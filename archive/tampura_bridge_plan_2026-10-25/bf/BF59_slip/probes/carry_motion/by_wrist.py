"""Held rate against the carry's wrist travel: python by_wrist.py <json>...
Per run: held by |dq7| bin (joint 7's travel from the lift to home, deg),
by die yaw, and by the hand's integrated spin about its approach axis."""
import json
import math
import sys
from collections import defaultdict

BINS = [(0, 45), (45, 90), (90, 135), (135, 180), (180, 225), (225, 400)]

for f in sys.argv[1:]:
    d = json.load(open(f))
    rs = [r for r in d['rows'] if r.get('grip') and 'dq7' in r]
    name = f.split('/')[-1].replace('.json', '')
    out = []
    for lo, hi in BINS:
        b = [r for r in rs if lo <= abs(math.degrees(r['dq7'])) < hi]
        if b:
            out.append(f"{lo}-{hi}: {sum(r['held'] for r in b)}/{len(b)}")
    byy = defaultdict(lambda: [0, 0, []])
    for r in rs:
        k = (round(r['yaw'], 2), r['tilt'])
        byy[k][0] += r['held']
        byy[k][1] += 1
        byy[k][2].append(round(math.degrees(r['dq7'])))
    spin = [abs(r['hand_rot_deg'][2]) for r in rs]
    print(f"{name}: held {sum(r['held'] for r in rs)}/{len(rs)}; by |dq7| deg: " + '; '.join(out))
    for k in sorted(byy):
        h, n, dq = byy[k]
        dq = sorted(dq)
        print(f"    yaw {k[0]:+.2f} tilt {k[1]:.0f}: {h}/{n}  dq7 deg median {dq[len(dq) // 2]} range {dq[0]}..{dq[-1]}")
