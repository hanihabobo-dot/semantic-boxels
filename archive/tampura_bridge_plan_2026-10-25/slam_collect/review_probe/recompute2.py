"""Reviewer's second recount (read only): the single-episode claims of ARGUMENT.md 3.5 to 4.6,
the t = 0 target_in atoms per seed, the hop ratio and episode times. Standard library only.
Usage: python3 recompute2.py > out/recompute2.txt
"""
import glob
import json
import math
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'probe', 'out')


def load(name):
    with open(os.path.join(SRC, name)) as f:
        return json.load(f)


def ep(rows, seed, rep):
    for r in rows:
        if r['seed'] == seed and r['rep'] == rep:
            return r
    return None


print('=== t = 0 target_in atoms per seed (maps.json, slam_collect) ===')
maps = [m for m in load('maps.json') if m['task'] == 'slam_collect']
n_atoms = 0
for m in maps:
    ti = [a for a in m['abstract_b0'] if a.startswith('target_in')]
    n_atoms += len(ti)
    if ti:
        print('seed', m['seed'], ti)
print('seeds with one or more:', sum(1 for m in maps if any(a.startswith('target_in') for a in m['abstract_b0'])),
      'atoms in all:', n_atoms)

print()
print('=== hop ratio: primitives / (Chebyshev distance / 0.2) from ctrl.json ===')
ctrl = load('ctrl.json')
mp = {m['seed']: m for m in maps}
rp, rg = [], []
for r in ctrl:
    tx = {t['name']: t['xy'] for t in mp[r['seed']]['targets']}
    for name, n, _ in r['pick_from_start']:
        s = max(abs(tx[name][0] - 1.0), abs(tx[name][1] - 1.0)) / 0.2
        if s > 3:
            rp.append(n / s)
    for name, n, _ in r['place_from_target']:
        s = max(abs(tx[name][0] - 8.0), abs(tx[name][1] - 8.0)) / 0.2
        if s > 3:
            rg.append(n / s)
print('pick from start: median', round(st.median(rp), 3), 'max', round(max(rp), 3), 'n', len(rp))
print('place to goal:   median', round(st.median(rg), 3), 'max', round(max(rg), 3), 'n', len(rg))
print('both:            median', round(st.median(rp + rg), 3), 'max', round(max(rp + rg), 3))

print()
print('=== episode seconds (median per file) ===')
for fn in sorted(glob.glob(os.path.join(SRC, 'policies_*.json')) + glob.glob(os.path.join(SRC, 'twobelief_*.json'))):
    rows = json.load(open(fn))
    secs = [r.get('seconds') for r in rows if r.get('seconds') is not None]
    if secs:
        print(os.path.basename(fn), 'median', st.median(secs), 'max', max(secs))

print()
print('=== single-episode claims ===')
S0 = load('policies_S0_none.json')
r = ep(S0, 1, 0)
picks = [(e['action'], e.get('primitives'), e.get('err_mean_true'), e.get('obs_holding')) for e in r['log']]
print('S0 seed 1 rep 0:', picks)

S4 = load('policies_S4_risk.json')
r = ep(S4, 6, 0)
print('S4 seed 6 rep 0:', [(e['action'], e.get('primitives'), e.get('obs_collision'), 'in_collision' in e.get('atoms', []))
                           for e in r['log']][:8])
r = ep(S4, 8, 1)
print('S4 seed 8 rep 1: belief success', r['success_belief'], 'world targets in goal', r['world_targets_in_goal'],
      'world collision', r['world_collision'])
print('   last steps:', [(e['action'], e.get('obs_collision'), 'in_collision' in e.get('atoms', [])) for e in r['log']][-6:])

S2o = load('twobelief_S2o.json')
for (s, k) in ((13, 0), (19, 2), (2, 2), (4, 2)):
    r = ep(S2o, s, k)
    print(f'S2o seed {s} rep {k}: world_end {r["world_success_end"]} stopped {r["acting_done_step"]}')
    for e in r['log']:
        if e['action'] != 'no-op()':
            print('    ', e['step'], e['action'], 'prims', e.get('primitives'), 'var', e.get('acting_var'),
                  'err', e.get('err_mean_true'), 'held', e.get('obs_holding'), 'coll', e.get('obs_collision'),
                  'removed', e.get('removed_by_failed_pick'), 'world', e.get('world'))

print()
print('=== S3 vs S4 on their belief: what the obstacle term adds ===')
for name in ('policies_S3_predictive.json', 'policies_S4_risk.json'):
    rows = load(name)
    print(name, 'belief', sum(r['success_belief'] for r in rows), 'world', sum(r['world_success'] for r in rows),
          'looks', sum(r['looks'] for r in rows), 'return', round(st.mean(r['return'] for r in rows), 3))
s3 = {(r['seed'], r['rep']): r for r in load('policies_S3_predictive.json')}
s4 = {(r['seed'], r['rep']): r for r in load('policies_S4_risk.json')}
both = sum(1 for k in s3 if s3[k]['world_success'] and s4[k]['world_success'])
only3 = sum(1 for k in s3 if s3[k]['world_success'] and not s4[k]['world_success'])
only4 = sum(1 for k in s3 if s4[k]['world_success'] and not s3[k]['world_success'])
print('paired by seed and rep, world: both', both, 'S3 only', only3, 'S4 only', only4)

print()
print('=== paired S2o vs S4o (world at end), seeds 0..19 and 100..119 ===')
for a, b in (('twobelief_S2o.json', 'twobelief_S4o.json'), ('twobelief_S2o_seeds100.json', 'twobelief_S4o_seeds100.json')):
    A = {(r['seed'], r['rep']): r['world_success_end'] for r in load(a)}
    B = {(r['seed'], r['rep']): r['world_success_end'] for r in load(b)}
    n01 = sum(1 for k in A if not A[k] and B[k])
    n10 = sum(1 for k in A if A[k] and not B[k])
    # exact two-sided McNemar (binomial) p value on the discordant pairs
    n = n01 + n10
    kmin = min(n01, n10)
    p = sum(math.comb(n, i) for i in range(0, kmin + 1)) / 2 ** n * 2 if n else 1.0
    print(a, 'vs', b, ': S4o only', n01, 'S2o only', n10, 'exact McNemar p', round(min(p, 1.0), 4))
    # per seed (3 or 2 reps) aggregated: seeds where S4o wins more episodes
    seeds = sorted({k[0] for k in A})
    better = sum(1 for s in seeds if sum(B[k] for k in B if k[0] == s) > sum(A[k] for k in A if k[0] == s))
    worse = sum(1 for s in seeds if sum(B[k] for k in B if k[0] == s) < sum(A[k] for k in A if k[0] == s))
    print('    seeds where S4o wins more episodes', better, 'fewer', worse, 'of', len(seeds))
