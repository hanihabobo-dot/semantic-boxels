"""#P4 B0: the runtime gate hooks trip on what they must and pass the rest.

Two throwaway DIRECT clients stand in for their executing world and our
plan twin: a Panda, a known task body (it has an OBJECT boxel) and a hidden
one.  Every positive case asserts the counter as well as the exception,
because the counter is what decides an episode (G21).
"""
import json
import types

import numpy as np
import pybullet as p
import pybullet_data
import pytest

import run_logger
from tampura_bridge import gate_hooks as gh

MISSION = ('and', ('holding', 'die'), ('at_config', 'q_home'))


@pytest.fixture
def w(tmp_path):
    c0 = p.connect(p.DIRECT)
    c1 = p.connect(p.DIRECT)
    for c in (c0, c1):
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=c)
    robot = p.loadURDF('franka_panda/panda.urdf', [0, 0, 0], useFixedBase=True,
                       physicsClientId=c0)
    known = p.loadURDF('cube_small.urdf', [0.5, 0.0, 0.05], physicsClientId=c0)
    hidden = p.loadURDF('cube_small.urdf', [0.5, 0.2, 0.05], physicsClientId=c0)
    twin = p.loadURDF('cube_small.urdf', [0.5, 0.0, 0.05], physicsClientId=c1)
    view = p.computeViewMatrix([0.1, -0.8, 0.7], [0.5, 0, 0], [0, 0, 1])
    proj = p.computeProjectionMatrixFOV(49.1, 640 / 480, 0.02, 5.0)
    run_logger.ledger_open(tmp_path)
    cfg = gh.GateConfig(executing_client=c0, robot_id=robot,
                        task_body_ids=frozenset({known, hidden}),
                        has_object_boxel=lambda b: b == known,
                        camera_view=tuple(view), camera_proj=tuple(proj),
                        mission_goal=MISSION, target_symbol='die')
    gh.install(cfg)
    gh.set_phase('main')
    yield types.SimpleNamespace(c0=c0, c1=c1, robot=robot, known=known,
                                hidden=hidden, twin=twin, view=view,
                                proj=proj, run_dir=tmp_path)
    run_logger.dispatch_end('ok')
    gh.uninstall()
    run_logger.ledger_close()
    p.disconnect(c0)
    p.disconnect(c1)


def _trips(gate, fn, *args, **kwargs):
    before = gh.counts().get(gate, 0)
    with pytest.raises(gh.GateViolation):
        fn(*args, **kwargs)
    assert gh.counts().get(gate, 0) == before + 1


def _ledger(run_dir, kind):
    run_logger._ledger_file.flush()
    rows = [json.loads(l) for l in open(run_dir / 'ledger.jsonl')]
    return [r for r in rows if r['kind'] == kind]


# ----- G14: state writes -------------------------------------------------

def test_teleport_of_a_task_body_trips_g14(w):
    _trips('G14', p.resetBasePositionAndOrientation, w.known, [0, 0, 1],
           [0, 0, 0, 1], physicsClientId=w.c0)
    _trips('G14', p.resetBaseVelocity, w.hidden, [0, 0, 1],
           physicsClientId=w.c0)
    _trips('G14', p.changeDynamics, w.known, -1, mass=0.0,
           physicsClientId=w.c0)
    _trips('G14', p.createConstraint, w.robot, 11, w.known, -1,
           p.JOINT_FIXED, [0, 0, 0], [0, 0, 0], [0, 0, 0],
           physicsClientId=w.c0)
    assert _ledger(w.run_dir, 'gate_violation')


def test_the_plan_twin_may_be_written(w):
    p.resetBasePositionAndOrientation(w.twin, [0, 0, 1], [0, 0, 0, 1],
                                      physicsClientId=w.c1)
    assert gh.counts().get('G14', 0) == 0


def test_bodyless_writes_trip_on_the_executing_client(w):
    _trips('G14', p.loadURDF, 'cube_small.urdf', physicsClientId=w.c0)
    _trips('G14', p.setGravity, 0, 0, 0, physicsClientId=w.c0)
    _trips('G14', p.saveState, physicsClientId=w.c0)
    _trips('G14', p.setRealTimeSimulation, 1, physicsClientId=w.c0)
    p.setRealTimeSimulation(0, physicsClientId=w.c0)
    p.setGravity(0, 0, -9.81, physicsClientId=w.c1)


