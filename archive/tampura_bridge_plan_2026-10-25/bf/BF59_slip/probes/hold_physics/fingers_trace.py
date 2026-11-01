"""Finger joints, pad forces and contact points (die frame) of a loss_recorder
carry.jsonl from the pick start: every 10th step, plus every step where the
mean finger position changes by more than 0.2 mm."""
import json
import sys

prev = None
for line in open(sys.argv[1]):
    d = json.loads(line)
    if d.get('kind') != 's':
        if d.get('kind') in ('pick_done', 'goal_check'):
            print(d)
        continue
    f = d['fing']
    m = sum(f) / 2
    if d['step'] % 10 == 0 or prev is None or abs(m - prev) > 0.2:
        pads = {k: (v['n'], round(v['nf'], 2), v['pts'][:2]) for k, v in d['pads'].items()}
        print(d['step'], d['wp'], 'fing', f, 'pads', pads, 'rel_p', d['rel_p'], 'die_z', d['die_z'])
    prev = m
