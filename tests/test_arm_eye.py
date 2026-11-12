"""Path 9 (b), provisional: the geometry of the arm-camera-only mode (arm_eye.py).

No episode, no planner: a camera pose, the image's frame test and the split of
the table into cells the first image shows and cells it does not.
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
from boxel_data import BoxelType  # noqa: E402
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


FINE = 0.10     # a finer tiling than one look needs, so that the image holds whole cells


def test_the_cells_tile_the_workspace_and_none_is_larger_than_asked():
    unseen, seen = arm_eye.unseen_cells(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, 0.05,
                                        max_side=FINE)
    cells = unseen + seen
    assert len(cells) == 64 and len(seen) >= 1 and len(unseen) >= 1
    area = sum((hi[0] - lo[0]) * (hi[1] - lo[1]) for lo, hi in cells)
    assert area == pytest.approx(0.8 * 0.8)
    for lo, hi in cells:
        assert hi[0] - lo[0] <= FINE + 1e-9 and hi[1] - lo[1] <= FINE + 1e-9
        assert lo[2] == TABLE_Z and hi[2] == pytest.approx(TABLE_Z + 0.05)
    keys = {(round(lo[0], 6), round(lo[1], 6)) for lo, _ in cells}
    assert len(keys) == 64                                    # no cell twice
    for lo, hi in seen:
        assert arm_eye.box_in_frame(POSE_A, lo, hi)
    for lo, hi in unseen:
        assert not arm_eye.box_in_frame(POSE_A, lo, hi)
    again = arm_eye.unseen_cells(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, 0.05,
                                 max_side=FINE)
    assert all(np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
               for a, b in zip(unseen + seen, again[0] + again[1]))


def test_at_the_look_cells_size_the_home_view_holds_no_whole_cell():
    """A finding for the design, kept as a test (2026-11-12): with cells of
    UNSEEN_MAX_SIDE_M anchored at the workspace corner, TAMPURA's home view
    cuts every cell it touches, so all 16 count as unseen although the image
    shows the table's middle.  Before this is wired, seen and unseen have to
    be told apart on a finer tiling than the cells a look is planned for."""
    unseen, seen = arm_eye.unseen_cells(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, 0.05)
    assert len(unseen) == 16 and seen == []
    for lo, hi in unseen:
        assert hi[0] - lo[0] <= arm_eye.UNSEEN_MAX_SIDE_M + 1e-9
        assert hi[1] - lo[1] <= arm_eye.UNSEEN_MAX_SIDE_M + 1e-9


def test_the_seen_cells_are_in_front_of_the_arm_and_the_far_ones_are_unseen():
    """TAMPURA's home view covers the table's middle in front of the robot
    (measured footprint x -0.16 to 0.30, at most 0.34 to either side); a cell
    0.9 m out is not in it."""
    unseen, seen = arm_eye.unseen_cells(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, 0.05,
                                        max_side=FINE)
    for lo, hi in seen:
        assert hi[0] <= 0.30 + 1e-9 and max(abs(lo[1]), abs(hi[1])) <= 0.34
    assert any(lo[0] >= 0.5 - 1e-9 for lo, _ in unseen)


def test_a_taller_target_leaves_fewer_seen_cells():
    """The whole box up to the target's height must be in the image, so a
    taller target can only turn seen cells into unseen ones."""
    low = arm_eye.unseen_cells(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, 0.02, max_side=FINE)
    tall = arm_eye.unseen_cells(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, 0.15, max_side=FINE)
    key = lambda cells: {(round(lo[0], 6), round(lo[1], 6)) for lo, _ in cells}
    assert len(low[1]) >= 1
    assert key(tall[1]) <= key(low[1])


def test_regions_straight_down_are_the_parts_outside_the_frame():
    """A camera straight down over the table: the seen part is a rectangle,
    so the regions are known by hand.  With 0.20 m look cells and 0.05 m fine
    cells the frame (x -0.012 to 0.612, y -0.232 to 0.232 at the box tops)
    shows the fine cells of x 0 to 0.6, y -0.2 to 0.2."""
    f = (H / 2.0) / math.tan(math.radians(robot_utils.WRIST_CAMERA_FOV_DEG) / 2.0)
    d = 0.525
    pose = _down(0.3, 0.0, TABLE_Z + 0.05 + d)
    assert (W / 2.0 - arm_eye.FRAME_MARGIN_PX) * d / f == pytest.approx(0.312, abs=1e-3)
    assert (H / 2.0 - arm_eye.FRAME_MARGIN_PX) * d / f == pytest.approx(0.232, abs=1e-3)
    regions = arm_eye.unseen_regions(pose, WORKSPACE[0], WORKSPACE[1], TABLE_Z, 0.05,
                                     max_side=0.20, fine_side=0.05)
    got = [tuple(round(float(v), 6) for v in (lo[0], lo[1], hi[0], hi[1])) for lo, hi in regions]
    want = [(-0.1, -0.4, 0.1, -0.2), (-0.1, -0.2, 0.0, 0.0), (-0.1, 0.0, 0.0, 0.2), (-0.1, 0.2, 0.1, 0.4),
            (0.1, -0.4, 0.3, -0.2), (0.1, 0.2, 0.3, 0.4),
            (0.3, -0.4, 0.5, -0.2), (0.3, 0.2, 0.5, 0.4),
            (0.5, -0.4, 0.7, -0.2), (0.6, -0.2, 0.7, 0.0), (0.6, 0.0, 0.7, 0.2), (0.5, 0.2, 0.7, 0.4)]
    assert got == pytest.approx(want)                         # x outer, y inner
    area = sum((hi[0] - lo[0]) * (hi[1] - lo[1]) for lo, hi in regions)
    assert area == pytest.approx(0.8 * 0.8 - 0.6 * 0.4)
    for lo, hi in regions:
        assert lo[2] == TABLE_Z and hi[2] == pytest.approx(TABLE_Z + 0.05)


def _fine_cells(max_side, fine):
    """The fine cells of unseen_regions' own two tilings, with the index of
    the look cell each lies in."""
    out = []
    k = 0
    for x0, x1 in arm_eye._tiles(WORKSPACE[0][0], WORKSPACE[0][1], max_side):
        for y0, y1 in arm_eye._tiles(WORKSPACE[1][0], WORKSPACE[1][1], max_side):
            for fx0, fx1 in arm_eye._tiles(x0, x1, fine):
                for fy0, fy1 in arm_eye._tiles(y0, y1, fine):
                    out.append((k, (x0, y0, x1, y1), (fx0, fy0, fx1, fy1)))
            k += 1
    return out


def test_regions_at_the_home_view_hold_every_unseen_fine_cell_and_no_more_than_a_look():
    """TAMPURA's home view (slanted): every fine cell the image does not hold
    lies in the region of its own look cell; a region stays inside its look
    cell, so none is larger than one look holds and no two overlap; each side
    of a region touches an unseen fine cell (the box is tight); a look cell
    wholly seen has no region."""
    side = observe_views.look_cell_side()
    fine = arm_eye.UNSEEN_FINE_SIDE_M
    regions = arm_eye.unseen_regions(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, 0.05,
                                     max_side=side)
    by_cell = {}
    for k, cell, (fx0, fy0, fx1, fy1) in _fine_cells(side, fine):
        seen = arm_eye.box_in_frame(POSE_A, (fx0, fy0, TABLE_Z), (fx1, fy1, TABLE_Z + 0.05))
        by_cell.setdefault(k, (cell, []))[1].append(((fx0, fy0, fx1, fy1), seen))
    with_unseen = [(cell, [c for c, s in fines if not s]) for cell, fines in by_cell.values()
                   if any(not s for _, s in fines)]
    assert len(regions) == len(with_unseen)
    assert len(with_unseen) < len(by_cell), "the home view should hold at least one look cell"
    eps = 1e-9
    for (lo, hi), (cell, unseen) in zip(regions, with_unseen):
        assert hi[0] - lo[0] <= side + eps and hi[1] - lo[1] <= side + eps
        assert cell[0] - eps <= lo[0] and hi[0] <= cell[2] + eps
        assert cell[1] - eps <= lo[1] and hi[1] <= cell[3] + eps
        for fx0, fy0, fx1, fy1 in unseen:
            assert lo[0] - eps <= fx0 and fx1 <= hi[0] + eps
            assert lo[1] - eps <= fy0 and fy1 <= hi[1] + eps
        assert lo[0] == pytest.approx(min(c[0] for c in unseen))
        assert lo[1] == pytest.approx(min(c[1] for c in unseen))
        assert hi[0] == pytest.approx(max(c[2] for c in unseen))
        assert hi[1] == pytest.approx(max(c[3] for c in unseen))
    area = sum((hi[0] - lo[0]) * (hi[1] - lo[1]) for lo, hi in regions)
    assert 0.0 < area < 0.8 * 0.8


def test_the_unseen_boxels_are_the_regions_with_fixed_names_and_no_parent():
    side = observe_views.look_cell_side()
    regions = arm_eye.unseen_regions(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, 0.05,
                                     max_side=side)
    boxels = arm_eye.unseen_boxels(POSE_A, WORKSPACE[0], WORKSPACE[1], TABLE_Z, 0.05,
                                   max_side=side)
    assert [b.id for b in boxels] == [f"unseen_{i:03d}" for i in range(len(regions))]
    for b, (lo, hi) in zip(boxels, regions):
        assert np.array_equal(b.min_corner, lo) and np.array_equal(b.max_corner, hi)
        assert b.boxel_type == BoxelType.SHADOW
        assert b.created_by_object is None and b.created_by_boxel_id is None
        assert b.on_surface == 'table' and b.surface_z == TABLE_Z
