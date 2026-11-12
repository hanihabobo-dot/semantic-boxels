"""BF#63's design, run 3 (eval3, 2026-11-12, jobs 52488*: our arm from
51428d8, the tag d6a9715 plus TB-16 and BF#64's shadow fix TB-1) beside
run 2 (eval2, 2026-11-04, jobs 5084*: our arm from the tag).  TAMPURA's arm
is the same code in both.  The runs are not pooled.  Printed: per arm the
outcome of each (scene, repetition) in run 3 against run 2, with the cells
that changed; one line per scene; the pairs of each run (ours against
TAMPURA) under the declared validity rule, and the same with a scene as
the unit; arm O's failure classes in both runs; walls and speed.
Usage: python -I bf63_run3.py <run 2 eval2 dir> <run 3 eval3 dir>"""
import collections
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


f2, f3 = load(sys.argv[1], '5084*'), load(sys.argv[2], '52488*')
RUNS = (('run 2', f2), ('run 3', f3))
SCENES = sorted({k[1] for k in f3})
NAME = {'O': 'ours', 'T': 'TAMPURA'}


def sym(r):
    if r is None:
        return '-'
    if not r['counts']:
        return 'x'
    return 'S' if r['success'] else 'T' if r['timed_out'] else 'F'


def o_class(r):
    if r['success']:
        return 'success'
    if r['timed_out']:
        return 'timeout'
    m = r['rec'].get('metrics') or {}
    return m.get('outcome') or r['rec'].get('bridge_status') or 'failure'


def what(arm, r):
    return o_class(r) if arm == 'O' else {'S': 'success', 'T': 'timeout', 'F': 'failure'}[sym(r)]


def scene_list(keys):
    by = collections.defaultdict(list)
    for _, s, rp in keys:
        by[s].append(rp)
    return ', '.join(f"{s} ({'both' if len(rps) == 2 else 'r%d' % rps[0]})" for s, rps in sorted(by.items()))


print('== run 3 against run 2 per (scene, repetition): the same arm, the same scene')
print('   (ours: the tag against the tag with the BF#64 fix, so the cells that differ are the fix')
print('   and the run-to-run spread together; TAMPURA: the same code, so run-to-run agreement)')
for arm in ('O', 'T'):
    allk = sorted(k for k in set(f2) | set(f3) if k[0] == arm)
    keys = [k for k in allk if f2.get(k, {}).get('counts') and f3.get(k, {}).get('counts')]
    b = [k for k in keys if f2[k]['success'] and f3[k]['success']]
    n3 = [k for k in keys if f3[k]['success'] and not f2[k]['success']]
    n2 = [k for k in keys if f2[k]['success'] and not f3[k]['success']]
    print(f"  {NAME[arm]} ({arm}): counted in both runs {len(keys)} of {len(allk)}: success in both {len(b)}, "
          f"only in run 3 {len(n3)}, only in run 2 {len(n2)}, in neither {len(keys) - len(b) - len(n3) - len(n2)}; "
          f"exact McNemar p = {mcnemar_exact(len(n3), len(n2)):.3g}")
    for nm, f in RUNS:
        n = sum(f[k]['success'] for k in keys)
        lo, hi = wilson(n, len(keys))
        print(f"     {nm} on these: {n}/{len(keys)} = {n / len(keys):.2f} [{lo:.2f}, {hi:.2f}]")
    out = [k for k in allk if k not in keys]
    if out:
        print('     not counted in a run: ' + ', '.join(
            f"s{k[1]} r{k[2]} (run 2 {sym(f2.get(k))}, run 3 {sym(f3.get(k))})" for k in out))
    if n3:
        print(f"     only in run 3: scenes {scene_list(n3)}")
    if n2:
        print(f"     only in run 2: scenes {scene_list(n2)}")
    for k in keys:
        if f2[k]['success'] != f3[k]['success']:
            print(f"       s{k[1]} r{k[2]} ({f3[k]['n_cups']} cups): run 2 {what(arm, f2[k])} ({f2[k]['wall_s']:.0f} s)"
                  f" -> run 3 {what(arm, f3[k])} ({f3[k]['wall_s']:.0f} s)")
    # a scene as the unit: its two repetitions are not independent
    up = down = same = 0
    for s in SCENES:
        ks = [(arm, s, rp) for rp in (0, 1)]
        if all(k in keys for k in ks):
            d = sum(f3[k]['success'] for k in ks) - sum(f2[k]['success'] for k in ks)
            up, down, same = up + (d > 0), down + (d < 0), same + (d == 0)
    print(f"     a scene as the unit (both repetitions counted in both runs, {up + down + same} scenes): more "
          f"successes in run 3 in {up}, fewer in {down}, as many in {same}; exact sign test p = "
          f"{mcnemar_exact(up, down):.3g}")

