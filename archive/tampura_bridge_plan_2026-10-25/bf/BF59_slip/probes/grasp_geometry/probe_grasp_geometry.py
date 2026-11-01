"""BF#59 grasp-geometry probe (physics only, no planner, no lock).

Their empty table, their Panda, their die (create_ycb, the vhacd hull), D9's
gravity, timestep, masses and frictions, as tools/_probe_q14_grip.py.  Unlike
Q14's probe the die is DYNAMIC and rests on the table before the pick, and
the hand reaches it the way execute_pick does:

  arm at the contact pose + 0.10 m (top-down, hand yaw psi), fingers at the
  pre-grasp aperture (pinch half 8.9 mm + 8 mm), the die resting at yaw
  psi + delta (+ k * 90 deg) with a lateral offset (dx across the pinch, dy
  along it) from the hand's axis; vertical descent to contact_z (est top -
  5 mm, never below PICK_CONTACT_FLOOR) with move_robot_smooth(settle=True);
  close_gripper_until_contact(60 N, GRIP_SQUEEZE, table and plane ignored);
  the grip check (both pads); the 10 cm lift (move_robot_smooth, no settle,
  as _apply_post_action_lift); the re-verify; move_robot_smooth to
  DEFAULT_ARM_POS (settle) and hold_at_config(HOME_HOLD_STEP_CAP).
  HELD = both pads, summed normal force >= 0.5 N (the goal check).

Recorded per trial: the measured half-width, the pad force, the contact
points on the die in the die's frame (height above the COM, offset across
the pinch, count per pad), the die's yaw relative to the hand after the
close, after the lift and at the loss, the minimum pad force in the carry
and the step of the loss.

  cd /root/tampura-work/tampura_environments
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<repo>:<repo>/tools:/root/tampura-work/tampura:. \\
    /root/armO-venvA/bin/python <this file> --out <json> [--deltas 0,5,10] \\
    [--dx 0,2] [--cells 4] [--squeeze-mm 0.5] [--floor-mm 13.2] [--margin-mm 5]
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
from _probe_b1p2_tampura import their_empty_world, top_down, ik_any_seed   # noqa: E402

FORCE = 60.0
HELD_FORCE = 0.5
DIE_HALF = 0.0089
# payload: (side, height, mass, inertia diagonal); the die from D9, our 40 mm
# cube class (boxel_env ObjectSpec, 0.1 kg, as _probe_q14_grip.OURS)
_c = 0.04
PAYLOADS = {'dice': (0.0175, 0.0178, task_spec.CLASS_MASS_KG['dice'],
                     task_spec.CLASS_INERTIA_DIAG['dice']),
            'cube40': (_c, _c, 0.1, (0.1 * 2 * _c * _c / 12,) * 3)}
CELLS = [(0.673, 0.216), (0.592, -0.242), (0.50, 0.05), (0.42, -0.10),
         (0.60, 0.30), (0.45, 0.25), (0.65, -0.05), (0.38, 0.12)]


def yaw_of(q):
    return p.getEulerFromQuaternion(q)[2]


def wrap_deg(a):
    return (a + 45.0) % 90.0 - 45.0


def pads(rb, body, cid, fingers):
    cs = p.getContactPoints(bodyA=rb, bodyB=body, physicsClientId=cid)
    links = {c[3] for c in cs if c[3] in fingers}
    nf = sum(c[9] for c in cs if c[3] in fingers)
    return links == set(fingers), float(nf), cs


def die_state(body, rb, ee_link, cid, hand_yaw):
    pos, orn = p.getBasePositionAndOrientation(body, physicsClientId=cid)
    rot = np.asarray(p.getMatrixFromQuaternion(orn)).reshape(3, 3)
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(rot[2, 2])))))
    ee = np.asarray(p.getLinkState(rb, ee_link, computeForwardKinematics=True,
                                   physicsClientId=cid)[0])
    rel = wrap_deg(math.degrees(yaw_of(orn) - hand_yaw))
    return {'rel_yaw_deg': round(rel, 2), 'tilt_deg': round(tilt, 2),
            'z_rel_ee_mm': round(1e3 * (pos[2] - ee[2]), 2),
            'dist_mm': round(1e3 * float(np.linalg.norm(np.asarray(pos) - ee)), 1)}


def contact_geometry(cs, body, cid, fingers):
    """Contact points on the die in the die's frame, per pad."""
    pos, orn = p.getBasePositionAndOrientation(body, physicsClientId=cid)
    inv_p, inv_q = p.invertTransform(pos, orn)
    out = {}
    for fj in fingers:
        pts = []
        for c in cs:
            if c[3] != fj:
                continue
            local = p.multiplyTransforms(inv_p, inv_q, c[6], [0, 0, 0, 1])[0]
            pts.append({'xyz_mm': [round(1e3 * v, 2) for v in local],
                        'world_rel_mm': [round(1e3 * (c[6][i] - pos[i]), 2) for i in range(3)],
                        'z_world_mm': round(1e3 * c[6][2], 2),
                        'nf': round(c[9], 2), 'dist_mm': round(1e3 * c[8], 3)})
        out[str(fj)] = pts
    return out


