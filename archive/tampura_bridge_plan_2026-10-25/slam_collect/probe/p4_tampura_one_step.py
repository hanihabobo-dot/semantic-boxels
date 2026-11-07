"""P4: one TAMPURA planning step (get_action at t = 0, not an episode) on
slam_collect, built exactly as run_planner.py does, to time a step on this machine
and record the first action. Read only over their tree; save_dir under /root/sc_probe.
Usage: python p4_tampura_one_step.py <task> <seed>"""
import json
import os
import random
import sys
import time

import numpy as np
from tampura.config import config as tconfig
import tampura_environments  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
task = sys.argv[1] if len(sys.argv) > 1 else 'slam_collect'
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 0
save_dir = f'/root/sc_probe/run_p4_{task}_{seed}'
os.makedirs(save_dir, exist_ok=True)
cfg = f'./env_configs/{task}.yml'
config = tconfig.load_config(config_file=cfg, arg_dict={'config': cfg, 'global_seed': seed,
                                                       'vis': False, 'save_dir': save_dir})
random.seed(config['global_seed'])
np.random.seed(config['global_seed'])
tconfig.setup_logger(config['save_dir'], log_level=30)  # warnings only
env = tconfig.get_env(config['task'])(config=config)
b0, store = env.initialize()
policy = tconfig.get_planner(config['planner'])(config, env.problem_spec, execution_data=None)
t0 = time.perf_counter()
action, info, store = policy.get_action(b0, store)
dt = time.perf_counter() - t0
F = info['F']
n_ab = len({ab for a in F.effects for ab in F.effects[a]})
out = {'task': task, 'seed': seed, 'get_action_s': round(dt, 2), 'action': str(action),
       'actions_in_F': len(F.effects), 'source_beliefs_in_F': n_ab}
print(json.dumps(out))
with open(os.path.join(OUT, f'tampura_one_step_{task}_{seed}.json'), 'w') as f:
    json.dump(out, f, indent=1)
