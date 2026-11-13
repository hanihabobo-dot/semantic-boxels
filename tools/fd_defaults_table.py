#!/usr/bin/env python3
"""Path 14 (worker B, 2026-11-13): the table of the find_dice check of the
candidate defaults, with the comparisons declared before any job in
tracks/meeting_2026-11-13/cluster_requests/B_find_dice_defaults_DRAFT.md
(section 5) and no others.  Standard library only; nothing is run.

  python tools/fd_defaults_table.py JOB_DIR [JOB_DIR ...] [--out FILE]

JOB_DIR is a job's folder of tools/cluster/fd_defaults.sbatch (unpacked):
results.jsonl and metadata.json of tools/slip_eval.py.  A job with a scenes
folder in its metadata is set G (the generated scenes), any other is set S
(the shipped scenes).  The sets are never pooled, and jobs of different
snapshots are refused.

The arms (the draft's names; --def, --deftrap, --trap and --co change them):
  def         today's four defaults, named one by one
  deftrap     def + carry_trapezoid
  trap        carry_trapezoid alone
  deftrap_co  deftrap with the driver flag --corridor-test object

Counting, as declared:
  success     the bridge's status AND the pipeline's goal check say success;
  at the cap  a failure of its arm;
  no plan     the pipeline's exit reason planner_failed;
  void        an episode with no outcome that the cap did not end (a crash),
              or, on set G, one that loaded another scene than its own: its
              seed and repetition are void for EVERY arm, and listed;
  incomplete  a seed and repetition some arm has no row for (a cut job):
              left out for every arm, and listed.
Comparisons:
  (a) deftrap against def, trap against def: losses per carry (Fisher's
      exact test, two-sided; Clopper-Pearson 95 % per arm); successes and
      episodes at the cap by seed and repetition (exact McNemar); on set G
      also by scene with the first repetition alone;
  (b) deftrap_co against deftrap: successes and no-plan endings by seed and
      repetition (exact McNemar); planning time per plan call and wall time
      as paired medians over the pairs both arms ran to the ledger's close;
  cost: the execution time of deftrap over def, the median of the ratios
      over the pairs both arms ran to the ledger's close.
"""
import argparse
import json
import math
import os
import statistics
import sys

D4 = 'solver_iters+force_hold+pose_radius_keep+grasp_wrist_home'
DEF = D4
DEFTRAP = D4 + '+carry_trapezoid'
TRAP = 'carry_trapezoid'
CO = DEFTRAP + '@corridor_object'
NO_PLAN = 'failure (planner_failed)'


# ---- the tests ---------------------------------------------------------

