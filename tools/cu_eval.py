#!/usr/bin/env python3
"""class_uncertain, arm T (TAMPURA) on the cluster (Q42): the episodes of one job, one process each.

  cu_eval.py --snapshot SB --out OUT --seeds 0-4 --reps 3 --venv-t TW/.venv --tampura-work TW
             [--cap 3600] [--scratch /tmp] [--hashseed episode|N|unset] [--dry-run]
             [--min-avail-gb 4] [--peak-report-gb 6]
  cu_eval.py --report OUT [OUT ...]            the rows of these folders, counted

Each episode is their run_planner.py through tools/cluster/cu_t.py (their file run as it is, one
read of their world after their rollout), in THEIR venv, from a scratch directory of its own that
holds only two links into their tree (env_configs, class_uncertain's problems), as
`run cu -System tampura` builds it for Hani's look.  Their tree is never written.  The scratch
directory is removed by its exact path when the episode ends.  The episode's own files stay in
OUT/T/seed<N>_rep<R>/ (their save folder with the history, the console, the spans, the read).

The hash seed (worker S's sheet, tracks/modes/CLUSTER_SHEET_CU.md section 2): every repetition of a
seed runs with the same --global-seed, and under one PYTHONHASHSEED their run may repeat itself to
the action (arm T on find_dice scene 113 did, three runs out of three, 2026-11-12).  The default
`episode` gives every episode its own recorded value, 1000 * seed + repetition + 1, so that the
repetitions are draws and each can be run again; a number sets that value for all, `unset` leaves
the variable out as their own way to run does (draws, but no episode can be repeated).

Order: repetitions outside, seeds inside, so a job that is cut short has whole repetitions first.
A row that exists is not run again (a second call of the same job folder resumes).

Row (OUT/rows_T.jsonl), with path 7's names where the meaning is the same (cu_rand.py's rows):
task, seed, rep, arm, policy, max_steps, steps, actions, rewards, reward_t0, success_first_goal,
first_goal_step, return, reward_last, n_noop, first_noop_step, world_success_end, world_rows,
broken, broken_reports, crash, timed_out, rc, wall_s, get_action_s (the sum of their get_action
spans), get_action_spans, read_s, counts (False when the episode gave no world test for a cause
that is not the arm's: see `why`), rule 18's five fields, `mem` and `peak_over_6gb` (rule 16).

Not in a row of this arm: a world test per step (world_first_steps and world_return are None: no
step of their run is watched), a drop count and a collision count.  Rule 18's words for an arm on
their controllers, never a 0: drops "cannot happen (kinematic carry)", collisions "not detected
(their execution reports no collision)", clean_success None.  Their pick's `broken` reports are in
the row under their own name.

Memory (rule 16, tools/memwatch.py): MemAvailable under the limit stops the job after the
episode's row (nothing starts under it): STOPPED_LOW_MEMORY.txt in OUT, exit code 4.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import memwatch as mw  # noqa: E402

TASK = 'class_uncertain'
ARM = 'T'
ARM_NAME = 'tampura_run_planner_cu_read_v1'
GAMMA = 0.98
CONFIG = './env_configs/class_uncertain.yml'
ROWS = 'rows_T.jsonl'
ROWS_SMOKE = 'rows_T_smoke.jsonl'     # --smoke only; --report never reads it
# --smoke: their own arguments that cut an episode to two steps and a small sample count
SMOKE_ARGS = ('--max-steps', '2', '--num-samples', '30', '--batch-size', '10')
FINAL_NAME = 'cu_final_world.json'
SPANS_NAME = 'get_action_spans.jsonl'
DROPS_WORDS = 'cannot happen (kinematic carry)'
COLLISIONS_WORDS = 'not detected (their execution reports no collision)'
LINKS = (('env_configs', ('tampura_environments', 'env_configs')),
         (os.path.join('tampura_environments', 'class_uncertain', 'problems'),
          ('tampura_environments', 'tampura_environments', 'class_uncertain', 'problems')))


def parse_seeds(text):
    """'0-4,7' -> [0, 1, 2, 3, 4, 7]; no seed twice."""
    out = []
    for part in text.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            lo, hi = part.split('-', 1)
            lo, hi = int(lo), int(hi)
            if hi < lo:
                raise SystemExit(f"--seeds: {part} runs backwards")
            out.extend(range(lo, hi + 1))
        else:
            out.append(int(part))
    if not out or len(set(out)) != len(out):
        raise SystemExit(f"--seeds: {text!r} is empty or names a seed twice")
    return out


def ep_name(seed, rep):
    return f"seed{seed}_rep{rep}"


def hashseed_for(mode, seed, rep):
    """The PYTHONHASHSEED of one episode: None (left unset), the fixed number, or the episode's own."""
    if mode == 'unset':
        return None
    if mode == 'episode':
        return 1000 * seed + rep + 1
    return int(mode)


