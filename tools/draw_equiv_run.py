"""BF#68 check harness: run the bridge driver (tampura_bridge/run_bridge_on_
finddice.py) in this process exactly as `run tampura` runs it, with every
pybullet.getCameraImage result hashed on the way through, so that two runs
(with and without `--draw boxels`) can be compared render for render by
tools/draw_equiv_compare.py.

  python tools/draw_equiv_run.py --out DIR [--repo CHECKOUT] -- --global-seed 0 \\
      --vis 1 --save-dir DIR/ep [--draw boxels]          (the driver's own arguments)

Run it as `run tampura` runs the driver: arm O's venv, PYTHONPATH and cwd
(their tampura_environments directory, or the one-scene directory of -Gen),
PYTHONHASHSEED=0, under `flock /root/sb_pipeline.lock`.  --repo names the
checkout whose driver runs (default: the one this file is in), so the frozen
base (sb-stable) can run under the same harness; PYTHONPATH must name the same
checkout.  DIR must be new: a second run in it would mix two runs.

Writes DIR/run_info.json (which driver ran), DIR/render_hashes.jsonl (one row
per getCameraImage call: its index, client, size, renderer, a hash of the view
and projection matrices and the sha256 prefixes of the rgb, depth and
segmentation arrays) and, when the driver ends, DIR/probe_final.json (the
global RNG states hashed, the bodies of every connected client, how many debug
lines and texts were added).  The wrappers read what the simulator returns and
return it as it came: they change nothing the run sees or does.  They are
Python functions where the simulator's are builtins, so BulletClient (which
adds its client id to builtins only) gets the same compensation gate_hooks
gives its own hooks, for the whole run.

The process is seen by tools/run_procs.sh (run ps, run kill, run.ps1's busy
refusal) under its own name; run kill ends it."""
import argparse
import functools
import hashlib
import json
import os
import random
import runpy
import sys

import numpy as np

HERE_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARK = '_draw_equiv_wrapped'


def _sha(x):
    return hashlib.sha256(np.ascontiguousarray(np.asarray(x)).tobytes()).hexdigest()[:24]


