"""BF#59 phase 8: the table of the die-slip eval from the pulled records.

Reads every <job>/results.jsonl under this folder (tools/slip_eval.py's
records, one per episode of our arms; the base arm runs in every job) and
every <job>/campaign.jsonl (tools/_bridge_campaign.py's records of arm T,
TAMPURA as shipped) and prints, as markdown:
  1. per arm: episodes, successes, timeouts, carries, losses, the loss
     per carry with its exact 95 % interval, the medians of the process
     wall (timeouts at the cap), the pipeline's wall, planning and
     execution time, the seeds whose repetitions disagree;
  2. the same successes and losses per scene (the seed-to-scene map of
     STATE.md's "Eval design notes" is read from the records);
  3. every arm against the base of its own job (the same node and hours)
     and against the pooled base: Fisher's exact test, two-sided, on the
     losses per carry and on the successes per episode;
  4. TAMPURA beside them: per repetition, per scene, its times.
No scipy: the hypergeometric sums and the Clopper-Pearson bounds are
computed with math.comb.  Usage:
  python slip_table.py [eval folder] [--md TABLE.md]
"""
import glob
import json
import os
import statistics
import sys
from collections import defaultdict
from math import comb

OUR = 'results.jsonl'
THEIRS = 'campaign.jsonl'


def read_jsonl(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def fisher_two_sided(a, b, c, d):
    """p of the 2x2 table [[a, b], [c, d]] (rows: arms; columns: event,
    no event): the sum of the hypergeometric probabilities of the tables
    with the same margins that are no more likely than the observed one."""
    n = a + b + c + d
    r1, c1 = a + b, a + c
    if n == 0 or r1 == 0 or r1 == n or c1 == 0 or c1 == n:
        return 1.0
    lo, hi = max(0, r1 - (n - c1)), min(r1, c1)
    denom = comb(n, r1)

    def prob(x):
        return comb(c1, x) * comb(n - c1, r1 - x) / denom

    p_obs = prob(a)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= p_obs * (1 + 1e-9)))


def binom_cdf(k, n, p):
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))


def clopper_pearson(k, n, alpha=0.05):
    """Exact two-sided interval of a rate k/n, by bisection on the
    binomial tail."""
    if n == 0:
        return (float('nan'), float('nan'))

    def solve(target, lower):
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            # lower bound: P(X >= k | mid) = alpha/2; upper: P(X <= k | mid) = alpha/2
            val = (1 - binom_cdf(k - 1, n, mid)) if lower else binom_cdf(k, n, mid)
            if lower:
                if val < target:
                    lo = mid
                else:
                    hi = mid
            else:
                if val > target:
                    lo = mid
                else:
                    hi = mid
        return (lo + hi) / 2

    low = 0.0 if k == 0 else solve(alpha / 2, True)
    high = 1.0 if k == n else solve(alpha / 2, False)
    return (low, high)


def median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else float('nan')


def fmt(x, nd=1):
    if x is None or x != x:
        return '-'
    return f'{x:.{nd}f}'


SEED_SCENE = {}  # seed -> scene stamp, learned from the records that carry one


def scene_of(rec):
    """The scene stamp of a record; a timed-out episode wrote no record of
    its own, so its scene comes from the other records of the same seed."""
    if rec.get('scene_file'):
        return str(rec['scene_file']).split('.')[0]
    return SEED_SCENE.get(rec.get('seed'), '?')


def outcome_code(rec):
    if rec.get('timed_out'):
        return 'T'
    return 'S' if rec.get('bridge_status') == 'success' else 'F'


