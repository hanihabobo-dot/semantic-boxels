#!/usr/bin/env python3
"""Path 6 (cluster eval of our code now, our thesis code and TAMPURA): the
phase 1a report, the tabletop benchmark, arm A (the tag plus TB-8/TB-20) against
arm B (the thesis commit 6b00cd7).  Runs on the laptop (stdlib only) on the job
tarballs tools/cluster/p6_tabletop.sbatch made, unpacked one folder each.

  python tools/p6_report.py --results DIR [DIR ...] --out OUT
      [--sweep eval_results/sweep_full_2026-05-28/aggregated.jsonl]
      [--stack-identical stack_identical_cells.json] [--cb113 aggregated.jsonl]
      [--sacct sacct.txt]

DIR is a job folder (it holds header.txt, A/, B/) or a folder of job folders.
sacct.txt is `sacct -P -j <job ids> --format=JobID,JobName,State,Elapsed,MaxRSS,ReqMem,NodeList`
(rule 16: the report prints each job's MaxRSS against its --mem and flags one over 6 GB).
Everything below was declared before the first run (PLAN.md sections 8 and 11):

  Counting rules of 14 and 15 Nov 2026 (Hani's words in tracks/meeting_2026-11-13/
  REVIEW_DECISIONS.md; they replace the validity and final-pass rules of PLAN.md
  sections 8 and 11):
  One result per cell: its FIRST real attempt.  A later attempt of the same cell
  (the runner's redo mode, a second job) is listed as a rerun and never counts, never
  replaces.  A void job or a cell with no timing_summary.json never started: it is
  not an attempt, the cell is "not full" and may run later as its first attempt.
  A run of the cell that ends in success, a pipeline failure or a runner timeout at
  the cap counts as such; a crash, no_summary (a hang or a start-up failure) and
  summary_mismatch (the banked summary belongs to another cell, D-08) are FAILURES of
  that arm; every rate has the number of crashed runs named beside it, never a second
  rate over the cells that "built".  Every crash of arm A (ours) is listed: each
  needs a BUGS.md entry with its cause (zero-crash rule of 15 Nov).  Arm B's pre-flight
  re-rolls a rejected seed (its seed then differs when the last "rerolling to seed=N"
  line in the cell's stdout.log names it): the replacement scene is never counted
  (status rerolled; its run is printed apart as an extra number).  A pre-flight
  rejection (preflight_rejected, rerolled) is a scene-level event, the same scenes in
  every arm of the sweeps it was seen in: PREFLIGHT_POLICY 'out' (the default, the
  coordinator's P-1 reading of 15 Nov) leaves those cells out of the numerators and
  denominators and names them beside every rate; 'failure' (--preflight failure, the
  reading of run sheet section 10 item 14) counts them as failures of that arm.  The
  one place the choice sits is PREFLIGHT_POLICY.
  The "timeout" label: both commits label every failed run without a give-up
  reason "timeout", so a timeout is counted only for a runner stub at the cap; an
  arm B stack row labelled timeout below the cap is a false success rejected at
  the end (CB#122); an arm A row labelled timeout below the cap is listed as "no
  give-up reason", to check.
  Tests: A against B pooled over find-and-tray-stack and stack only (Newcombe
  interval of the difference and Fisher's exact test, unpaired, over the declared
  cells, one rate, no all-cells variant beside it); stack's identical-layout cells
  also exact McNemar; holding A against B is a descriptive line, never pooled and
  never tested (B grasps by a weld, A by finger pads); B on the cluster against B
  in the thesis sweep: exact McNemar on the cells paired on the cell's own seed.
  Stall rule: two consecutive probe rows with the open on $W at 1 s or more are a
  stall; the cells overlapping one are listed and the pooled line is printed again
  without them.  No cell is re-run for a stall.
  Memory (rule 16, PLAN section 17; tools/memwatch.py): the block "memory" counts the
  cells that carry a record (OUT/<arm>/<label>/mem_cells.jsonl: MemAvailable at start and
  end, the lowest reading, peak RSS, the process sum, leftovers, new names in /dev/shm),
  prints the lowest MemAvailable and the highest peaks, every cell over 6 GB, every
  STOPPED_LOW_MEMORY file, each job's memory header lines and stray counts, and with
  --sacct each job's MaxRSS.  It never changes a count: memory is reported, not a validity rule.
  Drops and collisions (rule 18 of tracks/STATE.md; TB-22): a run's summary carries drops,
  collisions, how each was counted and clean_success; the block "drops and collisions" prints,
  per arm and goal, clean success beside success with the cells that had a drop or a collision.
  An arm whose summaries carry no such field (the thesis commit, which records neither) is
  "not measured", never 0.  Recorded only: no rate and no test above changes with them.
"""
import argparse
import collections
import csv
import glob
import json
import math
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import memwatch as mw  # noqa: E402
import p6_slots as ps  # noqa: E402

CAP_S = 1800
STALL_OPEN_S = 1.0
PROBE_PERIOD_S = 20
REROLL_RE = re.compile(r'rerolling to seed=(\d+)')
TARGET_RE = re.compile(r'^\s+Target:\s+(\S+)\s*$', re.M)
PREFLIGHT_RE = re.compile(r'^\[pre-flight\] seed \d+ rejected: ', re.M)
GOALS = ('holding', 'find-and-tray-stack', 'stack')
COUNTED = ('success', 'failure', 'timeout')        # a run that reached a result of the pipeline or the cap
CRASHED = ('crash', 'no_summary', 'summary_mismatch')   # runs of the cell that failed: failures, named beside the rate
PREFLIGHT_LIKE = ('preflight_rejected', 'rerolled')     # scene-level: no scene was run for this cell and seed
NEVER_STARTED = ('void', 'missing')                     # not an attempt: the cell is "not full"
# THE ONE PLACE the pre-flight choice sits (see the docstring): 'out' leaves a pre-flight rejection or a
# re-rolled cell out of the numerator and the denominator and names it beside the rate; 'failure' counts it
# as a failure of that arm.  Set by --preflight.
PREFLIGHT_POLICY = 'out'
STATUS_LABEL = {'crash': 'crashed', 'no_summary': 'no summary (hang or start-up failure)',
                'summary_mismatch': 'summary of another cell (D-08, a failure)',
                'preflight_rejected': 'pre-flight rejected', 'rerolled': 're-rolled (replacement never counts)'}


def in_set(status):
    """Does a cell with this final status belong to the rate's denominator?"""
    return status in COUNTED or status in CRASHED or (PREFLIGHT_POLICY == 'failure' and status in PREFLIGHT_LIKE)
# rule 18 (tracks/STATE.md): the fields a run's summary carries since TB-22 (world_counts.FIELDS)
R18_FIELDS = ('drops', 'collisions', 'drop_detector', 'collision_detector', 'clean_success')


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------