def mcnemar_exact(b, c):
    """Two-sided exact McNemar p of b against c discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) * 0.5 ** n
    return min(1.0, 2.0 * tail)


def fisher_two_sided(k1, n1, k2, n2):
    """Fisher's exact test, two-sided (the tables no more likely than the
    observed one), of k1 of n1 against k2 of n2."""
    k = k1 + k2
    n = n1 + n2
    if n1 == 0 or n2 == 0 or k == 0 or k == n:
        return 1.0
    den = math.comb(n, k)

    def prob(x):
        return math.comb(n1, x) * math.comb(n2, k - x) / den
    p_obs = prob(k1)
    lo, hi = max(0, k - n2), min(k, n1)
    return min(1.0, sum(p for p in (prob(x) for x in range(lo, hi + 1))
                        if p <= p_obs * (1 + 1e-9)))


def _binom_cdf(k, n, p):
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson(k, n, alpha=0.05):
    """The exact two-sided (1 - alpha) interval of k of n, by bisection."""
    if n == 0:
        return (float('nan'), float('nan'))

    def solve(f):                       # f falls from above 0 to below 0 on [0, 1]
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            if f(mid) > 0:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else solve(lambda p: alpha / 2 - (1 - _binom_cdf(k - 1, n, p)))
    upper = 1.0 if k == n else solve(lambda p: _binom_cdf(k, n, p) - alpha / 2)
    return (lower, upper)


def sign_test(plus, minus):
    """Two-sided sign test p of plus against minus (ties left out)."""
    return mcnemar_exact(plus, minus)


# ---- the rows ----------------------------------------------------------

def load_job(path):
    """(metadata, rows) of one job folder."""
    with open(os.path.join(path, 'metadata.json'), 'r', encoding='utf-8') as f:
        md = json.load(f)
    rows = []
    with open(os.path.join(path, 'results.jsonl'), 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return md, rows


def is_success(r):
    return (r.get('bridge_status') == 'success'
            and (r.get('metrics') or {}).get('outcome') == 'success')


def is_no_plan(r):
    return (r.get('metrics') or {}).get('outcome') == NO_PLAN


def is_void(r, set_name):
    """A crash (no outcome, and the cap did not end it), or on set G an
    episode that loaded another scene than its own."""
    if set_name == 'G' and not r.get('scene_ok'):
        return True
    if r.get('timed_out'):
        return False
    return r.get('bridge_status') not in ('success', 'failure')


def finished(r):
    """The episode ran to the ledger's close: its times are the pipeline's
    work, unlike a timeout's or a crash's (tools/slip_eval.py's rule)."""
    m = r.get('metrics') or {}
    return bool(not r.get('timed_out') and m.get('outcome') and m.get('wall_s') is not None)


def per_call(r):
    m = r.get('metrics') or {}
    if not m.get('plan_calls') or m.get('planning_s') is None:
        return None
    return m['planning_s'] / m['plan_calls']


def collect(job_dirs):
    """{set: {'snapshot': name, 'arms': [...], 'rows': {(arm, seed, rep): row},
    'jobs': [...]}} of the job folders; a later row of the same arm, seed and
    repetition replaces an earlier one, as in slip_eval's own loader."""
    sets = {}
    for path in job_dirs:
        md, rows = load_job(path)
        name = 'G' if md.get('scenes') else 'S'
        s = sets.setdefault(name, {'snapshot': md.get('snapshot_name'), 'arms': [],
                                   'rows': {}, 'jobs': []})
        if md.get('snapshot_name') != s['snapshot']:
            raise SystemExit(f"set {name}: {path} ran {md.get('snapshot_name')}, the jobs "
                             f"before it {s['snapshot']}: rows of different code are not pooled")
        for arm in md.get('arms') or []:
            if arm not in s['arms']:
                s['arms'].append(arm)
        s['jobs'].append(f"{os.path.basename(os.path.normpath(path))} "
                         f"(host {md.get('host')}, job {md.get('job')}, cap {md.get('cap_s')} s)")
        for r in rows:
            s['rows'][(r['arm'], r['seed'], r.get('rep', 0))] = r
    return sets


def split_keys(rows, arms, set_name):
    """(counted, void, incomplete) seed-and-repetition keys: counted when
    every arm has a row and none of them is void."""
    keys = sorted({(s, rep) for (_, s, rep) in rows})
    counted, void, incomplete = [], [], []
    for key in keys:
        have = [rows.get((x,) + key) for x in arms]
        if any(r is None for r in have):
            incomplete.append(key)
        elif any(is_void(r, set_name) for r in have):
            void.append(key)
        else:
            counted.append(key)
    return counted, void, incomplete


# ---- the table ---------------------------------------------------------

def _pct(k, n):
    return f"{k} of {n}" + (f" ({100.0 * k / n:.0f} %)" if n else '')


def _f(v, digits=2):
    return '-' if v is None else f"{v:.{digits}f}"


def _med(values):
    vals = [float(v) for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _keys_text(keys):
    return ' '.join(f"s{s}r{rep}" for s, rep in keys) or 'none'


def arm_block(label, arm, rows, keys):
    rs = [rows[(arm,) + k] for k in keys]
    n = len(rs)
    carries = sum(r.get('carries', 0) for r in rs)
    losses = sum(r.get('losses', 0) for r in rs)
    lo, hi = clopper_pearson(losses, carries)
    fin = [r for r in rs if finished(r)]
    drops = [r.get('drops') for r in rs]
    colls = [r.get('collisions') for r in rs]
    lines = [f"{label}  ({arm}): {n} episodes"]
    lines.append(f"  success                {_pct(sum(is_success(r) for r in rs), n)}")
    lines.append(f"  at the cap             {_pct(sum(bool(r.get('timed_out')) for r in rs), n)}")
    lines.append(f"  ended with no plan     {_pct(sum(is_no_plan(r) for r in rs), n)}")
    lines.append(f"  die carries {carries}, lost in the hand {losses}"
                 + (f" = {losses / carries:.2f} [{lo:.3f}, {hi:.3f}] (Clopper-Pearson 95 %)"
                    if carries else ''))
    lines.append(f"  pick tries {sum(r.get('pick_tries', 0) for r in rs)}")
    lines.append(f"  episodes with a drop   {sum(1 for d in drops if d)} of {n}"
                 f" (not detected in {sum(1 for d in drops if d is None)})")
    lines.append(f"  episodes with a collision  {sum(1 for c in colls if c)} of {n}"
                 f" (not detected in {sum(1 for c in colls if c is None)})")
    lines.append(f"  clean success          {_pct(sum(r.get('clean_success') is True for r in rs), n)}")
    lines.append(f"  medians over the {len(fin)} episodes that ran to the close: wall "
                 f"{_f(_med((r['metrics'] or {}).get('wall_s') for r in fin), 1)} s, planning per call "
                 f"{_f(_med(per_call(r) for r in fin))} s, execution "
                 f"{_f(_med((r['metrics'] or {}).get('exec_s') for r in fin), 1)} s, plan calls "
                 f"{_f(_med((r['metrics'] or {}).get('plan_calls') for r in fin), 0)}")
    return lines


def paired(test, rows, x, ref, keys):
    """(both, only ref, only x, neither, p) of a yes/no measure over keys."""
    both = only_ref = only_x = neither = 0
    for k in keys:
        a, b = test(rows[(x,) + k]), test(rows[(ref,) + k])
        if a and b:
            both += 1
        elif b:
            only_ref += 1
        elif a:
            only_x += 1
        else:
            neither += 1
    return both, only_ref, only_x, neither, mcnemar_exact(only_x, only_ref)


def paired_line(what, test, rows, x_label, x, ref_label, ref, keys):
    both, only_ref, only_x, neither, p = paired(test, rows, x, ref, keys)
    return (f"  {what}, {len(keys)} pairs: both {both}, only {ref_label} {only_ref}, "
            f"only {x_label} {only_x}, neither {neither}, exact McNemar p = {p:.3f}")


def loss_line(rows, x_label, x, ref_label, ref, keys):
    def tot(arm):
        rs = [rows[(arm,) + k] for k in keys]
        return sum(r.get('losses', 0) for r in rs), sum(r.get('carries', 0) for r in rs)
    lx, cx = tot(x)
    lr, cr = tot(ref)
    p = fisher_two_sided(lx, cx, lr, cr)
    return (f"  losses per carry: {x_label} {lx} of {cx}, {ref_label} {lr} of {cr}, "
            f"Fisher's exact p = {p:.3f}")


def time_lines(rows, x_label, x, ref_label, ref, keys):
    out = []
    pairs = [(rows[(x,) + k], rows[(ref,) + k]) for k in keys]
    pairs = [(a, b) for a, b in pairs if finished(a) and finished(b)]
    for what, get in (('planning time per plan call', per_call),
                      ('wall time', lambda r: (r.get('metrics') or {}).get('wall_s'))):
        vals = [(get(a), get(b)) for a, b in pairs]
        vals = [(a, b) for a, b in vals if a is not None and b is not None]
        diffs = [a - b for a, b in vals]
        slower = sum(1 for d in diffs if d > 0)
        faster = sum(1 for d in diffs if d < 0)
        out.append(f"  {what}, {len(vals)} pairs both ran to the close: {x_label} median "
                   f"{_f(_med(a for a, _ in vals))} s, {ref_label} {_f(_med(b for _, b in vals))} s, "
                   f"median difference {_f(_med(diffs))} s; {x_label} slower in {slower}, "
                   f"faster in {faster}, sign test p = {sign_test(slower, faster):.3f}")
    return out


def exec_ratio_line(rows, x_label, x, ref_label, ref, keys):
    ratios = []
    for k in keys:
        a, b = rows[(x,) + k], rows[(ref,) + k]
        if finished(a) and finished(b):
            ea, eb = a['metrics'].get('exec_s'), b['metrics'].get('exec_s')
            if ea is not None and eb:
                ratios.append(ea / eb)
    return (f"  cost: execution time of {x_label} over {ref_label}, {len(ratios)} pairs both ran "
            f"to the close: median ratio x{_f(_med(ratios))}")


def set_table(name, s, names):
    rows, arms = s['rows'], s['arms']
    labels = {arm: label for label, arm in names.items()}
    counted, void, incomplete = split_keys(rows, arms, name)
    what = ('the shipped scenes' if name == 'S' else 'the generated scenes')
    lines = [f"== set {name}, {what}: snapshot {s['snapshot']}, {len(rows)} rows, "
             f"{len(counted)} seed-and-repetition pairs counted for every arm",
             '   jobs: ' + '; '.join(s['jobs']),
             f"   void for every arm (a crash or another scene): {_keys_text(void)}",
             f"   incomplete (an arm has no row): {_keys_text(incomplete)}", '']
    for arm in arms:
        lines += arm_block(labels.get(arm, 'arm'), arm, rows, counted) + ['']
    have = set(arms)
    first = [k for k in counted if k[1] == 0]
    for x in ('deftrap', 'trap'):
        if names[x] in have and names['def'] in have:
            lines.append(f"(a) {x} against def")
            lines.append(loss_line(rows, x, names[x], 'def', names['def'], counted))
            lines.append(paired_line('success, by seed and repetition', is_success, rows,
                                     x, names[x], 'def', names['def'], counted))
            lines.append(paired_line('at the cap, by seed and repetition',
                                     lambda r: bool(r.get('timed_out')), rows,
                                     x, names[x], 'def', names['def'], counted))
            if name == 'G':
                lines.append(paired_line('success, by scene (the first repetition alone)',
                                         is_success, rows, x, names[x], 'def', names['def'], first))
            lines.append('')
    if names['deftrap_co'] in have and names['deftrap'] in have:
        x, ref = names['deftrap_co'], names['deftrap']
        lines.append('(b) deftrap_co against deftrap')
        lines.append(paired_line('success, by seed and repetition', is_success, rows,
                                 'deftrap_co', x, 'deftrap', ref, counted))
        lines.append(paired_line('ended with no plan, by seed and repetition', is_no_plan, rows,
                                 'deftrap_co', x, 'deftrap', ref, counted))
        lines += time_lines(rows, 'deftrap_co', x, 'deftrap', ref, counted)
        lines.append('')
    if names['deftrap'] in have and names['def'] in have:
        lines.append(exec_ratio_line(rows, 'deftrap', names['deftrap'], 'def', names['def'], counted))
        lines.append('')
    lines.append('every counted episode that is not a success')
    n = 0
    for k in counted:
        for arm in arms:
            r = rows[(arm,) + k]
            if not is_success(r):
                n += 1
                m = r.get('metrics') or {}
                lines.append(f"  {labels.get(arm, arm):10} seed {k[0]} rep {k[1]}: "
                             f"{'at the cap' if r.get('timed_out') else m.get('outcome')}, "
                             f"bridge {r.get('bridge_status')}, carries {r.get('carries')}, "
                             f"losses {r.get('losses')}, drops {r.get('drops')}, "
                             f"collisions {r.get('collisions')}")
    if not n:
        lines.append('  none')
    return lines


def table(job_dirs, names):
    sets = collect(job_dirs)
    lines = ['# tools/fd_defaults_table.py: the find_dice check of the candidate defaults',
             '# ours against ours through the bridge; the sets are not pooled; a row of this',
             '# table is never pooled with a laptop row or with BF#59 or BF#63 (other code)', '']
    for name in ('S', 'G'):
        if name in sets:
            lines += set_table(name, sets[name], names) + ['']
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('jobs', nargs='+', help='job folders (results.jsonl, metadata.json)')
    ap.add_argument('--def', dest='def_', default=DEF)
    ap.add_argument('--deftrap', default=DEFTRAP)
    ap.add_argument('--trap', default=TRAP)
    ap.add_argument('--co', default=CO)
    ap.add_argument('--out', help='also write the table to this file')
    a = ap.parse_args(argv)
    names = {'def': a.def_, 'deftrap': a.deftrap, 'trap': a.trap, 'deftrap_co': a.co}
    text = table(a.jobs, names)
    print(text)
    if a.out:
        with open(a.out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
