"""Loss shapes per hp_probe output: for every lost trial the first 'lost' event
(a pad with no contact or the die 5 mm off its post-close place in the hand)
classified as (a) slip at low force (both pads < 1 N at the event) or (b) under
force; the rotation per hand axis; for the held trials the minimum pad force in
the carry and the steps with a pad at zero contacts; the loss by the die's yaw
offset against the pinch."""
import json
import sys

import numpy as np

for path in sys.argv[1:]:
    d = json.load(open(path))
    rows = [r for r in d['rows'] if r.get('grip')]
    lost = [r for r in rows if not r['held_after']]
    held = [r for r in rows if r['held_after']]
    a = [r for r in lost if r['lost'] and max(r['lost']['nf']) < 1.0]
    b = [r for r in lost if r['lost'] and max(r['lost']['nf']) >= 1.0]
    print(f"== {d['lever']} ({d['summary'].get('body', 'dice')}): {len(lost)}/{len(rows)} lost; "
          f"(a) low-force slip {len(a)}, (b) under force {len(b)}")
    if lost:
        ev = [r['lost'] for r in lost if r['lost']]
        print('   lost events: phase', {ph: sum(e['phase'] == ph for e in ev) for ph in ('lift', 'carry', 'hold', 'after')},
              ' rot about pinch at event med %.1f, other %.1f deg' % (
                  np.median([e['pinch_rot'] for e in ev]), np.median([e['other_rot'] for e in ev])))
    for name, grp in (('held', held), ('lost', lost)):
        if not grp:
            continue
        rx = np.array([r['max_rot_xyz'] for r in grp])
        print(f"   {name}: n {len(grp)}, max rot x/y(pinch)/z(approach) med {np.median(rx, 0).round(1).tolist()}, "
              f"nf_min_carry med {np.median([min(r['nf_min_carry']) for r in grp]):.2f}, "
              f"zero-contact steps med {np.median([r['flicker_steps'] for r in grp]):.0f}, "
              f"widen med {np.median([r.get('widen_max_mm', 0) for r in grp]):.3f} mm, "
              f"nf_max med {np.median([r.get('nf_max_carry', 0) for r in grp]):.2f} N, "
              f"tilt max med {np.median([r.get('tilt_max') or 0 for r in grp]):.1f} deg, "
              f"half med {np.median([r['half_mm'] for r in grp]):.2f}")
    yaw = np.array([abs(r['die_dyaw_deg']) for r in rows])
    los = np.array([not r['held_after'] for r in rows])
    for lo, hi in ((0, 3), (3, 6), (6, 10)):
        m = (yaw >= lo) & (yaw < hi)
        print(f"   |die yaw - grasp yaw| {lo}-{hi} deg: lost {int(los[m].sum())}/{int(m.sum())}")
