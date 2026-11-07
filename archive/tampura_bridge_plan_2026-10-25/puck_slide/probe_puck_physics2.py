"""Second read-only probe of TAMPURA's puck_slide world (2026-11-06,
ARGUMENT.md 4).  Same set-up and run line as probe_puck_physics.py.

  F1  damping: the same single trial with the real puck's linear and angular
      damping set to 0 in the probe's own world; if pure Coulomb then
      recovers mu_eff = 0.1 mu, the bias of the Coulomb model in
      probe_analysis.py B is the engine's default damping.
  F2  mass: the launch speed and slide with the puck's mass 0.5, 1 and 2 kg
      (theirs is 1, env.py:73); if the launch speed moves < 1 %, an
      estimator built on the launch speed needs no mass model.
Every write below is to the probe's own world (changeDynamics, set_pose),
never to their tree.
"""
import json
import math
import random
import sys

import numpy as np

import tampura_environments.puck_slide.env as ps
import tampura_environments.panda_utils.pb_utils as pbu
from tampura_environments.panda_utils.panda_env_utils import ARM_GROUP
from tampura_environments.panda_utils.primitives import follow_path

OUT = sys.argv[1]
random.seed(0)
np.random.seed(0)
G = 9.8
GOAL = ps.GOAL_OBJECTS[0]


def make_world(mu):
    w = ps.setup_puck_world(pose=ps.PUCK_START_POSE, friction=mu, vis=False)
    for b in w.objects[1:]:
        w.client.removeBody(b)
    w.objects = w.objects[:1]
    return w


def trial(world, pose, joint_path, effort):
    c = world.client
    body = int(world.robot)
    arm = world.robot.get_group_joints(ARM_GROUP, client=c)
    real = world.objects[0]
    pbu.set_joint_positions(world.robot, arm, joint_path[0], client=c)
    pbu.set_pose(real, pose, client=c)
    pbu.set_joint_positions(world.robot, arm, joint_path[0], client=c)
    controller = follow_path(world.robot, arm, joint_path, lead_step=effort,
                             max_force=None, client=c)
    in_contact, last_sep = False, None

    def tick():
        nonlocal in_contact, last_sep
        touching = len(c.getContactPoints(bodyA=real, bodyB=body)) > 0
        if in_contact and not touching:
            pos = c.getBasePositionAndOrientation(real)[0]
            v = c.getBaseVelocity(real)[0]
            last_sep = (pos[0], pos[1], float(np.linalg.norm(v[:2])))
        in_contact = touching

    for _ in iter(pbu.simulate_controller(controller, client=c)):
        tick()
    for _ in range(2000):
        c.stepSimulation()
        tick()
    final = pbu.get_pose(real, client=c)
    sx, sy, sv = last_sep
    d_slide = math.hypot(final[0][0] - sx, final[0][1] - sy)
    return dict(x=final[0][0], y=final[0][1], off_table=bool(final[0][2] < 0),
                in_goal=bool(ps.test_in(final, GOAL)), sep_speed=sv, d_slide=d_slide,
                mu_eff_coulomb=sv * sv / (2 * G * d_slide))


def main():
    pose0 = ps.PUCK_START_POSE
    tp_goal = list(ps.REGION_POSES[GOAL][0][:2])
    w = make_world(0.10)
    _, jp, _ = ps.shoot_controller(None, w, w.objects, pose0, tp_goal, pc_steps=1, effort=0.005)
    out = {"F1": [], "F2": []}
    for mu in (0.05, 0.10, 0.15):
        for e in (0.010, 0.015, 0.020):
            for damp in (True, False):
                w = make_world(mu)
                if not damp:
                    w.client.changeDynamics(w.objects[0], -1, linearDamping=0.0, angularDamping=0.0)
                r = trial(w, pose0, jp, e)
                r.update(mu=mu, effort=e, default_damping=damp,
                         ratio=r["mu_eff_coulomb"] / (0.1 * mu))
                out["F1"].append(r)
                print(f"F1 mu={mu:.3f} e={e:.3f} damping={'default' if damp else 'zero'} "
                      f"x={r['x']:.4f} off={r['off_table']} v_sep={r['sep_speed']:.4f} "
                      f"coulomb mu_eff/(0.1 mu)={r['ratio']:.4f}", flush=True)
    for e in (0.010, 0.020):
        for mass in (0.5, 1.0, 2.0):
            w = make_world(0.10)
            w.client.changeDynamics(w.objects[0], -1, mass=mass)
            r = trial(w, pose0, jp, e)
            r.update(mu=0.10, effort=e, mass=mass)
            out["F2"].append(r)
            print(f"F2 e={e:.3f} mass={mass:.1f} v_sep={r['sep_speed']:.4f} x={r['x']:.4f} "
                  f"d_slide={r['d_slide']:.4f}", flush=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
