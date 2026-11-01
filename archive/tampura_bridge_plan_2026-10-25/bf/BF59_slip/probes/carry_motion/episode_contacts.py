"""BF#47's question on the recorded episodes (loss_dynamics' runs, read
only): did the die or the hand's cargo touch any body other than the robot
between the post-lift (pick_done) and the first step with neither pad in
contact?  python episode_contacts.py <runs dir>"""
import json
import os
import sys
from collections import Counter

root = sys.argv[1]
for run in sorted(os.listdir(root)):
    f = os.path.join(root, run, 'carry.jsonl')
    if not os.path.exists(f):
        continue
    rows = [json.loads(l) for l in open(f)]
    pd = [r for r in rows if r['kind'] == 'pick_done']
    if not pd:
        continue
    s0 = pd[-1]['step']
    st = [r for r in rows if r['kind'] == 's' and r['step'] > s0]
    before, after, gone = Counter(), Counter(), None
    for r in st:
        none = not any(r['pads'][k]['n'] for k in r['pads'])
        if none and gone is None:
            gone = r['step']
        for b in r.get('other', []):
            (after if gone is not None else before)[b] += 1
    print(f"{run:12s} carry steps {len(st)}, pads gone at {gone}; die touching other bodies "
          f"while held: {dict(before) or 'none'}; after: {dict(after) or 'none'}")