def test_setup_phase_allows_d9_but_no_physics_step(w):
    gh.set_phase('setup')
    p.setGravity(0, 0, -9.81, physicsClientId=w.c0)
    p.changeDynamics(w.known, -1, lateralFriction=1.0, physicsClientId=w.c0)
    p.resetJointState(w.robot, 9, 0.04, physicsClientId=w.c0)
    assert gh.counts().get('G14', 0) == 0
    _trips('G6', p.stepSimulation, physicsClientId=w.c0)


def test_bullet_client_calls_reach_the_hooks_with_their_client_id(w):
    from pybullet_utils import bullet_client
    bc = bullet_client.BulletClient(connection_mode=p.DIRECT)
    try:
        bc.setAdditionalSearchPath(pybullet_data.getDataPath())
        body = bc.loadURDF('cube_small.urdf', [0, 0, 0.05])
        bc.resetBasePositionAndOrientation(body, [0.3, 0, 0.05], [0, 0, 0, 1])
        pos, _ = bc.getBasePositionAndOrientation(body)
        assert abs(pos[0] - 0.3) < 1e-9
        assert gh.counts().get('G14', 0) == 0
        # The same call style on the executing client is trapped.
        own = bc._client
        bc._client = w.c0
        _trips('G14', bc.resetBasePositionAndOrientation, w.known,
               [0, 0, 1], [0, 0, 0, 1])
        bc._client = own
    finally:
        bc.disconnect()


# ----- G3: motion only inside a dispatched action ------------------------

def test_motor_command_outside_a_dispatched_action_trips_g3(w):
    _trips('G3', p.setJointMotorControl2, w.robot, 0, p.POSITION_CONTROL,
           targetPosition=0.1, physicsClientId=w.c0)
    run_logger.dispatch_begin(1, 1, 'move', ['q0', 'q1'])
    p.setJointMotorControl2(w.robot, 0, p.POSITION_CONTROL,
                            targetPosition=0.1, physicsClientId=w.c0)
    run_logger.dispatch_end('ok')
    assert gh.counts().get('G3', 0) == 1


# ----- G14: the executor's IK on the executing robot ---------------------

def test_solve_ik_is_exempt_inside_a_dispatch_and_net_zero(w):
    import robot_utils
    arm = [p.getJointState(w.robot, j, physicsClientId=w.c0)[0]
           for j in range(7)]
    run_logger.dispatch_begin(1, 1, 'pick', ['known'])
    q = robot_utils.solve_ik(w.robot, np.array([0.45, 0.0, 0.3]),
                             physics_client=w.c0)
    run_logger.dispatch_end('ok')
    assert q is not None
    assert gh.counts().get('G14', 0) == 0
    assert arm == [p.getJointState(w.robot, j, physicsClientId=w.c0)[0]
                   for j in range(7)]


def test_solve_ik_outside_a_dispatch_trips_g14(w):
    import robot_utils
    _trips('G14', robot_utils.solve_ik, w.robot, np.array([0.45, 0.0, 0.3]),
           physics_client=w.c0)


def test_arm_reset_outside_solve_ik_trips_g14_even_in_a_dispatch(w):
    run_logger.dispatch_begin(1, 1, 'move', ['q0', 'q1'])
    _trips('G14', p.resetJointState, w.robot, 0, 0.5, physicsClientId=w.c0)
    run_logger.dispatch_end('ok')


def test_collision_probe_on_the_executing_client_trips_g14(w):
    # Whether or not the probe swallows the exception, the counter holds.
    import robot_utils
    try:
        robot_utils.is_config_collision_free(w.robot, [0.0] * 7,
                                             physics_client=w.c0)
    except gh.GateViolation:
        pass
    assert gh.counts().get('G14', 0) >= 1


# ----- G6: no physics step after the last dispatched action --------------

def test_steps_after_the_last_dispatch_are_counted(w):
    run_logger.dispatch_begin(1, 1, 'move', ['q0', 'q1'])
    p.stepSimulation(physicsClientId=w.c0)
    run_logger.dispatch_end('ok')
    p.stepSimulation(physicsClientId=w.c0)
    rec = gh.gate_record()
    assert rec['steps_after_last_dispatch'] == 1
    assert rec['counts']['G6'] == 1
    gh.set_phase('post')
    _trips('G6', p.stepSimulation, physicsClientId=w.c0)


