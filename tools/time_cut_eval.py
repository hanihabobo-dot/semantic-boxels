#!/usr/bin/env python3
"""BF#53: the per-fix eval of the time cuts on TAMPURA's find_dice, our arm
(the bridge driver) alone, headless, serial, from a code snapshot.

Every seed runs under every arm; an arm is a set of the fixes switched on,
the others off ('base': none; '12': fixes 1 and 2), so "fix 2 alone",
"fixes 1 + 2" and "fix 1" are three arms of the same seeds.  Seeds are the
outer loop, so one seed's arms run close together in time.  Each episode
is a bridge run with --allow-g19-mismatch 1 (the laptop's scene map
differs from the campaign's, BF#39; the scene a seed loads is the same
under every arm).  results.jsonl holds one row per episode (rc, wall,
the bridge's outcome, tools/episode_metrics.py's metrics); summary.txt the
tables: per arm the success count and the means over the WORKING seeds
(the seeds every arm finished with the ledger's success), and per fix its
effect alone against base and added to the fixes before it.  A rerun
skips the episodes results.jsonl already holds (extend --seeds to add).

  PYTHONPATH=<snapshot>:<pddlstream_lib>:<their tampura>:<their envs> \\
    <arm O python> <snapshot>/tools/time_cut_eval.py --snapshot <snapshot> \\
    --out OUT [--seeds 0-19] [--arms base,1,2,12,3,123,4,1234] [--cap 600]
  python tools/time_cut_eval.py --out OUT --summary        the tables again
"""
import argparse
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import episode_metrics  # noqa: E402

# The fixes, in the order the cumulative arms add them, as the bridge
# driver's switches (run_logger's flags of the same names).
FIXES = OrderedDict([
    ('1', ("the fold: sense from the target's pick configuration over the "
           "region, pick from there (BF#52)", {'sense_over_region': 'on'})),
    ('2', ("M8's init cache: look and fixed sense renders reused while no "
           "twin body moved", {'m8_init_cache': 'on'})),
    ('3', ("the observe continuation: an observe that confirmed the pose "
           "does not force a replan", {'continue_after_observe': 'on'})),
    ('4', ("the search's effort weighting and starting complexity "
           "(pddlstream effort_weight 1, initial_complexity 3)",
           {'search_effort_weight': '1', 'search_initial_complexity': '3'})),
])
BASE = {'sense_over_region': 'off', 'm8_init_cache': 'off',
        'continue_after_observe': 'off', 'search_effort_weight': 'off',
        'search_initial_complexity': '0'}
DEFAULT_ARMS = 'base,1,2,12,3,123,4,1234'
# The metrics summarised per arm (tools/episode_metrics.py's names).
MEANS = ('wall_s', 'planning_s', 'planning_first_s', 'm8_build_s', 'exec_s',
         'plan_calls', 'steps', 'moves', 'senses', 'observes',
         'home_for_sense', 'move_s')


def arm_switches(arm):
    sw = dict(BASE)
    if arm != 'base':
        for ch in arm:
            if ch not in FIXES:
                raise SystemExit(f"unknown fix {ch!r} in arm {arm!r}")
            sw.update(FIXES[ch][1])
    return sw


def parse_seeds(s):
    out = []
    for part in s.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-')
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def load_results(path):
    done = OrderedDict()
    if os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    done[(r['arm'], r['seed'])] = r
    return done


def pipeline_alive(my_pid):
    """Another bridge or pipeline process on this machine (a 'python -c'
    dummy whose command line names the driver is not one)."""
    alive = []
    for pid in os.listdir('/proc'):
        if not pid.isdigit() or int(pid) == my_pid:
            continue
        try:
            with open(f'/proc/{pid}/cmdline', 'rb') as f:
                cmd = f.read().replace(b'\0', b' ').decode(errors='replace')
        except OSError:
            continue
        if (('run_bridge_on_finddice' in cmd or 'test_full_pipeline' in cmd)
                and ' -c ' not in cmd and 'time_cut_eval' not in cmd):
            alive.append(f"{pid}: {cmd[:100]}")
    return alive


