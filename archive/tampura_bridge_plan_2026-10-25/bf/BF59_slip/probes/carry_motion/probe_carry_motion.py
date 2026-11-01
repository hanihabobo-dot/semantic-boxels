"""BF#59 carry_motion probe: what the carry home does to the pinch.

Set-up copied from tools/_probe_carry_watch.py and tools/_probe_q14_grip.py:
TAMPURA's empty find_dice table, their Panda, D9's gravity, timestep and pad
friction; the die placed between the pads at the pick's contact height,
pinched by robot_utils.close_gripper_until_contact (60 N, GRIP_SQUEEZE),
given its mass, 60 settle steps.  Then the die is carried from the post-lift
pose to DEFAULT_ARM_POS by one of several EXECUTORS over the dispatcher's
trajectory (streams._linear_trajectory: 10 evenly spaced waypoints, what
plan_motion returns when the direct path is clear), and held at home.

Executors:
  pipe     the dispatcher today: move_robot_smooth(steps=30) per pair, settle
           at the last, hold_at_config(HOME_HOLD_STEP_CAP)
  hop      one move_robot_smooth to home (the existing probes' motion)
  slow     pipe with the velocity limits scaled by --scale
  trap     an acceleration-bounded schedule (trapezoidal velocity along the
           joint-space path, per-joint a_max = --amax rad/s^2), position
           targets only, then the same settle and hold
  trapff   trap with the schedule's velocity passed as targetVelocity
  via      pipe over a path with a raised via point (an RRT-like bend:
           pairs of unequal size and a direction change)

Per step it records the pad normal force per pad, both-pad contact, the die
offset in the EE frame against its pose after the settle (mm) and its
rotation in the hand (deg), the EE linear and angular acceleration (finite
differences of getLinkState's velocities), the largest joint acceleration,
and the pinch axis' angle to the horizontal.  A probe, not pipeline code.

  cd /root/tampura-work/tampura_environments
  PYTHONPATH=<repo>:<repo>/tools:/root/tampura-work/tampura:. \
    /root/armO-venvA/bin/python <this file> --executor pipe --out x.json
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np
import pybullet as p

REPO = '/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels'
for _d in (REPO, os.path.join(REPO, 'tools')):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import robot_utils                                   # noqa: E402
from tampura_bridge import task_spec                 # noqa: E402
from _probe_b1p2_tampura import top_down, ik_any_seed, LIFT, _coarse_cells   # noqa: E402
from _probe_q14_grip import _make_body, OURS, FORCE, GRASP_MARGIN_FROM_TOP, HELD_FORCE, SETTLE  # noqa: E402

DT = task_spec.TIMESTEP


def their_world():
    from tampura_environments.find_dice.env import setup_world
    from tampura_environments.panda_utils.panda_env_utils import setup_robot
    robot, client = setup_robot(vis=False)
    world = setup_world(robot, client, [], [])
    cid = client._client
    model = robot_utils.resolve_robot_model(robot.body, cid)
    robot_utils.use_robot_model(model)
    return world, robot, client, cid, model


class Recorder:
    def __init__(self, rb, body, cid, model):
        self.rb, self.body, self.cid, self.model = rb, body, cid, model
        self.n = 0
        self.phase = 'pre'
        self.rows = []
        self.prev = None
        self.ref = self._rel()
        self.lost = None
        self.slip = None

    def _ee(self):
        s = p.getLinkState(self.rb, self.model.ee_link, computeLinkVelocity=1,
                           computeForwardKinematics=True, physicsClientId=self.cid)
        return (np.asarray(s[0]), np.asarray(s[1]), np.asarray(s[6]), np.asarray(s[7]))

    def _rel(self):
        pos, orn, _, _ = self._ee()
        bp, bo = p.getBasePositionAndOrientation(self.body, physicsClientId=self.cid)
        inv = p.invertTransform(pos.tolist(), orn.tolist())
        rp, ro = p.multiplyTransforms(inv[0], inv[1], bp, bo)
        return np.asarray(rp), np.asarray(ro)

    def pads(self):
        cs = p.getContactPoints(bodyA=self.rb, bodyB=self.body, physicsClientId=self.cid)
        f = {fj: 0.0 for fj in self.model.finger_joints}
        for c in cs:
            if c[3] in f:
                f[c[3]] += c[9]
        both = all(
            any(c[3] == fj for c in cs) for fj in self.model.finger_joints)
        return both, [f[fj] for fj in self.model.finger_joints]

    def step(self):
        self.n += 1
        pos, orn, lv, av = self._ee()
        q = np.array([s[0] for s in p.getJointStates(self.rb, self.model.arm_joints,
                                                      physicsClientId=self.cid)])
        qd = np.array([s[1] for s in p.getJointStates(self.rb, self.model.arm_joints,
                                                       physicsClientId=self.cid)])
        both, f = self.pads()
        rp, ro = self._rel()
        off_mm = 1e3 * float(np.linalg.norm(rp - self.ref[0]))
        rot_deg = robot_utils.quat_angle_deg(ro, self.ref[1])
        # axis of the die's rotation in the hand, in the hand frame
        # (y = the pinch axis, z = the approach axis)
        inv_ref = p.invertTransform([0, 0, 0], self.ref[1].tolist())[1]
        dq = p.multiplyTransforms([0, 0, 0], ro.tolist(), [0, 0, 0], inv_ref)[1]
        ax = np.asarray(p.getAxisAngleFromQuaternion(dq)[0])
        rot = np.asarray(p.getMatrixFromQuaternion(orn.tolist())).reshape(3, 3)
        pinch = rot[:, 1]                       # the fingers slide along local y
        pinch_tilt = math.degrees(math.asin(min(1.0, abs(float(pinch[2])))))
        appr_tilt = math.degrees(math.acos(max(-1.0, min(1.0, -float(rot[2, 2])))))
        if self.prev is None:
            la = aa = 0.0
            qa = 0.0
        else:
            la = float(np.linalg.norm(lv - self.prev[0])) / DT
            aa = float(np.linalg.norm(av - self.prev[1])) / DT
            qa = float(np.max(np.abs(qd - self.prev[2]))) / DT
        self.prev = (lv, av, qd)
        # the hand's rotation integrated in its own frame (deg): x across
        # the pinch, y the pinch axis, z the approach axis (the wrist spin)
        w_h = rot.T @ av
        if not hasattr(self, 'spin'):
            self.spin = np.zeros(3)
            self.spin_abs = np.zeros(3)
        self.spin += np.degrees(w_h) * DT
        self.spin_abs += np.abs(np.degrees(w_h)) * DT
        row = dict(n=self.n, ph=self.phase, f1=round(f[0], 3), f2=round(f[1], 3),
                   both=both, off=round(off_mm, 2), rot=round(rot_deg, 2),
                   la=round(la, 2), aa=round(aa, 2), qa=round(qa, 2),
                   v=round(float(np.linalg.norm(lv)), 3),
                   w=round(float(np.linalg.norm(av)), 3),
                   qdmax=round(float(np.max(np.abs(qd))), 3),
                   tilt=round(pinch_tilt, 1), appr=round(appr_tilt, 1),
                   ax=[round(float(v), 2) for v in ax] if rot_deg > 2 else None)
        self.rows.append(row)
        if self.slip is None and off_mm > 1.0:
            self.slip = row
        if self.lost is None and (not both or sum(f) < HELD_FORCE):
            self.lost = row


# ---- executors ------------------------------------------------------------

def run_pairs(rb, wps, rec, steps=30):
    last = len(wps) - 1
    for wi, wp in enumerate(wps[1:], start=1):
        rec.phase = f'pair{wi}' if wi < last else 'pairlast'
        if wi == last:
            # the stream of the last pair, then its settle; mark the settle
            robot_utils.move_robot_smooth(rb, wp, False, steps=steps, settle=False,
                                          on_step=rec.step)
            rec.phase = 'settle'
            _settle(rb, wp, rec)
        else:
            robot_utils.move_robot_smooth(rb, wp, False, steps=steps, settle=False,
                                          on_step=rec.step)


def run_cont(rb, wps, rec, steps=30):
    """move_robot_smooth's schedule (30 steps floor, velocity stretch) per
    pair, but each pair's ramp starts at the previous pair's last COMMANDED
    target instead of the readback: the command is one continuous ramp."""
    arm = robot_utils.robot_model().arm_joints
    vlim = robot_utils.JOINT_VELOCITY_LIMITS
    cmd = np.array([p.getJointState(rb, i)[0] for i in arm])
    for wi, wp in enumerate(wps[1:], start=1):
        rec.phase = f'pair{wi}' if wi < len(wps) - 1 else 'pairlast'
        wp = np.asarray(wp, dtype=float)
        delta = np.abs(wp - cmd)
        n = max(steps, int(np.ceil(np.max(delta / (vlim * DT)))))
        start = cmd.copy()
        for t in range(n):
            a = (t + 1) / n
            tgt = (1 - a) * start + a * wp
            for k, i in enumerate(arm):
                p.setJointMotorControl2(rb, i, p.POSITION_CONTROL,
                                        targetPosition=float(tgt[k]), force=240)
            p.stepSimulation()
            rec.step()
        cmd = wp
    rec.phase = 'settle'
    _settle(rb, wps[-1], rec)


def _settle(rb, target, rec):
    arm = robot_utils.robot_model().arm_joints
    for _ in range(120):
        cur = [p.getJointState(rb, i)[0] for i in arm]
        if max(abs(c - t) for c, t in zip(cur, target)) < 2e-3:
            break
        for k, i in enumerate(arm):
            p.setJointMotorControl2(rb, i, p.POSITION_CONTROL,
                                    targetPosition=float(target[k]), force=240)
        p.stepSimulation()
        rec.step()


def hold(rb, home, rec, cap, gain=None):
    arm = robot_utils.robot_model().arm_joints
    rec.phase = 'hold'
    target = np.asarray(home, dtype=float)
    steps = 0
    while True:
        cur = np.array([p.getJointState(rb, i)[0] for i in arm])
        if np.allclose(cur, target, rtol=1e-4, atol=1e-4):
            return True, steps
        if steps >= cap:
            return False, steps
        for k, i in enumerate(arm):
            kw = {} if gain is None else {'positionGain': gain}
            p.setJointMotorControl2(rb, i, p.POSITION_CONTROL,
                                    targetPosition=float(target[k]), force=240, **kw)
        p.stepSimulation()
        rec.step()
        steps += 1


def trap_schedule(wps, amax, vscale=1.0):
    """Time-parameterise the polyline through wps along its arc (joint
    space): one trapezoid per straight segment, each segment starting and
    ending at rest when the direction changes, through-going when collinear.
    Returns per-step (q, qd)."""
    vmax = robot_utils.JOINT_VELOCITY_LIMITS * vscale
    # merge collinear segments (the linear trajectory is one segment)
    pts = [np.asarray(wps[0], dtype=float)]
    for w in wps[1:]:
        w = np.asarray(w, dtype=float)
        if len(pts) >= 2:
            d0 = pts[-1] - pts[-2]
            d1 = w - pts[-1]
            if (np.linalg.norm(d0) > 1e-9 and np.linalg.norm(d1) > 1e-9 and
                    np.dot(d0, d1) / (np.linalg.norm(d0) * np.linalg.norm(d1)) > 0.9999):
                pts[-1] = w
                continue
        if np.linalg.norm(w - pts[-1]) > 1e-9:
            pts.append(w)
    out = []
    for a, b in zip(pts[:-1], pts[1:]):
        d = b - a
        L = 1.0
        # path parameter s in [0, 1]; joint i moves d_i * s
        absd = np.abs(d)
        nz = absd > 1e-9
        sv = float(np.min(vmax[nz] / absd[nz]))         # max ds/dt
        sa = float(np.min((np.broadcast_to(amax, d.shape))[nz] / absd[nz]))   # max d2s/dt2
        t_acc = sv / sa
        if sa * t_acc * t_acc >= L:                       # triangle
            t_acc = math.sqrt(L / sa)
            sv = sa * t_acc
            t_flat = 0.0
        else:
            t_flat = (L - sa * t_acc * t_acc) / sv
        T = 2 * t_acc + t_flat
        nstep = max(1, int(math.ceil(T / DT)))
        for k in range(1, nstep + 1):
            t = min(T, k * DT)
            if t < t_acc:
                s, sd = 0.5 * sa * t * t, sa * t
            elif t < t_acc + t_flat:
                s, sd = 0.5 * sa * t_acc ** 2 + sv * (t - t_acc), sv
            else:
                tr = T - t
                s, sd = L - 0.5 * sa * tr * tr, sa * tr
            out.append((a + d * s, d * sd))
    return out


def run_trap(rb, wps, rec, amax, ff=False, vscale=1.0):
    arm = robot_utils.robot_model().arm_joints
    rec.phase = 'trap'
    for q, qd in trap_schedule(wps, amax, vscale):
        for k, i in enumerate(arm):
            kw = {'targetVelocity': float(qd[k])} if ff else {}
            p.setJointMotorControl2(rb, i, p.POSITION_CONTROL,
                                    targetPosition=float(q[k]), force=240, **kw)
        p.stepSimulation()
        rec.step()
    rec.phase = 'settle'
    _settle(rb, wps[-1], rec)


def linear_wps(q1, q2, n=10):
    return [((1 - t) * q1 + t * q2).tolist() for t in np.linspace(0, 1, n)]


def via_wps(q1, q2):
    """An RRT-like bend: through a via point with joint 2 raised and joint 1
    off the line, then shortcut-style long and short hops."""
    via = 0.5 * (q1 + q2)
    via[1] -= 0.35
    via[0] += 0.25
    via[3] += 0.25
    return [q1.tolist(), (0.8 * q1 + 0.2 * via).tolist(), via.tolist(),
            (0.3 * via + 0.7 * q2).tolist(), q2.tolist()]


def carry(k, cell, yaw, tilt_deg, args, rb, client, cid, model, home, st):
    ext = (OURS[args.payload][0] if args.payload in OURS
           else task_spec.CLASS_EXTENTS[args.payload])
    h = ext[2]
    contact = max(h - GRASP_MARGIN_FROM_TOP, task_spec.PICK_CONTACT_FLOOR)
    die_yaw = yaw
    # the believed yaw is `yaw`; the die itself sits delta further (the
    # yaw error between the pads and the die's faces; 45 deg = edge pinch)
    true_yaw = yaw + math.radians(args.delta_deg)
    if args.grasp_rule == 'flip':
        # the pipeline's M9 wrap, then of the two pad-swapped equivalents
        # (g, g + pi: the same pinch of any box) the one whose lift-pose
        # hand is the smaller rotation from home's hand
        g0 = float((die_yaw + math.pi / 4) % (math.pi / 2) - math.pi / 4)
        best = None
        for gy in (g0, g0 + math.pi):
            qq = ik_any_seed(st, [cell[0], cell[1], contact + LIFT], top_down(gy))
            if qq is None:
                continue
            ang = robot_utils.quat_angle_deg(top_down(gy), args._home_orn)
            if best is None or ang < best[0]:
                best = (ang, gy, qq)
        if best is None:
            return None
        _, yaw, q = best
    elif args.grasp_rule == 'minturn':
        # the die is a cube: grasps at die_yaw + k pi/2 pinch equivalent
        # faces; take the one whose lift-pose hand is the smallest rotation
        # from home's hand (FK of the planned configurations only)
        best = None
        for kk in range(4):
            gy = die_yaw + kk * math.pi / 2
            qq = ik_any_seed(st, [cell[0], cell[1], contact + LIFT], top_down(gy))
            if qq is None:
                continue
            ang = robot_utils.quat_angle_deg(top_down(gy), args._home_orn)
            if best is None or ang < best[0]:
                best = (ang, gy, qq)
        if best is None:
            return None
        _, yaw, q = best
    else:
        if args.grasp_rule == 'wrap':
            # the pipeline's M9 rule for a near-square footprint
            # (pose_belief.fitted_grasp_candidates): the quarter-turn class
            # wrapped into [-pi/4, pi/4)
            yaw = float((die_yaw + math.pi / 4) % (math.pi / 2) - math.pi / 4)
        q = ik_any_seed(st, [cell[0], cell[1], contact + LIFT], top_down(yaw))
    if q is None:
        return None
    q_lift = np.asarray(q.joint_positions, dtype=float)
    synth = None
    if args.path in ('pitchy', 'pitchx', 'spinz'):
        # a pure rotation of the hand about its own y (the pinch axis), x or
        # z (the approach axis) at the lift position, 1 deg per waypoint;
        # IK computed before the die exists (_pybullet_ik resets joints)
        axis = {'pitchy': [0, 1, 0], 'pitchx': [1, 0, 0], 'spinz': [0, 0, 1]}[args.path]
        pos0 = [cell[0], cell[1], contact + LIFT]
        orn0 = top_down(yaw).tolist()
        synth, seed = [q_lift.tolist()], q_lift.tolist()
        for deg in range(1, int(args.angle) + 1):
            dq = p.getQuaternionFromAxisAngle(axis, math.radians(deg))
            orn = p.multiplyTransforms([0, 0, 0], orn0, [0, 0, 0], dq)[1]
            got = st._pybullet_ik(np.asarray(pos0), np.asarray(orn), seed=seed)
            if got is None:
                break
            seed = list(got.joint_positions)
            synth.append(seed)
        if len(synth) < 3:
            return None
    if args.path in ('pitchspin', 'spinpitch'):
        # two pure rotations in sequence: pitch about the pinch axis by
        # --pitch deg and spin about the approach axis by --angle deg, in
        # either order, 1 deg per waypoint, at the lift position
        pos0 = [cell[0], cell[1], contact + LIFT]
        orn = top_down(yaw).tolist()
        seq = [([0, 1, 0], args.pitch), ([0, 0, 1], args.angle)]
        if args.path == 'spinpitch':
            seq = seq[::-1]
        synth, seed = [q_lift.tolist()], q_lift.tolist()
        for axis, total in seq:
            n = int(round(abs(total)))
            step = math.copysign(1.0, total)
            for _ in range(n):
                dq = p.getQuaternionFromAxisAngle(axis, math.radians(step))
                orn = p.multiplyTransforms([0, 0, 0], orn, [0, 0, 0], dq)[1]
                got = st._pybullet_ik(np.asarray(pos0), np.asarray(orn), seed=seed)
                if got is None:
                    return None
                seed = list(got.joint_positions)
                synth.append(seed)
    pinch_half = ext[0] / 2
    aperture = min(task_spec.FINGER_OPEN, pinch_half + 0.008)
    for j, v in zip(model.arm_joints, q_lift):
        p.resetJointState(rb, j, float(v), physicsClientId=cid)
        p.setJointMotorControl2(rb, j, p.POSITION_CONTROL, targetPosition=float(v),
                                force=240, physicsClientId=cid)
    for fj in model.finger_joints:
        p.resetJointState(rb, fj, aperture, physicsClientId=cid)
        p.setJointMotorControl2(rb, fj, p.POSITION_CONTROL, targetPosition=aperture,
                                force=FORCE, physicsClientId=cid)
    body, _, mass, inertia = _make_body(args.payload, client, cid)
    p.changeDynamics(body, -1, lateralFriction=task_spec.OBJECT_LATERAL_FRICTION,
                     physicsClientId=cid)
    orn = p.getQuaternionFromEuler([math.radians(tilt_deg), 0.0, true_yaw])
    p.resetBasePositionAndOrientation(body, [0, 0, 1.0], orn, physicsClientId=cid)
    ee = np.asarray(p.getLinkState(rb, model.ee_link, computeForwardKinematics=True,
                                   physicsClientId=cid)[0])
    lo, hi = (np.asarray(v) for v in p.getAABB(body, physicsClientId=cid))
    centre = (lo + hi) / 2
    dz = args.grasp_dz
    target = np.array([ee[0], ee[1], ee[2] + h - contact - (hi[2] - centre[2]) + dz])
    p.resetBasePositionAndOrientation(body, (np.array([0, 0, 1.0]) + target - centre).tolist(),
                                      orn, physicsClientId=cid)
    half = robot_utils.close_gripper_until_contact(rb, force=FORCE, squeeze=args.squeeze_mm / 1e3)
    if half is None:
        p.removeBody(body, physicsClientId=cid)
        return {'trial': k, 'grip': False}
    p.changeDynamics(body, -1, mass=mass, localInertiaDiagonal=inertia, physicsClientId=cid)
    for _ in range(SETTLE):
        p.stepSimulation(physicsClientId=cid)
    rec = Recorder(rb, body, cid, model)
    b0, f0 = rec.pads()
    # the pinch geometry: contact points in the hand frame (mm), per pad
    eep, eeo = rec._ee()[:2]
    inv = p.invertTransform(eep.tolist(), eeo.tolist())
    bp, _ = p.getBasePositionAndOrientation(body, physicsClientId=cid)
    com_h = np.asarray(p.multiplyTransforms(inv[0], inv[1], bp, [0, 0, 0, 1])[0])
    contacts = []
    for c in p.getContactPoints(bodyA=rb, bodyB=body, physicsClientId=cid):
        if c[3] in model.finger_joints:
            ph = p.multiplyTransforms(inv[0], inv[1], c[5], [0, 0, 0, 1])[0]
            contacts.append([int(c[3])] + [round(1e3 * v, 1) for v in ph] + [round(c[9], 2)])
    if not b0:
        p.removeBody(body, physicsClientId=cid)
        return {'trial': k, 'grip': False}
    if synth is not None:
        wps = synth
        home = np.asarray(synth[-1], dtype=float)
    elif args.path == 'via':
        wps = via_wps(q_lift, home)
    else:
        wps = linear_wps(q_lift, home)
    ex = args.executor
    limits = robot_utils.JOINT_VELOCITY_LIMITS
    try:
        if ex == 'pipe':
            run_pairs(rb, wps, rec)
        elif ex == 'hop':
            rec.phase = 'pairlast'
            robot_utils.move_robot_smooth(rb, home.tolist(), False, settle=False, on_step=rec.step)
            rec.phase = 'settle'
            _settle(rb, home.tolist(), rec)
        elif ex == 'slow':
            robot_utils.JOINT_VELOCITY_LIMITS = limits * args.scale
            run_pairs(rb, wps, rec, steps=int(round(30 / args.scale)))
        elif ex == 'cont':
            run_cont(rb, wps, rec, steps=args.steps)
        elif ex in ('trap', 'trapff'):
            run_trap(rb, wps, rec, args.amax, ff=(ex == 'trapff'), vscale=args.scale)
        else:
            raise ValueError(ex)
    finally:
        robot_utils.JOINT_VELOCITY_LIMITS = limits
    passed, hsteps = hold(rb, home, rec, args.hold_cap, gain=args.hold_gain)
    rec.phase = 'after'
    for _ in range(args.after):
        p.stepSimulation()
        rec.step()
    both, f = rec.pads()
    held = bool(both and sum(f) >= HELD_FORCE)
    rows = rec.rows
    move_rows = [r for r in rows if r['ph'] not in ('hold', 'after')]

    def peak(key, rs):
        return max((r[key] for r in rs), default=0.0)
    res = {'trial': k, 'grip': True, 'cell': list(cell), 'yaw': round(die_yaw, 3),
           'grasp_yaw': round(yaw, 3), 'delta_deg': args.delta_deg, 'q7_lift': round(float(q_lift[6]), 3),
           'tilt': tilt_deg, 'half_mm': round(1e3 * half, 2), 'f0': [round(v, 2) for v in f0],
           'com_hand_mm': [round(1e3 * v, 1) for v in com_h], 'contacts': contacts,
           'held': held, 'home_f': [round(v, 2) for v in f], 'home_both': both,
           'at_home': passed, 'hold_steps': hsteps, 'move_steps': len(move_rows),
           'fmin': round(min(min(r['f1'], r['f2']) for r in rows), 3),
           'fsum_min': round(min(r['f1'] + r['f2'] for r in rows), 3),
           'la_peak': peak('la', rows), 'aa_peak': peak('aa', rows),
           'qa_peak': peak('qa', rows), 'v_peak': peak('v', rows), 'w_peak': peak('w', rows),
           'tilt_peak': peak('tilt', rows), 'appr_peak': peak('appr', rows),
           'off_end': rows[-1]['off'], 'rot_end': rows[-1]['rot'],
           'off_peak': peak('off', rows), 'rot_peak': peak('rot', rows),
           'lost': rec.lost, 'slip': rec.slip,
           'hand_rot_deg': [round(float(v), 1) for v in getattr(rec, 'spin', np.zeros(3))],
           'hand_rot_abs_deg': [round(float(v), 1) for v in getattr(rec, 'spin_abs', np.zeros(3))],
           'dq7': round(float(home[6] - q_lift[6]), 3)}
    # where in the motion the peaks sit
    for key in ('la', 'aa', 'qa'):
        r = max(rows, key=lambda r: r[key])
        res[key + '_peak_at'] = r['ph']
    if args.trace and (not held or k <= 2):
        res['rows'] = rows
    p.removeBody(body, physicsClientId=cid)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--executor', default='pipe')
    ap.add_argument('--path', default='linear',
                    choices=('linear', 'via', 'pitchy', 'pitchx', 'spinz',
                             'pitchspin', 'spinpitch'))
    ap.add_argument('--pitch', type=float, default=35.0)
    ap.add_argument('--grasp-rule', default='same', choices=('same', 'minturn', 'wrap', 'flip'))
    ap.add_argument('--delta-deg', type=float, default=0.0)
    ap.add_argument('--payload', default='dice')
    ap.add_argument('--angle', type=float, default=60.0)
    ap.add_argument('--steps', type=int, default=30, help='cont: steps per pair')
    ap.add_argument('--yaws', default=None, help='comma list of yaws (rad); default five')
    ap.add_argument('--squeeze-mm', type=float, default=1e3 * robot_utils.GRIP_SQUEEZE)
    ap.add_argument('--scale', type=float, default=1.0)
    ap.add_argument('--amax', default='8.0', help='rad/s^2, or ds = the Panda datasheet per joint')
    ap.add_argument('--hold-cap', type=int, default=task_spec.HOME_HOLD_STEP_CAP)
    ap.add_argument('--hold-gain', type=float, default=None)
    ap.add_argument('--after', type=int, default=0,
                    help='extra steps after the hold (does the die leave later?)')
    ap.add_argument('--grasp-dz', type=float, default=0.0,
                    help='die offset along z against the contact rule (m)')
    ap.add_argument('--cells', type=int, default=12)
    ap.add_argument('--tilts', default='0,8')
    ap.add_argument('--trace', action='store_true')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    a.amax = (np.array([15.0, 7.5, 10.0, 12.5, 15.0, 20.0, 20.0]) if a.amax == 'ds'
              else float(a.amax))
    from tampura_environments.panda_utils.robot import DEFAULT_ARM_POS
    world, robot, client, cid, model = their_world()
    assert cid == 0
    rb = robot.body
    p.setGravity(0, 0, task_spec.GRAVITY_Z, physicsClientId=cid)
    p.setTimeStep(task_spec.TIMESTEP, physicsClientId=cid)
    for fj in model.finger_joints:
        p.changeDynamics(rb, fj, lateralFriction=task_spec.PAD_LATERAL_FRICTION,
                         physicsClientId=cid)
    home = np.asarray(DEFAULT_ARM_POS, dtype=float)
    for j, v in zip(model.arm_joints, home):
        p.resetJointState(rb, j, float(v), physicsClientId=cid)
    hs = p.getLinkState(rb, model.ee_link, computeForwardKinematics=True, physicsClientId=cid)
    a._home_orn = np.asarray(hs[1])
    print('home EE', [round(v, 3) for v in hs[0]], 'orn', [round(v, 3) for v in hs[1]],
          'top-down angle', round(robot_utils.quat_angle_deg(hs[1], top_down(0.0)), 1), flush=True)
    from boxel_data import BoxelRegistry
    from streams import BoxelStreams
    st = BoxelStreams(registry=BoxelRegistry(), robot_id=rb, physics_client=cid)
    W = {'x': list(task_spec.WINDOW_X), 'y': list(task_spec.WINDOW_Y)}
    cells = _coarse_cells(W)
    rng = np.random.RandomState(59)
    pick = rng.choice(len(cells), size=min(a.cells, len(cells)), replace=False)
    yaws = ([float(v) for v in a.yaws.split(',')] if a.yaws else
            [0.0, math.pi / 2, math.pi / 4, -math.pi / 4, math.pi / 8])
    tilts = [float(t) for t in a.tilts.split(',')]
    rows, t0, k = [], time.time(), 0
    for ci in pick:
        for yaw in yaws:
            for tilt in tilts:
                k += 1
                r = carry(k, cells[ci], yaw, tilt, a, rb, client, cid, model, home, st)
                if r is not None:
                    rows.append(r)
    done = [r for r in rows if r.get('grip')]
    held = sum(r['held'] for r in done)
    summ = {'executor': a.executor, 'path': a.path, 'scale': a.scale, 'amax': str(a.amax),
            'grasp_rule': a.grasp_rule, 'delta_deg': a.delta_deg, 'payload': a.payload,
            'squeeze_mm': a.squeeze_mm, 'hold_cap': a.hold_cap, 'hold_gain': a.hold_gain,
            'carries': len(done), 'held': held,
            'fsum_min_median': float(np.median([r['fsum_min'] for r in done])) if done else None,
            'la_peak_median': float(np.median([r['la_peak'] for r in done])) if done else None,
            'aa_peak_median': float(np.median([r['aa_peak'] for r in done])) if done else None,
            'qa_peak_median': float(np.median([r['qa_peak'] for r in done])) if done else None,
            'move_steps_median': float(np.median([r['move_steps'] for r in done])) if done else None,
            'lost_phase': [r['lost']['ph'] if r['lost'] else None for r in done if not r['held']],
            'wall_s': round(time.time() - t0, 1)}
    with open(a.out, 'w') as f:
        json.dump({'summary': summ, 'rows': rows}, f, indent=0)
    print(json.dumps(summ), flush=True)


if __name__ == '__main__':
    main()