def wilson(k, n, z=1.96):
    if not n:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def newcombe(k1, n1, k2, n2):
    """(difference p1 - p2, lower, upper): Newcombe's hybrid score interval
    (method 10) from the two Wilson intervals."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    d = p1 - p2
    return d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def fisher_exact(k1, n1, k2, n2):
    """Two-sided Fisher's exact test of k1/n1 against k2/n2 (the sum of the
    hypergeometric probabilities not above the observed table's)."""
    total_k, total_n = k1 + k2, n1 + n2
    lo, hi = max(0, total_k - n2), min(total_k, n1)

    def prob(x):
        return math.comb(n1, x) * math.comb(n2, total_k - x) / math.comb(total_n, total_k)

    observed = prob(k1)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= observed * (1 + 1e-7)))


def mcnemar_exact(b, c):
    """Two-sided exact McNemar (binomial on the discordant pairs)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def median(values):
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def fmt(v, d=1):
    return '-' if v is None else f"{v:.{d}f}"


def pct(k, n):
    return f"{100.0 * k / n:5.1f}" if n else '  n/a'


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def read_text(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return None


def read_json(path):
    text = read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def find_jobs(roots):
    jobs = []
    for root in roots:
        if os.path.isfile(os.path.join(root, 'header.txt')):
            jobs.append(root)
        else:
            jobs += sorted(os.path.dirname(p) for p in glob.glob(os.path.join(root, '*', 'header.txt')))
    return jobs


def load_probe(job):
    """[(epoch, open seconds)] of a job's io_probe.tsv."""
    text = read_text(os.path.join(job, 'io_probe.tsv'))
    rows = []
    for line in (text or '').splitlines()[1:]:
        parts = line.split('\t')
        if len(parts) >= 3:
            try:
                rows.append((float(parts[1]), float(parts[2])))
            except ValueError:
                pass
    return rows


def load_attempts(jobs):
    """Every cell attempt of every job: dicts with the arm, tag, the job and
    folder it came from, the parsed summary (or None), the stdout.log text, the
    run directory the runner named and the summary's modification time."""
    attempts = []
    for job in jobs:
        void = read_text(os.path.join(job, 'VOID'))
        name = os.path.basename(os.path.normpath(job))
        for arm in ps.ARMS:
            for folder in sorted(glob.glob(os.path.join(job, arm, '*', ''))):
                label = os.path.basename(os.path.normpath(folder))
                if label.startswith('slot_smoke') or not os.path.isdir(os.path.join(folder, 'cells')):
                    continue
                for cell_dir in sorted(glob.glob(os.path.join(folder, 'cells', '*', ''))):
                    tag = os.path.basename(os.path.normpath(cell_dir))
                    ts_path = os.path.join(cell_dir, 'timing_summary.json')
                    attempts.append({
                        'arm': arm, 'tag': tag, 'job': name, 'label': label, 'job_dir': job,
                        'redo': label.startswith('redo'), 'void': void,
                        'ts': read_json(ts_path),
                        'stdout': read_text(os.path.join(cell_dir, 'stdout.log')),
                        'run_dir': (read_text(os.path.join(cell_dir, 'run_dir.txt')) or '').strip() or None,
                        'mtime': os.path.getmtime(ts_path) if os.path.isfile(ts_path) else None})
    return attempts


def expected_cells(arm):
    return {ps.expected_tag(c): c for s in range(ps.N_SLOTS) for c in ps.slot_cells(arm, s)}


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

REASON_LABELS = {'planner_failed': 'no plan found', 'all_searched': 'search exhausted',
                 'physics_mismatch': 'false success (physics mismatch)',
                 'no_plan_binding_death': 'no plan (binding death)', 'pick_giveup': 'pick given up'}


def failure_label(arm, goal, reason, stub, wall, cap=CAP_S):
    """The failure mode of a counted failure (the timeout label rule)."""
    if reason == 'timeout':
        if stub or (wall is not None and wall >= 0.95 * cap):
            return 'timed out at the cap'
        if arm == 'B' and goal == 'stack':
            return 'false success rejected at the end (CB#122)'
        return 'no give-up reason (to check)'
    return REASON_LABELS.get(reason, reason or 'unlabelled failure')


def difficulty_of(cell):
    return cell['n_occluders']          # occluders on random-pairs, tower height on stack


def classify(att, cell, cap=CAP_S):
    """The attempt's status and facts: status is one of COUNTED, CRASHED, PREFLIGHT_LIKE or NEVER_STARTED."""
    arm, ts = att['arm'], att['ts']
    out = {'tag': att['tag'], 'arm': arm, 'job': att['job'], 'label': att['label'], 'redo': att['redo'],
           'goal': cell['goal'], 'scene': cell['scene'], 'difficulty': difficulty_of(cell), 'seed': cell['seed'],
           'eff_seed': cell['seed'], 'rerolled': False, 'wall': None, 'plan_time': None, 'plan_count': None,
           'failure': None, 'why': '', 'mtime': att['mtime'], 'run_dir': att['run_dir'],
           'success': False, '_stdout': att['stdout'], '_ts': ts}
    if att['void']:
        return dict(out, status='void', why=f"job {att['job']} is void: {att['void'].strip()[:120]}")
    if not isinstance(ts, dict):
        return dict(out, status='missing', why='no timing_summary.json')
    reason = ts.get('exit_reason')
    out['wall'] = ts.get('wall_clock_s')
    for k in R18_FIELDS:                     # rule 18: the run's own counts (a runner stub carries them too)
        out[k] = ts.get(k)
    rc = ts.get('run_config')
    if not isinstance(rc, dict):                                  # a runner stub
        if reason == 'timeout':
            return dict(out, status='timeout', failure='timed out at the cap', success=False)
        if isinstance(reason, str) and reason.startswith('crash_exit'):
            return dict(out, status='crash', why=reason)
        if reason == 'summary_mismatch':
            return dict(out, status='summary_mismatch', why=str(ts.get('summary_mismatch'))[:200])
        if reason == 'preflight_rejected' or (
                reason == 'no_summary' and att['stdout'] and PREFLIGHT_RE.search(att['stdout'])):
            return dict(out, status='preflight_rejected', why=str(ts.get('preflight_message') or '')[:200])
        return dict(out, status='no_summary', why=str(reason))
    mismatch = []
    for key, want in (('scene', cell['scene']), ('goal', cell['goal']), ('baseline', cell['baseline']),
                      ('unit_costs', cell['unit_costs'])):
        if rc.get(key) != want:
            mismatch.append(f"{key}={rc.get(key)!r} (cell {want!r})")
    if cell['scene'] == 'stack' and rc.get('stack_height') != cell['n_occluders']:
        mismatch.append(f"stack_height={rc.get('stack_height')!r} (cell {cell['n_occluders']!r})")
    eff = rc.get('seed')
    out['eff_seed'] = eff
    if eff != cell['seed']:
        last = REROLL_RE.findall(att['stdout'] or '')
        if arm == 'B' and last and int(last[-1]) == eff:
            out['rerolled'] = True               # B's pre-flight re-rolled the seed: the cell's own run
        else:
            mismatch.append(f"seed={eff!r} (cell {cell['seed']!r})")
    if cell['scene'] == 'random-pairs' and not out['rerolled'] and rc.get('n_occluders') != cell['n_occluders']:
        mismatch.append(f"n_occluders={rc.get('n_occluders')!r} (cell {cell['n_occluders']!r})")
    if mismatch:
        return dict(out, status='summary_mismatch', why='; '.join(mismatch))
    out['plan_time'] = ts.get('total_planning_time_s')
    out['plan_count'] = ts.get('plan_count')
    out['rc'] = rc
    out['first_replan'] = ((ts.get('boxel_counts_per_replan') or [None])[0])
    if out['rerolled']:                          # the replacement scene is never the cell's result (15 Nov)
        return dict(out, status='rerolled', why=f"seed {cell['seed']} was re-rolled to {eff}",
                    rerolled_success=bool(ts.get('success')))
    if ts.get('success'):
        return dict(out, status='success', success=True)
    return dict(out, status='failure', success=False,
                failure=failure_label(arm, cell['goal'], reason, False, out['wall'], cap), exit_reason=reason)