def run_episode(a, arm, seed):
    save_dir = os.path.join(a.out, arm, f'seed{seed:02d}')
    os.makedirs(save_dir, exist_ok=True)
    cmd = [a.python,
           os.path.join(a.snapshot, 'tampura_bridge', 'run_bridge_on_finddice.py'),
           '--global-seed', str(seed), '--vis', '0', '--save-dir', save_dir,
           '--allow-g19-mismatch', '1']
    switches = arm_switches(arm)
    for k, v in sorted(switches.items()):
        cmd += ['--' + k.replace('_', '-'), v]
    env = dict(os.environ, PYTHONHASHSEED='0', PYTHONDONTWRITEBYTECODE='1')
    t0 = time.time()
    timed_out = False
    with open(os.path.join(save_dir, 'stdout.txt'), 'w', encoding='utf-8') as log:
        proc = subprocess.Popen(cmd, cwd=a.cwd, env=env, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = proc.wait(timeout=a.cap)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            rc, timed_out = None, True
    rec = OrderedDict(arm=arm, seed=seed, rc=rc, timed_out=timed_out,
                      process_wall_s=round(time.time() - t0, 1),
                      started=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t0)),
                      switches=switches, save_dir=save_dir)
    try:
        with open(os.path.join(save_dir, 'bridge_episode.json'), 'r', encoding='utf-8') as f:
            bj = json.load(f)
        rec['bridge_status'] = (bj.get('outcome') or {}).get('status')
        rec['reward'] = (bj.get('rewards') or [None])[-1]
        rec['scene_file'] = os.path.basename(str(bj.get('scene_file')))
    except Exception as e:                       # no episode file: a crash or a kill
        rec['bridge_status'] = None
        rec['bridge_error'] = f"{type(e).__name__}: {e}"
    try:
        rec['metrics'] = episode_metrics.metrics(episode_metrics._find_run_dir(save_dir))
    except (Exception, SystemExit) as e:
        rec['metrics'] = None
        rec['metrics_error'] = str(e)
    return rec


def _ok(rec):
    return bool(rec and rec.get('metrics') and rec['metrics'].get('outcome') == 'success')


def _finished(rec):
    """The episode ran to the ledger's close (any outcome): its times are
    the pipeline's work, unlike a timeout's or a crash's."""
    return bool(rec and not rec.get('timed_out') and rec.get('metrics')
                and rec['metrics'].get('outcome') and rec['metrics'].get('wall_s') is not None)


def _mean(values):
    vals = [float(v) for v in values if v is not None]
    return statistics.fmean(vals) if vals else None


def _fmt(v, digits=1):
    if v is None:
        return '-'
    return f"{v:.{digits}f}" if isinstance(v, float) else str(v)


def _pct(a, b):
    if a in (None, 0) or b is None:
        return ''
    return f"{(b - a) / a * 100:+.0f}%"


