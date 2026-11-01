"""Hand-frame contact statistics (hand yaw 0: world x is across the pinch,
world y along it): the across-pinch offset between the two pads' force
centres (the arm of the normal-force couple about z) and the contacts'
height relative to the COM, at the close and after the lift, per delta
band, held against lost."""
import json
import sys
from collections import defaultdict

import numpy as np


def centres(contacts):
    out = []
    for fj, pts in contacts.items():
        if not pts or 'world_rel_mm' not in pts[0]:
            return None
        xyz = np.array([q['world_rel_mm'] for q in pts])
        w = np.array([max(q['nf'], 1e-6) for q in pts])
        out.append((xyz * w[:, None]).sum(0) / w.sum())
    return out if len(out) == 2 else None


rows = []
for f in sys.argv[1:]:
    rows += [r for r in json.load(open(f))['rows'] if r.get('grip')]
groups = defaultdict(list)
for r in rows:
    c = centres(r['close']['contacts'])
    l = centres(r['after_lift']['contacts']) if 'after_lift' in r else None
    if c is None:
        continue
    d = r['delta_deg']
    band = 'face 0' if d == 0 else ('face 1-25' if d <= 25 else 'edge 30-57')
    groups[band].append({'held': r['held'], 'arm': abs(c[0][0] - c[1][0]),
                         'z': 0.5 * (c[0][2] + c[1][2]),
                         'arm_lift': abs(l[0][0] - l[1][0]) if l else np.nan,
                         'z_lift': 0.5 * (l[0][2] + l[1][2]) if l else np.nan,
                         'nf': r['close']['nf'], 'nf_min': r.get('nf_min')})
for band, g in groups.items():
    for key in (True, False):
        s = [x for x in g if x['held'] == key]
        if not s:
            continue
        m = lambda k: np.nanmedian([x[k] for x in s])
        print(f"{band:11s} {'held' if key else 'lost'} n={len(s):3d}  couple arm close {m('arm'):5.2f} mm "
              f"lift {m('arm_lift'):5.2f} mm  contact z rel COM close {m('z'):5.2f} lift {m('z_lift'):5.2f} mm  "
              f"nf close {m('nf'):4.2f} N  nf_min {np.nanmedian([x['nf_min'] or 0 for x in s]):4.2f} N")
