"""#P4 GF3: G2's leak test, pre-planning half (PAPER_AUDIT.txt BF#14 GF3).

One process runs arm O's real driver (run_bridge_on_finddice.main) on one
seed with --stop-before-planning 1.  Right after gate_hooks.install, a
probe layer goes over pybullet's state reads:

  base   values pass through unchanged;
  noise  every value read while a declared write-only reader runs
         (gate_hooks.write_only: the settle disclosure, after_settle,
         world_eye, telemetry) is replaced by noise of the same shape, and
         in every tactile contact list (body A the robot, outside write-only)
         the non-robot body ids are permuted among the task bodies.

Both modes record what the pipeline built from its own inputs: the registry
(BoxelRegistry.to_dict at every belief-posed plan-twin sync), every
ray cast outside write-only (arguments and results) and every render
outside write-only.  `compare` passes when base and noise agree on all
three, and is only meaningful when two base runs agree as well and the noise
run replaced at least one value.  The noise comes from its own generator, so
the global random and numpy streams are untouched.

  python leak_probe.py run --seed 0 --mode noise --out probe.json --save-dir D
  python leak_probe.py compare base.json noise.json
--plant-leak adds a deliberate leak (the positive control; compare fails).
Run from their tampura_environments directory, arm O's venv, PYTHONPATH as
for the driver.
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import pybullet  # noqa: E402

from tampura_bridge import gate_hooks  # noqa: E402

READS = ('getBasePositionAndOrientation', 'getAABB', 'getClosestPoints',
         'getContactPoints', 'rayTest', 'rayTestBatch', 'getCameraImage',
         'getJointState', 'getJointStates', 'getLinkState', 'getLinkStates',
         'getBaseVelocity')
TACTILE = ('getClosestPoints', 'getContactPoints')
CASTS = ('rayTest', 'rayTestBatch')


def _digest(h, v):
    """Every value in full (repr would elide a large array)."""
    if isinstance(v, np.ndarray):
        h.update(f'{v.dtype}{v.shape}'.encode())
        h.update(np.ascontiguousarray(v).tobytes())
    elif isinstance(v, (list, tuple)):
        h.update(f'{type(v).__name__}{len(v)}('.encode())
        for x in v:
            _digest(h, x)
        h.update(b')')
    else:
        h.update(repr(v).encode() + b',')


class Probe:
    def __init__(self, mode):
        self.mode = mode
        self.rng = np.random.default_rng(20261028)
        self.noised = Counter()
        self.tactile_permuted = 0
        self.casts = hashlib.sha256()
        self.n_casts = 0
        self.renders = hashlib.sha256()
        self.n_renders = 0
        self.registry = None

    # ----- noise ----------------------------------------------------------

    def _noise(self, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, float):
            return float(self.rng.uniform(-2.0, 2.0))
        if isinstance(v, int):
            return int(self.rng.integers(-1, 12))
        if isinstance(v, np.ndarray):
            if v.dtype.kind == 'f':
                return self.rng.uniform(0.0, 1.0, v.shape).astype(v.dtype)
            return self.rng.integers(-1, 255, v.shape).astype(v.dtype)
        if isinstance(v, (list, tuple)):
            return type(v)(self._noise(x) for x in v)
        return v

    def _noise_image(self, img):
        w, h = img[0], img[1]
        out = [w, h]
        for k, arr in enumerate(img[2:]):
            a = np.asarray(arr)
            if k == 1:      # depth
                n = self.rng.uniform(0.0, 1.0, a.shape).astype(a.dtype)
            elif k == 2:    # segmentation
                n = self.rng.integers(-1, 12, a.shape).astype(a.dtype)
            else:           # rgba
                n = self.rng.integers(0, 256, a.shape).astype(a.dtype)
            out.append(n if isinstance(arr, np.ndarray)
                       else type(arr)(n.flatten().tolist()))
        return tuple(out)

    def _permute(self, points):
        cfg = gate_hooks._cfg
        ids = sorted(cfg.task_body_ids)
        if len(ids) < 2 or not points:
            return points
        perm = dict(zip(ids, ids[1:] + ids[:1]))
        out = []
        for pt in points:
            pt = list(pt)
            if pt[2] in perm:
                pt[2] = perm[pt[2]]
                self.tactile_permuted += 1
            out.append(tuple(pt))
        return tuple(out)

    # ----- the layer ------------------------------------------------------

    def wrap(self, name, inner):
        def probe(*args, **kwargs):
            result = inner(*args, **kwargs)
            if gate_hooks._write_only:
                if self.mode == 'noise':
                    self.noised[name] += 1
                    return (self._noise_image(result) if name == 'getCameraImage'
                            else self._noise(result))
                return result
            if name in CASTS:
                self.n_casts += 1
                _digest(self.casts, (name, args, sorted(kwargs.items()), result))
            elif name == 'getCameraImage':
                self.n_renders += 1
                for arr in result[2:]:
                    self.renders.update(np.ascontiguousarray(arr).tobytes())
            elif (name in TACTILE and self.mode == 'noise'
                  and gate_hooks._cfg is not None):
                a = gate_hooks._arg(args, kwargs, 0, 'bodyA')
                if a == gate_hooks._cfg.robot_id:
                    return self._permute(result)
            return result
        probe._gate_wrapped = True
        probe.__name__ = name
        return probe

    def install(self):
        orig_install, orig_uninstall = gate_hooks.install, gate_hooks.uninstall

        from world import boxel_env
        snapshots = self.registry = []

        def install(cfg):
            orig_install(cfg)
            for name in READS:
                setattr(pybullet, name, self.wrap(name, getattr(pybullet, name)))
            # The registry at every belief-posed plan-twin sync (main() lets
            # go of it on return, so it is copied here).
            hooked = boxel_env.BoxelTestEnv.sync_to_plan_client

            def sync_to_plan_client(env, held_body_id=None, registry=None):
                if hasattr(registry, 'to_dict'):
                    snapshots.append(registry.to_dict())
                elif registry is not None:   # _ObjectBoxLookup (B3(c))
                    snapshots.append({'object_estimates': [
                        b.to_dict() for _, b in sorted(registry._by_id.items())]})
                return hooked(env, held_body_id=held_body_id, registry=registry)
            boxel_env.BoxelTestEnv.sync_to_plan_client = sync_to_plan_client

        def uninstall():
            orig_uninstall()   # restores pybullet's originals and the sync

        gate_hooks.install, gate_hooks.uninstall = install, uninstall

    def record(self, seed, save_dir):
        reg = json.dumps(self.registry, sort_keys=True, default=str)
        episode = {}
        path = os.path.join(save_dir, 'bridge_episode.json')
        if os.path.isfile(path):
            with open(path) as f:
                episode = json.load(f)
        return {'seed': seed, 'mode': self.mode,
                'noised': dict(self.noised),
                'tactile_permuted': self.tactile_permuted,
                'registry_sha256': hashlib.sha256(reg.encode()).hexdigest(),
                'registry_summary': [s.get('summary') for s in self.registry],
                'casts': self.n_casts, 'casts_sha256': self.casts.hexdigest(),
                'renders': self.n_renders,
                'renders_sha256': self.renders.hexdigest(),
                'episode_error': episode.get('error'),
                'gate_counts': (episode.get('gates') or {}).get('counts'),
                'registry': self.registry}


def plant_leak():
    """The positive control: after_settle lets a write-only pose read reach
    the env (the table height every boxel stands on).  compare must FAIL."""
    from tampura_bridge import policy as bridge_policy
    make = bridge_policy.make_after_settle

    def make_after_settle(world, before, out):
        inner = make(world, before, out)

        def after_settle(env):
            inner(env)
            with gate_hooks.write_only('planted_leak'):
                z = pybullet.getBasePositionAndOrientation(
                    world.objects[0], physicsClientId=env.client_id)[0][2]
            env.table_surface_height += 1e-3 * z
        return after_settle
    bridge_policy.make_after_settle = make_after_settle


def run(a):
    probe = Probe(a.mode)
    probe.install()
    if a.plant_leak:
        plant_leak()
    from tampura_bridge import run_bridge_on_finddice
    sys.argv = ['run_bridge_on_finddice.py', '--global-seed', str(a.seed),
                '--vis', '0', '--stop-before-planning', '1',
                '--save-dir', a.save_dir]
    run_bridge_on_finddice.main()
    rec = probe.record(a.seed, a.save_dir)
    with open(a.out, 'w') as f:
        json.dump(rec, f, indent=1)
    print(json.dumps({k: v for k, v in rec.items() if k != 'registry'}))
    return 0


KEYS = ('registry_sha256', 'casts', 'casts_sha256', 'renders', 'renders_sha256')


def compare(paths):
    recs = []
    for p in paths:
        with open(p) as f:
            recs.append(json.load(f))
    bad = []
    for r in recs:
        if r['episode_error'] or r['gate_counts'] or not r['registry']:
            bad.append(f"{r['mode']}: error {r['episode_error']}, gate counts "
                       f"{r['gate_counts']}, {len(r['registry'])} registry "
                       f"snapshot(s)")
    ref = recs[0]
    for r in recs[1:]:
        diff = [k for k in KEYS if r[k] != ref[k]]
        if diff:
            bad.append(f"{r['mode']} differs from {ref['mode']} in {diff}")
    for r in recs:
        if r['mode'] == 'noise' and not sum(r['noised'].values()):
            bad.append('noise run replaced no value: vacuous')
    for r in recs:
        print(f"{r['mode']:<6} seed {r['seed']}  noised {r['noised']}  tactile "
              f"permuted {r['tactile_permuted']}  boxels {r['registry_summary']}  "
              f"casts {r['casts']}  renders {r['renders']}  registry "
              f"{r['registry_sha256'][:12]}")
    print('PASS' if not bad else 'FAIL: ' + '; '.join(bad))
    return 0 if not bad else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--seed', type=int, required=True)
    r.add_argument('--mode', choices=('base', 'noise'), required=True)
    r.add_argument('--out', required=True)
    r.add_argument('--save-dir', required=True)
    r.add_argument('--plant-leak', action='store_true')
    c = sub.add_parser('compare')
    c.add_argument('paths', nargs='+')
    a = ap.parse_args()
    return run(a) if a.cmd == 'run' else compare(a.paths)


if __name__ == '__main__':
    sys.exit(main())
