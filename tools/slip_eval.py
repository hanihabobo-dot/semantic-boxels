#!/usr/bin/env python3
"""BF#59: the eval of the die-slip campaign's fixes on TAMPURA's find_dice,
our arm (the bridge driver) alone, headless, serial, from a code snapshot.

An arm is a set of the campaign's fixes switched on ('base': none; 'a+b':
the fixes a and b together; the names are the ones slip_fixes.py
registers).  Every seed runs under every arm; within a repetition the seeds
are the outer loop, so one seed's arms run back to back under the same
machine conditions.  The replicated seeds (--rep-seeds, chosen by the
orchestrator's entropy rule plus two drawn at random, BRIEF.md section 6)
run --reps times, every other seed once: repetition 0 covers every seed,
the later repetitions the replicated ones, so a cut job still holds a
complete first pass.  Each episode is the bridge driver with
--allow-g19-mismatch 1 (the laptop's scene map differs from the campaign's,
BF#39; on the cluster the pinned map matches and every arm loads the same
scene for a seed).

results.jsonl holds one row per episode: arm, seed, rep, rc, wall, the
bridge's outcome, tools/episode_metrics.py's metrics, and the die's carries
and losses counted from the run's logs (a carry is a verified die pick, a
loss is a die lost after its lift or at the goal check).  summary.txt holds
the tables: per arm the counts and the loss rate per carry, the medians
over the seeds every arm ran to the ledger's close, each arm against base
on the seeds both closed, and the replication's disagreement (the variance
of the same scene under the same settings).  A rerun skips the episodes
results.jsonl already holds.

Path 14's check of the candidate defaults on find_dice (2026-11-13,
tracks/meeting_2026-11-13/cluster_requests/B_find_dice_defaults_DRAFT.md)
adds three things, all off unless asked for:
  an arm 'a+b@corridor_object' runs the fixes a and b with the driver flag
  ARM_FLAGS names for 'corridor_object' (--corridor-test object, TB-25);
  --scenes FOLDER runs every episode in a fresh folder that holds only its
  seed's scene of FOLDER/manifest.json (BF#63's generated scenes, as
  tools/gen_scene_eval.py does it for its two arms), and the row says which
  scene the episode loaded;
  --rotate starts each seed's arms one arm further (by seed and repetition),
  so no arm is always the first of a seed.

  PYTHONPATH=<snapshot>:<pddlstream_lib>:<their tampura>:<their envs> \\
    <arm O python> <snapshot>/tools/slip_eval.py --snapshot <snapshot> --out OUT \\
    [--arms base,a,b,a+b] [--seeds 0-19] [--reps 3 --rep-seeds 1,2,5] [--cap 600]
    [--scenes FOLDER] [--rotate]
  python tools/slip_eval.py --out OUT --summary        the tables again
"""
import argparse
import glob
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import episode_metrics  # noqa: E402
sys.path.append(os.path.dirname(HERE))   # the snapshot's root, last on the path
import world_counts  # noqa: E402  (TB-22: drops, collisions, clean success)

# The metrics summarised per arm (tools/episode_metrics.py's names).
MEDIANS = ('wall_s', 'planning_s', 'planning_first_s', 'exec_s', 'plan_calls',
           'steps', 'picks', 'moves', 'senses', 'observes')
# The console's verified pick of the die (one per carry), the executor's
# loss after the lift, carry_hold_check's loss after a move made while
# holding (BF#59, slip_fixes 'carry_hold_check'; without the switch that
# loss surfaces at the goal check), and the goal check's loss
# (test_full_pipeline).
CARRY_RE = re.compile(r"firm grip on dice")
LIFT_LOSS_RE = re.compile(r"grip lost after post-pick lift for dice")
CARRY_LOSS_RE = re.compile(r"grip lost in the carry for dice")
# The goal check's loss is the die believed held and physically not (the
# two reasons _verify_holding gives for that); its other reasons ("no held
# object (gripper is empty)" after an acknowledged loss or no pick, a wrong
# body, an unknown target) are not a lost carry.
GOAL_LOSS_RE = re.compile(r"PHYSICAL_FAILURE \(goal\): \(holding dice\).{0,4}"
                          r"(finger-pad contact incomplete|pads touch but squeeze force)")
