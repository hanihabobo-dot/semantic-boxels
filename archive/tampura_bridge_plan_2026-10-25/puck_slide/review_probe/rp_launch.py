"""Review probe (REVIEW.md), a copy of the author's probe_puck_physics2.py trial
with extra logging.  Read only: the same set-up and run line as the author's
probes (their venv, PYTHONPATH to their trees, PYTHONDONTWRITEBYTECODE=1, cwd
/root/ps_probe); every write is to the probe's own worlds.

Question: ARGUMENT.md 4.1 and 4.3 propose to obtain the launch speed from "the
contacting link's speed at the last pad contact, through a calibration of puck
launch against link speed", calibrated "on our table with our own bodies".  With
THEIR stroke (the only stroke that exists), how well does the link speed at the
last contact predict the puck's launch speed across frictions, efforts and a
mass outside the author's probed range (0.1 kg, the mass of our cubes), and how
well does the tool tip's position at separation locate the puck's separation
point (which the estimator also needs and which the author's probe read from
the simulator)?  Plus: are repeated trials in fresh worlds identical
(determinism, so that the author's "launch sd" across frictions is a friction
effect and not noise)?

Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=... <venv python> rp_launch.py <out.json>
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


def link_point_velocity(c, body, link, point):
    ls = c.getLinkState(body, link, computeLinkVelocity=1)
    com = np.array(ls[0])
    v = np.array(ls[6])
    w = np.array(ls[7])
    return v + np.cross(w, np.array(point) - com), v


def trial(world, pose, joint_path, effort):
    c = world.client
    body = int(world.robot)
    arm = world.robot.get_group_joints(ARM_GROUP, client=c)
    real = world.objects[0]
    tl = pbu.link_from_name(world.robot, "panda_tool_tip", client=c)
    pbu.set_joint_positions(world.robot, arm, joint_path[0], client=c)
    pbu.set_pose(real, pose, client=c)
    pbu.set_joint_positions(world.robot, arm, joint_path[0], client=c)
    controller = follow_path(world.robot, arm, joint_path, lead_step=effort,
                             max_force=None, client=c)
    state = {"prev": [], "events": [], "step": 0, "first_contact": None}

    def tick():
        state["step"] += 1
        cps = c.getContactPoints(bodyA=real, bodyB=body)
        if cps and state["first_contact"] is None:
            state["first_contact"] = state["step"]
        if state["prev"] and not cps:
            # contact ended this step: log the puck, the last contacting
            # link (from the previous step's list) and the tool tip
            last = max(state["prev"], key=lambda cp: cp[9])   # largest normal force
            link = last[4]
            point_on_robot = last[6]
            v_pt, v_com = link_point_velocity(c, body, link, point_on_robot)
            tls = c.getLinkState(body, tl, computeLinkVelocity=1)
            ppos = c.getBasePositionAndOrientation(real)[0]
            pv = c.getBaseVelocity(real)[0]
            state["events"].append(dict(
                step=state["step"], link=link,
                puck_x=ppos[0], puck_y=ppos[1],
                puck_speed=float(np.linalg.norm(pv[:2])),
                link_com_speed=float(np.linalg.norm(v_com[:2])),
                contact_point_speed=float(np.linalg.norm(v_pt[:2])),
                tooltip_x=tls[0][0], tooltip_y=tls[0][1],
                tooltip_speed=float(np.linalg.norm(np.array(tls[6])[:2]))))
        state["prev"] = cps

    for _ in iter(pbu.simulate_controller(controller, client=c)):
        tick()
    for _ in range(2000):
        c.stepSimulation()
        tick()
    final = pbu.get_pose(real, client=c)
    ev = state["events"]
    rec = dict(effort=effort, x=final[0][0], y=final[0][1],
               off_table=bool(final[0][2] < 0),
               in_goal=bool(ps.test_in(final, GOAL)),
               n_separations=len(ev), first_contact_step=state["first_contact"],
               events=ev)
    if ev:
        last = ev[-1]
        d_slide = math.hypot(final[0][0] - last["puck_x"], final[0][1] - last["puck_y"])
        rec.update(sep_speed=last["puck_speed"], d_slide=d_slide,
                   ratio_puck_to_link_com=last["puck_speed"] / last["link_com_speed"]
                   if last["link_com_speed"] > 1e-6 else None,
                   ratio_puck_to_contact_point=last["puck_speed"] / last["contact_point_speed"]
                   if last["contact_point_speed"] > 1e-6 else None,
                   ratio_puck_to_tooltip=last["puck_speed"] / last["tooltip_speed"]
                   if last["tooltip_speed"] > 1e-6 else None,
                   sep_offset_x=last["puck_x"] - last["tooltip_x"])
    return rec


def main():
    pose0 = ps.PUCK_START_POSE
    tp_goal = list(ps.REGION_POSES[GOAL][0][:2])
    w = make_world(0.10)
    _, jp, _ = ps.shoot_controller(None, w, w.objects, pose0, tp_goal, pc_steps=1, effort=0.005)
    out = {"joint_path_len": len(jp), "L1": [], "L2": [], "L3": []}
    # L1: frictions x efforts, mass 1 (theirs)
    for mu in (0.05, 0.10, 0.15):
        for e in (0.010, 0.015, 0.020, 0.030):
            w = make_world(mu)
            r = trial(w, pose0, jp, e)
            r.update(mu=mu, mass=1.0)
            out["L1"].append(r)
            print(f"L1 mu={mu:.3f} e={e:.3f} x={r['x']:.4f} nsep={r['n_separations']} "
                  f"v_sep={r.get('sep_speed', float('nan')):.4f} "
                  f"puck/link_com={r.get('ratio_puck_to_link_com') or float('nan'):.4f} "
                  f"puck/contact_pt={r.get('ratio_puck_to_contact_point') or float('nan'):.4f} "
                  f"puck/tooltip={r.get('ratio_puck_to_tooltip') or float('nan'):.4f} "
                  f"offset_x={r.get('sep_offset_x', float('nan')):.4f}", flush=True)
    # L2: mass 0.1 kg (our cubes' class) against 1 kg, mu 0.10
    for e in (0.010, 0.020):
        for mass in (0.1, 1.0):
            w = make_world(0.10)
            w.client.changeDynamics(w.objects[0], -1, mass=mass)
            r = trial(w, pose0, jp, e)
            r.update(mu=0.10, mass=mass)
            out["L2"].append(r)
            print(f"L2 e={e:.3f} mass={mass:.1f} v_sep={r.get('sep_speed', float('nan')):.4f} "
                  f"nsep={r['n_separations']} puck/link_com={r.get('ratio_puck_to_link_com') or float('nan'):.4f} "
                  f"puck/contact_pt={r.get('ratio_puck_to_contact_point') or float('nan'):.4f} "
                  f"x={r['x']:.4f}", flush=True)
    # L3: three fresh-world repeats of one cell (determinism)
    for rep in range(3):
        w = make_world(0.10)
        r = trial(w, pose0, jp, 0.010)
        r.update(mu=0.10, mass=1.0, rep=rep)
        out["L3"].append(r)
        print(f"L3 rep={rep} x={r['x']:.6f} v_sep={r.get('sep_speed', float('nan')):.6f}", flush=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
