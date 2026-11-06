"""Third read-only probe (2026-11-06), the answer to REVIEW.md objection 1.

Question: can arm O estimate mu_eff from several renders of the free slide
(test action T3), so that the estimate needs neither the launch speed nor the
separation point, the two inputs REVIEW.md N2 and N4 show to be weak; which
camera can see the slide while the arm holds the stroke's end pose; and does
the free slide follow the damped Coulomb law at shot speeds, so that the
shot's forward-model error of N4 (ii) can be located?

Set-up as the earlier probes: their venv, cwd /root/ps_probe, their
setup_puck_world with the 19 ghosts removed, their stroke (shoot_controller's
joint path toward goal0 from the start pose, computed as rp_launch.py does),
one fresh world per trial (the engine is deterministic, REVIEW 2.1).  Every
write is to the probe's own worlds.  The true track, contacts and body ids
are probe data, never inputs arm O would have; the truth only scores.

  S1  the test push (effort 0.010), 21 frictions in [0.05, 0.15].  Offline it
      imitates an eye rendering at known steps plus the rest pose, each
      position with Gaussian noise sigma per axis (100 draws per sigma), and
      fits (s1, v1, mu_eff) of dv/dt = -(mu_eff g + 0.04 v + 0.04 v^2)
      (PyBullet's default damping, REVIEW rp_damping.py: exact) to the
      along-track positions, closed form.  Schedules: from 24 steps after the
      stroke command ends, at 20 Hz and 5 Hz, or three renders; and "early":
      from 6 steps after the last robot-puck contact (in hindsight; arm O
      would take it from its own pad contacts), at 20 Hz and 60 Hz.
  S2  shot speeds (efforts 0.015, 0.020, 0.030 at mu 0.05, 0.10, 0.15): the
      same fit at sigma 0 on the on-slab part of the track, and two forward
      checks with the true mu_eff: from the first render's state, and from
      the separation event (the review's N4 (ii) check).
  S3  real renders (TinyRenderer, 640 x 480, the D4 intrinsics) at S1's
      "early 20 Hz" steps for mu 0.05, 0.10, 0.15, from two cameras: the
      D4 fixed eye (tampura_bridge/task_spec.py:70-75) and the wrist camera
      (their camera_frame link at the arm's current pose, looking along its
      z axis, up = world z, as their pb_utils.get_image_at_pose does).  Per
      render: puck pixels, time, and a stand-in centre estimate (midpoints of
      the x and y extents of the puck's top-face pixels back-projected
      through the depth buffer; the pixels picked by the segmentation mask,
      a probe shortcut).  Not our perception: a check on the noise levels S1
      assumes.  Then the S1 fit on the stand-in track.
(A first version used rayTest for line of sight; the real puck is in their
GROUP_GHOST with GHOST_MASK, env.py:347-349, so rays never hit it, and that
check was void; probe_occlusion_check.py shows it.)

Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/tampura-work/tampura:\
/root/tampura-work/tampura_environments <their venv python> -B <this file> <out.json>
"""
import json
import math
import random
import sys
import time

import numpy as np
import pybullet as p
from scipy.optimize import least_squares

import tampura_environments.puck_slide.env as ps
import tampura_environments.panda_utils.pb_utils as pbu
from tampura_environments.panda_utils.panda_env_utils import ARM_GROUP
from tampura_environments.panda_utils.primitives import follow_path

G = 9.8                      # their gravity, env.py:258
K1 = K2 = 0.04               # PyBullet's default damping (REVIEW rp_damping.py)
DT = 1.0 / 240.0             # their time step (probe_puck_physics_out.json)
TEST_EFFORT = 0.010          # the test push's effort (ARGUMENT 3.2, T2)
FRICTIONS = [round(float(m), 4) for m in np.linspace(0.05, 0.15, 21)]
SIGMAS = [0.0, 0.001, 0.002, 0.003]
DRAWS = 100
STOP_SPEED = 1e-3
SLAB_END_X = 1.40            # env.py:306-313, 329-333
PUCK_HALF_H = 0.02           # PUCK_HEIGHT 0.04 (create_puck, env.py:234-243)
SHOT_CELLS = [(mu, e) for mu in (0.05, 0.10, 0.15) for e in (0.015, 0.020, 0.030)]
RENDER_FRICTIONS = (0.05, 0.10, 0.15)
# start rule, step every k (None: three renders)
SCHEDULES = {"late_20Hz": ("late", 12), "late_5Hz": ("late", 48), "late_three": ("late", None),
             "early_20Hz": ("early", 12), "early_60Hz": ("early", 4)}
