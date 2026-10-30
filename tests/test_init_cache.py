"""BF#53, M8's init cache (observe_views.ObserveViews): between two inits
that leave every twin body where it was, a look configuration's wrist
render and a fixed sense configuration's eye render are reused and the
facts are the same; a body that moved empties the cache; off, every init
renders again.  A DIRECT world with pybullet_data's Panda and one box, as
tests/test_m8_observe.py builds it."""
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pybullet_data
import pytest

import observe_views
import robot_utils
from boxel_data import BoxelData, BoxelType
from streams import RobotConfig

HALF = (0.0088, 0.0088, 0.0089)
BOX_XY = (0.15, 0.05)
BASE = (-0.4, 0.0)
EYE = (0.6, 0.0, 0.9)


@pytest.fixture
def world():
    cid = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=cid)
    plane = p.loadURDF('plane.urdf', physicsClientId=cid)
    robot = p.loadURDF('franka_panda/panda.urdf', [BASE[0], BASE[1], 0.0],
                       useFixedBase=True, physicsClientId=cid)
    for j, v in zip(robot_utils.robot_model().arm_joints, robot_utils.REST_POSES):
        p.resetJointState(robot, j, v, physicsClientId=cid)
    for fj in (9, 10):
        p.resetJointState(robot, fj, 0.04, physicsClientId=cid)
    box = p.createMultiBody(
        0.005, p.createCollisionShape(p.GEOM_BOX, halfExtents=HALF, physicsClientId=cid),
        p.createVisualShape(p.GEOM_BOX, halfExtents=HALF, physicsClientId=cid),
        basePosition=[BOX_XY[0], BOX_XY[1], HALF[2]], physicsClientId=cid)
    view = p.computeViewMatrix(list(EYE), [0.2, 0.0, 0.0], [1.0, 0.0, 0.0])
    proj = p.computeProjectionMatrixFOV(50.0, 160.0 / 120.0, 0.05, 4.0)
    objs = {n: SimpleNamespace(object_id=b) for n, b in
            (('plane', plane), ('robot', robot), ('die', box))}
    env = SimpleNamespace(client_id=cid, plan_client_id=cid, plan_robot_id=robot,
                          objects=objs, _gui_to_plan={b: b for b in (plane, robot, box)},
                          table_surface_height=0.0, image_width=160, image_height=120,
                          near_plane=0.05, far_plane=4.0,
                          _view_and_projection_matrices=lambda: (view, proj))
    yield SimpleNamespace(cid=cid, robot=robot, box=box, env=env)
    p.disconnect(cid)


def _die_boxel():
    lo = np.array([BOX_XY[0] - HALF[0], BOX_XY[1] - HALF[1], 0.0])
    return BoxelData(id='die', boxel_type=BoxelType.OBJECT, min_corner=lo,
                     max_corner=lo + 2 * np.array(HALF))


def _shadow():
    lo = np.array([0.15, -0.05, 0.0])
    return BoxelData(id='shadow_of_x', boxel_type=BoxelType.SHADOW, min_corner=lo,
                     max_corner=lo + np.array([0.10, 0.10, 0.06]))


def _rest():
    return RobotConfig(joint_positions=np.array(robot_utils.REST_POSES, dtype=float),
                       name='q_rest')


def _home():
    q = np.array(robot_utils.REST_POSES, dtype=float)
    q[1] -= 0.3                                   # another configuration, named home
    return RobotConfig(joint_positions=q, name='q_home')


def _names(facts, pred):
    return sorted(str(f[1].name) for f in facts if f[0] == pred)


def test_look_configurations_come_from_the_cache_until_a_body_moves(world):
    views = observe_views.ObserveViews(world.env, BASE)
    facts1, _ = views.init_facts(_rest(), None, [], [_die_boxel()], [_rest()])
    looks = _names(facts1, 'look_config')
    assert looks, 'the box must have at least one look configuration'
    renders1 = views.last_stats['twin_renders']
    assert renders1 >= len(looks) and views.last_stats['cached_looks'] == 0
    facts2, _ = views.init_facts(_rest(), None, [], [_die_boxel()], [_rest()])
    assert _names(facts2, 'look_config') == looks
    assert views.last_stats['cached_looks'] == 1
    assert views.last_stats['twin_renders'] == 0
    # the cached configurations are the same joints, fresh objects
    q1 = {f[1].name: f[1] for f in facts1 if f[0] == 'look_config'}
    q2 = {f[1].name: f[1] for f in facts2 if f[0] == 'look_config'}
    for n in q1:
        assert np.allclose(q1[n].joint_positions, q2[n].joint_positions)
        assert q1[n] is not q2[n]
    # a body moved: the cache is empty, everything renders again
    p.resetBasePositionAndOrientation(world.box, [BOX_XY[0] + 0.03, BOX_XY[1], HALF[2]],
                                      [0, 0, 0, 1], physicsClientId=world.cid)
    views.init_facts(_rest(), None, [], [_die_boxel()], [_rest()])
    assert views.last_stats['cached_looks'] == 0
    assert views.last_stats['twin_renders'] == renders1


def test_the_fixed_sense_render_is_reused_and_the_current_one_is_not(world):
    views = observe_views.ObserveViews(world.env, BASE)
    facts1, _ = views.init_facts(_rest(), _home(), [_shadow()], [], [_rest()])
    assert views.last_stats['twin_renders'] == 2          # current and home
    assert views.last_stats['cached_renders'] == 0
    facts2, _ = views.init_facts(_rest(), _home(), [_shadow()], [], [_rest()])
    assert views.last_stats['twin_renders'] == 1          # the current one only
    assert views.last_stats['cached_renders'] == 1
    assert _names(facts1, 'sense_view') == _names(facts2, 'sense_view')


def test_off_renders_at_every_init(world):
    views = observe_views.ObserveViews(world.env, BASE)
    views.cache_enabled = False
    views.init_facts(_rest(), _home(), [_shadow()], [_die_boxel()], [_rest()])
    n = views.last_stats['twin_renders']
    views.init_facts(_rest(), _home(), [_shadow()], [_die_boxel()], [_rest()])
    assert views.last_stats['twin_renders'] == n
    assert views.last_stats['cached_looks'] == 0
    assert views.last_stats['cached_renders'] == 0