def summary(done, arms, seeds):
    by = {(r['arm'], r['seed']): r for r in done.values()}
    arms = [x for x in arms if any((x, s) in by for s in seeds)]
    working = [s for s in seeds if all(_ok(by.get((x, s))) for x in arms)]
    lines = [f"arms {', '.join(arms)}; seeds {len(seeds)}: {seeds[0]}-{seeds[-1]}" if seeds else 'no seeds',
             f"working seeds (the ledger's success under every arm): {len(working)}: "
             f"{', '.join(map(str, working))}", '']
    lines.append(f"{'arm':8} {'episodes':>8} {'success':>8} {'timeouts':>8} {'bridge success':>14}")
    for x in arms:
        recs = [by[(x, s)] for s in seeds if (x, s) in by]
        lines.append(f"{x:8} {len(recs):8} {sum(_ok(r) for r in recs):8} "
                     f"{sum(bool(r.get('timed_out')) for r in recs):8} "
                     f"{sum(r.get('bridge_status') == 'success' for r in recs):14}")
    finished = [s for s in seeds if all(_finished(by.get((x, s))) for x in arms)]
    for title, sel in ((f"means over the {len(working)} working seeds", working),
                       (f"means over the {len(finished)} seeds every arm ran to the ledger's close "
                        f"(any outcome)", finished)):
        lines.append('')
        lines.append(f"{title} (last column: the last arm against base)")
        lines.append(f"{'metric':18}" + ''.join(f"{x:>10}" for x in arms) + f"{'last vs base':>14}")
        for m in MEANS:
            row = {x: _mean(by[(x, s)]['metrics'].get(m) for s in sel) for x in arms}
            cells = ''.join(f"{_fmt(row[x]):>10}" for x in arms)
            lines.append(f"{m:18}{cells}{_pct(row.get('base'), row.get(arms[-1])):>14}")
    lines.append('')
    lines.append('per fix: alone against base, and added to the fixes before it '
                 '(over the seeds both arms ran to the close; success counts in brackets)')
    cum = ''
    for ch, (what, _) in FIXES.items():
        prev = cum or 'base'
        cum += ch
        lines.append(f"fix {ch}: {what}")
        for label, left, right in ((f"  alone     base -> {ch}", 'base', ch),
                                   (f"  added     {prev} -> {cum}", prev, cum)):
            if left not in arms or right not in arms:
                lines.append(f"{label}: (arm missing)")
                continue
            ws = [s for s in seeds if _finished(by.get((left, s))) and _finished(by.get((right, s)))]
            parts = []
            for m in ('wall_s', 'planning_s', 'exec_s', 'plan_calls', 'moves'):
                l_ = _mean(by[(left, s)]['metrics'].get(m) for s in ws)
                r_ = _mean(by[(right, s)]['metrics'].get(m) for s in ws)
                parts.append(f"{m} {_fmt(l_)} -> {_fmt(r_)} {_pct(l_, r_)}".rstrip())
            succ = (sum(_ok(by.get((left, s))) for s in ws), sum(_ok(by.get((right, s))) for s in ws))
            lines.append(f"{label} ({len(ws)} seeds, success {succ[0]} -> {succ[1]}): "
                         + '; '.join(parts))
    lines.append('')
    lines.append('wall_s per seed (x: not run, F: no success)')
    lines.append(f"{'seed':6}" + ''.join(f"{x:>9}" for x in arms))
    for s in seeds:
        cells = []
        for x in arms:
            r = by.get((x, s))
            if r is None:
                cells.append(f"{'x':>9}")
            elif not _ok(r):
                cells.append(f"{'F':>9}")
            else:
                cells.append(f"{_fmt(r['metrics'].get('wall_s')):>9}")
        lines.append(f"{s:<6}" + ''.join(cells))
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--snapshot', help='the code snapshot the episodes run from')
    ap.add_argument('--out', required=True)
    ap.add_argument('--seeds', default='0-19')
    ap.add_argument('--arms', default=DEFAULT_ARMS)
    ap.add_argument('--cap', type=float, default=600.0, help='wall cap per episode, s')
    ap.add_argument('--python', default=sys.executable)
    ap.add_argument('--cwd', default=os.path.join(
        os.environ.get('TAMPURA_WORK', '/root/tampura-work'), 'tampura_environments'),
        help="their tampura_environments directory (the driver runs from it)")
    ap.add_argument('--summary', action='store_true', help='print the tables of --out and exit')
    a = ap.parse_args(argv)
    seeds = parse_seeds(a.seeds)
    arms = [x.strip() for x in a.arms.split(',') if x.strip()]
    for x in arms:
        arm_switches(x)                          # a bad arm fails before any run
    results = os.path.join(a.out, 'results.jsonl')
    done = load_results(results)
    if a.summary:
        print(summary(done, arms, seeds))
        return 0
    if not a.snapshot or not os.path.isdir(a.snapshot):
        raise SystemExit(f"--snapshot must be a code snapshot directory: {a.snapshot}")
    alive = pipeline_alive(os.getpid())
    if alive:
        raise SystemExit("a pipeline process is alive: " + '; '.join(alive))
    os.makedirs(a.out, exist_ok=True)
    md_path = os.path.join(a.out, 'metadata.json')
    if not os.path.isfile(md_path):
        # A laptop snapshot (scratch snapshot.ps1) carries SNAPSHOT_HEAD.txt;
        # the cluster's immutable sb_<sha> is a git archive named by its sha.
        head_file = os.path.join(a.snapshot, 'SNAPSHOT_HEAD.txt')
        if os.path.isfile(head_file):
            with open(head_file, 'r', encoding='utf-8') as f:
                snap = f.read()
        else:
            snap = f"{os.path.basename(os.path.normpath(a.snapshot))} (git archive)"
        with open(md_path, 'w', encoding='utf-8') as f:
            json.dump({'snapshot': a.snapshot, 'snapshot_state': snap, 'arms': arms,
                       'seeds': seeds, 'cap_s': a.cap, 'base': BASE,
                       'fixes': {k: {'what': v[0], 'switches': v[1]} for k, v in FIXES.items()},
                       'started': time.strftime('%Y-%m-%d %H:%M:%S')}, f, indent=1)
    todo = [(s, x) for s in seeds for x in arms if (x, s) not in done]
    print(f"[eval] {len(todo)} episodes to run ({len(done)} done), arms {arms}, "
          f"seeds {seeds[0]}-{seeds[-1]}, cap {a.cap:.0f} s", flush=True)
    t_start = time.time()
    for i, (s, x) in enumerate(todo, 1):
        rec = run_episode(a, x, s)
        done[(x, s)] = rec
        with open(results, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec) + '\n')
        m = rec.get('metrics') or {}
        print(f"[eval] {i}/{len(todo)} seed {s} arm {x:5} rc {rec['rc']} "
              f"{'TIMEOUT ' if rec['timed_out'] else ''}"
              f"{m.get('outcome')} wall {_fmt(m.get('wall_s'))} planning {_fmt(m.get('planning_s'))} "
              f"exec {_fmt(m.get('exec_s'))} plans {m.get('plan_calls')} moves {m.get('moves')} "
              f"(process {rec['process_wall_s']} s; {(time.time() - t_start) / 60:.0f} min so far)",
              flush=True)
    text = summary(done, arms, seeds)
    with open(os.path.join(a.out, 'summary.txt'), 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