LATE_DELAY, EARLY_DELAY = 24, 6
# The D4 eye, copied from tampura_bridge/task_spec.py:70-75 (nothing of ours is imported).
EYE_POSITION = (0.17861445248126984, 0.048803217709064484, 0.5883188247680664)
EYE_TARGET = (3.285824775695801, -0.16977983713150024, -3.322878360748291)
EYE_UP = (0.0, 0.0, 1.0)
EYE_FOV_DEG = 49.13434264120263
EYE_W, EYE_H = 640, 480
EYE_NEAR, EYE_FAR = 0.02, 5.0


def make_world(mu):
    w = ps.setup_puck_world(pose=ps.PUCK_START_POSE, friction=mu, vis=False)
    for b in w.objects[1:]:
        w.client.removeBody(b)
    w.objects = w.objects[:1]
    return w


def link_index(c, body, name):
    for j in range(c.getNumJoints(body)):
        if c.getJointInfo(body, j)[12].decode() == name:
            return j
    raise KeyError(name)


def wrist_view(c, body, cam_link):
    pos, orn = c.getLinkState(body, cam_link, computeForwardKinematics=1)[4:6]
    R = np.array(c.getMatrixFromQuaternion(orn)).reshape(3, 3)
    z = R[:, 2]
    target = np.array(pos) + EYE_FAR * z
    up = EYE_UP if abs(z[2]) < 0.995 else tuple(-R[:, 1])   # world z is degenerate looking straight down
    return c.computeViewMatrix(pos, target.tolist(), up), float(math.degrees(math.asin(max(-1, min(1, -z[2])))))


def render_centre(c, real, view, proj):
    t0 = time.perf_counter()
    w, h, _rgb, depth, seg = c.getCameraImage(EYE_W, EYE_H, view, proj,
                                              renderer=p.ER_TINY_RENDERER)
    t_render = time.perf_counter() - t0
    depth = np.reshape(np.asarray(depth, dtype=np.float64), (h, w))
    seg = np.reshape(np.asarray(seg), (h, w)) & ((1 << 24) - 1)
    rows, cols = np.nonzero(seg == real)
    if len(rows) == 0:
        return dict(t_render=t_render, n_px=0)
    border = bool(rows.min() == 0 or cols.min() == 0 or rows.max() == h - 1 or cols.max() == w - 1)
    d = depth[rows, cols]
    ndc = np.stack([2 * (cols + 0.5) / w - 1, 1 - 2 * (rows + 0.5) / h, 2 * d - 1, np.ones_like(d)])
    V = np.array(view, dtype=np.float64).reshape(4, 4, order="F")
    P = np.array(proj, dtype=np.float64).reshape(4, 4, order="F")
    pts = np.linalg.inv(P @ V) @ ndc
    pts = pts[:3] / pts[3]
    zmax = float(pts[2].max())
    top = pts[:, pts[2] > zmax - 0.0025]
    return dict(t_render=t_render, n_px=int(len(rows)), n_top=int(top.shape[1]), border=border,
                cx=float(0.5 * (top[0].min() + top[0].max())),
                cy=float(0.5 * (top[1].min() + top[1].max())), ztop=zmax)


