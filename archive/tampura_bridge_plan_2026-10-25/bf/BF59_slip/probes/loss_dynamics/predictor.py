"""The carry loss predictor from the robot's own senses only (finger joint
readback, pad contact count and normal force): one line per carry.
Usage: python predictor.py carry.jsonl [more.jsonl ...]"""
import json
import sys


def line(path, thr=0.05):
    rows = [json.loads(l) for l in open(path)]
    s0 = [r for r in rows if r['kind'] == 'pick_done'][-1]['step']
    goal = [r for r in rows if r['kind'] == 'goal_check']
    st = [r for r in rows if r['kind'] == 's' and r['step'] >= s0]
    w0 = sum(st[0]['fing']) / 2
    widen = -1e9
    widen_at = None
    first_thr = None
    zero = 0
    nf_min = 9e9
    loss = None
    for r in st[1:]:
        if loss is not None:
            break
        w = sum(r['fing']) / 2 - w0
        if w > widen:
            widen, widen_at = w, (r['step'], r['wp'])
        if first_thr is None and w > thr:
            first_thr = (r['step'], r['wp'])
        nfs = [r['pads'][k]['nf'] for k in sorted(r['pads'])]
        ns = [r['pads'][k]['n'] for k in sorted(r['pads'])]
        nf_min = min(nf_min, min(nfs))
        if min(nfs) < 0.05:
            zero += 1
        if not all(ns):
            loss = (r['step'], r['wp'])
    held = bool(goal and goal[-1]['ok'])
    return (f"{path.split('/')[-2]:14s} carry_grip: width0 {w0:.3f} mm, widen_max "
            f"{widen:+.3f} mm at {widen_at}, first widen>{thr} mm at {first_thr}, "
            f"nf_min {nf_min:.2f} N, zero-force steps {zero}, first pad break "
            f"{loss}, held at the goal {held}")


if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(line(p))
