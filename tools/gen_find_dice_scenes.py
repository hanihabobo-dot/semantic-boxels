#!/usr/bin/env python3
"""BF#63: find_dice scenes made by TAMPURA's own generator, one per seed.

Their tampura_environments/find_dice/env_generator.py runs unmodified, as a
script (runpy, run_name '__main__'), in a scratch working directory: it
writes every scene it accepts to ./tampura_environments/find_dice/problems/
relative to that directory, never into their tree.  Before it runs, random
and numpy.random are seeded with the scene's seed, so scene s is the first
scene their generator accepts after random.seed(s).  The generator loops for
ever; the first complete JSON ends the run (its process group is killed).
The scene is copied to OUT/find_dice_gen_s<seed>.json and listed in
OUT/manifest.json with its sha256, their file name, the categories and the
generation time.  Nothing is filtered: every seed's first accepted scene is
kept, and a seed whose generator produces nothing within the timeout is
listed as such, never replaced.

  <their venv python> tools/gen_find_dice_scenes.py --seeds 100-139 \\
      --their-envs /root/tampura-work/tampura_environments --out DIR \\
      [--scratch DIR] [--jobs 4] [--timeout 600]
"""
import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

GENERATOR = os.path.join('tampura_environments', 'find_dice', 'env_generator.py')
PROBLEMS = os.path.join('tampura_environments', 'find_dice', 'problems')


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


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def child(seed, generator):
    """The generator's process: seed both global RNGs, then their script."""
    import random
    import runpy
    import numpy as np
    random.seed(seed)
    np.random.seed(seed)
    sys.argv = [generator]
    runpy.run_path(generator, run_name='__main__')


def first_scene(problems_dir):
    """The first complete scene JSON the generator wrote, or None."""
    try:
        names = sorted(n for n in os.listdir(problems_dir) if n.endswith('.json'))
    except OSError:
        return None
    for name in names:
        try:
            with open(os.path.join(problems_dir, name), 'r') as f:
                json.load(f)
            return name
        except (OSError, ValueError):
            continue
    return None


def generate(seed, a):
    cwd = os.path.join(a.scratch, f's{seed}')
    if os.path.isdir(cwd):
        shutil.rmtree(cwd)
    os.makedirs(cwd)
    problems_dir = os.path.join(cwd, PROBLEMS)
    log_path = os.path.join(cwd, 'generator.log')
    cmd = [sys.executable, '-u', os.path.abspath(__file__), '--child', str(seed),
           os.path.join(a.their_envs, GENERATOR)]
    t0 = time.time()
    name = None
    with open(log_path, 'w') as log:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        while time.time() - t0 < a.timeout:
            name = first_scene(problems_dir)
            if name or proc.poll() is not None:
                break
            time.sleep(0.2)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
    gen_s = round(time.time() - t0, 1)
    if name is None:
        name = first_scene(problems_dir)     # written between the last poll and the kill
    if name is None:
        with open(log_path, 'r', errors='replace') as f:
            tail = f.read()[-600:]
        return seed, {'scene': None, 'gen_s': gen_s, 'error': f'no scene in {gen_s} s: {tail}'}
    out_name = f'find_dice_gen_s{seed}.json'
    shutil.copyfile(os.path.join(problems_dir, name), os.path.join(a.out, out_name))
    with open(os.path.join(a.out, out_name), 'r') as f:
        data = json.load(f)
    cats = list(data.get('categories') or [])
    return seed, {'scene': out_name, 'their_name': name,
                  'sha256': sha256(os.path.join(a.out, out_name)),
                  'categories': cats, 'n_cups': sum('cups_ud' in c for c in cats),
                  'gen_s': gen_s}


def main(argv=None):
    if argv is None and len(sys.argv) > 1 and sys.argv[1] == '--child':
        child(int(sys.argv[2]), sys.argv[3])
        return 0
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--seeds', required=True)
    ap.add_argument('--their-envs', required=True, help='their tampura_environments checkout')
    ap.add_argument('--out', required=True)
    ap.add_argument('--scratch', default=None, help='working directories (deleted at the end)')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--timeout', type=float, default=600.0, help='seconds per seed')
    a = ap.parse_args(argv)
    a.out = os.path.abspath(a.out)
    a.scratch = os.path.abspath(a.scratch or os.path.join(a.out, '_scratch'))
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.scratch, exist_ok=True)
    gen_path = os.path.join(a.their_envs, GENERATOR)
    seeds = parse_seeds(a.seeds)
    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
        results = dict(pool.map(lambda s: generate(s, a), seeds))
    their_head = subprocess.run(['git', '-C', a.their_envs, 'rev-parse', '--short', 'HEAD'],
                                capture_output=True, text=True).stdout.strip()
    manifest = {
        'what': 'find_dice scenes from their env_generator.py, unmodified; scene s is the '
                'first scene it accepts after random.seed(s) and numpy.random.seed(s) (BF#63)',
        'generator': {'path': GENERATOR, 'sha256': sha256(gen_path),
                      'their_commit': their_head},
        'scenes': {str(s): results[s]['scene'] for s in seeds if results[s].get('scene')},
        'details': {str(s): results[s] for s in seeds},
        'made': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    with open(os.path.join(a.out, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=1)
    shutil.rmtree(a.scratch)
    for s in seeds:
        r = results[s]
        print(f"seed {s}: {r.get('scene') or 'NO SCENE'}  cups {r.get('n_cups')}  "
              f"{r.get('gen_s')} s{('  ' + r['error'][:200]) if r.get('error') else ''}", flush=True)
    missing = [s for s in seeds if not results[s].get('scene')]
    print(f"{len(seeds) - len(missing)} of {len(seeds)} scenes in {a.out}"
          + (f"; no scene for seeds {missing}" if missing else ''))
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
