"""Path 9: the geometry of the arm-camera-only mode (arm_eye.py).

No episode, no planner: a camera pose, the image's frame test, and the part of
the table the first image does not show as hidden regions: the fine cells out
of the frame merged into few boxes, minus the first scan's boxes (PLAN 11.16,
the first image's own cut).  The wired case, on a scene of ours, is in
tests/test_eye_switch.py.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pybullet as p
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import arm_eye  # noqa: E402
import observe_views  # noqa: E402
import robot_utils  # noqa: E402
from boxel_data import BoxelData, BoxelType  # noqa: E402
from test_look_views import world  # noqa: E402,F401

W, H = robot_utils.WRIST_CAMERA_WIDTH, robot_utils.WRIST_CAMERA_HEIGHT

# The arm camera at TAMPURA's home joints on our tabletop, as measured on
# 2026-11-12 (tracks/look/evidence/arm_camera_home_pose_20261112.txt): 0.263 m
# over the table top (z 0.325), 38.5 degrees from straight down toward +x.
POSE_A = np.array([[-0.04948, -0.7819, 0.62144, -0.22139],
                   [-0.99864, 0.02845, -0.04372, 0.0488],
                   [0.0165, -0.62276, -0.78224, 0.58832],
                   [0.0, 0.0, 0.0, 1.0]])
TABLE_Z = 0.325
WORKSPACE = ((-0.1, 0.70), (-0.40, 0.40))    # boxel_env's safe placement window


def _down(x, y, z):
    """A camera at (x, y, z) looking straight down: image right is world +x,
    image down is world -y."""
    pose = np.eye(4)
    pose[:3, 0] = (1.0, 0.0, 0.0)
    pose[:3, 1] = (0.0, -1.0, 0.0)
    pose[:3, 2] = (0.0, 0.0, -1.0)
    pose[:3, 3] = (x, y, z)
    return pose


def _pixels_from_matrices(pose, pts):
    view, proj = robot_utils.wrist_camera_matrices(pose)
    v = np.array(view, dtype=float).reshape(4, 4).T
    q = np.array(proj, dtype=float).reshape(4, 4).T
    clip = (q @ v @ np.c_[pts, np.ones(len(pts))].T).T
    ndc = clip[:, :3] / clip[:, 3:4]
    return np.stack([(ndc[:, 0] + 1.0) / 2.0 * W, (1.0 - ndc[:, 1]) / 2.0 * H], axis=1)


@pytest.mark.parametrize('pose', [POSE_A, _down(0.1, -0.05, 0.9)])
def test_project_is_the_renderers_projection(world, pose):
    """arm_eye.project gives the pixel the wrist render's own matrices give."""
    rot = pose[:3, :3]
    assert np.allclose(rot.T @ rot, np.eye(3), atol=1e-3)     # the measured pose is rounded
    rng = np.random.RandomState(0)
    cam_pts = np.c_[rng.uniform(-0.2, 0.2, 40), rng.uniform(-0.15, 0.15, 40),
                    rng.uniform(0.2, 0.9, 40)]
    pts = cam_pts @ rot.T + pose[:3, 3]
    mine, depth = arm_eye.project(pose, pts)
    theirs = _pixels_from_matrices(pose, pts)
    assert np.all(depth > 0.0)
    assert np.allclose(mine, theirs, atol=0.6), np.abs(mine - theirs).max()


