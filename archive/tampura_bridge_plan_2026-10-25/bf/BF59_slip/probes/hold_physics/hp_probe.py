"""BF#59 hold-physics probe (proposal phase, not pipeline code).

The pipeline's own pick and carry of their die on their empty table, with
D9's values, and a per-step record of the hold: the normal force on each
pad, the contact points per pad, the friction use |f_t| / (mu N) per pad,
the die's pose in the hand frame (offset, rotation about the pinch axis and
about the other axes), and the finger joints.

Pick (execution.execute_pick's physical steps): the arm stands over the die
at the approach altitude (contact + 0.10 m), the fingers go to the aperture
rule's opening (close_gripper, pinch half + 8 mm), the horizontal re-aim
move with settle, the vertical descent with settle, the tactile close
(close_gripper_until_contact, 60 N, the table and plane ignored), the
10 cm post-action lift (move_robot_smooth, no settle).  Carry
(test_full_pipeline's move): 'direct' streams the single segment to
DEFAULT_ARM_POS (plan_motion's fast path) with steps=30 and the endpoint
settle; 'via' inserts random via configurations first (an RRT-like
detour); then hold_at_config with HOME_HOLD_STEP_CAP, then 120 more steps.

Per trial a random draw (fixed by the trial seed, so every lever sees the
same trials): a cell of W, the grasp yaw, the die's yaw offset against the
pinch and its position offset against the grasp centre.

  cd /root/tampura-work/tampura_environments
  PYTHONPATH=$S:$TW/tampura:$TW/tampura_environments:$S/tools \
    /root/armO-venvA/bin/python hp_probe.py --lever base --trials 40 --out x.json
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np
import pybullet as p

REPO = os.environ.get('SB_REPO', '/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels')
for _d in (REPO, os.path.join(REPO, 'tools')):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import robot_utils                                   # noqa: E402
from tampura_bridge import task_spec                 # noqa: E402
from _probe_b1p2_tampura import top_down, ik_any_seed, LIFT, _coarse_cells   # noqa: E402

FORCE = 60.0
GRASP_MARGIN_FROM_TOP = 0.005
HELD_FORCE = 0.5
MU = task_spec.PAD_LATERAL_FRICTION * task_spec.OBJECT_LATERAL_FRICTION

# Levers: each a dict of options; 'base' is the pipeline as of 92d1e06.
LEVERS = {
    'base': {},
    'sq0': {'squeeze': 0.0},
    'sq1': {'squeeze': 0.001},
    'sq2': {'squeeze': 0.002},
    'sq3': {'squeeze': 0.003},
    'force5': {'hold_force': 5.0},
    'force10': {'hold_force': 10.0},
    'force20': {'hold_force': 20.0},
    'force40': {'hold_force': 40.0},
    'kp1': {'finger_kp': 1.0},
    'kp0.3': {'finger_kp': 0.3},
    'kd0.3': {'finger_kd': 0.3},
    'iters200': {'engine': {'numSolverIterations': 200}},
    'substeps4': {'engine': {'numSubSteps': 4}},
    'padk3e5': {'pad_k': 3e5, 'pad_d': 1000.0},
    'padd100': {'pad_k': 3e4, 'pad_d': 100.0},
    'padd25': {'pad_k': 3e4, 'pad_d': 25.0},
    'padrigid': {'pad_k': 1e7, 'pad_d': 1e3},
    'dieroll': {'die_rolling': 0.001},
    'diespin': {'die_spinning': 0.01},
    'dieanchor': {'die_anchor': True},
    'dieinertia10': {'die_inertia_scale': 10.0},
    'speed0.5': {'speed': 0.5},
    # added by the resumed agent
    'diespin0.1': {'die_spinning': 0.1},          # combined 0.1 x 0.1 = 0.01
    'diespin1': {'die_spinning': 1.0},            # combined 0.1
    'diespin10': {'die_spinning': 10.0},          # combined 1.0
    'roll0.01': {'die_rolling': 0.01, 'pad_rolling': 1.0},
    'padanchor0': {'pad_anchor': 0},
    'diemass10': {'die_mass_scale': 10.0},
    'diemass100': {'die_mass_scale': 100.0},
    'iters10': {'engine': {'numSolverIterations': 10}},
    'iters500': {'engine': {'numSolverIterations': 500}},
    'substeps2': {'engine': {'numSubSteps': 2}},
    'substeps8': {'engine': {'numSubSteps': 8}},
    'touch0': {'touch_tol': 0.0},
    'touch0sq0.25': {'touch_tol': 0.0, 'squeeze': 0.00025},
    'touch0sq0.1': {'touch_tol': 0.0, 'squeeze': 0.0001},
    'force2': {'hold_force': 2.0},
    'padstiff_die': {'die_k': 3e4, 'die_d': 1000.0},
    'padrigid_sq0.1': {'pad_k': 1e7, 'pad_d': 1e3, 'squeeze': 0.0001},
    # rolling, graded (combined = pad_roll x die_lat 1.0 + pad_lat 1.2 x die_roll)
    'droll0.003': {'die_rolling': 0.003},                  # 0.0036
    'droll0.01': {'die_rolling': 0.01},                    # 0.012
    'droll0.1': {'die_rolling': 0.1},                      # 0.12
    'proll0.001': {'pad_rolling': 0.001},                  # 0.001
    'proll0.01': {'pad_rolling': 0.01},                    # 0.01
    'proll0.1': {'pad_rolling': 0.1},                      # 0.1
    'tamptable': {'die_rolling': 0.01, 'die_spinning': 1.0},   # their table's set_dynamics on the die
    'droll0.01_sq1': {'die_rolling': 0.01, 'squeeze': 0.001},
    'droll0.01_sq3': {'die_rolling': 0.01, 'squeeze': 0.003},
    'droll0.01_force5': {'die_rolling': 0.01, 'hold_force': 5.0},
    'droll0.01_force10': {'die_rolling': 0.01, 'hold_force': 10.0},
    'droll0.01_force20': {'die_rolling': 0.01, 'hold_force': 20.0},
    'droll0.01_force60': {'die_rolling': 0.01, 'hold_force': 60.0},
    'proll0.01_force10': {'pad_rolling': 0.01, 'hold_force': 10.0},
    'droll0.01_speed0.5': {'die_rolling': 0.01, 'speed': 0.5},
    'diemass10_force10': {'die_mass_scale': 10.0, 'hold_force': 10.0},
    'iters500_force10': {'engine': {'numSolverIterations': 500}, 'hold_force': 10.0},
    'substeps4_force10': {'engine': {'numSubSteps': 4}, 'hold_force': 10.0},
    'dieinertia10_force10': {'die_inertia_scale': 10.0, 'hold_force': 10.0},
    'proll0.1_force10': {'pad_rolling': 0.1, 'hold_force': 10.0},
    'proll0.1_sq3': {'pad_rolling': 0.1, 'squeeze': 0.003},
    'proll0.01_sq3': {'pad_rolling': 0.01, 'squeeze': 0.003},
    'iters100_force10': {'engine': {'numSolverIterations': 100}, 'hold_force': 10.0},
    'iters200_force10': {'engine': {'numSolverIterations': 200}, 'hold_force': 10.0},
    'iters300_force10': {'engine': {'numSolverIterations': 300}, 'hold_force': 10.0},
    'iters200_force20': {'engine': {'numSolverIterations': 200}, 'hold_force': 20.0},
    'iters500_force20': {'engine': {'numSolverIterations': 500}, 'hold_force': 20.0},
    'iters500_force40': {'engine': {'numSolverIterations': 500}, 'hold_force': 40.0},
    'iters200_force5': {'engine': {'numSolverIterations': 200}, 'hold_force': 5.0},
    'iters500_force5': {'engine': {'numSolverIterations': 500}, 'hold_force': 5.0},
    'iters500_sq3': {'engine': {'numSolverIterations': 500}, 'squeeze': 0.003},
    'iters500_sq1': {'engine': {'numSolverIterations': 500}, 'squeeze': 0.001},
    'iters500_force10_proll0.01': {'engine': {'numSolverIterations': 500}, 'hold_force': 10.0,
                                   'pad_rolling': 0.01},
    'iters200_force10_proll0.01': {'engine': {'numSolverIterations': 200}, 'hold_force': 10.0,
                                   'pad_rolling': 0.01},
    'iters100_force5': {'engine': {'numSolverIterations': 100}, 'hold_force': 5.0},
    'iters100_force20': {'engine': {'numSolverIterations': 100}, 'hold_force': 20.0},
    'iters200_force60': {'engine': {'numSolverIterations': 200}, 'hold_force': 60.0},
    'gear': {'gear': True},
    'gear_iters200': {'gear': True, 'engine': {'numSolverIterations': 200}},
    'gear_force5': {'gear': True, 'hold_force': 5.0},
    'gear_force10': {'gear': True, 'hold_force': 10.0},
    'gear_force20': {'gear': True, 'hold_force': 20.0},
    'gear_iters200_force5': {'gear': True, 'hold_force': 5.0, 'engine': {'numSolverIterations': 200}},
    'gear_iters200_force10': {'gear': True, 'hold_force': 10.0, 'engine': {'numSolverIterations': 200}},
    'gear_iters200_force20': {'gear': True, 'hold_force': 20.0, 'engine': {'numSolverIterations': 200}},
    'gear_sq1': {'gear': True, 'squeeze': 0.001},
    'gear_iters200_sq1': {'gear': True, 'squeeze': 0.001, 'engine': {'numSolverIterations': 200}},
    'force1': {'hold_force': 1.0},
    'force3': {'hold_force': 3.0},
}


def close_until_contact(rb, force, squeeze, ignore, tol, step=0.0005, max_steps=240):
    """robot_utils.close_gripper_until_contact with the contact tolerance as a
    parameter (the pipeline's is 0.5 mm); same law otherwise."""
    model = robot_utils.robot_model()
    fingers = model.finger_joints
    target = min(p.getJointState(rb, fj)[0] for fj in fingers)
    for _ in range(max_steps):
        target = max(0.0, target - step)
        for fj in fingers:
            p.setJointMotorControl2(rb, fj, p.POSITION_CONTROL, targetPosition=target, force=force)
        p.stepSimulation()
        pads = set()
        for c in p.getContactPoints(bodyA=rb):
            if c[3] in fingers and c[2] != rb and c[2] not in ignore and c[8] <= tol:
                pads.add(c[3])
        fpos = [p.getJointState(rb, fj)[0] for fj in fingers]
        if pads == set(fingers):
            width = float(np.mean(fpos))
            hold = max(0.0, width - squeeze)
            for _ in range(60):
                for fj in fingers:
                    p.setJointMotorControl2(rb, fj, p.POSITION_CONTROL, targetPosition=hold, force=force)
                p.stepSimulation()
            return width
        if target <= 0.0 and max(fpos) <= 0.0015:
            break
    return None


def their_world():
    from tampura_environments.find_dice.env import setup_world
    from tampura_environments.panda_utils.panda_env_utils import setup_robot
    robot, client = setup_robot(vis=False)
    world = setup_world(robot, client, [], [])
    cid = client._client
    model = robot_utils.resolve_robot_model(robot.body, cid)
    robot_utils.use_robot_model(model)
    return world, robot, client, cid, model


def ee_frame(rb, model):
    ls = p.getLinkState(rb, model.ee_link, computeLinkVelocity=1, computeForwardKinematics=True)
    pos = np.asarray(ls[0])
    R = np.asarray(p.getMatrixFromQuaternion(ls[1])).reshape(3, 3)
    return pos, R, np.asarray(ls[6]), np.asarray(ls[7])


def rot_angle(R):
    c = max(-1.0, min(1.0, (np.trace(R) - 1) / 2))
    return math.degrees(math.acos(c))


def sample(rng, cells):
    cell = cells[int(rng.integers(len(cells)))]
    return {'cell': [float(cell[0]), float(cell[1])],
            'grasp_yaw': float(rng.uniform(-math.pi / 2, math.pi / 2)),
            'die_dyaw_deg': float(rng.uniform(-10, 10)),
            'die_dxy_mm': [float(rng.uniform(-2, 2)), float(rng.uniform(-2, 2))],
            'via_seed': int(rng.integers(1 << 30))}


def trial(k, draw, lev, ctx, carry_mode, n_via, keep_trace):
    rb, cid, model, st, home, table_ids = (ctx[n] for n in
                                           ('rb', 'cid', 'model', 'st', 'home', 'static'))
    from tampura_environments.panda_utils.panda_env_utils import create_ycb
    bspec = ctx['body']
    if bspec['kind'] == 'ycb':
        ext = task_spec.CLASS_EXTENTS[bspec['name']]
    else:
        ext = tuple(bspec['ext'])
    h = ext[2]
    contact = max(h - GRASP_MARGIN_FROM_TOP, task_spec.PICK_CONTACT_FLOOR)
    gyaw = draw['grasp_yaw']
    orn = top_down(gyaw)
    cx, cy = draw['cell']
    q_above = ik_any_seed(st, [cx, cy, contact + LIFT], orn)
    if q_above is None:
        return {'trial': k, 'ik': False}
    # the arm over the die, fingers fully open (the pipeline arrives so)
    for j, v in zip(model.arm_joints, q_above.joint_positions):
        p.resetJointState(rb, j, float(v))
        p.setJointMotorControl2(rb, j, p.POSITION_CONTROL, targetPosition=float(v), force=240)
    for fj in model.finger_joints:
        p.resetJointState(rb, fj, task_spec.FINGER_OPEN)
        p.setJointMotorControl2(rb, fj, p.POSITION_CONTROL, targetPosition=task_spec.FINGER_OPEN,
                                force=FORCE)
    # the die on the table, its yaw = grasp yaw + offset (the pinch is along
    # the hand's y axis; a die face normal along it at offset 0)
    if bspec['kind'] == 'ycb':
        body = create_ycb(bspec['name'], client=ctx['client'], use_concave=True)
        mass0 = task_spec.CLASS_MASS_KG[bspec['name']]
        inertia0 = task_spec.CLASS_INERTIA_DIAG[bspec['name']]
    else:
        # a box primitive (our scenes' cubes, or the die as a sharp box)
        he = [e / 2 for e in ext]
        mass0 = bspec['mass']
        body = p.createMultiBody(mass0, p.createCollisionShape(p.GEOM_BOX, halfExtents=he))
        inertia0 = p.getDynamicsInfo(body, -1)[2]
    inertia = [v * lev.get('die_inertia_scale', 1.0) for v in inertia0]
    ms = lev.get('die_mass_scale', 1.0)
    inertia = [v * ms for v in inertia]
    p.changeDynamics(body, -1, mass=mass0 * ms, localInertiaDiagonal=inertia,
                     lateralFriction=task_spec.OBJECT_LATERAL_FRICTION)
    if 'die_k' in lev:
        p.changeDynamics(body, -1, contactStiffness=lev['die_k'], contactDamping=lev['die_d'])
    if 'die_rolling' in lev:
        p.changeDynamics(body, -1, rollingFriction=lev['die_rolling'])
    if 'die_spinning' in lev:
        p.changeDynamics(body, -1, spinningFriction=lev['die_spinning'])
    if lev.get('die_anchor'):
        p.changeDynamics(body, -1, frictionAnchor=1)
    dyaw = math.radians(draw['die_dyaw_deg'])
    dorn = p.getQuaternionFromEuler([0, 0, gyaw + dyaw])
    p.resetBasePositionAndOrientation(body, [0, 0, 1.0], dorn)
    lo, hi = (np.asarray(v) for v in p.getAABB(body))
    base_pos = np.array([0, 0, 1.0])
    ctr = (lo + hi) / 2
    tgt = np.array([cx + 1e-3 * draw['die_dxy_mm'][0], cy + 1e-3 * draw['die_dxy_mm'][1],
                    (hi[2] - lo[2]) / 2 + 0.0005])
    p.resetBasePositionAndOrientation(body, (base_pos + tgt - ctr).tolist(), dorn)
    for _ in range(120):
        p.stepSimulation()
    # the pick: aperture, re-aim (already above), descent, tactile close
    pinch_half = ext[0] / 2
    robot_utils.close_gripper(rb, False, target_finger_pos=min(task_spec.FINGER_OPEN,
                                                               pinch_half + 0.008))
    robot_utils.move_robot_smooth(rb, q_above.joint_positions, False, settle=True)
    q_contact = robot_utils.solve_ik(rb, np.array([cx, cy, contact]), orn, cid,
                                     seed=q_above.joint_positions)
    if q_contact is None:
        p.removeBody(body)
        return {'trial': k, 'ik': False}
    robot_utils.move_robot_smooth(rb, q_contact, False, settle=True)
    squeeze = lev.get('squeeze', robot_utils.GRIP_SQUEEZE)
    if 'touch_tol' in lev:
        half = close_until_contact(rb, FORCE, squeeze, table_ids, lev['touch_tol'])
    else:
        half = robot_utils.close_gripper_until_contact(rb, False, force=FORCE, squeeze=squeeze,
                                                       ignore_body_ids=table_ids)
    row = {'trial': k, 'ik': True, **draw, 'half_mm': None if half is None else round(1e3 * half, 2)}
    if half is None:
        row.update(grip=False)
        p.removeBody(body)
        return row
    # hold-mode levers act after the close (the close itself is unchanged)
    fpos = [p.getJointState(rb, fj)[0] for fj in model.finger_joints]
    if 'hold_force' in lev:
        for fj in model.finger_joints:
            p.setJointMotorControl2(rb, fj, p.POSITION_CONTROL,
                                    targetPosition=max(0.0, half - 0.004), force=lev['hold_force'])
    if 'finger_kp' in lev or 'finger_kd' in lev:
        for fj in model.finger_joints:
            p.setJointMotorControl2(rb, fj, p.POSITION_CONTROL,
                                    targetPosition=max(0.0, half - squeeze), force=FORCE,
                                    positionGain=lev.get('finger_kp', 0.1),
                                    velocityGain=lev.get('finger_kd', 1.0))
    # the hand frame reference after the close
    pe, Re, _, _ = ee_frame(rb, model)
    dp, do = p.getBasePositionAndOrientation(body)
    Rd = np.asarray(p.getMatrixFromQuaternion(do)).reshape(3, 3)
    rel0_R = Re.T @ Rd
    rel0_p = Re.T @ (np.asarray(dp) - pe)
    pads = list(model.finger_joints)
    S = {'n': 0, 'phase': 'close', 'nf_min': [1e9, 1e9], 'nf_min_carry': [1e9, 1e9],
         'util_max': 0.0, 'lost': None, 'trace': [], 'max_off_mm': 0.0, 'max_pinch_rot': 0.0,
         'max_other_rot': 0.0, 'npts_min': [99, 99], 'max_acc': 0.0, 'v_prev': None,
         'flicker': 0, 'max_rot_axis': [0.0, 0.0, 0.0], 'nf_max_carry': 0.0, 'fw_max': 0.0,
         'tilt_max': 0.0, 'tilt_sum': 0.0, 'tilt_w': 0.0}

    def record():
        S['n'] += 1
        cs = p.getContactPoints(bodyA=rb, bodyB=body)
        nf, npts, ft, util = [0.0, 0.0], [0, 0], [0.0, 0.0], [0.0, 0.0]
        cz = [[], []]
        pe, Re, v, w = ee_frame(rb, model)
        for c in cs:
            if c[3] in pads:
                i = pads.index(c[3])
                nf[i] += c[9]
                npts[i] += 1
                ft[i] += math.hypot(c[10], c[12])
                cz[i].append((Re.T @ (np.asarray(c[5]) - pe)).tolist())
                if c[9] > 0.2 and S['phase'] in ('carry', 'hold', 'settle', 'lift'):
                    tilt = math.degrees(math.acos(min(1.0, abs(float(np.dot(c[7], Re[:, 1]))))))
                    S['tilt_max'] = max(S['tilt_max'], tilt)
                    S['tilt_sum'] += tilt * c[9]
                    S['tilt_w'] += c[9]
        for i in range(2):
            util[i] = ft[i] / (MU * nf[i]) if nf[i] > 1e-6 else (9.9 if ft[i] > 0 else 0.0)
        dp, do = p.getBasePositionAndOrientation(body)
        Rd = np.asarray(p.getMatrixFromQuaternion(do)).reshape(3, 3)
        # the die's rotation since the close, expressed in the hand frame
        relR = (Re.T @ Rd) @ rel0_R.T
        relp = Re.T @ (np.asarray(dp) - pe) - rel0_p
        ang = rot_angle(relR)
        # rotation about the pinch axis (hand y) from the rotation vector
        rv = np.array([relR[2, 1] - relR[1, 2], relR[0, 2] - relR[2, 0], relR[1, 0] - relR[0, 1]])
        nrm = np.linalg.norm(rv)
        axis = rv / nrm if nrm > 1e-9 else np.zeros(3)
        pinch_rot = ang * abs(axis[1])
        other_rot = ang * math.hypot(axis[0], axis[2])
        if S['phase'] in ('carry', 'hold'):
            for i in range(3):
                S['max_rot_axis'][i] = max(S['max_rot_axis'][i], ang * abs(axis[i]))
        off = 1e3 * float(np.linalg.norm(relp))
        if S['phase'] in ('carry', 'hold'):
            S['max_off_mm'] = max(S['max_off_mm'], off)
            S['max_pinch_rot'] = max(S['max_pinch_rot'], pinch_rot)
            S['max_other_rot'] = max(S['max_other_rot'], other_rot)
        if S['phase'] != 'close':
            for i in range(2):
                S['nf_min'][i] = min(S['nf_min'][i], nf[i])
                S['npts_min'][i] = min(S['npts_min'][i], npts[i])
                if S['phase'] in ('carry', 'hold'):
                    S['nf_min_carry'][i] = min(S['nf_min_carry'][i], nf[i])
            if min(npts) == 0:
                S['flicker'] += 1
            if nf[0] > 0.05 and nf[1] > 0.05:
                S['util_max'] = max(S['util_max'], max(util))
        if S['v_prev'] is not None:
            S['max_acc'] = max(S['max_acc'], float(np.linalg.norm(v - S['v_prev'])) * 240.0)
        S['v_prev'] = v
        fj = [p.getJointState(rb, j) for j in pads]
        if S['phase'] in ('carry', 'hold') and S['lost'] is None:
            S['nf_max_carry'] = max(S['nf_max_carry'], max(nf))
            S['fw_max'] = max(S['fw_max'], 1e3 * (np.mean([s[0] for s in fj]) - np.mean(fpos)))
        rowt = {'n': S['n'], 'ph': S['phase'], 'nf': [round(x, 3) for x in nf], 'np': npts,
                'util': [round(x, 3) for x in util], 'off_mm': round(off, 2),
                'relp_mm': [round(1e3 * x, 2) for x in relp], 'pinch_rot': round(pinch_rot, 2),
                'other_rot': round(other_rot, 2), 'q_f_mm': [round(1e3 * s[0], 3) for s in fj],
                'v_f_mms': [round(1e3 * s[1], 2) for s in fj],
                'tau_f': [round(s[3], 2) for s in fj],
                'cpts': [[[round(1e3 * x, 1) for x in q] for q in cz[i]] for i in range(2)]}
        if S['lost'] is None and S['phase'] != 'close' and (min(npts) == 0 or off > 5.0):
            S['lost'] = {'n': S['n'], 'phase': S['phase'], 'off_mm': round(off, 2),
                         'pinch_rot': round(pinch_rot, 1), 'other_rot': round(other_rot, 1),
                         'nf': rowt['nf'], 'np': npts, 'relp_mm': rowt['relp_mm']}
        if keep_trace:
            S['trace'].append(rowt)

    S['phase'] = 'settle'
    record()
    nf0 = None
    # the post-action lift (the pick's 10 cm, no settle)
    S['phase'] = 'lift'
    lift = robot_utils.solve_ik(rb, np.array([cx, cy, contact + LIFT]), orn, cid, seed=q_contact)
    if lift is not None:
        robot_utils.move_robot_smooth(rb, lift, False, on_step=record)
    lifted_ok = S['lost'] is None
    # the carry
    S['phase'] = 'carry'
    limits = robot_utils.JOINT_VELOCITY_LIMITS
    robot_utils.JOINT_VELOCITY_LIMITS = limits * lev.get('speed', 1.0)
    try:
        q_now = np.array([p.getJointState(rb, j)[0] for j in model.arm_joints])
        wps = []
        if carry_mode == 'line':
            # the pipeline's carry home: plan_motion's shortcut path is the
            # straight joint line, cut into n_via + 1 equal waypoint pairs
            # (loss_dynamics' carry.jsonl: 9 pairs with identical dq)
            for i in range(1, n_via + 1):
                a = i / (n_via + 1)
                wps.append((1 - a) * q_now + a * home)
        if carry_mode == 'via':
            r2 = np.random.default_rng(draw['via_seed'])
            for i in range(1, n_via + 1):
                a = i / (n_via + 1)
                q = (1 - a) * q_now + a * home + r2.normal(0, 0.25, 7)
                q = np.clip(q, robot_utils.JOINT_LIMITS_LOW + 0.05, robot_utils.JOINT_LIMITS_HIGH - 0.05)
                wps.append(q)
        wps.append(home)
        for i, q in enumerate(wps):
            robot_utils.move_robot_smooth(rb, list(q), False, steps=30, settle=(i == len(wps) - 1),
                                          on_step=record)
    finally:
        robot_utils.JOINT_VELOCITY_LIMITS = limits
    S['phase'] = 'hold'
    arm = model.arm_joints
    # hold_at_config with the probe's record on every step (same law)
    tgt = np.asarray(home, dtype=float)
    steps = 0
    while True:
        cur = np.array([p.getJointState(rb, j)[0] for j in arm])
        if np.allclose(cur, tgt, rtol=1e-4, atol=1e-4) or steps >= task_spec.HOME_HOLD_STEP_CAP:
            break
        for kk, j in enumerate(arm):
            p.setJointMotorControl2(rb, j, p.POSITION_CONTROL, targetPosition=float(tgt[kk]), force=240)
        p.stepSimulation()
        record()
        steps += 1
    cs = p.getContactPoints(bodyA=rb, bodyB=body)
    links = {c[3] for c in cs if c[3] in pads}
    nf_home = sum(c[9] for c in cs if c[3] in pads)
    held = links == set(pads) and nf_home >= HELD_FORCE
    finger_home = [round(1e3 * p.getJointState(rb, fj)[0], 3) for fj in pads]
    S['phase'] = 'after'
    for _ in range(120):
        p.stepSimulation()
        record()
    cs = p.getContactPoints(bodyA=rb, bodyB=body)
    links2 = {c[3] for c in cs if c[3] in pads}
    held_after = links2 == set(pads) and sum(c[9] for c in cs if c[3] in pads) >= HELD_FORCE
    row.update(grip=True, lifted_ok=lifted_ok, held=bool(held), held_after=bool(held_after),
               nf_home=round(nf_home, 3), lost=S['lost'], n_wps=len(wps),
               finger_mm=[round(1e3 * x, 3) for x in fpos], finger_home_mm=finger_home,
               nf_min=[round(x, 3) for x in S['nf_min']],
               nf_min_carry=[round(x, 3) for x in S['nf_min_carry']],
               npts_min=S['npts_min'], flicker_steps=S['flicker'],
               util_max=round(S['util_max'], 3), max_off_mm=round(S['max_off_mm'], 2),
               max_pinch_rot=round(S['max_pinch_rot'], 2),
               max_other_rot=round(S['max_other_rot'], 2), max_ee_acc=round(S['max_acc'], 2),
               max_rot_xyz=[round(x, 1) for x in S['max_rot_axis']],
               nf_max_carry=round(S['nf_max_carry'], 2), widen_max_mm=round(S['fw_max'], 3),
               tilt_max=round(S['tilt_max'], 1),
               tilt_mean=round(S['tilt_sum'] / S['tilt_w'], 1) if S['tilt_w'] > 0 else None,
               steps=S['n'])
    if keep_trace:
        row['trace'] = S['trace']
    p.removeBody(body)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lever', default='base')
    ap.add_argument('--trials', type=int, default=40)
    ap.add_argument('--first', type=int, default=0)
    ap.add_argument('--carry', default='line', choices=('direct', 'via', 'line'))
    ap.add_argument('--n-via', type=int, default=8)
    ap.add_argument('--trace', default='', help='comma list of trial ids to trace, or all')
    ap.add_argument('--out', required=True)
    ap.add_argument('--body', default='dice',
                    help='a task_spec class (dice, a_cups_ud ..), cube40_<kg>, or boxdie')
    a = ap.parse_args()
    lev = LEVERS[a.lever]
    from tampura_environments.panda_utils.robot import DEFAULT_ARM_POS
    world, robot, client, cid, model = their_world()
    assert cid == 0
    rb = robot.body
    p.setGravity(0, 0, task_spec.GRAVITY_Z)
    p.setTimeStep(task_spec.TIMESTEP)
    for fj in model.finger_joints:
        p.changeDynamics(rb, fj, lateralFriction=task_spec.PAD_LATERAL_FRICTION)
        if 'pad_k' in lev:
            p.changeDynamics(rb, fj, contactStiffness=lev['pad_k'], contactDamping=lev['pad_d'])
        if 'pad_anchor' in lev:
            p.changeDynamics(rb, fj, frictionAnchor=lev['pad_anchor'])
        if 'pad_rolling' in lev:
            p.changeDynamics(rb, fj, rollingFriction=lev['pad_rolling'])
    if 'engine' in lev:
        p.setPhysicsEngineParameter(**lev['engine'])
    if lev.get('gear'):
        # the URDF's <mimic joint="panda_finger_joint1"/> realised as a gear
        # constraint (gearRatio -1 keeps q1 = q2, gear_test.py)
        f1, f2 = model.finger_joints
        gc = p.createConstraint(rb, f1, rb, f2, jointType=p.JOINT_GEAR, jointAxis=[1, 0, 0],
                                parentFramePosition=[0, 0, 0], childFramePosition=[0, 0, 0])
        p.changeConstraint(gc, gearRatio=-1, erp=0.1, maxForce=lev.get('gear_force', 50.0))
    static = frozenset(b for b in range(p.getNumBodies()) if b != rb)
    home = np.asarray(DEFAULT_ARM_POS, dtype=float)
    from boxel_data import BoxelRegistry
    from streams import BoxelStreams
    st = BoxelStreams(registry=BoxelRegistry(), robot_id=rb, physics_client=cid)
    cells = _coarse_cells({'x': list(task_spec.WINDOW_X), 'y': list(task_spec.WINDOW_Y)})
    if a.body in task_spec.CLASS_EXTENTS:
        bspec = {'kind': 'ycb', 'name': a.body}
    elif a.body.startswith('cube40_'):
        bspec = {'kind': 'box', 'ext': (0.04, 0.04, 0.04), 'mass': float(a.body.split('_')[1])}
    elif a.body == 'boxdie':
        bspec = {'kind': 'box', 'ext': task_spec.CLASS_EXTENTS['dice'],
                 'mass': task_spec.CLASS_MASS_KG['dice']}
    else:
        raise SystemExit(f'unknown body {a.body}')
    ctx = dict(rb=rb, cid=cid, model=model, st=st, home=home, static=static, client=client,
               body=bspec)
    tr = set(range(10 ** 6)) if a.trace == 'all' else {int(x) for x in a.trace.split(',') if x}
    rows, t0 = [], time.time()
    for k in range(a.first, a.first + a.trials):
        rng = np.random.default_rng(1000 + k)
        draw = sample(rng, cells)
        r = trial(k, draw, lev, ctx, a.carry, a.n_via, k in tr)
        rows.append(r)
    done = [r for r in rows if r.get('grip')]
    summ = {'lever': a.lever, 'body': a.body, 'carry': a.carry, 'trials': len(rows), 'grips': len(done),
            'held': sum(r['held'] for r in done), 'held_after': sum(r['held_after'] for r in done),
            'lost_in_lift': sum(not r['lifted_ok'] for r in done),
            'wall_s': round(time.time() - t0, 1)}
    if done:
        summ['nf_home_median'] = float(np.median([r['nf_home'] for r in done]))
        summ['nf_min_carry_median'] = float(np.median([min(r['nf_min_carry']) for r in done]))
    with open(a.out, 'w') as f:
        json.dump({'lever': a.lever, 'params': lev, 'summary': summ, 'rows': rows}, f)
    print(json.dumps(summ), flush=True)


if __name__ == '__main__':
    main()
