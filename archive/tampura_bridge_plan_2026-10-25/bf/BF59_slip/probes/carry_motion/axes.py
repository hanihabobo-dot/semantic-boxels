"""Per trial: pick geometry (COM and contacts in the hand frame, mm) and the
axis of the die's rotation in the hand when it passes 5, 15 and 30 deg.
python axes.py <json> [lost|all]"""
import json
import sys

d = json.load(open(sys.argv[1]))
mode = sys.argv[2] if len(sys.argv) > 2 else 'lost'
for r in d['rows']:
    if not r.get('grip') or (mode == 'lost' and r['held']):
        continue
    rows = r.get('rows', [])
    marks = []
    for th in (5, 15, 30):
        for x in rows:
            if x['rot'] > th:
                marks.append(f"{th}deg {x['ph']}@{x['n']} ax={x['ax']} appr={x['appr']} f={x['f1']:.1f}/{x['f2']:.1f}")
                break
    cs = r.get('contacts', [])
    pads = {}
    for c in cs:
        pads.setdefault(c[0], []).append(c[1:4])
    span = {k: (min(v[2] for v in vs), max(v[2] for v in vs), len(vs)) for k, vs in
            ((k, [[None, None, z] for _, _, z in [(a[0], a[1], a[2]) for a in vs]]) for k, vs in pads.items())}
    print(f"t{r['trial']:3d} yaw={r['yaw']:+.2f} tilt={r['tilt']:.0f} held={int(r['held'])} rot_end={r['rot_end']} "
          f"com={r.get('com_hand_mm')} contacts z-range per pad (mm, n)={span}")
    for m in marks:
        print('     ', m)
