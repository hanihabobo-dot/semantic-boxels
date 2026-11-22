"""#P4 B3's tests (PAPER_AUDIT P4.4 B3, ACCEPTANCE): the robot model by name,
the adopt-existing-client path, main()'s new keyword arguments and D7's loop
change, on our own scene adopted the way the bridge adopts TAMPURA's world.

The adopted world is a random-pairs scene built by BoxelTestEnv in client 0
(the default client execution.py drives), whose own plan twin is then
disconnected; AdoptedEnv adopts client 0 and builds a fresh twin from the
bodies' URDFs and collision shapes, as B2's adapter will from TAMPURA's.
"""
import json
import os
import random

import numpy as np
import pybullet as p
import pybullet_data
import pytest

from acting import robot_utils
from console import telemetry
import test_full_pipeline as tfp
from world import world_eye
from world.boxel_env import BoxelTestEnv, random_pairs_scene
from world.boxel_types import ObjectInfo
from console.run_logger import RunLogger, parse_pipeline_args

THEIR_PANDA = ('/root/tampura-work/tampura_environments/models/srl/'
               'franka_panda/panda.urdf')
SEED = 1


# ----- (a) the robot model by name ---------------------------------------

def test_pybullet_data_panda_resolves_to_todays_indices():
    c = p.connect(p.DIRECT)
    try:
        rb = p.loadURDF(os.path.join(pybullet_data.getDataPath(),
                                     'franka_panda/panda.urdf'),
                        useFixedBase=True, physicsClientId=c)
        m = robot_utils.resolve_robot_model(rb, c)
        assert m == robot_utils.PANDA_PYBULLET_DATA
        assert m.arm_joints == (0, 1, 2, 3, 4, 5, 6)
        assert m.finger_joints == (9, 10) and m.ee_link == 11
        # The one pair beyond the hand-written set names panda_grasptarget,
        # which has no collision shape, so no contact can carry it.
        extra = m.ignored_self_pairs - robot_utils._PANDA_IGNORED_SELF_PAIRS
        assert extra == {(8, 11)}
        assert robot_utils._PANDA_IGNORED_SELF_PAIRS <= m.ignored_self_pairs
        assert p.getCollisionShapeData(rb, 11, physicsClientId=c) == ()
    finally:
        p.disconnect(c)


@pytest.mark.skipif(not os.path.isfile(THEIR_PANDA),
                    reason="TAMPURA's tree is not on this machine")
def test_their_panda_resolves_by_name():
    c = p.connect(p.DIRECT)
    try:
        rb = p.loadURDF(THEIR_PANDA, useFixedBase=True, physicsClientId=c)
        m = robot_utils.resolve_robot_model(rb, c)
        assert m.arm_joints == (0, 1, 2, 3, 4, 5, 6)
        assert m.finger_joints == (12, 13) and m.ee_link == 14   # BF#4 (a)
        assert m.gripper_links == frozenset(range(6, 15))
        assert m.finger_limits == ((0.0, 0.04), (0.0, 0.04))
        # No self-contact outside the ignored pairs at REST_POSES with the
        # fingers open (the hand, camera frame and fingers are rigid).
        for j, q in zip(m.arm_joints, robot_utils.REST_POSES):
            p.resetJointState(rb, j, q, physicsClientId=c)
        for fj in m.finger_joints:
            p.resetJointState(rb, fj, 0.04, physicsClientId=c)
        p.performCollisionDetection(physicsClientId=c)
        bad = {(min(x[3], x[4]), max(x[3], x[4]))
               for x in p.getContactPoints(rb, rb, physicsClientId=c)}
        assert bad <= m.ignored_self_pairs, bad - m.ignored_self_pairs
    finally:
        p.disconnect(c)


# ----- the adopted world -------------------------------------------------

class AdoptedEnv(BoxelTestEnv):
    """Adopts the executing client of an already-built scene."""

    def __init__(self, src):
        self._src = src
        super().__init__(gui=False, adopt_client=src.client_id)

    def _adopt_scene(self):
        src = self._src
        self.table_surface_height = src.table_surface_height
        self.table_x_range = src.table_x_range
        self.table_y_range = src.table_y_range
        self._tray_xy = None
        for name, info in src.objects.items():
            self.objects[name] = ObjectInfo(
                object_id=info.object_id, name=name, position=None,
                orientation=None, size=info.size, is_visible=False,
                is_occluder=info.is_occluder, is_tray=info.is_tray)
        o = src.objects
        self._plan_load_urdf(o['plane'].object_id, 'plane.urdf',
                             [0, 0, 0], [0, 0, 0, 1])
        self._plan_load_urdf(o['table'].object_id, 'table/table.urdf',
                             [0.5, 0.0, -0.3], [0, 0, 0, 1], useFixedBase=True)
        self.plan_robot_id = self._plan_load_urdf(
            o['robot'].object_id, 'franka_panda/panda.urdf',
            [-0.4, 0.0, 0.0], [0, 0, 0, 1], useFixedBase=True)
        for name, info in o.items():
            if name in ('plane', 'table', 'robot'):
                continue
            self._plan_register_twin(info.object_id,
                                     _twin_from_shape(info.object_id,
                                                      self.client_id,
                                                      self.plan_client_id))


