"""BF#59 grasp_wrist_home: read formula.json (probe_wrist_formula.py) and
print where the joint-7 prediction misses the IK, and every cell where the
choice by prediction (with the tie band) differs from the choice by IK.

  python analyse.py formula.json [tie band deg, default 20]
"""
import json
import math
import sys

TIE = math.radians(float(sys.argv[2]) if len(sys.argv) > 2 else 20.0)
LIM = 2.8973
res = json.load(open(sys.argv[1]))
for w in res:
    h = w['home_q7']
    print(f"== {w['world']} (home q7 {h:.3f})")
    big = []
    by_member = {'today': [], 'twin': []}
    for r in w['rows']:
        for tag in ('today', 'twin'):
            ik = r[tag]['ik_first']
            if ik is None:
                continue
            e = (ik - r[tag]['pred'] + math.pi) % (2 * math.pi) - math.pi
            clipped = abs(r[tag]['pred']) > LIM
            by_member[tag].append((abs(e), clipped))
            if abs(e) > math.radians(15):
                big.append((r['x'], r['y'], r['gy_deg'], tag, r[tag]['pred'], ik, round(math.degrees(e), 1), clipped))
    for tag, v in by_member.items():
        unclipped = sorted(math.degrees(e) for e, c in v if not c)
        clipped = sorted(math.degrees(e) for e, c in v if c)
        if unclipped:
            print(f"  {tag}: unclipped n={len(unclipped)} median {unclipped[len(unclipped)//2]:.1f} "
                  f"p95 {unclipped[int(0.95*(len(unclipped)-1))]:.1f} max {unclipped[-1]:.1f} deg; "
                  f"predicted past the limit n={len(clipped)}"
                  + (f" max err {clipped[-1]:.1f}" if clipped else ''))
    print(f"  errors > 15 deg: {len(big)}")
    for b in big[:12]:
        print('   ', b)
    # Choice with the tie band against the IK's joint 7 (first certified seed).
    n, agree, kept_in_band, bad = 0, 0, 0, []
    travel_today, travel_chosen = [], []
    for r in w['rows']:
        a, b = r['today'], r['twin']
        da = abs(min(max(a['pred'], -LIM), LIM) - h)
        db = abs(min(max(b['pred'], -LIM), LIM) - h)
        twin = da - db > 2 * TIE
        if not twin and da - db > 0:
            kept_in_band += 1
        if a['ik_first'] is None or b['ik_first'] is None:
            continue
        n += 1
        ia, ib = abs(a['ik_first'] - h), abs(b['ik_first'] - h)
        chosen = ib if twin else ia
        travel_today.append(ia)
        travel_chosen.append(chosen)
        if chosen <= min(ia, ib) + 1e-9:
            agree += 1
        else:
            bad.append((r['x'], r['y'], r['gy_deg'], round(math.degrees(ia), 1), round(math.degrees(ib), 1), twin))
    print(f"  choice (tie band {math.degrees(TIE):.0f} deg) picks the IK-nearer member in {agree}/{n} cells "
          f"(kept today's inside the band: {kept_in_band}); misses (x, y, yaw, |dq7| today, twin deg, twin?):")
    for b in bad:
        print('   ', b)
    # The clip: today's member and the chosen one, IK at the joint-7 limit
    # or no IK at all (every cell, not only those where both have IK).
    lim_t = lim_c = none_t = none_c = 0
    for r in w['rows']:
        a, b = r['today'], r['twin']
        da = abs(min(max(a['pred'], -LIM), LIM) - h)
        db = abs(min(max(b['pred'], -LIM), LIM) - h)
        ch = b if da - db > 2 * TIE else a
        lim_t += int(a['ik_first'] is not None and abs(a['ik_first']) >= 2.89)
        lim_c += int(ch['ik_first'] is not None and abs(ch['ik_first']) >= 2.89)
        none_t += int(a['ik_first'] is None)
        none_c += int(ch['ik_first'] is None)
    print(f"  of {len(w['rows'])} cells: IK at the joint-7 limit today {lim_t}, chosen {lim_c}; "
          f"no IK today {none_t}, chosen {none_c}")
    worse = [math.degrees(c - t) for c, t in zip(travel_chosen, travel_today) if c > t + 1e-9]
    print(f"  chosen member farther than today's in {len(worse)} cells, by at most "
          f"{max(worse) if worse else 0:.1f} deg; median |dq7| today "
          f"{math.degrees(sorted(travel_today)[len(travel_today)//2]):.0f} deg, chosen "
          f"{math.degrees(sorted(travel_chosen)[len(travel_chosen)//2]):.0f} deg")
