"""BF#59 pose_radius_keep (pose_belief.record_detection): a later complete
detection of a body the belief already bounds keeps min(r_new, r_ref +
centre shift), and the overhead eye's re-fused yaw does not replace a
consistent wrist yaw.  Synthetic detections; the radius formula is stubbed
to the cup loop's numbers (reviews/loss_dynamics.md: the wrist observe's
0.39 mm, the eye refresh's 5.49 mm, a centre shift of 1.66 mm)."""
import math

import numpy as np
import pytest

from sensing import pose_belief
from acting import slip_fixes
from world.boxel_data import BoxelData, BoxelType
from sensing.perception import ObjectDetection

R = {'wrist': 0.00039, 'eye': 0.00549}
CUP_AABB = 0.0696          # the cup's registry box side (pose_belief BF#46)
CUP_TOP = 0.051            # its fitted top-face rectangle
C0 = np.array([0.50, 0.10])
WRIST_YAW = math.radians(5.0)


@pytest.fixture
def belief(monkeypatch):
    """M8 and M9 on, the slip registry's state restored after the test,
    and the A formula stubbed to the camera's radius."""
    saved = dict(pose_belief.SWITCHES)
    pose_belief.SWITCHES.update({'M8': True, 'M9': True})
    known, enabled = dict(slip_fixes.KNOWN), slip_fixes.ENABLED
    slip_fixes.ENABLED = frozenset()                         # every switch off for the test
    monkeypatch.setattr(
        pose_belief, 'pose_radius',
        lambda det, yaw_noise, *a, **k:
            R['wrist'] if yaw_noise == pose_belief.YAW_NOISE['wrist'] else R['eye'])
    yield
    pose_belief.SWITCHES.clear()
    pose_belief.SWITCHES.update(saved)
    slip_fixes.KNOWN.clear()
    slip_fixes.KNOWN.update(known)
    slip_fixes.ENABLED = enabled


def keep_on():
    slip_fixes.configure('pose_radius_keep')


def det(centre, yaw=0.0):
    c = np.asarray(centre, dtype=float)
    h = CUP_AABB / 2.0
    return ObjectDetection(
        name='cup', body_id=1, pixel_count=900,
        est_min=np.array([c[0] - h, c[1] - h, 0.0]),
        est_max=np.array([c[0] + h, c[1] + h, 0.07]),
        yaw=yaw, yaw_valid=True, rect_center=c.copy(),
        body_extents=np.array([CUP_TOP, CUP_TOP, 0.07]),
        pixel_steps=np.array([[0.0005, 0.0], [0.0, 0.0005]]),
        raw_xy_ext=np.array([CUP_AABB, CUP_AABB]))


def cup():
    h = CUP_AABB / 2.0
    return BoxelData(id='cup', boxel_type=BoxelType.OBJECT,
                     min_corner=np.array([C0[0] - h, C0[1] - h, 0.0]),
                     max_corner=np.array([C0[0] + h, C0[1] + h, 0.07]))


def write(b, d, camera, first=False, complete=True):
    """A pose writer: the rule, then the box re-posed at the detection's
    centre (refresh_object_aabbs, handle_observe_action)."""
    pose_belief.record_detection(b, d, camera, complete, first=first)
    b.min_corner, b.max_corner = d.est_min.copy(), d.est_max.copy()


def committed(b):
    """The pick's commit check with the bridge's numbers (half opening
    0.04 m, GRASP_MAX_SPAN 0.076, GRASP_SQUARE_TOL 0.005)."""
    return pose_belief.pose_known(b, 0.04, 0.076, 0.005)


def loop(b, eye_offset_mm=(1.66, 0.0)):
    """The cup loop: the eye registers the cup, the wrist observe re-poses
    it 0.2 mm away at 5 deg, the next move's eye refresh re-poses it."""
    write(b, det(C0), 'eye', first=True)
    c_w = C0 + np.array([0.0002, 0.0])
    write(b, det(c_w, WRIST_YAW), 'wrist')
    assert b.pose_radius == pytest.approx(R['wrist'])
    assert b.yaw == pytest.approx(WRIST_YAW)
    write(b, det(c_w + np.asarray(eye_offset_mm) * 1e-3, 0.0), 'eye')
    return c_w


def test_registered_and_on_by_default():
    assert 'pose_radius_keep' in slip_fixes.KNOWN
    assert 'pose_radius_keep' in slip_fixes.DEFAULT_ON       # BF#62: one of the four
    saved = slip_fixes.ENABLED
    try:
        assert 'pose_radius_keep' in slip_fixes.configure('')
        assert slip_fixes.on('pose_radius_keep')
        assert slip_fixes.configure('none') == frozenset()
        assert not slip_fixes.on('pose_radius_keep')
    finally:
        slip_fixes.ENABLED = saved


def test_off_the_refresh_sets_the_eye_radius_and_yaw(belief, capsys):
    b = cup()
    loop(b)
    assert b.pose_radius == pytest.approx(R['eye'])      # today: latest wins
    assert b.yaw == 0.0                                  # the eye's, deadbanded
    assert not committed(b)                              # the refusal of the loop
    assert 'pose_radius_keep' not in capsys.readouterr().out
    assert not hasattr(b, '_prk_ref')


