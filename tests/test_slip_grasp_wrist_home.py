"""BF#59 grasp_wrist_home: the grasp sampler takes, of a top-down grasp yaw
and its pad-swapped twin (yaw + pi), the one whose wrist (joint 7) is
nearer home (pose_belief.wrist_home_twin, streams.sample_grasp)."""
import math
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pybullet_data
import pytest

import pose_belief
import robot_utils
import slip_fixes
import streams
from boxel_data import BoxelData, BoxelType

HOME_Q7 = 0.785          # REST_POSES and their DEFAULT_ARM_POS
BASE = np.array([0.0, 0.0])
YAWS = [-0.7, -0.3, 0.0, 0.2, 0.4, 0.7]


@pytest.fixture
def switch():
    """The registry as the import left it, ENABLED restored after the test."""
    known, enabled = dict(slip_fixes.KNOWN), slip_fixes.ENABLED
    slip_fixes.configure('')
    yield slip_fixes
    slip_fixes.KNOWN.clear()
    slip_fixes.KNOWN.update(known)
    slip_fixes.ENABLED = enabled


@pytest.fixture
def m9_on():
    saved = dict(pose_belief.SWITCHES)
    pose_belief.SWITCHES['M9'] = True
    yield
    pose_belief.SWITCHES.clear()
    pose_belief.SWITCHES.update(saved)


def die(yaw, center=(0.6, 0.1), ext=(0.0178, 0.0178, 0.0178)):
    """A die-class boxel with a valid fitted yaw at ``center``."""
    c = np.array([center[0], center[1], 0.0089])
    h = 0.5 * np.array(ext)
    b = BoxelData(id='o', boxel_type=BoxelType.OBJECT,
                  min_corner=c - h, max_corner=c + h)
    b.yaw, b.yaw_valid = yaw, True
    b.body_extents = np.array(ext)
    return b


def sampled(boxel, home_q7=HOME_Q7):
    """(grasp yaw, z) of every grasp sample_grasp yields for ``boxel``."""
    reg = SimpleNamespace(get_boxel=lambda i: boxel)
    s = SimpleNamespace(ungraspable_objects=set(), registry=reg, _grasp_counter=0,
                        GRASP_MAX_SPAN=streams.BoxelStreams.GRASP_MAX_SPAN,
                        GRASP_SQUARE_TOL=streams.BoxelStreams.GRASP_SQUARE_TOL,
                        _GRASP_Z_OFFSETS=list(streams.BoxelStreams._GRASP_Z_OFFSETS),
                        _robot_base_xy=BASE,
                        home_config=SimpleNamespace(joint_positions=np.array(
                            robot_utils.REST_POSES[:6] + [home_q7])))
    out = []
    for (g,) in streams.BoxelStreams.sample_grasp(s, 'o'):
        # top_down(yaw) = Rz(yaw) Ry(pi): the hand's y axis (the pads'
        # direction) is (-sin yaw, cos yaw).
        m = np.array(p.getMatrixFromQuaternion(g.orientation)).reshape(3, 3)
        out.append((round(math.atan2(-m[0, 1], m[1, 1]), 6), float(g.position[2])))
    return out


def q7(boxel, yaw):
    return pose_belief.wrist_joint7_top_down(boxel.center[:2], BASE, yaw)


def test_registered_and_off_by_default(switch):
    assert 'grasp_wrist_home' in slip_fixes.KNOWN
    assert not slip_fixes.on('grasp_wrist_home')
    assert slip_fixes.configure('grasp_wrist_home') == {'grasp_wrist_home'}
    assert slip_fixes.on('grasp_wrist_home')


def test_off_the_wrap_gives_todays_yaw(switch, m9_on):
    for yaw in YAWS:
        b = die(yaw)
        want = [gy for gy, _ in pose_belief.fitted_grasp_candidates(
            yaw, b.body_extents, streams.BoxelStreams.GRASP_SQUARE_TOL,
            aabb_ext=b.max_corner - b.min_corner)]
        got = sampled(b)
        assert [y for y, _ in got] == [pytest.approx(w) for w in want for _ in (0.10, 0.06)]
        assert all(-math.pi / 4 - 1e-9 <= y < math.pi / 4 for y, _ in got)


def test_on_the_chosen_twin_is_nearer_home_and_the_count_is_kept(switch, m9_on):
    for yaw in YAWS:
        b = die(yaw)
        off = sampled(b)
        switch.configure('grasp_wrist_home')
        on = sampled(b)
        switch.configure('')
        assert len(on) == len(off)
        assert [z for _, z in on] == [z for _, z in off]
        for (y_on, _), (y_off, _) in zip(on, off):
            # The same pinch: the twin, half a turn away.
            assert abs(pose_belief._wrap(y_on - y_off, math.pi)) < 1e-6
            assert abs(q7(b, y_on) - HOME_Q7) < abs(q7(b, y_off) - HOME_Q7)
            assert abs(q7(b, y_on) - HOME_Q7) < math.radians(90)


