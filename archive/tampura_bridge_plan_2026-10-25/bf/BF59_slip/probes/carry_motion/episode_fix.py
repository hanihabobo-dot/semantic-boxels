"""One find_dice bridge episode with this angle's two candidate fixes
patched in (a probe; no tracked file changed), and loss_dynamics'
per-step recorder installed for the die's carry.

  flip  (env CM_FLIP=1): pose_belief.fitted_grasp_candidates returns, for
        each candidate yaw g, the one of g and g + pi (the same pinch, the
        pads swapped) whose top-down hand is the smaller rotation from the
        hand at DEFAULT_ARM_POS (their home; the quaternion is the FK the
        carry probe printed, a constant here, FK of the planner's home in
        a real change).
  trap  (env CM_TRAP=1): the dispatcher's waypoint stream (the
        test_full_pipeline name move_robot_smooth) buffers every
        settle=False waypoint and, at the settle=True one, runs the whole
        polyline from the readback as one acceleration-bounded schedule
        (trapezoid per straight segment at the Panda datasheet
        accelerations and the existing velocity limits, through-going on
        collinear pairs, at rest at a direction change), then the original
        settle.  Every step calls telemetry.tick() like the original.

  cd /root/tampura-work/tampura_environments
  CM_FLIP=1 CM_TRAP=1 python <this> <recorder jsonl> <driver args...>
"""
import math
import os
import runpy
import sys

import numpy as np

REPO = '/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels'
LD = os.path.join(REPO, 'archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/loss_dynamics')
DRIVER = os.path.join(REPO, 'tampura_bridge', 'run_bridge_on_finddice.py')
out = sys.argv[1]
sys.argv = [DRIVER] + sys.argv[2:]
sys.path.insert(0, REPO)
sys.path.insert(1, LD)

import console_ui                                   # noqa: E402
console_ui.install_early('__main__')
from tampura.config import config as _tconfig       # noqa: E402,F401
import tampura_environments                         # noqa: E402,F401
from tampura_bridge import policy as _bp            # noqa: E402,F401
import pybullet as p                                # noqa: E402
import pose_belief                                  # noqa: E402
import robot_utils                                  # noqa: E402
import telemetry                                    # noqa: E402
import test_full_pipeline as tfp                    # noqa: E402

HOME_ORN = [0.943, -0.023, 0.332, 0.007]
AMAX = np.array([15.0, 7.5, 10.0, 12.5, 15.0, 20.0, 20.0])


def _ang(q1, q2):
    d = abs(float(np.dot(np.asarray(q1) / np.linalg.norm(q1), np.asarray(q2) / np.linalg.norm(q2))))
    return math.degrees(2 * math.acos(min(1.0, d)))


if os.environ.get('CM_FLIP') == '1':
    _orig_fgc = pose_belief.fitted_grasp_candidates

    def fgc(yaw, body_extents, square_tol, aabb_ext=None):
        out_c = []
        for gy, span in _orig_fgc(yaw, body_extents, square_tol, aabb_ext):
            alts = [gy, gy + math.pi]
            best = min(alts, key=lambda g: _ang(p.getQuaternionFromEuler([0, math.pi, g]), HOME_ORN))
            if best != gy:
                print(f"    [cm flip] grasp yaw {math.degrees(gy):.1f} -> {math.degrees(best):.1f} deg", flush=True)
            out_c.append((best, span))
        return out_c
    pose_belief.fitted_grasp_candidates = fgc


def trap_schedule(wps):
    vmax = robot_utils.JOINT_VELOCITY_LIMITS
    pts = [np.asarray(wps[0], dtype=float)]
    for w in wps[1:]:
        w = np.asarray(w, dtype=float)
        if len(pts) >= 2:
            d0, d1 = pts[-1] - pts[-2], w - pts[-1]
            if (np.linalg.norm(d0) > 1e-9 and np.linalg.norm(d1) > 1e-9 and
                    np.dot(d0, d1) / (np.linalg.norm(d0) * np.linalg.norm(d1)) > 0.9999):
                pts[-1] = w
                continue
        if np.linalg.norm(w - pts[-1]) > 1e-9:
            pts.append(w)
    dt = robot_utils.SIM_TIMESTEP
    out_q = []
    for a, b in zip(pts[:-1], pts[1:]):
        d = b - a
        absd = np.abs(d)
        nz = absd > 1e-9
        sv = float(np.min(vmax[nz] / absd[nz]))
        sa = float(np.min(AMAX[nz] / absd[nz]))
        t_acc = sv / sa
        if sa * t_acc * t_acc >= 1.0:
            t_acc = math.sqrt(1.0 / sa)
            sv, t_flat = sa * t_acc, 0.0
        else:
            t_flat = (1.0 - sa * t_acc * t_acc) / sv
        T = 2 * t_acc + t_flat
        for k in range(1, max(1, int(math.ceil(T / dt))) + 1):
            t = min(T, k * dt)
            if t < t_acc:
                s = 0.5 * sa * t * t
            elif t < t_acc + t_flat:
                s = 0.5 * sa * t_acc ** 2 + sv * (t - t_acc)
            else:
                s = 1.0 - 0.5 * sa * (T - t) ** 2
            out_q.append(a + d * s)
    return out_q, len(pts) - 1


if os.environ.get('CM_TRAP') == '1':
    _orig_mrs = tfp.move_robot_smooth
    _buf = []

    def mrs(robot_id, target_joints, gui=False, steps=60, settle=False, **kw):
        _buf.append([float(v) for v in target_joints][:7])
        if not settle:
            return None
        arm = robot_utils.robot_model().arm_joints
        q0 = [p.getJointState(robot_id, i)[0] for i in arm]
        sched, nseg = trap_schedule([q0] + _buf)
        print(f"    [cm trap] {len(_buf)} waypoints, {nseg} segments, {len(sched)} steps", flush=True)
        _buf.clear()
        for q in sched:
            for k, i in enumerate(arm):
                p.setJointMotorControl2(robot_id, i, p.POSITION_CONTROL,
                                        targetPosition=float(q[k]), force=240)
            p.stepSimulation()
            telemetry.tick()
        return _orig_mrs(robot_id, target_joints, gui, steps=1, settle=True, **kw)
    tfp.move_robot_smooth = mrs

    _orig_phase = telemetry.phase

    def phase(label):
        if _buf:
            print(f"    [cm trap] WARNING: {len(_buf)} buffered waypoints dropped at a phase change", flush=True)
            _buf.clear()
        _orig_phase(label)
    telemetry.phase = phase

import loss_recorder                                # noqa: E402
loss_recorder.install(out)
runpy.run_path(DRIVER, run_name='__main__')
