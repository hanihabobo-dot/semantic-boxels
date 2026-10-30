"""#P4 GF10: Q14's pre-registered die-loss probe (PAPER_AUDIT.txt P4.10 Q14,
BF#15, amended BF#34; BF#37 item 1).

B1(i)'s set-up extended (tools/_probe_b1p2_tampura.py item_i): THEIR empty
table, their Panda, D9's gravity, timestep, pad friction and opening.  For
each payload class and each of the 96 cells of W (5 cm grid, task_spec's
window), the arm stands at the class's post-place lift pose over the cell
(top-down, yaw 0, the pick contact height + 0.10 m), the fingers stand at the
aperture rule's pre-grasp opening, a static body of the class is created
between the pads at the pick's contact height (top 5 mm above the EE, or the
D8 floor), the pads close on it with close_gripper_until_contact, the body
gets its declared mass and inertia, 60 settle steps, then move_robot_smooth
to DEFAULT_ARM_POS (endpoint settle) and hold_at_config with
HOME_HOLD_STEP_CAP.  HELD = both pads touch the body at >= 0.5 N after the
hold (scoring's test).  A lost body's resting place is logged.

Payload classes: their die and the five cup classes (create_ycb, the body
B7 meets, D9's masses, inertias and frictions), the 100 g control (our
40 mm cube class, 0.1 kg) and BF#37's block check (our 60 x 60 x 75 mm
block class, 0.5 kg; not part of Q14's rule, it must still hold).

M9 and the aperture rule ON: the body is axis-aligned with the pads, so the
M9 pinch and the AABB pinch coincide; the pre-grasp opening is the aperture
rule's min(open, pinch half + pose radius + 8 mm) with pose radius 0 (the
narrowest opening the rule gives).  No retry, masses and frictions as
declared.

LEVELS, fixed before the first run, in Q14's order.  Within a factor the
levels run in the listed order (the smallest departure from today first)
and the first that qualifies is adopted; the later factors then do not run.
  base         today: 60 N, squeeze 3 mm, speed 1, solver as their client
  squeeze      sq2mm, sq1mm, sq0.5mm (60 N cap); cap40N, cap20N (3 mm)
  speed        speed0.5, speed0.25 (joint velocity limits scaled)
  solver       iters200 (numSolverIterations), substeps4 (numSubSteps)
  table pick   B6's floor, execute_pick from the table: runs only if no
               earlier level qualifies (a separate probe)
QUALIFIES: die >= 95 % held AND every cup class >= 95 % held (stricter than
Q14's "a cup-class body"; the any-cup reading is reported too), AND
BF#37's check: the 100 g control and the 0.5 kg block >= 95 % or not below
base.

  cd /root/tampura-work/tampura_environments
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/root/tampura-work/tampura:.:<repo>:<repo>/tools \\
    /root/tampura-work/.venv/bin/python <repo>/tools/_probe_q14_grip.py <level> <out json> \\
    [--payloads dice,a_cups_ud,...] [--cells N]
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np
import pybullet as p

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in (REPO, os.path.join(REPO, 'tools')):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import robot_utils                                   # noqa: E402
from tampura_bridge import task_spec                 # noqa: E402
from _probe_b1p2_tampura import (their_empty_world, top_down, ik_any_seed,   # noqa: E402
                                 _coarse_cells, LIFT)

LEVELS = {
    'base': {},
    'sq2mm': {'squeeze': 0.002}, 'sq1mm': {'squeeze': 0.001},
    'sq0.5mm': {'squeeze': 0.0005},
    'cap40N': {'force': 40.0}, 'cap20N': {'force': 20.0},
    'speed0.5': {'speed': 0.5}, 'speed0.25': {'speed': 0.25},
    'iters200': {'numSolverIterations': 200}, 'substeps4': {'numSubSteps': 4},
}
FORCE, SQUEEZE = 60.0, 0.003                  # execution.py execute_pick's close
GRASP_MARGIN_FROM_TOP = 0.005                 # execution.py _GRASP_MARGIN_FROM_TOP
HELD_FORCE = 0.5                              # scoring.py's pad force floor
SETTLE = 60                                   # B1(i)'s post-close settle
# Our scene classes (boxel_env.py ObjectSpec, full extents and mass).
OURS = {'cube100g': ((0.04, 0.04, 0.04), 0.1),
        'block500g': ((0.06, 0.06, 0.075), 0.5)}
PAYLOADS = ('dice',) + task_spec.CUP_CATEGORIES + tuple(OURS)


def _pads(rb, body, cid, model):
    cs = p.getContactPoints(bodyA=rb, bodyB=body, physicsClientId=cid)
    links = {c[3] for c in cs if c[3] in model.finger_joints}
    nf = sum(c[9] for c in cs if c[3] in model.finger_joints)
    return links == set(model.finger_joints), float(nf)


def _make_body(payload, client, cid):
    """A static body of the class; returns (body, extents, mass, inertia)."""
    if payload in OURS:
        ext, mass = OURS[payload]
        col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[e / 2 for e in ext],
                                     physicsClientId=cid)
        body = p.createMultiBody(baseMass=0.0, baseCollisionShapeIndex=col,
                                 physicsClientId=cid)
        a, b, c = ext
        inertia = [mass * (b * b + c * c) / 12, mass * (a * a + c * c) / 12,
                   mass * (a * a + b * b) / 12]
        return body, ext, mass, inertia
    from tampura_environments.panda_utils.panda_env_utils import create_ycb
    body = create_ycb(payload, client=client, use_concave=True)
    return (body, task_spec.CLASS_EXTENTS[payload], task_spec.CLASS_MASS_KG[payload],
            list(task_spec.CLASS_INERTIA_DIAG[payload]))


def trial(payload, cell, q_lift, level, rb, client, cid, model, home):
    ext_h = (OURS[payload][0] if payload in OURS else task_spec.CLASS_EXTENTS[payload])
    pinch_half = ext_h[0] / 2
    aperture = min(task_spec.FINGER_OPEN, pinch_half + 0.0 + 0.008)
    for j, v in zip(model.arm_joints, q_lift):
        p.resetJointState(rb, j, float(v), physicsClientId=cid)
        p.setJointMotorControl2(rb, j, p.POSITION_CONTROL, targetPosition=float(v),
                                force=240, physicsClientId=cid)
    for fj in model.finger_joints:
        p.resetJointState(rb, fj, aperture, physicsClientId=cid)
        p.setJointMotorControl2(rb, fj, p.POSITION_CONTROL, targetPosition=aperture,
                                force=FORCE, physicsClientId=cid)
    body, ext, mass, inertia = _make_body(payload, client, cid)
    p.changeDynamics(body, -1, lateralFriction=task_spec.OBJECT_LATERAL_FRICTION,
                     physicsClientId=cid)
    ee = np.asarray(p.getLinkState(rb, model.ee_link, computeForwardKinematics=True,
                                   physicsClientId=cid)[0])
    h = ext[2]
    contact = max(h - GRASP_MARGIN_FROM_TOP, task_spec.PICK_CONTACT_FLOOR)
    pos, orn = p.getBasePositionAndOrientation(body, physicsClientId=cid)
    lo, hi = (np.asarray(v) for v in p.getAABB(body, physicsClientId=cid))
    shift = np.array([ee[0] - (lo[0] + hi[0]) / 2, ee[1] - (lo[1] + hi[1]) / 2,
                      (ee[2] + h - contact) - hi[2]])
    p.resetBasePositionAndOrientation(body, (np.asarray(pos) + shift).tolist(), orn,
                                      physicsClientId=cid)
    row = {'payload': payload, 'cell': [round(cell[0], 3), round(cell[1], 3)]}
    half = robot_utils.close_gripper_until_contact(
        rb, force=level.get('force', FORCE), squeeze=level.get('squeeze', SQUEEZE))
    both, nf = _pads(rb, body, cid, model)
    row['close'] = {'half_mm': None if half is None else round(1e3 * half, 2),
                    'both': both, 'nf': round(nf, 2)}
    plausible = half is not None and 0.005 <= half <= pinch_half + 0.008
    if not (both and plausible):
        row.update(grip=False, held=False)
        p.removeBody(body, physicsClientId=cid)
        return row
    p.changeDynamics(body, -1, mass=mass, localInertiaDiagonal=inertia,
                     physicsClientId=cid)
    for _ in range(SETTLE):
        p.stepSimulation(physicsClientId=cid)
    both, nf = _pads(rb, body, cid, model)
    row['settled'] = {'both': both, 'nf': round(nf, 2)}
    trace = {'n': 0, 'nf_min': nf, 'lost_at': None}

    def on_step():
        b, f = _pads(rb, body, cid, model)
        trace['n'] += 1
        trace['nf_min'] = min(trace['nf_min'], f)
        if trace['lost_at'] is None and (not b or f < HELD_FORCE):
            ee_z = p.getLinkState(rb, model.ee_link, physicsClientId=cid)[0][2]
            trace['lost_at'] = {'step': trace['n'], 'ee_z': round(ee_z, 3)}

    limits = robot_utils.JOINT_VELOCITY_LIMITS
    robot_utils.JOINT_VELOCITY_LIMITS = limits * level.get('speed', 1.0)
    try:
        robot_utils.move_robot_smooth(rb, home.tolist(), False, settle=True,
                                      on_step=on_step)
    finally:
        robot_utils.JOINT_VELOCITY_LIMITS = limits
    passed, steps = robot_utils.hold_at_config(rb, home.tolist(),
                                               task_spec.HOME_HOLD_STEP_CAP)
    both, nf = _pads(rb, body, cid, model)
    held = bool(both and nf >= HELD_FORCE)
    row.update(grip=True, held=held, home_nf=round(nf, 2), home_both=both,
               at_home=passed, hold_steps=steps, carry_steps=trace['n'],
               nf_min_carry=round(trace['nf_min'], 2), lost_at=trace['lost_at'])
    if not held:
        row['rest_pos'] = [round(v, 3) for v in
                           p.getBasePositionAndOrientation(body, physicsClientId=cid)[0]]
    p.removeBody(body, physicsClientId=cid)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('level', choices=tuple(LEVELS))
    ap.add_argument('out')
    ap.add_argument('--payloads', default=','.join(PAYLOADS))
    ap.add_argument('--cells', type=int, default=None, help='smoke: first N cells')
    a = ap.parse_args()
    level = LEVELS[a.level]
    from tampura_environments.panda_utils.robot import DEFAULT_ARM_POS
    world, robot, client, cid, model = their_empty_world()
    assert cid == 0, 'our motion functions drive the default client'
    rb = robot.body
    p.setGravity(0, 0, task_spec.GRAVITY_Z, physicsClientId=cid)
    p.setTimeStep(task_spec.TIMESTEP, physicsClientId=cid)
    for fj in model.finger_joints:
        p.changeDynamics(rb, fj, lateralFriction=task_spec.PAD_LATERAL_FRICTION,
                         physicsClientId=cid)
    engine = {k: v for k, v in level.items() if k in ('numSolverIterations', 'numSubSteps')}
    if engine:
        p.setPhysicsEngineParameter(physicsClientId=cid, **engine)
    home = np.asarray(DEFAULT_ARM_POS, dtype=float)
    W = {'x': list(task_spec.WINDOW_X), 'y': list(task_spec.WINDOW_Y)}
    cells = _coarse_cells(W)[:a.cells]
    from boxel_data import BoxelRegistry
    from streams import BoxelStreams
    st = BoxelStreams(registry=BoxelRegistry(), robot_id=rb, physics_client=cid)
    rows, t0 = [], time.time()
    for payload in a.payloads.split(','):
        h = (OURS[payload][0] if payload in OURS else task_spec.CLASS_EXTENTS[payload])[2]
        contact = max(h - GRASP_MARGIN_FROM_TOP, task_spec.PICK_CONTACT_FLOOR)
        held = 0
        for cell in cells:
            q = ik_any_seed(st, [cell[0], cell[1], contact + LIFT], top_down(0.0))
            if q is None:
                rows.append({'payload': payload, 'cell': list(cell), 'ik': False,
                             'held': False})
                continue
            rows.append(trial(payload, cell, q.joint_positions, level, rb, client,
                              cid, model, home))
            held += rows[-1]['held']
        print(f'{a.level} {payload}: held {held}/{len(cells)} '
              f'({time.time() - t0:.0f} s)', flush=True)
    summary = {}
    for payload in a.payloads.split(','):
        rs = [r for r in rows if r['payload'] == payload]
        summary[payload] = {'n': len(rs), 'held': sum(r['held'] for r in rs),
                            'grip': sum(bool(r.get('grip')) for r in rs),
                            'ik_fail': sum(r.get('ik') is False for r in rs)}
    with open(a.out, 'w') as f:
        json.dump({'level': a.level, 'params': level, 'force': level.get('force', FORCE),
                   'squeeze': level.get('squeeze', SQUEEZE), 'cells': len(cells),
                   'summary': summary, 'rows': rows}, f, indent=1)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
