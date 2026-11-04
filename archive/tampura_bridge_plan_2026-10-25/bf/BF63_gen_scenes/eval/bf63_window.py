"""BF#63: the run of 2026-11-03 split by the slow window.  From about 21:00
to 22:00 every node ran planning 15 to 24 times slower while execution
steps kept their speed (the NFS volume the episodes wrote to; other users'
CPU allocations on the ten nodes stayed flat).  The window is read off the
run (post hoc), so this cut is descriptive.  A pair (scene, repetition) is
in the window when either arm's final run overlaps 21:00 to 22:00.
Usage: python -I bf63_window.py <eval dir>"""
import datetime as dt
import glob
import json
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
root = here
while not os.path.isfile(os.path.join(root, 'tools', 'gen_scene_eval.py')):
    root = os.path.dirname(root)
sys.path.insert(0, os.path.join(root, 'tools'))
from gen_scene_eval import mcnemar_exact, wilson  # noqa: E402

F = '%Y-%m-%d %H:%M:%S'
W0, W1 = dt.datetime(2026, 11, 3, 21, 0, 0), dt.datetime(2026, 11, 3, 22, 0, 0)
rows = []
for p in sorted(glob.glob(os.path.join(sys.argv[1], '50630*', 'results.jsonl'))):
    rows += [json.loads(line) for line in open(p, encoding='utf-8') if line.strip()]
final = {}
for r in rows:
    k = (r['arm'], r['seed'], r['rep'])
    if k not in final or r['attempt'] >= final[k]['attempt']:
        final[k] = r


def span(r):
    end = dt.datetime.strptime(r['finished'], F)
    return end - dt.timedelta(seconds=r['wall_s']), end


def in_window(r):
    a, b = span(r)
    return a < W1 and b > W0


pairs = sorted((s, rp) for (a, s, rp), r in final.items() if a == 'O' and r['counts']
               and final.get(('T', s, rp), {}).get('counts'))
inside = [k for k in pairs if in_window(final[('O',) + k]) or in_window(final[('T',) + k])]
outside = [k for k in pairs if k not in inside]


def report(name, keys):
    print(f"== {name}: {len(keys)} pairs")
    for arm in ('O', 'T'):
        rs = [final[(arm,) + k] for k in keys]
        n = sum(r['success'] for r in rs)
        lo, hi = wilson(n, len(rs)) if rs else (0, 0)
        print(f"  {arm}: {n}/{len(rs)} [{lo:.2f}, {hi:.2f}], timeouts {sum(r['timed_out'] for r in rs)}")
    b = sum(final[('O',) + k]['success'] and final[('T',) + k]['success'] for k in keys)
    o = sum(final[('O',) + k]['success'] and not final[('T',) + k]['success'] for k in keys)
    t = sum(final[('T',) + k]['success'] and not final[('O',) + k]['success'] for k in keys)
    print(f"  both {b}, only O {o}, only T {t}, neither {len(keys) - b - o - t}; "
          f"exact McNemar p = {mcnemar_exact(o, t):.3g}")


report('all pairs', pairs)
report('pairs outside 21:00-22:00', outside)
report('pairs inside 21:00-22:00', inside)
print('== timeouts by start time (final runs)')
for arm in ('T', 'O'):
    ts = sorted(span(r)[0].strftime('%H:%M') + f" s{r['seed']} r{r['rep']}"
                for (a, s, rp), r in final.items() if a == arm and r['timed_out'] and r['counts'])
    print(f"  {arm}: {len(ts)}: " + ', '.join(ts))
print('== runs killed at the cap that took longer than 905 s to end (all attempts)')
late = sorted((span(r)[0].strftime('%H:%M'), r['arm'], r['seed'], r['rep'], r['wall_s'])
              for r in rows if r['timed_out'] and r['wall_s'] > 905)
print('  ' + ', '.join(f"{a}{s} r{rp} {w:.0f} s (start {t})" for t, a, s, rp, w in late))
