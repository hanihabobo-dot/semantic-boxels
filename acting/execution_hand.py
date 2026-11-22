"""The robot's own hand: which bodies touch it and what its joints read back.

`execution` imports every name of this file, and callers import them from
there.
"""
import pybullet as p

from acting.robot_utils import robot_model


def audit_robot_held_state(env, robot_id, expected_held_body_id=None,
                            tag: str = ""):
    """List non-static bodies in contact with the robot; log anomalies.

    Audit #82 diagnostic.  Surfaces the "robot holding two cubes"
    divergence between PDDL (handempty) and physics when a release
    failure leaves a cube friction-pinned to the EE after the dispatcher's
    audit-#79 state-clear has already set (handempty) symbolically.

    Static bodies (plane, table, robot, trays) are filtered out so the
    return list contains only dynamic objects (cubes / occluders).

    Anomaly cases (each prints "!!! HELD-STATE ANOMALY"):
      (a) expected_held_body_id is None and any body is in contact;
      (b) expected_held_body_id is X and a body other than X is in
          contact, OR more than one body is in contact.
    Success cases stay quiet (empty contacts on either expected mode;
    exactly the expected body on expected=X).

    Returns the sorted list of dynamic body ids found so callers may
    branch on it later.
    """
    static_ids = {-1, robot_id}
    for name, info in env.objects.items():
        if name in ("plane", "table", "robot"):
            static_ids.add(info.object_id)
            continue
        if getattr(info, "is_tray", False):
            static_ids.add(info.object_id)

    contacts = p.getContactPoints(bodyA=robot_id)
    bodies = sorted({c[2] for c in contacts} - static_ids)

    if not bodies:
        return bodies  # quiet success — empty contacts on either mode

    if expected_held_body_id is None:
        print(f"    !!! HELD-STATE ANOMALY ({tag}): expected handempty, "
              f"robot in contact with bodies={bodies}")
    elif len(bodies) > 1 or expected_held_body_id not in bodies:
        print(f"    !!! HELD-STATE ANOMALY ({tag}): expected only "
              f"body={expected_held_body_id}, robot in contact with "
              f"bodies={bodies}")

    return bodies


def held_pad_contacts(robot_id, body_id):
    """The robot's tactile sense of one body (BF#59 carry_hold_check, the
    shared helper): the finger pad links in contact with it, their summed
    normal force (N) and the number of contact points on the pads.  It
    applies no rule: the post-lift re-verify and the carry check both ask
    for presence on both pads and nothing more (reviews/loss_dynamics.md:
    the post-lift check has no 0.5 N floor and must not get one); the
    force is a logged number only."""
    contacts = p.getContactPoints(bodyA=robot_id, bodyB=body_id)
    fingers = robot_model().finger_joints
    pad = [c for c in contacts if c[3] in fingers]
    return (frozenset(c[3] for c in pad), float(sum(c[9] for c in pad)),
            len(pad))


def _finger_readback(robot_id):
    return tuple(float(p.getJointState(robot_id, fj)[0])
                 for fj in robot_model().finger_joints)


def _wrist_readback(robot_id):
    return float(p.getJointState(robot_id, robot_model().arm_joints[-1])[0])
