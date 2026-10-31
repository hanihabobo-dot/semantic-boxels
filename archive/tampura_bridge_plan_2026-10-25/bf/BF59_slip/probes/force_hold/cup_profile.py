"""The seed-0 cup's collision radius per height (BF#59 force_hold jam probe):
d_cups_ud from their create_ycb (concave, VHACD hulls) at the scene pose on
their table; horizontal rays from 90 mm outside toward the cup's axis (the
AABB centre) at 36 bearings per height, the first hit is the outer surface.
Also the finger links' inner faces at the full open (q 40 mm).
  S=<worktree> python cup_profile.py"""
import math
import os
import sys

import numpy as np
import pybullet as p

S = os.environ['S']
sys.path.insert(0, S)
import robot_utils                                   # noqa: E402
from tampura_bridge import task_spec                 # noqa: E402
from tampura_environments.find_dice.env import setup_world   # noqa: E402
from tampura_environments.panda_utils.panda_env_utils import setup_robot, create_ycb   # noqa: E402

robot, client = setup_robot(vis=False)
setup_world(robot, client, [], [])
cup = create_ycb('d_cups_ud', client=client, use_concave=True)
p.resetBasePositionAndOrientation(cup, [0.6727, 0.2161, 0.0493], [0.0, 0.0, -0.8249, 0.5653])
print('collision shapes (hulls):', len(p.getCollisionShapeData(cup, -1)))
lo, hi = p.getAABB(cup)
cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
print(f'aabb z {1e3 * lo[2]:.1f} to {1e3 * hi[2]:.1f} mm, half-widths {1e3 * (hi[0] - lo[0]) / 2:.1f} '
      f'{1e3 * (hi[1] - lo[1]) / 2:.1f} mm')
R = 0.09
for z in np.arange(0.002, hi[2], 0.004):
    starts, ends = [], []
    for k in range(36):
        a = 2 * math.pi * k / 36
        starts.append([cx + R * math.cos(a), cy + R * math.sin(a), z])
        ends.append([cx, cy, z])
    hits = p.rayTestBatch(starts, ends)
    r = [R * (1 - h[2]) for h in hits if h[0] == cup]
    if r:
        print(f'z {1e3 * z:5.1f} mm: outer radius {1e3 * min(r):5.1f} to {1e3 * max(r):5.1f} mm '
              f'(median {1e3 * float(np.median(r)):5.1f}, {len(r)} of 36 bearings hit)')
# the finger links at the full open, the hand top down over the cup's axis
model = robot_utils.resolve_robot_model(robot.body, client._client)
for fj in model.finger_joints:
    p.resetJointState(robot.body, fj, task_spec.FINGER_OPEN)
a, b = (p.getAABB(robot.body, fj) for fj in model.finger_joints)
print('finger link aabbs at q 40 mm (hand at home):', [[round(1e3 * x, 1) for x in v] for v in a],
      [[round(1e3 * x, 1) for x in v] for v in b])