PICK_TRY_RE = re.compile(r"Picking dice")
# A driver flag an arm carries besides its slip fixes, named after an '@'
# ('a+b@corridor_object').  A fixed table: an arm stays a name in the
# record and never becomes a command line.
ARM_FLAGS = {'corridor_object': ('--corridor-test', 'object')}
# --scenes: where their loader looks under the working directory, and its
# line on the console (tools/gen_scene_eval.py's, BF#63).
PROBLEMS_REL = os.path.join('tampura_environments', 'find_dice', 'problems')
SCENE_RE = re.compile(r'Loading scene from (\S+)')


def split_arm(arm):
    """(the fixes part, the flag names) of an arm 'a+b@flag'."""
    head, *flags = [p.strip() for p in arm.split('@')]
    for name in flags:
        if name not in ARM_FLAGS:
            raise SystemExit(f"unknown arm flag {name!r} in {arm!r} "
                             f"(known: {', '.join(sorted(ARM_FLAGS))})")
    if len(set(flags)) != len(flags):
        raise SystemExit(f"arm {arm!r} names a flag twice")
    return head, flags


def arm_fixes(arm):
    """The fix names of an arm as the driver's flag value; 'base' is 'none',
    every switch off (BF#62 made the chosen four the default, so an empty
    value would run them).  An arm's '@flag' part is not a fix."""
    head, _ = split_arm(arm)
    if head == 'base':
        return 'none'
    names = [n.strip() for n in head.split('+') if n.strip()]
    if not names:
        raise SystemExit(f"empty arm {arm!r}")
    return ','.join(names)


def arm_args(arm):
    """The driver arguments of an arm's flags, in the arm's order."""
    return [x for name in split_arm(arm)[1] for x in ARM_FLAGS[name]]


def arm_order(arms, seed_index, rep, rotate):
    """One seed's arms in running order: as given, or with --rotate starting
    one arm further for every seed and repetition."""
    arms = list(arms)
    if not rotate or not arms:
        return arms
    k = (seed_index + rep) % len(arms)
    return arms[k:] + arms[:k]


def parse_seeds(s):
    out = []
    for part in str(s).split(','):
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
                    done[(r['arm'], r['seed'], r.get('rep', 0))] = r
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
                and ' -c ' not in cmd and 'slip_eval' not in cmd):
            alive.append(f"{pid}: {cmd[:100]}")
    return alive


