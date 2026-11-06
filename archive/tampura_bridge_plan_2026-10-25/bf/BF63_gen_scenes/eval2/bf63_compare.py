"""BF#63: run 2 (eval2, 2026-11-04, the job folders on the nodes' own
disks) beside run 1 (eval, 2026-11-03, with its slow hour 21:00 to 22:00,
BF#63 THE SLOW HOUR).  The runs are not pooled.  Printed: per (arm, scene,
repetition) counted in both runs, the same outcome or not; the pairs of
each run, run 1 also split by the slow hour and run 2 on the same split of
scene-repetitions; the speed of planning and of execution of both arms.
A run 1 run is in the slow hour when it overlaps 21:00 to 22:00, a pair
when either arm's run does (as bf63_window.py).
Usage: python -I bf63_compare.py <run 1 eval dir> <run 2 eval2 dir>"""
import datetime as dt
import glob
import json
import os
import statistics
import sys

here = os.path.dirname(os.path.abspath(__file__))
root = here
while not os.path.isfile(os.path.join(root, 'tools', 'gen_scene_eval.py')):
    root = os.path.dirname(root)
sys.path.insert(0, os.path.join(root, 'tools'))
from gen_scene_eval import mcnemar_exact, wilson  # noqa: E402

F = '%Y-%m-%d %H:%M:%S'
W0, W1 = dt.datetime(2026, 11, 3, 21, 0, 0), dt.datetime(2026, 11, 3, 22, 0, 0)


def load(ev, pat):
    rows = []
    for p in sorted(glob.glob(os.path.join(ev, pat, 'results.jsonl'))):
        rows += [json.loads(line) for line in open(p, encoding='utf-8') if line.strip()]
    final = {}
    for r in rows:
        k = (r['arm'], r['seed'], r['rep'])
        if k not in final or r['attempt'] >= final[k]['attempt']:
            final[k] = r
    return final


f1, f2 = load(sys.argv[1], '50630*'), load(sys.argv[2], '5084*')


def span(r):
    end = dt.datetime.strptime(r['finished'], F)
    return end - dt.timedelta(seconds=r['wall_s']), end


def slow(r):
    a, b = span(r)
    return a < W1 and b > W0


def pairs(f):
    return sorted((s, rp) for (a, s, rp), r in f.items() if a == 'O' and r['counts']
                  and f.get(('T', s, rp), {}).get('counts'))


def outcome(r):
    return 'success' if r['success'] else 'timeout' if r['timed_out'] else 'failure'


def report(name, f, keys):
    print(f"  {name}: {len(keys)} pairs")
    for arm in ('O', 'T'):
        rs = [f[(arm,) + k] for k in keys]
        n = sum(r['success'] for r in rs)
        lo, hi = wilson(n, len(rs)) if rs else (0, 0)
        print(f"    {arm}: {n}/{len(rs)} = {n / len(rs):.2f} [{lo:.2f}, {hi:.2f}], timeouts "
              f"{sum(r['timed_out'] for r in rs)}")
    b = sum(f[('O',) + k]['success'] and f[('T',) + k]['success'] for k in keys)
    o = sum(f[('O',) + k]['success'] and not f[('T',) + k]['success'] for k in keys)
    t = sum(f[('T',) + k]['success'] and not f[('O',) + k]['success'] for k in keys)
    print(f"    both {b}, only O {o}, only T {t}, neither {len(keys) - b - o - t}; "
          f"exact McNemar p = {mcnemar_exact(o, t):.3g}")


print('== the same outcome in both runs, per (arm, scene, repetition) counted in both')
for arm in ('O', 'T'):
    keys = sorted(k for k in f1 if k[0] == arm and f1[k]['counts'] and f2.get(k, {}).get('counts'))
    same = [k for k in keys if f1[k]['success'] == f2[k]['success']]
    out = [k for k in keys if not slow(f1[k])]
    same_out = [k for k in out if f1[k]['success'] == f2[k]['success']]
    ins = [k for k in keys if slow(f1[k])]
    same_in = [k for k in ins if f1[k]['success'] == f2[k]['success']]
    print(f"  {arm}: {len(same)} of {len(keys)} the same; run 1 outside the slow hour {len(same_out)} of "
          f"{len(out)}, inside it {len(same_in)} of {len(ins)}")
    for k in keys:
        if f1[k]['success'] != f2[k]['success']:
            print(f"     s{k[1]} r{k[2]}: run 1 {outcome(f1[k])} ({f1[k]['wall_s']:.0f} s"
                  f"{', in the slow hour' if slow(f1[k]) else ''}) -> run 2 {outcome(f2[k])} ({f2[k]['wall_s']:.0f} s)")

print('\n== the pairs')
p1, p2 = pairs(f1), pairs(f2)
k_in = {k for k in p1 if slow(f1[('O',) + k]) or slow(f1[('T',) + k])}
report('run 1, all', f1, p1)
report('run 1, outside the slow hour', f1, [k for k in p1 if k not in k_in])
report('run 1, inside the slow hour', f1, [k for k in p1 if k in k_in])
report('run 2, all', f2, p2)
report("run 2, the scene-repetitions that were run 1's pairs outside the slow hour", f2,
       [k for k in p2 if k in set(p1) - k_in])
report("run 2, the scene-repetitions that were run 1's pairs inside it", f2, [k for k in p2 if k in k_in])


def med(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return 'n/a'
    qs = statistics.quantiles(xs, n=4) if len(xs) > 1 else (xs[0],) * 3
    return f"{statistics.median(xs):7.2f} [{qs[0]:.2f}, {qs[2]:.2f}] (n {len(xs)})"


def o_speed(r):
    m = r['rec'].get('metrics') or {}
    calls, steps = m.get('plan_calls'), m.get('steps')
    return {'s per planning call': m['planning_s'] / calls if calls and m.get('planning_s') is not None else None,
            'first planning call s': m.get('planning_first_s'),
            'M8 build s': m.get('m8_build_s'),
            's per execution step': m['exec_s'] / steps if steps and m.get('exec_s') is not None else None,
            'pipeline wall s': m.get('wall_s')}


def t_speed(r):
    rec = r['rec']
    sp = rec.get('get_action_spans') or []
    n = rec.get('n_actions')
    return {'first get_action s': sp[0] if sp else None,
            'planning s per action': rec['planning_s'] / n if n and rec.get('planning_s') is not None else None,
            'their loop s': rec.get('loop_s')}


print('\n== speed (median [quartiles] over counted runs; run 1 split by the slow hour)')
for arm, fn in (('O', o_speed), ('T', t_speed)):
    groups = (('run 1 outside', [r for k, r in f1.items() if k[0] == arm and r['counts'] and not slow(r)]),
              ('run 1 inside ', [r for k, r in f1.items() if k[0] == arm and r['counts'] and slow(r)]),
              ('run 2        ', [r for k, r in f2.items() if k[0] == arm and r['counts']]))
    names = list(fn(groups[2][1][0]).keys())
    print(f"  arm {arm}")
    for nm in names:
        print(f"    {nm}")
        for g, rs in groups:
            print(f"      {g} {med([fn(r)[nm] for r in rs])}")
    keys = sorted(k for k, r in f1.items() if k[0] == arm and r['counts'] and not slow(r)
                  and f2.get(k, {}).get('counts'))
    nm = names[0]
    ratio = [fn(f2[k])[nm] / fn(f1[k])[nm] for k in keys if fn(f1[k])[nm] and fn(f2[k])[nm] is not None]
    print(f"    the same (scene, repetition), run 2 / run 1 outside the slow hour, {nm}: {med(ratio)}")