def test_start_camera_is_the_arm_cameras_pose(world):
    for j, q in zip(robot_utils.robot_model().arm_joints, robot_utils.REST_POSES):
        p.resetJointState(world.robot, j, q, physicsClientId=world.cid)
    cam = arm_eye.start_camera(world.robot, world.cid)
    pose = robot_utils.wrist_camera_pose(world.robot, world.cid)
    assert np.allclose(cam['camera_pose'], pose)
    assert np.allclose(cam['camera_position'], pose[:3, 3])
    assert np.allclose(np.asarray(cam['camera_target']) - cam['camera_position'], pose[:3, 2])
    assert np.allclose(cam['camera_up'], -pose[:3, 1])
    assert (cam['image_width'], cam['image_height']) == (W, H)
    assert cam['fov'] == robot_utils.WRIST_CAMERA_FOV_DEG
    assert (cam['near_plane'], cam['far_plane']) == (robot_utils.WRIST_CAMERA_NEAR,
                                                      robot_utils.WRIST_CAMERA_FAR)
    # The view and projection the env would build from these attributes are
    # the wrist render's own.
    view = p.computeViewMatrix(cameraEyePosition=list(cam['camera_position']),
                               cameraTargetPosition=list(cam['camera_target']),
                               cameraUpVector=list(cam['camera_up']))
    proj = p.computeProjectionMatrixFOV(fov=cam['fov'], aspect=W / H,
                                        nearVal=cam['near_plane'], farVal=cam['far_plane'])
    wview, wproj = robot_utils.wrist_camera_matrices(pose)
    assert np.allclose(view, wview, atol=1e-6) and np.allclose(proj, wproj, atol=1e-6)
    _cam, _buf, _depth, _seg, rview, rproj = observe_views.wrist_render(world.cid, world.robot)
    assert np.allclose(view, rview, atol=1e-6) and np.allclose(proj, rproj, atol=1e-6)


def test_straight_down_the_frame_is_the_rectangle_under_the_camera():
    """From height d over a box's top the image holds half-widths
    (W / 2 - margin) d / f by (H / 2 - margin) d / f."""
    cam_z, top = TABLE_Z + 0.50, TABLE_Z + 0.05
    pose = _down(0.2, 0.1, cam_z)
    f = (H / 2.0) / math.tan(math.radians(robot_utils.WRIST_CAMERA_FOV_DEG) / 2.0)
    d = cam_z - top
    hx = (W / 2.0 - arm_eye.FRAME_MARGIN_PX) * d / f
    hy = (H / 2.0 - arm_eye.FRAME_MARGIN_PX) * d / f
    inside = ([0.2 - hx + 1e-4, 0.1 - hy + 1e-4, TABLE_Z], [0.2 + hx - 1e-4, 0.1 + hy - 1e-4, top])
    assert arm_eye.box_in_frame(pose, *inside)
    for axis, half in ((0, hx), (1, hy)):
        lo, hi = np.array(inside[0]), np.array(inside[1])
        hi[axis] = (0.2, 0.1)[axis] + half + 2e-3          # 2 mm past the frame
        assert not arm_eye.box_in_frame(pose, lo, hi)
    # A box behind the camera is never in the frame.
    assert not arm_eye.box_in_frame(pose, [0.15, 0.05, cam_z + 0.1], [0.25, 0.15, cam_z + 0.2])


# ----- the part of the table the first image does not show ---------------------------

HEIGHT = 0.05            # the regions' height over the table in these cases
EPS = 1e-9
F = (H / 2.0) / math.tan(math.radians(robot_utils.WRIST_CAMERA_FOV_DEG) / 2.0)
# Straight down over the window's middle, 0.525 m over the box tops: there the
# frame holds x -0.012 to 0.612 and y -0.232 to 0.232, so the fine cells of
# x 0 to 0.6, y -0.2 to 0.2 are seen.
DOWN = _down(0.3, 0.0, TABLE_Z + HEIGHT + 0.525)
# The four strips around that rectangle as (x0, y0, x1, y1), first row first.
STRIPS = [(-0.1, -0.4, 0.0, 0.4), (0.0, -0.4, 0.6, -0.2),
          (0.0, 0.2, 0.6, 0.4), (0.6, -0.4, 0.7, 0.4)]
# Case 3's known boxes: an object box taller than the regions, from the image
# into the far strip, and a shadow fragment lower than the regions, from the
# image into a side strip.
OBJ = ((0.50, -0.05, TABLE_Z), (0.65, 0.05, TABLE_Z + 0.10))
SHADOW = ((0.20, 0.15, TABLE_Z), (0.40, 0.30, TABLE_Z + 0.03))