def check_arms(a, arms):
    """Every arm's names must be registered in the snapshot: one import of
    the pipeline per arm, before any episode, so a typo fails here."""
    for arm in arms:
        code = ("import test_full_pipeline, slip_fixes; "
                f"slip_fixes.configure({arm_fixes(arm)!r}); "
                "print(sorted(slip_fixes.ENABLED))")
        r = subprocess.run([a.python, '-c', code], cwd=a.snapshot,
                           capture_output=True, text=True, timeout=600,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        if r.returncode != 0:
            raise SystemExit(f"arm {arm!r} is not runnable from {a.snapshot}:\n"
                             f"{r.stderr.strip()[-2000:]}")
        print(f"arm {arm}: fixes {r.stdout.strip().splitlines()[-1]}", flush=True)


def check_arm_flags(snapshot, arms):
    """An arm's driver flag must be an argument of the snapshot's driver
    (its source names it), so an arm the driver would refuse fails here,
    before any episode, and not once per episode with a usage error."""
    src = _read_text(os.path.join(snapshot, 'tampura_bridge', 'run_bridge_on_finddice.py'))
    for arm in arms:
        for flag in arm_args(arm)[::2]:
            if f"'{flag}'" not in src and f'"{flag}"' not in src:
                raise SystemExit(f"arm {arm!r}: the driver of {snapshot} has no {flag}")


def load_scenes(folder, seeds):
    """{seed: scene file} of a scenes folder's manifest.json for these
    seeds.  The manifest must be the one BRIDGE_SCENE_MANIFEST names, since
    G19 pins the seeds to their scenes by it (tools/bridge_gates.py)."""
    path = os.path.join(folder, 'manifest.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            scenes = json.load(f)['scenes']
    except (OSError, ValueError, KeyError) as e:
        raise SystemExit(f"no scene manifest in {folder}: {type(e).__name__}: {e}")
    missing = [s for s in seeds if str(s) not in scenes]
    if missing:
        raise SystemExit(f"no scene for seeds {missing} in {path}")
    if (os.path.realpath(os.environ.get('BRIDGE_SCENE_MANIFEST') or '')
            != os.path.realpath(path)):
        raise SystemExit(f"BRIDGE_SCENE_MANIFEST must name {path} (G19 pins the seeds by it)")
    return {s: scenes[str(s)] for s in seeds}


def scene_cwd(a, arm, seed, rep, scene):
    """A working directory that holds the episode's one scene where their
    loader looks, so its random.choice can only load that scene, and their
    env_configs/ (the driver's --config is ./env_configs/find_dice.yml).
    The same folder as tools/gen_scene_eval.py's episode_cwd builds."""
    d = os.path.join(a.out, 'cwd', f'{arm}_s{seed}_r{rep}')
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, PROBLEMS_REL))
    shutil.copyfile(os.path.join(a.scenes, scene), os.path.join(d, PROBLEMS_REL, scene))
    os.symlink(os.path.join(a.cwd, 'env_configs'), os.path.join(d, 'env_configs'))
    return d


def scene_seen(rec):
    """The scene file an episode loaded: the bridge's record, or their
    loader's line on the console when the run left no record (a kill at
    the cap, a crash)."""
    if rec.get('scene_file') and rec['scene_file'] != 'None':
        return rec['scene_file']
    m = SCENE_RE.search(_read_text(os.path.join(rec['save_dir'], 'stdout.txt')))
    return os.path.basename(m.group(1)) if m else None


def _read_text(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''


def _glob_text(save_dir, name):
    return '\n'.join(_read_text(p) for p in
                     sorted(glob.glob(os.path.join(save_dir, 'ours', 'run_*', name))))


def count_carries(save_dir):
    """(carries, losses, pick tries) of the die from the run's files, each
    event counted once (checked on the campaign's check episodes,
    2026-10-31, tests/test_slip_eval.py):

    - the pipeline's prints (the pick tries, the executor's loss lines, the
      goal check's line) are read from run_*.log, which holds each once;
      console_debug.log holds them too but adds a "[console]" echo of every
      ERROR and action line, so it is the fallback with those lines
      dropped; the driver's stdout.txt (the curated console, the echoes
      included, each once) is the last fallback;
    - the verified pick "firm grip" is a curated line: stdout.txt, or the
      console log's "[console]" lines without it.
    Joining the logs, as before 2026-10-31, counted every loss and pick
    try twice."""
    stdout = _read_text(os.path.join(save_dir, 'stdout.txt'))
    console = _glob_text(save_dir, 'console_debug.log')
    pipe = _glob_text(save_dir, 'run_*.log')
    if not pipe.strip():
        pipe = '\n'.join(l for l in console.splitlines() if '[console]' not in l)
    if not pipe.strip():
        pipe = stdout
    curated = stdout if stdout.strip() else '\n'.join(
        l for l in console.splitlines() if '[console]' in l)
    carries = len(CARRY_RE.findall(curated))
    losses = (len(LIFT_LOSS_RE.findall(pipe)) + len(CARRY_LOSS_RE.findall(pipe))
              + min(1, len(GOAL_LOSS_RE.findall(pipe))))
    tries = len(PICK_TRY_RE.findall(pipe))
    return carries, losses, tries


def run_episode(a, arm, seed, rep, extra_args=(), extra_env=None):
    # extra_args / extra_env: BF#63's generated-scene eval adds
    # --save-screenshots on for its failure screenshots; none here.
    save_dir = os.path.join(a.out, arm, f'seed{seed:02d}_r{rep}')
    os.makedirs(save_dir, exist_ok=True)
    cmd = [a.python,
           os.path.join(a.snapshot, 'tampura_bridge', 'run_bridge_on_finddice.py'),
           '--global-seed', str(seed), '--vis', '0', '--save-dir', save_dir,
           '--allow-g19-mismatch', '1', '--slip-fixes', arm_fixes(arm)]
    cmd += arm_args(arm) + list(extra_args)
    env = dict(os.environ, PYTHONHASHSEED='0', PYTHONDONTWRITEBYTECODE='1', **(extra_env or {}))
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
    rec = OrderedDict(arm=arm, seed=seed, rep=rep, rc=rc, timed_out=timed_out,
                      process_wall_s=round(time.time() - t0, 1),
                      started=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t0)),
                      fixes=arm_fixes(arm), save_dir=save_dir)
    if arm_args(arm):
        rec['arm_args'] = arm_args(arm)
    bj = None
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
    rec['carries'], rec['losses'], rec['pick_tries'] = count_carries(save_dir)
    # TB-22 (tracks rule 18): drops, collisions and clean success of the
    # episode, under this harness's success test (the pipeline's goal check);
    # a run killed at the cap keeps the counts up to the kill.
    rec.update(world_counts.from_bridge_episode(
        bj if isinstance(bj, dict) else None, save_dir, _ok(rec)))
    return rec


