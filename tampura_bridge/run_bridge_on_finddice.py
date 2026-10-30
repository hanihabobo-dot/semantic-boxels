"""#P4 B2: our pipeline on TAMPURA's find_dice, one seed (PAPER_AUDIT.txt
P4.4 B2).  Arm O's driver: run_planner.py's order (seed random and numpy
with the global seed, build FindDiceEnv, initialize), then the bridge's
only additions: assert the loaded scene against the pinned map (G19),
register the boxel_episode schema (G13's one arm-O registration) and run
their rollout with BoxelBridgePolicy.  It stamps its clock and records the
RNG state for G18 and G19, and writes one outcome field that combines
rewards[-1], the error and the ledger reader's gates (RG1.7).  Exit code 0
iff that outcome is success.  Run from their tampura_environments
directory in arm O's venv:

  PYTHONPATH=<repo>:<pddlstream_lib>:<their tampura>:<their envs> \\
    <arm O python> <repo>/tampura_bridge/run_bridge_on_finddice.py \\
    --global-seed 0 --vis 0
"""
import argparse
import importlib.util
import json
import logging
import os
import random
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from tampura.config import config as tconfig    # noqa: E402
import tampura_environments                      # noqa: E402,F401

from tampura_bridge import g13_runtime              # noqa: E402
from tampura_bridge import policy as bridge_policy   # noqa: E402


