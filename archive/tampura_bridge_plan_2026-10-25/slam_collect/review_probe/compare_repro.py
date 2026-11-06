"""Reviewer: compare the reproduction (review_probe/out/twobelief_<rule>.json) with the author's
files (../probe/out/twobelief_<rule>.json), episode by episode. Read only; prints only.
Usage: python3 compare_repro.py S4o S2o
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KEYS = ['replica_success', 'replica_steps', 'world_first_steps', 'world_success_end', 'world_collision',
        'acting_done_step', 'looks', 'replica_in_collision_end']

for rule in sys.argv[1:]:
    mine = json.load(open(os.path.join(HERE, 'out', f'twobelief_{rule}.json')))
    theirs = json.load(open(os.path.join(HERE, '..', 'probe', 'out', f'twobelief_{rule}.json')))
    A = {(r['seed'], r['rep']): r for r in theirs}
    B = {(r['seed'], r['rep']): r for r in mine}
    same = diff = 0
    first = []
    for k in sorted(A):
        if k not in B:
            first.append((k, 'missing in reproduction'))
            diff += 1
            continue
        d = [x for x in KEYS if A[k].get(x) != B[k].get(x)]
        # the action sequence too
        aa = [e['action'] for e in A[k]['log']]
        bb = [e['action'] for e in B[k]['log']]
        if aa != bb:
            d.append('actions')
        # per-step state: primitives, true-pose error of the acting mean, acting variance, world flag
        for fld in ('primitives', 'err_mean_true', 'acting_var', 'world', 'replica_reward'):
            if [e.get(fld) for e in A[k]['log']] != [e.get(fld) for e in B[k]['log']]:
                d.append(fld)
        if d:
            diff += 1
            if len(first) < 8:
                first.append((k, d))
        else:
            same += 1
    print(rule, 'episodes identical', same, 'different', diff, first)
    for name, rows in (('author', theirs), ('review', mine)):
        n = len(rows)
        print('  ', name, 'n', n, 'replica success', sum(r['replica_success'] for r in rows),
              'world end', sum(r['world_success_end'] for r in rows),
              'true collisions', sum(r['world_collision'] for r in rows))