def final_cells(attempts, cap=CAP_S):
    """arm -> tag -> {'final': classified attempt, 'attempts': [all classified], 'reruns': [...]}: the
    FIRST real attempt is the cell's result, whatever it was (a crash is a failure and no later attempt
    replaces it); a void or missing attempt never started and is skipped; later real attempts are listed
    as reruns and never count.  A cell with no real attempt has the first never-started attempt as final,
    or None when there is none."""
    result = {arm: {} for arm in ps.ARMS}
    for arm in ps.ARMS:
        cells = expected_cells(arm)
        by_tag = collections.defaultdict(list)
        for a in attempts:
            if a['arm'] == arm and a['tag'] in cells:
                by_tag[a['tag']].append(a)
        for tag, cell in cells.items():
            atts = sorted(by_tag.get(tag, []), key=lambda a: (a['redo'], a['job'], a['label']))
            classified = [classify(a, cell, cap) for a in atts]
            real = [c for c in classified if c['status'] not in NEVER_STARTED]
            final = real[0] if real else (classified[0] if classified else None)
            result[arm][tag] = {'final': final, 'attempts': classified, 'cell': cell, 'reruns': real[1:]}
    return result


def unknown_tags(attempts):
    """Cell folders that no slot of that arm names: a wrong snapshot or a stray folder."""
    known = {arm: expected_cells(arm) for arm in ps.ARMS}
    return sorted({(a['arm'], a['tag']) for a in attempts if a['tag'] not in known[a['arm']]})


def claims(attempts):
    """Run directories named by more than one cell of the same job and arm (a banked summary)."""
    seen = collections.defaultdict(list)
    for a in attempts:
        if a['run_dir']:
            seen[(a['job'], a['arm'], a['run_dir'])].append(a['tag'])
    return {k: v for k, v in seen.items() if len(v) > 1}


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------

def group_cells(res, arm, goal=None, difficulty=None):
    out = []
    for tag, rec in res[arm].items():
        c = rec['cell']
        if goal is not None and c['goal'] != goal:
            continue
        if difficulty is not None and c['n_occluders'] != difficulty:
            continue
        out.append(rec)
    return out


def tally(recs, exclude=frozenset()):
    """Counts of a group of cell records.  'all' is the declared cells; 'n' the cells in the rate's
    denominator (in_set: a result, a crash or hang counted as a failure, and under PREFLIGHT_POLICY
    'failure' a pre-flight rejection); 'k' the successes; 'crashed' the crash, no_summary and
    summary_mismatch runs among the n (named beside the rate); 'other' the cells left out, by status
    ('no attempt' for a cell nobody started); 'cells' the runs that reached a result (timing)."""
    finals = [r['final'] for r in recs if r['final'] is not None and (r['final']['arm'], r['final']['tag']) not in exclude]
    n_all = len(recs) - sum(1 for r in recs if r['final'] is not None and (r['final']['arm'], r['final']['tag']) in exclude)
    inside = [f for f in finals if in_set(f['status'])]
    k = sum(1 for f in inside if f['success'])
    other = collections.Counter(f['status'] for f in finals if not in_set(f['status']))
    other['no attempt'] = n_all - len(finals)
    crashed = collections.Counter(f['status'] for f in inside if f['status'] in CRASHED)
    return {'all': n_all, 'n': len(inside), 'k': k, 'other': {s: n for s, n in other.items() if n},
            'crashed': dict(crashed), 'cells': [f for f in inside if f['status'] in COUNTED]}


def rate_line(t):
    """One rate over the declared set (crashes and hangs are failures); no second rate beside it."""
    lo, hi = wilson(t['k'], t['n'])
    return (f"{t['n']:3d} runs  {t['k']:3d} ok  {pct(t['k'], t['n'])} %  [{100 * lo:4.1f}, {100 * hi:4.1f}]"
            f"   declared {t['all']:3d}")


def beside(t):
    """What stands beside a rate: the crashed runs (counted as failures) and the cells left out, named."""
    parts = []
    if t['crashed']:
        parts.append(f"crashed: {sum(t['crashed'].values())} of {t['n']} ("
                     + ', '.join(f"{n} {s}" for s, n in sorted(t['crashed'].items())) + ')')
    if t['other']:
        parts.append('left out: ' + ', '.join(f"{n} {s}" for s, n in sorted(t['other'].items())))
    return ('  ' + '; '.join(parts)) if parts else ''


def rates_table(res, arm, lines):
    lines.append(f"arm {arm}: success over the declared cells, first attempts, a crash or hang a failure (95 % Wilson)")
    for goal in GOALS:
        for d in ps.DIFFICULTIES:
            t = tally(group_cells(res, arm, goal, d))
            lines.append(f"  {goal:20} {'height' if goal == 'stack' else 'occ'} {d}  {rate_line(t)}{beside(t)}")
        t = tally(group_cells(res, arm, goal))
        lines.append(f"  {goal:20} all      {rate_line(t)}{beside(t)}")


def failure_modes(res, arm, lines):
    lines.append(f"arm {arm}: failure modes of the failures")
    for goal in GOALS:
        modes = collections.Counter()
        for rec in group_cells(res, arm, goal):
            f = rec['final']
            if f is None or not in_set(f['status']) or f['success']:
                continue
            modes[f['failure'] or STATUS_LABEL.get(f['status'], f['status'])] += 1
        lines.append(f"  {goal:20} " + (', '.join(f"{n} {m}" for m, n in modes.most_common()) or 'none'))


