"""#P4 B2: our pipeline on TAMPURA's find_dice, one seed (PAPER_AUDIT.txt
P4.4 B2).  Arm O's driver: run_planner.py's order (seed random and numpy
with the global seed, build FindDiceEnv, initialize), then the bridge's
only additions: assert the loaded scene against the pinned map (G19),
register the boxel_episode schema (G13's one arm-O registration) and run
their rollout with BoxelBridgePolicy.  Exit code 0 iff rewards[-1] == 1.0
(G12).  Run from their tampura_environments directory in arm O's venv:

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


def _pinned_scene_map():
    """G19's pinned map, from tools/bridge_gates.py (one place only)."""
    path = os.path.join(REPO, 'tools', 'bridge_gates.py')
    spec = importlib.util.spec_from_file_location('_bridge_gates_map', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SCENE_MAP


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
    a = ap.parse_args()
    arg_dict = {'config': a.config, 'global_seed': a.global_seed,
                'vis': bool(a.vis), 'save_dir': a.save_dir}
    config = tconfig.load_config(config_file=a.config, arg_dict=arg_dict)

    # G19: the global RNG is seeded exactly as run_planner.py does, and
    # nothing consumes it before their get_scene_data.
    random.seed(config['global_seed'])
    np.random.seed(config['global_seed'])
    tconfig.setup_logger(config['save_dir'], log_level=logging.INFO)
    scene = _SceneFile()
    logging.getLogger().addHandler(scene)

    env = tconfig.get_env(config['task'])(config=config)
    b0, store = env.initialize()

    pinned = _pinned_scene_map().get(a.global_seed)
    if scene.name_seen is None or pinned is None or pinned not in scene.name_seen:
        raise SystemExit(f"G19: seed {a.global_seed} loaded {scene.name_seen}, "
                         f"pinned {pinned}")
    cfg = bridge_policy.EpisodeConfig(
        seed=a.global_seed, scene_file=scene.name_seen,
        log_dir=os.path.join(config['save_dir'], 'ours'), vis=bool(a.vis),
        stop_before_planning=bool(a.stop_before_planning),
        log_level=a.log_level, max_plan_time=a.max_plan_time)
    execute_fn = bridge_policy.make_execute_fn(env, cfg)
    bridge_policy.register_schema(env, execute_fn)
    policy = bridge_policy.bridge_policy_class()(config, env.problem_spec)
    # G13's runtime half (GF1): recorded, and the run stops here on a failure
    g13 = g13_runtime.check_arm_o(env, policy, b0, bridge_policy.SCHEMA_NAME, execute_fn)
    cfg.out['g13_runtime'] = g13
    g13_runtime.write_and_enforce(g13, config['save_dir'])
    history, _ = policy.rollout(env, b0, store)

    cfg.out['rewards'] = [float(r) for r in history.rewards]
    cfg.out['time_deltas'] = [float(t) for t in history.time_deltas]
    with open(os.path.join(config['save_dir'], 'bridge_episode.json'), 'w') as f:
        json.dump({'seed': a.global_seed, 'scene_file': scene.name_seen,
                   **cfg.out}, f, indent=1, default=str)
    print(f"seed {a.global_seed}: their RolloutHistory rewards[-1] = "
          f"{history.rewards[-1]}; details in {config['save_dir']}")
    return 0 if history.rewards[-1] == 1.0 else 1


if __name__ == '__main__':
    sys.exit(main())
