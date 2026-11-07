"""Check for probe_slide_track.py (2026-11-06): its S1 rays found the puck's
top hidden from the D4 eye at every render step and S3 rendered no puck pixel
at rest.  Is that the arm (a real occlusion) or an artifact (ray start,
segmentation id)?  One trial at mu 0.10, effort 0.010, as in S1; then, at
rest: the first hit of rays from the eye to the puck, the robot links nearest
the ray, the ids a render sees; then the same with the arm set to
DEFAULT_ARM_POS (a write to the probe's own world).  Read only otherwise.
"""
import math
import sys

import numpy as np
import pybullet as p

import tampura_environments.puck_slide.env as ps
import tampura_environments.panda_utils.pb_utils as pbu
from tampura_environments.panda_utils.panda_env_utils import ARM_GROUP
from tampura_environments.panda_utils.primitives import follow_path

EYE_POSITION = (0.17861445248126984, 0.048803217709064484, 0.5883188247680664)
EYE_TARGET = (3.285824775695801, -0.16977983713150024, -3.322878360748291)
EYE_UP = (0.0, 0.0, 1.0)
EYE_FOV_DEG = 49.13434264120263
W, H = 640, 480


def make_world(mu):
    w = ps.setup_puck_world(pose=ps.PUCK_START_POSE, friction=mu, vis=False)
    for b in w.objects[1:]:
        w.client.removeBody(b)
    w.objects = w.objects[:1]
    return w


def look(c, robot, real, label):
    pos = c.getBasePositionAndOrientation(real)[0]
    top = np.array([pos[0], pos[1], pos[2] + 0.02])
    eye = np.array(EYE_POSITION)
    d = top - eye
    hit = c.rayTest(eye.tolist(), (top + 0.01 * d / np.linalg.norm(d)).tolist())[0]
    print(f"[{label}] puck at {pos[0]:.4f} {pos[1]:.4f} {pos[2]:.4f}; ray first hit body {hit[0]} "
          f"link {hit[1]} fraction {hit[2]:.4f} at {tuple(round(v, 4) for v in hit[3])} "
          f"(robot {robot}, puck {real})")
    n = c.getNumJoints(robot)
    rows = []
    for j in range(-1, n):
        lp = np.array(c.getBasePositionAndOrientation(robot)[0] if j < 0 else c.getLinkState(robot, j)[0])
        s = np.clip(np.dot(lp - eye, d) / np.dot(d, d), 0, 1)
        dist = np.linalg.norm(eye + s * d - lp)
        name = "base" if j < 0 else c.getJointInfo(robot, j)[12].decode()
        rows.append((dist, j, name, lp, s))
    rows.sort()
    for dist, j, name, lp, s in rows[:4]:
        print(f"   link {j} {name} at {tuple(round(v, 3) for v in lp)}: {dist * 1000:.0f} mm from the ray at s {s:.2f}")
    view = c.computeViewMatrix(EYE_POSITION, EYE_TARGET, EYE_UP)
    proj = c.computeProjectionMatrixFOV(EYE_FOV_DEG, W / H, 0.02, 5.0)
    _w, _h, _rgb, _depth, seg = c.getCameraImage(W, H, view, proj, renderer=p.ER_TINY_RENDERER)
    seg = np.asarray(seg).reshape(H, W)
    ids, counts = np.unique(seg, return_counts=True)
    print(f"   render: ids {dict(zip(ids.tolist(), counts.tolist()))}")
    obj = seg & ((1 << 24) - 1)
    print(f"   puck pixels (low 24 bits == puck): {int((obj == real).sum())}")


def main():
    pose0 = ps.PUCK_START_POSE
    tp_goal = list(ps.REGION_POSES[ps.GOAL_OBJECTS[0]][0][:2])
    w = make_world(0.10)
    _, jp, _ = ps.shoot_controller(None, w, w.objects, pose0, tp_goal, pc_steps=1, effort=0.005)
    w = make_world(0.10)
    c, robot, real = w.client, int(w.robot), w.objects[0]
    arm = w.robot.get_group_joints(ARM_GROUP, client=c)
    print(f"bodies: {[(i, c.getBodyInfo(c.getBodyUniqueId(i))[1].decode()) for i in range(c.getNumBodies())]}")
    look(c, robot, real, "as built (arm at DEFAULT_ARM_POS)")
    pbu.set_joint_positions(w.robot, arm, jp[0], client=c)
    pbu.set_pose(real, pose0, client=c)
    pbu.set_joint_positions(w.robot, arm, jp[0], client=c)
    look(c, robot, real, "arm at the stroke start")
    ctrl = follow_path(w.robot, arm, jp, lead_step=0.010, max_force=None, client=c)
    for _ in iter(pbu.simulate_controller(ctrl, client=c)):
        pass
    for _ in range(2000):
        c.stepSimulation()
    look(c, robot, real, "rest, arm at the stroke end")
    pbu.set_joint_positions(w.robot, arm, ps.DEFAULT_ARM_POS, client=c)
    look(c, robot, real, "rest, arm set to DEFAULT_ARM_POS")


if __name__ == "__main__":
    main()