def clean_of(f):
    """Rule 18's clean success of a counted cell: a failure is never clean; a success whose drops or
    collisions nothing counted is unknown (None), never clean by default."""
    if not f.get('success'):
        return False
    d, c = f.get('drops'), f.get('collisions')
    if d is None or c is None:
        return None
    return d == 0 and c == 0


def rule18_lines(res, lines):
    """Rule 18: per arm and goal the drops, the collisions and clean success beside success, and how each
    count was taken.  Recorded only: no rate above changes.  An arm whose summaries carry no such field
    (the thesis commit; a snapshot from before TB-22) is said to be not measured, never printed as 0."""
    lines.append("drops and collisions (rule 18; recorded, they change no rate above): a drop is a held object that "
                 "left the gripper outside a place; clean = success with no drop and no collision; a count that "
                 "nothing took is never printed as 0")
    measured = {}
    for arm in ps.ARMS:
        built = [rec['final'] for rec in res[arm].values()
                 if rec['final'] is not None and in_set(rec['final']['status'])]
        measured[arm] = any(f.get('drop_detector') is not None for f in built)
        if not measured[arm]:
            lines.append(f"  arm {arm}: its summaries carry no drop or collision field"
                         + (" (the thesis code records neither and holds the object by a weld constraint)"
                            if arm == 'B' else " (a snapshot from before TB-22?)")
                         + ": clean success is not measured for it")
            continue
        lines.append(f"  arm {arm}:  {'goal':20} {'built':>5} {'ok':>4} {'clean':>10} {'95 % Wilson':>14} "
                     f"{'unknown':>7} {'cells with a drop':>17} {'drops':>5} {'cells with a collision':>22} "
                     f"{'collisions':>10} {'no count':>8}")
        for goal in GOALS + ('all',):
            g = [f for f in built if goal == 'all' or f['goal'] == goal]
            verdicts = [clean_of(f) for f in g]
            k = sum(1 for f in g if f.get('success'))
            kc = sum(1 for v in verdicts if v is True)
            unknown = sum(1 for v in verdicts if v is None)
            drops = [f['drops'] for f in g if isinstance(f.get('drops'), (int, float))]
            colls = [f['collisions'] for f in g if isinstance(f.get('collisions'), (int, float))]
            no_count = sum(1 for f in g if f.get('drops') is None or f.get('collisions') is None)
            if unknown == 0:
                lo, hi = wilson(kc, len(g))
                cell, ci = f"{kc:10d}", f"[{100 * lo:4.1f}, {100 * hi:4.1f}]"
            else:
                cell, ci = f"{f'at least {kc}':>10}", '-'
            lines.append(f"          {goal:20} {len(g):5d} {k:4d} {cell} {ci:>14} {unknown:7d} "
                         f"{sum(1 for v in drops if v > 0):17d} {int(sum(drops)):5d} "
                         f"{sum(1 for v in colls if v > 0):22d} {int(sum(colls)):10d} {no_count:8d}")
        for field in ('drop_detector', 'collision_detector'):
            texts = collections.Counter(str(f.get(field) or 'no field in the summary') for f in built)
            for t, n in texts.most_common():
                lines.append(f"    {field} ({n} cells): {t[:200]}")
    if not all(measured.values()):
        who = [a for a in ps.ARMS if measured[a]]
        lines.append("  A against B on clean success: not printed (it is measured for "
                     + (f"{' and '.join(who)} only" if who else 'neither arm') + ")")


def status_accounting(res, arm, lines):
    c = collections.Counter()
    for rec in res[arm].values():
        c[rec['final']['status'] if rec['final'] else 'no attempt'] += 1
    lines.append(f"arm {arm}: {sum(c.values())} cells: " + ', '.join(f"{n} {s}" for s, n in sorted(c.items())))


def first_attempt_trouble(res, lines):
    """Cells whose first attempt crashed, hung, did not match, or was not a run (a pre-flight rejection or
    a re-roll), and the reruns that exist (never counted)."""
    lines.append('cells whose first attempt did not reach a result (a crash, hang or mismatch is a failure, a pre-flight '
                 'rejection or re-roll follows PREFLIGHT_POLICY; none is run again, a rerun never counts):')
    n = 0
    for arm in ps.ARMS:
        for tag, rec in res[arm].items():
            f = rec['final']
            if f is not None and (f['status'] in CRASHED or f['status'] in PREFLIGHT_LIKE):
                n += 1
                lines.append(f"  {arm} {tag}: {f['status']} ({f['why'][:100]}); counts as "
                             f"{'a failure' if in_set(f['status']) else 'left out'}"
                             + (f"; {len(rec['reruns'])} rerun(s) listed apart, never counted" if rec['reruns'] else ''))
    if not n:
        lines.append('  none')
    reruns = [(arm, tag, rec['reruns']) for arm in ps.ARMS for tag, rec in res[arm].items() if rec['reruns']]
    if reruns:
        lines.append(f"reruns (never counted, {sum(len(r) for _, _, r in reruns)} attempts on {len(reruns)} cells): "
                     + '; '.join(f"{a} {t}: " + ', '.join(f"{x['status']} ({x['label']})" for x in r) for a, t, r in reruns[:6])
                     + (' ...' if len(reruns) > 6 else ''))


def completeness_lines(res, lines):
    """Planned against rows, 'not full', the zero-crash rule's list for arm A, and the cells where both
    arms failed to run (a possible shared-code cause)."""
    lines.append('completeness (planned runs against rows, REVIEW 4.5 item 3):')
    full = True
    for arm in ps.ARMS:
        recs = list(res[arm].values())
        planned = len(recs)
        started = sum(1 for r in recs if r['final'] is not None and r['final']['status'] not in NEVER_STARTED)
        never = [t for t, r in res[arm].items() if r['final'] is None or r['final']['status'] in NEVER_STARTED]
        crashed = [t for t, r in res[arm].items() if r['final'] is not None and r['final']['status'] in CRASHED]
        full = full and not never and not crashed
        lines.append(f"  arm {arm}: planned {planned}, rows {started}; never started {len(never)}"
                     + (f" (first: {never[:3]})" if never else '') + f"; crashed {len(crashed)}")
    lines.append('  ' + ('full: every planned cell has a first attempt and none crashed' if full else
                          'NOT FULL: a cell never started or a run crashed (a crash is a failure and is counted; '
                          'a cell that never started runs later as its first attempt)'))
    a_crash = [(t, r['final']['status'], r['final']['why'][:80]) for t, r in res['A'].items()
               if r['final'] is not None and r['final']['status'] in CRASHED]
    lines.append(f"  crashes of arm A, ours (zero-crash rule: each needs a BUGS.md entry with its investigated cause): "
                 f"{len(a_crash)}" + (': ' + '; '.join(f"{t} {s} ({w})" for t, s, w in a_crash[:8]) if a_crash else ''))
    both = [t for t, r in res['A'].items() if r['final'] is not None and r['final']['status'] in CRASHED
            and res['B'].get(t, {}).get('final') is not None and res['B'][t]['final']['status'] in CRASHED]
    lines.append(f"  cells where A and B both failed to run (crash, no summary, mismatch): {len(both)}"
                 + (f" {both[:6]}: a shared-code cause would eliminate the seed and replace it by a declared new one "
                    f"(a run not made here); each counts as a failure for both until then" if both else ''))