def main():
    argv = sys.argv[1:]
    if '--' not in argv:
        raise SystemExit(__doc__)
    cut = argv.index('--')
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--repo', default=HERE_REPO)
    opts = ap.parse_args(argv[:cut])
    driver_args = argv[cut + 1:]
    repo = os.path.abspath(opts.repo)
    driver = os.path.join(repo, 'tampura_bridge', 'run_bridge_on_finddice.py')
    if not os.path.isfile(driver):
        raise SystemExit(f"draw_equiv_run: no driver at {driver}")
    if os.path.exists(os.path.join(opts.out, 'render_hashes.jsonl')):
        raise SystemExit(f"draw_equiv_run: {opts.out} holds a run already; use a new --out")
    os.makedirs(opts.out, exist_ok=True)
    with open(os.path.join(opts.out, 'run_info.json'), 'w', encoding='utf-8') as f:
        json.dump({'harness': 2, 'repo': repo, 'driver': driver, 'args': driver_args}, f, indent=1)
    if repo not in sys.path:
        sys.path.insert(0, repo)

    # The console first, as the driver does it, before pybullet's banner.
    import console_ui
    console_ui.install_early('__main__', argv=driver_args)

    import pybullet
    from pybullet_utils import bullet_client
    renders = open(os.path.join(opts.out, 'render_hashes.jsonl'), 'w', encoding='utf-8')
    n_render = [0]
    n_debug = {'line': 0, 'text': 0, 'remove': 0, 'remove_all': 0}
    real_camera = pybullet.getCameraImage
    real_line = pybullet.addUserDebugLine
    real_text = pybullet.addUserDebugText
    real_remove = pybullet.removeUserDebugItem
    real_remove_all = pybullet.removeAllUserDebugItems

    def camera(*args, **kwargs):
        out = real_camera(*args, **kwargs)
        view = kwargs.get('viewMatrix', args[2] if len(args) > 2 else None)
        proj = kwargs.get('projectionMatrix', args[3] if len(args) > 3 else None)
        # getCameraImage(width, height, viewMatrix, projectionMatrix,
        # lightDirection, lightColor, lightDistance, shadow, lightAmbientCoeff,
        # lightDiffuseCoeff, lightSpecularCoeff, renderer, ...)
        renderer = kwargs.get('renderer', args[11] if len(args) > 11 else None)
        row = {'i': n_render[0], 'client': kwargs.get('physicsClientId', 0),
               'w': int(out[0]), 'h': int(out[1]),
               'renderer': renderer,
               # TinyRenderer makes every observation; the hardware renderer
               # makes TAMPURA's own first image and refreshes the GUI's own
               # panes (boxel_env.py:1805, 1834)
               'tiny': renderer == pybullet.ER_TINY_RENDERER,
               'view': _sha(view) if view is not None else None,
               'proj': _sha(proj) if proj is not None else None,
               'rgb': _sha(out[2]), 'depth': _sha(out[3]), 'seg': _sha(out[4])}
        renders.write(json.dumps(row) + '\n')
        renders.flush()
        n_render[0] += 1
        return out

    def line(*args, **kwargs):
        n_debug['line'] += 1
        return real_line(*args, **kwargs)

    def text(*args, **kwargs):
        n_debug['text'] += 1
        return real_text(*args, **kwargs)

    def remove(*args, **kwargs):
        n_debug['remove'] += 1
        return real_remove(*args, **kwargs)

    def remove_all(*args, **kwargs):
        n_debug['remove_all'] += 1
        return real_remove_all(*args, **kwargs)

    wrappers = (camera, line, text, remove, remove_all)
    for fn in wrappers:
        setattr(fn, MARK, True)
    pybullet.getCameraImage = camera
    pybullet.addUserDebugLine = line
    pybullet.addUserDebugText = text
    pybullet.removeUserDebugItem = remove
    pybullet.removeAllUserDebugItems = remove_all

    # BulletClient.__getattr__ puts physicsClientId into a call only when the
    # function is a builtin; ours are not, so without this a call through a
    # BulletClient (their pb_utils and voxel_utils debug draws, the driver's
    # clear_debug_lines) would reach client 0 whichever client it names.
    real_getattr = bullet_client.BulletClient.__getattr__

    def getattr_(self, name):
        attr = real_getattr(self, name)
        if getattr(attr, MARK, False):
            attr = functools.partial(attr, physicsClientId=self._client)
        return attr

    bullet_client.BulletClient.__getattr__ = getattr_

    real_finish = console_ui.finish

    def finish(code=0):
        try:
            nps = np.random.get_state()
            clients = {}
            for k in range(8):
                try:
                    if pybullet.isConnected(physicsClientId=k):
                        n = pybullet.getNumBodies(physicsClientId=k)
                        clients[str(k)] = {
                            'bodies': n,
                            'ids': [pybullet.getBodyUniqueId(i, physicsClientId=k)
                                    for i in range(n)]}
                except Exception:
                    pass
            final = {
                'random_state': hashlib.sha256(
                    repr(random.getstate()).encode()).hexdigest()[:24],
                'numpy_state': hashlib.sha256(
                    nps[1].tobytes() + repr(nps[2:]).encode()).hexdigest()[:24],
                'renders': n_render[0], 'debug_calls': n_debug,
                'clients': clients, 'exit_code': code}
            with open(os.path.join(opts.out, 'probe_final.json'), 'w',
                      encoding='utf-8') as f:
                json.dump(final, f, indent=1)
            renders.close()
        except Exception as e:                      # never touches the run
            print(f"draw_equiv_run: final probe failed: {e!r}", file=sys.stderr)
        return real_finish(code)

    console_ui.finish = finish
    sys.argv = [driver] + driver_args
    runpy.run_path(driver, run_name='__main__')


if __name__ == '__main__':
    main()
