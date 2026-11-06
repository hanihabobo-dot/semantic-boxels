"""BF#63: the paired numbers per repetition, and without the pairs whose
arm T run timed out (run 1: both arms slower on the same scenes in rep 1,
arm T's timeouts 3 -> 11; the cause was the slow hour on the NFS volume,
BF#63 THE SLOW HOUR, not busier nodes).  Usage: python -I bf63_reps.py
<eval dir> [job glob: 50630* = run 1, the default; 5084* = run 2 in eval2]"""
import glob, json, os, statistics, sys

here = os.path.dirname(os.path.abspath(__file__))
root = here
while not os.path.isfile(os.path.join(root, 'tools', 'gen_scene_eval.py')):
    root = os.path.dirname(root)
sys.path.insert(0, os.path.join(root, 'tools'))
from gen_scene_eval import mcnemar_exact, wilson  # noqa: E402

pat = sys.argv[2] if len(sys.argv) > 2 else '50630*'
rows = []
for p in sorted(glob.glob(os.path.join(sys.argv[1], pat, 'results.jsonl'))):
    rows += [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]
final = {}
for r in rows:
    k = (r['arm'], r['seed'], r['rep'])
    if k not in final or r['attempt'] >= final[k]['attempt']:
        final[k] = r
seeds = sorted({s for (_, s, _) in final})


def paired(keys):
    b = sum(final[('O', s, r)]['success'] and final[('T', s, r)]['success'] for s, r in keys)
    o = sum(final[('O', s, r)]['success'] and not final[('T', s, r)]['success'] for s, r in keys)
    t = sum(final[('T', s, r)]['success'] and not final[('O', s, r)]['success'] for s, r in keys)
    return (f"{len(keys)} pairs: both {b}, only O {o}, only T {t}, neither {len(keys) - b - o - t}; "
            f"exact McNemar p = {mcnemar_exact(o, t):.3g}")


for rep in (0, 1):
    print(f"== repetition {rep}")
    for arm in ('O', 'T'):
        rs = [r for (a, s, rp), r in final.items() if a == arm and rp == rep and r['counts']]
        k = sum(r['success'] for r in rs)
        lo, hi = wilson(k, len(rs))
        succ = [r for r in rs if r['success']]
        print(f"  {arm}: {k}/{len(rs)} = {k / len(rs):.2f} [{lo:.2f}, {hi:.2f}], timeouts "
              f"{sum(r['timed_out'] for r in rs)}, median wall of successes "
              f"{statistics.median(r['wall_s'] for r in succ):.1f} s")
    print('  ' + paired([(s, rep) for s in seeds
                         if final[('O', s, rep)]['counts'] and final[('T', s, rep)]['counts']]))
for arm, clock in (('T', 'time_to_success_s'), ('O', None)):
    both = [s for s in seeds if all(final.get((arm, s, rp), {}).get('success') for rp in (0, 1))]
    get = (lambda r: r['rec'].get(clock)) if clock else (lambda r: r['loop_s'])
    d = [get(final[(arm, s, 1)]) - get(final[(arm, s, 0)]) for s in both]
    print(f"== {arm}: {len(both)} scenes successful in both reps; rep 1 minus rep 0 "
          f"({'their loop clock to success' if clock else 'pipeline wall'}): median {statistics.median(d):+.1f} s")
keys = [(s, rp) for (a, s, rp), r in final.items() if a == 'O' and r['counts']
        and final[('T', s, rp)]['counts'] and not final[('T', s, rp)]['timed_out']]
print('== both reps, the pairs whose arm T run did not time out: ' + paired(sorted(keys)))