def _known(kind, lo, hi):
    return BoxelData(boxel_type=kind, min_corner=np.array(lo, dtype=float),
                     max_corner=np.array(hi, dtype=float))


def _cells(pose, height=HEIGHT):
    """The window's fine cells told apart by box_in_frame alone, as
    (x0, y0, x1, y1, seen): the reference the regions are checked against."""
    side = arm_eye.UNSEEN_FINE_SIDE_M
    return [(x0, y0, x1, y1,
             arm_eye.box_in_frame(pose, (x0, y0, TABLE_Z), (x1, y1, TABLE_Z + height)))
            for x0, x1 in arm_eye._tiles(WORKSPACE[0][0], WORKSPACE[0][1], side)
            for y0, y1 in arm_eye._tiles(WORKSPACE[1][0], WORKSPACE[1][1], side)]


def _overlap(a, b):
    """True when the boxes a and b, each (lo, hi), share a volume; touching
    faces do not."""
    return bool(np.all(np.minimum(a[1], b[1]) - np.maximum(a[0], b[0]) > EPS))


def _in_any(pts, boxes, dims=3):
    """For each point, whether it lies strictly inside one of the boxes, each
    (lo, hi), on the first ``dims`` coordinates."""
    if len(boxes) == 0:
        return np.zeros(len(pts), dtype=bool)
    lo = np.array([b[0][:dims] for b in boxes], dtype=float)
    hi = np.array([b[1][:dims] for b in boxes], dtype=float)
    q = pts[:, None, :dims]
    return np.any(np.all((q > lo[None]) & (q < hi[None]), axis=2), axis=1)


def _xy(boxes):
    return np.array([[lo[0], lo[1], hi[0], hi[1]] for lo, hi in boxes], dtype=float)


def _assert_exact(boxes, cells, height=HEIGHT):
    """The boxes are the unseen fine cells' union exactly: each unseen cell
    lies in one box and no seen cell's centre in any, no two boxes share a
    volume, and their area is the unseen cells' area."""
    for lo, hi in boxes:
        assert lo[2] == pytest.approx(TABLE_Z) and hi[2] == pytest.approx(TABLE_Z + height)
    for x0, y0, x1, y1, seen in cells:
        if seen:
            centre = np.array([[(x0 + x1) / 2.0, (y0 + y1) / 2.0]])
            assert not _in_any(centre, boxes, dims=2)[0], (x0, y0)
        else:
            holders = [1 for lo, hi in boxes
                       if lo[0] - EPS <= x0 and x1 <= hi[0] + EPS
                       and lo[1] - EPS <= y0 and y1 <= hi[1] + EPS]
            assert len(holders) == 1, (x0, y0)
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert not _overlap(a, b)
    area = sum((hi[0] - lo[0]) * (hi[1] - lo[1]) for lo, hi in boxes)
    assert area == pytest.approx(sum((x1 - x0) * (y1 - y0)
                                     for x0, y0, x1, y1, seen in cells if not seen))


