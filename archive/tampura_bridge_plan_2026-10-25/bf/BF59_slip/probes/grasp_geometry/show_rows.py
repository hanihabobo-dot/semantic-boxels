"""Print a probe JSON's rows with their contact geometry (analysis helper)."""
import json
import sys

d = json.load(open(sys.argv[1]))
full = len(sys.argv) > 2 and sys.argv[2] == 'full'
for r in d['rows']:
    if 'close' not in r:
        print('no close', r)
        continue
    print(f"cell {r['cell']} k{r['k90']} dx {r['dx_mm']:.0f} dy {r['dy_mm']:.0f} "
          f"delta {r['delta_deg']}: ee_z {r.get('ee_z_mm')} contact_z {r['contact_z_mm']} "
          f"pre {r['pre_close']['rel_yaw_deg']} half {r['close']['half_mm']} "
          f"nf {r['close']['nf']} closed rel {r['close']['die']['rel_yaw_deg']} "
          f"tilt {r['close']['die']['tilt_deg']} held {r.get('held')} "
          f"nfmin {r.get('nf_min')} range {r.get('rel_yaw_range')} tiltmax {r.get('tilt_max')} "
          f"lost {r.get('lost')}")
    if full:
        for k in ('close', 'after_lift'):
            if k in r:
                for fj, pts in r[k]['contacts'].items():
                    print(f"   {k} pad {fj}: " + '; '.join(
                        f"{q['xyz_mm']} nf {q['nf']}" for q in pts))
