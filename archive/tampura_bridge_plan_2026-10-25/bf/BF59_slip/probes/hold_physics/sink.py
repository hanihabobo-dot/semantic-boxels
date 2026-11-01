"""How far the fingers close past the measured width in the held trials at home:
2 x half_mm minus (q1 + q2) at home, the pads' total sink into the body under
the hold (the mean of the two fingers hides it when the body slides off centre
between force-limited fingers); and the off-centre shift (q1 - q2) / 2."""
import json
import sys

import numpy as np

for path in sys.argv[1:]:
    d = json.load(open(path))
    rows = [r for r in d['rows'] if r.get('grip') and r['held'] and r.get('finger_home_mm')]
    if not rows:
        continue
    s = [2 * r['half_mm'] - sum(r['finger_home_mm']) for r in rows]
    off = [abs(r['finger_home_mm'][0] - r['finger_home_mm'][1]) / 2 for r in rows]
    print(f"{d['lever']:>18s} {d['summary'].get('body'):>10s} held {len(rows):3d}: total sink past the measured "
          f"width at home median {np.median(s):.2f} mm (min {np.min(s):.2f}, max {np.max(s):.2f}); "
          f"off-centre median {np.median(off):.2f} mm; nf_home med {np.median([r['nf_home'] for r in rows]):.1f} N")