print('\n== per scene (r0 r1 of each run; S success, F failure, T timeout at the 900 s cap, x not counted;')
print('   * = a cell of this scene differs between the runs)')
print('   scene cups | ours run 2  run 3 | TAMPURA run 2  run 3')
for s in SCENES:
    cell = {(arm, nm): ' '.join(sym(f.get((arm, s, rp))) for rp in (0, 1)) for arm in 'OT' for nm, f in RUNS}
    star = ('*' if cell[('O', 'run 2')] != cell[('O', 'run 3')] else ' ',
            '*' if cell[('T', 'run 2')] != cell[('T', 'run 3')] else ' ')
    print(f"   {s}   {f3[('O', s, 0)]['n_cups']}   |    {cell[('O', 'run 2')]}     {cell[('O', 'run 3')]} {star[0]}"
          f" |       {cell[('T', 'run 2')]}     {cell[('T', 'run 3')]} {star[1]}")


def pairs(f):
    return sorted((s, rp) for (a, s, rp), r in f.items() if a == 'O' and r['counts']
                  and f.get(('T', s, rp), {}).get('counts'))


def cells(f, keys, ok):
    b = sum(ok(f[('O',) + k]) and ok(f[('T',) + k]) for k in keys)
    o = sum(ok(f[('O',) + k]) and not ok(f[('T',) + k]) for k in keys)
    t = sum(ok(f[('T',) + k]) and not ok(f[('O',) + k]) for k in keys)
    return b, o, t, len(keys) - b - o - t


def report(name, f, keys):
    print(f"  {name}: {len(keys)} pairs")
    if not keys:
        return
    for arm in ('O', 'T'):
        rs = [f[(arm,) + k] for k in keys]
        n = sum(r['success'] for r in rs)
        lo, hi = wilson(n, len(rs))
        print(f"    {arm}: {n}/{len(rs)} = {n / len(rs):.2f} [{lo:.2f}, {hi:.2f}], timeouts "
              f"{sum(r['timed_out'] for r in rs)}")
    b, o, t, n = cells(f, keys, lambda r: r['success'])
    print(f"    both {b}, only O {o}, only T {t}, neither {n}; exact McNemar p = {mcnemar_exact(o, t):.3g}")


print('\n== the pairs: ours against TAMPURA on the same (scene, repetition), both arms counted (the declared rule)')
for nm, f in RUNS:
    report(f"{nm}, all", f, pairs(f))
changed = {k[1] for k in f3 if k[0] == 'O' and f2.get(k, {}).get('counts') and f3[k]['counts']
           and f2[k]['success'] != f3[k]['success']}
for nm, f in RUNS:
    report(f"{nm}, the {len(changed)} scenes in which our arm's outcome differs between the runs", f,
           [k for k in pairs(f) if k[0] in changed])
    report(f"{nm}, the other {len(SCENES) - len(changed)} scenes", f, [k for k in pairs(f) if k[0] not in changed])