def test_on_the_aabb_path_and_a_rectangle(switch, m9_on):
    # AABB path (M9 off): yaw 0 and pi/2 of a rectangle, spans and order kept.
    pose_belief.SWITCHES['M9'] = False
    b = die(0.0, ext=(0.04, 0.02, 0.02))
    off = sampled(b)
    switch.configure('grasp_wrist_home')
    on = sampled(b)
    assert len(on) == len(off) == 4
    for (y_on, _), (y_off, _) in zip(on, off):
        assert abs(pose_belief._wrap(y_on - y_off, math.pi)) < 1e-6
        assert abs(q7(b, y_on) - HOME_Q7) <= abs(q7(b, y_off) - HOME_Q7)
    # The candidate list keeps its spans (the pinch is sign-blind).
    cands = [(0.0, 0.02), (math.pi / 2, 0.04)]
    kept = streams._prefer_wrist_home('o', b, cands, BASE, HOME_Q7)
    assert [s for _, s in kept] == [0.02, 0.04]


def test_a_yaw_already_nearest_home_is_unchanged(switch, m9_on):
    # A home whose wrist sits where today's yaw puts it: nothing turns.
    for yaw in YAWS:
        b = die(yaw)
        today = q7(b, pose_belief._wrap(yaw, math.pi / 2))
        off = sampled(b, home_q7=today)
        switch.configure('grasp_wrist_home')
        assert sampled(b, home_q7=today) == off
        switch.configure('')
    for yaw in YAWS:
        b = die(yaw)
        gy = pose_belief._wrap(yaw, math.pi / 2)
        chosen, info = pose_belief.wrist_home_twin(gy, b.center[:2], BASE, q7(b, gy))
        assert chosen == gy and not info['twin']


def test_the_tie_band_keeps_todays_member_near_the_split():
    # A target at bearing 90 deg: today's yaw 0 has joint 7 at -45 deg, the
    # twin at 135 deg; with home at 45 deg they are 90 deg each, a tie.
    t = (0.0, 0.5)
    chosen, info = pose_belief.wrist_home_twin(0.0, t, BASE, math.radians(45))
    assert info['d'] == pytest.approx(info['twin_d'])
    assert chosen == 0.0 and not info['twin']
    # 4 deg past the split is inside the 5 deg band; 6 deg is not.
    near = pose_belief.wrist_home_twin(0.0, t, BASE, math.radians(45 + 4))[1]
    far = pose_belief.wrist_home_twin(0.0, t, BASE, math.radians(45 + 6))[1]
    assert not near['twin'] and far['twin']


def test_the_formula_matches_the_kin_streams_ik():
    """The joint 7 the formula predicts for the chosen member is the IK's
    within a few degrees (pybullet_data's Panda, our base pose), and the
    chosen member's IK joint 7 is nearer home than the other's."""
    saved = robot_utils.robot_model()
    cid = p.connect(p.DIRECT)
    try:
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=cid)
        base = [-0.4, 0.0, 0.0]
        rid = p.loadURDF('franka_panda/panda.urdf', base, [0, 0, 0, 1],
                         useFixedBase=True, physicsClientId=cid)
        robot_utils.use_robot_model(robot_utils.resolve_robot_model(rid, cid))
        ns = SimpleNamespace(robot_id=rid, physics_client=cid,
                             ik_max_iterations=100, ik_residual_threshold=1e-4)
        seeds = list(streams.BoxelStreams._ik_seeds(streams.BoxelStreams))
        checked = 0
        for x, y in ((0.0, -0.2), (0.2, 0.15), (0.3, 0.0)):
            t = np.array([x, y, 0.445])
            for gy in (-0.6, 0.0, 0.5):
                chosen, info = pose_belief.wrist_home_twin(gy, t[:2], base[:2], HOME_Q7)
                other = info['yaw'] if info['twin'] else info['twin_yaw']
                ik = {}
                for g in (chosen, other):
                    # The kin stream's first certified seed, as it yields.
                    orn = np.array(p.getQuaternionFromEuler([0, math.pi, g]))
                    sols = (streams.BoxelStreams._pybullet_ik(ns, t, orn, seed=s)
                            for s in seeds)
                    c = next((c for c in sols if c is not None), None)
                    ik[g] = None if c is None else float(c.joint_positions[6])
                assert ik[chosen] is not None
                pred = pose_belief.wrist_joint7_top_down(t[:2], base[:2], chosen)
                assert abs(ik[chosen] - pred) < math.radians(15)
                if ik[other] is not None:
                    assert abs(ik[chosen] - HOME_Q7) < abs(ik[other] - HOME_Q7)
                checked += 1
        assert checked == 9
    finally:
        robot_utils.use_robot_model(saved)
        p.disconnect(cid)