def test_the_fine_cells_tile_the_window_and_the_frame_splits_them():
    """The window in equal cells of at most UNSEEN_FINE_SIDE_M, x outer, y
    inner, unseen exactly where box_in_frame refuses the cell's whole box.
    TAMPURA's home view covers the table's middle in front of the robot
    (measured footprint x -0.16 to 0.30, at most 0.34 to either side): the
    seen cells lie there, and the cells from x 0.5 on are unseen."""
    xs, ys, unseen = arm_eye.unseen_fine_cells(POSE_A, WORKSPACE[0], WORKSPACE[1],
                                               TABLE_Z, HEIGHT)
    assert len(xs) == len(ys) == 16 and [len(row) for row in unseen] == [16] * 16
    for tiles, (lo, hi) in ((xs, WORKSPACE[0]), (ys, WORKSPACE[1])):
        assert tiles[0][0] == lo and tiles[-1][1] == pytest.approx(hi)
        assert all(a[1] == b[0] for a, b in zip(tiles, tiles[1:]))     # no gap, no overlap
        assert all(t1 - t0 <= arm_eye.UNSEEN_FINE_SIDE_M + EPS for t0, t1 in tiles)
    seen = []
    for i, (x0, x1) in enumerate(xs):
        for j, (y0, y1) in enumerate(ys):
            inside = arm_eye.box_in_frame(POSE_A, (x0, y0, TABLE_Z), (x1, y1, TABLE_Z + HEIGHT))
            assert unseen[i][j] == (not inside)
            if inside:
                seen.append((x0, y0, x1, y1))
    assert seen
    for x0, y0, x1, y1 in seen:
        assert x1 <= 0.30 + EPS and max(abs(y0), abs(y1)) <= 0.34
    assert all(unseen[i][j] for i, (x0, _) in enumerate(xs) if x0 >= 0.5 - EPS
               for j in range(len(ys)))


def test_a_taller_target_leaves_fewer_seen_cells():
    """The whole box up to the target's height must be in the image, so a
    taller target can only turn seen cells into unseen ones."""
    _, _, low = arm_eye.unseen_fine_cells(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, 0.02)
    _, _, tall = arm_eye.unseen_fine_cells(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, 0.15)
    seen = lambda m: {(i, j) for i, row in enumerate(m) for j, u in enumerate(row) if not u}
    assert seen(low)
    assert seen(tall) <= seen(low)


def test_straight_down_the_unseen_part_is_four_strips_around_the_image():
    """Case 1: rows run along y and stack along x, so the part out of the
    frame is two full strips at the window's x ends and two strips between
    them, before and after the image."""
    d = 0.525
    assert (W / 2.0 - arm_eye.FRAME_MARGIN_PX) * d / F == pytest.approx(0.312, abs=1e-3)
    assert (H / 2.0 - arm_eye.FRAME_MARGIN_PX) * d / F == pytest.approx(0.232, abs=1e-3)
    boxes = arm_eye.unseen_regions(DOWN, WORKSPACE[0], WORKSPACE[1], TABLE_Z, HEIGHT)
    assert len(boxes) == 4
    assert np.allclose(_xy(boxes), STRIPS, atol=EPS)
    _assert_exact(boxes, _cells(DOWN))
    area = sum((hi[0] - lo[0]) * (hi[1] - lo[1]) for lo, hi in boxes)
    assert area == pytest.approx(0.8 * 0.8 - 0.6 * 0.4)


def test_at_the_home_view_the_regions_are_the_unseen_cells_exactly_and_replay():
    """Case 2: TAMPURA's home view, tilted 38.5 degrees: the same exactness,
    fewer boxes than unseen cells, a fixed order, the same list twice."""
    cells = _cells(POSE_A)
    n_unseen = sum(1 for *_, seen in cells if not seen)
    assert 0 < n_unseen < len(cells)
    boxes = arm_eye.unseen_regions(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, HEIGHT)
    _assert_exact(boxes, cells)
    assert len(boxes) < n_unseen
    keys = [(round(float(lo[0]), 9), round(float(lo[1]), 9)) for lo, _ in boxes]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)     # first row, then first y tile
    again = arm_eye.unseen_regions(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, HEIGHT)
    assert len(again) == len(boxes)
    assert all(np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
               for a, b in zip(boxes, again))


