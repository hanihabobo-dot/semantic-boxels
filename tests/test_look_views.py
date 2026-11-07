"""Path 9: the look viewpoints and the static look facts, on a DIRECT world
with our Panda, an occluder, a die and a hidden region behind the occluder.
No planner, no episode: the twin is the only client."""
import math
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pybullet_data
import pytest

import look_views
import observe_views
import pose_belief
import robot_utils
from boxel_data import BoxelData, BoxelRegistry, BoxelType

OCC = dict(centre=(0.10, 0.0), half=(0.05, 0.05, 0.075))
DIE = dict(centre=(0.30, 0.15), half=(0.0088, 0.0088, 0.0089))


def _box(cid, centre, half):
    return p.createMultiBody(
        0.005, p.createCollisionShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid),
        p.createVisualShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid),
        basePosition=[centre[0], centre[1], half[2]], physicsClientId=cid)


def _boxel(bid, kind, lo, hi, **kw):
    return BoxelData(id=bid, boxel_type=kind, min_corner=np.array(lo, dtype=float),
                     max_corner=np.array(hi, dtype=float), **kw)


@pytest.fixture
def world():
    cid = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=cid)
    plane = p.loadURDF('plane.urdf', physicsClientId=cid)
    robot = p.loadURDF('franka_panda/panda.urdf', [-0.4, 0.0, 0.0],
                       useFixedBase=True, physicsClientId=cid)
    for fj in (9, 10):
        p.resetJointState(robot, fj, 0.04, physicsClientId=cid)
    occ = _box(cid, OCC['centre'], OCC['half'])
    die = _box(cid, DIE['centre'], DIE['half'])
    objs = {n: SimpleNamespace(object_id=b) for n, b in
            (('plane', plane), ('robot', robot), ('occluder', occ), ('die', die))}
    env = SimpleNamespace(client_id=cid, plan_client_id=cid, plan_robot_id=robot,
                          objects=objs,
                          _gui_to_plan={b: b for b in (plane, robot, occ, die)},
                          table_surface_height=0.0)
    saved = dict(pose_belief.SWITCHES)
    pose_belief.SWITCHES.update({k: True for k in saved})
    reg = BoxelRegistry()
    o = OCC
    reg.add_boxel(_boxel('occluder', BoxelType.OBJECT,
                         [o['centre'][0] - o['half'][0], o['centre'][1] - o['half'][1], 0.0],
                         [o['centre'][0] + o['half'][0], o['centre'][1] + o['half'][1], 2 * o['half'][2]],
                         object_name='occluder'))
    d = DIE
    reg.add_boxel(_boxel('die', BoxelType.OBJECT,
                         [d['centre'][0] - d['half'][0], d['centre'][1] - d['half'][1], 0.0],
                         [d['centre'][0] + d['half'][0], d['centre'][1] + d['half'][1], 2 * d['half'][2]],
                         object_name='die'))
    reg.add_boxel(_boxel('shadow_a', BoxelType.SHADOW, [0.16, -0.05, 0.0], [0.26, 0.05, 0.05]))
    reg.add_boxel(_boxel('free_up_shadow', BoxelType.FREE_SPACE, [0.16, -0.10, 0.05],
                         [0.40, 0.10, 0.45]))
    reg.add_boxel(_boxel('free_up_occ', BoxelType.FREE_SPACE, [0.05, -0.05, 0.15],
                         [0.15, 0.05, 0.45]))
    reg.add_boxel(_boxel('free_side', BoxelType.FREE_SPACE, [0.05, 0.12, 0.0],
                         [0.20, 0.30, 0.45], on_surface='table'))
    views = observe_views.ObserveViews(env, (-0.4, 0.0))
    yield SimpleNamespace(cid=cid, robot=robot, env=env, reg=reg, views=views,
                          lv=look_views.LookViews(views))
    pose_belief.SWITCHES.clear()
    pose_belief.SWITCHES.update(saved)
    p.disconnect(cid)


def _home():
    from streams import RobotConfig
    return RobotConfig(joint_positions=np.array(robot_utils.REST_POSES, dtype=float),
                       name='q_home')


def _facts(world, regions=('shadow_a',), objects=('die',), **kw):
    return world.lv.facts(world.reg, [world.reg.get_boxel(r) for r in regions],
                          [world.reg.get_boxel(o) for o in objects], _home(), **kw)


# ----- the pose ----------------------------------------------------------------