def pooled(res, arm, goals, exclude=frozenset()):
    t = {'all': 0, 'n': 0, 'k': 0}
    for g in goals:
        x = tally(group_cells(res, arm, g), exclude)
        for key in t:
            t[key] += x[key]
    return t


def a_vs_b(res, exclude, lines, heading):
    lines.append(heading)
    for variant, key in (('over the declared cells, first attempts, a crash or hang a failure (the one rate)', 'n'),):
        a = pooled(res, 'A', ('find-and-tray-stack', 'stack'), exclude)
        b = pooled(res, 'B', ('find-and-tray-stack', 'stack'), exclude)
        na, nb = a[key], b[key]
        if not na or not nb:
            lines.append(f"  {variant}: no cells")
            continue
        d, lo, hi = newcombe(a['k'], na, b['k'], nb)
        lines.append(f"  {variant}: A {a['k']}/{na} = {100 * a['k'] / na:.1f} %, B {b['k']}/{nb} = {100 * b['k'] / nb:.1f} %; "
                     f"A - B = {100 * d:+.1f} points, 95 % Newcombe [{100 * lo:+.1f}, {100 * hi:+.1f}]; "
                     f"Fisher exact p = {fisher_exact(a['k'], na, b['k'], nb):.3g} (unpaired)")


def per_goal_ab(res, lines):
    lines.append('per goal, descriptive (declared cells, first attempts; the holding line is never pooled or tested):')
    for goal in GOALS:
        a, b = tally(group_cells(res, 'A', goal)), tally(group_cells(res, 'B', goal))
        lines.append(f"  {goal:20} A {a['k']:3d}/{a['n']:3d} = {pct(a['k'], a['n'])} %   B {b['k']:3d}/{b['n']:3d} = {pct(b['k'], b['n'])} %"
                     + ('   (A scores a pad squeeze of 0.5 N, B a weld constraint: two different claims)' if goal == 'holding' else ''))
    for goal in ('find-and-tray-stack',):
        for arm in ps.ARMS:
            rej = sum(1 for r in group_cells(res, arm, goal) if r['final'] and r['final']['status'] == 'preflight_rejected')
            rer = [r['final'] for r in group_cells(res, arm, goal) if r['final'] and r['final']['status'] == 'rerolled']
            lines.append(f"  {goal:20} arm {arm}: {rej} pre-flight rejected, {len(rer)} cells re-rolled by the arm's runner "
                         f"(neither is run again; both follow PREFLIGHT_POLICY = {PREFLIGHT_POLICY})")
            if rer:
                lines.append("    re-rolled (cell seed to the seed that ran, the replacement never counts): "
                             + ', '.join(f"occ{f['difficulty']} {f['seed']}>{f['eff_seed']}" for f in rer[:12])
                             + (' ...' if len(rer) > 12 else ''))
        rr = [r['final'] for r in group_cells(res, 'B', goal) if r['final'] and r['final']['status'] == 'rerolled']
        kr = sum(1 for f in rr if f.get('rerolled_success'))
        lines.append(f"  {goal:20} B's runs on the replacement seeds, an extra number apart from every rate: {kr}/{len(rr)}")


def stack_identical_pairs(res, identical, lines):
    if not identical:
        lines.append("stack's identical-layout cells: no list given (--stack-identical)")
        return
    both = a_only = b_only = neither = 0
    used = 0
    for seed, height in identical:
        tag = ps.expected_tag(ps.stack_cell(height, seed))
        fa, fb = res['A'].get(tag, {}).get('final'), res['B'].get(tag, {}).get('final')
        if not fa or not fb or not in_set(fa['status']) or not in_set(fb['status']):
            continue
        used += 1
        if fa['success'] and fb['success']:
            both += 1
        elif fa['success']:
            a_only += 1
        elif fb['success']:
            b_only += 1
        else:
            neither += 1
    lines.append(f"stack, the {len(identical)} cells whose spawned layout is identical in both commits (a code-only paired subset): "
                 f"{used} counted in both arms; both succeed {both}, only A {a_only}, only B {b_only}, neither {neither}; "
                 f"exact McNemar p = {mcnemar_exact(a_only, b_only):.3g}")


def sweep_key(rc):
    if rc.get('scene') == 'stack':
        return ('stack', rc.get('goal'), rc.get('stack_height'), rc.get('seed'))
    return (rc.get('scene'), rc.get('goal'), rc.get('n_occluders'), rc.get('seed'))


def b_against_sweep(res, sweep_rows, lines):
    """B on the cluster against B in the thesis sweep: exact McNemar on the cells paired on the seed run."""
    lines.append('B on the cluster against B in the thesis sweep (the noise floor and the reproduction check):')
    if not sweep_rows:
        lines.append('  no sweep rows given (--sweep)')
        return
    index = {}
    dup = 0
    for r in sweep_rows:
        rc = r.get('run_config') if isinstance(r.get('run_config'), dict) else r
        if rc.get('baseline') != 'semantic' or rc.get('unit_costs') or rc.get('min_boxel_size') not in (None, ''):
            continue
        if rc.get('scene') not in ('random-pairs', 'stack'):
            continue
        key = sweep_key(rc)
        if key in index:
            dup += 1
            continue
        index[key] = r
    both = c_only = s_only = neither = 0
    unpaired = []
    per_goal = collections.defaultdict(lambda: [0, 0])      # goal -> [pairs, agreeing]
    cluster_cap = sweep_cap = 0
    for tag, rec in res['B'].items():
        f = rec['final']
        if f is None or not in_set(f['status']) or f['status'] in PREFLIGHT_LIKE:
            continue                         # a re-rolled or rejected cell has no run of its own to pair
        cell = rec['cell']
        key = ('stack', 'stack', cell['n_occluders'], cell['seed']) if cell['scene'] == 'stack' \
            else ('random-pairs', cell['goal'], cell['n_occluders'], cell['seed'])
        r = index.get(key)
        if r is None:
            unpaired.append(tag)
            continue
        sweep_ok = bool(r.get('success'))
        if f['success'] and sweep_ok:
            both += 1
        elif f['success']:
            c_only += 1
        elif sweep_ok:
            s_only += 1
        else:
            neither += 1
        per_goal[cell['goal']][0] += 1
        per_goal[cell['goal']][1] += (f['success'] == sweep_ok)
        cluster_cap += f['status'] == 'timeout'
        sweep_cap += (r.get('exit_reason') == 'timeout' and (r.get('wall_clock_s') or 0) >= 0.95 * CAP_S)
    pairs = both + c_only + s_only + neither
    lines.append(f"  {pairs} cells paired on the cell's own seed (a re-rolled or rejected cell is not paired, a crash is a failure); "
                 f"both succeed {both}, only the cluster {c_only}, only the sweep {s_only}, neither {neither}; "
                 f"exact McNemar p = {mcnemar_exact(c_only, s_only):.3g}; agreement {pct(both + neither, pairs)} %")
    lines.append('  by goal (pairs, agreeing): ' + ', '.join(f"{g} {v[0]}/{v[1]}" for g, v in sorted(per_goal.items())))
    lines.append(f"  cells at the cap: cluster {cluster_cap}, sweep {sweep_cap} (over the paired cells)"
                 + (f"; {len(unpaired)} cluster cells have no sweep row: {unpaired[:6]}{' ...' if len(unpaired) > 6 else ''}" if unpaired else ''))
    if dup:
        lines.append(f"  ({dup} sweep rows shared a key with an earlier one and were ignored)")


