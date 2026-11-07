#!/usr/bin/env python3
"""BF#63: both arms on find_dice scenes made by TAMPURA's own generator.

The scenes are tampura_bridge/gen_scenes/find_dice/ (tools/
gen_find_dice_scenes.py: their env_generator.py unmodified, scene s the first
it accepts after random.seed(s)); its manifest pins each seed to its scene
for G19 (BRIDGE_SCENE_MANIFEST, tools/bridge_gates.py).  Their loader picks
random.choice(os.listdir('tampura_environments/find_dice/problems')) from the
working directory, so every episode runs in a fresh directory of its own
that holds that one scene (and a link to their env_configs/): the episode
loads its scene whatever the seed draws, with their code and their tree
untouched.  The global seed of an episode is its scene's seed.

Per repetition the scenes are the outer loop and the arms run back to back
on each scene (T, then O), so both arms of a scene meet the same machine.
The episodes are the BF#59 ones: arm T is tools/_bridge_campaign.py's
episode_t (their planner as shipped; success is their rewards[-1] == 1.0),
arm O is tools/slip_eval.py's run_episode with BF#62's four switches named
(success is the bridge's outcome 'success' and the pipeline's own goal
check), both under the same wall cap (900 s in tools/cluster/
gen_eval.sbatch, B8's D10 value).

ARM O2 (path 6, PLAN.md P6-Q9): arm O's episode again, from a second snapshot
(--snapshot-o2: arm O's snapshot plus one fix, TB-1, and nothing else; the
runner prints the two snapshots' scene files and manifest equal or stops), run
on the same scenes with the same switches, same venv, same cap.  --arms picks
the arms (T,O by default; T,O,O2 runs the three back to back per scene; O2
alone runs the fix later on scenes already pinned).  The report then adds the
pairs O2 against O and O2 against T; with the default arms it is BF#63's.

VALIDITY (declared before any run): an episode counts if it loaded its own
scene and ended with an outcome: success, failure, or the cap (a timeout is
a failure of that arm).  It does not count if it crashed (no outcome), a
gate failed, or it loaded another scene; such an episode runs once more
with the same scene, seed and repetition, and if that run does not count
either, the scene's repetition leaves the paired comparison for both arms
and is listed.

SCREENSHOTS (Hani, 2026-11-03: a failed run keeps the screenshot that
explains it, with its metadata): every run that is not a counted success,
of either arm, gets OUT/failures/<arm>_s<seed>_r<rep>_a<attempt>/ with
meta.json and its last two camera views: arm T's from its RolloutHistory
(their look observations carry the wrist camera's image; read in their venv
like _bridge_campaign's history reader; a run killed at the cap wrote no
history, so its folder holds the metadata alone; their driver stays
run_planner.py's copy, so nothing renders their final scene), arm O's
final scene from two fixed cameras over the table (the bridge's
overview_final*.png, made after the rollout; the one that shows where the
die ended up) and its last eye images (--save-screenshots on), with the
curated console's tail and the eye's last record (true and believed
poses).  A success's images are deleted, and so
are every run's other images (--shots all keeps the views of successes too,
for a check; none takes no screenshot).

  <arm O python> tools/gen_scene_eval.py --snapshot SB --out OUT --seeds 100-103 \\
      --reps 2 --python-o PY --venv-t TW/.venv --tampura-work TW [--cap 600]
      [--shots failures|all|none] [--arms T,O,O2 --snapshot-o2 SB2]
  python tools/gen_scene_eval.py --report OUT [OUT ...]     the tables
"""
import argparse
import glob
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _bridge_campaign as bc  # noqa: E402
import slip_eval as se  # noqa: E402

# Arm O: BF#62's default set, named so the record says what ran.
ARM_O = 'solver_iters+force_hold+pose_radius_keep+grasp_wrist_home'
SCENES_REL = os.path.join('tampura_bridge', 'gen_scenes', 'find_dice')
PROBLEMS_REL = os.path.join('tampura_environments', 'find_dice', 'problems')
SCENE_RE = re.compile(r'Loading scene from (\S+)')
SHOTS_KEPT = 2
ARMS_ALL = ('T', 'O', 'O2')          # the order they run and print in
ARMS_DEFAULT = ('T', 'O')


