#!/usr/bin/env python3
"""#P4 B8: the campaign harness (PAPER_AUDIT.txt P4.6, D10, B8).

Both arms on TAMPURA's find_dice, seeds 0-19, two repetitions, serial and
interleaved per seed within a repetition (T k, then O k), each episode under
one wall cap owned here (D10, 900 s), the MACHINE check before every
episode, resumable, every episode appended to campaign.jsonl as it lands
and the campaign's metadata in campaign.json.  Standard library only; it
runs under any Python 3 and only spawns the two drivers:

  arm T  tools/run_tampura_timed.py in THEIR venv (P4.6 ARMS), cwd their
         tampura_environments, --planner tampura_policy_timed, --save-dir
         always given, --vis never given (their parser reads it as bool),
         PYTHONPATH = the snapshot (tampura_bridge.timed_policy only);
  arm O  tampura_bridge/run_bridge_on_finddice.py in arm O's venv (D12),
         cwd their tampura_environments, --vis 0, --max-plan-time = the
         cap (D10's episode-deadline keyword is absent, BF#14; the kill
         here is the cap), the PYTHONPATH of tools/cluster/bridge_run.sbatch.

Success is P4.6 G12: arm T's rewards[-1] == 1.0 from their RolloutHistory,
arm O's the outcome field of its driver (rewards[-1], the error and the
ledger gates).  Arm T's record also carries the standard test of path 6
(DV-1): the physical readings of its final world, written by the reviewed
rollout wrapper into final_world.json, as 'final_world', 'standard_read' and
'standard_success' beside their reward.  A killed or crashed episode is a failure with every time
at the cap, flagged censored (D10).  A gate-failed episode keeps its times
and its gate's name.  Per-run gates (G13, G19) and the HARNESS STOP RULE
(three gate-failed episodes of one arm with the same gate) stop the
campaign; the stalled-episode rule (wall above 1.5 x cap) re-runs once,
flagged.  The cluster wrapper is tools/cluster/b8_campaign.sbatch.

  python tools/_bridge_campaign.py --snapshot SB --tampura-work TW
      --venv-t TW/.venv --venv-o W/armO-venvA --pddlstream-lib W/pddlstream_lib
      --out OUT [--seeds 0-19] [--reps 2] [--cap 900] [--mode full|smoke]
      [--arms T,O] [--machine-check stop|log]
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time

# P4.6 MACHINE: before each episode no other pipeline process may run.
MACHINE_PATTERN = ("test_full_pipeline|run_planner|run_bridge_on_finddice|"
                   "run_tampura_timed|tampura_sweep|_bridge_campaign")
STALL_FACTOR = 1.5          # P4.6 MACHINE: wall above 1.5 x cap is a stall
STOP_RULE_COUNT = 3         # P4.6 HARNESS STOP RULE
PER_RUN_GATES = ('G13', 'G19')
HERE = os.path.abspath(__file__)
sys.path.append(os.path.dirname(os.path.dirname(HERE)))   # the snapshot's root, last
try:                                     # the folders of the folder move (22 Nov 2026) ...
    from world import world_counts  # noqa: E402  (TB-22: drops, collisions, clean success)
except ImportError:                      # ... or a snapshot from before it: the module at the root
    import world_counts  # noqa: E402

# Their RolloutHistory is read in THEIR venv with nothing of ours on the
# path (G6's convention); the reader prints one JSON line.  The pickle is
# the one their rollout wrote seconds earlier on this node (the same read
# as tools/tampura_sweep_cluster.py and B1(g)), never a file from elsewhere.
T_HISTORY_READER = r"""
import glob, json, os, pickle, sys
d = sys.argv[1]
pks = sorted(glob.glob(os.path.join(d, '**', '*.pkl'), recursive=True),
             key=os.path.getmtime)
if not pks:
    print(json.dumps({'history': False}))
    sys.exit(0)
with open(pks[-1], 'rb') as f:
    h = pickle.load(f)
ours = sorted(m for m in sys.modules
              if 'tampura_bridge' in m or m.split('.')[0] in
              ('boxel_env', 'execution', 'perception', 'streams', 'robot_utils',
               # since the folder move our modules load as <folder>.<module>
               'world', 'sensing', 'planning', 'acting', 'console', 'evaluation'))