def child_env(base, tampura_work, hashseed, venv):
    """The environment of an episode: the caller's, with their two packages on PYTHONPATH and
    nothing of ours, the hash seed as declared, and their venv active (its bin first on PATH,
    VIRTUAL_ENV set, as find_dice's arm T has it in tools/_bridge_campaign.py).  The venv on PATH
    is needed: their solver starts the translator and the search as a bare `python`
    (tampura/solvers/symk.py), and without it the first get_action dies with FileNotFoundError
    (seen in the two-step smoke of 2026-11-13)."""
    env = dict(base)
    env['PATH'] = os.path.join(venv, 'bin') + os.pathsep + env.get('PATH', '')
    env['VIRTUAL_ENV'] = venv
    env['PYTHONPATH'] = os.pathsep.join([os.path.join(tampura_work, 'tampura'),
                                         os.path.join(tampura_work, 'tampura_environments')])
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['MPLBACKEND'] = 'Agg'
    env.pop('PYTHONHOME', None)
    if hashseed is None:
        env.pop('PYTHONHASHSEED', None)
    else:
        env['PYTHONHASHSEED'] = str(int(hashseed))
    return env


def command(a, seed, save_dir):
    """Their driver through cu_t.py with their config.  --smoke adds their own arguments that cut
    the episode short (a check of the mechanics, never a result)."""
    return [os.path.join(a.venv_t, 'bin', 'python'), '-u',
            os.path.join(a.snapshot, 'tools', 'cluster', 'cu_t.py'),
            '--run-planner', os.path.join(a.tampura_work, 'tampura_environments', 'run_planner.py'),
            '--world-test-dir', os.path.join(a.snapshot, 'tasks_probe'),
            '--config', CONFIG, '--global-seed', str(seed), '--save-dir', save_dir] \
        + (list(SMOKE_ARGS) if getattr(a, 'smoke', False) else [])


def make_scratch(path, tampura_work):
    """A new directory with the two links their config and env read through; refuses one that exists."""
    if os.path.lexists(path):
        raise SystemExit(f"scratch {path} exists already: nothing run (remove it by its path first)")
    for rel, target in LINKS:
        link = os.path.join(path, rel)
        os.makedirs(os.path.dirname(link), exist_ok=True)
        os.symlink(os.path.join(tampura_work, *target), link)
    return path


def read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_spans(path):
    out = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except (OSError, ValueError):
        pass
    return out