def parse_arms(spec, snapshot_o2=None):
    """The arms of a run, in the order they run: 'T,O' (the default), 'T,O,O2',
    'O2' alone.  O2 needs its snapshot."""
    names = [s.strip() for s in str(spec).replace('+', ',').split(',') if s.strip()]
    bad = [n for n in names if n not in ARMS_ALL]
    if bad or not names or len(set(names)) != len(names):
        raise SystemExit(f"--arms {spec!r}: expected a non-empty list of distinct arms from {ARMS_ALL}")
    if 'O2' in names and not snapshot_o2:
        raise SystemExit("arm O2 needs --snapshot-o2 (arm O's snapshot plus TB-1)")
    if 'O2' not in names and snapshot_o2:
        raise SystemExit("--snapshot-o2 given but --arms does not name O2")
    return tuple(n for n in ARMS_ALL if n in names)


def check_same_scenes(snapshot_a, snapshot_b, seeds, manifest):
    """The two snapshots hold the same manifest and the same scene file for
    every seed of the run (byte for byte), so O and O2 meet the same scenes
    under the same G19 pins."""
    import hashlib

    def digest(path):
        with open(path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()

    names = ['manifest.json'] + [manifest['scenes'][str(s)] for s in seeds]
    diff = [n for n in names
            if digest(os.path.join(snapshot_a, SCENES_REL, n)) != digest(os.path.join(snapshot_b, SCENES_REL, n))]
    if diff:
        raise SystemExit(f"the snapshots' scene files differ ({len(diff)}): {diff[:5]}")


# Arm T's last camera views from its RolloutHistory, run in their venv with
# nothing of ours on the path (the history reader's convention); prints one
# JSON line.  The observation at index i follows the action at index i.
# The pickle is the one their rollout wrote seconds earlier in this
# episode's own save directory, never a file from elsewhere (the same trust
# as _bridge_campaign's T_HISTORY_READER).
T_SHOTS_READER = r"""
import glob, json, os, pickle, sys
import numpy as np
from PIL import Image
d, out, keep = sys.argv[1], sys.argv[2], int(sys.argv[3])
pks = sorted(glob.glob(os.path.join(d, '**', '*.pkl'), recursive=True), key=os.path.getmtime)
if not pks:
    print(json.dumps({'images': [], 'note': 'no RolloutHistory (killed or crashed before it was written)'}))
    sys.exit(0)
with open(pks[-1], 'rb') as f:
    h = pickle.load(f)
shots = [(i, o.camera_image) for i, o in enumerate(h.observations)
         if getattr(o, 'camera_image', None) is not None]
os.makedirs(out, exist_ok=True)
saved = []
for i, ci in shots[-keep:]:
    rgb = np.asarray(ci.rgbPixels)
    if rgb.ndim != 3:
        continue
    name = 'tampura_step%02d_camera.png' % i
    Image.fromarray(rgb[:, :, :3].astype(np.uint8)).save(os.path.join(out, name))
    saved.append({'file': name, 'step': i,
                  'action': str(h.actions[i]) if i < len(h.actions) else None})
print(json.dumps({'images': saved, 'camera_observations': [i for i, _ in shots],
                  'actions': [str(a) for a in h.actions]}))
"""


def t_shots(a, save_dir, dest):
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env['PATH'] = os.path.join(a.venv_t, 'bin') + os.pathsep + env.get('PATH', '')
    try:
        out = subprocess.run([os.path.join(a.venv_t, 'bin', 'python'), '-c', T_SHOTS_READER,
                              save_dir, dest, str(SHOTS_KEPT)], cwd=save_dir, env=env,
                             capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'images': [], 'note': repr(e)}
    for line in reversed(out.stdout.splitlines()):
        if line.strip().startswith('{'):
            try:
                return json.loads(line)
            except ValueError:
                break
    return {'images': [], 'note': (out.stderr or out.stdout)[-600:]}


def drop_pickle(rec):
    """_bridge_campaign's --drop-t-history, done here after the screenshots."""
    pkl = (rec.get('history_read') or {}).get('pkl')
    if pkl and os.path.isfile(pkl):
        size = os.path.getsize(pkl)
        os.remove(pkl)
        rec['history_dropped'] = {'pkl': pkl, 'bytes': size}
        rec['note'] = (rec.get('note') or '') + f"RolloutHistory pickle deleted after reading ({size} bytes); "


def o_shots(save_dir, dest, keep):
    """Arm O's final overviews and last eye camera images copied to dest
    when kept; every image of the run deleted from its run directory
    either way."""
    pngs = sorted(glob.glob(os.path.join(save_dir, '**', 'eye_*.png'), recursive=True),
                  key=lambda p: (os.path.dirname(p), os.path.basename(p)))
    overviews = sorted(glob.glob(os.path.join(save_dir, 'overview_*.png')))
    cams = [p for p in pngs if p.endswith('_camera.png')]
    saved = []
    if keep:
        os.makedirs(dest, exist_ok=True)
        for p in overviews + cams[-SHOTS_KEPT:]:
            shutil.copyfile(p, os.path.join(dest, os.path.basename(p)))
            saved.append(os.path.basename(p))
        tail = se._read_text(os.path.join(save_dir, 'stdout.txt')).splitlines()[-40:]
        with open(os.path.join(dest, 'console_tail.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(tail) + '\n')
        eye = sorted(glob.glob(os.path.join(save_dir, '**', 'eye.jsonl'), recursive=True))
        if eye:
            lines = se._read_text(eye[-1]).strip().splitlines()
            if lines:
                with open(os.path.join(dest, 'eye_last.json'), 'w', encoding='utf-8') as f:
                    f.write(lines[-1] + '\n')
    for p in pngs + overviews:
        os.remove(p)
    return {'images': saved, 'taken': len(pngs) + len(overviews)}


def load_rows(path):
    rows = []
    if os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def episode_cwd(a, arm, seed, rep, attempt, scene):
    """A working directory holding the episode's one scene where their
    loader looks, and their env_configs/ (both drivers' --config is
    ./env_configs/find_dice.yml)."""
    d = os.path.join(a.out, 'cwd', f'{arm}_s{seed}_r{rep}_a{attempt}')
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, PROBLEMS_REL))
    shutil.copyfile(os.path.join(a.scenes, scene), os.path.join(d, PROBLEMS_REL, scene))
    os.symlink(os.path.join(a.tampura_work, 'tampura_environments', 'env_configs'),
               os.path.join(d, 'env_configs'))
    return d


def classify_t(rec):
    """(counts, why) of an arm T record (_bridge_campaign's statuses)."""
    if not rec.get('scene_ok'):
        return False, f"scene {rec.get('scene_file')}"
    st = rec.get('status')
    if st in ('success', 'failure'):
        return True, ''
    if st == 'killed':
        return True, 'timeout'
    return False, f"{st}: {rec.get('error') or rec.get('gate_failures')}"


def scene_seen_o(rec):
    if rec.get('scene_file'):
        return rec['scene_file']
    m = SCENE_RE.search(se._read_text(os.path.join(rec['save_dir'], 'stdout.txt')))
    return os.path.basename(m.group(1)) if m else None


def classify_o(rec, scene):
    """(counts, why) of an arm O record (slip_eval's run_episode)."""
    seen = scene_seen_o(rec)
    if seen != scene:
        return False, f"scene {seen}"
    if rec.get('timed_out'):
        return True, 'timeout'
    st = rec.get('bridge_status')
    if st in ('success', 'failure'):
        return True, ''
    return False, f"{st or 'no outcome'}: {rec.get('bridge_error', '')}"


def keep_shots(a, ok, success):
    return a.shots == 'all' or (a.shots == 'failures' and not (ok and success))


def run_one(a, arm, seed, rep, attempt, scene, order):
    cwd = episode_cwd(a, arm, seed, rep, attempt, scene)
    sub = arm                          # T, O or O2: one folder each (O2 = arm O from the second snapshot)
    out = os.path.join(a.out, sub if attempt == 1 else f'{sub}_retry')
    shots_dir = os.path.join(a.out, 'failures', f'{arm}_s{seed}_r{rep}_a{attempt}')
    if arm == 'T':
        ns = SimpleNamespace(out=out, venv_t=a.venv_t, snapshot=a.snapshot, mode='full',
                             cap=a.cap, their_envs=cwd, pythonhashseed='0',
                             tampura_work=a.tampura_work, drop_t_history=False)
        rec = bc.episode_t(ns, rep, seed, order, {seed: scene}, bc.machine_check())
        ok, why = classify_t(rec)
        success = rec.get('status') == 'success'
        keep = keep_shots(a, ok, success)
        if keep:
            try:                          # a screenshot never ends the eval
                rec['shots'] = t_shots(a, rec['save_dir'], shots_dir)
            except Exception as e:
                rec['shots'] = {'images': [], 'note': f"{type(e).__name__}: {e}"}
        drop_pickle(rec)
        wall, loop = rec.get('wall_s'), rec.get('loop_s')
        timed_out = rec.get('status') == 'killed'
    else:
        ns = SimpleNamespace(out=out, python=a.python_o,
                             snapshot=(a.snapshot_o2 if arm == 'O2' else a.snapshot),
                             cwd=cwd, cap=a.cap)
        shots_on = a.shots != 'none'
        rec = se.run_episode(ns, ARM_O, seed, rep,
                             extra_args=('--save-screenshots', 'on') if shots_on else (),
                             extra_env={'BOXEL_EYE_IMAGES': '1'} if shots_on else None)
        ok, why = classify_o(rec, scene)
        m = rec.get('metrics') or {}
        # the bridge's outcome (their reward, the error, the ledger gates) and
        # the pipeline's own goal check must both say success
        success = rec.get('bridge_status') == 'success' and m.get('outcome') == 'success'
        if (rec.get('bridge_status') == 'success') != (m.get('outcome') == 'success'):
            why = (why + '; ' if why else '') + (f"outcomes disagree: bridge {rec.get('bridge_status')}"
                                                 f", pipeline {m.get('outcome')}")
        keep = keep_shots(a, ok, success)
        try:                              # a screenshot never ends the eval
            rec['shots'] = o_shots(rec['save_dir'], shots_dir, keep)
        except Exception as e:
            rec['shots'] = {'images': [], 'note': f"{type(e).__name__}: {e}"}
        wall, loop = rec.get('process_wall_s'), m.get('wall_s')
        timed_out = bool(rec.get('timed_out'))
    shutil.rmtree(cwd)
    row = {'arm': arm, 'seed': seed, 'rep': rep, 'attempt': attempt, 'scene': scene,
           'n_cups': a.cups.get(str(seed)), 'counts': ok, 'why': why,
           'success': bool(ok and success and not timed_out), 'timed_out': timed_out,
           'wall_s': wall, 'loop_s': loop, 'host': os.uname().nodename,
           'finished': time.strftime('%Y-%m-%d %H:%M:%S'), 'rec': rec}
    if keep:
        os.makedirs(shots_dir, exist_ok=True)
        meta = {k: v for k, v in row.items() if k != 'rec'}
        for k in ('status', 'returncode', 'max_reward', 'n_actions', 'get_action_actions',
                  'bridge_status', 'reward', 'carries', 'losses', 'pick_tries', 'scene_file',
                  'save_dir', 'note', 'error', 'bridge_error', 'shots'):
            if k in rec:
                meta[k] = rec[k]
        if rec.get('metrics'):
            meta['outcome_pipeline'] = rec['metrics'].get('outcome')
            meta['metrics'] = rec['metrics']
        bc.write_json(os.path.join(shots_dir, 'meta.json'), meta)
    return row


def run(a):
    manifest = bc.read_json(os.path.join(a.scenes, 'manifest.json'))
    if not manifest:
        raise SystemExit(f"no manifest in {a.scenes}")
    if (os.path.realpath(os.environ.get('BRIDGE_SCENE_MANIFEST') or '')
            != os.path.realpath(os.path.join(a.scenes, 'manifest.json'))):
        raise SystemExit("BRIDGE_SCENE_MANIFEST must name the scenes' manifest (G19 of arm O)")
    a.cups = {s: d.get('n_cups') for s, d in manifest['details'].items()}
    seeds = se.parse_seeds(a.seeds)
    missing = [s for s in seeds if str(s) not in manifest['scenes']]
    if missing:
        raise SystemExit(f"no scene for seeds {missing}")
    arms = parse_arms(getattr(a, 'arms', ','.join(ARMS_DEFAULT)), getattr(a, 'snapshot_o2', None))
    if 'O2' in arms:
        check_same_scenes(a.snapshot, a.snapshot_o2, seeds, manifest)
    alive = se.pipeline_alive(os.getpid())
    if alive:
        raise SystemExit("a pipeline process is alive: " + '; '.join(alive))
    os.makedirs(a.out, exist_ok=True)
    if arms != ('O2',):                 # as before: the main snapshot's arm O imports, even for T alone
        se.check_arms(SimpleNamespace(python=a.python_o, snapshot=a.snapshot), [ARM_O])
    if 'O2' in arms:
        se.check_arms(SimpleNamespace(python=a.python_o, snapshot=a.snapshot_o2), [ARM_O])
    md_path = os.path.join(a.out, 'metadata.json')
    if not os.path.isfile(md_path):
        bc.write_json(md_path, {'snapshot': a.snapshot, 'scenes': a.scenes, 'seeds': seeds,
                                'reps': a.reps, 'cap_s': a.cap, 'arm_o': ARM_O, 'shots': a.shots,
                                'arms': list(arms), 'snapshot_o2': getattr(a, 'snapshot_o2', None),
                                'python_o': a.python_o, 'venv_t': a.venv_t,
                                'tampura_work': a.tampura_work, 'host': os.uname().nodename,
                                'cpu': bc.cpu_model(), 'job': os.environ.get('SLURM_JOB_ID'),
                                'started': time.strftime('%Y-%m-%d %H:%M:%S')})
    path = os.path.join(a.out, 'results.jsonl')
    rows = load_rows(path)
    order = len(rows)
    for rep in range(a.reps):
        for seed in seeds:
            scene = manifest['scenes'][str(seed)]
            for arm in arms:
                tries = [r for r in rows if (r['arm'], r['seed'], r['rep']) == (arm, seed, rep)]
                if any(r['counts'] for r in tries) or len(tries) >= 2:
                    continue
                for attempt in range(len(tries) + 1, 3):
                    print(f"[gen] rep {rep} seed {seed} ({scene}) arm {arm} attempt {attempt} ...",
                          end=' ', flush=True)
                    row = run_one(a, arm, seed, rep, attempt, scene, order)
                    order += 1
                    bc.append_jsonl(path, row)
                    rows.append(row)
                    print(f"{'success' if row['success'] else 'no success'}"
                          f"{' (timeout)' if row['timed_out'] else ''}, wall {row['wall_s']} s"
                          f"{'' if row['counts'] else ', DOES NOT COUNT: ' + row['why']}", flush=True)
                    if row['counts']:
                        break
    print(report([a.out]))
    return 0


# ----- the tables -------------------------------------------------------

def wilson(k, n, z=1.96):
    if not n:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mcnemar_exact(b, c):
    """Two-sided exact McNemar (binomial on the discordant pairs)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def _f(v, d=1):
    return '-' if v is None else f"{v:.{d}f}"


def final_rows(dirs):
    rows = []
    for d in dirs:
        for p in sorted(set(glob.glob(os.path.join(d, 'results.jsonl'))
                            + glob.glob(os.path.join(d, '*', 'results.jsonl')))):
            rows += load_rows(p)
    final = {}
    for r in rows:
        key = (r['arm'], r['seed'], r['rep'])
        if key not in final or r['attempt'] >= final[key]['attempt']:
            final[key] = r
    return rows, final


def pair_stats(final, keys, x, y):
    """(pairs, both, x only, y only, neither): the (scene, repetition) pairs
    both arms counted on, and who succeeded on them."""
    pairs = [(s, rep) for (s, rep) in keys
             if final.get((x, s, rep), {}).get('counts') and final.get((y, s, rep), {}).get('counts')]
    both = sum(final[(x, s, r)]['success'] and final[(y, s, r)]['success'] for s, r in pairs)
    x_only = sum(final[(x, s, r)]['success'] and not final[(y, s, r)]['success'] for s, r in pairs)
    y_only = sum(final[(y, s, r)]['success'] and not final[(x, s, r)]['success'] for s, r in pairs)
    return pairs, both, x_only, y_only, len(pairs) - both - x_only - y_only


def report(dirs):
    rows, final = final_rows(dirs)
    if not final:
        return 'no episodes'
    has_o2 = any(arm == 'O2' for (arm, _, _) in final)      # path 6's arm A' (TB-1), see the docstring
    keys = sorted({(s, rep) for (_, s, rep) in final})
    lines = [f"{len(rows)} episode runs, {len(final)} final (arm, scene, repetition); "
             f"scenes {len({s for s, _ in keys})}, repetitions {len({r for _, r in keys})}", '']
    retried = [r for r in rows if r['attempt'] == 1 and not r['counts']]
    lines.append(f"first runs that did not count (each ran once more): {len(retried)}"
                 + ''.join(f"\n  {r['arm']} seed {r['seed']} rep {r['rep']}: {r['why'][:160]}"
                           for r in retried))
    lines.append('')
    lines.append(f"{'arm':4} {'counted':>8} {'success':>8} {'rate':>6} {'95 % Wilson':>14} "
                 f"{'timeouts':>8} {'not counted':>11} {'median wall s':>13} {'(successes)':>11}")
    cols = ['O'] + (['O2'] if has_o2 else []) + ['T']
    for arm in cols:
        rs = [r for (x, _, _), r in final.items() if x == arm]
        cnt = [r for r in rs if r['counts']]
        k = sum(r['success'] for r in cnt)
        lo, hi = wilson(k, len(cnt))
        lines.append(f"{arm:4} {len(cnt):8} {k:8} {(k / len(cnt) if cnt else float('nan')):6.2f} "
                     f"[{lo:.2f}, {hi:.2f}]  {sum(r['timed_out'] for r in cnt):8} "
                     f"{len(rs) - len(cnt):11} {_f(_med(r['wall_s'] for r in cnt)):>13} "
                     f"{_f(_med(r['wall_s'] for r in cnt if r['success'])):>11}")
    lines.append('')
    for x, y in [('O', 'T')] + ([('O2', 'O'), ('O2', 'T')] if has_o2 else []):
        pairs, both, x_only, y_only, neither = pair_stats(final, keys, x, y)
        lines.append((f"paired (both arms counted on the same scene and repetition)" if (x, y) == ('O', 'T')
                      else f"paired {x} against {y} (both counted on the same scene and repetition)")
                     + f": {len(pairs)} pairs; "
                     f"both succeed {both}, only {x} {x_only}, only {y} {y_only}, neither {neither}; "
                     f"exact McNemar p = {mcnemar_exact(x_only, y_only):.3g}")
        dropped = [(s, rep) for (s, rep) in keys if (s, rep) not in pairs]
        if dropped:
            lines.append(f"left out of the pairs{'' if (x, y) == ('O', 'T') else f' of {x} and {y}'} "
                         "(an arm did not count twice): "
                         + ', '.join(f"seed {s} rep {r}" for s, r in dropped))
    lines.append('')
    lines.append('per scene (successes / counted runs; cups from the manifest):')
    lines.append(f"{'seed':>6} {'cups':>5} " + ' '.join(f"{c:>6}" for c in cols)
                 + "   T's last actions when it failed")
    for s in sorted({s for s, _ in keys}):
        cells = {}
        for arm in cols:
            rs = [r for (x, ss, _), r in final.items() if x == arm and ss == s and r['counts']]
            cells[arm] = f"{sum(r['success'] for r in rs)}/{len(rs)}"
        cups = next((r.get('n_cups') for (x, ss, _), r in final.items() if ss == s), None)
        tails = []
        for (x, ss, _), r in sorted(final.items()):
            if x == 'T' and ss == s and r['counts'] and not r['success']:
                acts = (r['rec'].get('get_action_actions') or [])[-3:]
                tails.append('|'.join(acts) or r['why'])
        lines.append(f"{s:>6} {_f(cups, 0) if cups is not None else '-':>5} "
                     + ' '.join(f"{cells[c]:>6}" for c in cols) + "   "
                     + '; '.join(t[:90] for t in tails))
    lines.append('')
    for oa in ['O'] + (['O2'] if has_o2 else []):
        o_c = sum((r['rec'].get('carries') or 0) for (x, _, _), r in final.items() if x == oa and r['counts'])
        o_l = sum((r['rec'].get('losses') or 0) for (x, _, _), r in final.items() if x == oa and r['counts'])
        lines.append(f"arm {oa} die carries {o_c}, lost in the hand {o_l}")
    t_s = [r['rec'].get('time_to_success_s') for (x, _, _), r in final.items() if x == 'T' and r['success']]
    lines.append(f"arm T median time to success {_f(_med(t_s))} s (their loop clock)")
    shot_rows = [r for r in rows if (r['rec'].get('shots') or {}).get('images') is not None
                 and not (r['counts'] and r['success'])]
    lines.append(f"failure screenshots: {len(shot_rows)} runs, "
                 f"{sum(len(r['rec']['shots']['images']) for r in shot_rows)} images under failures/ "
                 f"(no image: " + (', '.join(f"{r['arm']} s{r['seed']} r{r['rep']}" for r in shot_rows
                                             if not r['rec']['shots']['images']) or 'none') + ')')
    return '\n'.join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--report', nargs='+', help='print the tables of these result directories')
    ap.add_argument('--snapshot')
    ap.add_argument('--out')
    ap.add_argument('--seeds')
    ap.add_argument('--reps', type=int, default=2)
    ap.add_argument('--cap', type=float, default=600.0, help='wall cap per episode, s')
    ap.add_argument('--python-o', help="arm O's python (its venv)")
    ap.add_argument('--venv-t', help="arm T's venv (theirs)")
    ap.add_argument('--tampura-work', help='their tree: tampura, tampura_environments')
    ap.add_argument('--shots', choices=('failures', 'all', 'none'), default='failures',
                    help="which runs keep their last camera views (see SCREENSHOTS)")
    ap.add_argument('--arms', default=','.join(ARMS_DEFAULT),
                    help="the arms, e.g. T,O (default), T,O,O2 or O2 (see ARM O2)")
    ap.add_argument('--snapshot-o2', default=None,
                    help="arm O2's snapshot: arm O's plus TB-1 only (needed for O2)")
    a = ap.parse_args(argv)
    if a.report:
        print(report(a.report))
        return 0
    for name in ('snapshot', 'out', 'seeds', 'python_o', 'venv_t', 'tampura_work'):
        if not getattr(a, name):
            ap.error(f"--{name.replace('_', '-')} is required to run episodes")
    parse_arms(a.arms, a.snapshot_o2)        # fail before anything starts
    a.snapshot = os.path.abspath(a.snapshot)
    if a.snapshot_o2:
        a.snapshot_o2 = os.path.abspath(a.snapshot_o2)
    a.out = os.path.abspath(a.out)
    a.tampura_work = os.path.abspath(a.tampura_work)
    a.venv_t = os.path.abspath(a.venv_t)
    a.scenes = os.path.join(a.snapshot, SCENES_REL)
    return run(a)


if __name__ == '__main__':
    sys.exit(main())