def test_settle_before_the_first_dispatch_is_not_a_g6_step(w):
    for _ in range(50):
        p.stepSimulation(physicsClientId=w.c0)
    rec = gh.gate_record()
    assert rec['counts'].get('G6', 0) == 0
    assert rec['steps']['main_outside_dispatch'] == 50


# ----- G8(b): the identity-map boundary ----------------------------------

def test_queries_of_a_hidden_body_trip_g8(w):
    _trips('G8', p.getAABB, w.hidden, physicsClientId=w.c0)
    _trips('G8', p.getBasePositionAndOrientation, w.hidden,
           physicsClientId=w.c0)
    _trips('G8', p.getClosestPoints, w.known, w.hidden, 0.1,
           physicsClientId=w.c0)
    _trips('G8', p.getContactPoints, physicsClientId=w.c0)
    p.getAABB(w.known, physicsClientId=w.c0)
    p.getContactPoints(bodyA=w.robot, physicsClientId=w.c0)
    p.getAABB(w.twin, physicsClientId=w.c1)
    with gh.write_only('world_eye'):
        p.getAABB(w.hidden, physicsClientId=w.c0)
    with gh.scoring():
        p.getBasePositionAndOrientation(w.hidden, physicsClientId=w.c0)
    assert gh.counts()['G8'] == 4


def test_rays_on_the_executing_client_trip_g8(w):
    _trips('G8', p.rayTest, [0, 0, 1], [0.5, 0.2, 0], physicsClientId=w.c0)
    _trips('G8', p.rayTestBatch, [[0, 0, 1]], [[0.5, 0.2, 0]],
           physicsClientId=w.c0)
    p.rayTest([0, 0, 1], [0.5, 0.2, 0], physicsClientId=w.c1)


# ----- G20: the camera ---------------------------------------------------

def test_renders_must_use_the_declared_eye(w):
    p.getCameraImage(32, 24, w.view, w.proj, physicsClientId=w.c0)
    other = p.computeViewMatrix([0, 0, 2], [0.5, 0, 0], [0, 0, 1])
    _trips('G20', p.getCameraImage, 32, 24, other, w.proj,
           physicsClientId=w.c0)
    with gh.capture('gui_pane'):
        p.getCameraImage(32, 24, other, w.proj, physicsClientId=w.c0)
    renders = _ledger(w.run_dir, 'render')
    assert [r['matched'] for r in renders] == [True, False, None]


# ----- G10 and G11(ii): planner identity, goal pin, call path ------------

def _bare_planner(cls=None):
    import pddlstream_planner as pp
    import streams
    cls = cls or pp.PDDLStreamPlanner
    planner = cls.__new__(cls)
    planner.streams = streams.BoxelStreams.__new__(streams.BoxelStreams)
    planner.domain_pddl = pp.read_pddl_file('domain_pddlstream.pddl')
    planner.stream_pddl = pp.read_pddl_file('stream.pddl')
    return planner


def test_goal_and_target_pin_g10(w):
    planner = _bare_planner()
    gh.check_plan_call(planner, MISSION, ['die'])
    gh.check_plan_call(planner, ('handempty',), ['die'])
    assert gh.counts().get('G10', 0) == 0
    # The pre-registered positive control: one extra conjunct trips it.
    steered = MISSION + (('obj_at_boxel', 'cup_0', 'free_3'),)
    _trips('G10', gh.check_plan_call, planner, steered, ['die'])
    _trips('G10', gh.check_plan_call, planner, MISSION, ['die', 'cup_0'])


def test_planner_subclass_and_domain_swap_trip_g10(w):
    import pddlstream_planner as pp

    class Sub(pp.PDDLStreamPlanner):
        pass

    _trips('G10', gh.check_plan_call, _bare_planner(Sub), MISSION, ['die'])
    planner = _bare_planner()
    planner.domain_pddl += '\n; one more line'
    _trips('G10', gh.check_plan_call, planner, MISSION, ['die'])


def test_solve_outside_plan_trips_g11(w):
    import pddlstream_planner as pp
    _trips('G11', pp.solve, None)


# ----- G16 and G21 -------------------------------------------------------

def test_oracle_path_and_gate_record(w):
    gh.count_update_object_positions()
    _trips('G16', gh.oracle_called)
    rec = gh.gate_record()
    assert rec['counts']['G16'] == 1
    assert rec['info']['G16_update_object_positions_noop'] == 1
    assert _ledger(w.run_dir, 'gate_record')[-1]['counts']['G16'] == 1