def test_camera_pose_is_a_right_handed_frame_and_tilt_zero_is_m8s_pose():
    cam = look_views.camera_pose([0.2, 0.0, 0.3], 0.0, 0.0, [0.3, 0.0])
    r = cam[:3, :3]
    assert np.allclose(r.T @ r, np.eye(3), atol=1e-9)
    assert np.isclose(np.linalg.det(r), 1.0)
    assert np.allclose(r[:, 2], [0, 0, -1])
    assert np.allclose(r[:, 0], [1, 0, 0]) and np.allclose(r[:, 1], [0, -1, 0])
    tilted = look_views.camera_pose([0.2, 0.0, 0.3], math.radians(20), math.pi / 2, [0.3, 0.0])
    t = tilted[:3, :3]
    assert np.allclose(t.T @ t, np.eye(3), atol=1e-9)
    assert np.isclose(np.degrees(np.arccos(-t[2, 2])), 20.0)      # from straight down
    assert t[0, 2] > 0                                            # toward +x, the goal


# ----- the facts ---------------------------------------------------------------

def test_a_region_behind_an_occluder_gets_a_certified_view(world):
    facts, stats = _facts(world)
    by = {}
    for f in facts:
        by.setdefault(f[0], []).append(f)
    assert stats['certified'] >= 1 and 'shadow_a' not in stats['no_view']
    cfgs = {f[1] for f in by['reveals'] if f[2] == 'shadow_a'}
    assert cfgs, 'no configuration reveals the region'
    for q in cfgs:
        assert ('Config', q) in facts
        (cb,) = [f for f in by['config_for_boxel'] if f[1] is q]
        v = world.reg.get_boxel(cb[2])
        assert v.boxel_type == BoxelType.FREE_SPACE
        world.views._set_arm(q.joint_positions)
        cam = robot_utils.wrist_camera_pose(world.robot, world.cid)[:3, 3]
        assert np.all(cam >= v.min_corner - 0.005) and np.all(cam <= v.max_corner + 0.005)
    # no body is listed as hiding a view from above
    assert not any(f[0] == 'blocks_look_at' and f[4] == 'shadow_a' and f[1] == f[2]
                   for f in by.get('blocks_look_at', []))


def test_config_names_are_unique_and_prefixed(world):
    facts, _ = _facts(world)
    names = [f[1].name for f in facts if f[0] == 'Config']
    assert len(names) == len(set(names))
    assert all(n.startswith('look_') for n in names)


def test_the_die_is_revealed_complete_from_above(world):
    facts, _ = _facts(world)
    assert any(f[0] == 'reveals' and f[2] == 'die' for f in facts)


def test_the_facts_are_deterministic(world):
    a, _ = _facts(world)
    b, _ = _facts(world)
    key = lambda fs: [(f[0],) + tuple(getattr(x, 'name', x) for x in f[1:]) for f in fs]
    assert key(a) == key(b)
    assert all(np.array_equal(x[1].joint_positions, y[1].joint_positions)
               for x, y in zip(a, b) if x[0] == 'Config')


def test_a_goal_outside_every_boxel_has_no_view_and_is_named(world):
    far = world.reg.add_boxel(_boxel('shadow_far', BoxelType.SHADOW,
                                     [0.9, 0.9, 0.0], [0.95, 0.95, 0.05]))
    facts, stats = _facts(world, regions=('shadow_far',), objects=())
    assert 'shadow_far' in stats['no_view']
    assert not any(f[0] == 'reveals' for f in facts)


def test_the_arm_is_put_back(world):
    before = world.views._arm()
    _facts(world)
    assert np.allclose(world.views._arm(), before)


# ----- the render rule ---------------------------------------------------------

def _render(world, eye, target, up=(0.0, 0.0, 1.0)):
    view = p.computeViewMatrix(list(eye), list(target), list(up))
    proj = p.computeProjectionMatrixFOV(
        fov=robot_utils.WRIST_CAMERA_FOV_DEG,
        aspect=robot_utils.WRIST_CAMERA_WIDTH / robot_utils.WRIST_CAMERA_HEIGHT,
        nearVal=robot_utils.WRIST_CAMERA_NEAR, farVal=robot_utils.WRIST_CAMERA_FAR)
    _b, depth_m, seg = observe_views._render(
        world.cid, view, proj, robot_utils.WRIST_CAMERA_WIDTH,
        robot_utils.WRIST_CAMERA_HEIGHT, robot_utils.WRIST_CAMERA_NEAR,
        robot_utils.WRIST_CAMERA_FAR)
    return depth_m, seg, view, proj