def timing_lines(res, lines):
    lines.append('time (runs that reached a result): median planning time of the successes, median wall time, cells at the cap, total wall hours')
    for arm in ps.ARMS:
        for goal in GOALS:
            cells = tally(group_cells(res, arm, goal))['cells']
            succ = [c for c in cells if c['success']]
            lines.append(f"  {arm} {goal:20} plan {fmt(median(c['plan_time'] for c in succ))} s   wall {fmt(median(c['wall'] for c in cells))} s   "
                         f"at the cap {sum(1 for c in cells if c['status'] == 'timeout')}   total {fmt(sum((c['wall'] or 0) for c in cells) / 3600, 2)} h")


def stall_windows(job):
    rows = load_probe(job)
    wins = []
    for (e0, o0), (e1, o1) in zip(rows, rows[1:]):
        if o0 >= STALL_OPEN_S and o1 >= STALL_OPEN_S:
            wins.append((e0, e1 + PROBE_PERIOD_S))
    return wins


def stalled_cells(attempts, jobs):
    """{(arm, tag)} of the final-or-not attempts whose run overlapped a stall of their job's probe."""
    windows = {os.path.basename(os.path.normpath(j)): stall_windows(j) for j in jobs}
    hit = set()
    for a in attempts:
        ts = a['ts']
        if a['mtime'] is None or not isinstance(ts, dict) or ts.get('wall_clock_s') is None:
            continue
        end, start = a['mtime'], a['mtime'] - ts['wall_clock_s']
        if any(start < w1 and end > w0 for w0, w1 in windows.get(a['job'], [])):
            hit.add((a['arm'], a['tag']))
    return hit, {j: len(w) for j, w in windows.items()}


def provenance(jobs, lines):
    lines.append('jobs:')
    trees = collections.defaultdict(set)
    for job in jobs:
        head = (read_text(os.path.join(job, 'header.txt')) or '').splitlines()
        name = os.path.basename(os.path.normpath(job))
        void = read_text(os.path.join(job, 'VOID'))
        first = head[0] if head else ''
        host = (re.search(r'host (\S+)', first) or [None, '?'])[1]
        mode = (re.search(r'mode (\S+)', first) or [None, '?'])[1]
        cpu = next((l for l in head if l.startswith('cpu ')), 'cpu ?')[4:].split('  ')[0]
        lines.append(f"  {name}: host {host}, mode {mode}, {cpu}" + (f"  VOID: {void.strip()[:100]}" if void else ''))
        for l in head:
            m = re.match(r'snapshot ([AB]) (\S+): (\d+) files, tree hash (\w+)', l)
            if m:
                trees[m.group(1)].add((m.group(2), m.group(4)))
    for arm, s in sorted(trees.items()):
        lines.append(f"  snapshot {arm}: " + ('; '.join(f"{n} tree hash {h}" for n, h in sorted(s))
                                              + ('' if len(s) == 1 else '   <-- MORE THAN ONE SNAPSHOT, check')))


# ---------------------------------------------------------------------------
# memory (rule 16)
# ---------------------------------------------------------------------------

SIZE_RE = re.compile(r'^\s*([\d.]+)\s*([KMGT]?)[nc]?\s*$', re.I)
SIZE_KB = {'': 1, 'K': 1, 'M': 1024, 'G': 1024 ** 2, 'T': 1024 ** 3}
JOB_ID_RE = re.compile(r'\sjob (\d+)')
HEADER_MEM_PREFIXES = ('memory at the start:', 'memory after the job:')


def slurm_kb(text):
    """kB of a Slurm size ('2345678K', '12G', '12Gn', '4000Mc'; no unit is kB as in /proc), None if it is not one."""
    m = SIZE_RE.match(text or '')
    return int(float(m.group(1)) * SIZE_KB[m.group(2).upper()]) if m else None


def parse_sacct(text):
    """{job id: {name, state, elapsed, req_mem, node, max_rss_kb}} from `sacct -P` output with the columns
    JobID,JobName,State,Elapsed,MaxRSS,ReqMem,NodeList (their order is read from the header line, other
    columns are ignored).  MaxRSS sits on a job's steps (.batch, .extern, .0), so a job's max_rss_kb is
    the largest of its steps'."""
    rows = [ln for ln in (text or '').splitlines() if ln.strip()]
    head = [h.strip() for h in rows[0].split('|')] if rows else []
    if 'JobID' not in head:
        return {}
    col = {h: i for i, h in enumerate(head)}
    jobs = {}
    for ln in rows[1:]:
        f = [x.strip() for x in ln.split('|')]

        def get(name, f=f):
            i = col.get(name)
            return f[i] if i is not None and i < len(f) else ''
        base, _, step = get('JobID').partition('.')
        if not base:
            continue
        j = jobs.setdefault(base, {'max_rss_kb': None})
        rss = slurm_kb(get('MaxRSS'))
        if rss is not None and (j['max_rss_kb'] is None or rss > j['max_rss_kb']):
            j['max_rss_kb'] = rss
        if not step:
            j.update(name=get('JobName'), state=get('State'), elapsed=get('Elapsed'),
                     req_mem=get('ReqMem'), node=get('NodeList'))
    return jobs


def header_job_id(job):
    """The Slurm job id in the first line of a job folder's header.txt ('host node-a  job 5062001  ...')."""
    first = (read_text(os.path.join(job, 'header.txt')) or '').splitlines()[:1]
    m = JOB_ID_RE.search(first[0]) if first else None
    return m.group(1) if m else None