def test_known_boxes_out_of_the_frame_take_their_part_of_the_unseen_regions():
    """Case 3, traced: the side strip loses the shadow fragment's volume and
    leaves four pieces (beside it in x, behind it in y, over it), the far
    strip loses the object box's and leaves three.  No region shares a volume
    with a known box or another region, and a point lies in a region exactly
    when its fine cell is unseen and no known box holds it."""
    known = [_known(BoxelType.OBJECT, *OBJ), _known(BoxelType.SHADOW, *SHADOW)]
    boxes = arm_eye.unseen_regions(DOWN, WORKSPACE[0], WORKSPACE[1], TABLE_Z, HEIGHT,
                                   known=known)
    t, z = TABLE_Z, TABLE_Z + HEIGHT
    want = [(-0.1, -0.4, t, 0.0, 0.4, z), (0.0, -0.4, t, 0.6, -0.2, z),
            (0.0, 0.2, t, 0.2, 0.4, z), (0.4, 0.2, t, 0.6, 0.4, z),
            (0.2, 0.3, t, 0.4, 0.4, z), (0.2, 0.2, t + 0.03, 0.4, 0.3, z),
            (0.65, -0.4, t, 0.7, 0.4, z), (0.6, -0.4, t, 0.65, -0.05, z),
            (0.6, 0.05, t, 0.65, 0.4, z)]
    got = np.array([np.r_[lo, hi] for lo, hi in boxes])
    assert got.shape == (9, 6) and np.allclose(got, want, atol=EPS)
    claimed = [(k.min_corner, k.max_corner) for k in known]
    for i, a in enumerate(boxes):
        assert not any(_overlap(a, c) for c in claimed)
        assert not any(_overlap(a, b) for b in boxes[i + 1:])
    rng = np.random.RandomState(0)
    n = 20000
    pts = np.c_[rng.uniform(WORKSPACE[0][0], WORKSPACE[0][1], n),
                rng.uniform(WORKSPACE[1][0], WORKSPACE[1][1], n),
                rng.uniform(TABLE_Z, TABLE_Z + HEIGHT, n)]
    unseen_cells = [((x0, y0), (x1, y1)) for x0, y0, x1, y1, seen in _cells(DOWN) if not seen]
    expected = _in_any(pts, unseen_cells, dims=2) & ~_in_any(pts, claimed)
    assert np.array_equal(_in_any(pts, boxes), expected)


def test_the_unseen_boxels_are_the_regions_with_fixed_names_and_no_parent():
    known = [_known(BoxelType.OBJECT, *OBJ), _known(BoxelType.SHADOW, *SHADOW)]
    regions = arm_eye.unseen_regions(DOWN, WORKSPACE[0], WORKSPACE[1], TABLE_Z, HEIGHT,
                                     known=known)
    boxels = arm_eye.unseen_boxels(DOWN, WORKSPACE[0], WORKSPACE[1], TABLE_Z, HEIGHT,
                                   known=known)
    assert len(boxels) == len(regions) == 9
    assert [b.id for b in boxels] == [f"unseen_{i:03d}" for i in range(9)]
    for b, (lo, hi) in zip(boxels, regions):
        assert np.array_equal(b.min_corner, lo) and np.array_equal(b.max_corner, hi)
        assert b.boxel_type == BoxelType.SHADOW
        assert b.created_by_object is None and b.created_by_boxel_id is None
        assert b.on_surface == 'table' and b.surface_z == TABLE_Z


def test_a_camera_that_holds_the_whole_window_leaves_no_unseen_region():
    """Case 4: from 1.2 m over the box tops the frame holds 0.71 by 0.53 m to
    either side of the window's middle; the window reaches 0.4 by 0.4."""
    d = 1.2
    pose = _down(0.3, 0.0, TABLE_Z + HEIGHT + d)
    assert (W / 2.0 - arm_eye.FRAME_MARGIN_PX) * d / F > 0.4
    assert (H / 2.0 - arm_eye.FRAME_MARGIN_PX) * d / F > 0.4
    assert all(seen for *_, seen in _cells(pose))
    known = [_known(BoxelType.OBJECT, *OBJ)]
    assert arm_eye.unseen_regions(pose, WORKSPACE[0], WORKSPACE[1], TABLE_Z, HEIGHT,
                                  known=known) == []
    assert arm_eye.unseen_boxels(pose, WORKSPACE[0], WORKSPACE[1], TABLE_Z, HEIGHT) == []


