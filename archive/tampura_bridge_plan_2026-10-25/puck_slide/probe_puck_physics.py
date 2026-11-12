"""Read-only probe of TAMPURA's puck_slide world (2026-11-06, ARGUMENT.md 4).

Run in their venv from /root/ps_probe (env_configs symlinked there):
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/root/tampura-work/tampura:/root/tampura-work/tampura_environments \
  /root/tampura-work/.venv/bin/python <this file> <out.json>

It imports their puck_slide module, builds worlds with their own
setup_puck_world in DIRECT mode and replays their push trial.  The trial
below mirrors their code line for line (shoot_controller's per-trial resets,
env.py:496-503, and follow_joint_path, env.py:384-415) so that the tool tip's
and the puck's velocities can be logged; the joint path comes from their own
shoot_controller (plan_workspace_motion).  Nothing is written under
/root/tampura-work; the probe's worlds are its own, so the resets below are
probe control, not an episode.

Experiments:
  E1  slide law: puck friction x effort, single trial toward goal0, no ghosts.
  E2  ghost load: the same trial with their 19 ghost pucks co-located vs removed.
  E3  their nudge: effort 0.005 toward the ik centre + (0, 0.2), per friction.
  E4  their 5-trial effort correction with an exact friction (median of one).
  E5  reach of their push geometry along the slab.
"""
import json
import math
import random
import sys
import time

import numpy as np

import tampura_environments.puck_slide.env as ps
import tampura_environments.panda_utils.pb_utils as pbu
from tampura_environments.panda_utils.panda_env_utils import ARM_GROUP
from tampura_environments.panda_utils.primitives import follow_path

OUT = sys.argv[1]
random.seed(0)
np.random.seed(0)

FRICTIONS = [0.05, 0.075, 0.10, 0.125, 0.15]
EFFORTS = [0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04]
GOAL = ps.GOAL_OBJECTS[0]
IK = f"{ps.OBJ}ik"
G = 9.8                      # their gravity, env.py:258


def make_world(mu, ghosts):
    w = ps.setup_puck_world(pose=ps.PUCK_START_POSE, friction=mu, vis=False)
    if not ghosts:
        for b in w.objects[1:]:
            w.client.removeBody(b)
        w.objects = w.objects[:1]
    return w


def tool_link(world):
    return pbu.link_from_name(world.robot, "panda_tool_tip", client=world.client)


def trial(world, pucks, pose, joint_path, effort):
    """One push trial as shoot_controller runs it (resets, then
    follow_joint_path), with velocity and contact logging."""
    c = world.client
    body = int(world.robot)
    arm = world.robot.get_group_joints(ARM_GROUP, client=c)
    real = pucks[0]
    pbu.set_joint_positions(world.robot, arm, joint_path[0], client=c)   # env.py:496-498
    for pk in pucks:                                                     # env.py:500-501
        pbu.set_pose(pk, pose, client=c)
    # follow_joint_path, env.py:387-409
    pbu.set_joint_positions(world.robot, arm, joint_path[0], client=c)
    controller = follow_path(world.robot, arm, joint_path, lead_step=effort,
                             max_force=None, client=c)
    tl = tool_link(world)
    ee_vmax = 0.0
    puck_vmax = 0.0
    steps = 0
    in_contact = False
    last_sep = None            # (step, x, y, speed) at the last contact end
    ctrl_steps = 0
    for _ in iter(pbu.simulate_controller(controller, client=c)):
        ctrl_steps += 1
        steps += 1
        ls = c.getLinkState(body, tl, computeLinkVelocity=1)
        ee_vmax = max(ee_vmax, float(np.linalg.norm(ls[6][:2])))
        v = c.getBaseVelocity(real)[0]
        sp = float(np.linalg.norm(v[:2]))
        puck_vmax = max(puck_vmax, sp)
        touching = len(c.getContactPoints(bodyA=real, bodyB=body)) > 0
        if in_contact and not touching:
            pos = c.getBasePositionAndOrientation(real)[0]
            last_sep = (steps, pos[0], pos[1], sp)
        in_contact = touching
    for _ in range(2000):                                                # env.py:406-409
        c.stepSimulation()
        steps += 1
        v = c.getBaseVelocity(real)[0]
        sp = float(np.linalg.norm(v[:2]))
        puck_vmax = max(puck_vmax, sp)
        touching = len(c.getContactPoints(bodyA=real, bodyB=body)) > 0
        if in_contact and not touching:
            pos = c.getBasePositionAndOrientation(real)[0]
            last_sep = (steps, pos[0], pos[1], sp)
        in_contact = touching
    final = pbu.get_pose(real, client=c)
    v_end = c.getBaseVelocity(real)[0]
    rec = dict(
        effort=effort,
        x=final[0][0], y=final[0][1], z=final[0][2],
        dx=final[0][0] - pose[0][0], dy=final[0][1] - pose[0][1],
        ctrl_steps=ctrl_steps,
        ee_speed_max=ee_vmax,
        puck_speed_max=puck_vmax,
        speed_at_end=float(np.linalg.norm(v_end[:2])),
        in_goal=bool(ps.test_in(final, GOAL)),
        in_ik=bool(ps.test_in(final, IK)),
        off_table=bool(final[0][2] < 0),
        touching_at_end=in_contact,
    )
    if last_sep is not None:
        s_step, sx, sy, sv = last_sep
        d_slide = math.hypot(final[0][0] - sx, final[0][1] - sy)
        rec.update(sep_step=s_step, sep_x=sx, sep_speed=sv, d_slide=d_slide,
                   mu_eff_from_slide=(sv * sv / (2 * G * d_slide)) if d_slide > 1e-4 else None)
    return rec