class _SceneFile(logging.Handler):
    """Their get_scene_data logs the scene file it loaded (env.py:806); the
    bridge reads that line and nothing of the file."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.name_seen = None

    def emit(self, record):
        msg = record.getMessage()
        if msg.startswith('Loading scene from '):
            self.name_seen = msg[len('Loading scene from '):].strip()


def _bridge_gates():
    """tools/bridge_gates.py: G19's pinned map (one place only) and the
    ledger reader behind the outcome field."""
    path = os.path.join(REPO, 'tools', 'bridge_gates.py')
    spec = importlib.util.spec_from_file_location('_bridge_gates', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rng_untouched(seed):
    """G19: both global RNGs are in the state their seeding left."""
    s, t = np.random.get_state(), np.random.RandomState(seed).get_state()
    return {'random': random.getstate() == random.Random(seed).getstate(),
            'numpy': (s[0] == t[0] and bool(np.array_equal(s[1], t[1]))
                      and tuple(s[2:]) == tuple(t[2:]))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='./env_configs/find_dice.yml')
    ap.add_argument('--global-seed', type=int, required=True)
    ap.add_argument('--vis', type=int, default=0)
    ap.add_argument('--save-dir', default=os.path.join(
        os.getcwd(), 'runs', f'bridge_{time.time()}'))
    ap.add_argument('--stop-before-planning', type=int, default=0)
    ap.add_argument('--log-level', default='smart')
    ap.add_argument('--max-plan-time', type=float, default=900.0)
    # BF#45: a headless diagnostic run on a scene the laptop maps to another
    # seed than the campaign does (BF#8, BF#39) continues past G19 like a
    # GUI run, never scored; the ledger's G19 gate records the mismatch.
    ap.add_argument('--allow-g19-mismatch', type=int, default=0)
    # M8-M10 (P4.5 model tweaks), passed through to main()'s CLI flags.
    # (--sense-anywhere, BF#52: sense from the pick configuration over the
    # region when the arm there does not block the eye's view; off returns
    # to a view spot before every sense as before.)
    for flag in ('--m8', '--m9', '--m10', '--pick-aperture-from-pose',
                 '--sense-anywhere'):
        ap.add_argument(flag, choices=('off', 'on'), default='on')
    # GF10 (BF#38): the pick close's squeeze (0.5 mm since BF#44), passed through like the switches.
    ap.add_argument('--grip-squeeze-mm', type=float, default=0.5)
    # BF#50 (user rule, 2026-10-30): the eye images are for debugging only,
    # off unless asked; passed through like the switches.
    ap.add_argument('--save-screenshots', choices=('off', 'on'), default='off')
    a = ap.parse_args()
    arg_dict = {'config': a.config, 'global_seed': a.global_seed,
                'vis': bool(a.vis), 'save_dir': a.save_dir}
    config = tconfig.load_config(config_file=a.config, arg_dict=arg_dict)

    # G18: the driver's clock stamps (perf_counter, the ledger's clock),
    # written to the episode's ledger by execute_fn.
    events = []

    def stamp(name):
        events.append((name, time.perf_counter()))

    # G19: the global RNG is seeded exactly as run_planner.py does, and
    # nothing consumes it before their get_scene_data.
    random.seed(config['global_seed'])
    np.random.seed(config['global_seed'])
    stamp('seeded')
    tconfig.setup_logger(config['save_dir'], log_level=logging.INFO)
    scene = _SceneFile()
    logging.getLogger().addHandler(scene)

    rng_untouched = _rng_untouched(config['global_seed'])
    stamp('initialize_call')
    env = tconfig.get_env(config['task'])(config=config)
    b0, store = env.initialize()
    stamp('initialize_return')
    # Their initialize draws the visibility grid's boxes as GUI debug lines
    # (voxel_utils.draw_intervals, cloud_vis False); clear them so the GUI
    # shows the scene alone.  Debug lines are not in camera renders, so the
    # eye images are the same either way.
    def clear_debug_lines():
        for w in {id(x): x for x in (env.world, getattr(env, 'sim_world', None))
                  if x is not None}.values():
            w.client.removeAllUserDebugItems()

    if a.vis:
        clear_debug_lines()
        # BF#41: their rollout redraws the grid after every step
        # (Policy.rollout calls env.vis_updated_belief), so our get_action
        # clears it before each step and the driver once more after the
        # rollout.  Nothing is set when headless.
        bridge_policy.GUI_CLEANUP = clear_debug_lines

    gates = _bridge_gates()
    pinned = gates.SCENE_MAP.get(a.global_seed)
    mismatch = (scene.name_seen is None or pinned is None
                or pinned not in scene.name_seen)
    if mismatch and not a.vis and not a.allow_g19_mismatch:
        raise SystemExit(f"G19: seed {a.global_seed} loaded {scene.name_seen}, "
                         f"pinned {pinned}")
    if mismatch:
        # BF#39: a GUI run is for watching only and is never scored (P4.6
        # MODE).  Their problems/ listing order differs between the laptop
        # and the cluster (BF#8), so most seeds load another scene here than
        # the campaign map pins; the run goes on with the scene this machine
        # gave the seed, and the ledger's G19 gate records the mismatch (the
        # outcome field then says gate_failed).  Headless runs still stop.
        print(f"G19: seed {a.global_seed} loaded {scene.name_seen}, the campaign "
              f"pins {pinned}: a watching or diagnostic run, never scored "
              f"(the ledger's G19 gate records the mismatch)", flush=True)
    stamp('scene_map_asserted')
    cfg = bridge_policy.EpisodeConfig(
        seed=a.global_seed, scene_file=scene.name_seen,
        log_dir=os.path.join(config['save_dir'], 'ours'), vis=bool(a.vis),
        stop_before_planning=bool(a.stop_before_planning),
        log_level=a.log_level, max_plan_time=a.max_plan_time,
        switches={'m8': a.m8, 'm9': a.m9, 'm10': a.m10,
                  'pick_aperture_from_pose': a.pick_aperture_from_pose,
                  'sense_anywhere': a.sense_anywhere,
                  'grip_squeeze_mm': str(a.grip_squeeze_mm),
                  'save_screenshots': a.save_screenshots})
    cfg.driver = {'events': events, 'seed': config['global_seed'],
                  'rng_untouched': rng_untouched,
                  'pythonhashseed': os.environ.get('PYTHONHASHSEED')}
    execute_fn = bridge_policy.make_execute_fn(env, cfg)
    bridge_policy.register_schema(env, execute_fn)
    stamp('schema_registered')
    policy = bridge_policy.bridge_policy_class()(config, env.problem_spec)
    stamp('policy_built')
    # G13's runtime half (GF1): recorded, and the run stops here on a failure
    g13 = g13_runtime.check_arm_o(env, policy, b0, bridge_policy.SCHEMA_NAME, execute_fn)
    cfg.out['g13_runtime'] = g13
    g13_runtime.write_and_enforce(g13, config['save_dir'])
    stamp('g13_checked')
    stamp('rollout_start')
    history, _ = policy.rollout(env, b0, store)
    if a.vis:
        clear_debug_lines()

    cfg.out['rewards'] = [float(r) for r in history.rewards]
    cfg.out['time_deltas'] = [float(t) for t in history.time_deltas]
    # The outcome field (RG1.7): rewards[-1], the error and the ledger
    # reader's per-episode gates; success is never rewards[-1] alone.
    report = gates.Report()
    try:
        gates.run_ledger(report, cfg.out['run_dir'])
    except Exception as e:
        report.add('ledger', 'FAIL', f"{type(e).__name__}: {e}")
    cfg.out['ledger_gates'] = report.rows
    cfg.out['outcome'] = gates.episode_outcome(
        cfg.out['rewards'], cfg.out.get('error'), report)
    with open(os.path.join(config['save_dir'], 'bridge_episode.json'), 'w') as f:
        # BF#41: the switches (M8 to M10, the aperture rule, the squeeze)
        # travel with the episode; bridge runs leave main()'s run_config
        # empty, so this is the one record of them.
        json.dump({'seed': a.global_seed, 'scene_file': scene.name_seen,
                   'switches': dict(cfg.switches), **cfg.out}, f, indent=1,
                  default=str)
    report.show()
    print(f"seed {a.global_seed}: outcome {cfg.out['outcome']['status']}, their "
          f"RolloutHistory rewards[-1] = {history.rewards[-1]}; details in "
          f"{config['save_dir']}")
    return 0 if cfg.out['outcome']['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
