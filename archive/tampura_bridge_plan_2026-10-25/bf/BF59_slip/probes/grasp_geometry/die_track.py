"""The die's recorded truth (print-only diagnostics in eye.jsonl) at every
eye record of an episode: tag, true position, true AABB side, tilt."""
import json
import sys

for line in open(sys.argv[1]):
    r = json.loads(line)
    for o in r.get('objects', []):
        if o.get('name') != 'dice':
            continue
        lo, hi = o['true_aabb']
        print(f"k {r['k']:3d} {r['tag'][:60]:60s} held {r.get('held')!s:5s} "
              f"pos {o['true_pos']} aabb {round(1e3 * (hi[0] - lo[0]), 1)} x "
              f"{round(1e3 * (hi[1] - lo[1]), 1)} mm tilt {o.get('tilt_deg')} "
              f"fingers {r['robot'].get('fingers')}")
