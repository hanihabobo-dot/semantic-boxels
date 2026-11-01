"""Print the per-trial rows of hp_probe outputs (no trace).  --summary prints one line per file."""
import json
import sys

import numpy as np

KEYS = ('trial', 'die_dyaw_deg', 'half_mm', 'finger_mm', 'held', 'held_after', 'nf_home',
        'nf_min_carry', 'nf_max_carry', 'widen_max_mm', 'npts_min', 'flicker_steps', 'util_max',
        'max_off_mm', 'max_rot_xyz', 'max_ee_acc', 'lost')
args = [a for a in sys.argv[1:] if not a.startswith('--')]
summary = '--summary' in sys.argv
for path in args:
    d = json.load(open(path))
    rows = [r for r in d['rows'] if r.get('grip')]
    if summary:
        n = len(rows)
        held = sum(r['held'] for r in rows)
        ha = sum(r['held_after'] for r in rows)
        lost = n - ha
        # Wilson 95 % interval of the loss rate
        z = 1.96
        ph = lost / n if n else 0
        den = 1 + z * z / n if n else 1
        c = (ph + z * z / (2 * n)) / den if n else 0
        h = z * np.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den if n else 0
        rot = [max(r.get('max_rot_xyz', [0, 0, 0])) for r in rows if r['held_after']]
        nfh = [r['nf_home'] for r in rows if r['held_after']]
        print(f"{d['lever']:>18s} {d['summary'].get('body', 'dice'):>10s} {d['summary']['carry']:>5s} trials {len(d['rows'])} grips {n} "
              f"held@home {held} held+120 {ha} LOSS {lost}/{n} = {100 * ph:.1f} % "
              f"[{100 * (c - h):.1f}, {100 * (c + h):.1f}]  held: rot med {np.median(rot) if rot else 0:.1f} deg "
              f"nf_home med {np.median(nfh) if nfh else 0:.2f} N  half med {np.median([r['half_mm'] for r in rows]):.2f}")
        continue
    print('==', path, d['summary'])
    for r in d['rows']:
        if not r.get('grip'):
            print('  no grip', r.get('trial'), r.get('half_mm'))
            continue
        print('  ' + ' '.join(f"{k}={r.get(k)}" for k in KEYS))