def test_a_body_in_front_is_a_blocker_not_a_loss(world):
    goal = look_views.region_goal(world.reg.get_boxel('shadow_a'))
    movable, _ = world.lv._movable(world.reg)
    depth_m, seg, view, proj = _render(world, (-0.05, 0.0, 0.08), (0.21, 0.0, 0.02))
    mine = world.lv._statuses([goal], (depth_m, seg, view, proj), movable, world.reg)['shadow_a']
    assert mine.revealed and mine.blockers == ['occluder']
    assert mine.total_frac > look_views.LOOK_TOL_REGION >= mine.hard_frac


def test_a_clear_view_and_a_region_outside_the_frame(world):
    goal = look_views.region_goal(world.reg.get_boxel('shadow_a'))
    movable, _ = world.lv._movable(world.reg)
    # the camera straight over the region
    depth_m, seg, view, proj = _render(world, (0.21, 0.0, 0.30), (0.21, 0.0, 0.0),
                                       up=(1.0, 0.0, 0.0))
    clear = world.lv._statuses([goal], (depth_m, seg, view, proj), movable, world.reg)['shadow_a']
    assert clear.revealed and not clear.blockers
    # a region outside the frame is lost, not blockable
    far = look_views.region_goal(_boxel('x', BoxelType.SHADOW, [0.9, 0.9, 0.0], [0.95, 0.95, 0.05]))
    lost = world.lv._statuses([far], (depth_m, seg, view, proj), movable, world.reg)['x']
    assert not lost.revealed and lost.hard_frac > 0.9


def test_content_of_a_region_is_seen_not_a_blocker(world):
    box = _boxel('shadow_c', BoxelType.SHADOW, [0.04, -0.06, 0.0], [0.16, 0.06, 0.2])
    goal = look_views.region_goal(box)                  # encloses the occluder
    movable, _ = world.lv._movable(world.reg)
    depth_m, seg, view, proj = _render(world, (0.10, 0.0, 0.35), (0.10, 0.0, 0.0),
                                       up=(1.0, 0.0, 0.0))
    st = world.lv._statuses([goal], (depth_m, seg, view, proj), movable, world.reg)['shadow_c']
    assert st.revealed and st.blockers == []


# ----- placement facts ---------------------------------------------------------

def test_a_placed_body_blocks_only_inside_the_corridor(world):
    goal = look_views.region_goal(world.reg.get_boxel('shadow_a'))
    cam = np.array([0.45, 0.0, 0.20])
    between = (np.array([0.31, -0.02, 0.0]), np.array([0.35, 0.02, 0.3]))
    beside = (np.array([0.31, 0.23, 0.0]), np.array([0.35, 0.27, 0.3]))
    assert look_views.LookViews._placed_blocks(cam, goal, *between)
    assert not look_views.LookViews._placed_blocks(cam, goal, *beside)


def test_facts_of_names_the_cells_that_would_block(world):
    goal = look_views.region_goal(world.reg.get_boxel('shadow_a'))
    cam = np.eye(4)
    cam[:3, 3] = [0.45, 0.0, 0.20]
    cfg = _home()
    cert = look_views.Cert(cfg, 'free_up_shadow', 'shadow_a',
                           {'shadow_a': look_views.Reveal(0.0, 0.0, True, [])}, cam)
    world.lv.last_stats = {'placement_facts': 0}
    between = _boxel('free_between', BoxelType.FREE_SPACE, [0.31, -0.05, 0.0],
                     [0.35, 0.05, 0.3], on_surface='table')
    beside = _boxel('free_beside', BoxelType.FREE_SPACE, [0.31, 0.20, 0.0],
                    [0.35, 0.30, 0.3], on_surface='table')
    facts = world.lv._facts_of([cert], [goal], None, world.reg,
                               {(40, 40, 200): ['x1', 'x2']}, [between, beside])
    assert ('blocks_look_at', 'x1', 'free_between', cfg, 'shadow_a') in facts
    assert ('blocks_look_at', 'x2', 'free_between', cfg, 'shadow_a') in facts
    assert not any(f[2] == 'free_beside' for f in facts if f[0] == 'blocks_look_at')
    assert ('reveals', cfg, 'shadow_a') in facts and ('Config', cfg) in facts