def record(world, pose, joint_path, effort, render_at=()):
    """Their trial (as probe_puck_physics2.py), logging the puck every step;
    sample k is the state after k + 1 simulation steps.  At the samples in
    render_at it renders from the D4 eye and from the wrist camera."""
    c = world.client
    body = int(world.robot)
    arm = world.robot.get_group_joints(ARM_GROUP, client=c)
    real = world.objects[0]
    cam = link_index(c, body, "camera_frame")
    pbu.set_joint_positions(world.robot, arm, joint_path[0], client=c)
    pbu.set_pose(real, pose, client=c)
    pbu.set_joint_positions(world.robot, arm, joint_path[0], client=c)
    controller = follow_path(world.robot, arm, joint_path, lead_step=effort,
                             max_force=None, client=c)
    view_eye = c.computeViewMatrix(EYE_POSITION, EYE_TARGET, EYE_UP)
    proj = c.computeProjectionMatrixFOV(EYE_FOV_DEG, EYE_W / EYE_H, EYE_NEAR, EYE_FAR)
    want = set(render_at)
    L = {k: [] for k in ("x", "y", "z", "speed", "wz", "tilt", "touch")}
    renders = {}

    def log():
        k = len(L["x"])
        pos, orn = c.getBasePositionAndOrientation(real)
        lin, ang = c.getBaseVelocity(real)
        L["x"].append(pos[0])
        L["y"].append(pos[1])
        L["z"].append(pos[2])
        L["speed"].append(float(math.hypot(lin[0], lin[1])))
        L["wz"].append(float(ang[2]))
        L["tilt"].append(float(math.degrees(math.acos(max(-1.0, min(1.0, 1 - 2 * (orn[0] ** 2 + orn[1] ** 2)))))))
        L["touch"].append(len(c.getContactPoints(bodyA=real, bodyB=body)) > 0)
        if k in want:
            vw, down = wrist_view(c, body, cam)
            renders[k] = {"eye": render_centre(c, real, view_eye, proj),
                          "wrist": dict(render_centre(c, real, vw, proj), look_down_deg=down)}

    n_ctrl = 0
    for _ in iter(pbu.simulate_controller(controller, client=c)):
        n_ctrl += 1
        log()
    for _ in range(2000):
        c.stepSimulation()
        log()
    rec = {k: np.array(v) for k, v in L.items()}
    rec["n_ctrl"] = n_ctrl
    rec["renders"] = renders
    return rec


def slide(t, v1, mu):
    """Along-track distance after time t >= 0 from speed v1 under
    dv/dt = -(mu g + K1 v + K2 v^2), closed form (arctan branch, valid for
    mu > K1^2 / (4 K2 g) = 0.001)."""
    A, B, C = K2, K1, mu * G
    om = math.sqrt(C / A - B * B / (4 * A * A))
    th0 = math.atan((v1 + B / (2 * A)) / om)
    ths = math.atan((B / (2 * A)) / om)
    tstop = (th0 - ths) / (A * om)
    tt = np.minimum(np.asarray(t, dtype=float), tstop)
    return (1.0 / A) * np.log(np.cos(th0 - A * om * tt) / math.cos(th0)) - (B / (2 * A)) * tt


def schedule(rec, rule, every):
    x, sp = rec["x"], rec["speed"]
    touch_idx = np.nonzero(rec["touch"])[0]
    last_touch = int(touch_idx[-1]) if len(touch_idx) else 0
    first = rec["n_ctrl"] + LATE_DELAY if rule == "late" else last_touch + EARLY_DELAY
    off = np.nonzero(x > SLAB_END_X - 0.06)[0]
    off_idx = int(off[0]) if len(off) else len(x)
    moving = np.nonzero(sp[:off_idx] > STOP_SPEED)[0]
    end = int(moving[-1]) + 1 if len(moving) else first + 1
    if every is None:
        steps = [first, first + 60, first + 120]
    else:
        steps = list(range(first, max(end, first + 1), every))
    steps = [s for s in steps if s < off_idx]
    fell = bool(rec["z"][-1] < 0.05) or off_idx < len(x)
    return steps, end, fell


def fit_track(t, px, py, rest, w, mu_fixed=None):
    """rest: (rx, ry) or None.  Returns (mu, s1, v1, residuals in metres)."""
    end = np.array(rest) if rest is not None else np.array([px[-1], py[-1]])
    u = end - np.array([px[0], py[0]])
    nu = np.linalg.norm(u)
    u = u / nu if nu > 1e-6 else np.array([1.0, 0.0])
    s = (px - px[0]) * u[0] + (py - py[0]) * u[1]
    s_rest = None if rest is None else (rest[0] - px[0]) * u[0] + (rest[1] - py[0]) * u[1]

    def res(q):
        if mu_fixed is None:
            s1, v1, mu = q
        else:
            (s1, v1), mu = q, mu_fixed
        r = s1 + slide(t, v1, mu) - s
        if s_rest is not None:
            r = np.append(r, s1 + slide(1e3, v1, mu) - s_rest)
        return r * w

    v_guess = max((s[1] - s[0]) / (t[1] - t[0]), 0.01) if len(s) > 1 else 0.1
    if mu_fixed is None:
        sol = least_squares(res, [0.0, v_guess, 0.01], bounds=([-0.05, 1e-3, 0.0015], [0.05, 2.0, 0.05]))
        mu = float(sol.x[2])
    else:
        sol = least_squares(res, [0.0, v_guess], bounds=([-0.05, 1e-3], [0.05, 2.0]))
        mu = mu_fixed
    return mu, float(sol.x[0]), float(sol.x[1]), sol.fun / w