print('  a scene as the unit (both repetitions a pair): our successes of 2 against TAMPURA\'s of 2')
for nm, f in RUNS:
    pk = set(pairs(f))
    up = down = same = 0
    for s in SCENES:
        if (s, 0) in pk and (s, 1) in pk:
            d = sum(f[('O', s, rp)]['success'] - f[('T', s, rp)]['success'] for rp in (0, 1))
            up, down, same = up + (d > 0), down + (d < 0), same + (d == 0)
    print(f"    {nm}: {up + down + same} scenes: ours more in {up}, TAMPURA more in {down}, as many in {same}; "
          f"exact sign test p = {mcnemar_exact(up, down):.3g}")
print('  NOT the declared rule, for comparison only: all 80 (scene, repetition), a run that did not count taken')
print('  as no success')
for nm, f in RUNS:
    keys = sorted({(s, rp) for (a, s, rp) in f})
    ok = lambda r: bool(r['counts'] and r['success'])  # noqa: E731
    b, o, t, n = cells(f, keys, ok)
    print(f"    {nm}: O {b + o}/{len(keys)}, T {b + t}/{len(keys)}; both {b}, only O {o}, only T {t}, neither {n}; "
          f"exact McNemar p = {mcnemar_exact(o, t):.3g}")

print("\n== arm O: the outcome of each (scene, repetition) in run 2 -> in run 3")
tr = collections.Counter()
where = collections.defaultdict(list)
for k in sorted(k for k in f3 if k[0] == 'O' and k in f2):
    key = (o_class(f2[k]), o_class(f3[k]))
    tr[key] += 1
    where[key].append(k)
for (a, b), n in sorted(tr.items(), key=lambda kv: (kv[0][0] == 'success', -kv[1])):
    print(f"  {n:2}  {a:22} -> {b:22}" + ('' if a == b == 'success' else '  scenes ' + scene_list(where[(a, b)])))
for nm, f in RUNS:
    c = collections.Counter(o_class(r) for k, r in f.items() if k[0] == 'O' and r['counts'] and not r['success'])
    print(f"  {nm}, counted failures by class: {dict(sorted(c.items()))}")


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


print('\n== the harness wall per episode, s (the last attempt of each (scene, repetition))')
for arm in ('O', 'T'):
    for nm, f in RUNS:
        allr = [r for k, r in f.items() if k[0] == arm]
        cr = [r for r in allr if r['counts']]
        sr = [r for r in cr if r['success']]
        print(f"  {arm} {nm}: mean over all {len(allr)} {statistics.mean(r['wall_s'] for r in allr):6.1f}; counted "
              f"{len(cr)}: mean {statistics.mean(r['wall_s'] for r in cr):6.1f}, median "
              f"{statistics.median(r['wall_s'] for r in cr):6.1f}; successes {len(sr)}: median "
              f"{statistics.median(r['wall_s'] for r in sr):6.1f}")
    keys = sorted(k for k in f3 if k[0] == arm and f3[k]['counts'] and f2.get(k, {}).get('counts')
                  and f2[k]['success'] and f3[k]['success'])
    print(f"  {arm}: the same (scene, repetition), a success in both runs, wall run 3 / run 2: "
          f"{med([f3[k]['wall_s'] / f2[k]['wall_s'] for k in keys])}")

print('\n== speed (median [quartiles] over counted runs)')
for arm, fn in (('O', o_speed), ('T', t_speed)):
    groups = [(nm, [r for k, r in f.items() if k[0] == arm and r['counts']]) for nm, f in RUNS]
    names = list(fn(groups[1][1][0]).keys())
    print(f"  arm {arm}")
    for nm in names:
        print(f"    {nm}")
        for g, rs in groups:
            print(f"      {g} {med([fn(r)[nm] for r in rs])}")
    keys = sorted(k for k, r in f2.items() if k[0] == arm and r['counts'] and f3.get(k, {}).get('counts'))
    nm = names[0]
    ratio = [fn(f3[k])[nm] / fn(f2[k])[nm] for k in keys if fn(f2[k])[nm] and fn(f3[k])[nm] is not None]
    print(f"    the same (scene, repetition), run 3 / run 2, {nm}: {med(ratio)}")
