"""BF#59 force_hold (reviews/impl_force_hold.md): the force-limited hold
after the tactile close and the finger gear that couples the two finger
joints, in robot_utils.close_gripper_until_contact, tampura_bridge/policy.py
d9_setup and boxel_env.py _setup_scene.

The worlds are DIRECT clients with pybullet_data's Panda (the same file as
their URDF for the fingers, proposals/hold_physics.md item 2), as
tests/test_kin_contact.py builds them; close_gripper_until_contact drives
the default client, so the world must be client 0.  200 solver iterations
on the test world stand in for the solver_iters switch, which lives on
another branch; the switch itself is set in the registry by hand.
"""
import types

import numpy as np
import pybullet as p
import pybullet_data
import pytest

from acting import robot_utils
from acting import slip_fixes

HOME = [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785]     # hand down, as DEFAULT_ARM_POS
DIE = 0.0178                                             # the die's side (BRIEF.md 1)


@pytest.fixture
def registry(monkeypatch):
    """The registry as the module set it at import, restored after."""
    known, enabled = dict(slip_fixes.KNOWN), slip_fixes.ENABLED
    monkeypatch.delenv(robot_utils.FORCE_HOLD_NO_ITERS_ENV, raising=False)
    slip_fixes.ENABLED = frozenset()
    yield slip_fixes
    slip_fixes.KNOWN.clear()
    slip_fixes.KNOWN.update(known)
    slip_fixes.ENABLED = enabled


@pytest.fixture
def panda():
    """Client 0 with the Panda, the hand pointing down at HOME, the arm held
    by its motors, fingers open; the robot model restored after."""
    cid = p.connect(p.DIRECT)
    if cid != 0:
        p.disconnect(cid)
        pytest.fail(f"another test left client 0 connected (got {cid})")
    prev = robot_utils.robot_model()
    try:
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=cid)
        p.setGravity(0, 0, -9.81, physicsClientId=cid)
        p.setTimeStep(robot_utils.SIM_TIMESTEP, physicsClientId=cid)
        rb = p.loadURDF('franka_panda/panda.urdf', [0, 0, 0], useFixedBase=True,
                        physicsClientId=cid)
        model = robot_utils.resolve_robot_model(rb, cid)
        robot_utils.use_robot_model(model)
        for j, v in zip(model.arm_joints, HOME):
            p.resetJointState(rb, j, v, physicsClientId=cid)
            p.setJointMotorControl2(rb, j, p.POSITION_CONTROL, targetPosition=v,
                                    force=240, physicsClientId=cid)
        for fj in model.finger_joints:
            p.changeDynamics(rb, fj, lateralFriction=1.2, physicsClientId=cid)
            p.resetJointState(rb, fj, 0.04, physicsClientId=cid)
        yield cid, rb, model
    finally:
        robot_utils.use_robot_model(prev)
        p.disconnect(cid)


def _fake_world(cid, rb):
    """The parts of their world d9_setup reads: the client, the robot body,
    no task bodies."""
    return types.SimpleNamespace(client=types.SimpleNamespace(_client=cid),
                                 robot=types.SimpleNamespace(body=rb),
                                 objects=[], categories=[])


def _box_between_pads(cid, rb, model, offset=0.0):
    """A 17.8 mm, 5.2 g box at the pads' midpoint (shifted ``offset`` along
    the pinch axis) on a fixed pedestal, settled."""
    ee = np.asarray(p.getLinkState(rb, model.ee_link, physicsClientId=cid)[0])
    f1 = np.asarray(p.getLinkState(rb, model.finger_joints[0], physicsClientId=cid)[0])
    f2 = np.asarray(p.getLinkState(rb, model.finger_joints[1], physicsClientId=cid)[0])
    axis = (f1 - f2) / np.linalg.norm(f1 - f2)
    centre = ee + offset * axis
    he = DIE / 2
    box = p.createMultiBody(0.0052, p.createCollisionShape(p.GEOM_BOX, halfExtents=[he] * 3,
                                                           physicsClientId=cid),
                            basePosition=centre.tolist(), physicsClientId=cid)
    p.changeDynamics(box, -1, lateralFriction=1.0, physicsClientId=cid)
    ped = p.createMultiBody(0.0, p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.01, 0.01, 0.05],
                                                        physicsClientId=cid),
                            basePosition=(centre - [0, 0, he + 0.05]).tolist(),
                            physicsClientId=cid)
    for _ in range(20):
        p.stepSimulation(physicsClientId=cid)
    return box, ped, axis