def build_row(seed, rep, order, rc, timed_out, wall_s, final, spans, hashseed):
    """One row from what the episode left.  `counts` is False when there is no world test and the
    cause is not the arm's own crash or its timeout: such an episode is neither a success nor a failure."""
    final = final or {}
    row = {'task': TASK, 'seed': seed, 'rep': rep, 'arm': ARM, 'arm_name': ARM_NAME, 'policy': 'tampura_policy',
           'order': order, 'rc': rc, 'timed_out': bool(timed_out), 'wall_s': round(wall_s, 2),
           'pythonhashseed': hashseed,
           'get_action_s': round(sum(s.get('get_action_s', 0.0) for s in spans), 3),
           'get_action_spans': [round(s.get('get_action_s', 0.0), 3) for s in spans]}
    for k in ('max_steps', 'steps', 'actions', 'rewards', 'reward_t0', 'success_first_goal', 'first_goal_step',
              'reward_last', 'n_noop', 'first_noop_step', 'broken', 'broken_reports', 'world_rows', 'read_s'):
        row[k] = final.get(k)
    first = row['first_goal_step']
    row['return'] = (GAMMA ** first if first else 0.0) if final.get('ok') else None
    row['world_success_end'] = final.get('world_success_end') if final.get('ok') else None
    row['world_first_steps'] = None       # no step of their run is watched
    row['world_return'] = None
    row['crash'] = final.get('crash')
    why = None
    if timed_out:
        why = 'timeout: the episode passed the cap and was ended (a failure of the arm)'
    elif final.get('crash'):
        why = 'crash inside their rollout (a failure of the arm, CU-14)'
    elif not final.get('ok'):
        why = ('the read after their rollout failed: ' + str(final.get('read_error'))) if final.get('read_error') \
            else f"no {FINAL_NAME} and no crash record (rc {rc}): the episode did not reach their rollout's end"
    row['why'] = why
    # a timeout and a crash are the arm's failures and count; a missing or failed read is ours and does not
    row['counts'] = bool(final.get('ok')) or bool(timed_out) or bool(final.get('crash'))
    row['success'] = bool(row['world_success_end']) if row['counts'] else None
    row.update({'drops': None, 'drop_detector': DROPS_WORDS, 'collisions': None,
                'collision_detector': COLLISIONS_WORDS, 'clean_success': None})
    return row


