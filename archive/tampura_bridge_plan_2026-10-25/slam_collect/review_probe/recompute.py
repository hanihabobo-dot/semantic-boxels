"""Reviewer's independent recount of the author's probe outputs (read only).

Reads ../probe/out/*.json (the author's files, never written) and prints the numbers
ARGUMENT.md quotes, computed without p2_summarize.py. Standard library only.
Usage: python3 recompute.py > out/recompute.txt
"""
import glob
import json
import math
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'probe', 'out')
G = 0.98


def load(name):
    with open(os.path.join(SRC, name)) as f:
        return json.load(f)


def se_p(xs):
    return st.pstdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else 0.0


def se_s(xs):
    return st.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else 0.0


def has_coll(atoms):
    return any(a == 'in_collision' or a.startswith('in_collision(') for a in atoms)


def med(xs):
    return st.median(xs) if xs else None


print('=== A. scripted rules on their belief (3.5 table) ===')
for fn in sorted(glob.glob(os.path.join(SRC, 'policies_*.json'))):
    base = os.path.basename(fn)
    if 'S0_S1_S2_S3' in base:
        continue
    rows = json.load(open(fn))
    n = len(rows)
    succ = [r for r in rows if r['success_belief']]
    ret = [r['return'] for r in rows]
    world = sum(1 for r in rows if r['world_success'])
    steps = [r['steps_to_success'] for r in succ]
    # episodes whose belief ever held in_collision; was the true robot in collision at that first step?
    ep = true_first = phantom = 0
    for r in rows:
        for e in r['log']:
            if has_coll(e.get('atoms', [])):
                ep += 1
                if e.get('obs_collision'):
                    true_first += 1
                else:
                    phantom += 1
                break
    true_coll_end = sum(1 for r in rows if r['world_collision'])
    b_only = sum(1 for r in rows if r['success_belief'] and not r['world_success'])
    w_only = sum(1 for r in rows if r['world_success'] and not r['success_belief'])
    seeds = sorted({r['seed'] for r in rows})
    zero = [s for s in seeds if not any(r['success_belief'] for r in rows if r['seed'] == s)]
    zero_world = [s for s in seeds if not any(r['world_success'] for r in rows if r['seed'] == s)]
    errs = sum(1 for r in rows if r.get('error'))
    print(f"{base}: n {n} success {len(succ)}/{n} return {st.mean(ret):.3f} se_pop {se_p(ret):.3f} se_samp {se_s(ret):.3f}"
          f" | world_end {world}/{n} | median steps {med(steps)} | in_collision episodes {ep} (true at first {true_first},"
          f" particle only {phantom}) | true collision at end {true_coll_end} | belief only {b_only} world only {w_only}"
          f" | seeds never won (belief) {zero} | seeds never won (world) {zero_world} | errors {errs}")

