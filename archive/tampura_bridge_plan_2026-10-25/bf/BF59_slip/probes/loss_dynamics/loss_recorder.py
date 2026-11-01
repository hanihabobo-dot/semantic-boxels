"""BF#59 loss_dynamics probe: a per-step recorder of the die's carry.

Print-only diagnostics (never feeds control): wraps telemetry.tick (called
after every p.stepSimulation of the executing world), the dispatcher's
move_robot_smooth and hold_at_config names in test_full_pipeline, and
execute_pick, so every simulation step from the die pick's entry to 300
steps after the pads last held it is written as one JSON line:

  step, phase (the dispatched action label), wp (waypoint index of the move,
  'hold' for the home hold, 'pick' inside execute_pick), pads (per finger
  link: n contacts, normal force sum, friction sums, contact points on the
  die in the die frame), die pose in the hand (grasptarget) frame, arm joint
  velocities, the hand's linear and angular velocity, finger positions.
"""
import json
import os

import numpy as np
import pybullet as p

OUT = None
_f = None
STATE = {'carry': None, 'step': 0, 'phase': '', 'wp': None, 'move_k': 0,
         'last_held': None, 'pick_n': 0}


def _open(path):
    global _f, OUT
    OUT = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _f = open(path, 'w', buffering=1)


def _row(kind, **kw):
    if _f is not None:
        _f.write(json.dumps(dict(kind=kind, **kw), default=float) + '\n')


def _rel(hand_pos, hand_orn, pos, orn):
    inv_p, inv_o = p.invertTransform(hand_pos, hand_orn)
    rp, ro = p.multiplyTransforms(inv_p, inv_o, pos, orn)
    return list(rp), list(ro)


def on_tick():
    c = STATE['carry']
    if c is None:
        return
    STATE['step'] += 1
    robot, die, rm = c['robot'], c['die'], c['rm']
    fingers = rm.finger_joints
    pads = {}
    dpos, dorn = p.getBasePositionAndOrientation(die)
    inv_dp, inv_do = p.invertTransform(dpos, dorn)
    for fl in fingers:
        cps = [x for x in p.getContactPoints(bodyA=robot, bodyB=die) if x[3] == fl]
        pts = []
        for x in cps:
            q, _ = p.multiplyTransforms(inv_dp, inv_do, x[6], [0, 0, 0, 1])
            pts.append([round(v * 1e3, 2) for v in q])   # mm in the die frame
        pads[str(fl)] = {'n': len(cps),
                         'nf': round(sum(x[9] for x in cps), 4),
                         'f1': round(sum(x[10] for x in cps), 4),
                         'f2': round(sum(x[12] for x in cps), 4),
                         'pts': pts}
    other = sorted({x[2] for x in p.getContactPoints(bodyA=die)
                    if x[2] not in (robot,)})
    ls = p.getLinkState(robot, rm.ee_link, computeLinkVelocity=1,
                        computeForwardKinematics=1)
    hp, ho = ls[4], ls[5]
    rp, ro = _rel(hp, ho, dpos, dorn)
    dv, dw = p.getBaseVelocity(die)
    qd = [p.getJointState(robot, j)[1] for j in rm.arm_joints]
    fpos = [p.getJointState(robot, j)[0] for j in fingers]
    held = all(pads[str(fl)]['n'] > 0 for fl in fingers)
    if held:
        STATE['last_held'] = STATE['step']
    _row('s', step=STATE['step'], phase=STATE['phase'], wp=STATE['wp'],
         pads=pads, other=other,
         rel_p=[round(v * 1e3, 3) for v in rp], rel_q=[round(v, 6) for v in ro],
         die_z=round(dpos[2], 5), die_v=[round(v, 4) for v in dv],
         die_w=[round(v, 3) for v in dw],
         hand_v=[round(v, 4) for v in ls[6]], hand_w=[round(v, 3) for v in ls[7]],
         qd=[round(v, 4) for v in qd], fing=[round(v * 1e3, 3) for v in fpos])
    if (STATE['last_held'] is not None
            and STATE['step'] - STATE['last_held'] > 300):
        _row('end', step=STATE['step'], reason='300 steps without both pads')
        STATE['carry'] = None


def install(out_path):
    import telemetry
    import test_full_pipeline as tfp
    from robot_utils import robot_model
    _open(out_path)

    orig_tick = telemetry.tick

    def tick():
        orig_tick()
        try:
            on_tick()
        except Exception as e:   # a probe never breaks the episode
            _row('err', where='tick', msg=repr(e))
    telemetry.tick = tick

    orig_phase = telemetry.phase

    def phase(label):
        orig_phase(label)
        STATE['phase'] = label
        STATE['wp'] = None
        STATE['move_k'] = 0
        _row('phase', step=STATE['step'], label=label,
             carrying=STATE['carry'] is not None)
    telemetry.phase = phase

    orig_mrs = tfp.move_robot_smooth

    def mrs(robot_id, target_joints, *a, **kw):
        STATE['move_k'] += 1
        STATE['wp'] = STATE['move_k']
        if STATE['carry'] is not None:
            cur = [p.getJointState(robot_id, j)[0] for j in robot_model().arm_joints]
            _row('wp', step=STATE['step'], wp=STATE['wp'],
                 settle=kw.get('settle'),
                 dq=[round(float(t) - c, 4) for t, c in zip(target_joints, cur)])
        return orig_mrs(robot_id, target_joints, *a, **kw)
    tfp.move_robot_smooth = mrs

    orig_hold = tfp.hold_at_config

    def hold(robot_id, target_joints, step_cap, *a, **kw):
        STATE['wp'] = 'hold'
        r = orig_hold(robot_id, target_joints, step_cap, *a, **kw)
        _row('hold_done', step=STATE['step'], ret=list(r))
        return r
    tfp.hold_at_config = hold

    orig_pick = tfp.execute_pick

    def pick(robot_id, env, obj_name, *a, **kw):
        is_die = obj_name == 'dice'
        if is_die:
            STATE['pick_n'] += 1
            STATE['carry'] = {'robot': robot_id,
                              'die': env.objects[obj_name].object_id,
                              'rm': robot_model()}
            STATE['last_held'] = None
            STATE['wp'] = 'pick'
            _row('pick_start', step=STATE['step'], n=STATE['pick_n'])
        r = orig_pick(robot_id, env, obj_name, *a, **kw)
        if is_die:
            _row('pick_done', step=STATE['step'],
                 held=(r[0] is not None))
            STATE['wp'] = 'post_pick'
        return r
    tfp.execute_pick = pick

    orig_vh = tfp._verify_holding

    def vh(env, target_name, held_body_id):
        r = orig_vh(env, target_name, held_body_id)
        _row('goal_check', step=STATE['step'], ok=r[0], reason=r[1])
        return r
    tfp._verify_holding = vh
