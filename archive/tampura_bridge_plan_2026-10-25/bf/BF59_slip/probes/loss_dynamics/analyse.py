"""Summarise a loss_recorder carry.jsonl: per waypoint the pad forces, the
die's drift in the hand frame, the hand's acceleration; the first motion,
the first pad break and the loss step.  Usage: python analyse.py carry.jsonl"""
import json
import math
import sys

import numpy as np

DT = 1 / 240


def qang(q):
    w = min(1.0, abs(q[3]))
    return math.degrees(2 * math.acos(w))


def qmul(a, b):
    x1, y1, z1, w1 = a
    x2, y2, z2, w2 = b
    return [w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2]


def qinv(q):
    return [-q[0], -q[1], -q[2], q[3]]


def main(path):
    rows = [json.loads(l) for l in open(path)]
    ev = [r for r in rows if r['kind'] != 's']
    st = [r for r in rows if r['kind'] == 's']
    for r in ev:
        if r['kind'] in ('pick_start', 'pick_done', 'goal_check', 'hold_done', 'end'):
            print('EVENT', r)
    phases = [r for r in ev if r['kind'] == 'phase' and r['carrying']]
    for r in phases:
        print('PHASE', r['step'], r['label'])
    wps = [r for r in ev if r['kind'] == 'wp']
    for r in wps:
        print('WP', r['step'], r['wp'], 'settle', r['settle'], 'max|dq|',
              max(abs(x) for x in r['dq']))
    done = [r for r in ev if r['kind'] == 'pick_done']
    if not done:
        print('no pick_done'); return
    s0 = done[-1]['step']
    ref = next(r for r in st if r['step'] == s0)
    rp0, rq0 = np.array(ref['rel_p']), ref['rel_q']
    print(f"reference (post-lift, step {s0}): rel_p mm {ref['rel_p']}, "
          f"pads {[(k, v['n'], v['nf']) for k, v in ref['pads'].items()]}, "
          f"fingers mm {ref['fing']}")
    prev_v = None
    first_motion = first_break = loss = None
    groups = {}
    for r in st:
        if r['step'] <= s0:
            continue
        d = float(np.linalg.norm(np.array(r['rel_p']) - rp0))
        a = qang(qmul(qinv(rq0), r['rel_q']))
        hv = np.array(r['hand_v'])
        acc = 0.0 if prev_v is None else float(np.linalg.norm(hv - prev_v) / DT)
        prev_v = hv
        pads = r['pads']
        nfs = [pads[k]['nf'] for k in sorted(pads)]
        ns = [pads[k]['n'] for k in sorted(pads)]
        both = all(n > 0 for n in ns)
        if first_motion is None and (d > 0.5 or a > 1.0):
            first_motion = (r['step'], r['phase'][-40:], r['wp'], round(d, 3), round(a, 2))
        if first_break is None and not both:
            first_break = (r['step'], r['wp'], ns, nfs, round(d, 2), round(a, 1))
        if loss is None and not any(n > 0 for n in ns):
            loss = (r['step'], r['wp'], round(d, 2), round(a, 1), r['die_z'], r['other'])
        key = (r['phase'][-30:], str(r['wp']))
        g = groups.setdefault(key, dict(n=0, nf_min=[9e9, 9e9], d_max=0, a_max=0,
                                        acc_max=0, qd_max=0, both_all=True, first=r['step']))
        g['n'] += 1
        g['nf_min'] = [min(g['nf_min'][i], nfs[i]) for i in range(2)]
        g['d_max'] = max(g['d_max'], d)
        g['a_max'] = max(g['a_max'], a)
        g['acc_max'] = max(g['acc_max'], acc)
        g['qd_max'] = max(g['qd_max'], max(abs(x) for x in r['qd']))
        g['both_all'] &= both
    print(f"{'phase':32s} {'wp':5s} {'from':>5s} {'n':>4s} {'nfmin12':>14s} "
          f"{'drift':>6s} {'rot':>6s} {'acc':>6s} {'qd':>5s} both")
    for (ph, wp), g in groups.items():
        print(f"{ph:32s} {wp:5s} {g['first']:5d} {g['n']:4d} "
              f"{g['nf_min'][0]:6.2f},{g['nf_min'][1]:6.2f} {g['d_max']:6.2f} "
              f"{g['a_max']:6.1f} {g['acc_max']:6.2f} {g['qd_max']:5.2f} {g['both_all']}")
    print('FIRST_MOTION (step, phase, wp, drift mm, rot deg):', first_motion)
    print('FIRST_PAD_BREAK (step, wp, n per pad, nf per pad, drift, rot):', first_break)
    print('LOSS (no pad, step, wp, drift, rot, die_z, die touching):', loss)


if __name__ == '__main__':
    main(sys.argv[1])
