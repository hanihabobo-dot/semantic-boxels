"""Trace of the k-th lost (or held) trial: python trace.py <json> <k> <every> [held]"""
import json
import sys

d = json.load(open(sys.argv[1]))
k, every = int(sys.argv[2]), int(sys.argv[3])
want_held = len(sys.argv) > 4
rs = [x for x in d['rows'] if x.get('grip') and bool(x['held']) == want_held and x.get('rows')]
r = rs[k]
print('trial', r['trial'], 'yaw', r['yaw'], 'tilt', r['tilt'], 'cell', r['cell'], 'contacts', r.get('contacts'))
rows = r['rows']
prev_both = True
for x in rows:
    edge = prev_both and not x['both']
    prev_both = x['both']
    if x['n'] % every == 0 or edge:
        print(x['n'], x['ph'], 'f', x['f1'], x['f2'], 'both', int(x['both']), 'off', x['off'],
              'rot', x['rot'], 'ax', x['ax'], 'qd', x['qdmax'], 'w', x['w'], 'appr', x['appr'],
              'tilt', x['tilt'], '<-- pads lost' if edge else '')
