"""Held against lost by trial features: python corr.py <json>...
Prints medians of the peak pinch-axis tilt, the peak hand angular speed, the
peak approach tilt, the contact count, and the loss rate by pinch-tilt bin."""
import json
import sys

def med(xs):
    xs = sorted(xs)
    return round(xs[len(xs) // 2], 2) if xs else None

for f in sys.argv[1:]:
    d = json.load(open(f))
    rs = [r for r in d['rows'] if r.get('grip')]
    for r in rs:
        rows = r.get('rows', [])
        # features up to the first loss (or the whole carry)
        upto = rows
        for i, x in enumerate(rows):
            if not x['both']:
                upto = rows[:i + 1]
                break
        r['_tilt'] = max((x['tilt'] for x in upto), default=0)
        r['_w'] = max((x['w'] for x in upto), default=0)
        r['_nc'] = len(r.get('contacts', []))
    H = [r for r in rs if r['held']]
    L = [r for r in rs if not r['held']]
    print(f"{f.split('/')[-1]}: held {len(H)}/{len(rs)}")
    for k in ('_tilt', '_w', '_nc', 'tilt_peak', 'w_peak'):
        print(f"   {k:10s} held {med([r[k] for r in H])}  lost {med([r[k] for r in L])}")
    bins = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 90)]
    out = []
    for lo, hi in bins:
        b = [r for r in rs if lo <= r['tilt_peak'] < hi]
        if b:
            out.append(f"{lo}-{hi}deg: {sum(not r['held'] for r in b)}/{len(b)} lost")
    print('   by full-carry peak pinch tilt:', '; '.join(out))
    nb = {}
    for r in rs:
        nb.setdefault(r['_nc'], [0, 0])
        nb[r['_nc']][0] += (not r['held'])
        nb[r['_nc']][1] += 1
    print('   by pad contact points at the pinch:', {k: f"{v[0]}/{v[1]}" for k, v in sorted(nb.items())})
