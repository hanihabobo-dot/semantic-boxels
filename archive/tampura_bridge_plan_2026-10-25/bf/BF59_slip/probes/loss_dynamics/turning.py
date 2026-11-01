"""Where does the die turn?  Per carry: the share of the total in-hand
rotation that happens within 3 steps after a waypoint junction, against the
share of steps that are such steps; and the rotation rate against the
hand's angular acceleration (correlation), up to the first pad break.
Usage: python turning.py carry.jsonl [...]"""
import json
import sys

import numpy as np
from analyse import qang, qinv, qmul


def main(path):
    rows = [json.loads(l) for l in open(path)]
    s0 = [r for r in rows if r['kind'] == 'pick_done'][-1]['step']
    junctions = {r['step'] for r in rows if r['kind'] == 'wp'}
    st = [r for r in rows if r['kind'] == 's' and r['step'] >= s0]
    rates, accs, near = [], [], []
    prev = st[0]
    for r in st[1:]:
        if not all(r['pads'][k]['n'] for k in r['pads']):
            break
        dq = qang(qmul(qinv(prev['rel_q']), r['rel_q']))
        aw = np.linalg.norm(np.array(r['hand_w']) - np.array(prev['hand_w'])) * 240
        rates.append(dq)
        accs.append(aw)
        near.append(any(0 < r['step'] - j <= 3 for j in junctions))
        prev = r
    rates, accs, near = np.array(rates), np.array(accs), np.array(near)
    tot = rates.sum()
    print(f"{path.split('/')[-2]:8s} steps {len(rates)}, total turn {tot:6.1f} deg, "
          f"junction steps {near.mean() * 100:4.1f} % carry "
          f"{rates[near].sum() / tot * 100:4.1f} % of the turn; "
          f"corr(rate, |dw/dt|) {np.corrcoef(rates, accs)[0, 1]:+.2f}")


if __name__ == '__main__':
    for p in sys.argv[1:]:
        main(p)