def _twin_from_shape(body, src_client, dst_client):
    """A plan-twin body with the source body's collision shape (test only)."""
    s = p.getCollisionShapeData(body, -1, physicsClientId=src_client)[0]
    kind, dims = s[2], s[3]
    if kind == p.GEOM_BOX:
        col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[d / 2 for d in dims],
                                     physicsClientId=dst_client)
    elif kind == p.GEOM_CYLINDER:
        col = p.createCollisionShape(p.GEOM_CYLINDER, radius=dims[1],
                                     height=dims[0], physicsClientId=dst_client)
    else:
        col = p.createCollisionShape(p.GEOM_SPHERE, radius=dims[0],
                                     physicsClientId=dst_client)
    mass = p.getDynamicsInfo(body, -1, physicsClientId=src_client)[0]
    return p.createMultiBody(baseMass=mass, baseCollisionShapeIndex=col,
                             basePosition=[5, 5, -5], physicsClientId=dst_client)


def _source_world(seed):
    """Our scene in client 0 with its own plan twin dropped; returns the
    env, a visible target and a hidden one (oracle reads: test code)."""
    random.seed(seed)
    np.random.seed(seed)
    src = BoxelTestEnv(gui=False, scene_config=random_pairs_scene(seed=seed))
    assert src.client_id == 0
    p.disconnect(src.plan_client_id)
    visible, _ = src.oracle_detect_objects()
    targets = [n for n, i in src.objects.items()
               if not i.is_occluder and n not in ('plane', 'table', 'robot')]
    shown = [t for t in targets if t in visible]
    hidden = [t for t in targets if t not in visible]
    return src, (shown or hidden)[0], (hidden or shown)[0]


def _run_main(tmp_path, env, target, **kwargs):
    tfp.args = parse_pipeline_args(['--no-gui', '--scene', 'random-pairs',
                                    '--seed', str(SEED), '--goal', 'holding',
                                    '--log-level', 'quiet',
                                    # D7's tests assume the first move to
                                    # q_home is the post-pick one; M8 adds
                                    # sense moves there (BF#34).
                                    '--m8', 'off'])
    logger = RunLogger(verbosity='quiet', log_dir=str(tmp_path / 'logs'))
    try:
        out = tfp.main(gui=False, run_logger=logger, goal_kind='holding',
                       draw_boxel_overlays=False, env=env, target_name=target,
                       oracle_phases=False, gui_hold_s=0, **kwargs)
    finally:
        telemetry.disable()
        world_eye.disable()
        logger.close()
    rows = [json.loads(line) for line in
            open(logger.run_dir / 'ledger.jsonl', encoding='utf-8')]
    return out, rows


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src, shown, hidden = _source_world(SEED)
    yield src, shown, hidden
    for c in range(8):
        try:
            p.disconnect(c)
        except Exception:
            pass
    robot_utils.use_robot_model(robot_utils.PANDA_PYBULLET_DATA)


def _record_rays(monkeypatch):
    calls = []
    for name in ('rayTest', 'rayTestBatch'):
        orig = getattr(p, name)

        def hook(*a, _orig=orig, _name=name, **kw):
            calls.append((_name, kw.get('physicsClientId', 0)))
            return _orig(*a, **kw)
        monkeypatch.setattr(p, name, hook)
    return calls


# ----- (b), (c): stop_before_planning, after_settle, raycast client -------

