"""Per-trial table of one run: python losses.py out/b1_pipe.json [all]
For each trial: yaw, tilt, held, rot peak, where the die's rotation in the
hand first passed 15 deg and 45 deg (phase, step), the pad force then."""
import json
import sys

d = json.load(open(sys.argv[1]))
show_all = len(sys.argv) > 2
for r in d['rows']:
    if not r.get('grip'):
        continue
    if r['held'] and not show_all:
        continue
    rows = r.get('rows', [])
    def first(th):
        for x in rows:
            if x['rot'] > th:
                return f"{x['ph']}@{x['n']} f={x['f1']:.2f}/{x['f2']:.2f} appr={x['appr']} tilt={x['tilt']}"
        return '-'
    gone = '-'
    for x in rows:
        if not x['both'] and x['f1'] + x['f2'] == 0:
            gone = f"{x['ph']}@{x['n']}"
            break
    print(f"t{r['trial']:3d} cell={r['cell']} yaw={r['yaw']:+.2f} tilt={r['tilt']:.0f} held={int(r['held'])} "
          f"rot_peak={r['rot_peak']:6.1f} steps={r['move_steps']} | rot>15: {first(15)} | rot>45: {first(45)} | pads gone: {gone}")