class _Motors:
    """Records the finger motor commands while passing them through."""

    def __init__(self, fingers):
        self.fingers = set(fingers)
        self.calls = []
        self._orig = p.setJointMotorControl2

    def __call__(self, body, joint, mode, *a, **kw):
        if joint in self.fingers:
            self.calls.append((joint, kw.get('targetPosition'), kw.get('force')))
        return self._orig(body, joint, mode, *a, **kw)


# ----- the switch -----------------------------------------------------------

def test_registered_and_on_by_default(registry):
    assert 'force_hold' in registry.KNOWN
    assert 'force_hold' in registry.configure('')            # BF#62: one of the four
    assert registry.on('force_hold') and registry.on('solver_iters')
    assert registry.configure('none') == frozenset()
    assert not registry.on('force_hold')


def test_refused_without_solver_iters(registry, monkeypatch):
    registry.ENABLED = frozenset({'force_hold'})
    with pytest.raises(RuntimeError, match=r"'force_hold' needs 'solver_iters'"):
        robot_utils.force_hold_requires_solver_iters('a test')
    registry.ENABLED = frozenset({'force_hold', 'solver_iters'})
    robot_utils.force_hold_requires_solver_iters('a test')            # passes
    registry.ENABLED = frozenset({'force_hold'})
    monkeypatch.setenv(robot_utils.FORCE_HOLD_NO_ITERS_ENV, '1')     # the check-only escape
    robot_utils.force_hold_requires_solver_iters('a test')


def test_the_gear_refuses_without_solver_iters(registry, panda):
    cid, rb, model = panda
    from tampura_bridge import policy
    registry.ENABLED = frozenset({'force_hold'})
    with pytest.raises(RuntimeError, match='solver_iters'):
        policy.d9_setup(_fake_world(cid, rb), model)
    assert p.getNumConstraints(physicsClientId=cid) == 0


# ----- the hold law -----------------------------------------------------------

@pytest.mark.parametrize('switch', ['off', 'on'])
def test_the_hold_target_and_force(registry, panda, monkeypatch, switch):
    cid, rb, model = panda
    if switch == 'on':
        registry.ENABLED = frozenset({'force_hold', 'solver_iters'})
    p.setPhysicsEngineParameter(numSolverIterations=200, physicsClientId=cid)
    box, ped, _ = _box_between_pads(cid, rb, model)
    motors = _Motors(model.finger_joints)
    monkeypatch.setattr(p, 'setJointMotorControl2', motors)
    width = robot_utils.close_gripper_until_contact(rb, force=60.0, ignore_body_ids={ped})
    assert width is not None and 0.005 < width < 0.015
    # the 60-step position hold is today's in both cases: 0.5 mm inside at 60 N
    hold = [c for c in motors.calls if c[1] == pytest.approx(width - 0.0005)]
    assert len(hold) == 2 * 60 and all(c[2] == 60.0 for c in hold)
    last = motors.calls[-2:]
    if switch == 'off':
        assert last == hold[-2:]
    else:
        assert {c[0] for c in last} == set(model.finger_joints)
        assert all(c[1] == pytest.approx(width - 0.004) and c[2] == 10.0 for c in last)
        assert motors.calls[:-2][-2:] == hold[-2:]          # the force hold comes after it


# ----- the gear ---------------------------------------------------------------

def _drive_finger_1(cid, rb, model, target):
    f1, f2 = model.finger_joints
    p.setJointMotorControl2(rb, f2, p.VELOCITY_CONTROL, targetVelocity=0, force=0,
                            physicsClientId=cid)
    for _ in range(240):
        p.setJointMotorControl2(rb, f1, p.POSITION_CONTROL, targetPosition=target,
                                force=10.0, physicsClientId=cid)
        p.stepSimulation(physicsClientId=cid)
    return [p.getJointState(rb, fj, physicsClientId=cid)[0] for fj in (f1, f2)]


