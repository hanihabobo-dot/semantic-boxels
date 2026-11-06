"""BF#63 run 2: the stall rule declared before the run (STATE.md phase 8),
applied to the jobs' I/O probes (eval2/<job>/io_probe.tsv: every 20 s the
seconds to open a file on $W, to write 4 kB there with fsync, and the same
write on the node's own disk).

A stall is two or more consecutive probe rows whose open on $W took 1 s or
more.  It is taken to last from the probe row before it to the row after
it (the whole time no row showed the volume normal).  A pair (scene,
repetition) is flagged when the final run of either arm overlaps a stall
seen by any job's probe (the volume is shared).  Beside it, as a check of
the rule only (not declared): the same with every single row whose open or
write on $W took 1 s or more.  Usage: python -I bf63_io.py <eval2 dir> [job glob]"""
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
ev = sys.argv[1]
pat = sys.argv[2] if len(sys.argv) > 2 else '5084*'
jobs = sorted(d for d in glob.glob(os.path.join(ev, pat)) if os.path.isdir(d))

rows = []
for d in jobs:
    with open(os.path.join(d, 'results.jsonl'), encoding='utf-8') as f:
        rows += [dict(json.loads(line), job=os.path.basename(d)) for line in f if line.strip()]
final = {}
for r in rows:
    k = (r['arm'], r['seed'], r['rep'])
    if k not in final or r['attempt'] >= final[k]['attempt']:
        final[k] = r
pairs = sorted((s, rp) for (a, s, rp), r in final.items() if a == 'O' and r['counts']
               and final.get(('T', s, rp), {}).get('counts'))


def span(r):
    end = dt.datetime.strptime(r['finished'], F)
    return end - dt.timedelta(seconds=r['wall_s']), end


def probe(d):
    out = []
    with open(os.path.join(d, 'io_probe.tsv'), encoding='utf-8') as f:
        n = len(f.readline().rstrip('\n').split('\t'))
        for line in f:
            v = line.rstrip('\n').split('\t')
            if len(v) == n:
                out.append({'t': dt.datetime.strptime(v[0], F), 'open': float(v[1]),
                            'write': float(v[2]), 'local': float(v[3])})
    return out


def stalls(p, slow, min_rows):
    """Runs of at least min_rows consecutive slow rows, as (start, end, rows):
    from the row before the run to the row after it."""
    out, i = [], 0
    while i < len(p):
        if not slow(p[i]):
            i += 1
            continue
        j = i
        while j + 1 < len(p) and slow(p[j + 1]):
            j += 1
        if j - i + 1 >= min_rows:
            a = p[i - 1]['t'] if i > 0 else p[i]['t']
            b = (p[j + 1]['t'] if j + 1 < len(p)
                 else p[j]['t'] + dt.timedelta(seconds=p[j]['open'] + p[j]['write']))
            out.append((a, b, p[i:j + 1]))
        i = j + 1
    return out


def q(xs):
    return f"{statistics.median(xs):.3f} / {max(xs):.3f}"


probes = {os.path.basename(d): probe(d) for d in jobs}
hosts = {r['job']: r['host'] for r in rows}
print('== the probe per job (s, median / maximum): open on $W; write 4 kB + fsync on $W; the same write locally')
for j, p in probes.items():
    print(f"{j} {hosts.get(j, '?'):6} {len(p):3} rows {p[0]['t']:%H:%M:%S} to {p[-1]['t']:%H:%M:%S}: "
          f"open {q([x['open'] for x in p])} ({sum(x['open'] >= 1 for x in p)} rows >= 1 s); "
          f"write {q([x['write'] for x in p])} ({sum(x['write'] >= 1 for x in p)} rows >= 1 s); "
          f"local {q([x['local'] for x in p])}")


def report(name, keys):
    print(f"  {name}: {len(keys)} pairs")
    for arm in ('O', 'T'):
        rs = [final[(arm,) + k] for k in keys]
        n = sum(r['success'] for r in rs)
        lo, hi = wilson(n, len(rs)) if rs else (0, 0)
        print(f"    {arm}: {n}/{len(rs)} = {n / len(rs):.2f} [{lo:.2f}, {hi:.2f}], timeouts "
              f"{sum(r['timed_out'] for r in rs)}")
    b = sum(final[('O',) + k]['success'] and final[('T',) + k]['success'] for k in keys)
    o = sum(final[('O',) + k]['success'] and not final[('T',) + k]['success'] for k in keys)
    t = sum(final[('T',) + k]['success'] and not final[('O',) + k]['success'] for k in keys)
    print(f"    both {b}, only O {o}, only T {t}, neither {len(keys) - b - o - t}; "
          f"exact McNemar p = {mcnemar_exact(o, t):.3g}")


def apply(title, slow, min_rows):
    print(f"\n== {title}")
    found = [(j,) + s for j, p in probes.items() for s in stalls(p, slow, min_rows)]
    if not found:
        print('  no stall')
    for j, a, b, rs in found:
        print(f"  job {j} ({hosts.get(j, '?')}): {a:%H:%M:%S} to {b:%H:%M:%S}, rows "
              + ', '.join(f"{x['t']:%H:%M:%S} open {x['open']:.3f} write {x['write']:.3f}" for x in rs))
    hit = set()
    for r in sorted(rows, key=lambda r: span(r)[0]):
        a, b = span(r)
        over = [(j, s0, s1) for j, s0, s1, _ in found if a < s1 and b > s0]
        if not over:
            continue
        fin = final[(r['arm'], r['seed'], r['rep'])] is r
        if fin and (r['seed'], r['rep']) in pairs:
            hit.add((r['seed'], r['rep']))
        print(f"  overlaps: {r['arm']} s{r['seed']} r{r['rep']} attempt {r['attempt']} {a:%H:%M:%S} to "
              f"{b:%H:%M:%S} ({r['wall_s']:.1f} s), {'success' if r['success'] else 'no success'}, "
              f"{'counts' if r['counts'] else 'does not count'}{'' if fin else ', not the final run'}")
    flagged = sorted(hit)
    print(f"  pairs flagged: {len(flagged)} of {len(pairs)} ("
          + (', '.join(f"s{s} r{rp}" for s, rp in flagged) or 'none') + ')'
          + (f"; more than a tenth of the pairs" if len(flagged) > len(pairs) / 10 else '; not more than a tenth of the pairs'))
    report('all pairs (the headline)', pairs)
    report('without the flagged pairs', [k for k in pairs if k not in hit])


apply('the declared rule: two or more consecutive rows with the open on $W at 1 s or more',
      lambda x: x['open'] >= 1, 2)
apply('check of the rule only (not declared): any single row with the open or the write on $W at 1 s or more',
      lambda x: x['open'] >= 1 or x['write'] >= 1, 1)