def _ok(rec):
    return bool(rec and rec.get('metrics') and rec['metrics'].get('outcome') == 'success')


def _finished(rec):
    """The episode ran to the ledger's close (any outcome): its times are
    the pipeline's work, unlike a timeout's or a crash's."""
    return bool(rec and not rec.get('timed_out') and rec.get('metrics')
                and rec['metrics'].get('outcome') and rec['metrics'].get('wall_s') is not None)


def _median(values):
    vals = [float(v) for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _fmt(v, digits=1):
    if v is None:
        return '-'
    return f"{v:.{digits}f}" if isinstance(v, float) else str(v)


def _ratio_median(pairs):
    """The median of the per-seed ratios right / left."""
    rs = [r / l for l, r in pairs if l and r is not None and l > 0]
    return statistics.median(rs) if rs else None


def summary(done, arms, seeds):
    first = {(r['arm'], r['seed']): r for r in done.values() if r.get('rep', 0) == 0}
    arms = [x for x in arms if any((x, s) in first for s in seeds)]
    lines = [f"arms {', '.join(arms)}; seeds {len(seeds)}: {seeds[0]}-{seeds[-1]}" if seeds else 'no seeds',
             f"rows {len(done)} (repetition 0: {len(first)})", '']
    lines.append(f"{'arm':14} {'episodes':>8} {'success':>8} {'timeouts':>8} "
                 f"{'carries':>8} {'losses':>7} {'loss/carry':>10} {'pick tries':>10}")
    per_arm = {}
    for x in arms:
        recs = [r for r in done.values() if r['arm'] == x]
        carries = sum(r.get('carries', 0) for r in recs)
        losses = sum(r.get('losses', 0) for r in recs)
        per_arm[x] = (carries, losses)
        lines.append(f"{x:14} {len(recs):8} {sum(_ok(r) for r in recs):8} "
                     f"{sum(bool(r.get('timed_out')) for r in recs):8} "
                     f"{carries:8} {losses:7} "
                     f"{(losses / carries if carries else float('nan')):10.2f} "
                     f"{sum(r.get('pick_tries', 0) for r in recs):10}")
    finished = [s for s in seeds if all(_finished(first.get((x, s))) for x in arms)]
    lines.append('')
    lines.append(f"medians over the {len(finished)} seeds every arm ran to the ledger's close "
                 f"(repetition 0, any outcome)")
    lines.append(f"{'metric':18}" + ''.join(f"{x:>12}" for x in arms))
    for m in MEDIANS:
        row = {x: _median(first[(x, s)]['metrics'].get(m) for s in finished) for x in arms}
        lines.append(f"{m:18}" + ''.join(f"{_fmt(row[x]):>12}" for x in arms))
    if 'base' in arms:
        lines.append('')
        lines.append('each arm against base on the seeds both ran to the close (repetition 0): '
                     'success, losses per carry, and the median per-seed ratio of wall and planning')
        for x in arms:
            if x == 'base':
                continue
            ws = [s for s in seeds if _finished(first.get(('base', s))) and _finished(first.get((x, s)))]
            b_c = sum(first[('base', s)].get('carries', 0) for s in ws)
            b_l = sum(first[('base', s)].get('losses', 0) for s in ws)
            x_c = sum(first[(x, s)].get('carries', 0) for s in ws)
            x_l = sum(first[(x, s)].get('losses', 0) for s in ws)
            succ = (sum(_ok(first[('base', s)]) for s in ws), sum(_ok(first[(x, s)]) for s in ws))
            parts = []
            for m in ('wall_s', 'planning_s', 'exec_s'):
                pairs = [(first[('base', s)]['metrics'].get(m), first[(x, s)]['metrics'].get(m)) for s in ws]
                parts.append(f"{m} x{_fmt(_ratio_median(pairs), 2)}")
            lines.append(f"  {x:12} ({len(ws)} seeds): success {succ[0]} -> {succ[1]}; "
                         f"losses/carries {b_l}/{b_c} -> {x_l}/{x_c}; " + ', '.join(parts))
    reps = {}
    for r in done.values():
        reps.setdefault((r['arm'], r['seed']), []).append(r)
    rep_groups = {k: v for k, v in reps.items() if len(v) >= 2}
    if rep_groups:
        lines.append('')
        lines.append('replication (the same arm and seed run more than once): outcomes per run, '
                     'and the wall times; "mixed" marks a seed whose runs disagree')
        for x in arms:
            groups = sorted((k, v) for k, v in rep_groups.items() if k[0] == x)
            if not groups:
                continue
            mixed = 0
            cells = []
            for (_, s), runs in groups:
                outs = ['S' if _ok(r) else ('T' if r.get('timed_out') else 'F') for r in runs]
                if len(set(outs)) > 1:
                    mixed += 1
                walls = [r.get('process_wall_s') for r in runs]
                cells.append(f"seed {s}: {''.join(outs)} "
                             f"[{', '.join(_fmt(w, 0) for w in walls)}]"
                             + (' mixed' if len(set(outs)) > 1 else ''))
            lines.append(f"  {x:12} mixed {mixed}/{len(groups)}: " + '; '.join(cells))
    lines.append('')
    lines.append('outcome and wall_s per seed, repetition 0 (x: not run, T: timeout, F: no success)')
    lines.append(f"{'seed':6}" + ''.join(f"{x:>12}" for x in arms))
    for s in seeds:
        cells = []
        for x in arms:
            r = first.get((x, s))
            if r is None:
                cells.append(f"{'x':>12}")
            elif r.get('timed_out'):
                cells.append(f"{'T':>12}")
            elif not _ok(r):
                cells.append(f"{'F ' + _fmt(r.get('process_wall_s'), 0):>12}")
            else:
                cells.append(f"{_fmt(r['metrics'].get('wall_s')):>12}")
        lines.append(f"{s:<6}" + ''.join(cells))
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--snapshot', help='the code snapshot the episodes run from')
    ap.add_argument('--out', required=True)
    ap.add_argument('--seeds', default='0-19')
    ap.add_argument('--arms', default='base')
    ap.add_argument('--reps', type=int, default=1, help='runs of each replicated seed')
    ap.add_argument('--rep-seeds', default='', help='the replicated seeds, e.g. 1,2,5')
    ap.add_argument('--cap', type=float, default=600.0, help='wall cap per episode, s')
    ap.add_argument('--python', default=sys.executable)
    ap.add_argument('--cwd', default=os.path.join(
        os.environ.get('TAMPURA_WORK', '/root/tampura-work'), 'tampura_environments'),
        help="their tampura_environments directory (the driver runs from it)")
    ap.add_argument('--scenes', default='',
                    help="a folder of scenes with a manifest.json: every episode runs in a "
                         "fresh folder that holds only its seed's scene")
    ap.add_argument('--rotate', action='store_true',
                    help="start each seed's arms one arm further (by seed and repetition)")
    ap.add_argument('--summary', action='store_true', help='print the tables of --out and exit')
    a = ap.parse_args(argv)
    seeds = parse_seeds(a.seeds)
    rep_seeds = set(parse_seeds(a.rep_seeds))
    arms = [x.strip() for x in a.arms.split(',') if x.strip()]
    for x in arms:
        arm_fixes(x)                             # a malformed arm fails before any run
    if len(set(arms)) != len(arms):
        raise SystemExit(f"an arm is named twice: {arms}")
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
    a.out = os.path.abspath(a.out)               # an episode may run from its own folder
    if a.scenes:
        a.scenes = os.path.abspath(a.scenes)
    scenes = load_scenes(a.scenes, seeds) if a.scenes else None
    os.makedirs(a.out, exist_ok=True)
    check_arm_flags(a.snapshot, arms)
    check_arms(a, arms)
    md_path = os.path.join(a.out, 'metadata.json')
    if not os.path.isfile(md_path):
        with open(md_path, 'w', encoding='utf-8') as f:
            json.dump({'snapshot': a.snapshot,
                       'snapshot_name': os.path.basename(os.path.normpath(a.snapshot)),
                       'arms': arms, 'fixes': {x: arm_fixes(x) for x in arms},
                       'arm_args': {x: arm_args(x) for x in arms},
                       'seeds': seeds, 'reps': a.reps, 'rep_seeds': sorted(rep_seeds),
                       'cap_s': a.cap, 'python': a.python, 'cwd': a.cwd,
                       'scenes': a.scenes or None, 'rotate': bool(a.rotate),
                       'host': os.uname().nodename, 'job': os.environ.get('SLURM_JOB_ID'),
                       'started': time.strftime('%Y-%m-%d %H:%M:%S')}, f, indent=1)
    todo = [(rep, s, x) for rep in range(max(1, a.reps)) for k, s in enumerate(seeds)
            for x in arm_order(arms, k, rep, a.rotate)
            if (rep == 0 or s in rep_seeds) and (x, s, rep) not in done]
    print(f"[eval] {len(done)} episodes done, {len(todo)} to run: arms {arms}, "
          f"seeds {seeds[0]}-{seeds[-1]}, reps {a.reps} on {sorted(rep_seeds)}", flush=True)
    for i, (rep, s, x) in enumerate(todo, 1):
        print(f"[eval] {i}/{len(todo)} arm {x} seed {s} rep {rep} ...", end=' ', flush=True)
        if scenes:
            ep = argparse.Namespace(**vars(a))
            ep.cwd = scene_cwd(a, x, s, rep, scenes[s])
            rec = run_episode(ep, x, s, rep)
            rec['scene'] = scenes[s]
            rec['scene_seen'] = scene_seen(rec)
            rec['scene_ok'] = rec['scene_seen'] == scenes[s]
            shutil.rmtree(ep.cwd, ignore_errors=True)
        else:
            rec = run_episode(a, x, s, rep)
        done[(x, s, rep)] = rec
        with open(results, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec) + '\n')
        m = rec.get('metrics') or {}
        print(f"{m.get('outcome') or rec.get('bridge_status') or 'no outcome'} "
              f"wall {rec['process_wall_s']} s carries {rec['carries']} losses {rec['losses']}"
              f"{' TIMEOUT' if rec['timed_out'] else ''}", flush=True)
    text = summary(done, arms, seeds)
    with open(os.path.join(a.out, 'summary.txt'), 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
