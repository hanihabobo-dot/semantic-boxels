"""PLAN_P4_POSE_GRASP_SAMPLERS.md step 5: M8's generated domain, the look
configurations and the wrist observe, on a DIRECT world with our Panda
and one box (the robot model is pybullet_data's, our default)."""
import math
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pybullet_data
import pytest

from planning import m8_domain
from sensing import observe_views
from sensing import pose_belief
from world.boxel_data import BoxelData, BoxelRegistry, BoxelType

HALF = (0.0088, 0.0088, 0.0089)          # a die-class box
BOX_XY = (0.15, 0.05)


# ----- the domain ---------------------------------------------------------

def test_generated_domain_is_the_live_file_plus_the_delta():
    live = m8_domain.read(m8_domain.LIVE_FILE)
    gen = m8_domain.generate(live)
    assert m8_domain.domain_file(False) == m8_domain.LIVE_FILE
    assert m8_domain.read(m8_domain.domain_file(True)) == gen
    assert '(:action observe' in gen and '(:action observe' not in live
    assert ':parameters (?o ?region ?q)' in gen
    # pick needs the pose; place, place_hiding and stack give it.
    pick = gen.split('(:action pick')[1].split('(:action')[0]
    assert '(obj_pose_known ?o)' in pick.split(':effect')[0]
    for act in ('place', 'place_hiding', 'stack'):
        body = gen.split(f'(:action {act}\n')[1].split('(:action')[0]
        assert '(obj_pose_known ?o)' in body.split(':effect')[1]


def test_a_drifted_live_file_is_refused():
    live = m8_domain.read(m8_domain.LIVE_FILE)
    with pytest.raises(ValueError):
        m8_domain.generate(live.replace('(obj_at_boxel_KIF ?o ?o)', ''))


# ----- the world ----------------------------------------------------------

@pytest.fixture
def world():
    cid = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=cid)
    plane = p.loadURDF('plane.urdf', physicsClientId=cid)
    robot = p.loadURDF('franka_panda/panda.urdf', [-0.4, 0.0, 0.0],
                       useFixedBase=True, physicsClientId=cid)
    for fj in (9, 10):
        p.resetJointState(robot, fj, 0.04, physicsClientId=cid)
    box = p.createMultiBody(
        0.005, p.createCollisionShape(p.GEOM_BOX, halfExtents=HALF, physicsClientId=cid),
        p.createVisualShape(p.GEOM_BOX, halfExtents=HALF, physicsClientId=cid),
        basePosition=[BOX_XY[0], BOX_XY[1], HALF[2]], physicsClientId=cid)
    objs = {n: SimpleNamespace(object_id=b) for n, b in
            (('plane', plane), ('robot', robot), ('die', box))}
    env = SimpleNamespace(client_id=cid, plan_client_id=cid, plan_robot_id=robot,
                          objects=objs, _gui_to_plan={b: b for b in (plane, robot, box)},
                          table_surface_height=0.0)
    saved = dict(pose_belief.SWITCHES)
    pose_belief.SWITCHES.update({k: True for k in saved})
    yield SimpleNamespace(cid=cid, robot=robot, box=box, env=env)
    pose_belief.SWITCHES.clear()
    pose_belief.SWITCHES.update(saved)
    p.disconnect(cid)


def _die_boxel(dx=0.0):
    lo = np.array([BOX_XY[0] - HALF[0] + dx, BOX_XY[1] - HALF[1], 0.0])
    return BoxelData(id='die', boxel_type=BoxelType.OBJECT, min_corner=lo,
                     max_corner=lo + 2 * np.array(HALF))


def _known(bd):
    return pose_belief.pose_known(bd, 0.04, 0.076, 0.005)


def test_look_configs_pass_and_a_removed_pair_stays_removed(world):
    views = observe_views.ObserveViews(world.env, (-0.4, 0.0))
    views.last_stats = {'twin_render_s': 0.0, 'twin_renders': 0, 'look_ik': 0}
    bd = _die_boxel()
    looks = views.look_configs(bd)
    ks = [k for k, _ in looks]
    assert ks, 'no look configuration passes over a lone box'
    assert all(q.name == observe_views.look_name('die', k) for k, q in looks)
    assert observe_views.look_index(looks[0][1].name, 'die') == ks[0]
    views.removed.add(('die', ks[0]))
    assert [k for k, _ in views.look_configs(bd)] == ks[1:]


def test_wrist_observe_reposes_the_target_and_leaves_regions(world):
    from acting import execution
    views = observe_views.ObserveViews(world.env, (-0.4, 0.0))
    views.last_stats = {'twin_render_s': 0.0, 'twin_renders': 0, 'look_ik': 0}
    reg = BoxelRegistry()
    bd = _die_boxel(dx=0.003)                 # the belief is 3 mm off
    reg.add_boxel(bd)
    shadow = BoxelData(id='shadow_of_x', boxel_type=BoxelType.SHADOW,
                       min_corner=np.array([0.3, 0.2, 0.0]),
                       max_corner=np.array([0.4, 0.3, 0.05]))
    free = BoxelData(id='', boxel_type=BoxelType.FREE_SPACE,
                     min_corner=np.array([0.3, -0.3, 0.0]),
                     max_corner=np.array([0.4, -0.2, 0.05]))
    reg.add_boxel(shadow)
    reg.add_boxel(free)
    before = {b.id: (b.min_corner.copy(), b.max_corner.copy())
              for b in (shadow, free)}
    k, q = views.look_configs(bd)[0]
    views._set_arm(q.joint_positions)
    status, lost = execution.handle_observe_action(
        env=world.env, registry=reg, viz=None, obj='die', robot_id=world.robot,
        pose_known=_known)
    assert (status, lost) == ('observe_ok', False)
    centre = (bd.min_corner + bd.max_corner) / 2.0
    assert np.linalg.norm(centre[:2] - np.array(BOX_XY)) < 0.0015
    assert math.isfinite(bd.pose_radius) and _known(bd)
    assert bd.complete_detections == 1
    for b in (shadow, free):
        assert np.array_equal(b.min_corner, before[b.id][0])
        assert np.array_equal(b.max_corner, before[b.id][1])
    assert len(reg.boxels) == 3                # nothing new registered


def test_observe_that_does_not_see_the_target_goes_to_the_lost_path(world):
    from acting import execution
    views = observe_views.ObserveViews(world.env, (-0.4, 0.0))
    views.last_stats = {'twin_render_s': 0.0, 'twin_renders': 0, 'look_ik': 0}
    reg = BoxelRegistry()
    bd = _die_boxel()
    reg.add_boxel(bd)
    k, q = views.look_configs(bd)[0]
    # The die was knocked away after the belief was formed.
    p.resetBasePositionAndOrientation(world.box, [0.6, -0.4, HALF[2]], [0, 0, 0, 1],
                                      physicsClientId=world.cid)
    views._set_arm(q.joint_positions)
    status, lost = execution.handle_observe_action(
        env=world.env, registry=reg, viz=None, obj='die', robot_id=world.robot,
        pose_known=_known)
    assert (status, lost) == ('observe_incomplete', True)


def test_pose_known_uses_the_believed_margin(world):
    bd = _die_boxel()
    assert not _known(bd)                       # inf: unknown
    bd.pose_radius = 0.0039
    assert _known(bd)                           # margin 0.5 * 8.8 mm = 4.4 mm
    bd.pose_radius = 0.0045
    assert not _known(bd)