def mem_records(jobs):
    """Every cell's memory record (OUT/<arm>/<label>/mem_cells.jsonl, written by tools/memwatch.py's guard
    around the runner's run_cell) with where it came from, and the STOPPED_LOW_MEMORY files: ([record], [line])."""
    recs, stops = [], []
    for job in jobs:
        name = os.path.basename(os.path.normpath(job))
        for arm in ps.ARMS:
            for folder in sorted(glob.glob(os.path.join(job, arm, '*', ''))):
                label = os.path.basename(os.path.normpath(folder))
                for r in mw.read_jsonl(os.path.join(folder, 'mem_cells.jsonl')):
                    recs.append(dict(r, job=name, arm=arm, folder=label,
                                     label=f"{name} {arm} {label} {r.get('tag')}"))
                stop = read_text(os.path.join(folder, mw.STOP_FILE))
                if stop and stop.strip():
                    stops.append(f"{stop.splitlines()[0]}  ({name} {arm} {label})")
    return recs, stops


def stray_count(job):
    """The processes of ours that strays.txt lists after the arms of a job (its 'after arm ...' lines
    are headings); None when the job has no strays.txt."""
    text = read_text(os.path.join(job, 'strays.txt'))
    if text is None:
        return None
    return sum(1 for ln in text.splitlines() if ln.strip() and not ln.startswith('after arm'))


def mem_lines(jobs, attempts, lines, sacct=None):
    """The memory block of the report: what the guard recorded around each cell, the jobs' own header and
    stray lines, and (with sacct text) each job's MaxRSS.  Reported only; no count depends on it."""
    recs, stops = mem_records(jobs)
    lines.append('memory (rule 16, PLAN section 17; tools/memwatch.py reads /proc around each cell, the runners are not edited):')
    cells = {(a['job'], a['arm'], a['label'], a['tag']) for a in attempts}
    have = {(r['job'], r['arm'], r['folder'], r.get('tag')) for r in recs}
    covered = len(have & cells)
    lines.append(f"  {covered} of {len(cells)} cell attempts carry a memory record"
                 + ('' if covered == len(cells) else " (a cell without one was banked by an earlier run, or ran before the guard)"))
    lines += ['  ' + ln for ln in mw.summary_lines(recs)]
    lines += (['  ' + s for s in stops] if stops else ['  no STOPPED_LOW_MEMORY file'])
    for job in jobs:
        name = os.path.basename(os.path.normpath(job))
        head = (read_text(os.path.join(job, 'header.txt')) or '').splitlines()
        mem_head = [ln for ln in head if ln.startswith(HEADER_MEM_PREFIXES)]
        n = stray_count(job)
        lines += [f"  {name}: {ln}" for ln in mem_head] or [f"  {name}: no memory lines in header.txt (a job from before rule 16)"]
        if n is not None:
            lines.append(f"  {name}: {n} pipeline process(es) listed in strays.txt after the arms (a cell cut at the cap may leave "
                         f"its planner's children; they end with the job)")
    if sacct is not None:
        info = parse_sacct(sacct)
        limit_kb = mw.limit_kb(mw.PEAK_REPORT_GB)
        seen = set()
        for job in jobs:
            jid = header_job_id(job)
            j = info.get(jid) if jid else None
            name = os.path.basename(os.path.normpath(job))
            if j is None:
                lines.append(f"  sacct: no row for {name} (job {jid or '?'})")
                continue
            seen.add(jid)
            lines.append(_sacct_line(f"job {jid} ({name})", j, limit_kb))
        for jid, j in sorted(info.items()):
            if jid not in seen:
                lines.append(_sacct_line(f"job {jid} (not among the results folders)", j, limit_kb))


def _sacct_line(who, j, limit_kb):
    rss = j.get('max_rss_kb')
    over = rss is not None and rss > limit_kb
    return (f"  sacct {who}: MaxRSS {mw.fmt_gb(rss)}, requested {j.get('req_mem') or '?'}, {j.get('state') or '?'}, "
            f"{j.get('elapsed') or '?'}, {j.get('node') or '?'}" + ('  OVER 6 GB (report it)' if over else ''))


def targets_files(res, out_dir, lines):
    """targets_occK.json for phase 2: A's holding cells' Target: line, by seed (path 5's --targets)."""
    written = []
    for d in ps.DIFFICULTIES:
        targets, missing = {}, []
        for tag, rec in res['A'].items():
            c = rec['cell']
            if c['goal'] != 'holding' or c['n_occluders'] != d:
                continue
            text = rec['final']['_stdout'] if rec['final'] else None      # the attempt that counted
            m = TARGET_RE.search(text or '')
            if m:
                targets[str(c['seed'])] = m.group(1)
            else:
                missing.append(c['seed'])
        path = os.path.join(out_dir, f"targets_occ{d}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(targets, f, indent=1, sort_keys=True)
        written.append(path)
        lines.append(f"  targets_occ{d}.json: {len(targets)} seeds" + (f"; no Target line for seeds {missing} (timeout stubs keep no stdout.log)" if missing else ''))
    return written



def redo_list(res, path, lines):
    """The list file for p6_tabletop.sbatch redo: only cells that never started (no attempt, a void job, no
    summary file), one line per arm.  A crash, hang or mismatch is a first attempt and a failure: not listed."""
    out = []
    for arm in ps.ARMS:
        tags = [t for t, rec in res[arm].items()
                if rec['final'] is None or rec['final']['status'] in NEVER_STARTED]
        if tags:
            out.append(f"{arm} {','.join(sorted(tags))}")
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out) + ('\n' if out else ''))
    lines.append(f"final pass list {os.path.basename(path)}: " + (', '.join(f"{o.split()[0]} {len(o.split()[1].split(','))} cells" for o in out) or 'nothing to re-run'))


def write_merged_sweeps(res, out_dir, lines):
    """One merged sweep folder per arm (aggregated.jsonl and .csv, matrix.json) for eval_plotter.py."""
    for arm in ps.ARMS:
        d = os.path.join(out_dir, f"sweep_{arm}")
        os.makedirs(d, exist_ok=True)
        rows = []
        for tag, rec in sorted(res[arm].items()):
            f = rec['final']
            if f is None:
                continue
            row = dict(f['_ts'] or {})

            rc = row.get('run_config')
            if isinstance(rc, dict):
                for k, v in rc.items():
                    row.setdefault(k, v)
            row.update({'p6_tag': tag, 'p6_status': f['status'], 'p6_label': f.get('failure') or f['why'], 'p6_arm': arm})
            if not isinstance(rc, dict):
                for k, v in rec['cell'].items():
                    row.setdefault(k, v)
            rows.append(row)
        with open(os.path.join(d, 'aggregated.jsonl'), 'w', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r) + '\n')
        scalar = sorted({k for r in rows for k, v in r.items() if not isinstance(v, (list, dict))})
        with open(os.path.join(d, 'aggregated.csv'), 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=scalar, extrasaction='ignore')
            w.writeheader()
            for r in rows:
                w.writerow(r)
        with open(os.path.join(d, 'matrix.json'), 'w', encoding='utf-8') as fh:
            json.dump({'preset': 'p6', 'cells': [rec['cell'] for rec in res[arm].values()]}, fh, indent=1)
        lines.append(f"  {os.path.basename(d)}: {len(rows)} rows")



