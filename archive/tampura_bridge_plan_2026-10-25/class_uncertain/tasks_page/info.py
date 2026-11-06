"""Print what each scene holds (bodies, categories, poses) at seed 0."""
import sys

import numpy as np

from common import build_env

task = sys.argv[1]
if task == 'slam_collect':
    import matplotlib
    matplotlib.rcParams['savefig.dpi'] = 200
env, save_dir = build_env(task)
print('ENV', type(env).__name__, 'save_dir', save_dir)


def bodies(world):
    c = world.client
    print('objects', world.objects)
    print('categories', getattr(world, 'categories', None))
    print('regions', getattr(world, 'regions', None))
    for b in range(c.getNumBodies()):
        bid = c.getBodyUniqueId(b)
        pos, orn = c.getBasePositionAndOrientation(bid)
        name = c.getBodyInfo(bid)[1].decode()
        vs = c.getVisualShapeData(bid)
        rgba = [round(x, 2) for x in vs[0][7]] if vs else None
        aabb = c.getAABB(bid)
        print(f'  body {bid} {name} pos {np.round(pos, 3)} rgba {rgba} aabb {np.round(aabb[0], 3)} {np.round(aabb[1], 3)}')


if task == 'class_uncertain':
    w = env.state.world
    bodies(w)
elif task == 'find_dice':
    bodies(env.world)
elif task == 'tool_use':
    w = env.world
    print('ghosts', w.ghosts)
    bodies(w)
elif task == 'puck_slide':
    bodies(env.state.world)
elif task.startswith('slam_collect'):
    s = env.state
    print(type(s).__name__, [a for a in dir(s) if not a.startswith('_')])
    for k in ['robot', 'obstacles', 'beacons', 'targets', 'corners', 'goal']:
        v = getattr(s, k, None)
        items = v if isinstance(v, list) else [v]
        for r in items:
            print(k, getattr(r, 'pose', r), getattr(r, 'shape', None))