def end_group(proc):
    """End the episode's own process group (the python we started and what it started)."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, AttributeError):
        try:
            proc.kill()
        except OSError:
            pass


def run_one(a, seed, rep, order, base_env=None, popen=subprocess.Popen):
    name = ep_name(seed, rep)
    ep_dir = os.path.join(a.out, ARM, name)
    save_dir = os.path.join(ep_dir, 'save')
    os.makedirs(save_dir, exist_ok=True)
    scratch = os.path.join(a.scratch, f"cu_{ARM}_{os.path.basename(os.path.normpath(a.out))}_{name}")
    make_scratch(scratch, a.tampura_work)
    hashseed = hashseed_for(a.hashseed, seed, rep)
    env = child_env(os.environ if base_env is None else base_env, a.tampura_work, hashseed, a.venv_t)
    cmd = command(a, seed, save_dir)
    t0 = time.time()
    timed_out = False
    try:
        with open(os.path.join(ep_dir, 'console.txt'), 'w', encoding='utf-8', errors='replace') as con:
            con.write('cwd ' + scratch + '\n' + ' '.join(cmd) + '\n')
            con.flush()
            proc = popen(cmd, cwd=scratch, env=env, stdout=con, stderr=subprocess.STDOUT,
                         start_new_session=True)
            try:
                rc = proc.wait(timeout=a.cap)
            except subprocess.TimeoutExpired:
                timed_out = True
                end_group(proc)
                rc = proc.wait()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)        # the directory this episode made, by its exact path
    wall = time.time() - t0
    return build_row(seed, rep, order, rc, timed_out, wall, read_json(os.path.join(save_dir, FINAL_NAME)),
                     read_spans(os.path.join(save_dir, SPANS_NAME)), hashseed)


def load_rows(path):
    rows = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except OSError:
        pass
    return rows


def append_row(path, row):
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(row, default=str) + '\n')
        f.flush()
        os.fsync(f.fileno())


def count_lines(rows):
    """The counts of a set of rows, as lines (no interval: path 7's analysis makes the table)."""
    n = len(rows)
    counted = [r for r in rows if r.get('counts')]
    wok = sum(1 for r in counted if r.get('world_success_end'))
    rew = sum(1 for r in counted if r.get('success_first_goal'))
    lines = [f"arm T on {TASK}: {n} episode(s), {len(counted)} counted",
             f"  world-state test at the end (primary): {wok} of {len(counted)}",
             f"  their reward reached: {rew} of {len(counted)}",
             f"  timeouts {sum(1 for r in rows if r.get('timed_out'))}, crashes inside their rollout "
             f"{sum(1 for r in rows if r.get('crash'))}, episodes with a `broken` report "
             f"{sum(1 for r in rows if r.get('broken'))}, not counted {n - len(counted)}",
             f"  drops: {DROPS_WORDS}; collisions: {COLLISIONS_WORDS}; clean success: not measured"]
    walls = [r['wall_s'] for r in rows if r.get('wall_s') is not None]
    if walls:
        lines.append(f"  wall per episode: mean {sum(walls) / len(walls):.0f} s, longest {max(walls):.0f} s, "
                     f"all together {sum(walls) / 3600:.2f} h")
    for r in rows:
        if not r.get('counts'):
            lines.append(f"  NOT COUNTED seed {r.get('seed')} rep {r.get('rep')}: {r.get('why')}")
    return lines


def report(dirs):
    rows = []
    for d in dirs:
        rows.extend(load_rows(os.path.join(d, ROWS)))
    seen = {}
    for r in rows:
        seen.setdefault((r.get('seed'), r.get('rep')), []).append(r)
    dup = sorted(k for k, v in seen.items() if len(v) > 1)
    lines = count_lines(rows)
    if dup:
        lines.append(f"  WARNING: {len(dup)} (seed, repetition) pair(s) appear more than once: {dup[:10]}")
    return '\n'.join(lines)


def run(a):
    for need in (os.path.join(a.snapshot, 'tools', 'cluster', 'cu_t.py'),
                 os.path.join(a.snapshot, 'tasks_probe', 'cu_rand.py'),
                 os.path.join(a.tampura_work, 'tampura_environments', 'run_planner.py'),
                 os.path.join(a.tampura_work, 'tampura_environments', 'env_configs', 'class_uncertain.yml'),
                 os.path.join(a.venv_t, 'bin', 'python')):
        if not os.path.exists(need):
            print(f"[cu] {need} is missing: nothing run")
            return 2
    os.makedirs(a.out, exist_ok=True)
    # a smoke's rows go to their own file: --report reads ROWS alone, so a cut episode is never counted
    path = os.path.join(a.out, ROWS_SMOKE if a.smoke else ROWS)
    rows = load_rows(path)
    done = {(r['seed'], r['rep']) for r in rows}
    min_kb = mw.limit_kb(mw.MIN_AVAIL_GB if a.min_avail_gb is None else a.min_avail_gb)
    peak_kb = mw.limit_kb(mw.PEAK_REPORT_GB if a.peak_report_gb is None else a.peak_report_gb)
    with open(os.path.join(a.out, 'cu_eval.json'), 'w', encoding='utf-8') as f:
        json.dump({'task': TASK, 'arm': ARM, 'arm_name': ARM_NAME, 'seeds': a.seed_list, 'reps': a.reps,
                   'cap_s': a.cap, 'hashseed': a.hashseed, 'snapshot': a.snapshot, 'venv_t': a.venv_t,
                   'smoke': bool(a.smoke), 'smoke_args': list(SMOKE_ARGS) if a.smoke else None,
                   'tampura_work': a.tampura_work, 'scratch': a.scratch, 'host': os.uname().nodename
                   if hasattr(os, 'uname') else None, 'job': os.environ.get('SLURM_JOB_ID'),
                   'min_avail_limit_kb': min_kb, 'peak_limit_kb': peak_kb,
                   'started': time.strftime('%Y-%m-%d %H:%M:%S')}, f, indent=1)
    order = len(rows)
    try:
        for rep in range(a.reps):
            for seed in a.seed_list:
                if (seed, rep) in done:
                    continue
                label = f"T seed {seed} rep {rep}"
                avail = mw.mem_available_kb()
                if mw.low_memory(avail, min_kb):
                    raise mw.LowMemory('start', avail, min_kb, label)
                print(f"[cu] rep {rep} seed {seed} (MemAvailable {mw.fmt_gb(avail)}) ...", end=' ', flush=True)
                with mw.EpisodeWatch(min_kb, peak_kb) as w:
                    row = run_one(a, seed, rep, order)
                row.update(mw.row_fields(w.as_row()))
                if a.smoke:
                    row['smoke'] = True
                order += 1
                append_row(path, row)
                rows.append(row)
                print(f"world test {row['world_success_end']}, their reward {row['success_first_goal']}, "
                      f"wall {row['wall_s']} s{' (timeout)' if row['timed_out'] else ''}"
                      f"{'' if row['counts'] else ', DOES NOT COUNT: ' + str(row['why'])}", flush=True)
                for line in w.end_lines(label):
                    print('[cu] ' + line, flush=True)
                if w.low():
                    raise mw.LowMemory('end', w.avail_min_kb, min_kb, label)
    except mw.LowMemory as e:
        mw.write_stop(a.out, e)
        print('\n'.join(count_lines(rows)))
        return mw.EXIT_LOW_MEMORY
    print('\n'.join(count_lines(rows)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--report', nargs='+', help='count the rows of these job folders')
    ap.add_argument('--snapshot')
    ap.add_argument('--out')
    ap.add_argument('--seeds')
    ap.add_argument('--reps', type=int, default=1)
    ap.add_argument('--cap', type=float, default=3600.0, help='wall cap per episode, s')
    ap.add_argument('--venv-t', help="arm T's venv (theirs)")
    ap.add_argument('--tampura-work', help='their tree: tampura, tampura_environments')
    ap.add_argument('--scratch', default='/tmp', help='where the episodes get their working directories')
    ap.add_argument('--hashseed', default='episode',
                    help="PYTHONHASHSEED: 'episode' (1000 * seed + repetition + 1, the default), a number for all, or 'unset'")
    ap.add_argument('--dry-run', action='store_true', help='print the episodes and their commands, run nothing')
    ap.add_argument('--smoke', action='store_true',
                    help='a check of the mechanics, never a result: their run cut to ' + ' '.join(SMOKE_ARGS)
                         + '; the rows go to ' + ROWS_SMOKE + ' and are never counted')
    ap.add_argument('--min-avail-gb', type=float, default=None)
    ap.add_argument('--peak-report-gb', type=float, default=None)
    a = ap.parse_args(argv)
    if a.report:
        print(report(a.report))
        return 0
    for name in ('snapshot', 'out', 'seeds', 'venv_t', 'tampura_work'):
        if not getattr(a, name):
            ap.error('--' + name.replace('_', '-') + ' is needed')
    if a.hashseed not in ('unset', 'episode') and not 0 <= int(a.hashseed) <= 4294967295:
        ap.error('--hashseed must be episode, unset or a number from 0 to 4294967295')
    if a.reps < 1:
        ap.error('--reps must be at least 1')
    a.seed_list = parse_seeds(a.seeds)
    if a.dry_run:
        env = child_env({'PATH': '$PATH'}, a.tampura_work, None, a.venv_t)
        print(f"{len(a.seed_list) * a.reps} episode(s), cap {a.cap:.0f} s each, hash seed {a.hashseed}, environment " +
              ' '.join(f"{k}={v}" for k, v in sorted(env.items())))
        for rep in range(a.reps):
            for seed in a.seed_list:
                save = os.path.join(a.out, ARM, ep_name(seed, rep), 'save')
                hs = hashseed_for(a.hashseed, seed, rep)
                print(f"rep {rep} seed {seed}: " + ('' if hs is None else f"PYTHONHASHSEED={hs} ")
                      + ' '.join(command(a, seed, save)))
        return 0
    return run(a)


if __name__ == '__main__':
    sys.exit(main())
