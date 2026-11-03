"""Read-only probe for no_fit_case.md (2026-11-03).

Question: with tool_use's collision filters (tool_use/env.py:247-255, 263-287),
can the Panda's fingers or another cube touch a cube, and does a stacked cube
stay up under gravity?  Uses pybullet only and reads TAMPURA's Panda URDF;
imports nothing from their tree and writes nothing but stdout.
"""
import pybullet as p

URDF = "/root/tampura-work/tampura_environments/models/srl/franka_panda/panda.urdf"
# tool_use/env.py:248-255, copied as literals
GROUP_MAIN_CUBE, GROUP_GHOST, GROUP_FLOOR_HOOK, GROUP_OTHERS = 1, 2, 4, 8
MASK_GHOST = GROUP_FLOOR_HOOK
MASK_FLOOR_HOOK = GROUP_MAIN_CUBE | GROUP_GHOST | GROUP_OTHERS


def cube(c, pos, half=0.02, mass=0.1):
    col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[half] * 3,
                                 physicsClientId=c)
    return p.createMultiBody(baseMass=mass, baseCollisionShapeIndex=col,
                             basePosition=pos, physicsClientId=c)


def finger_links(c, robot):
    out = []
    for j in range(p.getNumJoints(robot, physicsClientId=c)):
        info = p.getJointInfo(robot, j, physicsClientId=c)
        if b"finger" in info[12]:
            out.append((j, info[12].decode()))
    return out


def finger_test(filtered):
    c = p.connect(p.DIRECT)
    robot = p.loadURDF(URDF, useFixedBase=True, flags=0, physicsClientId=c)
    res = {}
    for link, name in finger_links(c, robot):
        lo, hi = p.getAABB(robot, link, physicsClientId=c)
        centre = [(a + b) / 2 for a, b in zip(lo, hi)]
        b = cube(c, centre)
        if filtered:
            p.setCollisionFilterGroupMask(b, -1, GROUP_GHOST, MASK_GHOST,
                                          physicsClientId=c)
        p.performCollisionDetection(physicsClientId=c)
        n_contact = len(p.getContactPoints(bodyA=robot, bodyB=b,
                                           linkIndexA=link, physicsClientId=c))
        n_any = len(p.getContactPoints(bodyA=robot, bodyB=b, physicsClientId=c))
        n_closest = len(p.getClosestPoints(robot, b, 0.0, linkIndexA=link,
                                           physicsClientId=c))
        res[name] = dict(contacts_link=n_contact, contacts_any_link=n_any,
                         closest_points_d0=n_closest)
        p.removeBody(b, physicsClientId=c)
    p.disconnect(c)
    return res


def stack_test(filtered):
    c = p.connect(p.DIRECT)
    p.setGravity(0, 0, -10, physicsClientId=c)
    tcol = p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.3, 0.3, 0.015],
                                  physicsClientId=c)
    table = p.createMultiBody(baseMass=0, baseCollisionShapeIndex=tcol,
                              basePosition=[0.5, 0, -0.015], physicsClientId=c)
    lower = cube(c, [0.5, 0, 0.02])
    upper = cube(c, [0.5, 0, 0.0601])
    if filtered:
        p.setCollisionFilterGroupMask(table, -1, GROUP_FLOOR_HOOK,
                                      MASK_FLOOR_HOOK, physicsClientId=c)
        for k in (lower, upper):
            p.setCollisionFilterGroupMask(k, -1, GROUP_GHOST, MASK_GHOST,
                                          physicsClientId=c)
    for _ in range(480):
        p.stepSimulation(physicsClientId=c)
    z_lower = p.getBasePositionAndOrientation(lower, physicsClientId=c)[0][2]
    z_upper = p.getBasePositionAndOrientation(upper, physicsClientId=c)[0][2]
    p.performCollisionDetection(physicsClientId=c)
    n_cc = len(p.getContactPoints(bodyA=lower, bodyB=upper, physicsClientId=c))
    p.disconnect(c)
    return dict(z_lower=round(z_lower, 4), z_upper=round(z_upper, 4),
                cube_cube_contacts=n_cc)


if __name__ == "__main__":
    print("pybullet API", p.getAPIVersion())
    print("FINGER x CUBE, default filters:", finger_test(False))
    print("FINGER x CUBE, tool_use cube filter:", finger_test(True))
    print("STACK, default filters:", stack_test(False))
    print("STACK, tool_use filters:", stack_test(True))
