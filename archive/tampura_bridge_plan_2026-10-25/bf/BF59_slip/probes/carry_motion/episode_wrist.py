"""The wrist travel of the recorded episode carries (loss_dynamics' runs,
read only): per run, the summed waypoint dq per joint of the move home, the
pair count and the outcome.  python episode_wrist.py <runs dir>"""
import json
import os
import sys

import numpy as np

root = sys.argv[1]
for run in sorted(os.listdir(root)):
    f = os.path.join(root, run, 'carry.jsonl')
    if not os.path.exists(f):
        continue
    rows = [json.loads(l) for l in open(f)]
    wps = [r for r in rows if r['kind'] == 'wp']
    goal = [r for r in rows if r['kind'] == 'goal_check']
    if not wps:
        print(run, 'no carry')
        continue
    tot = np.sum([r['dq'] for r in wps], axis=0)
    print(f"{run:12s} pairs {len(wps)} goal {goal[-1]['ok'] if goal else None} "
          f"sum dq {np.round(tot, 3).tolist()} |dq7| {abs(tot[6]):.2f} rad "
          f"({np.degrees(abs(tot[6])):.0f} deg)")