def test_a_remainder_under_a_millimetre_is_dropped():
    """Case 5: box_minus keeps a 1.1 mm remainder and drops a 0.9 mm one; a
    box that only touches the other's face stays whole.  In the whole cut an
    object box that leaves 0.5 mm of the near strip leaves only the strip's
    far 20 mm."""
    lo, hi = (0.0, 0.0, 0.0), (0.1, 0.1, 0.1)
    assert arm_eye.box_minus(lo, hi, (0.0009, -1.0, -1.0), (1.0, 1.0, 1.0)) == []
    kept = arm_eye.box_minus(lo, hi, (0.0011, -1.0, -1.0), (1.0, 1.0, 1.0))
    assert len(kept) == 1
    assert np.allclose(kept[0][0], lo) and np.allclose(kept[0][1], (0.0011, 0.1, 0.1))
    whole = arm_eye.box_minus(lo, hi, (0.1, 0.0, 0.0), (0.2, 0.1, 0.1))
    assert len(whole) == 1
    assert np.array_equal(whole[0][0], lo) and np.array_equal(whole[0][1], hi)
    obj = _known(BoxelType.OBJECT, (-0.0995, -0.5, TABLE_Z), (-0.02, 0.5, TABLE_Z + 0.10))
    boxes = arm_eye.unseen_regions(DOWN, WORKSPACE[0], WORKSPACE[1], TABLE_Z, HEIGHT,
                                   known=[obj])
    assert len(boxes) == 4
    assert np.allclose(_xy(boxes), [(-0.02, -0.4, 0.0, 0.4)] + STRIPS[1:], atol=EPS)


def test_a_known_box_inside_a_region_leaves_five_pieces_in_a_fixed_order():
    """Case 8: a shadow fragment wholly inside the far strip and lower than
    the regions.  The strip becomes the pieces beside it in x, beside it in y
    and over it, in that order, named after the strips before it.  A known
    box in the seen part that meets a strip at its face takes nothing."""
    t, z = TABLE_Z, TABLE_Z + HEIGHT
    inner = _known(BoxelType.SHADOW, (0.63, -0.02, t), (0.67, 0.02, t + 0.03))
    boxels = arm_eye.unseen_boxels(DOWN, WORKSPACE[0], WORKSPACE[1], TABLE_Z, HEIGHT,
                                   known=[inner])
    want = [(-0.1, -0.4, t, 0.0, 0.4, z), (0.0, -0.4, t, 0.6, -0.2, z),
            (0.0, 0.2, t, 0.6, 0.4, z),
            (0.6, -0.4, t, 0.63, 0.4, z), (0.67, -0.4, t, 0.7, 0.4, z),
            (0.63, -0.4, t, 0.67, -0.02, z), (0.63, 0.02, t, 0.67, 0.4, z),
            (0.63, -0.02, t + 0.03, 0.67, 0.02, z)]
    got = np.array([np.r_[b.min_corner, b.max_corner] for b in boxels])
    assert got.shape == (8, 6) and np.allclose(got, want, atol=EPS)
    assert [b.id for b in boxels] == [f"unseen_{i:03d}" for i in range(8)]
    vol = sum(float(np.prod(b.max_corner - b.min_corner)) for b in boxels[3:])
    assert vol == pytest.approx(0.1 * 0.8 * HEIGHT - 0.04 * 0.04 * 0.03)
    beside = _known(BoxelType.OBJECT, (0.55, -0.1, t), (0.6, 0.1, t + 0.10))
    boxes = arm_eye.unseen_regions(DOWN, WORKSPACE[0], WORKSPACE[1], TABLE_Z, HEIGHT,
                                   known=[beside])
    assert len(boxes) == 4
    assert np.allclose(_xy(boxes), STRIPS, atol=EPS)