print(json.dumps({'history': True, 'pkl': pks[-1],
                  'rewards': [float(r) for r in h.rewards],
                  'time_deltas': [float(t) for t in h.time_deltas],
                  'actions': [str(a) for a in h.actions],
                  'ours_loaded': ours}))
"""


def log(*a):
    print(*a, flush=True)


def now_iso():
    return datetime.datetime.now().isoformat(timespec='seconds')


def parse_seeds(s):
    out = []
    for part in str(s).replace(' ', ',').split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            lo, hi = part.split('-')
            out.extend(range(int(lo), int(hi) + 1))
        else:
            out.append(int(part))
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def read_text(path):
    try:
        with open(path, errors='replace') as f:
            return f.read()
    except OSError:
        return ''


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_jsonl(path):
    rows = []
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return rows


def write_json(path, payload):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(payload, f, indent=1, default=str)
    os.replace(tmp, path)


def append_jsonl(path, rec):
    with open(path, 'a') as f:
        f.write(json.dumps(rec, default=str) + '\n')
        f.flush()
        os.fsync(f.fileno())


def cpu_model():
    try:
        for line in open('/proc/cpuinfo'):
            if line.startswith('model name'):
                return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return None


def machine_check():
    """Other pipeline processes visible to pgrep, this harness and its
    parent shell excluded (P4.6 MACHINE)."""
    try:
        out = subprocess.run(['pgrep', '-af', MACHINE_PATTERN],
                             capture_output=True, text=True).stdout.splitlines()
    except OSError:
        return []
    mine = {str(os.getpid()), str(os.getppid())}
    return [l for l in out if l.split(' ', 1)[0] not in mine]


def load_bridge_gates(snapshot):
    """tools/bridge_gates.py of the snapshot (standard library only): G19's
    pinned map, one place only."""
    path = os.path.join(snapshot, 'tools', 'bridge_gates.py')
    spec = importlib.util.spec_from_file_location('_campaign_bridge_gates', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_capped(cmd, cwd, env, cap, console):
    """One episode under the wall cap; on timeout the whole process group
    is killed.  Returns (returncode, wall_s, wall_clock_s, timed_out)."""
    t0 = time.perf_counter()
    w0 = time.time()
    with open(console, 'w') as cf:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=cf,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = proc.wait(timeout=cap)
            timed_out = False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            rc = proc.wait()
            timed_out = True
    return rc, round(time.perf_counter() - t0, 3), round(time.time() - w0, 3), timed_out


def scene_from(text):
    m = re.search(r'Loading scene from (\S+)', text)
    return m.group(1) if m else None


def symk_times(text):
    return [float(x) for x in re.findall(r'Time:\s*([0-9]+\.?[0-9]*)', text)]


def base_record(arm, rep, seed, order, a, cmd, save_dir, console):
    return {
        'arm': arm, 'rep': rep, 'seed': seed, 'order': order, 'mode': a.mode,
        'started': now_iso(), 'cmd': cmd, 'save_dir': save_dir,
        'console': console, 'wall_s': None, 'wall_clock_s': None,
        'returncode': None, 'timed_out': False, 'status': None,
        'success': False, 'censored': False, 'cap_s': a.cap,
        'loop_s': None, 'scene_file': None, 'pinned_scene': None,
        'scene_ok': None, 'rewards': None, 'time_deltas': None,
        'solve_step': None, 'time_to_success_s': None, 'max_reward': None,
        'n_actions': None, 'n_macro_actions': None, 'n_dispatched': None,
        'planning_s': None, 'setup_share_s': None, 'symk_solve_s': None,
        'g13_ok': None, 'gate_failures': {}, 'error': None, 'run_dir': None,
        'machine_check_others': [], 'stalled': False, 'stall_rerun': False,
        'note': '',
    }


def finish_times(rec, rewards, time_deltas, cap):
    rec['rewards'] = rewards
    rec['time_deltas'] = time_deltas
    if rewards:
        rec['max_reward'] = max(rewards)
        rec['solve_step'] = next((i for i, r in enumerate(rewards) if r == 1.0), None)
    if time_deltas:
        rec['loop_s'] = round(time_deltas[-1], 3)
        if rec['solve_step'] is not None and rec['solve_step'] < len(time_deltas):
            rec['time_to_success_s'] = round(time_deltas[rec['solve_step']], 3)
    if rec['loop_s'] is None:
        rec['loop_s'] = cap
        rec['censored'] = True


def child_env(a, venv, pythonpath):
    env = os.environ.copy()
    env['PATH'] = os.path.join(venv, 'bin') + os.pathsep + env.get('PATH', '')
    env['VIRTUAL_ENV'] = venv
    env.pop('PYTHONHOME', None)
    env['PYTHONPATH'] = pythonpath
    env['PYTHONHASHSEED'] = a.pythonhashseed
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['BOXEL_EYE_IMAGES'] = '0'           # no sim screenshots (BF#17)
    env['TAMPURA_WORK'] = a.tampura_work
    return env


def read_history_t(a, save_dir):
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env['PATH'] = os.path.join(a.venv_t, 'bin') + os.pathsep + env.get('PATH', '')
    try:
        out = subprocess.run([os.path.join(a.venv_t, 'bin', 'python'), '-c',
                              T_HISTORY_READER, save_dir], cwd=save_dir, env=env,
                             capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'history': False, 'read_error': repr(e)}
    for line in reversed(out.stdout.splitlines()):
        line = line.strip()
        if line.startswith('{'):
            try:
                return json.loads(line)
            except ValueError:
                break
    return {'history': False, 'read_error': (out.stderr or out.stdout)[-800:]}


def move_stale_dir(path):
    """D-15: a folder that already holds an earlier run (an episode cut by a
    kill and run again on resume, or a relaunch into the same --out) is
    renamed to the first free sibling <name>.stale<k>, k = 1, 2, ..., so the
    new run starts empty and reads nothing of the old one.  Renamed, never
    deleted: the retention sweeps own run data.  Returns the new path, or
    None when nothing was moved (no folder, an empty one, or a file there)."""
    if not os.path.isdir(path) or not os.listdir(path):
        return None
    k = 1
    while os.path.lexists(f'{path}.stale{k}'):
        k += 1
    os.rename(path, f'{path}.stale{k}')
    return f'{path}.stale{k}'


def episode_t(a, rep, seed, order, scene_map, others, stall_rerun=False):
    save_dir = os.path.join(a.out, f'rep{rep}', 'T', f'seed{seed}'
                            + ('_rerun' if stall_rerun else ''))
    stale = move_stale_dir(save_dir)        # D-15: every run starts empty
    os.makedirs(save_dir, exist_ok=True)
    console = os.path.join(save_dir, 'console.txt')
    cmd = [os.path.join(a.venv_t, 'bin', 'python'), '-u',
           os.path.join(a.snapshot, 'tools', 'run_tampura_timed.py'),
           '--config', './env_configs/find_dice.yml',
           '--planner', 'tampura_policy_timed',
           '--global-seed', str(seed), '--save-dir', save_dir]
    if a.mode == 'smoke':
        cmd += ['--max-steps', '1']
    env = child_env(a, a.venv_t, a.snapshot)
    rec = base_record('T', rep, seed, order, a, cmd, save_dir, console)
    rec['machine_check_others'] = others
    rec['stall_rerun'] = stall_rerun
    rec['stale_dir_moved_to'] = stale
    if stale:
        rec['note'] += f'this folder held an earlier run, moved to {stale}; '
    rc, wall, wall_clock, timed_out = run_capped(cmd, a.their_envs, env, a.cap, console)
    rec.update(returncode=rc, wall_s=wall, wall_clock_s=wall_clock, timed_out=timed_out)
    text = read_text(console)
    for name in sorted(os.listdir(save_dir)):
        if name.endswith('.log'):
            text += read_text(os.path.join(save_dir, name))
    rec['scene_file'] = scene_from(text)
    rec['pinned_scene'] = scene_map.get(seed)
    rec['scene_ok'] = bool(rec['scene_file'] and rec['pinned_scene']
                           and rec['pinned_scene'] in rec['scene_file'])
    g13 = read_json(os.path.join(save_dir, 'g13_runtime.json'))
    rec['g13_ok'] = None if g13 is None else bool(g13.get('ok'))
    # DV-1 (path 6): the standard success test, read from their final world by
    # the reviewed rollout wrapper (tampura_bridge/final_world.py); their own
    # reward stays in 'status' and 'rewards'.  No file, or ok false = unread.
    fwj = read_json(os.path.join(save_dir, 'final_world.json'))
    rec['final_world'] = fwj
    rec['standard_read'] = bool(fwj and fwj.get('ok'))
    rec['standard_success'] = bool(rec['standard_read'] and fwj.get('standard_success'))
    spans = read_jsonl(os.path.join(save_dir, 'get_action_spans.jsonl'))
    rec['get_action_spans'] = [s.get('get_action_s') for s in spans]
    rec['get_action_actions'] = [s.get('action') for s in spans]
    rec['planning_s'] = round(sum(s.get('get_action_s') or 0 for s in spans), 3) if spans else None
    st = symk_times(text)
    rec['symk_solve_s'] = round(sum(st), 3) if st else None
    hist = {'history': False} if timed_out else read_history_t(a, save_dir)
    rec['history_read'] = {k: v for k, v in hist.items()
                           if k in ('history', 'pkl', 'ours_loaded', 'read_error')}
    if hist.get('ours_loaded'):
        rec['note'] += f"our modules loaded while reading their pickle: {hist['ours_loaded']}; "
    rewards = hist.get('rewards') or []
    time_deltas = hist.get('time_deltas') or []
    if hist.get('history'):
        actions = hist.get('actions') or []
        rec['n_actions'] = len([x for x in actions if x != 'None'])
        rec['n_macro_actions'] = rec['n_actions']   # their actions are macro
        rec['n_dispatched'] = rec['n_actions']
    finish_times(rec, rewards, time_deltas, a.cap)
    if getattr(a, 'drop_t_history', False) and hist.get('history') and hist.get('pkl'):
        # BF#59: the record above holds everything the campaign reads from
        # the pickle; the pickle itself goes (data hygiene, by path).
        try:
            size = os.path.getsize(hist['pkl'])
            os.remove(hist['pkl'])
            rec['history_dropped'] = {'pkl': hist['pkl'], 'bytes': size}
            rec['note'] += f"RolloutHistory pickle deleted after reading ({size} bytes); "
        except OSError as e:
            rec['note'] += f"RolloutHistory pickle not deleted: {e}; "
    if timed_out:
        rec['status'] = 'killed'
        rec['note'] += f'killed at the {a.cap} s cap; '
    elif rec['g13_ok'] is False or 'G13 runtime check failed' in text:
        rec['status'] = 'gate_failed'
        rec['gate_failures']['G13'] = (g13 or {}).get('failures') or 'G13 runtime check failed'
    elif not hist.get('history'):
        rec['status'] = 'crashed'
        rec['error'] = f"rc {rc}, no RolloutHistory ({hist.get('read_error', '')[:300]})"
    else:
        rec['status'] = 'success' if rewards and rewards[-1] == 1.0 else 'failure'
    if not rec['scene_ok'] and rec['status'] not in ('killed',):
        rec['gate_failures']['G19'] = (f"loaded {rec['scene_file']}, "
                                       f"pinned {rec['pinned_scene']}")
        if rec['status'] in ('success', 'failure'):
            rec['status'] = 'gate_failed'
    if rec['status'] in ('killed', 'crashed'):
        rec['censored'] = True
        rec['loop_s'] = a.cap
    rec['success'] = rec['status'] == 'success'
    if rc == 139 and rec['status'] == 'success':
        rec['note'] += 'rc 139 after the history was written (pybullet teardown); '
    # TB-22 (tracks rule 18): their carry is kinematic, so a drop cannot
    # happen; their find_dice execution reports no collision, so that count
    # is "not detected" (never a 0 nothing could see).
    rec.update(world_counts.kinematic_arm_fields(rec['success']))
    return rec


def ledger_stats(rows):
    steps = [r for r in rows if r.get('kind') == 'step']
    ends = {(r.get('plan'), r.get('step')): r.get('status')
            for r in rows if r.get('kind') == 'step_end'}
    clock = next((r for r in rows if r.get('kind') == 'driver_clock'), None)
    start = None
    if clock:
        try:
            start = dict((n, t) for n, t in clock.get('events', [])).get('rollout_start')
        except (TypeError, ValueError):
            start = None
    first_plan = next((r.get('t') for r in rows if r.get('kind') == 'plan_call'), None)
    bt = next((r for r in rows if r.get('kind') == 'bridge_timing'), {})
    return {
        'n_dispatched': len(steps),
        'n_macro_actions': sum(1 for s in steps if s.get('action') != 'move'),
        'actions': [(s.get('plan'), s.get('step'), s.get('action'),
                     ends.get((s.get('plan'), s.get('step')))) for s in steps],
        'setup_share_s': (round(first_plan - start, 3)
                          if start is not None and first_plan is not None else None),
        'd9_setup_s': bt.get('d9_setup_s'), 'env_build_s': bt.get('env_build_s'),
    }


def episode_o(a, rep, seed, order, scene_map, others, stall_rerun=False):
    save_dir = os.path.join(a.out, f'rep{rep}', 'O', f'seed{seed}'
                            + ('_rerun' if stall_rerun else ''))
    os.makedirs(save_dir, exist_ok=True)
    console = os.path.join(save_dir, 'console.txt')
    cmd = [os.path.join(a.venv_o, 'bin', 'python'), '-u',
           os.path.join(a.snapshot, 'tampura_bridge', 'run_bridge_on_finddice.py'),
           '--global-seed', str(seed), '--vis', '0',
           '--stop-before-planning', '1' if a.mode == 'smoke' else '0',
           '--max-plan-time', str(a.cap), '--save-dir', save_dir]
    pythonpath = os.pathsep.join([a.snapshot, a.pddlstream_lib,
                                  os.path.join(a.tampura_work, 'tampura'),
                                  a.their_envs])
    env = child_env(a, a.venv_o, pythonpath)
    rec = base_record('O', rep, seed, order, a, cmd, save_dir, console)
    rec['machine_check_others'] = others
    rec['stall_rerun'] = stall_rerun
    rc, wall, wall_clock, timed_out = run_capped(cmd, a.their_envs, env, a.cap, console)
    rec.update(returncode=rc, wall_s=wall, wall_clock_s=wall_clock, timed_out=timed_out)
    text = read_text(console)
    be = read_json(os.path.join(save_dir, 'bridge_episode.json'))
    rec['pinned_scene'] = scene_map.get(seed)
    g13 = read_json(os.path.join(save_dir, 'g13_runtime.json'))
    rec['g13_ok'] = None if g13 is None else bool(g13.get('ok'))
    rewards, time_deltas = [], []
    if be is not None:
        rewards = [float(r) for r in be.get('rewards') or []]
        time_deltas = [float(t) for t in be.get('time_deltas') or []]
        rec['scene_file'] = be.get('scene_file')
        rec['run_dir'] = be.get('run_dir')
        rec['scene_changed_by_settle'] = be.get('scene_changed_by_settle')
        rec['settle_max_dxy_m'] = be.get('settle_max_dxy_m')
        rec['settle'] = be.get('settle')
        rec['readback_identical'] = be.get('readback_identical')
        rec['ledger_gates'] = be.get('ledger_gates')
        rec['gate_info'] = be.get('gates')
        rec['switches'] = be.get('switches')      # BF#41: M8 to M10, the squeeze
        out = be.get('outcome') or {}
        rec['outcome_status'] = out.get('status')
        rec['error'] = out.get('error')
        rec['gate_failures'] = dict(out.get('gate_failures') or {})
    else:
        rec['scene_file'] = scene_from(text)
    rec['scene_ok'] = bool(rec['scene_file'] and rec['pinned_scene']
                           and rec['pinned_scene'] in rec['scene_file'])
    run_dir = rec['run_dir']
    if run_dir and os.path.isdir(run_dir):
        ts = read_json(os.path.join(run_dir, 'timing_summary.json')) or {}
        rec['planning_s'] = ts.get('total_planning_time_s')
        rec['per_call_planning_s'] = ts.get('per_call_planning_time_s')
        rec['plan_count'] = ts.get('plan_count')
        rec['exit_reason'] = ts.get('exit_reason')
        rec['n_sense_actions'] = ts.get('n_sense_actions')
        m8 = ts.get('m8') or {}
        rec['parked_count'] = len(m8.get('parked') or []) if isinstance(m8, dict) else None
        rec['run_config'] = ts.get('run_config')
        rec.update(ledger_stats(read_jsonl(os.path.join(run_dir, 'ledger.jsonl'))))
    finish_times(rec, rewards, time_deltas, a.cap)
    if timed_out:
        rec['status'] = 'killed'
        rec['note'] += f'killed at the {a.cap} s cap; '
    elif be is None:
        m = re.search(r'^G19: seed .*$', text, re.M)
        if m:
            rec['status'] = 'gate_failed'
            rec['gate_failures']['G19'] = m.group(0)
        elif 'G13 runtime check failed' in text or rec['g13_ok'] is False:
            rec['status'] = 'gate_failed'
            rec['gate_failures']['G13'] = (g13 or {}).get('failures') or 'G13 runtime check failed'
        else:
            rec['status'] = 'crashed'
            rec['error'] = f'rc {rc}, no bridge_episode.json'
    else:
        rec['status'] = rec['outcome_status'] or 'crashed'
    if rec['status'] in ('killed', 'crashed'):
        rec['censored'] = True
        rec['loop_s'] = a.cap
    rec['success'] = (be is not None and bool((be.get('outcome') or {}).get('success'))
                      and rec['status'] == 'success')
    # TB-22 (tracks rule 18): the simulator's drops and collisions of the
    # episode; a run killed at the cap keeps the counts up to the kill.
    rec.update(world_counts.from_bridge_episode(be, save_dir, rec['success']))
    return rec


def freeze_sha(venv):
    try:
        out = subprocess.run([os.path.join(venv, 'bin', 'python'), '-m', 'pip', 'freeze'],
                             capture_output=True, text=True, timeout=600).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        return f'unavailable: {e!r}'
    return hashlib.sha256(out.encode()).hexdigest()


def git_head(path):
    try:
        return subprocess.run(['git', '-C', path, 'rev-parse', 'HEAD'],
                              capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return f'unavailable: {e!r}'


def squeeze_defaults(snapshot):
    """The pipeline's pick squeeze (robot_utils.GRIP_SQUEEZE) and the
    driver's --grip-squeeze-mm default, read from the snapshot's source so
    the campaign record names the value every arm O episode ran with
    (BF#38, BF#41); None where a line is not found."""
    out = {}
    ru = os.path.join(snapshot, 'acting', 'robot_utils.py')    # the folders of the folder move ...
    if not os.path.isfile(ru):
        ru = os.path.join(snapshot, 'robot_utils.py')          # ... or a snapshot from before it
    m = re.search(r'^GRIP_SQUEEZE\s*=\s*([0-9.eE+-]+)',
                  read_text(ru), re.M)
    out['robot_utils_GRIP_SQUEEZE_m'] = float(m.group(1)) if m else None
    m = re.search(r"--grip-squeeze-mm'[^\n]*default=([0-9.eE+-]+)",
                  read_text(os.path.join(snapshot, 'tampura_bridge',
                                         'run_bridge_on_finddice.py')))
    out['driver_grip_squeeze_mm_default'] = float(m.group(1)) if m else None
    return out


def metadata(a, seeds, arms):
    domain = ''
    try:
        domain = subprocess.run([os.path.join(a.venv_o, 'bin', 'python'),
                                 os.path.join(a.snapshot, 'tools', 'bridge_gates.py'),
                                 'domain'], cwd=a.snapshot, capture_output=True,
                                text=True, timeout=600).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        domain = f'unavailable: {e!r}'
    return {
        'harness': {'file': HERE, 'sha256': sha256_file(HERE)},
        'snapshot': {'dir': a.snapshot,
                     'sha': os.path.basename(a.snapshot.rstrip('/')).split('_', 1)[-1]},
        'their_commits': {
            'tampura': git_head(os.path.join(a.tampura_work, 'tampura')),
            'tampura_environments': git_head(a.their_envs)},
        'venvs': {'arm_T': a.venv_t, 'arm_O': a.venv_o,
                  'd12_choice': 'arm O in its own venv holding arm T package set (A)'},
        'pip_freeze_sha256': {'arm_T': freeze_sha(a.venv_t), 'arm_O': freeze_sha(a.venv_o)},
        'find_dice_yml': read_text(os.path.join(a.their_envs, 'env_configs', 'find_dice.yml')),
        'task_spec_sha256': sha256_file(os.path.join(a.snapshot, 'tampura_bridge', 'task_spec.py')),
        'squeeze': squeeze_defaults(a.snapshot),
        'domain_gates': domain,
        'machine': {'host': os.uname().nodename, 'cpu_model': cpu_model(),
                    'nproc': os.cpu_count(), 'kernel': os.uname().release,
                    'slurm_job_id': os.environ.get('SLURM_JOB_ID'),
                    'pythonhashseed': a.pythonhashseed},
        'protocol': {
            'cap_s': a.cap, 'max_plan_time_s': a.cap,
            'episode_deadline_keyword': 'absent (D10 state at BF#14): the harness kill is the cap',
            'order': 'repetition outer; seeds ascending; T then O per seed',
            'stall_factor': STALL_FACTOR, 'stop_rule_count': STOP_RULE_COUNT,
            'per_run_gates': list(PER_RUN_GATES),
            'success': ('P4.6 G12: arm T rewards[-1] == 1.0 from their RolloutHistory; '
                        'arm O the outcome field of its driver (rewards[-1], error, '
                        'ledger gates); the shared success test of BF#37 item 2 is '
                        'not applied (Q18 open)'),
            'mode': a.mode, 'seeds': seeds, 'reps': a.reps, 'arms': arms,
            'machine_check': a.machine_check},
        'started': now_iso(), 'status': 'running', 'resumed': [],
    }


def load_done(jsonl):
    records = read_jsonl(jsonl)
    done = set()
    for r in records:
        if not r.get('stalled'):
            done.add(f"{r['arm']}:{r['rep']}:{r['seed']}")
    return done, records


def summary(records):
    out = {}
    for r in records:
        if r.get('stalled'):
            continue
        key = f"{r['arm']}_rep{r['rep']}"
        s = out.setdefault(key, {'n': 0, 'success': 0, 'statuses': {}, 'censored': 0})
        s['n'] += 1
        s['success'] += 1 if r.get('success') else 0
        s['statuses'][r.get('status')] = s['statuses'].get(r.get('status'), 0) + 1
        s['censored'] += 1 if r.get('censored') else 0
    return out


def print_table(records, reps):
    latest = {}
    for r in records:
        if not r.get('stalled'):
            latest[(r['arm'], r['rep'], r['seed'])] = r
    seeds = sorted({k[2] for k in latest})
    head = f"{'seed':>4} {'scene':<11}"
    for rep in range(1, reps + 1):
        head += f" {'T r' + str(rep):<11} {'O r' + str(rep):<11} {'T s':>7} {'O s':>7}"
    log(head)
    for seed in seeds:
        line = f"{seed:>4} "
        scene = None
        for rep in range(1, reps + 1):
            for arm in ('T', 'O'):
                r = latest.get((arm, rep, seed))
                if r and r.get('scene_file') and scene is None:
                    scene = str(r['scene_file'])[:10]
        line += f"{scene or '?':<11}"
        for rep in range(1, reps + 1):
            cells = []
            times = []
            for arm in ('T', 'O'):
                r = latest.get((arm, rep, seed))
                cells.append(f"{(r.get('status') or '?') if r else '-':<11}")
                times.append(f"{(str(r.get('loop_s')) + ('*' if r.get('censored') else '')) if r else '-':>7}")
            line += ' ' + ' '.join(cells) + ' ' + ' '.join(times)
        log(line)
    log("(* = censored at the cap; status per P4.6: success, failure, gate_failed, crashed, killed)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--snapshot', required=True, help='immutable snapshot of our code (sb_<sha>)')
    ap.add_argument('--tampura-work', required=True, help='their tree: tampura, tampura_environments')
    ap.add_argument('--venv-t', required=True, help="arm T's venv (their venv)")
    ap.add_argument('--venv-o', required=True, help="arm O's venv (D12 candidate A)")
    ap.add_argument('--pddlstream-lib', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--seeds', default='0-19')
    ap.add_argument('--reps', type=int, default=2)
    ap.add_argument('--cap', type=float, default=900.0, help='wall cap per episode, s (D10)')
    ap.add_argument('--mode', choices=('full', 'smoke'), default='full',
                    help='smoke: T --max-steps 1, O --stop-before-planning 1')
    ap.add_argument('--arms', default='T,O')
    ap.add_argument('--machine-check', choices=('stop', 'log'), default='stop')
    ap.add_argument('--pythonhashseed', default='0')
    # BF#59: their per-episode RolloutHistory pickle (12 to 16 MB allocated
    # each on the cluster) is deleted once its rewards, times and actions are
    # in the episode's record, so a campaign of 60 T episodes stays under
    # the cluster's 1 GiB cap (BF#49); the deletion is noted in the record.
    ap.add_argument('--drop-t-history', action='store_true',
                    help="delete arm T's RolloutHistory pickle after reading it")
    a = ap.parse_args()
    a.snapshot = os.path.abspath(a.snapshot)
    a.tampura_work = os.path.abspath(a.tampura_work)
    a.venv_t = os.path.abspath(a.venv_t)
    a.venv_o = os.path.abspath(a.venv_o)
    a.pddlstream_lib = os.path.abspath(a.pddlstream_lib)
    a.out = os.path.abspath(a.out)
    a.their_envs = os.path.join(a.tampura_work, 'tampura_environments')
    seeds = parse_seeds(a.seeds)
    arms = [x.strip() for x in a.arms.split(',') if x.strip()]
    for arm in arms:
        if arm not in ('T', 'O'):
            ap.error(f'unknown arm {arm}')
    os.makedirs(a.out, exist_ok=True)
    jsonl = os.path.join(a.out, 'campaign.jsonl')
    md_path = os.path.join(a.out, 'campaign.json')
    done, records = load_done(jsonl)
    md = read_json(md_path)
    if md is None:
        md = metadata(a, seeds, arms)
    else:
        md.setdefault('resumed', []).append(now_iso())
        md['status'] = 'running'
    write_json(md_path, md)
    scene_map = load_bridge_gates(a.snapshot).SCENE_MAP
    log(f"[campaign] {a.mode}: arms {arms}, seeds {seeds}, reps {a.reps}, cap {a.cap} s, "
        f"out {a.out}; {len(done)} episodes already done")
    gate_counts = {}
    for r in records:
        if not r.get('stalled'):
            for g in (r.get('gate_failures') or {}):
                gate_counts[(r['arm'], g)] = gate_counts.get((r['arm'], g), 0) + 1
    stop = None
    order = len(records)
    runners = {'T': episode_t, 'O': episode_o}
    for rep in range(1, a.reps + 1):
        for seed in seeds:
            for arm in arms:
                key = f'{arm}:{rep}:{seed}'
                if key in done:
                    continue
                others = machine_check()
                if others:
                    log(f'[campaign] MACHINE: other pipeline processes before {key}: {others}')
                    if a.machine_check == 'stop':
                        stop = {'rule': 'MACHINE', 'before': key, 'processes': others}
                        break
                log(f'[campaign] {now_iso()} start {key}')
                rec = runners[arm](a, rep, seed, order, scene_map, others)
                order += 1
                if (rec['wall_clock_s'] or 0) > STALL_FACTOR * a.cap:
                    rec['stalled'] = True
                    rec['note'] += (f"stalled: wall clock {rec['wall_clock_s']} s above "
                                    f"{STALL_FACTOR} x cap, re-run once (P4.6); ")
                    append_jsonl(jsonl, rec)
                    records.append(rec)
                    log(f"[campaign] {key} STALLED ({rec['wall_clock_s']} s), re-running once")
                    rec = runners[arm](a, rep, seed, order, scene_map, machine_check(),
                                       stall_rerun=True)
                    order += 1
                append_jsonl(jsonl, rec)
                records.append(rec)
                done.add(key)
                log(f"[campaign] {key} {rec['status']} loop_s={rec['loop_s']}"
                    f"{'*' if rec['censored'] else ''} wall_s={rec['wall_s']} "
                    f"rc={rec['returncode']} scene={rec['scene_file']} "
                    f"gates={list((rec.get('gate_failures') or {}).keys())} "
                    f"{rec['note']}")
                for g in (rec.get('gate_failures') or {}):
                    if g in PER_RUN_GATES:
                        stop = {'rule': 'PER_RUN_GATE', 'episode': key, 'gate': g,
                                'detail': rec['gate_failures'][g]}
                    gate_counts[(arm, g)] = gate_counts.get((arm, g), 0) + 1
                    if gate_counts[(arm, g)] >= STOP_RULE_COUNT and stop is None:
                        stop = {'rule': 'HARNESS_STOP', 'arm': arm, 'gate': g,
                                'count': gate_counts[(arm, g)], 'episode': key}
                if stop:
                    break
            if stop:
                break
        if stop:
            break
    md['finished'] = now_iso()
    md['status'] = 'stopped' if stop else 'finished'
    md['stop'] = stop
    md['summary'] = summary(records)
    md['n_records'] = len(records)
    write_json(md_path, md)
    log('[campaign] ' + ('STOPPED: ' + json.dumps(stop) if stop else 'finished'))
    for k, s in sorted(md['summary'].items()):
        log(f"[campaign] {k}: {s['success']}/{s['n']} success, statuses {s['statuses']}, "
            f"{s['censored']} censored")
    print_table(records, a.reps)
    log(f'[campaign] records in {jsonl}, metadata in {md_path}')
    return 2 if stop else 0


if __name__ == '__main__':
    sys.exit(main())