print()
print('=== B. two beliefs (3.6 table) ===')
for fn in sorted(glob.glob(os.path.join(SRC, 'twobelief_*.json'))):
    base = os.path.basename(fn)
    rows = json.load(open(fn))
    n = len(rows)
    rs = [r for r in rows if r['replica_success']]
    rret = [r['replica_return'] for r in rows]
    wever = [r for r in rows if r['world_first_steps'] is not None]
    wend = [r for r in rows if r['world_success_end']]
    wret = [r['world_return'] for r in rows]

    def stable_first(r):
        w = [e.get('world', False) for e in r['log'] if not e.get('inapplicable')]
        if not w or not w[-1]:
            return None
        k = len(w)
        while k > 0 and w[k - 1]:
            k -= 1
        return k + 1
    sf = [stable_first(r) for r in rows]
    sret = [G ** s if s else 0.0 for s in sf]
    tcoll = sum(1 for r in rows if r['world_collision'])
    w_only = sum(1 for r in rows if r['world_first_steps'] is not None and not r['replica_success'])
    r_only = sum(1 for r in rows if r['replica_success'] and r['world_first_steps'] is None)
    w_only_end = sum(1 for r in rows if r['world_success_end'] and not r['replica_success'])
    fails = [r for r in rows if not r['world_success_end']]
    false_stop = [r for r in fails if r['acting_done_step'] is not None]
    stopped = sum(1 for r in rows if r['acting_done_step'] is not None)
    stopped_w = sum(1 for r in rows if r['acting_done_step'] is not None and r['world_success_end'])
    never_stop = [r for r in rows if r['acting_done_step'] is None]
    never_stop_tc = sum(1 for r in never_stop if r['world_collision'])
    rc_end = [r for r in rows if r['replica_in_collision_end']]
    rc_end_true = sum(1 for r in rc_end if r['world_collision'])
    lost = sum(1 for r in rows if r['world_first_steps'] is not None and not r['world_success_end'])
    ws = [r['world_first_steps'] for r in wever]
    per = {s: sum(1 for r in rows if r['seed'] == s and r['world_success_end']) for s in (5, 6, 10, 102, 106, 112)
           if any(r['seed'] == s for r in rows)}
    errs = sum(1 for r in rows if r.get('error'))
    print(f"{base}: n {n} | replica success {len(rs)}/{n} return {st.mean(rret):.3f} se_pop {se_p(rret):.3f}"
          f" | world ever {len(wever)} end {len(wend)} return(first) {st.mean(wret):.3f} se_pop {se_p(wret):.3f}"
          f" return(stable) {st.mean(sret):.3f} | median world steps {med(ws)} | true collisions {tcoll}"
          f" | world only {w_only} (end-based {w_only_end}) replica only {r_only} | held then lost {lost}"
          f" | world failures {len(fails)} of which agent stopped (false stop) {len(false_stop)}"
          f" | stopped {stopped} (world true {stopped_w}); never stopped {len(never_stop)} (true collision {never_stop_tc})"
          f" | replica in_collision at end {len(rc_end)} (true collision {rc_end_true}) | world wins on tight seeds {per}"
          f" | errors {errs}")

print()
print('=== C. controllers (ctrl.json) ===')
rows = load('ctrl.json')
pick = [p[1] for r in rows for p in r['pick_from_start']]
place = [p[1] for r in rows for p in r['place_from_target']]
look = [p[1] for r in rows for p in r['look_from_start'] if p[1] is not None]
lookf = sum(1 for r in rows for p in r['look_from_start'] if p[1] is None)
tog = [r['to_goal_from_start'] for r in rows if r['to_goal_from_start'] is not None]
secs = [p[2] for r in rows for p in r['pick_from_start'] + r['place_from_target']]
hits = sum(c['in_corner_region_of_10'] for r in rows for c in r['corner_from_start'])
tot = 10 * sum(len(r['corner_from_start']) for r in rows)
prims = sorted({c['primitives'] for r in rows for c in r['corner_from_start']})
print('pick from start: median', med(pick), 'min', min(pick), 'max', max(pick), 'n', len(pick))
print('place target->goal: median', med(place), 'min', min(place), 'max', max(place), 'n', len(place))
print('look from start: median', med(look), 'min', min(look), 'max', max(look), 'n', len(look), 'rrt failures', lookf)
print('move_to goal from start: median', med(tog), 'min', min(tog), 'max', max(tog), 'n', len(tog))
print('controller seconds pick/place: median', med(secs))
print('move_corner from start in corner:', hits, 'of', tot, 'primitive counts', prims)
ends = {}
for r in rows:
    for c in r['corner_from_start']:
        ends.setdefault(tuple(c['corner_xy']), set()).add(tuple(c['noise_free_end']))
for k, v in ends.items():
    print('  corner', k, 'distinct noise-free ends over 20 seeds:', sorted(v)[:5], 'count', len(v))

print()
print('=== D. corner.json ===')
rows = load('corner.json')
nf = sum(sum(r['noise_free_in_corner'].values()) for r in rows)
nz = sum(sum(r['noisy_in_corner'].values()) for r in rows)
tot = sum(r['starts'] * len(r['noise_free_in_corner']) for r in rows)
print('noise-free', nf, 'noisy', nz, 'of', tot)

