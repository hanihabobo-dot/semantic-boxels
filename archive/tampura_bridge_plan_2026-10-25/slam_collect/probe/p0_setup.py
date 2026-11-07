"""P0: build slam_collect at seed 0 exactly as run_planner.py does (seeding, config,
get_env, initialize), print the map, the store names, the initial belief, and time one
call of each controller (their RRT on the mean particle). Read only over their tree;
save_dir is /root/sc_probe/run_p0."""
import os
import random
import sys
import time

import numpy as np

t0 = time.time()
from tampura.config import config as tconfig  # noqa: E402
import tampura_environments  # noqa: E402,F401
import tampura_environments.slam_collect.env as E  # noqa: E402
from tampura.structs import Action  # noqa: E402

print('import s', round(time.time() - t0, 2))
try:
    import scipy  # noqa: F401
    print('scipy', scipy.__version__)
except Exception as e:  # noqa: BLE001
    print('scipy missing', e)

task = sys.argv[1] if len(sys.argv) > 1 else 'slam_collect'
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 0
save_dir = f'/root/sc_probe/run_p0_{task}_{seed}'
os.makedirs(save_dir, exist_ok=True)
cfg = f'./env_configs/{task}.yml'
config = tconfig.load_config(config_file=cfg, arg_dict={'config': cfg, 'global_seed': seed,
                                                       'vis': False, 'save_dir': save_dir})
random.seed(config['global_seed'])
np.random.seed(config['global_seed'])
env = tconfig.get_env(config['task'])(config=config)
b0, store = env.initialize()
s = env.state
print('config', {k: config[k] for k in ['task', 'max_steps', 'num_samples', 'batch_size', 'gamma', 'decision_strategy']})
print('robot', s.robot.pose, s.robot.shape)
for k in ['obstacles', 'beacons', 'targets', 'corners']:
    for r in getattr(s, k):
        print(k, r.name, tuple(round(v, 3) for v in r.pose.to_array()), (round(r.shape.width, 3), round(r.shape.height, 3)))
print('goal', s.goal.name, s.goal.pose, s.goal.shape)
print('start', s.start.name, s.start.pose, s.start.shape)
print('regions', [r.name for r in s.regions])
print('subtypes', s.subtypes)
print('objects', env.objects)
print('certified', [str(a) for a in store.certified])
print('type_dict', {k: list(v) for k, v in store.type_dict.items()})
print('b0 particles', len(b0.particles), 'abstract', b0.abstract(store))
spec = env.problem_spec
print('reward(b0)', spec.get_reward(b0.abstract(store), store))

# time each controller once from the initial belief
names = {r.name: r for r in s.regions}
tg = s.targets[0].name
beacon = s.beacons[0].name
corner = s.corners[0].name
goal = s.goal.name
for a in [Action('move_pick', [tg]), Action('move_look', [beacon]), Action('move_to', [goal]),
          Action('move_corner', [corner])]:
    fn = {'move_pick': E.move_pick, 'move_look': E.move_look, 'move_to': E.move_to,
          'move_corner': E.move_corner}[a.name]
    t1 = time.time()
    prims = fn(a, b0, store)
    dt = time.time() - t1
    n = 0 if prims is None else len(prims)
    print('controller', a.name, a.args, 'primitives', n, 'seconds', round(dt, 2))
