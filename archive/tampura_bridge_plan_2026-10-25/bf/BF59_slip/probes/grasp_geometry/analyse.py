"""Contact-set statistics of the grasp-geometry probe rows, held against lost.

Per grip, at the close and after the lift: contact points per pad, the
vertical span of each pad's contacts (z in the die frame, mm), the mean
contact height relative to the COM (the hinge line's height), the offset
across the pinch between the two pads' force centres (the couple arm).
"""
import json
import sys
from collections import defaultdict

import numpy as np


def pad_stats(contacts):
    out = {}
    for fj, pts in contacts.items():
        if not pts:
            out[fj] = None
            continue
        xyz = np.array([q['xyz_mm'] for q in pts])
        w = np.array([max(q['nf'], 1e-6) for q in pts])
        out[fj] = {'n': len(pts), 'zspan': float(xyz[:, 2].max() - xyz[:, 2].min()),
                   'xspan': float(xyz[:, 0].max() - xyz[:, 0].min()),
                   'zc': float((xyz[:, 2] * w).sum() / w.sum()),
                   'xc': float((xyz[:, 0] * w).sum() / w.sum())}
    return out


def row_stats(r, key):
    s = pad_stats(r[key]['contacts'])
    vals = [v for v in s.values() if v is not None]
    if len(vals) < 2:
        return None
    return {'n_min': min(v['n'] for v in vals),
            'zspan_min': min(v['zspan'] for v in vals),
            'span_min': min(max(v['zspan'], v['xspan']) for v in vals),
            'hinge_z': float(np.mean([v['zc'] for v in vals])),
            'couple_x': abs(vals[0]['xc'] - vals[1]['xc'])}


rows = []
for f in sys.argv[1:]:
    rows += [r for r in json.load(open(f))['rows'] if r.get('grip')]
by = defaultdict(list)
print('delta k90 cell            half  nf    | close: nmin zspan hinge_z couple_x | lift: nmin zspan hinge_z couple_x | nfmin held')
for r in rows:
    c = row_stats(r, 'close')
    l = row_stats(r, 'after_lift') if 'after_lift' in r else None
    fmt = lambda s: ('%4d %5.2f %7.2f %8.2f' % (s['n_min'], s['zspan_min'], s['hinge_z'], s['couple_x'])) if s else '   none'
    print('%5.1f %3d %-16s %5.2f %5.2f | %s | %s | %s %s' % (
        r['delta_deg'], r['k90'], r['cell'], r['close']['half_mm'], r['close']['nf'],
        fmt(c), fmt(l), r.get('nf_min'), r['held']))
    by[(r['delta_deg'] if r['delta_deg'] < 25 else 'edge')].append((r, l))
print()
for key in ('held', 'lost'):
    sel = [(r, l) for r, l in sum(by.values(), []) if (r['held'] == (key == 'held')) and l]
    if not sel:
        continue
    arr = lambda k: np.array([l[k] for r, l in sel])
    print(f"{key:5s} n={len(sel)}  lift contacts/pad min median {np.median(arr('n_min')):.1f}  "
          f"zspan median {np.median(arr('zspan_min')):.2f} mm  hinge_z median {np.median(arr('hinge_z')):.2f} mm  "
          f"couple_x median {np.median(arr('couple_x')):.2f} mm  nf at close median "
          f"{np.median([r['close']['nf'] for r, l in sel]):.2f}")
