"""Summaries of the jam probe's out/<prefix>*.json: per file the releases,
the jams split light (pad force < 10 N after the last open) and deep, the
carry's slip and turn of the cup in the hand, the pads' deepest contact
during the place descent, and the turn of jammed against released trials.
  python analyse.py <out dir> [prefix]"""
import glob
import json
import os
import sys

import numpy as np

d = sys.argv[1]
pre = sys.argv[2] if len(sys.argv) > 2 else 'b1_'
allj, allr = [], []
for f in sorted(glob.glob(os.path.join(d, pre + '*.json'))):
    J = json.load(open(f))
    rows = [r for r in J['rows'] if 'released' in r]
    jam = [r for r in rows if not r['released']]
    deep = [r for r in jam if max(v[0] for v in r['attempts'][-1]['links'].values()) >= 10]
    turn = [r['carry_turn_deg'] for r in rows if r.get('carry_turn_deg') is not None]
    slip = [abs(r['carry_slip_mm'][2]) for r in rows if r.get('carry_slip_mm')]
    dmin = [min(x for x in r['descent_min_d'] if x is not None) for r in rows
            if any(x is not None for x in r['descent_min_d'])]
    allj += [r['carry_turn_deg'] for r in jam if r.get('carry_turn_deg') is not None]
    allr += [r['carry_turn_deg'] for r in rows if r['released'] and r.get('carry_turn_deg') is not None]
    print(f"{os.path.basename(f)[:-5]:<26} released {len(rows) - len(jam)}/{len(rows)} "
          f"jam light {len(jam) - len(deep)} deep {len(deep)} | carry turn med {np.median(turn):.2f} "
          f"max {max(turn):.2f} deg | carry |slip z| med {np.median(slip):.2f} max {max(slip):.2f} mm | "
          f"descent min pad d med {np.median(dmin):.2f} min {min(dmin):.2f} mm")
print(f"carry turn, jammed trials: median {np.median(allj):.2f} deg (n {len(allj)}); "
      f"released: median {np.median(allr):.2f} deg (n {len(allr)})")
