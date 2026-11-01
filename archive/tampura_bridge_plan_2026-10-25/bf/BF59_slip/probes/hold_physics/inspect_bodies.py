"""BF#59 hold physics: the dynamics of the pads and the die as the bridge world has them
(their world, D9's values), and the die hull's geometry.  Print only."""
import os
import sys

import numpy as np
import pybullet as p

REPO = os.environ.get('SB_REPO', '/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels')
sys.path.insert(0, REPO)
import robot_utils                                   # noqa: E402
from tampura_bridge import task_spec                 # noqa: E402
from tampura_environments.find_dice.env import setup_world   # noqa: E402
from tampura_environments.panda_utils.panda_env_utils import setup_robot, create_ycb   # noqa: E402

robot, client = setup_robot(vis=False)
world = setup_world(robot, client, [], [])
rb = robot.body
model = robot_utils.resolve_robot_model(rb, 0)
print('fingers', model.finger_joints, 'ee', model.ee_link)
for fj in model.finger_joints:
    p.changeDynamics(rb, fj, lateralFriction=task_spec.PAD_LATERAL_FRICTION)
    di = p.getDynamicsInfo(rb, fj)
    print('pad', fj, 'mass', di[0], 'lat', di[1], 'inertia', di[2], 'rest', di[5], 'roll', di[6],
          'spin', di[7], 'damp', di[8], 'stiff', di[9], 'margin', di[11] if len(di) > 11 else None)
    for s in p.getCollisionShapeData(rb, fj):
        print('   shape', s[2], s[3], s[4][-60:] if isinstance(s[4], bytes) else s[4], 'pos', s[5])
print('engine', p.getPhysicsEngineParameters())
body = create_ycb('dice', client=client, use_concave=True)
p.changeDynamics(body, -1, mass=task_spec.CLASS_MASS_KG['dice'],
                 localInertiaDiagonal=task_spec.CLASS_INERTIA_DIAG['dice'],
                 lateralFriction=task_spec.OBJECT_LATERAL_FRICTION)
di = p.getDynamicsInfo(body, -1)
print('die', 'mass', di[0], 'lat', di[1], 'inertia', di[2], 'local inertial pos', di[3], 'rest', di[5],
      'roll', di[6], 'spin', di[7], 'damp', di[8], 'stiff', di[9], 'margin', di[11] if len(di) > 11 else None)
print('declared inertia', task_spec.CLASS_INERTIA_DIAG['dice'], 'extents', task_spec.CLASS_EXTENTS['dice'])
m = task_spec.CLASS_MASS_KG['dice']
s = task_spec.CLASS_EXTENTS['dice'][0]
print('solid cube inertia m s^2/6', m * s * s / 6)
for sh in p.getCollisionShapeData(body, -1):
    print('die shape', sh[2], sh[3], sh[4], 'pos', sh[5], 'orn', sh[6])
p.resetBasePositionAndOrientation(body, [0, 0, 0.5], [0, 0, 0, 1])
lo, hi = p.getAABB(body)
print('die AABB at identity', np.round(lo, 5), np.round(hi, 5), 'size mm', np.round(1e3 * (np.array(hi) - np.array(lo)), 2))
print('base pos', p.getBasePositionAndOrientation(body)[0])
mesh = p.getMeshData(body, -1)
v = np.asarray(mesh[1])
print('hull vertices', len(v), 'min', np.round(1e3 * v.min(0), 2), 'max', np.round(1e3 * v.max(0), 2))
# how round is it: the support distance along directions at angles from the x face normal
c = (v.min(0) + v.max(0)) / 2
for ang in (0, 15, 30, 45):
    d = np.array([np.cos(np.radians(ang)), np.sin(np.radians(ang)), 0])
    print(f'support along {ang:2d} deg in xy: {1e3 * np.max((v - c) @ d):.2f} mm (sharp cube {1e3 * s / 2 * (abs(np.cos(np.radians(ang))) + abs(np.sin(np.radians(ang)))):.2f})')
for ang in (0, 15, 30, 45):
    d = np.array([np.cos(np.radians(ang)), 0, np.sin(np.radians(ang))])
    print(f'support along {ang:2d} deg in xz: {1e3 * np.max((v - c) @ d):.2f} mm')
# the face: vertices within 0.3 mm of the +x support plane
xmax = (v - c)[:, 0].max()
face = (v - c)[(v - c)[:, 0] > xmax - 0.0003]
print('+x face vertices', len(face), 'y range', np.round(1e3 * face[:, 1].min(), 2), np.round(1e3 * face[:, 1].max(), 2),
      'z range', np.round(1e3 * face[:, 2].min(), 2), np.round(1e3 * face[:, 2].max(), 2))
face = (v - c)[(v - c)[:, 0] > xmax - 0.001]
print('+x within 1 mm', len(face), 'y range', np.round(1e3 * face[:, 1].min(), 2), np.round(1e3 * face[:, 1].max(), 2),
      'z range', np.round(1e3 * face[:, 2].min(), 2), np.round(1e3 * face[:, 2].max(), 2))
print('centre of hull vs base (mm)', np.round(1e3 * c, 2))
# finger pad geometry: finger link AABB and inner face position vs joint value
for q in (0.0, 0.0089, 0.0102):
    for fj in model.finger_joints:
        p.resetJointState(rb, fj, q)
    ls = p.getLinkState(rb, model.ee_link, computeForwardKinematics=True)
    R = np.asarray(p.getMatrixFromQuaternion(ls[1])).reshape(3, 3)
    for fj in model.finger_joints:
        md = p.getMeshData(rb, fj) if False else None
        lo, hi = p.getAABB(rb, fj)
    # closest distance between the two finger links
    cp = p.getClosestPoints(rb, rb, 0.1, linkIndexA=model.finger_joints[0], linkIndexB=model.finger_joints[1])
    dmin = min(c[8] for c in cp) if cp else None
    print(f'finger q {1e3 * q:.1f} mm: closest distance between finger links {None if dmin is None else round(1e3 * dmin, 3)} mm')