def test_adopted_stop_before_planning(world, tmp_path, monkeypatch):
    src, shown, _ = world
    bodies = p.getNumBodies(physicsClientId=0)
    env = AdoptedEnv(src)
    assert p.getNumBodies(physicsClientId=0) == bodies
    assert env.plan_client_id != 0
    env.shadow_raycast_client = env.plan_client_id

    steps = []
    orig_step = p.stepSimulation
    monkeypatch.setattr(p, 'stepSimulation',
                        lambda *a, **k: (steps.append(k.get('physicsClientId', 0)),
                                         orig_step(*a, **k))[1])
    rays = _record_rays(monkeypatch)

    def state():
        poses = [p.getBasePositionAndOrientation(b, physicsClientId=0)
                 for b in range(p.getNumBodies(physicsClientId=0))]
        rid = env.objects['robot'].object_id
        joints = [p.getJointState(rid, j, physicsClientId=0)[:2]
                  for j in range(p.getNumJoints(rid, physicsClientId=0))]
        return poses, joints

    seen = {}

    def after_settle(e):
        assert e is env and 'hook' not in seen
        seen['hook'] = (len(steps), state())

    orig_obs = env.get_camera_observation

    def first_render():
        seen.setdefault('render', (len(steps), state()))
        return orig_obs()
    monkeypatch.setattr(env, 'get_camera_observation', first_render)

    from planning import pddlstream_planner
    plan_calls = []
    orig_plan = pddlstream_planner.PDDLStreamPlanner.plan
    monkeypatch.setattr(pddlstream_planner.PDDLStreamPlanner, 'plan',
                        lambda self, *a, **k: (plan_calls.append(1),
                                               orig_plan(self, *a, **k))[1])

    out, rows = _run_main(tmp_path, env, shown, after_settle=after_settle,
                          stop_before_planning=True)
    assert out is None
    assert plan_calls == [] and not [r for r in rows if r['kind'] == 'plan']
    # The hook ran once, after main()'s 50 settle steps; nothing stepped or
    # moved between it and the first render.
    assert seen['hook'][0] >= 50
    assert seen['hook'] == seen['render']
    # Every shadow ray hit the plan twin; none reached the executing world.
    assert rays and all(c == env.plan_client_id for _, c in rays), rays
    # The adopted client survives main(); only the plan twin closed.
    assert p.getConnectionInfo(0)['isConnected'] == 1
    assert p.getConnectionInfo(env.plan_client_id)['isConnected'] == 0
    assert p.getNumBodies(physicsClientId=0) == bodies


# ----- (d), D7 (iv) to (vii): one full episode ----------------------------

def test_adopted_goal_at_home_episode(world, tmp_path, monkeypatch):
    """D7 (iv)'s two tests in one episode: the post-pick move to q_home is
    re-solved with the target as cargo, and after an injected at-home miss
    the planner plans the corrective move to q_home while holding.  Also:
    no ray reaches the executing client, and the adopted client survives."""
    src, shown, _ = world
    env = AdoptedEnv(src)
    env.shadow_raycast_client = env.plan_client_id
    rays = _record_rays(monkeypatch)

    # The injected miss: the first readback after a move to q_home (the
    # second call; the first is main()'s initial readback) reads 5 mrad off.
    calls = []
    orig_read = tfp.arm_joint_positions

    def readback(*a, **k):
        q = orig_read(*a, **k)
        calls.append(1)
        if len(calls) == 2:
            q = q.copy()
            q[0] += 5e-3
        return q
    monkeypatch.setattr(tfp, 'arm_joint_positions', readback)

    target_plan = env.plan_body_id(env.objects[shown].object_id)
    out, rows = _run_main(tmp_path, env, shown, goal_at_home=True,
                          held_cargo_resolve=True, home_hold_step_cap=2400)

    plans = [r for r in rows if r['kind'] == 'plan']
    assert all(r['goal'][0] == 'and' and r['goal'][2] == ['at_config', 'q_home']
               for r in plans if r.get('call') == 'mission'), plans
    tests = [r for r in rows if r['kind'] == 'at_home_test']
    assert tests and tests[0]['passed'] is False
    assert tests[0]['config'] == 'q_readback_1'
    # (a) the post-pick move to q_home: re-solved with the target as cargo.
    steps = [r for r in rows if r['kind'] in ('step', 'move_resolve',
                                               'at_home_test', 'plan')]
    first_home = next(i for i, r in enumerate(steps)
                      if r['kind'] == 'step' and r['action'] == 'move'
                      and r['args'][1] == 'cfg:q_home')
    assert steps[first_home + 1]['kind'] == 'move_resolve'
    assert steps[first_home + 1]['cargo'] == [target_plan]
    assert steps[first_home + 1]['goal_equal'] is True
    # (b) the corrective move after the miss: planned from q_readback_1 to
    # q_home while holding, and re-solved with the cargo.
    later = steps[first_home + 1:]
    corr = next(i for i, r in enumerate(later)
                if r['kind'] == 'step' and r['action'] == 'move'
                and r['args'][:2] == ['cfg:q_readback_1', 'cfg:q_home'])
    plan_row = next(r for r in reversed(later[:corr]) if r['kind'] == 'plan')
    assert plan_row['actions'][0][:3] == ['move', 'cfg:q_readback_1',
                                          'cfg:q_home']
    assert later[corr + 1]['kind'] == 'move_resolve'
    assert later[corr + 1]['cargo'] == [target_plan]
    print(f"[B3 D7] at-home tests: {[(t['passed'], t['max_abs_err'], t['hold_steps']) for t in tests]}; "
          f"main() returned {out}")
    # No ray on the executing world; the adopted client survives main().
    assert rays and all(c == env.plan_client_id for _, c in rays)
    assert p.getConnectionInfo(0)['isConnected'] == 1