def their_joint_path(world, pose, target_point, effort=0.005):
    _, joint_path, _ = ps.shoot_controller(None, world, world.objects[:1], pose,
                                           target_point, pc_steps=1, effort=effort)
    return joint_path


def main():
    t0 = time.time()
    out = {"frictions": FRICTIONS, "efforts": EFFORTS,
           "puck_start": list(ps.PUCK_START_POSE[0]),
           "goal_target": list(ps.REGION_POSES[GOAL][0][:2])}
    tp_goal = list(ps.REGION_POSES[GOAL][0][:2])
    pose0 = ps.PUCK_START_POSE

    # Rest height of the puck on the slab (their start pose has z 0.06).
    w = make_world(0.10, ghosts=False)
    c = w.client
    pbu.set_pose(w.objects[0], pose0, client=c)
    for _ in range(480):
        c.stepSimulation()
    rest = pbu.get_pose(w.objects[0], client=c)
    out["rest_pose_after_480_steps"] = [list(rest[0]), list(rest[1])]
    # Their joint path toward goal0 from the start pose (shoot_controller geometry).
    jp_goal = their_joint_path(w, pose0, tp_goal)
    out["joint_path_len_goal"] = len(jp_goal)
    out["time_step"] = c.getPhysicsEngineParameters()["fixedTimeStep"]
    out["solver_iterations"] = c.getPhysicsEngineParameters()["numSolverIterations"]
    out["robot_link_lateral_friction"] = {
        name: c.getDynamicsInfo(int(w.robot), pbu.link_from_name(w.robot, name, client=c))[1]
        for name in ("panda_leftfinger", "panda_rightfinger", "panda_hand")}

    # E1: slide law.
    e1 = []
    for mu in FRICTIONS:
        w = make_world(mu, ghosts=False)
        for e in EFFORTS:
            r = trial(w, w.objects, pose0, jp_goal, e)
            r["mu"] = mu
            e1.append(r)
            print(f"E1 mu={mu:.3f} e={e:.3f} x={r['x']:.4f} y={r['y']:.4f} "
                  f"v_sep={r.get('sep_speed', float('nan')):.4f} "
                  f"mu_eff={r.get('mu_eff_from_slide')} goal={r['in_goal']} "
                  f"off={r['off_table']} v_end={r['speed_at_end']:.4f}", flush=True)
    out["E1"] = e1

    # E2: ghost load (their t=0 world: 19 ghosts at the start pose with
    # frictions from their prior draw, env.py:353-361).
    e2 = []
    for e in (0.01, 0.02, 0.03):
        for ghosts in (False, True):
            w = make_world(0.10, ghosts=ghosts)
            r = trial(w, w.objects, pose0, jp_goal, e)
            r.update(mu=0.10, ghosts=ghosts)
            e2.append(r)
            print(f"E2 e={e:.3f} ghosts={ghosts} x={r['x']:.5f} y={r['y']:.5f} "
                  f"ee_vmax={r['ee_speed_max']:.4f}", flush=True)
    out["E2"] = e2

    # E3: their nudge, effort 0.005, toward the ik centre + (0, 0.2)
    # (nudge_execute_fn, env.py:611-630, one trial instead of five).
    tp_n = list(ps.REGION_POSES[IK][0][:2])
    tp_n = [tp_n[0] + 0.0, tp_n[1] + 0.2]
    w = make_world(0.10, ghosts=False)
    jp_n = their_joint_path(w, pose0, tp_n)
    e3 = []
    for mu in FRICTIONS:
        w = make_world(mu, ghosts=False)
        r = trial(w, w.objects, pose0, jp_n, 0.005)
        r["mu"] = mu
        e3.append(r)
        print(f"E3 mu={mu:.3f} x={r['x']:.4f} y={r['y']:.4f} "
              f"disp={math.hypot(r['dx'], r['dy']):.4f}", flush=True)
    out["E3"] = e3
    out["E3_target"] = tp_n

    # E4: their 5-trial correction (env.py:493-509) with an exact friction:
    # the median over one puck is the real puck's x.
    e4 = []
    for mu in FRICTIONS:
        w = make_world(mu, ghosts=False)
        effort = ps.DEFAULT_EFFORT
        hist = []
        for step in range(ps.SHOOT_CONTROLLER_PC):
            r = trial(w, w.objects, pose0, jp_goal, effort)
            hist.append(dict(effort=effort, x=r["x"], in_goal=r["in_goal"],
                             off_table=r["off_table"]))
            effort = effort - (r["x"] - tp_goal[0]) * 0.01                # KP, env.py:460, 509
        replay = trial(w, w.objects, pose0, jp_goal, effort)              # what update() replays
        e4.append(dict(mu=mu, trials=hist, returned_effort=effort,
                       replay_at_returned_effort_x=replay["x"],
                       last_trial_x=hist[-1]["x"], last_trial_in_goal=hist[-1]["in_goal"]))
        print(f"E4 mu={mu:.3f} " + " ".join(f"[{h['effort']:.4f}->{h['x']:.3f}]" for h in hist)
              + f" e5={effort:.4f} replay_x={replay['x']:.3f}", flush=True)
    out["E4"] = e4

    # E5: reach of their push geometry with the puck at x along the slab.
    e5 = []
    w = make_world(0.10, ghosts=False)
    for x in (0.39, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 1.0):
        pose = pbu.Pose(pbu.Point(x=x, z=rest[0][2]))
        ok = 0
        for rep in range(3):
            jp = their_joint_path(w, pose, tp_goal)
            ok += int(bool(jp))
        e5.append(dict(x=x, found=ok, of=3))
        print(f"E5 x={x:.2f} push path found {ok}/3", flush=True)
    out["E5"] = e5

    out["wall_s"] = time.time() - t0
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {OUT} in {out['wall_s']:.1f} s")


if __name__ == "__main__":
    main()