def load_rows_jsonl(path):
    rows = []
    text = read_text(path)
    for line in (text or '').splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def build_report(results, sweep=None, identical=None, cb113=None, cap=CAP_S, out_dir=None, sacct=None):
    jobs = find_jobs(results)
    attempts = load_attempts(jobs)
    res = final_cells(attempts, cap)

    stalled, n_windows = stalled_cells(attempts, jobs)
    lines = ['Path 6, phase 1a: the tabletop benchmark, arm A (our code now) against arm B (the thesis commit)', '']
    lines.append("On random-pairs the comparison of A and B measures our code and the benchmark together: the scene builder "
                 "changed after the thesis (occluder sizes, target sizes), so the two arms run each its own vetted seed list "
                 "and the spawned layouts differ; A against B there is unpaired. holding is scored by two different physical "
                 "tests (A: both finger pads squeeze at 0.5 N or more, B: a weld constraint).")
    lines.append('')
    lines.append("Counting (Hani, 14 and 15 Nov): one result per cell, its first attempt; a crash, a hang (no summary) and a summary of "
                 "another cell are failures, with the crashed count named beside every rate; no rerun and no re-rolled replacement "
                 f"counts; one rate, over the declared cells.  Pre-flight rejections and re-rolled cells: PREFLIGHT_POLICY = {PREFLIGHT_POLICY} "
                 + ("(left out of numerators and denominators, named beside each rate)" if PREFLIGHT_POLICY == 'out'
                    else "(counted as failures of that arm)") + ".")
    lines.append('')
    provenance(jobs, lines)
    bad = unknown_tags(attempts)
    if bad:
        lines.append(f"CELL FOLDERS NO SLOT NAMES ({len(bad)}): {bad[:6]}")
    dups = claims(attempts)
    if dups:
        lines.append(f"run directories named by more than one cell ({len(dups)}): {list(dups.items())[:3]}")
    lines.append('')
    for arm in ps.ARMS:
        status_accounting(res, arm, lines)
    first_attempt_trouble(res, lines)
    lines.append('')
    completeness_lines(res, lines)
    lines.append('')
    for arm in ps.ARMS:
        rates_table(res, arm, lines)
        lines.append('')
    for arm in ps.ARMS:
        failure_modes(res, arm, lines)
    lines.append('')
    rule18_lines(res, lines)
    lines.append('')
    a_vs_b(res, frozenset(), lines, 'TEST 1: A against B pooled over find-and-tray-stack and stack (holding excluded)')
    per_goal_ab(res, lines)
    stack_identical_pairs(res, identical, lines)
    lines.append('')
    b_against_sweep(res, sweep, lines)
    lines.append('')
    timing_lines(res, lines)
    lines.append('')
    lines.append(f"stall rule: {sum(n_windows.values())} stalls in {len(n_windows)} probes ({', '.join(f'{j} {n}' for j, n in sorted(n_windows.items()) if n) or 'none'}); "
                 f"{len(stalled)} cells overlap one" + (f": {sorted(stalled)[:8]}" if stalled else ''))
    if stalled:
        a_vs_b(res, stalled, lines, 'TEST 1 again without the cells that overlap a stall (no cell is re-run for a stall):')
    lines.append('')
    mem_lines(jobs, attempts, lines, sacct)
    if cb113:
        lines.append('')
        lines.append('A against CB#113 (the partial laptop run of 430a214, descriptive only):')
        descriptive_rows(res, cb113, lines)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        lines.append('')
        lines.append('files written:')
        redo_list(res, os.path.join(out_dir, 'redo_list.txt'), lines)
        targets_files(res, out_dir, lines)
        write_merged_sweeps(res, out_dir, lines)
    return '\n'.join(lines), res


def descriptive_rows(res, rows, lines):
    """A's cluster rates beside another run's aggregated rows (same goal and difficulty, semantic auto cell)."""
    other = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        rc = r.get('run_config') if isinstance(r.get('run_config'), dict) else r
        if rc.get('baseline') != 'semantic' or rc.get('min_boxel_size') not in (None, '') or rc.get('scene') != 'random-pairs':
            continue
        if r.get('exit_reason') == 'preflight_rejected':
            continue
        key = (rc.get('goal'), rc.get('n_occluders'))
        other[key][0] += bool(r.get('success'))
        other[key][1] += 1
    for goal in ('holding', 'find-and-tray-stack'):
        for d in ps.DIFFICULTIES:
            t = tally(group_cells(res, 'A', goal, d))
            k, n = other.get((goal, d), [0, 0])
            lines.append(f"  {goal:20} occ {d}  A on the cluster {t['k']}/{t['n']}   CB#113 {k}/{n}")


def main(argv=None):
    global PREFLIGHT_POLICY
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--results', nargs='+', required=True, help='job folders, or folders of job folders')
    ap.add_argument('--out', default=None, help='where redo_list.txt, targets_occK.json, sweep_A/ and sweep_B/ and report.txt go')
    ap.add_argument('--sweep', default=None, help="the thesis sweep's aggregated.jsonl (B's reproduction)")
    ap.add_argument('--stack-identical', default=None, help='JSON [[seed, height], ...] of the stack cells with an identical layout')
    ap.add_argument('--cb113', default=None, help="CB#113's aggregated.jsonl (descriptive)")
    ap.add_argument('--cap', type=float, default=CAP_S)
    ap.add_argument('--preflight', choices=('out', 'failure'), default='out',
                    help="pre-flight rejections and re-rolled cells: 'out' (left out, named; default, the coordinator's P-1 "
                         "reading) or 'failure' (counted as failures of that arm; run sheet section 10 item 14)")
    ap.add_argument('--sacct', default=None,
                    help="`sacct -P -j <ids> --format=JobID,JobName,State,Elapsed,MaxRSS,ReqMem,NodeList` output (rule 16)")
    a = ap.parse_args(argv)
    PREFLIGHT_POLICY = a.preflight
    sweep = load_rows_jsonl(a.sweep) if a.sweep else None
    identical = read_json(a.stack_identical) if a.stack_identical else None
    cb113 = load_rows_jsonl(a.cb113) if a.cb113 else None
    sacct = read_text(a.sacct) if a.sacct else None
    if a.sacct and sacct is None:
        raise SystemExit(f"cannot read --sacct {a.sacct}")
    text, _ = build_report([os.path.abspath(p) for p in a.results], sweep, identical, cb113, a.cap,
                           os.path.abspath(a.out) if a.out else None, sacct)
    print(text)
    if a.out:
        with open(os.path.join(a.out, 'report.txt'), 'w', encoding='utf-8') as f:
            f.write(text + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
