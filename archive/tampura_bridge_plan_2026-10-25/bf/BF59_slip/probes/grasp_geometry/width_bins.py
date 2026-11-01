"""Hold rate by measured half-width bin (the eval's only geometric reading)
and by close force, over probe JSONs of the die."""
import json
import sys
from collections import defaultdict

bins = defaultdict(lambda: [0, 0])
fbins = defaultdict(lambda: [0, 0])
for f in sys.argv[1:]:
    d = json.load(open(f))
    if d['args'].get('payload', 'dice') != 'dice':
        continue
    for r in d['rows']:
        if not r.get('grip'):
            continue
        w = r['close']['half_mm']
        b = ('a <10.15' if w < 10.15 else 'b 10.15-10.45' if w < 10.45 else
             'c 10.45-10.75' if w < 10.75 else 'd 10.75-12.0' if w < 12.0 else 'e >=12 (edge)')
        bins[b][0] += 1
        bins[b][1] += r['held']
        nf = r['close']['nf']
        fb = 'nf <2' if nf < 2 else 'nf 2-3' if nf < 3 else 'nf 3-4' if nf < 4 else 'nf >=4'
        key = ('edge ' if w >= 12.0 else 'face ') + fb
        fbins[key][0] += 1
        fbins[key][1] += r['held']
for b in sorted(bins):
    n, h = bins[b]
    print(f"{b:14s} n={n:4d} held={h:4d} ({100 * h / n:.0f} %)")
for b in sorted(fbins):
    n, h = fbins[b]
    print(f"{b:14s} n={n:4d} held={h:4d} ({100 * h / n:.0f} %)")