def test_d9_setup_couples_the_fingers(registry, panda):
    cid, rb, model = panda
    from tampura_bridge import policy
    registry.ENABLED = frozenset({'force_hold', 'solver_iters'})
    policy.d9_setup(_fake_world(cid, rb), model)
    assert p.getNumConstraints(physicsClientId=cid) == 1
    for target in (0.010, 0.030):
        q1, q2 = _drive_finger_1(cid, rb, model, target)
        assert abs(q1 - target) < 0.001
        assert abs(q1 - q2) < 0.00005                  # coupled within 0.05 mm


def test_d9_setup_without_the_switch_creates_no_gear(registry, panda):
    cid, rb, model = panda
    from tampura_bridge import policy
    policy.d9_setup(_fake_world(cid, rb), model)
    assert p.getNumConstraints(physicsClientId=cid) == 0
    q1, q2 = _drive_finger_1(cid, rb, model, 0.010)
    assert abs(q1 - q2) > 0.005                        # finger 2 stays where it was


def test_our_world_gets_the_gear_at_load_and_after_reset(registry):
    from world.boxel_env import BoxelTestEnv, random_pairs_scene
    registry.ENABLED = frozenset({'force_hold', 'solver_iters'})
    prev = robot_utils.robot_model()
    env = BoxelTestEnv(gui=False, scene_config=random_pairs_scene(seed=1))
    try:
        cid, rb = env.client_id, env.objects['robot'].object_id
        model = robot_utils.robot_model()
        assert p.getNumConstraints(physicsClientId=cid) == 1
        assert p.getNumConstraints(physicsClientId=env.plan_client_id) == 0
        q1, q2 = _drive_finger_1(cid, rb, model, 0.012)
        assert abs(q1 - q2) < 0.00005
        env.reset()
        cid, rb = env.client_id, env.objects['robot'].object_id
        assert p.getNumConstraints(physicsClientId=cid) == 1
        q1, q2 = _drive_finger_1(cid, rb, model, 0.012)
        assert abs(q1 - q2) < 0.00005
    finally:
        env.close()
        robot_utils.use_robot_model(prev)


# ----- the held box -------------------------------------------------------------

def test_a_held_box_stays_held_and_centred(registry, panda):
    """The die-sized box 2 mm off the hand's centre: the coupled close
    centres it, and with the pedestal gone it is still between both pads
    200 steps later, the fingers centred."""
    cid, rb, model = panda
    from tampura_bridge import policy
    registry.ENABLED = frozenset({'force_hold', 'solver_iters'})
    p.setPhysicsEngineParameter(numSolverIterations=200, physicsClientId=cid)
    policy.d9_setup(_fake_world(cid, rb), model)
    box, ped, axis = _box_between_pads(cid, rb, model, offset=0.002)
    width = robot_utils.close_gripper_until_contact(rb, force=60.0, ignore_body_ids={ped})
    assert width is not None
    p.removeBody(ped, physicsClientId=cid)
    for _ in range(200):
        p.stepSimulation(physicsClientId=cid)
    pads = {c[3] for c in p.getContactPoints(bodyA=rb, bodyB=box, physicsClientId=cid)}
    assert pads == set(model.finger_joints)
    nf = sum(c[9] for c in p.getContactPoints(bodyA=rb, bodyB=box, physicsClientId=cid)
             if c[3] in model.finger_joints)
    assert nf >= 0.5                                   # _verify_holding's floor
    q1, q2 = (p.getJointState(rb, fj, physicsClientId=cid)[0] for fj in model.finger_joints)
    assert abs(q1 - q2) < 0.00005                      # the pair centred
    ee = np.asarray(p.getLinkState(rb, model.ee_link, physicsClientId=cid)[0])
    bp = np.asarray(p.getBasePositionAndOrientation(box, physicsClientId=cid)[0])
    assert abs(float(np.dot(bp - ee, axis))) < 0.0005  # the box on the hand's axis
