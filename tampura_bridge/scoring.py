"""#P4 D3: the scoring channel (PAPER_AUDIT.txt P4.3 D3, gate G6).

The ONLY writer of TAMPURA's belief inputs.  After main() returns, the
terminal observation is built from physical readback alone:
SceneObservation(camera_image=None, poses={}, grasp=G, grasp_body=S, conf=Q).
  S  the store symbol s in their sim world's objects with store.get(s) ==
     the body both finger pads touch with squeeze force >= 0.5 N (the
     _verify_holding rule) and no constraint on it; resolved with the same
     lookup their obs_from_camera_image uses (env.py:70-73); never chosen
     by name; None when the pads hold nothing or a non-task body.
  G  a store symbol of type grasp, added once with store.add_typed, holding
     a plain tuple (EE position, EE quaternion, finger width) read from the
     robot, so deep copies and the pickle stay plain data; None without S.
  Q  the readback of the 7 arm joints, never a constant.
Their reward then reads holding(S) and at-home(Q) on their own belief.
The contact and joint reads run inside gate_hooks.scoring() (G2, G8(b)).
"""
import pybullet as p

import robot_utils
from tampura_bridge import gate_hooks

SQUEEZE_MIN_N = 0.5     # test_full_pipeline._verify_holding


def held_body(client, robot):
    """The body both finger pads touch with >= SQUEEZE_MIN_N, or None."""
    fingers = robot_utils.robot_model().finger_joints
    by_body = {}
    for c in p.getContactPoints(bodyA=robot, physicsClientId=client):
        if c[3] in fingers and c[2] != robot:
            pads, force = by_body.get(c[2], (set(), 0.0))
            by_body[c[2]] = (pads | {c[3]}, force + c[9])
    held = [b for b, (pads, force) in by_body.items()
            if pads == set(fingers) and force >= SQUEEZE_MIN_N]
    if len(held) != 1:
        return None
    body = held[0]
    for k in range(p.getNumConstraints(physicsClientId=client)):
        info = p.getConstraintInfo(p.getConstraintUniqueId(
            k, physicsClientId=client), physicsClientId=client)
        if body in (info[0], info[2]):
            return None
    return body


def build_observation(their_env, store, client, robot):
    """The terminal SceneObservation from physical readback (D3)."""
    from tampura_environments.find_dice.env import SceneObservation
    rm = robot_utils.robot_model()
    with gate_hooks.scoring():
        body = held_body(client, robot)
        q = [p.getJointState(robot, j, physicsClientId=client)[0]
             for j in rm.arm_joints]
        ee = p.getLinkState(robot, rm.ee_link, computeForwardKinematics=True,
                            physicsClientId=client)
        width = sum(p.getJointState(robot, j, physicsClientId=client)[0]
                    for j in rm.finger_joints)
    symbol = None
    if body is not None:
        found = [s for s in their_env.sim_world.objects if store.get(s) == body]
        symbol = found[0] if len(found) == 1 else None
    grasp = None
    if symbol is not None:
        grasp = store.add_typed((tuple(float(v) for v in ee[4]),
                                 tuple(float(v) for v in ee[5]),
                                 float(width)), 'grasp')
    return SceneObservation(camera_image=None, poses={}, grasp=grasp,
                            grasp_body=symbol, conf=[float(v) for v in q])
