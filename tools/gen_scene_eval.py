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
episode_t (their planner as shipped), arm O is tools/slip_eval.py's
run_episode with BF#62's four switches named, both under the same wall cap
(900 s in tools/cluster/gen_eval.sbatch, B8's D10 value).

SUCCESS (path 6, DV-1, Hani 2026-11-07: "no, mkae our test the standard
test."): the standard test is ours on both arms.  Arm O: the bridge's outcome
'success' and the pipeline's own goal check, as BF#63 (the die between both
pads at 0.5 N, the arm at home).  Arm T: the physical facts of its final
world, read after their rollout by the reviewed wrapper in
tampura_bridge/timed_policy.py (tampura_bridge/final_world.py: the target
body attached, both finger pads within 5 mm of it, the arm at home); their
own reward stays in the record and in the row's 't_reward_success'.  An arm-T
episode whose final world could not be read does not count (it runs once
more, as any episode that does not count) and counts like a gate failure in
the harness stop rule (P4.6, R2 of the G13 review): three episodes of one arm
under the same gate (G13, G19, or FINAL_WORLD for an unread world) stop the
job, which writes the stop to metadata.json, prints STOPPED and exits 2; the
report lists the unread worlds apart with their errors, prints the largest pad
gap of arm T's attached episodes and the episodes the pad bound alone fails
(R1), and opens with the caveat that T's test is geometric and ours physical
(R5).  The report prints, for every counted arm T episode, the standard test and
their own reward side by side and counts both (the coordinator's order of 15 Nov,
from R's recount: the two criteria can differ on a real run); which of the two is
the headline sits in one place, T_HEADLINE (--report --t-headline standard|reward;
default standard until Hani's 13:51 "no" is confirmed).

ACTION CAP (DV-2, Hani 2026-11-07: "add the cap to us as well and make sure it
is documented."): arm O is held to T's 20-step horizon on a proxy, the
episode's picks + places + senses + observes plus 1 go-home on a success
(t_equiv; their actions include the motion, so ours are absorbed).  The
episodes run uncapped and the cap is a cut-off on each episode's own count:
'success' is the uncapped result, 'capped_success' is success with
t_equiv <= 20 (arm T keeps its own 20 steps: capped = uncapped).  The report
prints the capped view as the headline and the uncapped view beside it from
the same episodes, which is also the evaluation of our approach with against
without the limit.  Rows without the cap fields (BF#63 run 2) are an uncapped
block and print as before.

MEMORY (rule 16, PLAN section 17, tools/memwatch.py): every episode runs in a
process of its own (the arms' runners start one child per episode) and the harness
measures around it: MemAvailable at its start, at every 2 s poll and at its end,
the biggest resident set of one process of the episode (exact when the children's
high-water mark rose, else the largest seen at a poll) and the highest sum over
its processes, new /dev/shm names and pipeline processes left behind (reported,
never ended).  The row carries them as `mem` (kB) and the flag `peak_over_6gb`;
the log prints them after the row.  MemAvailable under 4 GB at any reading of an
episode stops the job after that episode's row (nothing starts under it): the
STOPPED_LOW_MEMORY line, OUT/STOPPED_LOW_MEMORY.txt, metadata.json's stop, exit
code 4.  --min-avail-gb and --peak-report-gb change the limits (0 only records).
The report prints the memory lines and, from each job folder, the job script's
own memory_lines.txt.

DROPS AND COLLISIONS (rule 18 of tracks/STATE.md; TB-22): since TB-22 every
row carries drops, collisions, drop_detector, collision_detector and
clean_success (world_counts.of_record in run_one; arm T's carry is kinematic,
so its drops "cannot happen" and its collisions are "not detected").  The
report prints them after the tables: the episodes with a drop or a collision
per arm, the records' own words on how each count was taken, and clean success
beside success for each view.  A count nothing could take is printed as words,
never as 0, and a success without a count is "unknown", never clean.  Recorded
only: no count, pair or test above changes.  Rows from before TB-22 print one
line saying so.

ARM O2 (path 6, PLAN.md P6-Q9): arm O's episode again, from a second snapshot
(--snapshot-o2: arm O's snapshot plus one fix, TB-1, and nothing else; the
runner prints the two snapshots' scene files and manifest equal or stops), run
on the same scenes with the same switches, same venv, same cap.  --arms picks
the arms (T,O by default; T,O,O2 runs the three back to back per scene; O2
alone runs the fix later on scenes already pinned).  The report then adds the
pairs O2 against O and O2 against T; with the default arms it is BF#63's.

VALIDITY (Hani, 14 and 15 Nov 2026; replaces the retry rule declared for BF#63): ONE attempt per
(arm, scene, repetition), and its row is the result, whatever happened.  A run that crashed (their
exception, our crash, no outcome), hung to the cap, or ended with an outcome whose final world could
not be read is a FAILURE of that arm and counts (counts True, success False, the cause in 'why').
Only a harness fault that belongs to neither arm does not count: the episode loaded another scene or
a gate (G13, G19) failed; it is listed, never run again, and the report says it is not full.  No
episode is run a second time: a cell with a row is skipped on a resume, a cell without one runs as its
first attempt.  A later attempt that exists anyway (an old results folder, a manual run) is a rerun:
listed, never counted, never replaces the first attempt.  final_rows lists every duplicate row of a
cell instead of collapsing it silently.

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
import memwatch as mw  # noqa: E402
import slip_eval as se  # noqa: E402

# Arm O: BF#62's default set, named so the record says what ran.
ARM_O = 'solver_iters+force_hold+pose_radius_keep+grasp_wrist_home'
SCENES_REL = os.path.join('tampura_bridge', 'gen_scenes', 'find_dice')
PROBLEMS_REL = os.path.join('tampura_environments', 'find_dice', 'problems')
SCENE_RE = re.compile(r'Loading scene from (\S+)')
SHOTS_KEPT = 2
ARMS_ALL = ('T', 'O', 'O2')          # the order they run and print in
ARMS_DEFAULT = ('T', 'O')
CAP_ACTIONS = 20                     # T's horizon (its config's 20 steps); DV-2 holds arm O to it too
STOP_RULE_COUNT = bc.STOP_RULE_COUNT  # P4.6 HARNESS STOP RULE: three episodes of one arm under the same gate
UNREAD_WHY = 'final world unreadable'  # classify_t's reason; the stop rule and the report read it
FINAL_WORLD_GATE = 'FINAL_WORLD'     # an arm T outcome without a readable final world counts like a gate failure
OUR_SCENE_GATES = ('G19', 'G19h')     # arm O gates that say the scene is not the declared one: only these do not count


def t_equiv(metrics, success):
    """DV-2's proxy of T's steps for one arm-O episode: picks + places + senses
    + observes from the run's own metrics (tools/episode_metrics.py), plus 1
    go-home on a success.  None when the run has no such counts."""
    if not metrics:
        return None
    parts = [metrics.get(k) for k in ('picks', 'places', 'senses', 'observes')]
    if any(p is None for p in parts):
        return None
    return int(sum(parts)) + (1 if success else 0)


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
    """(counts, why) of an arm T record (_bridge_campaign's statuses).  counts is False only for a harness
    fault of neither arm (another scene, a failed gate).  A crash of their code, a kill at the cap and an
    outcome whose final world could not be read (DV-1: the standard test needs the read) all count, as
    failures of arm T, with the cause in why (the row's success is then False)."""
    st = rec.get('status')
    # only a scene that was seen and is another one is a harness fault: a run that hung or died before
    # the scene line has no scene to compare and is a failure of the arm (R, 15 Nov: TB-15's kind)
    if rec.get('scene_file') and not rec.get('scene_ok'):
        return False, f"scene {rec.get('scene_file')}"
    if st == 'killed':
        return True, 'timeout'
    if st in ('success', 'failure'):
        if not rec.get('scene_ok'):
            return False, f"scene {rec.get('scene_file')}"
        if 'standard_read' not in rec:       # a record from before DV-1: no final world was ever read,
            return True, ''                  # success is their reward (see score_rec)
        if not rec.get('standard_read'):
            err = (rec.get('final_world') or {}).get('error') or 'no final_world.json'
            return True, f"{UNREAD_WHY}: {err}"
        return True, ''
    if st == 'crashed':
        err = (rec.get('history_read') or {}).get('read_error')
        if err:        # their pickle exists and OUR reader failed: we do not know their result (R 6b)
            return False, f"our read failed: their pickle exists and our reader could not read it: {str(err)[:200]}"
        return True, f"crashed: {rec.get('error')}"           # no pickle: their crash
    return False, f"{st}: {rec.get('error') or rec.get('gate_failures')}"


def scene_seen_o(rec):
    if rec.get('scene_file'):
        return rec['scene_file']
    m = SCENE_RE.search(se._read_text(os.path.join(rec.get('save_dir') or os.devnull, 'stdout.txt')))
    return os.path.basename(m.group(1)) if m else None


def classify_o(rec, scene):
    """(counts, why) of an arm O record (slip_eval's run_episode).  As classify_t: a crash of ours, no
    outcome and a kill at the cap count as failures of arm O (every crash of ours needs a BUGS.md entry);
    only another scene or a failed gate is a harness fault that does not count."""
    seen = scene_seen_o(rec)
    if seen and seen != scene:                    # a scene that was seen and is another one
        return False, f"scene {seen}"
    if rec.get('timed_out'):                      # a hang, also one before the scene line (TB-15)
        return True, 'timeout'
    st = rec.get('bridge_status')
    err = rec.get('bridge_outcome_error') or rec.get('bridge_error', '')
    if st in ('success', 'failure'):
        if not seen:
            return False, 'scene None'
        return True, ''
    if st == 'gate_failed':
        gates = sorted(rec.get('gate_failures') or {})
        if gates and all(g in OUR_SCENE_GATES for g in gates):
            # the scene is not the declared one: our fault, flagged for a BUGS.md entry, does not count
            return False, f"gate_failed {','.join(gates)}: {err}"
        # any other failed gate means our pipeline broke one of its own rules: a failure of arm O
        return True, f"gate_failed {','.join(gates) or '(gate not recorded)'}: {err}"
    return True, f"{st or 'no outcome'}: {err}"      # our crash, or no outcome at all


def score_rec(arm, rec, scene):
    """Everything a row says about the result, from the record alone (so run_one and the report's
    re-classification of a stored row use one rule): (counts, why, success, timed_out, t_reward, t_equiv_,
    capped).  A T record from before DV-1 (no 'standard_read' key) scores by their own reward, the only
    test it ever had."""
    if arm == 'T':
        ok, why = classify_t(rec)
        pre_dv1 = 'standard_read' not in rec
        success = (rec.get('status') == 'success') if pre_dv1 else bool(rec.get('standard_success'))
        timed_out = rec.get('status') == 'killed'
        t_reward, te = rec.get('status') == 'success', None
    else:
        ok, why = classify_o(rec, scene)
        m = rec.get('metrics') or {}
        # the bridge's outcome (their reward, the error, the ledger gates) and
        # the pipeline's own goal check must both say success
        success = rec.get('bridge_status') == 'success' and m.get('outcome') == 'success'
        if (rec.get('bridge_status') == 'success') != (m.get('outcome') == 'success'):
            why = (why + '; ' if why else '') + (f"outcomes disagree: bridge {rec.get('bridge_status')}"
                                                 f", pipeline {m.get('outcome')}")
        timed_out = bool(rec.get('timed_out'))
        t_reward, te = None, t_equiv(rec.get('metrics'), success)
    row_success = bool(ok and success and not timed_out and not str(why).startswith(UNREAD_WHY))
    # DV-2: T keeps its own 20 steps, so its capped view is its result
    capped = row_success if arm == 'T' else bool(row_success and te is not None and te <= CAP_ACTIONS)
    return ok, why, row_success, timed_out, t_reward, te, capped


def scorable(row):
    """Does the row's stored rec hold what the rule reads (arm T: its status; arm O: the bridge's status or
    the kill flag)?  Every real episode's record does; a cut row and a hand-made row may not."""
    rec = row.get('rec')
    if not isinstance(rec, dict) or not rec or rec.get('cut'):
        return False
    return 'status' in rec if row.get('arm') == 'T' else ('bridge_status' in rec or 'timed_out' in rec)


def reclassify_row(row):
    """The row's class by today's rule, from its stored rec: a copy with counts, why, success, capped_success,
    timed_out (and t_reward_success) recomputed, never trusting the stored values.  A row whose rec lacks
    the inputs (scorable) is returned as it is."""
    if not scorable(row):
        return row
    ok, why, success, timed_out, t_reward, te, capped = score_rec(row['arm'], row['rec'], row.get('scene'))
    new = dict(row, counts=ok, why=why, success=success, timed_out=timed_out)
    if 'capped_success' in row:
        new['capped_success'] = capped
    if row['arm'] == 'T' and row.get('t_reward_success') is not None:
        new['t_reward_success'] = t_reward
    return new


def failure_kind(row):
    """The kind of a counted failure that has a cause of its own: 'timeout' (a hang to the cap, also before
    the scene line), 'cut' (started, no row), 'unread world' (our read failed), 'gate' (a failed gate of our
    arm), 'crashed'; else None."""
    why = str(row.get('why') or '')
    if not row.get('counts'):
        return None
    if why == 'timeout' or row.get('timed_out'):
        return 'timeout'
    if why.startswith('cut:'):
        return 'cut'
    if why.startswith(UNREAD_WHY):
        return 'unread world'
    if why.startswith('gate_failed'):
        return 'gate'
    if why.startswith(('crashed', 'no outcome')):
        return 'crashed'
    return None


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
        # DV-1: the standard test; their own reward is kept as t_reward_success
        ok, why, row_success, timed_out, t_reward, te, capped = score_rec('T', rec, scene)
        keep = keep_shots(a, ok, row_success)
        if keep:
            try:                          # a screenshot never ends the eval
                rec['shots'] = t_shots(a, rec['save_dir'], shots_dir)
            except Exception as e:
                rec['shots'] = {'images': [], 'note': f"{type(e).__name__}: {e}"}
        drop_pickle(rec)
        wall, loop = rec.get('wall_s'), rec.get('loop_s')
    else:
        ns = SimpleNamespace(out=out, python=a.python_o,
                             snapshot=(a.snapshot_o2 if arm == 'O2' else a.snapshot),
                             cwd=cwd, cap=a.cap)
        shots_on = a.shots != 'none'
        rec = se.run_episode(ns, ARM_O, seed, rep,
                             extra_args=('--save-screenshots', 'on') if shots_on else (),
                             extra_env={'BOXEL_EYE_IMAGES': '1'} if shots_on else None)
        # the bridge's outcome and the pipeline's own goal check must both say success (score_rec)
        ok, why, row_success, timed_out, t_reward, te, capped = score_rec(arm, rec, scene)
        keep = keep_shots(a, ok, row_success)
        try:                              # a screenshot never ends the eval
            rec['shots'] = o_shots(rec['save_dir'], shots_dir, keep)
        except Exception as e:
            rec['shots'] = {'images': [], 'note': f"{type(e).__name__}: {e}"}
        wall, loop = rec.get('process_wall_s'), (rec.get('metrics') or {}).get('wall_s')
    shutil.rmtree(cwd)
    row = {'arm': arm, 'seed': seed, 'rep': rep, 'attempt': attempt, 'scene': scene,
           'n_cups': a.cups.get(str(seed)), 'counts': ok, 'why': why,
           'success': row_success, 'capped_success': capped, 't_equiv': te,
           't_reward_success': t_reward, 'timed_out': timed_out,
           'wall_s': wall, 'loop_s': loop, 'host': os.uname().nodename,
           'finished': time.strftime('%Y-%m-%d %H:%M:%S'), 'rec': rec}
    if keep:
        os.makedirs(shots_dir, exist_ok=True)
        meta = {k: v for k, v in row.items() if k != 'rec'}
        for k in ('status', 'returncode', 'max_reward', 'n_actions', 'get_action_actions',
                  'bridge_status', 'reward', 'carries', 'losses', 'pick_tries', 'scene_file',
                  'save_dir', 'note', 'error', 'bridge_error', 'shots',
                  'standard_read', 'standard_success', 'final_world'):
            if k in rec:
                meta[k] = rec[k]
        if rec.get('metrics'):
            meta['outcome_pipeline'] = rec['metrics'].get('outcome')
            meta['metrics'] = rec['metrics']
        bc.write_json(os.path.join(shots_dir, 'meta.json'), meta)
    return row


def marker_path(out, arm, seed, rep):
    """The start marker of an episode: written before it starts, removed when its row is written."""
    return os.path.join(out, 'started', f'{arm}_s{seed}_r{rep}.json')


def cut_row(a, arm, seed, rep, scene, marker):
    """The row of an episode that started (its marker is still there) and left no row: a failure of that
    arm, counted, with the cause named; it never runs again."""
    started = (marker or {}).get('started') or 'at an unknown time'
    return {'arm': arm, 'seed': seed, 'rep': rep, 'attempt': 1, 'scene': scene,
            'n_cups': a.cups.get(str(seed)), 'counts': True,
            'why': f"cut: the episode started {started} and left no row (the job or the runner was cut); "
                   "a failure of this arm, never run again",
            'success': False, 'capped_success': False, 't_equiv': None,
            't_reward_success': False if arm == 'T' else None, 'timed_out': False,
            'wall_s': None, 'loop_s': None, 'host': (marker or {}).get('host') or '?',
            'finished': time.strftime('%Y-%m-%d %H:%M:%S'), 'rec': {'cut': True, 'marker': marker}}


class HarnessStop(Exception):
    """The harness stop rule tripped; args[0] is the stop record."""


def gate_names(row):
    """What a row counts under in the harness stop rule (P4.6): the per-run gates its
    record names (G13, G19) and, for arm T, FINAL_WORLD when an outcome's final world
    could not be read (R2 of the G13 review: an unread world counts like a gate failure)."""
    names = list(((row.get('rec') or {}).get('gate_failures')) or {})
    if row.get('arm') == 'T' and str(row.get('why') or '').startswith(UNREAD_WHY):
        names.append(FINAL_WORLD_GATE)
    return names


def stop_counts(rows):
    """{(arm, gate): episodes} over every run in the rows (retries included)."""
    counts = {}
    for r in rows:
        for g in gate_names(r):
            counts[(r['arm'], g)] = counts.get((r['arm'], g), 0) + 1
    return counts


def stop_reached(counts):
    """The stop record for the first (arm, gate) at STOP_RULE_COUNT, else None."""
    for (arm, g), n in sorted(counts.items()):
        if n >= STOP_RULE_COUNT:
            return {'rule': 'HARNESS_STOP', 'arm': arm, 'gate': g, 'count': n}
    return None


def finish_metadata(md_path, stop, counts):
    md = bc.read_json(md_path) or {}
    md['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
    md['status'] = 'stopped' if stop else 'finished'
    md['stop'] = stop
    md['stop_counts'] = {f'{arm}:{g}': n for (arm, g), n in sorted(counts.items())}
    bc.write_json(md_path, md)


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
    counts = stop_counts(rows)
    stop = stop_reached(counts)
    if stop:
        print('[gen] STOPPED before any episode, the stop rule is met by the rows of an earlier run: '
              + json.dumps(stop))
        return 2
    # rule 16 (tools/memwatch.py): MemAvailable and peak RSS around every episode, in its row and in the log;
    # MemAvailable under the limit stops the job after that episode's row (nothing starts under it)
    min_kb = mw.limit_kb(mw.MIN_AVAIL_GB if getattr(a, 'min_avail_gb', None) is None else a.min_avail_gb)
    peak_kb = mw.limit_kb(mw.PEAK_REPORT_GB if getattr(a, 'peak_report_gb', None) is None else a.peak_report_gb)
    low = None
    try:
        for rep in range(a.reps):
            for seed in seeds:
                scene = manifest['scenes'][str(seed)]
                for arm in arms:
                    # ONE attempt per cell, its row is the result (Hani, 14 Nov): a cell with any row is
                    # skipped, never run a second time; a cell without a row runs as its first attempt
                    if any((r['arm'], r['seed'], r['rep']) == (arm, seed, rep) for r in rows):
                        continue
                    marker = marker_path(a.out, arm, seed, rep)
                    if os.path.isfile(marker):
                        # started and never wrote a row (the job or the runner was cut): a failed first attempt
                        # of that arm, cause named; it is not run again as a first attempt
                        row = cut_row(a, arm, seed, rep, scene, bc.read_json(marker))
                        bc.append_jsonl(path, row)
                        rows.append(row)
                        order += 1
                        os.remove(marker)
                        print(f"[gen] rep {rep} seed {seed} ({scene}) arm {arm}: FAILURE (cut): {row['why']}",
                              flush=True)
                        continue
                    attempt = 1
                    label = f"{arm} seed {seed} rep {rep} attempt {attempt}"
                    avail = mw.mem_available_kb()
                    if mw.low_memory(avail, min_kb):
                        raise mw.LowMemory('start', avail, min_kb, label)
                    print(f"[gen] rep {rep} seed {seed} ({scene}) arm {arm} attempt {attempt} "
                          f"(MemAvailable {mw.fmt_gb(avail)}) ...", end=' ', flush=True)
                    os.makedirs(os.path.dirname(marker), exist_ok=True)       # the start marker, before the episode
                    bc.write_json(marker, {'arm': arm, 'seed': seed, 'rep': rep, 'scene': scene,
                                           'started': time.strftime('%Y-%m-%d %H:%M:%S'),
                                           'host': os.uname().nodename, 'job': os.environ.get('SLURM_JOB_ID')})
                    with mw.EpisodeWatch(min_kb, peak_kb) as w:
                        row = run_one(a, arm, seed, rep, attempt, scene, order)
                    row.update(mw.row_fields(w.as_row()))
                    order += 1
                    bc.append_jsonl(path, row)
                    rows.append(row)
                    try:                                  # the row is written: the marker has done its job
                        os.remove(marker)
                    except OSError:
                        pass
                    kind = failure_kind(row)
                    print(f"{'success' if row['success'] else 'no success'}"
                          f"{' (timeout)' if row['timed_out'] else ''}, wall {row['wall_s']} s"
                          f"{'' if row['counts'] else ', HARNESS FAULT, DOES NOT COUNT: ' + row['why']}"
                          f"{', FAILURE (' + kind + '): ' + str(row['why'])[:200] if kind and kind != 'timeout' else ''}",
                          flush=True)
                    for line in w.end_lines(label):
                        print('[gen] ' + line, flush=True)
                    for g in gate_names(row):
                        counts[(arm, g)] = counts.get((arm, g), 0) + 1
                    stop = stop_reached(counts)
                    if stop:
                        raise HarnessStop(stop)
                    if w.low():
                        raise mw.LowMemory('end', w.avail_min_kb, min_kb, label)
    except HarnessStop as e:
        stop = e.args[0]
    except mw.LowMemory as e:
        low = e
        stop = {'rule': 'STOPPED_LOW_MEMORY', 'where': e.where, 'label': e.label,
                'avail_kb': e.avail_kb, 'limit_kb': e.min_kb}
        mw.write_stop(a.out, e)
    finish_metadata(md_path, stop, counts)
    if stop and not low:
        print('[gen] STOPPED: ' + json.dumps(stop))
    print(report([a.out]))
    return mw.EXIT_LOW_MEMORY if low else (2 if stop else 0)


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


def planned_cells(dirs):
    """The set of (arm, seed, rep) the jobs planned, from each folder's metadata.json (its arms, seeds and
    repetitions), or None when no metadata.json was found: 'full' is only said against this set."""
    planned, found = set(), False
    for d in dirs:
        for p in sorted(set(glob.glob(os.path.join(d, 'metadata.json'))
                            + glob.glob(os.path.join(d, '*', 'metadata.json')))):
            md = bc.read_json(p) or {}
            if not md.get('seeds') or md.get('reps') is None:
                continue
            found = True
            for arm in md.get('arms') or list(ARMS_DEFAULT):
                for seed in md['seeds']:
                    for rep in range(int(md['reps'])):
                        planned.add((arm, int(seed), rep))
    return planned if found else None


def load_all(dirs):
    """Everything the report reads: rows (every stored row classified again from its stored rec by today's
    rule, so old and new folders get one rule), final (the FIRST attempt of each (arm, scene, repetition):
    the lowest attempt number, and of equal attempts the row read first), reruns (every other row of a cell
    as (row, source file, kind): 'later attempt' or 'duplicate'; never counted, nothing collapsed
    silently), changed (the rows whose class, counts or success, differs from their stored fields:
    (stored counts, stored success, row)) and planned (planned_cells)."""
    rows, per_key, changed, unscored = [], {}, [], 0
    for d in dirs:
        for p in sorted(set(glob.glob(os.path.join(d, 'results.jsonl'))
                            + glob.glob(os.path.join(d, '*', 'results.jsonl')))):
            for stored in load_rows(p):
                r = reclassify_row(stored)
                unscored += 0 if scorable(stored) or (stored.get('rec') or {}).get('cut') else 1
                if (bool(r['counts']), bool(r['success'])) != (bool(stored['counts']), bool(stored['success'])):
                    changed.append((stored['counts'], stored['success'], r))
                rows.append(r)
                per_key.setdefault((r['arm'], r['seed'], r['rep']), []).append((r, p))
    final, reruns = {}, []
    for key, items in per_key.items():
        first = min(range(len(items)), key=lambda i: (items[i][0]['attempt'], i))
        final[key] = items[first][0]
        for i, (r, p) in enumerate(items):
            if i != first:
                reruns.append((r, p, 'later attempt' if r['attempt'] > items[first][0]['attempt'] else 'duplicate'))
    return {'rows': rows, 'final': final, 'reruns': reruns, 'changed': changed, 'unscored': unscored,
            'planned': planned_cells(dirs)}


def final_rows_listed(dirs):
    a = load_all(dirs)
    return a['rows'], a['final'], a['reruns']


def final_rows(dirs):
    rows, final, _ = final_rows_listed(dirs)
    return rows, final


def common_cells(final):
    """(final restricted to the (scene, repetition) cells where every arm of the run has a row that counts,
    the left-out cells with the arms that did not count): the headline table never gives the arms different
    denominators."""
    arms = sorted({k[0] for k in final})
    cells = sorted({(s, rep) for (_, s, rep) in final})
    keep, left = set(), []
    for c in cells:
        bad = [x for x in arms if not (final.get((x,) + c) or {}).get('counts')]
        if bad:
            left.append((c, bad))
        else:
            keep.add(c)
    return {k: r for k, r in final.items() if (k[1], k[2]) in keep}, left


def pair_stats(final, keys, x, y):
    """(pairs, both, x only, y only, neither): the (scene, repetition) pairs
    both arms counted on, and who succeeded on them."""
    pairs = [(s, rep) for (s, rep) in keys
             if final.get((x, s, rep), {}).get('counts') and final.get((y, s, rep), {}).get('counts')]
    both = sum(final[(x, s, r)]['success'] and final[(y, s, r)]['success'] for s, r in pairs)
    x_only = sum(final[(x, s, r)]['success'] and not final[(y, s, r)]['success'] for s, r in pairs)
    y_only = sum(final[(y, s, r)]['success'] and not final[(x, s, r)]['success'] for s, r in pairs)
    return pairs, both, x_only, y_only, len(pairs) - both - x_only - y_only


def attempt_lines(final, reruns, planned=None, changed=(), n_rows=None, left_out=(), unscored=0):
    """The first attempts and what became of them: the rows re-classified by today's rule, harness faults,
    failures that count by kind, our read failures, reruns and duplicates (never counted), the cells where
    both arms crashed, the planned cells against the rows, and whether the eval is full."""
    lines = []
    if n_rows is not None:
        lines.append(f"rows classified again from their stored records by today's rule (never from the stored "
                     f"counts and success): {len(changed)} of {n_rows} changed class"
                     + (f"; {unscored} row(s) have no stored record to score from and keep their stored class"
                        if unscored else ''))
        for stored_counts, stored_success, r in changed[:6]:
            lines.append(f"  {r['arm']} seed {r['seed']} rep {r['rep']} attempt {r['attempt']}: stored counts "
                         f"{stored_counts} success {stored_success}, now counts {r['counts']} success {r['success']} "
                         f"({str(r['why'])[:80] or 'no cause'})")
    faults = sorted((k, r) for k, r in final.items() if not r['counts'])
    lines.append("harness faults, first attempts that do not count (a scene that was seen and is another one, a gate "
                 "that says the scene is not the declared one, a pickle of theirs our reader could not read; none is "
                 f"run again, the eval is not full): {len(faults)}"
                 + ''.join(f"\n  {a} seed {s} rep {rep}: {str(r['why'])[:160]}"
                           + ('  (ours: needs a BUGS.md entry)'
                              if str(r['why']).startswith(('our read failed', 'gate_failed')) else '')
                           for (a, s, rep), r in faults))
    kinds = {}
    for k, r in sorted(final.items()):
        kd = failure_kind(r)
        if kd:
            kinds.setdefault(kd, []).append((k, r))
    arm_fail = {kd: v for kd, v in kinds.items() if kd != 'unread world'}
    lines.append("failures that count (first attempt; a crash, a hang to the cap, a failed gate of our arm or an "
                 "episode cut after its start is a failure of that arm): "
                 + (', '.join(f"{len(v)} {kd}" for kd, v in sorted(arm_fail.items())) or 'none'))
    for kd in ('crashed', 'gate', 'cut'):
        for (a, s, rep), r in kinds.get(kd, []):
            lines.append(f"  {a} seed {s} rep {rep} {kd}: {str(r['why'])[:200]}"
                         + ("  (ours: needs a BUGS.md entry with its cause)" if a != 'T' else ''))
    lines.append(f"our read failed (arm T's final world could not be read by our reader; ours, never booked as "
                 f"their failure, counted in the denominator as a non-success): {len(kinds.get('unread world', []))}")
    lines.append(f"reruns and duplicate rows (never counted, listed here, none collapsed silently): {len(reruns)}"
                 + ''.join(f"\n  {r['arm']} seed {r['seed']} rep {r['rep']} attempt {r['attempt']} ({kind}, "
                           f"{'counts' if r['counts'] else 'does not count'}, "
                           f"{'success' if r['success'] else 'no success'}) in {p}" for r, p, kind in reruns))
    both = sorted((s, rep) for (s, rep) in {(k[1], k[2]) for k in final}
                  if all(failure_kind(final.get((x, s, rep)) or {}) == 'crashed' for x in ('T', 'O')))
    lines.append(f"cells where both arms crashed: {len(both)}"
                 + (f" {both[:8]}: candidates for a shared-code cause (Hani, 15 Nov: then the seed is replaced and "
                    "disclosed); each stays a failure for both until then" if both else ''))
    if left_out:
        lines.append(f"headline cells: the cells where every arm has a counting first attempt; left out of the "
                     f"headline table for every arm (named): {len(left_out)} "
                     + ', '.join(f"seed {s} rep {rep} ({'/'.join(bad)} did not count)" for (s, rep), bad in left_out[:10]))
    missing = sorted(planned - set(final)) if planned is not None else []
    if planned is None:
        lines.append("planned cells: unknown (no metadata.json with seeds and repetitions was found), so 'full' is "
                     "not said")
    else:
        lines.append(f"planned cells {len(planned)} (arms x seeds x repetitions), rows for {len(planned & set(final))}; "
                     f"cells with no row: {len(missing)}"
                     + (f" {missing[:8]}" if missing else ''))
    problems = [x for x in (f"{len(missing)} planned cell(s) have no row" if missing else '',
                            f"{len(faults)} harness fault(s)" if faults else '',
                            f"{len(reruns)} rerun/duplicate row(s)" if reruns else '') if x]
    lines.append('full: every planned cell has one first attempt that counts' if planned is not None and not problems
                 else ('NOT FULL: ' + ', '.join(problems) if problems else 'full: not said (the planned cells are unknown)'))
    return lines


def report_tables(rows, final, brief=False, extra=()):
    """The tables of one view of the final rows (success = each row's
    'success'); brief leaves out the run counts, the per-scene table and the
    tail, for the second view of the same episodes."""
    has_o2 = any(arm == 'O2' for (arm, _, _) in final)      # path 6's arm A' (TB-1), see the docstring
    keys = sorted({(s, rep) for (_, s, rep) in final})
    lines = []
    if not brief:
        lines = [f"{len(rows)} episode runs, {len(final)} final (arm, scene, repetition); "
                 f"scenes {len({s for s, _ in keys})}, repetitions {len({r for _, r in keys})}", '']
        lines += list(extra)
        lines.append('')
        unread = [r for r in final.values() if r['arm'] == 'T' and str(r.get('why') or '').startswith(UNREAD_WHY)]
        if unread:
            lines.append("arm T outcomes whose final world our reader could not read (our read failed: ours, not a "
                         f"failure of arm T; {STOP_RULE_COUNT} stop the job, R2 of the G13 review): {len(unread)}"
                         + ''.join(f"\n  T seed {r['seed']} rep {r['rep']} attempt {r['attempt']}: "
                                   f"{r['why'][len(UNREAD_WHY) + 2:][:300]}" for r in unread))
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
                         "(an arm's first attempt did not count): "
                         + ', '.join(f"seed {s} rep {r}" for s, r in dropped))
    if brief:
        return '\n'.join(lines)
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


T_CAVEAT = ("Caveat first: TAMPURA carries the die kinematically (their Attachment), so arm T's standard test is "
            "read geometrically from its final world (the target attached, both finger pads within 5 mm of it, "
            "the arm at home), while arm O's is physical (both pads in contact at 0.5 N, the pipeline's own goal "
            "check). The same facts are read in two forms; they are not one measurement. Their own reward is "
            "printed beside the standard test.")


def stop_lines(dirs):
    """A job that the harness stop rule ended says so in its metadata.json; the report repeats it."""
    out = []
    for d in dirs:
        for p in sorted(set(glob.glob(os.path.join(d, 'metadata.json'))
                            + glob.glob(os.path.join(d, '*', 'metadata.json')))):
            md = bc.read_json(p) or {}
            if md.get('stop'):
                low = md['stop'].get('rule') == 'STOPPED_LOW_MEMORY'
                out.append(f"{'STOPPED_LOW_MEMORY' if low else 'STOPPED by the harness stop rule'} "
                           f"({os.path.dirname(p)}): {json.dumps(md['stop'])}")
    return out


def job_memory_lines(dirs):
    """The job script's own memory lines (tools/cluster/gen_eval.sbatch writes OUT/memory_lines.txt: the memory at the
    start and the file system under the job's folder, then what is left alive and in /dev/shm after the job)."""
    out = []
    for d in dirs:
        for p in sorted(set(glob.glob(os.path.join(d, 'memory_lines.txt'))
                            + glob.glob(os.path.join(d, '*', 'memory_lines.txt')))):
            with open(p, encoding='utf-8', errors='replace') as f:
                out += [f"memory ({os.path.dirname(p)}): {ln.strip()}" for ln in f if ln.strip()]
    return out


# THE ONE PLACE the choice of arm T's headline criterion sits (Hani 2026-11-15 13:51, "no" to the shared test
# deciding TAMPURA's success, is a reading the coordinator still confirms).  'standard' (default, DV-1): success
# is the standard test, their own reward beside it.  'reward': arm T's success in the headline tables and pairs is
# their own reward, the standard test beside it.  Whichever it is, both criteria are printed per episode and
# counted both ways (t_both_criteria_lines); the 5 mm bound is not claimed to change no result.
T_HEADLINE = 'standard'


def apply_t_headline(final):
    """final with arm T's success (and capped_success) replaced by their own reward when T_HEADLINE is 'reward'.
    An episode with no recorded reward keeps the standard test (and the report says how many)."""
    if T_HEADLINE != 'reward':
        return final
    out = {}
    for key, r in final.items():
        if key[0] == 'T' and r.get('t_reward_success') is not None:
            r = dict(r, success=bool(r['t_reward_success']), capped_success=bool(r['t_reward_success']))
        out[key] = r
    return out


def t_both_criteria_lines(final):
    """Arm T, both criteria for every counted episode and counted both ways: the standard test (the geometric
    final-world test, pad bound included) and their own reward.  `final` is the standard-test view."""
    eps = sorted(((s, rep), r) for (x, s, rep), r in final.items() if x == 'T' and r['counts'])
    if not eps:
        return []
    n = len(eps)
    k_std = sum(1 for _, r in eps if r['success'])
    k_rew = sum(1 for _, r in eps if r.get('t_reward_success'))
    (l1, h1), (l2, h2) = wilson(k_std, n), wilson(k_rew, n)
    no_reward = sum(1 for _, r in eps if r.get('t_reward_success') is None)
    lines = [f"arm T, both criteria counted ({n} counted episodes, first attempts, a crash a failure): the standard test "
             f"{k_std}/{n} [{l1:.2f}, {h1:.2f}], their own reward {k_rew}/{n} [{l2:.2f}, {h2:.2f}] (95 % Wilson); "
             f"the headline above uses {'their own reward' if T_HEADLINE == 'reward' else 'the standard test'} "
             f"(T_HEADLINE = {T_HEADLINE}); the two tests can differ on a real run, one episode's grasp can lie between "
             f"2 and 5 mm of the pad bound"
             + (f"; {no_reward} episodes have no recorded reward" if no_reward else '')]
    lines.append(f"  {'seed':>6} {'rep':>3} {'standard test':>13} {'their reward':>12}  pad readings, final world")
    for (s, rep), r in eps:
        fw = (r.get('rec') or {}).get('final_world') or {}
        gaps = ' and '.join('unseen' if g is None else f"{abs(g) * 1000:.2f} mm" for g in (fw.get('pad_gaps_m') or [])) or '-'
        rew = r.get('t_reward_success')
        lines.append(f"  {s:6} {rep:3} {('success' if r['success'] else 'failure'):>13} "
                     f"{('unknown' if rew is None else ('success' if rew else 'failure')):>12}  {gaps}"
                     + ('   <- the two differ' if rew is not None and bool(rew) != bool(r['success']) else ''))
    return lines


def t_pad_lines(final):
    """R1 of the G13 review: how far arm T's finger pads end from the held body in its final world (the raw
    readings), and the episodes that the pad bound alone fails."""
    reads = []
    for (arm, seed, rep), r in sorted(final.items()):
        fw = (r.get('rec') or {}).get('final_world') or {}
        if arm == 'T' and r['counts'] and fw.get('ok') and fw.get('attached'):
            gaps = [abs(g) for g in (fw.get('pad_gaps_m') or []) if g is not None]
            reads.append((seed, rep, r, fw, max(gaps) if gaps else None))
    if not reads:
        return []
    worst = [(w, s, rep) for s, rep, _, _, w in reads if w is not None]
    alone = [(s, rep, r, fw) for s, rep, r, fw, _ in reads if fw.get('at_home') and not fw.get('pads_on_target')]
    head = (f"arm T pad gaps in the final world (R1 of the G13 review; the raw readings are in each row's "
            f"final_world): target attached in {len(reads)} counted episodes")
    if worst:
        big = max(worst)
        head += (f"; largest pad gap {big[0] * 1000:.2f} mm (seed {big[1]} rep {big[2]}), median of the larger "
                 f"gap per episode {statistics.median(w for w, _, _ in worst) * 1000:.2f} mm")
    lines = [head + f"; attached and at home but failed by the pad bound alone: {len(alone)}"]
    for s, rep, r, fw in alone:
        gaps = ' and '.join('unseen' if g is None else f"{abs(g) * 1000:.2f} mm" for g in (fw.get('pad_gaps_m') or []))
        lines.append(f"  T seed {s} rep {rep}: pad gaps {gaps}, bound {fw['pad_gap_max_m'] * 1000:g} mm, "
                     f"their reward {'success' if r.get('t_reward_success') else 'failure'}; "
                     "reported to Sub-manager T and Go before a wave counts")
    return lines


def with_vs_without(final):
    """DV-2's evaluation of our approach with against without the 20-action
    limit, from the same episodes (arms O and O2; T keeps its own 20 steps)."""
    lines = ["with against without the 20-action limit (the same episodes, success = the standard test; "
             "t = the proxy picks + places + senses + observes + 1 on a success):",
             f"{'arm':4} {'counted':>8} {'without':>8} {'with':>6} {'lost':>5} "
             f"{'share of the successes':>23} {'t median':>9} {'t max':>6} {'t > 20':>7} {'t unknown':>9}"]
    lost_scenes, unknown_scenes = [], []
    for arm in ('O', 'O2'):
        cnt = [r for (x, _, _), r in final.items() if x == arm and r['counts']]
        if not cnt:
            continue
        wo = [r for r in cnt if r['success']]
        wi = [r for r in cnt if r['capped_success']]
        ts = [r['t_equiv'] for r in wo if r.get('t_equiv') is not None]
        lost = [r for r in wo if not r['capped_success']]
        over = [r for r in lost if r.get('t_equiv') is not None]      # the proxy is known and above the limit
        unknown = [r for r in lost if r.get('t_equiv') is None]       # no proxy count: a missing count
        share = f"{len(lost)}/{len(wo)}" if wo else '-'
        lines.append(f"{arm:4} {len(cnt):8} {len(wo):8} {len(wi):6} {len(lost):5} {share:>23} "
                     f"{_f(_med(ts)):>9} {(str(max(ts)) if ts else '-'):>6} {len(over):7} {len(unknown):9}")
        lost_scenes += [f"{arm} seed {r['seed']} rep {r['rep']} (t {r.get('t_equiv')})" for r in over]
        unknown_scenes += [f"{arm} seed {r['seed']} rep {r['rep']}" for r in unknown]
    if lost_scenes:
        lines.append("the limit turns these successes into failures: " + ', '.join(lost_scenes))
    if unknown_scenes:
        lines.append("successes without a proxy count (a missing count, not an action-limit failure; the "
                     "headline view counts them as not within the limit): " + ', '.join(unknown_scenes))
    lines.append("(a capped success is always an uncapped success, so a McNemar test of capped against "
                 "uncapped has no discordant pair on one side and is not printed; the tests are each "
                 "view against T, above)")
    return '\n'.join(lines)


def clean_of(row, success):
    """Rule 18's clean success of a row under one view's success: a failure is
    never clean; a success whose drops or collisions nothing could count is
    unknown (None), never clean by default."""
    if not success:
        return False
    d, c = row.get('drops'), row.get('collisions')
    if d is None or c is None:
        return None
    return d == 0 and c == 0


def _count_cells(cnt, field, detector):
    """The two cells of one count column of an arm (episodes with one or more,
    the total) and a note: numbers only over the episodes something counted;
    'cannot happen' and 'not detected' are printed as words, never as 0."""
    counted = [r[field] for r in cnt
               if isinstance(r.get(field), (int, float)) and not isinstance(r.get(field), bool)
               and not str(r.get(detector) or '').startswith('cannot happen')]
    if not counted:
        cannot = cnt and all(str(r.get(detector) or '').startswith('cannot happen') for r in cnt)
        return ('cannot happen' if cannot else 'not detected'), '-', ''
    rest = len(cnt) - len(counted)
    return (str(sum(1 for v in counted if v > 0)), str(int(sum(counted))),
            f"{rest} of {len(cnt)} episodes without a count" if rest else '')


def clean_lines(final, views=(('success', 'success'),)):
    """Rule 18 (tracks/STATE.md): the drops and the collisions of the counted
    episodes, how each count was taken, and clean success beside success for
    each view.  Recorded only: no count above changes with them.  The rows
    carry the fields since TB-22 (world_counts.of_record in run_one); rows
    from before it print one line."""
    counted = {k: r for k, r in final.items() if r['counts']}
    if not any('drop_detector' in r for r in counted.values()):
        return ["drops and collisions (rule 18): these rows carry no such fields (they were recorded before "
                "TB-22), so clean success is not shown"]
    arms = [x for x in ('O', 'O2', 'T') if any(k[0] == x for k in counted)]
    by_arm = {x: [r for k, r in counted.items() if k[0] == x] for x in arms}
    lines = ["drops and collisions (rule 18; recorded, they change no count above): a drop is a held body that left "
             "the gripper outside a place; a count that nothing could take is never printed as 0",
             f"{'arm':4} {'counted':>8} {'episodes with a drop':>21} {'drops':>6} "
             f"{'episodes with a collision':>26} {'collisions':>10}"]
    notes = []
    for arm in arms:
        cnt = by_arm[arm]
        d1, d2, dn = _count_cells(cnt, 'drops', 'drop_detector')
        c1, c2, cn = _count_cells(cnt, 'collisions', 'collision_detector')
        lines.append(f"{arm:4} {len(cnt):8} {d1:>21} {d2:>6} {c1:>26} {c2:>10}")
        notes += [f"  {arm} drops: {dn}"] if dn else []
        notes += [f"  {arm} collisions: {cn}"] if cn else []
    lines += notes
    lines.append("how each count was taken (the records' own words, with the number of episodes):")
    for arm in arms:
        for field in ('drop_detector', 'collision_detector'):
            texts = {}
            for r in by_arm[arm]:
                t = str(r.get(field) or 'no field in the row')
                texts[t] = texts.get(t, 0) + 1
            for t, n in sorted(texts.items(), key=lambda kv: -kv[1]):
                lines.append(f"  {arm} {field} ({n}): {t[:200]}")
    lines.append(f"{'arm':4} {'view':30} {'counted':>8} {'success':>8} {'clean success':>13} {'95 % Wilson':>14} "
                 f"{'unknown':>8}")
    for arm in arms:
        cnt = by_arm[arm]
        for key, label in views:
            verdicts = [clean_of(r, r.get(key)) for r in cnt]
            k = sum(1 for r in cnt if r.get(key))
            kc = sum(1 for v in verdicts if v is True)
            unknown = sum(1 for v in verdicts if v is None)
            if unknown == 0:
                lo, hi = wilson(kc, len(cnt))
                cell, ci = f"{kc:13}", f"[{lo:.2f}, {hi:.2f}]"
            elif unknown == k:
                cell, ci = f"{'not measured':>13}", f"{'-':>12}"
            else:
                cell, ci = f"{f'at least {kc}':>13}", f"{'-':>12}"
            lines.append(f"{arm:4} {label:30} {len(cnt):8} {k:8} {cell} {ci:>14} {unknown:8}")
    keys = sorted({(s, rep) for (_, s, rep) in counted})
    for x, y in (('O', 'T'), ('O2', 'O'), ('O2', 'T')):
        if x not in arms or y not in arms:
            continue
        for key, label in views:
            pairs = [(s, rep) for (s, rep) in keys if (x, s, rep) in counted and (y, s, rep) in counted]
            vx = {p: clean_of(counted[(x,) + p], counted[(x,) + p].get(key)) for p in pairs}
            vy = {p: clean_of(counted[(y,) + p], counted[(y,) + p].get(key)) for p in pairs}
            n_unknown = sum(1 for p in pairs if vx[p] is None or vy[p] is None)
            if n_unknown:
                lines.append(f"paired {x} against {y} on clean success ({label}): not printed, {n_unknown} of "
                             f"{len(pairs)} pairs hold a success whose drops or collisions nothing could count")
                continue
            both = sum(1 for p in pairs if vx[p] and vy[p])
            xo = sum(1 for p in pairs if vx[p] and not vy[p])
            yo = sum(1 for p in pairs if vy[p] and not vx[p])
            lines.append(f"paired {x} against {y} on clean success ({label}): {len(pairs)} pairs; both clean "
                         f"{both}, only {x} {xo}, only {y} {yo}, neither {len(pairs) - both - xo - yo}; "
                         f"exact McNemar p = {mcnemar_exact(xo, yo):.3g}")
    return lines


def report(dirs):
    loaded = load_all(dirs)
    rows, first_attempts, reruns = loaded['rows'], loaded['final'], loaded['reruns']
    if not first_attempts:
        return 'no episodes'
    stops = stop_lines(dirs)
    stops = stops + [''] if stops else []
    # the headline over the cells where every arm counts (the arms never get different denominators); the
    # first attempts of every cell, the faults and the reruns are listed in full beside it
    common, left_out = common_cells(first_attempts)
    extra = attempt_lines(first_attempts, reruns, loaded['planned'], loaded['changed'], len(rows), left_out,
                          loaded['unscored'])
    # arm T's own descriptive lines (both criteria, the pad gaps) read every first attempt of arm T that counts,
    # with success = the standard test: they compare nothing between arms, so no cell is left out of them
    std_final = first_attempts
    final = apply_t_headline(common)
    if not final:
        return '\n'.join(stops + extra + ['', 'no cell where every arm counts: no headline table'])
    if not all('capped_success' in r for r in final.values()):
        # no cap fields (BF#63 run 2 and earlier): an uncapped block, printed as before
        return '\n'.join(stops + [report_tables(rows, final, extra=extra), ''] + clean_lines(final))
    capped = {k: dict(r, success=r['capped_success']) for k, r in final.items()}
    out = [T_CAVEAT, ''] + stops
    out += [("success = the standard test (DV-1)" if T_HEADLINE != 'reward' else
             "success = the standard test for arms O and O2 and TAMPURA's own reward for arm T (T_HEADLINE = reward)")
            + f". Arms O and O2 are held to T's {CAP_ACTIONS}-action horizon "
            f"(DV-2): the headline view counts as a failure every episode whose proxy count exceeds "
            f"{CAP_ACTIONS}; the second view is the same episodes without the limit.",
            '',
            f"== headline: success within {CAP_ACTIONS} actions ==",
            report_tables(rows, capped, extra=extra),
            '',
            '== the same episodes without the action limit ==',
            report_tables(rows, final, brief=True),
            '',
            with_vs_without(final)]
    t_rows = [r for (x, _, _), r in std_final.items() if x == 'T' and r['counts']]
    both = sum(1 for r in t_rows if r['success'] and r.get('t_reward_success'))
    t_only = sum(1 for r in t_rows if r['success'] and not r.get('t_reward_success'))
    r_only = sum(1 for r in t_rows if not r['success'] and r.get('t_reward_success'))
    out += ['', f"arm T, the standard test against their own reward ({len(t_rows)} counted episodes): "
                f"both say success {both}, only the standard test {t_only}, only their reward {r_only}"]
    out += t_both_criteria_lines(std_final)
    out += t_pad_lines(std_final)
    out += [''] + clean_lines(final, views=(('capped_success', f'within {CAP_ACTIONS} actions (headline)'),
                                            ('success', 'without the action limit')))
    mem = [{'label': f"{r['arm']} seed {r['seed']} rep {r['rep']} attempt {r['attempt']}", 'mem': r['mem'],
            'peak_over_6gb': r.get('peak_over_6gb')} for r in rows if r.get('mem')]
    memory = (mw.summary_lines(mem) if mem else []) + job_memory_lines(dirs)
    if memory:
        out += [''] + memory
    return '\n'.join(out)


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
    ap.add_argument('--min-avail-gb', type=float, default=None,
                    help="rule 16: MemAvailable under this stops the job after the episode (default 4; 0 only records)")
    ap.add_argument('--peak-report-gb', type=float, default=None,
                    help="rule 16: a peak RSS over this is flagged peak_over_6gb (default 6; 0 only records)")
    ap.add_argument('--t-headline', choices=('standard', 'reward'), default='standard',
                    help="--report only: arm T's headline criterion, the standard test (default, DV-1) or their own "
                         "reward; both are printed per episode and counted either way (T_HEADLINE)")
    a = ap.parse_args(argv)
    if a.report:
        global T_HEADLINE
        T_HEADLINE = a.t_headline
        try:
            print(report(a.report))
        finally:
            T_HEADLINE = 'standard'
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