def trial(cell, delta_deg, k90, dx, dy, a, rb, cid, model, st, home, static_ids):
    fingers = model.finger_joints
    hand_yaw = math.radians(a.hand_yaw_deg)
    orn_h = top_down(hand_yaw)
    side, top, mass, inertia = PAYLOADS[a.payload]
    contact_z = max(top - a.margin_mm / 1e3, a.floor_mm / 1e3)
    q_above = ik_any_seed(st, [cell[0], cell[1], contact_z + 0.10], orn_h)
    if q_above is None:
        return {'cell': cell, 'ik': False}
    dr = math.radians(delta_deg)
    half_along = 0.5 * side * (abs(math.cos(dr)) + abs(math.sin(dr)))
    if a.aperture_sized:
        aperture = min(task_spec.FINGER_OPEN, half_along + 0.008)
    else:
        aperture = min(task_spec.FINGER_OPEN, DIE_HALF + 0.008)
    for j, v in zip(model.arm_joints, q_above.joint_positions):
        p.resetJointState(rb, j, float(v), physicsClientId=cid)
        p.setJointMotorControl2(rb, j, p.POSITION_CONTROL, targetPosition=float(v),
                                force=240, physicsClientId=cid)
    for fj in fingers:
        p.resetJointState(rb, fj, aperture, physicsClientId=cid)
        p.setJointMotorControl2(rb, fj, p.POSITION_CONTROL, targetPosition=aperture,
                                force=FORCE, physicsClientId=cid)
    if a.payload == 'dice':
        from tampura_environments.panda_utils.panda_env_utils import create_ycb
        body = create_ycb('dice', client=a._client, use_concave=True)
    else:
        col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[side / 2, side / 2, top / 2],
                                     physicsClientId=cid)
        body = p.createMultiBody(baseMass=mass, baseCollisionShapeIndex=col,
                                 physicsClientId=cid)
    p.changeDynamics(body, -1, mass=mass, localInertiaDiagonal=list(inertia),
                     lateralFriction=task_spec.OBJECT_LATERAL_FRICTION, physicsClientId=cid)
    die_yaw = hand_yaw + math.radians(delta_deg + 90.0 * k90)
    orn_d = p.getQuaternionFromEuler([0.0, 0.0, die_yaw])
    # hand frame axes in the world: pads close along (-sin, cos) of the hand
    # yaw (pose_belief.pad_direction); across the pinch is (cos, sin).
    across = np.array([math.cos(hand_yaw), math.sin(hand_yaw)])
    along = np.array([-math.sin(hand_yaw), math.cos(hand_yaw)])
    xy = np.array(cell) + dx * across + dy * along
    p.resetBasePositionAndOrientation(body, [xy[0], xy[1], 0.05], orn_d, physicsClientId=cid)
    lo, hi = p.getAABB(body, physicsClientId=cid)
    pos0 = p.getBasePositionAndOrientation(body, physicsClientId=cid)[0]
    p.resetBasePositionAndOrientation(body, [xy[0], xy[1], pos0[2] - lo[2] + 0.0002],
                                      orn_d, physicsClientId=cid)
    for _ in range(120):
        p.stepSimulation(physicsClientId=cid)
    row = {'cell': list(cell), 'delta_deg': delta_deg, 'k90': k90, 'dx_mm': 1e3 * dx,
           'dy_mm': 1e3 * dy, 'contact_z_mm': round(1e3 * contact_z, 2),
           'rest': die_state(body, rb, model.ee_link, cid, hand_yaw)}
    q_contact = st._pybullet_ik(np.array([cell[0], cell[1], contact_z]), orn_h,
                                seed=q_above.joint_positions)
    if q_contact is None:
        # execute_pick's own contact IK (robot_utils.solve_ik, seeded)
        q = robot_utils.solve_ik(rb, np.array([cell[0], cell[1], contact_z]), orn_h, cid,
                                 seed=q_above.joint_positions)
        if q is not None:
            class _Q:
                joint_positions = np.asarray(q, dtype=float)
            q_contact = _Q()
            row['contact_ik'] = 'solve_ik'
    if q_contact is None:
        p.removeBody(body, physicsClientId=cid)
        row['ik'] = False
        return row
    robot_utils.move_robot_smooth(rb, q_contact.joint_positions.tolist(), False, settle=True)
    ee = p.getLinkState(rb, model.ee_link, computeForwardKinematics=True, physicsClientId=cid)[0]
    row['ee_z_mm'] = round(1e3 * ee[2], 2)
    row['pre_close'] = die_state(body, rb, model.ee_link, cid, hand_yaw)
    half = robot_utils.close_gripper_until_contact(
        rb, force=FORCE, squeeze=a.squeeze_mm / 1e3, ignore_body_ids=static_ids)
    both, nf, cs = pads(rb, body, cid, fingers)
    row['close'] = {'half_mm': None if half is None else round(1e3 * half, 2),
                    'both': both, 'nf': round(nf, 2),
                    'contacts': contact_geometry(cs, body, cid, fingers),
                    'die': die_state(body, rb, model.ee_link, cid, hand_yaw)}
    if half is None or not both or not (0.005 <= half <= max(DIE_HALF, half_along) + 0.008):
        row.update(grip=False, held=False)
        p.removeBody(body, physicsClientId=cid)
        return row
    trace = {'n': 0, 'nf_min': nf, 'lost': None, 'phase': 'lift',
             'rel_yaw_min': 1e9, 'rel_yaw_max': -1e9, 'tilt_max': 0.0}

    def on_step():
        trace['n'] += 1
        b, f, _ = pads(rb, body, cid, fingers)
        trace['nf_min'] = min(trace['nf_min'], f)
        if trace['n'] % 4 == 0 or (trace['lost'] is None and (not b or f < HELD_FORCE)):
            d = die_state(body, rb, model.ee_link, cid, hand_yaw)
            trace['rel_yaw_min'] = min(trace['rel_yaw_min'], d['rel_yaw_deg'])
            trace['rel_yaw_max'] = max(trace['rel_yaw_max'], d['rel_yaw_deg'])
            trace['tilt_max'] = max(trace['tilt_max'], d['tilt_deg'])
            if trace['lost'] is None and (not b or f < HELD_FORCE):
                trace['lost'] = dict(step=trace['n'], phase=trace['phase'], both=b,
                                     nf=round(f, 3), **d)

    lift = np.array([cell[0], cell[1], contact_z + 0.10])
    q_lift = robot_utils.solve_ik(rb, lift, orn_h, cid, seed=q_contact.joint_positions)
    if q_lift is not None:
        robot_utils.move_robot_smooth(rb, list(q_lift), False, on_step=on_step)
    both, nf, cs = pads(rb, body, cid, fingers)
    row['after_lift'] = {'both': both, 'nf': round(nf, 2),
                         'contacts': contact_geometry(cs, body, cid, fingers),
                         'die': die_state(body, rb, model.ee_link, cid, hand_yaw)}
    if not both:
        row.update(grip=True, lift_ok=False, held=False, lost=trace['lost'])
        p.removeBody(body, physicsClientId=cid)
        return row
    trace['phase'] = 'carry'
    if a.carry_mode == 'pipeline':
        # the dispatcher's streaming of a direct (linear) plan_motion path:
        # N waypoints, every pair through move_robot_smooth(steps=30),
        # settle only at the last (test_full_pipeline.py 1877-1896)
        q_now = np.asarray(robot_utils.arm_joint_positions(rb), dtype=float)
        wps = [q_now + (home - q_now) * t for t in np.linspace(0.0, 1.0, a.waypoints)]
        for wi, wp in enumerate(wps[1:], start=1):
            robot_utils.move_robot_smooth(rb, wp.tolist(), False, steps=30,
                                          settle=(wi == len(wps) - 1), on_step=on_step)
    else:
        robot_utils.move_robot_smooth(rb, home.tolist(), False, settle=True, on_step=on_step)
    trace['phase'] = 'hold'
    passed, steps = robot_utils.hold_at_config(rb, home.tolist(), task_spec.HOME_HOLD_STEP_CAP)
    both, nf, cs = pads(rb, body, cid, fingers)
    held = bool(both and nf >= HELD_FORCE)
    row.update(grip=True, lift_ok=True, held=held, home_nf=round(nf, 2),
               home_die=die_state(body, rb, model.ee_link, cid, hand_yaw),
               carry_steps=trace['n'], nf_min=round(trace['nf_min'], 3),
               lost=trace['lost'], rel_yaw_range=[trace['rel_yaw_min'], trace['rel_yaw_max']],
               tilt_max=trace['tilt_max'],
               home_contacts=contact_geometry(cs, body, cid, fingers) if both else None)
    p.removeBody(body, physicsClientId=cid)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--deltas', default='0,2,4,6,8,10,12,15,20,30,45')
    ap.add_argument('--dx', default='0')
    ap.add_argument('--dy', default='0')
    ap.add_argument('--cells', type=int, default=4)
    ap.add_argument('--k90', default='0,1')
    ap.add_argument('--squeeze-mm', type=float, default=1e3 * robot_utils.GRIP_SQUEEZE)
    ap.add_argument('--floor-mm', type=float, default=1e3 * task_spec.PICK_CONTACT_FLOOR)
    ap.add_argument('--margin-mm', type=float, default=5.0)
    ap.add_argument('--payload', default='dice', choices=('dice', 'cube40'))
    ap.add_argument('--hand-yaw-deg', type=float, default=0.0)
    ap.add_argument('--carry-mode', default='single', choices=('single', 'pipeline'))
    ap.add_argument('--waypoints', type=int, default=10)
    ap.add_argument('--cell-list', default=None, help='x,y;x,y overriding --cells')
    ap.add_argument('--aperture-sized', type=int, default=0,
                    help='1: pre-grasp aperture = half-width along the pads + 8 mm')
    a = ap.parse_args()
    from tampura_environments.panda_utils.robot import DEFAULT_ARM_POS
    world, robot, client, cid, model = their_empty_world()
    assert cid == 0
    a._client = client
    rb = robot.body
    p.setGravity(0, 0, task_spec.GRAVITY_Z, physicsClientId=cid)
    p.setTimeStep(task_spec.TIMESTEP, physicsClientId=cid)
    for fj in model.finger_joints:
        p.changeDynamics(rb, fj, lateralFriction=task_spec.PAD_LATERAL_FRICTION,
                         physicsClientId=cid)
    static_ids = frozenset(b for b in range(p.getNumBodies(physicsClientId=cid))
                           if p.getBodyUniqueId(b, physicsClientId=cid) != rb)
    home = np.asarray(DEFAULT_ARM_POS, dtype=float)
    from boxel_data import BoxelRegistry
    from streams import BoxelStreams
    st = BoxelStreams(registry=BoxelRegistry(), robot_id=rb, physics_client=cid)
    deltas = [float(v) for v in a.deltas.split(',')]
    dxs = [float(v) / 1e3 for v in a.dx.split(',')]
    dys = [float(v) / 1e3 for v in a.dy.split(',')]
    k90s = [int(v) for v in a.k90.split(',')]
    rows, t0 = [], time.time()
    cells = (CELLS[:a.cells] if a.cell_list is None else
             [tuple(float(v) for v in c.split(',')) for c in a.cell_list.split(';')])
    for ci, cell in enumerate(cells):
        for k90 in k90s:
            for dx in dxs:
                for dy in dys:
                    for d in deltas:
                        r = trial(cell, d, k90, dx, dy, a, rb, cid, model, st, home, static_ids)
                        rows.append(r)
                        c = r.get('close', {})
                        print(f"cell {cell} k{k90} dx {1e3*dx:.0f} dy {1e3*dy:.0f} delta {d:5.1f}: "
                              f"rest rel {r.get('rest', {}).get('rel_yaw_deg')} "
                              f"half {c.get('half_mm')} nf {c.get('nf')} "
                              f"closed rel {c.get('die', {}).get('rel_yaw_deg')} "
                              f"lift {r.get('lift_ok')} held {r.get('held')} "
                              f"nfmin {r.get('nf_min')} lost {(r.get('lost') or {}).get('phase')}",
                              flush=True)
    summary = {}
    for d in deltas:
        rs = [r for r in rows if r['delta_deg'] == d and r.get('grip')]
        summary[str(d)] = {'grips': len(rs), 'held': sum(r['held'] for r in rs),
                           'half_mm_med': float(np.median([r['close']['half_mm'] for r in rs])) if rs else None}
    with open(a.out, 'w') as f:
        json.dump({'args': {k: v for k, v in vars(a).items() if not k.startswith('_')},
                   'summary': summary, 'rows': rows, 'wall_s': round(time.time() - t0, 1)},
                  f, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