class Arm:
    def __init__(self, name, job):
        self.name, self.job, self.recs = name, job, []

    def add(self, rec):
        self.recs.append(rec)

    @property
    def episodes(self):
        return len(self.recs)

    @property
    def successes(self):
        return sum(1 for r in self.recs if outcome_code(r) == 'S')

    @property
    def timeouts(self):
        return sum(1 for r in self.recs if outcome_code(r) == 'T')

    @property
    def carries(self):
        return sum(int(r.get('carries') or 0) for r in self.recs)

    @property
    def losses(self):
        return sum(int(r.get('losses') or 0) for r in self.recs)

    @property
    def tries(self):
        return sum(int(r.get('pick_tries') or 0) for r in self.recs)

    def metric(self, key):
        return [((r.get('metrics') or {}).get(key)) for r in self.recs]

    def mixed_seeds(self):
        by_seed = defaultdict(list)
        for r in self.recs:
            by_seed[r['seed']].append(outcome_code(r))
        seeds = sorted(by_seed)
        mixed = [s for s in seeds if len(set(by_seed[s])) > 1]
        return mixed, seeds

    def by_scene(self):
        out = defaultdict(lambda: [0, 0, 0, 0])  # episodes, successes, carries, losses
        for r in self.recs:
            row = out[scene_of(r)]
            row[0] += 1
            row[1] += outcome_code(r) == 'S'
            row[2] += int(r.get('carries') or 0)
            row[3] += int(r.get('losses') or 0)
        return out


