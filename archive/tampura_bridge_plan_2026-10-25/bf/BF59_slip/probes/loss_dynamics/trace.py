"""Step trace of a carry: every k-th step after the pick (and every step in
[a, b] if given): wp, pad n and force, drift, rotation angle and axis (hand
frame), the pads' contact centroids in the die frame (mm), hand speed and
acceleration.  Usage: python trace.py carry.jsonl [k] [a b]"""
import json
import sys

import numpy as np
from analyse import qang, qinv, qmul

DT = 1 / 240


def axis(q):
    v = np.array(q[:3])
    n = np.linalg.norm(v)
    return (v / n).round(2).tolist() if n > 1e-9 else [0, 0, 0]


def main(path, k=10, a=None, b=None):
    rows = [json.loads(l) for l in open(path)]
    s0 = [r for r in rows if r['kind'] == 'pick_done'][-1]['step']
    st = [r for r in rows if r['kind'] == 's' and r['step'] >= s0]
    ref = st[0]
    prev = None
    for r in st:
        hv = np.array(r['hand_v'])
        acc = 0.0 if prev is None else float(np.linalg.norm(hv - prev) / DT)
        prev = hv
        show = (r['step'] - s0) % k == 0 or (a is not None and a <= r['step'] <= b)
        if not show:
            continue
        dq = qmul(qinv(ref['rel_q']), r['rel_q'])
        d = np.linalg.norm(np.array(r['rel_p']) - np.array(ref['rel_p']))
        cents = []
        for key in sorted(r['pads']):
            pts = r['pads'][key]['pts']
            cents.append(np.mean(pts, axis=0).round(1).tolist() if pts else None)
        print(f"{r['step']:5d} wp {str(r['wp']):5s} n {[r['pads'][x]['n'] for x in sorted(r['pads'])]} "
              f"nf {[round(r['pads'][x]['nf'], 2) for x in sorted(r['pads'])]} "
              f"d {d:5.2f} rot {qang(dq):5.1f} ax {axis(dq)} "
              f"c {cents} |v| {np.linalg.norm(hv):.3f} acc {acc:6.1f} "
              f"fing {r['fing']} oth {r['other']} z {r['die_z']}")


if __name__ == '__main__':
    args = sys.argv[1:]
    main(args[0], int(args[1]) if len(args) > 1 else 10,
         int(args[2]) if len(args) > 2 else None,
         int(args[3]) if len(args) > 3 else None)
