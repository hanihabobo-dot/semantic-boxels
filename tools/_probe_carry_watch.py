"""Carry watch (2026-10-30, Hani: "maybe your detection system is wrong, set
up some experiment to test this with me").

The hold detector under test is the goal check of test_full_pipeline.py
(and execute_place's entry assert): the held body must touch BOTH finger
pads and the pads' normal force must be at least 0.5 N (scoring's floor).
Here a body of a find_dice class (their die by default) is pinched by our
pick close (robot_utils.close_gripper_until_contact, the squeeze under
test), given its declared mass, settled, and carried home with the
pipeline's own motion (robot_utils.move_robot_smooth to DEFAULT_ARM_POS,
the velocity limits untouched), then held at home as the pipeline does.
At every simulation step the detector's verdict and the body's TRUE
position are read side by side; the GUI is slowed by sleeping between
steps (the trajectory itself is unchanged), a line is printed every tenth
of a simulated second, and the first step the detector reports the body
lost is frozen for a few seconds with a red marker at the body.  At the
end of each carry two verdicts are printed, the detector's and the
truth's (the body within 5 cm of the end effector), and the summary
counts their disagreements: a disagreement is a detector bug, an
agreement with "lost" is a real loss you can watch happen.

TAMPURA's empty table, their Panda, D9's gravity, timestep and pad
friction (as tools/_probe_q14_grip.py).  A probe, not pipeline code.

  cd /root/tampura-work/tampura_environments
  PYTHONPATH=/root/tampura-work/tampura:.:<repo>:<repo>/tools \\
    /root/tampura-work/.venv/bin/python <repo>/tools/_probe_carry_watch.py \\
    --squeeze-mm 0.5 --trials 5 [--tilt-deg 10] [--payload dice] \\
    [--cell 0.673,0.216] [--slow 4] [--vis 1] [--out file.json]
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
from _probe_b1p2_tampura import top_down, ik_any_seed, LIFT   # noqa: E402
from _probe_q14_grip import (_make_body, _pads, FORCE, GRASP_MARGIN_FROM_TOP,   # noqa: E402
                             HELD_FORCE, SETTLE, OURS)

HZ = 1.0 / task_spec.TIMESTEP
NEAR_EE_M = 0.05                                     # truth: the body rides with the hand


def their_world(vis):
    from tampura_environments.find_dice.env import setup_world
    from tampura_environments.panda_utils.panda_env_utils import setup_robot
    robot, client = setup_robot(vis=bool(vis))
    world = setup_world(robot, client, [], [])
    cid = client._client
    model = robot_utils.resolve_robot_model(robot.body, cid)
    robot_utils.use_robot_model(model)
    return world, robot, client, cid, model


def verdicts(rb, body, cid, model):
    both, nf = _pads(rb, body, cid, model)
    ee = np.asarray(p.getLinkState(rb, model.ee_link, computeForwardKinematics=True,
                                   physicsClientId=cid)[0])
    pos, orn = p.getBasePositionAndOrientation(body, physicsClientId=cid)
    pos = np.asarray(pos)
    rot = np.asarray(p.getMatrixFromQuaternion(orn)).reshape(3, 3)
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(rot[2, 2])))))
    dist = float(np.linalg.norm(pos - ee))
    return {'detector': bool(both and nf >= HELD_FORCE), 'both': both, 'nf': round(nf, 2),
            'truth': dist <= NEAR_EE_M, 'dist_mm': round(1e3 * dist, 1),
            'ee': [round(v, 3) for v in ee], 'body': [round(v, 3) for v in pos],
            'tilt_deg': round(tilt, 1)}


def line(t, v):
    return (f"  t={t:5.2f}s  pads={'both' if v['both'] else 'not both':8s}  "
            f"force={v['nf']:6.2f} N  detector={'HELD' if v['detector'] else 'LOST'}  "
            f"body-to-hand={v['dist_mm']:6.1f} mm  truth={'HELD' if v['truth'] else 'LOST'}  "
            f"tilt={v['tilt_deg']:5.1f} deg")


def carry(k, payload, cell, yaw, tilt_deg, squeeze, rb, client, cid, model, home, st,
          slow, vis, freeze_s):
    ext_h = OURS[payload][0] if payload in OURS else task_spec.CLASS_EXTENTS[payload]
    h = ext_h[2]
    contact = max(h - GRASP_MARGIN_FROM_TOP, task_spec.PICK_CONTACT_FLOOR)
    q = ik_any_seed(st, [cell[0], cell[1], contact + LIFT], top_down(yaw))
    if q is None:
        print(f"trial {k}: no IK over the cell {cell} at yaw {yaw:.2f}")
        return None
    pinch_half = ext_h[0] / 2
    aperture = min(task_spec.FINGER_OPEN, pinch_half + 0.008)
    for j, v in zip(model.arm_joints, q.joint_positions):
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
    # The body between the pads: axis-aligned with the pinch, tilted about
    # the horizontal axis across the pinch (the pads then meet inclined faces,
    # the die of the 12:12 run sat 12 deg tilted in the grasp).
    orn = p.getQuaternionFromEuler([math.radians(tilt_deg), 0.0, yaw])
    p.resetBasePositionAndOrientation(body, [0, 0, 1.0], orn, physicsClientId=cid)
    ee = np.asarray(p.getLinkState(rb, model.ee_link, computeForwardKinematics=True,
                                   physicsClientId=cid)[0])
    lo, hi = (np.asarray(v) for v in p.getAABB(body, physicsClientId=cid))
    centre = (lo + hi) / 2
    target = np.array([ee[0], ee[1], ee[2] + h - contact - (hi[2] - centre[2])])
    p.resetBasePositionAndOrientation(body, (np.array([0, 0, 1.0]) + target - centre).tolist(),
                                      orn, physicsClientId=cid)
    half = robot_utils.close_gripper_until_contact(rb, force=FORCE, squeeze=squeeze)
    v0 = verdicts(rb, body, cid, model)
    print(f"trial {k}: {payload} at ({cell[0]:.3f}, {cell[1]:.3f}) yaw {yaw:.2f} "
          f"tilt {tilt_deg:.0f} deg, squeeze {1e3 * squeeze:.1f} mm: close measured "
          f"half-width {'none' if half is None else f'{1e3 * half:.1f} mm'}, "
          f"pads {'both' if v0['both'] else 'not both'} at {v0['nf']:.1f} N")
    if half is None or not v0['both']:
        print("  no grip formed; trial skipped")
        p.removeBody(body, physicsClientId=cid)
        return {'trial': k, 'grip': False}
    p.changeDynamics(body, -1, mass=mass, localInertiaDiagonal=inertia,
                     physicsClientId=cid)
    for _ in range(SETTLE):
        p.stepSimulation(physicsClientId=cid)
    v1 = verdicts(rb, body, cid, model)
    print("  after the settle:" + line(0.0, v1)[1:])
    trace = {'n': 0, 'lost': None, 'rows': []}
    every = int(round(HZ / 10))

    def on_step():
        trace['n'] += 1
        v = verdicts(rb, body, cid, model)
        t = trace['n'] / HZ
        if trace['n'] % every == 0:
            print(line(t, v), flush=True)
            trace['rows'].append(dict(t=round(t, 3), **v))
        if trace['lost'] is None and not v['detector']:
            trace['lost'] = dict(t=round(t, 3), **v)
            print(f"  >>> DETECTOR SAYS LOST at t={t:.2f} s: pads "
                  f"{'both' if v['both'] else 'not both'}, force {v['nf']:.2f} N; "
                  f"the body is {v['dist_mm']:.0f} mm from the hand "
                  f"({'still with it' if v['truth'] else 'away from it'})", flush=True)
            if vis:
                p.addUserDebugText('LOST HERE', v['body'], textColorRGB=[1, 0, 0],
                                   textSize=1.5, physicsClientId=cid)
                p.addUserDebugLine(v['ee'], v['body'], lineColorRGB=[1, 0, 0],
                                   lineWidth=3, physicsClientId=cid)
                time.sleep(freeze_s)
        if vis and slow > 0:
            time.sleep(slow / HZ)

    robot_utils.move_robot_smooth(rb, home.tolist(), False, settle=True, on_step=on_step)
    passed, steps = robot_utils.hold_at_config(rb, home.tolist(), task_spec.HOME_HOLD_STEP_CAP)
    v2 = verdicts(rb, body, cid, model)
    agree = v2['detector'] == v2['truth']
    print(f"  at home after a {steps}-step hold: detector says "
          f"{'HELD' if v2['detector'] else 'LOST'} (pads {'both' if v2['both'] else 'not both'}, "
          f"{v2['nf']:.2f} N), the truth is {'HELD' if v2['truth'] else 'LOST'} "
          f"(body {v2['dist_mm']:.0f} mm from the hand, at {v2['body']}) -> "
          f"{'AGREE' if agree else 'DISAGREE'}")
    if vis:
        time.sleep(freeze_s)
        p.removeAllUserDebugItems(physicsClientId=cid)
    p.removeBody(body, physicsClientId=cid)
    return {'trial': k, 'grip': True, 'yaw': yaw, 'tilt_deg': tilt_deg,
            'half_mm': round(1e3 * half, 2), 'settled': v1, 'lost': trace['lost'],
            'carry_steps': trace['n'], 'home': v2, 'at_home': passed, 'agree': agree,
            'rows': trace['rows']}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--squeeze-mm', type=float, default=0.5)
    ap.add_argument('--trials', type=int, default=5)
    ap.add_argument('--tilt-deg', type=float, default=0.0)
    ap.add_argument('--payload', default='dice')
    ap.add_argument('--cell', default='0.673,0.216',
                    help='x,y of the pick, world frame (the 12:12 run of seed 0)')
    ap.add_argument('--slow', type=float, default=4.0,
                    help='GUI slow-motion factor (sleep per step; the motion is unchanged)')
    ap.add_argument('--freeze-s', type=float, default=3.0)
    ap.add_argument('--vis', type=int, default=1)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    squeeze = a.squeeze_mm / 1000.0
    cell = tuple(float(v) for v in a.cell.split(','))
    from tampura_environments.panda_utils.robot import DEFAULT_ARM_POS
    world, robot, client, cid, model = their_world(a.vis)
    assert cid == 0, 'our motion functions drive the default client'
    rb = robot.body
    p.setGravity(0, 0, task_spec.GRAVITY_Z, physicsClientId=cid)
    p.setTimeStep(task_spec.TIMESTEP, physicsClientId=cid)
    for fj in model.finger_joints:
        p.changeDynamics(rb, fj, lateralFriction=task_spec.PAD_LATERAL_FRICTION,
                         physicsClientId=cid)
    home = np.asarray(DEFAULT_ARM_POS, dtype=float)
    from boxel_data import BoxelRegistry
    from streams import BoxelStreams
    st = BoxelStreams(registry=BoxelRegistry(), robot_id=rb, physics_client=cid)
    print(f"carry watch: {a.payload}, squeeze {a.squeeze_mm} mm, {a.trials} trials, "
          f"tilt {a.tilt_deg} deg, cell {cell}, slow x{a.slow}")
    print("detector = the goal check: both pads touch the body with >= 0.5 N of normal "
          "force; truth = the body within 50 mm of the end effector")
    rows = []
    yaws = [0.0, math.pi / 2, math.pi / 4, -math.pi / 4, math.pi / 8]
    for k in range(a.trials):
        r = carry(k + 1, a.payload, cell, yaws[k % len(yaws)], a.tilt_deg, squeeze,
                  rb, client, cid, model, home, st, a.slow, a.vis, a.freeze_s)
        if r is not None:
            rows.append(r)
    done = [r for r in rows if r.get('grip')]
    det = sum(r['home']['detector'] for r in done)
    tru = sum(r['home']['truth'] for r in done)
    dis = sum(not r['agree'] for r in done)
    print(f"\nsummary: {len(done)} carries at {a.squeeze_mm} mm: detector held {det}, "
          f"truth held {tru}, disagreements {dis}")
    if a.out:
        with open(a.out, 'w') as f:
            json.dump({'payload': a.payload, 'squeeze_mm': a.squeeze_mm, 'tilt_deg': a.tilt_deg,
                       'cell': list(cell), 'rows': rows,
                       'summary': {'carries': len(done), 'detector_held': det,
                                   'truth_held': tru, 'disagreements': dis}}, f, indent=1)
        print(f"written {a.out}")
    if a.vis:
        print("close the GUI window to end")
        try:
            while p.isConnected(cid):
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
