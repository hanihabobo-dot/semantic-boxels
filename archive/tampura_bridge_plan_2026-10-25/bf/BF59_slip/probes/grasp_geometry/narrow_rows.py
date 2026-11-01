"""The face grips whose measured half-width reads narrow (< 10.15 mm)
against the typical face reading: contact heights and positions in the
hand frame (world, relative to the die's COM), the die's tilt and yaw at
the close."""
import json
import sys

import numpy as np

for f in sys.argv[1:]:
    for r in json.load(open(f))['rows']:
        if not r.get('grip') or r['close']['half_mm'] >= 12.0:
            continue
        w = r['close']['half_mm']
        tag = 'NARROW' if w < 10.15 else 'typical' if w < 10.45 else 'wide'
        pts = []
        for fj, ps in r['close']['contacts'].items():
            for q in ps:
                if 'world_rel_mm' in q:
                    pts.append((fj, q['world_rel_mm'], q['nf']))
        zs = [p[1][2] for p in pts]
        xs = {fj: np.mean([p[1][0] for p in pts if p[0] == fj]) for fj in {p[0] for p in pts}}
        print(f"{tag:7s} w {w:5.2f} d {r['delta_deg']:4.1f} k{r['k90']} held {r['held']!s:5s} "
              f"tilt {r['close']['die']['tilt_deg']:5.2f} rel_yaw {r['close']['die']['rel_yaw_deg']:6.2f} "
              f"nf {r['close']['nf']:4.2f} contact z {np.round(zs, 1).tolist()} x by pad "
              f"{ {k: round(float(v), 1) for k, v in xs.items()} }")