def test_on_keeps_the_shift_grown_radius_and_the_wrist_yaw(belief, capsys):
    keep_on()
    b = cup()
    loop(b)
    assert b.pose_radius == pytest.approx(0.00039 + 0.00166)     # 2.05 mm
    assert b.yaw == pytest.approx(WRIST_YAW)
    assert committed(b)                                  # under the ~3 mm margin
    out = capsys.readouterr().out
    assert ('pose_radius_keep: cup radius kept 2.05 mm (this eye detection\'s '
            '5.49 mm; the wrist detection\'s 0.39 mm + centre shift 1.66 mm)') in out
    assert 'pose_radius_keep: cup yaw kept 5.00 deg (wrist) over this eye ' \
           'detection\'s 0.00 deg (centre shift 1.66 mm)' in out
    # The box and the rectangle centre are the eye's (the review's rule).
    assert np.allclose(b.rect_center, C0 + [0.0002 + 0.00166, 0.0])


def test_a_moved_body_takes_the_new_radius_and_yaw(belief, capsys):
    keep_on()
    b = cup()
    loop(b, eye_offset_mm=(100.0, 0.0))
    assert b.pose_radius == pytest.approx(R['eye'])
    assert b.yaw == 0.0
    assert 'pose_radius_keep' not in capsys.readouterr().out


def test_a_first_detection_is_unchanged(belief, capsys):
    keep_on()
    b = cup()
    write(b, det(C0), 'eye', first=True)
    assert b.pose_radius == pytest.approx(R['eye'])
    c = cup()
    write(c, det(C0, WRIST_YAW), 'wrist', first=True)
    assert c.pose_radius == pytest.approx(R['wrist'])
    assert c.yaw == pytest.approx(WRIST_YAW)
    assert 'pose_radius_keep' not in capsys.readouterr().out


def test_repeated_refreshes_do_not_add_their_shifts(belief):
    """The reference stays the wrist's disc: a second eye refresh 0.3 mm
    across the first is bounded by 0.39 mm + its distance to the wrist's
    centre, not by 2.05 mm + 0.3 mm."""
    keep_on()
    b = cup()
    c_w = loop(b)
    write(b, det(c_w + np.array([0.00166, 0.0003]), 0.0), 'eye')
    assert b.pose_radius == pytest.approx(0.00039 + math.hypot(0.00166, 0.0003))
    assert b.yaw == pytest.approx(WRIST_YAW)


def test_another_radius_writer_invalidates_the_reference(belief):
    keep_on()
    b = cup()
    write(b, det(C0), 'eye', first=True)
    c_w = C0 + np.array([0.0002, 0.0])
    write(b, det(c_w, WRIST_YAW), 'wrist')
    pose_belief.mark_pose_commanded(b)                   # a commanded place
    write(b, det(c_w + np.array([0.00166, 0.0]), 0.0), 'eye')
    assert b.pose_radius == pytest.approx(R['eye'])
    assert b.yaw == 0.0
    pose_belief.mark_pose_unknown(b)                     # a disturbance
    write(b, det(c_w + np.array([0.00166, 0.0]), 0.0), 'eye')
    assert b.pose_radius == pytest.approx(R['eye'])


def test_a_box_moved_without_the_rule_invalidates_the_reference(belief):
    """A partial detection leaves the radius but its writer still re-poses
    the box (refresh_object_aabbs); the post-place writer moves the box
    before the rule runs.  Either way the earlier disc no longer bounds
    the body, so the next detection takes its own radius."""
    keep_on()
    b = cup()
    write(b, det(C0), 'eye', first=True)
    c_w = C0 + np.array([0.0002, 0.0])
    write(b, det(c_w, WRIST_YAW), 'wrist')
    write(b, det(c_w + np.array([0.002, 0.0])), 'eye', complete=False)
    assert b.pose_radius == pytest.approx(R['wrist'])    # partial: unchanged
    write(b, det(c_w + np.array([0.00166, 0.0]), 0.0), 'eye')
    assert b.pose_radius == pytest.approx(R['eye'])
    assert b.yaw == 0.0


def test_an_eye_yaw_outside_the_noise_is_taken(belief):
    """The eye sees the cup 30 deg off the wrist's yaw: not consistent
    within the two cameras' noise, so yaw = latest as today (the radius
    rule still applies, it bounds the centre only)."""
    keep_on()
    b = cup()
    write(b, det(C0), 'eye', first=True)
    c_w = C0 + np.array([0.0002, 0.0])
    write(b, det(c_w, WRIST_YAW), 'wrist')
    write(b, det(c_w + np.array([0.00166, 0.0]), math.radians(35.0)), 'eye')
    assert b.yaw == pytest.approx(math.radians(35.0))
    assert b.pose_radius == pytest.approx(0.00205)


def test_a_wrist_detection_after_the_eye_is_latest(belief):
    """The keep is for the coarser camera only: a wrist yaw replaces an
    eye yaw, and its smaller radius wins the min."""
    keep_on()
    b = cup()
    write(b, det(C0, 0.0), 'eye', first=True)
    write(b, det(C0 + np.array([0.0002, 0.0]), WRIST_YAW), 'wrist')
    assert b.yaw == pytest.approx(WRIST_YAW)
    assert b.pose_radius == pytest.approx(R['wrist'])
