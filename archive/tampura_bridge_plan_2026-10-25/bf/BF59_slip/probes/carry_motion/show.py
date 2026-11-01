"""Print a trial's trace compactly: python show.py <json> [trial] [every]"""
import json
import sys

d = json.load(open(sys.argv[1]))
k = int(sys.argv[2]) if len(sys.argv) > 2 else 1
every = int(sys.argv[3]) if len(sys.argv) > 3 else 6
r = [x for x in d['rows'] if x.get('trial') == k][0]
print({kk: v for kk, v in r.items() if kk != 'rows'})
prev = None
for row in r.get('rows', []):
    mark = row['ph'] != prev
    prev = row['ph']
    if mark or row['n'] % every == 0 or row['la'] > 20 or row['f1'] + row['f2'] < 0.5:
        print(f"{row['n']:4d} {row['ph']:8s} f={row['f1']:6.2f}/{row['f2']:6.2f} both={int(row['both'])} "
              f"off={row['off']:5.2f}mm rot={row['rot']:5.2f} la={row['la']:6.1f} aa={row['aa']:6.1f} "
              f"qa={row['qa']:6.1f} v={row['v']:.3f} w={row['w']:.3f} qd={row['qdmax']:.3f} "
              f"tilt={row['tilt']:4.1f} appr={row['appr']:4.1f}")
