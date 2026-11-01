"""Over the die carry of a loss_recorder carry.jsonl (after pick_done): the
fingers' off-centre shift |q1 - q2| / 2 (median, max) and their sum against
the post-lift sum (the pads' sink, positive = closed further)."""
import json
import sys

import numpy as np

for path in sys.argv[1:]:
    on, ref, off, sink = False, None, [], []
    for line in open(path):
        d = json.loads(line)
        if d.get('kind') == 'pick_done':
            on = True
            continue
        if on and d.get('kind') == 's':
            q1, q2 = d['fing']
            if ref is None:
                ref = q1 + q2
            off.append(abs(q1 - q2) / 2)
            sink.append(ref - (q1 + q2))
    print(f'{path}: {len(off)} carry steps, off-centre median {np.median(off):.3f} mm, max {np.max(off):.3f} mm; '
          f'sink against the post-lift width median {np.median(sink):.3f} mm, range {np.min(sink):.3f} to {np.max(sink):.3f} mm')