def stats(errs):
    e = np.asarray(errs)
    a = np.abs(e)
    return dict(n=int(len(e)), median=float(np.median(e)), p95_abs=float(np.percentile(a, 95)),
                p99_abs=float(np.percentile(a, 99)), max_abs=float(np.max(a)))


def wilson_lo(k, n, z=1.96):
    q = k / n
    d = 1 + z * z / n
    return (q + z * z / (2 * n) - z * math.sqrt(q * (1 - q) / n + z * z / (4 * n * n))) / d


def camera_stats(rec, steps, cam, mu):
    rs = [rec["renders"][s][cam] for s in steps]
    ok = [i for i, r in enumerate(rs) if r.get("n_px", 0) > 0 and not r.get("border", False)]
    out = dict(n_renders=len(steps), n_puck_seen=sum(1 for r in rs if r.get("n_px", 0) > 0),
               n_usable=len(ok), t_render_median_s=float(np.median([r["t_render"] for r in rs])),
               n_px=[int(r.get("n_px", 0)) for r in rs])
    if cam == "wrist":
        out["look_down_deg"] = [round(r["look_down_deg"], 1) for r in rs]
    if not ok:
        return out
    ex = np.array([rs[i]["cx"] - rec["x"][steps[i]] for i in ok])
    ey = np.array([rs[i]["cy"] - rec["y"][steps[i]] for i in ok])
    out.update(err_x_mean_mm=float(ex.mean() * 1000), err_x_sd_mm=float(ex.std() * 1000),
               err_y_mean_mm=float(ey.mean() * 1000), err_y_sd_mm=float(ey.std() * 1000),
               err_max_mm=float(np.max(np.hypot(ex, ey)) * 1000))
    if len(ok) >= 4 and ok[-1] == len(steps) - 1:
        trk = ok[:-1]
        t = (np.array([steps[i] for i in trk]) - steps[trk[0]]) * DT
        px = np.array([rs[i]["cx"] for i in trk])
        py = np.array([rs[i]["cy"] for i in trk])
        m, _s1, _v1, r = fit_track(t, px, py, (rs[-1]["cx"], rs[-1]["cy"]), 1.0 / 0.001)
        out.update(mu_rel_err=m / (0.1 * mu) - 1.0, fit_max_resid_mm=float(np.max(np.abs(r)) * 1000),
                   n_fit=len(trk))
    return out


