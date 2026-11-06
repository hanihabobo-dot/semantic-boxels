"""Fourth read-only probe (2026-11-06), after probe_slide_track.py found
that the slide follows the damped Coulomb law at launches of 0.28 to 0.37
m/s but not at 0.55 m/s, and that neither the D4 eye nor the wrist camera
sees the puck while the arm holds the stroke's end pose.  Same set-up and
run line as probe_slide_track.py, whose functions it imports.

  SL  where between effort 0.020 (0.37 m/s) and 0.030 (0.55 m/s) the free
      slide stops following the law, and why: per trial the law fitted to
      the on-slab track after the last robot contact (free, and with the
      true mu_eff), the forward check from the separation event, the puck's
      support contacts (contact points with any body but the robot) and its
      height range after separation.
  V   the D4 eye with the arm at DEFAULT_ARM_POS (as built): the puck set
      at rest at x 0.40 to 1.30 on y 0 (a write to the probe's own world):
      pixels, and the stand-in centre's static error (a check of the view
      extent 4.2 computed by arithmetic, and of the stand-in's noise).
  R   the retreat: after the test push's stroke (effort 0.010) the arm is
      driven to DEFAULT_ARM_POS by their waypoint controller (follow_path,
      lead times 0.05 and 0.10 s, the stroke's own controller family) while
      the puck slides; the D4 eye renders every 12 steps.  When is the
      puck first fully seen, and how much of its slide is left then?
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_slide_track as pst  # noqa: E402

import pybullet as p  # noqa: E402
import tampura_environments.puck_slide.env as ps  # noqa: E402
import tampura_environments.panda_utils.pb_utils as pbu  # noqa: E402
from tampura_environments.panda_utils.panda_env_utils import ARM_GROUP  # noqa: E402
from tampura_environments.panda_utils.primitives import follow_path  # noqa: E402

CELLS = [(mu, e) for mu in (0.10, 0.125, 0.15) for e in (0.020, 0.022, 0.024, 0.026, 0.028, 0.030)]
VIEW_X = (0.40, 0.55, 0.70, 0.80, 0.90, 1.00, 1.10, 1.19, 1.30)
RETREAT = [(mu, lead) for mu in (0.05, 0.10, 0.15) for lead in (0.05, 0.10)]


def views(c):
    return (c.computeViewMatrix(pst.EYE_POSITION, pst.EYE_TARGET, pst.EYE_UP),
            c.computeProjectionMatrixFOV(pst.EYE_FOV_DEG, pst.EYE_W / pst.EYE_H, pst.EYE_NEAR, pst.EYE_FAR))


def record_sl(world, pose, joint_path, effort):
    c = world.client
    body = int(world.robot)
    arm = world.robot.get_group_joints(ARM_GROUP, client=c)
    real = world.objects[0]
    pbu.set_joint_positions(world.robot, arm, joint_path[0], client=c)
    pbu.set_pose(real, pose, client=c)
    pbu.set_joint_positions(world.robot, arm, joint_path[0], client=c)
    controller = follow_path(world.robot, arm, joint_path, lead_step=effort, max_force=None, client=c)
    L = {k: [] for k in ("x", "y", "z", "speed", "touch", "support", "vz")}

    def log():
        pos, _orn = c.getBasePositionAndOrientation(real)
        lin, _ang = c.getBaseVelocity(real)
        L["x"].append(pos[0])
        L["y"].append(pos[1])
        L["z"].append(pos[2])
        L["vz"].append(lin[2])
        L["speed"].append(float(math.hypot(lin[0], lin[1])))
        cps = c.getContactPoints(bodyA=real)
        L["touch"].append(any(cp[2] == body for cp in cps))
        L["support"].append(sum(1 for cp in cps if cp[2] != body))

    n_ctrl = 0
    for _ in iter(pbu.simulate_controller(controller, client=c)):
        n_ctrl += 1
        log()
    for _ in range(2000):
        c.stepSimulation()
        log()
    rec = {k: np.array(v) for k, v in L.items()}
    rec["n_ctrl"] = n_ctrl
    return rec


def part_sl(jp, pose0, out):
    for mu, e in CELLS:
        rec = record_sl(pst.make_world(mu), pose0, jp, e)
        truth = 0.1 * mu
        steps, end, fell = pst.schedule(rec, "early", 12)
        t = (np.array(steps) - steps[0]) * pst.DT
        px, py = rec["x"][steps], rec["y"][steps]
        rest = None if fell else (rec["x"][-1], rec["y"][-1])
        m_free, _a, _b, r_free = pst.fit_track(t, px, py, rest, 1e4)
        _m, _s1, _v1, r_fix = pst.fit_track(t, px, py, rest, 1e4, mu_fixed=truth)
        sep = int(np.nonzero(rec["touch"])[0][-1]) + 1
        v_sep = float(rec["speed"][sep])
        sl = slice(sep, max(end, sep + 1))
        sup = rec["support"][sl]
        cell = dict(mu=mu, effort=e, x_rest=float(rec["x"][-1]), fell=fell, sep=sep, v_sep=v_sep,
                    mu_free_rel_err=m_free / truth - 1.0,
                    free_fit_max_resid_mm=float(np.max(np.abs(r_free)) * 1000),
                    fixed_mu_rest_resid_mm=(float(r_fix[-1] * 1000) if rest is not None else None),
                    steps_without_support=int((sup == 0).sum()), support_min=int(sup.min()),
                    support_max=int(sup.max()),
                    z_range_mm=float((rec["z"][sl].max() - rec["z"][sl].min()) * 1000),
                    vz_max=float(np.abs(rec["vz"][sl]).max()))
        if not fell:
            d_act = math.hypot(rec["x"][-1] - rec["x"][sep], rec["y"][-1] - rec["y"][sep])
            d_pred = float(pst.slide(1e3, v_sep, truth))
            cell.update(sep_forward_err_mm=(d_act - d_pred) * 1000, sep_forward_err_rel=d_act / d_pred - 1.0)
        out["SL"].append(cell)
        print(f"SL mu={mu:.3f} e={e:.3f} v_sep={v_sep:.4f} x_rest={cell['x_rest']:.4f} fell={fell} "
              f"mu_free_err={cell['mu_free_rel_err']:+.4f} resid={cell['free_fit_max_resid_mm']:.2f}mm "
              f"fixed_rest={cell['fixed_mu_rest_resid_mm']} sep_fwd={cell.get('sep_forward_err_mm')} "
              f"rel={cell.get('sep_forward_err_rel')} airborne_steps={cell['steps_without_support']} "
              f"support={cell['support_min']}..{cell['support_max']} z_range={cell['z_range_mm']:.2f}mm "
              f"vz_max={cell['vz_max']:.4f}", flush=True)


def part_v(out):
    w = pst.make_world(0.10)
    c, real = w.client, w.objects[0]
    for _ in range(240):
        c.stepSimulation()          # the start pose is 1.5 cm inside the surface; let it settle
    z = c.getBasePositionAndOrientation(real)[0][2]
    view, proj = views(c)
    for x in VIEW_X:
        c.resetBasePositionAndOrientation(real, [x, 0.0, z], [0, 0, 0, 1])
        c.resetBaseVelocity(real, [0, 0, 0], [0, 0, 0])
        c.performCollisionDetection()
        r = pst.render_centre(c, real, view, proj)
        cell = dict(x=x, z=z, n_px=r.get("n_px", 0), border=r.get("border"),
                    err_x_mm=(r["cx"] - x) * 1000 if "cx" in r else None,
                    err_y_mm=(r["cy"] - 0.0) * 1000 if "cy" in r else None, t_render=r["t_render"])
        out["V"].append(cell)
        print(f"V x={x:.2f} n_px={cell['n_px']} border={cell['border']} err_x={cell['err_x_mm']} "
              f"err_y={cell['err_y_mm']} t={cell['t_render']:.3f}s", flush=True)


def part_r(jp, pose0, out):
    for mu, lead in RETREAT:
        w = pst.make_world(mu)
        c = w.client
        body = int(w.robot)
        arm = w.robot.get_group_joints(ARM_GROUP, client=c)
        real = w.objects[0]
        view, proj = views(c)
        pbu.set_joint_positions(w.robot, arm, jp[0], client=c)
        pbu.set_pose(real, pose0, client=c)
        pbu.set_joint_positions(w.robot, arm, jp[0], client=c)
        stroke = follow_path(w.robot, arm, jp, lead_step=pst.TEST_EFFORT, max_force=None, client=c)
        xs, ys, touch = [], [], []

        def log():
            pos = c.getBasePositionAndOrientation(real)[0]
            xs.append(pos[0])
            ys.append(pos[1])
            touch.append(len(c.getContactPoints(bodyA=real, bodyB=body)) > 0)

        for _ in iter(pbu.simulate_controller(stroke, client=c)):
            log()
        n_stroke = len(xs)
        q_end = pbu.get_joint_positions(w.robot, arm, client=c)
        back = follow_path(w.robot, arm, [q_end, ps.DEFAULT_ARM_POS], lead_step=lead, max_force=None, client=c)
        seen, n_back, k = [], 0, 0
        qd_max = 0.0
        gen = iter(pbu.simulate_controller(back, client=c))
        while True:
            try:
                next(gen)
                n_back += 1
            except StopIteration:
                break
            log()
            qd = [abs(js[1]) for js in c.getJointStates(body, arm)]
            qd_max = max(qd_max, max(qd))
            if len(xs) % 12 == 0:
                r = pst.render_centre(c, real, view, proj)
                seen.append((len(xs) - 1, r.get("n_px", 0), (r["cx"] - xs[-1]) * 1000 if "cx" in r else None))
            if n_back > 2400:
                break
        for _ in range(2000):
            c.stepSimulation()
            log()
            if len(xs) % 12 == 0 and len(seen) < 400:
                r = pst.render_centre(c, real, view, proj)
                seen.append((len(xs) - 1, r.get("n_px", 0), (r["cx"] - xs[-1]) * 1000 if "cx" in r else None))
        xs, ys = np.array(xs), np.array(ys)
        last_touch = int(np.nonzero(touch)[0][-1]) if any(touch) else 0
        first_full = next((s for s, n, e in seen if n > 0 and e is not None and abs(e) < 3.0 and s > last_touch), None)
        d_total = math.hypot(xs[-1] - xs[last_touch], ys[-1] - ys[last_touch])
        d_left = (math.hypot(xs[-1] - xs[first_full], ys[-1] - ys[first_full]) / d_total) if first_full else None
        cell = dict(mu=mu, lead=lead, n_stroke=n_stroke, n_back=n_back, qd_max=qd_max, last_touch=last_touch,
                    first_full_view=first_full, share_of_slide_left=d_left, x_rest=float(xs[-1]),
                    touch_after_stroke=bool(any(touch[n_stroke:])), seen=seen[:40])
        out["R"].append(cell)
        print(f"R mu={mu:.2f} lead={lead:.2f} stroke_steps={n_stroke} retreat_steps={n_back} "
              f"qd_max={qd_max:.2f}rad/s last_touch={last_touch} first_full_view={first_full} "
              f"share_left={d_left} x_rest={cell['x_rest']:.4f} touch_after_stroke={cell['touch_after_stroke']}",
              flush=True)


def main(out_path):
    pose0 = ps.PUCK_START_POSE
    tp_goal = list(ps.REGION_POSES[ps.GOAL_OBJECTS[0]][0][:2])
    w = pst.make_world(0.10)
    _, jp, _ = ps.shoot_controller(None, w, w.objects, pose0, tp_goal, pc_steps=1, effort=0.005)
    out = {"SL": [], "V": [], "R": []}
    part_sl(jp, pose0, out)
    part_v(out)
    part_r(jp, pose0, out)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main(sys.argv[1])