print()
print('=== E. maps.json (slam_collect) ===')
maps = [m for m in load('maps.json') if m['task'] == 'slam_collect']
ds = [t['d_start'] for m in maps for t in m['targets']]
dg = [t['d_goal'] for m in maps for t in m['targets']]
db = [t['d_nearest_beacon'] for m in maps for t in m['targets']]
gb = [m['goal_nearest_beacon'][1] for m in maps]
print('target d_start median', med(ds), 'min', min(ds), 'max', max(ds))
print('target d_goal median', med(dg), 'min', min(dg), 'max', max(dg))
print('target to nearest beacon median', med(db), 'min', min(db), 'max', max(db))
print('goal to nearest beacon median', med(gb), 'min', min(gb), 'max', max(gb))
with_ti = [m['seed'] for m in maps if any(a.startswith('target_in') for a in m['abstract_b0'])]
print('seeds with a target_in atom at t=0:', len(with_ti), with_ti)
print('regions per seed:', sorted({len(m['regions']) for m in maps}), 'names seed 0:', maps[0]['regions'])
for task in ('slam_collect', 'slam_collect_simple', 'slam_collect_custom'):
    sub = [m for m in load('maps.json') if m['task'] == task]
    print(task, 'signatures', min(m['signatures_distinct'] for m in sub), max(m['signatures_distinct'] for m in sub),
          'components', min(m['signature_components'] for m in sub), max(m['signature_components'] for m in sub),
          'obstacles', sorted({m['n_obstacles'] for m in sub}), 'regions', sorted({len(m['regions']) for m in sub}),
          'targets', sorted({m['n_targets'] for m in sub}))


def rect_dist(px, py, ox, oy, th, w, h):
    c, s = math.cos(th), math.sin(th)
    dx, dy = px - ox, py - oy
    lx, ly = c * dx + s * dy, -s * dx + c * dy
    return math.hypot(max(abs(lx) - w / 2, 0), max(abs(ly) - h / 2, 0))


print('clearances (centre to nearest obstacle rectangle):')
for m in maps:
    if m['seed'] in (5, 6, 10):
        cg = min(rect_dist(8.0, 8.0, *o) for o in m['obstacles'])
        ct = [round(min(rect_dist(t['xy'][0], t['xy'][1], *o) for o in m['obstacles']), 3) for t in m['targets']]
        print('  seed', m['seed'], 'goal', round(cg, 3), 'targets', ct)
allc = []
for m in maps:
    cg = min(rect_dist(8.0, 8.0, *o) for o in m['obstacles'])
    ct = [min(rect_dist(t['xy'][0], t['xy'][1], *o) for o in m['obstacles']) for t in m['targets']]
    allc.append((m['seed'], round(cg, 2), [round(c, 2) for c in ct], min([cg] + ct)))
tight = [(s, g, t) for s, g, t, mn in allc if mn < 0.7]
print('seeds with goal or a target within 0.7 m of an obstacle:', len(tight), tight)

print()
print('=== F. boxes.json ===')
rows = load('boxes.json')
for k in ('arrangement_cells', 'merged_boxes', 'free_boxes', 'plain_free_boxes', 'distinct_signatures'):
    xs = [r[k] for r in rows]
    print(k, 'min', min(xs), 'median', med(xs), 'max', max(xs))

print()
print('=== G. variance.json ===')
v = load('variance.json')
for name, rows in v.items():
    print(name, [(r['k'], r['p_known_pose']) for r in rows])

print()
print('=== H. primitives per executed move in the scripted logs (S0..S5, seeds 0..19) ===')
pr = []
for fn in sorted(glob.glob(os.path.join(SRC, 'policies_S*.json'))):
    if 'S0_S1' in fn or 'seeds100' in fn:
        continue
    for r in json.load(open(fn)):
        pr += [e['primitives'] for e in r['log'] if e.get('primitives')]
print('n', len(pr), 'median', med(pr), 'mean', round(st.mean(pr), 2))