def elapsed_of_job(folder):
    for log in glob.glob(os.path.join(folder, 'p4-slip*.txt')):
        with open(log, encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith('Elapsed Time:'):
                    return line.split(':', 1)[1].strip()
    return '-'


def main(argv):
    folder = '.'
    md_path = None
    args = list(argv)
    if '--md' in args:
        i = args.index('--md')
        md_path = args[i + 1]
        del args[i:i + 2]
    if args:
        folder = args[0]
    here = os.path.abspath(folder)
    lines = []
    out = lines.append

    # ---- our jobs -------------------------------------------------------
    jobs = {}  # job folder name -> {arm name: Arm}
    for path in sorted(glob.glob(os.path.join(here, '*', OUR))):
        job = os.path.basename(os.path.dirname(path))
        arms = jobs.setdefault(job, {})
        for rec in read_jsonl(path):
            arms.setdefault(rec['arm'], Arm(rec['arm'], job)).add(rec)
    pooled_base = Arm('base (pooled)', 'all')
    for job, arms in jobs.items():
        if 'base' in arms:
            for r in arms['base'].recs:
                pooled_base.add(r)
    for arms in jobs.values():
        for a in arms.values():
            for r in a.recs:
                if r.get('scene_file'):
                    SEED_SCENE.setdefault(r['seed'], scene_of(r))
    for path in glob.glob(os.path.join(here, '*', THEIRS)):
        for r in read_jsonl(path):
            if r.get('scene_file'):
                SEED_SCENE.setdefault(r['seed'], scene_of(r))

    out('## Our arms (one row per arm and job; base runs in every job)')
    out('')
    out('Wall "all" is the process wall of every episode with the timeouts at the cap (median and mean); "finished" the pipeline\'s own wall over the episodes that reached an outcome, so an arm that times out on the slow seeds looks faster there than it is: the paired ratios in the next tables compare the same seeds.')
    out('')
    out('| job | arm | episodes | success | timeouts | carries | losses | loss/carry [95 %] | pick tries | wall s all: median | mean | wall s finished | planning s | exec s | mixed seeds | job elapsed |')
    out('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    rows_for_scene = []
    for job in sorted(jobs):
        for name in ([n for n in jobs[job] if n == 'base'] + sorted(n for n in jobs[job] if n != 'base')):
            a = jobs[job][name]
            lo, hi = clopper_pearson(a.losses, a.carries)
            mixed, seeds = a.mixed_seeds()
            walls = [r.get('process_wall_s') for r in a.recs if r.get('process_wall_s') is not None]
            out(f"| {job} | {name} | {a.episodes} | {a.successes} | {a.timeouts} | {a.carries} | {a.losses} | "
                f"{fmt(a.losses / a.carries if a.carries else float('nan'), 2)} [{fmt(lo, 2)}, {fmt(hi, 2)}] | {a.tries} | "
                f"{fmt(median(walls))} | {fmt(statistics.mean(walls) if walls else float('nan'))} | {fmt(median(a.metric('wall_s')))} | "
                f"{fmt(median(a.metric('planning_s')))} | {fmt(median(a.metric('exec_s')))} | "
                f"{len(mixed)}/{len(seeds)}{(' (' + ','.join(str(s) for s in mixed) + ')') if mixed else ''} | {elapsed_of_job(os.path.join(here, job))} |")
            rows_for_scene.append((job, name, a))
    if pooled_base.episodes:
        a = pooled_base
        lo, hi = clopper_pearson(a.losses, a.carries)
        mixed, seeds = a.mixed_seeds()
        walls = [r.get('process_wall_s') for r in a.recs if r.get('process_wall_s') is not None]
        out(f"| all | base (pooled) | {a.episodes} | {a.successes} | {a.timeouts} | {a.carries} | {a.losses} | "
            f"{fmt(a.losses / a.carries if a.carries else float('nan'), 2)} [{fmt(lo, 2)}, {fmt(hi, 2)}] | {a.tries} | "
            f"{fmt(median(walls))} | {fmt(statistics.mean(walls) if walls else float('nan'))} | {fmt(median(a.metric('wall_s')))} | "
            f"{fmt(median(a.metric('planning_s')))} | {fmt(median(a.metric('exec_s')))} | {len(mixed)}/{len(seeds)} | - |")
    out('')

    # ---- paired times against the base of the same job ---------------------
    out('## Times paired with the base of the same job (the same seed and repetition, both finished)')
    out('')
    out('| job | arm | pairs | wall s median arm / base | median of the per-pair ratio | planning s arm / base | ratio | exec s arm / base | ratio | process wall all 60, mean arm / base |')
    out('|---|---|---|---|---|---|---|---|---|---|')
    for job, name, a in rows_for_scene:
        if name == 'base' or 'base' not in jobs[job]:
            continue
        b = jobs[job]['base']
        bmap = {(r['seed'], r['rep']): r for r in b.recs if (r.get('metrics') or {}).get('wall_s') is not None}
        pairs = [(r, bmap[(r['seed'], r['rep'])]) for r in a.recs
                 if (r.get('metrics') or {}).get('wall_s') is not None and (r['seed'], r['rep']) in bmap]
        cells = [job, name, str(len(pairs))]
        for key in ('wall_s', 'planning_s', 'exec_s'):
            av = [p[0]['metrics'][key] for p in pairs]
            bv = [p[1]['metrics'][key] for p in pairs]
            ratios = [x / y for x, y in zip(av, bv) if y]
            cells += [f'{fmt(median(av))} / {fmt(median(bv))}', f'x{fmt(median(ratios), 2)}']
        aw = [r.get('process_wall_s') for r in a.recs if r.get('process_wall_s') is not None]
        bw = [r.get('process_wall_s') for r in b.recs if r.get('process_wall_s') is not None]
        cells.append(f'{fmt(statistics.mean(aw))} / {fmt(statistics.mean(bw))}' if aw and bw else '-')
        out('| ' + ' | '.join(cells) + ' |')
    out('')

    # ---- per scene -------------------------------------------------------
    scenes = sorted({scene_of(r) for arms in jobs.values() for a in arms.values() for r in a.recs})
    seeds_of_scene = defaultdict(set)
    for arms in jobs.values():
        for a in arms.values():
            for r in a.recs:
                seeds_of_scene[scene_of(r)].add(r['seed'])
    out('## Per scene: successes/episodes and losses/carries')
    out('')
    out('| job | arm | ' + ' | '.join(f"{s} (seeds {','.join(str(x) for x in sorted(seeds_of_scene[s]))})" for s in scenes) + ' |')
    out('|---|---|' + '---|' * len(scenes))
    for job, name, a in rows_for_scene:
        cells = []
        for s in scenes:
            e, su, c, l = a.by_scene().get(s, [0, 0, 0, 0])
            cells.append(f'{su}/{e}, losses {l}/{c}')
        out(f'| {job} | {name} | ' + ' | '.join(cells) + ' |')
    out('')

    # ---- pairwise --------------------------------------------------------
    out("## Each arm against base (Fisher's exact test, two-sided)")
    out('')
    out('| job | arm | losses/carries arm vs base of its job | p | vs pooled base | p | success arm vs base of its job | p | vs pooled base | p |')
    out('|---|---|---|---|---|---|---|---|---|---|')
    for job, name, a in rows_for_scene:
        if name == 'base':
            continue
        b = jobs[job].get('base')
        cells = [job, name]
        for ref in (b, pooled_base):
            if ref is None or not ref.episodes:
                cells += ['-', '-']
                continue
            p = fisher_two_sided(a.losses, a.carries - a.losses, ref.losses, ref.carries - ref.losses)
            cells += [f'{a.losses}/{a.carries} vs {ref.losses}/{ref.carries}', f'{p:.3g}']
        for ref in (b, pooled_base):
            if ref is None or not ref.episodes:
                cells += ['-', '-']
                continue
            p = fisher_two_sided(a.successes, a.episodes - a.successes, ref.successes, ref.episodes - ref.successes)
            cells += [f'{a.successes}/{a.episodes} vs {ref.successes}/{ref.episodes}', f'{p:.3g}']
        out('| ' + ' | '.join(cells) + ' |')
    out('')

    # ---- replication: per arm and seed the outcome string -------------------
    out('## Replication: outcomes per seed (S success, F failure, T timeout; repetitions in order)')
    out('')
    all_seeds = sorted({r['seed'] for arms in jobs.values() for a in arms.values() for r in a.recs})
    out('| job | arm | ' + ' | '.join(str(s) for s in all_seeds) + ' |')
    out('|---|---|' + '---|' * len(all_seeds))
    for job, name, a in rows_for_scene:
        by_seed = defaultdict(list)
        for r in sorted(a.recs, key=lambda r: (r['seed'], r['rep'])):
            by_seed[r['seed']].append(outcome_code(r))
        out(f'| {job} | {name} | ' + ' | '.join(''.join(by_seed.get(s, ['x'])) for s in all_seeds) + ' |')
    out('')

    # ---- TAMPURA -----------------------------------------------------------
    for path in sorted(glob.glob(os.path.join(here, '*', THEIRS))):
        job = os.path.basename(os.path.dirname(path))
        recs = [r for r in read_jsonl(path) if r.get('arm') == 'T']
        if not recs:
            continue
        out(f'## TAMPURA (arm T, job {job}, elapsed {elapsed_of_job(os.path.dirname(path))})')
        out('')
        succ = sum(1 for r in recs if r.get('success'))
        crashed = sum(1 for r in recs if r.get('status') == 'crashed')
        censored = sum(1 for r in recs if r.get('censored'))
        lo, hi = clopper_pearson(succ, len(recs))
        out(f'- episodes {len(recs)}, successes {succ} ({fmt(100 * succ / len(recs), 0)} %, exact 95 % [{fmt(100 * lo, 0)}, {fmt(100 * hi, 0)}] %), '
            f'crashed {crashed}, censored at the cap {censored}')
        reps = sorted({r['rep'] for r in recs})
        out('- per repetition: ' + '; '.join(
            f"rep {k}: {sum(1 for r in recs if r['rep'] == k and r.get('success'))}/{sum(1 for r in recs if r['rep'] == k)}" for k in reps))
        by_scene = defaultdict(lambda: [0, 0])
        for r in recs:
            by_scene[scene_of(r)][0] += 1
            by_scene[scene_of(r)][1] += bool(r.get('success'))
        out('- per scene: ' + '; '.join(f'{s}: {v[1]}/{v[0]}' for s, v in sorted(by_scene.items())))
        finished = [r for r in recs if not r.get('censored')]
        out(f"- times (finished episodes, n={len(finished)}): median loop {fmt(median([r.get('loop_s') for r in finished]))} s, "
            f"wall {fmt(median([r.get('wall_s') for r in finished]))} s, planning {fmt(median([r.get('planning_s') for r in finished]))} s; "
            f"successes only: loop {fmt(median([r.get('loop_s') for r in finished if r.get('success')]))} s, "
            f"time to success {fmt(median([r.get('time_to_success_s') for r in finished if r.get('success')]))} s")
        by_seed = defaultdict(list)
        for r in sorted(recs, key=lambda r: (r['seed'], r['rep'])):
            by_seed[r['seed']].append('S' if r.get('success') else ('C' if r.get('status') == 'crashed' else 'F'))
        mixed = [s for s in by_seed if len(set(by_seed[s])) > 1]
        out(f'- replication: {len(mixed)}/{len(by_seed)} seeds mixed ({", ".join(str(s) for s in sorted(mixed))}); per seed: '
            + ', '.join(f"{s}:{''.join(v)}" for s, v in sorted(by_seed.items())))
        out('')

    text = '\n'.join(lines)
    print(text)
    if md_path:
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(text + '\n')


if __name__ == '__main__':
    main(sys.argv[1:])