def main(out_path):
    t0 = time.time()
    random.seed(0)
    np.random.seed(0)
    pose0 = ps.PUCK_START_POSE
    tp_goal = list(ps.REGION_POSES[ps.GOAL_OBJECTS[0]][0][:2])
    w = make_world(0.10)
    _, jp, _ = ps.shoot_controller(None, w, w.objects, pose0, tp_goal, pc_steps=1, effort=0.005)
    rng = np.random.default_rng(0)
    out = {"test_effort": TEST_EFFORT, "sigmas": SIGMAS, "draws": DRAWS, "schedules": SCHEDULES,
           "late_delay": LATE_DELAY, "early_delay": EARLY_DELAY, "joint_path_len": len(jp),
           "S1": [], "S2": [], "S3": []}
    agg = {(sch, sg): [] for sch in SCHEDULES for sg in SIGMAS}

    # S1: the test push, fitted from noisy positions
    for mu in FRICTIONS:
        rec = record(make_world(mu), pose0, jp, TEST_EFFORT)
        truth = 0.1 * mu
        touch_idx = np.nonzero(rec["touch"])[0]
        fr = dict(mu=mu, x_rest=float(rec["x"][-1]), y_rest=float(rec["y"][-1]),
                  n_ctrl=rec["n_ctrl"], last_touch=int(touch_idx[-1]), n_touch_steps=int(len(touch_idx)),
                  results={})
        for sch, (rule, k) in SCHEDULES.items():
            steps, end, fell = schedule(rec, rule, k)
            t = (np.array(steps) - steps[0]) * DT
            row = {"n_renders": len(steps), "first": steps[0], "slide_end": end,
                   "touch_after_first": bool(rec["touch"][steps[0]:].any()),
                   "share_of_slide_after_first": float(
                       math.hypot(rec["x"][-1] - rec["x"][steps[0]], rec["y"][-1] - rec["y"][steps[0]]) /
                       max(1e-9, math.hypot(rec["x"][-1] - rec["x"][fr["last_touch"]],
                                            rec["y"][-1] - rec["y"][fr["last_touch"]])))}
            for sg in SIGMAS:
                errs = []
                for _ in range(1 if sg == 0.0 else DRAWS):
                    px = rec["x"][steps] + rng.normal(0, sg, len(steps))
                    py = rec["y"][steps] + rng.normal(0, sg, len(steps))
                    rest = (rec["x"][-1] + rng.normal(0, sg), rec["y"][-1] + rng.normal(0, sg))
                    m, _s1, _v1, r = fit_track(t, px, py, rest, 1.0 / max(sg, 1e-4))
                    errs.append(m / truth - 1.0)
                    if sg == 0.0:
                        row["fit_max_resid_mm_sigma0"] = float(np.max(np.abs(r)) * 1000)
                agg[(sch, sg)].extend(errs)
                row[f"sigma_{sg * 1000:.0f}mm"] = stats(errs)
            fr["results"][sch] = row
        out["S1"].append(fr)
        R = fr["results"]
        print(f"S1 mu={mu:.4f} x_rest={fr['x_rest']:.4f} last_touch={fr['last_touch']} "
              f"late: first={R['late_20Hz']['first']} share={R['late_20Hz']['share_of_slide_after_first']:.2f} "
              f"bias0={R['late_20Hz']['sigma_0mm']['median']:+.4f} p95@2mm={R['late_20Hz']['sigma_2mm']['p95_abs']:.4f} | "
              f"early: first={R['early_20Hz']['first']} share={R['early_20Hz']['share_of_slide_after_first']:.2f} "
              f"bias0={R['early_20Hz']['sigma_0mm']['median']:+.4f} resid0={R['early_20Hz']['fit_max_resid_mm_sigma0']:.3f}mm "
              f"20Hz p95@1/2/3mm={R['early_20Hz']['sigma_1mm']['p95_abs']:.4f}/{R['early_20Hz']['sigma_2mm']['p95_abs']:.4f}/"
              f"{R['early_20Hz']['sigma_3mm']['p95_abs']:.4f} "
              f"60Hz p95@1/2/3mm={R['early_60Hz']['sigma_1mm']['p95_abs']:.4f}/{R['early_60Hz']['sigma_2mm']['p95_abs']:.4f}/"
              f"{R['early_60Hz']['sigma_3mm']['p95_abs']:.4f} p99@2mm={R['early_60Hz']['sigma_2mm']['p99_abs']:.4f}",
              flush=True)
    out["S1_aggregate"] = {f"{sch}|sigma_{sg * 1000:.0f}mm": stats(e) for (sch, sg), e in agg.items()}
    for key, v in out["S1_aggregate"].items():
        print(f"AGG {key}: n={v['n']} median {v['median']:+.4f} p95 {v['p95_abs']:.4f} "
              f"p99 {v['p99_abs']:.4f} max {v['max_abs']:.4f}", flush=True)

    # S2: shot speeds, the law after separation and the forward checks
    for mu, e in SHOT_CELLS:
        rec = record(make_world(mu), pose0, jp, e)
        truth = 0.1 * mu
        steps, end, fell = schedule(rec, "early", 12)
        t = (np.array(steps) - steps[0]) * DT
        px, py = rec["x"][steps], rec["y"][steps]
        rest = None if fell else (rec["x"][-1], rec["y"][-1])
        m_free, _a, _b, r_free = fit_track(t, px, py, rest, 1e4)
        _m, s1f, v1f, r_fix = fit_track(t, px, py, rest, 1e4, mu_fixed=truth)
        touch_idx = np.nonzero(rec["touch"])[0]
        sep = int(touch_idx[-1]) + 1
        v_sep = float(rec["speed"][sep])
        zs = rec["z"][sep:end] if end > sep else rec["z"][sep:sep + 1]
        cell = dict(mu=mu, effort=e, x_rest=float(rec["x"][-1]), fell=fell, n_ctrl=rec["n_ctrl"],
                    sep_index=sep, v_sep=v_sep, n_renders=len(steps), first=steps[0],
                    mu_free_rel_err=m_free / truth - 1.0,
                    free_fit_max_resid_mm=float(np.max(np.abs(r_free)) * 1000),
                    fixed_mu_track_rms_mm=float(np.sqrt(np.mean(r_fix[:len(steps)] ** 2)) * 1000),
                    fixed_mu_rest_resid_mm=(float(r_fix[-1] * 1000) if rest is not None else None),
                    wz_at_sep=float(rec["wz"][sep]), tilt_max_after_sep=float(rec["tilt"][sep:end + 1].max()),
                    z_min_after_sep=float(zs.min()), z_max_after_sep=float(zs.max()))
        if not fell:
            d_act = math.hypot(rec["x"][-1] - rec["x"][sep], rec["y"][-1] - rec["y"][sep])
            d_pred = float(slide(1e3, v_sep, truth))
            cell.update(d_from_sep_actual=d_act, d_from_sep_pred=d_pred,
                        sep_forward_err_mm=(d_act - d_pred) * 1000)
        out["S2"].append(cell)
        print(f"S2 mu={mu:.2f} e={e:.3f} x_rest={cell['x_rest']:.4f} fell={fell} sep={sep} v_sep={v_sep:.4f} "
              f"renders={len(steps)} mu_free_err={cell['mu_free_rel_err']:+.4f} "
              f"free_resid={cell['free_fit_max_resid_mm']:.2f}mm fixed_rms={cell['fixed_mu_track_rms_mm']:.2f}mm "
              f"fixed_rest={cell['fixed_mu_rest_resid_mm']} sep_fwd_err_mm={cell.get('sep_forward_err_mm')} "
              f"wz_sep={cell['wz_at_sep']:.3f} tilt_max={cell['tilt_max_after_sep']:.3f} "
              f"z {cell['z_min_after_sep']:.4f} to {cell['z_max_after_sep']:.4f}", flush=True)

    # S3: real renders from the D4 eye and the wrist camera
    for mu in RENDER_FRICTIONS:
        base = record(make_world(mu), pose0, jp, TEST_EFFORT)
        steps, _end, _fell = schedule(base, "early", 12)
        steps = steps + [len(base["x"]) - 1]
        rec = record(make_world(mu), pose0, jp, TEST_EFFORT, render_at=steps)
        same = bool(np.array_equal(rec["x"], base["x"]))
        cell = dict(mu=mu, deterministic_rerun=same, first=steps[0],
                    eye=camera_stats(rec, steps, "eye", mu), wrist=camera_stats(rec, steps, "wrist", mu))
        out["S3"].append(cell)
        for cam in ("eye", "wrist"):
            cs = cell[cam]
            print(f"S3 mu={mu:.2f} cam={cam} renders={cs['n_renders']} seen={cs['n_puck_seen']} "
                  f"usable={cs['n_usable']} t_render={cs['t_render_median_s']:.3f}s "
                  f"err_x={cs.get('err_x_mean_mm', float('nan')):+.2f}+-{cs.get('err_x_sd_mm', float('nan')):.2f}mm "
                  f"err_y={cs.get('err_y_mean_mm', float('nan')):+.2f}+-{cs.get('err_y_sd_mm', float('nan')):.2f}mm "
                  f"err_max={cs.get('err_max_mm', float('nan')):.2f}mm mu_err={cs.get('mu_rel_err', float('nan')):+.4f} "
                  f"n_px first/last={cs['n_px'][0]}/{cs['n_px'][-1]} "
                  f"down={cs.get('look_down_deg', ['-'])[0]} rerun_same={same}", flush=True)

    out["wilson_lower"] = {f"{k}/{n}": wilson_lo(k, n) for k, n in
                           ((19, 20), (20, 20), (98, 100), (99, 100), (100, 100), (195, 200), (197, 200), (200, 200))}
    for key, v in out["wilson_lower"].items():
        print(f"WILSON {key}: {v:.4f}")
    out["wall_s"] = time.time() - t0
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {out_path} in {out['wall_s']:.1f} s")


if __name__ == "__main__":
    main(sys.argv[1])
