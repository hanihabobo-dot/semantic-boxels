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

VALIDITY (declared before any run): an episode counts if it loaded its own
scene and ended with an outcome: success, failure, or the cap (a timeout is
a failure of that arm).  It does not count if it crashed (no outcome), a
gate failed, or it loaded another scene; such an episode runs once more
with the same scene, seed and repetition, and if that run does not count
either, the scene's repetition leaves the paired comparison for both arms
and is listed.

  <arm O python> tools/gen_scene_eval.py --snapshot SB --out OUT --seeds 100-103 \\
      --reps 2 --python-o PY --venv-t TW/.venv --tampura-work TW [--cap 600]
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


def run_one(a, arm, seed, rep, attempt, scene, order):
    cwd = episode_cwd(a, arm, seed, rep, attempt, scene)
    sub = 'T' if arm == 'T' else 'O'
    out = os.path.join(a.out, sub if attempt == 1 else f'{sub}_retry')
    if arm == 'T':
        ns = SimpleNamespace(out=out, venv_t=a.venv_t, snapshot=a.snapshot, mode='full',
                             cap=a.cap, their_envs=cwd, pythonhashseed='0',
                             tampura_work=a.tampura_work, drop_t_history=True)
        rec = bc.episode_t(ns, rep, seed, order, {seed: scene}, bc.machine_check())
        ok, why = classify_t(rec)
        success = rec.get('status') == 'success'
        wall, loop = rec.get('wall_s'), rec.get('loop_s')
        timed_out = rec.get('status') == 'killed'
    else:
        ns = SimpleNamespace(out=out, python=a.python_o, snapshot=a.snapshot, cwd=cwd, cap=a.cap)
        rec = se.run_episode(ns, ARM_O, seed, rep)
        ok, why = classify_o(rec, scene)
        m = rec.get('metrics') or {}
        # the bridge's outcome (their reward, the error, the ledger gates) and
        # the pipeline's own goal check must both say success
        success = rec.get('bridge_status') == 'success' and m.get('outcome') == 'success'
        if (rec.get('bridge_status') == 'success') != (m.get('outcome') == 'success'):
            why = (why + '; ' if why else '') + (f"outcomes disagree: bridge {rec.get('bridge_status')}"
                                                 f", pipeline {m.get('outcome')}")
        wall, loop = rec.get('process_wall_s'), m.get('wall_s')
        timed_out = bool(rec.get('timed_out'))
    shutil.rmtree(cwd)
    return {'arm': arm, 'seed': seed, 'rep': rep, 'attempt': attempt, 'scene': scene,
            'n_cups': a.cups.get(str(seed)), 'counts': ok, 'why': why,
            'success': bool(ok and success and not timed_out), 'timed_out': timed_out,
            'wall_s': wall, 'loop_s': loop, 'host': os.uname().nodename,
            'finished': time.strftime('%Y-%m-%d %H:%M:%S'), 'rec': rec}


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
    alive = se.pipeline_alive(os.getpid())
    if alive:
        raise SystemExit("a pipeline process is alive: " + '; '.join(alive))
    os.makedirs(a.out, exist_ok=True)
    se.check_arms(SimpleNamespace(python=a.python_o, snapshot=a.snapshot), [ARM_O])
    md_path = os.path.join(a.out, 'metadata.json')
    if not os.path.isfile(md_path):
        bc.write_json(md_path, {'snapshot': a.snapshot, 'scenes': a.scenes, 'seeds': seeds,
                                'reps': a.reps, 'cap_s': a.cap, 'arm_o': ARM_O,
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
            for arm in ('T', 'O'):
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


def report(dirs):
    rows, final = final_rows(dirs)
    if not final:
        return 'no episodes'
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
    for arm in ('O', 'T'):
        rs = [r for (x, _, _), r in final.items() if x == arm]
        cnt = [r for r in rs if r['counts']]
        k = sum(r['success'] for r in cnt)
        lo, hi = wilson(k, len(cnt))
        lines.append(f"{arm:4} {len(cnt):8} {k:8} {(k / len(cnt) if cnt else float('nan')):6.2f} "
                     f"[{lo:.2f}, {hi:.2f}]  {sum(r['timed_out'] for r in cnt):8} "
                     f"{len(rs) - len(cnt):11} {_f(_med(r['wall_s'] for r in cnt)):>13} "
                     f"{_f(_med(r['wall_s'] for r in cnt if r['success'])):>11}")
    pairs = [(s, rep) for (s, rep) in keys
             if final.get(('O', s, rep), {}).get('counts') and final.get(('T', s, rep), {}).get('counts')]
    both = sum(final[('O', s, r)]['success'] and final[('T', s, r)]['success'] for s, r in pairs)
    o_only = sum(final[('O', s, r)]['success'] and not final[('T', s, r)]['success'] for s, r in pairs)
    t_only = sum(final[('T', s, r)]['success'] and not final[('O', s, r)]['success'] for s, r in pairs)
    neither = len(pairs) - both - o_only - t_only
    lines.append('')
    lines.append(f"paired (both arms counted on the same scene and repetition): {len(pairs)} pairs; "
                 f"both succeed {both}, only O {o_only}, only T {t_only}, neither {neither}; "
                 f"exact McNemar p = {mcnemar_exact(o_only, t_only):.3g}")
    dropped = [(s, rep) for (s, rep) in keys if (s, rep) not in pairs]
    if dropped:
        lines.append('left out of the pairs (an arm did not count twice): '
                     + ', '.join(f"seed {s} rep {r}" for s, r in dropped))
    lines.append('')
    lines.append('per scene (successes / counted runs; cups from the manifest):')
    lines.append(f"{'seed':>6} {'cups':>5} {'O':>6} {'T':>6}   T's last actions when it failed")
    for s in sorted({s for s, _ in keys}):
        cells = {}
        for arm in ('O', 'T'):
            rs = [r for (x, ss, _), r in final.items() if x == arm and ss == s and r['counts']]
            cells[arm] = f"{sum(r['success'] for r in rs)}/{len(rs)}"
        cups = next((r.get('n_cups') for (x, ss, _), r in final.items() if ss == s), None)
        tails = []
        for (x, ss, _), r in sorted(final.items()):
            if x == 'T' and ss == s and r['counts'] and not r['success']:
                acts = (r['rec'].get('get_action_actions') or [])[-3:]
                tails.append('|'.join(acts) or r['why'])
        lines.append(f"{s:>6} {_f(cups, 0) if cups is not None else '-':>5} {cells['O']:>6} {cells['T']:>6}   "
                     + '; '.join(t[:90] for t in tails))
    o_c = sum((r['rec'].get('carries') or 0) for (x, _, _), r in final.items() if x == 'O' and r['counts'])
    o_l = sum((r['rec'].get('losses') or 0) for (x, _, _), r in final.items() if x == 'O' and r['counts'])
    lines.append('')
    lines.append(f"arm O die carries {o_c}, lost in the hand {o_l}")
    t_s = [r['rec'].get('time_to_success_s') for (x, _, _), r in final.items() if x == 'T' and r['success']]
    lines.append(f"arm T median time to success {_f(_med(t_s))} s (their loop clock)")
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
    a = ap.parse_args(argv)
    if a.report:
        print(report(a.report))
        return 0
    for name in ('snapshot', 'out', 'seeds', 'python_o', 'venv_t', 'tampura_work'):
        if not getattr(a, name):
            ap.error(f"--{name.replace('_', '-')} is required to run episodes")
    a.snapshot = os.path.abspath(a.snapshot)
    a.out = os.path.abspath(a.out)
    a.tampura_work = os.path.abspath(a.tampura_work)
    a.venv_t = os.path.abspath(a.venv_t)
    a.scenes = os.path.join(a.snapshot, SCENES_REL)
    return run(a)


if __name__ == '__main__':
    sys.exit(main())
