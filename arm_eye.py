"""Path 9 (b), PROVISIONAL: ours with the arm camera only (--eye arm).

Design: archive/tampura_bridge_plan_2026-10-25/tracks/look/ARM_ONLY_DESIGN.md.
The overview camera of this mode is the arm camera at the arm's start
configuration, so an overview image exists only while the arm stands there.

This module holds the geometry of that mode and nothing else.  Nothing in the
pipeline imports it yet (2026-11-12): the wiring comes behind a switch that is
off by default, and Hani has not answered the two questions it rests on
(tracks/look/FOR_HANI.md, Q1 and Q2).

  start_camera       the env's observation-camera attributes for the arm
                     camera at the arm's current joints (the hand's forward
                     kinematics times the declared mount: proprioception,
                     never a simulator object read);
  project            world points to pixels of a camera pose, the convention
                     of robot_utils.wrist_camera_matrices;
  box_in_frame       whether a box lies wholly inside the image with a margin;
  unseen_cells       the table cells the first image does not show: the
                     workspace tiled into cells one look can hold, minus the
                     cells whose whole volume (up to the hidden target's
                     height) is inside the image.  Bodies inside the image
                     hide what is behind them; that part is the shadow code's,
                     unchanged;
  unseen_regions     the same split told on a finer tiling and grouped into
                     regions one look holds: what the wiring will use;
  unseen_boxels      those regions as hidden-region boxels with fixed names.
"""
import math
from typing import Dict, List, Sequence, Tuple

import numpy as np

import robot_utils
from boxel_data import BoxelData, BoxelType

# No side of an unseen cell is longer than this: the arm camera sees 0.37 by
# 0.27 m of the table from 0.30 m above it, so one look holds one cell.
UNSEEN_MAX_SIDE_M = 0.20
# Seen and unseen are told apart on cells of at most this side; the unseen
# ones are then grouped into regions one look holds (unseen_regions).
UNSEEN_FINE_SIDE_M = 0.05
# The frame margin of the look's own certification (observe_views: every
# lattice point in the frame "with 8 px to spare").
FRAME_MARGIN_PX = 8


def _focal_px() -> float:
    """Focal length in pixels (square pixels) of the arm camera."""
    return (robot_utils.WRIST_CAMERA_HEIGHT / 2.0) / math.tan(
        math.radians(robot_utils.WRIST_CAMERA_FOV_DEG) / 2.0)


def start_camera(robot_id: int, physics_client: int = 0) -> Dict[str, object]:
    """The observation-camera attributes boxel_env reads (camera_position,
    camera_target, camera_up, fov, image_width, image_height, near_plane,
    far_plane) for the arm camera at the arm's current joints, and the 4 x 4
    pose they come from."""
    pose = robot_utils.wrist_camera_pose(robot_id, physics_client)
    pos = np.asarray(pose[:3, 3], dtype=float)
    return {
        'camera_pose': pose,
        'camera_position': pos,
        'camera_target': pos + np.asarray(pose[:3, 2], dtype=float),
        'camera_up': -np.asarray(pose[:3, 1], dtype=float),
        'fov': robot_utils.WRIST_CAMERA_FOV_DEG,
        'image_width': robot_utils.WRIST_CAMERA_WIDTH,
        'image_height': robot_utils.WRIST_CAMERA_HEIGHT,
        'near_plane': robot_utils.WRIST_CAMERA_NEAR,
        'far_plane': robot_utils.WRIST_CAMERA_FAR,
    }


def project(camera_pose: np.ndarray, points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Pixels (u right, v down) and depths along the optical axis of world
    ``points`` (n x 3) for a camera pose whose +z column is the optical axis,
    +x column image right and +y column image down."""
    pts = np.atleast_2d(np.asarray(points, dtype=float))
    rel = (pts - camera_pose[:3, 3]) @ camera_pose[:3, :3]
    z = rel[:, 2]
    f = _focal_px()
    safe = np.where(np.abs(z) < 1e-12, 1e-12, z)
    u = f * rel[:, 0] / safe + robot_utils.WRIST_CAMERA_WIDTH / 2.0
    v = f * rel[:, 1] / safe + robot_utils.WRIST_CAMERA_HEIGHT / 2.0
    return np.stack([u, v], axis=1), z


def box_in_frame(camera_pose: np.ndarray, lo: Sequence[float], hi: Sequence[float],
                 margin_px: float = FRAME_MARGIN_PX) -> bool:
    """True when all eight corners of the box [lo, hi] lie in front of the
    near plane and inside the image with ``margin_px`` to spare.  The image
    of a box is the hull of its corners, so this holds for the whole box."""
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1])
                        for z in (lo[2], hi[2])])
    px, depth = project(camera_pose, corners)
    if np.any(depth <= robot_utils.WRIST_CAMERA_NEAR):
        return False
    w, h = robot_utils.WRIST_CAMERA_WIDTH, robot_utils.WRIST_CAMERA_HEIGHT
    return bool(np.all(px[:, 0] >= margin_px) and np.all(px[:, 0] <= w - margin_px)
                and np.all(px[:, 1] >= margin_px) and np.all(px[:, 1] <= h - margin_px))


def _tiles(lo: float, hi: float, max_side: float) -> List[Tuple[float, float]]:
    n = max(1, int(math.ceil((hi - lo) / max_side - 1e-9)))
    step = (hi - lo) / n
    return [(lo + i * step, lo + (i + 1) * step) for i in range(n)]


def unseen_cells(camera_pose: np.ndarray, x_range: Sequence[float],
                 y_range: Sequence[float], table_z: float, height: float,
                 max_side: float = UNSEEN_MAX_SIDE_M,
                 margin_px: float = FRAME_MARGIN_PX
                 ) -> Tuple[List[Tuple[np.ndarray, np.ndarray]],
                            List[Tuple[np.ndarray, np.ndarray]]]:
    """Tile the workspace rectangle into equal cells no longer than
    ``max_side`` and split them by the first image: (unseen, seen), each a
    list of (min corner, max corner) boxes from the table top to ``height``
    above it.  A cell is seen only when its whole box is inside the image; a
    cell the image cuts counts as unseen (the cautious side).  Together the
    two lists tile the rectangle with no overlap, in a fixed order (x outer,
    y inner), so a seed replays."""
    unseen, seen = [], []
    for x0, x1 in _tiles(float(x_range[0]), float(x_range[1]), max_side):
        for y0, y1 in _tiles(float(y_range[0]), float(y_range[1]), max_side):
            lo = np.array([x0, y0, table_z])
            hi = np.array([x1, y1, table_z + height])
            (seen if box_in_frame(camera_pose, lo, hi, margin_px) else unseen).append((lo, hi))
    return unseen, seen


def unseen_regions(camera_pose: np.ndarray, x_range: Sequence[float],
                   y_range: Sequence[float], table_z: float, height: float,
                   max_side: float, fine_side: float = UNSEEN_FINE_SIDE_M,
                   margin_px: float = FRAME_MARGIN_PX
                   ) -> List[Tuple[np.ndarray, np.ndarray]]:
    """The regions of the table the first image does not show, each one small
    enough for one look (no side over ``max_side``).

    Two tilings, because the image's edge cuts every look-sized cell it
    touches (measured 2026-11-12: at 0.20 m no whole cell lies inside
    TAMPURA's home view).  The workspace is tiled into look cells; each look
    cell is tiled into fine cells (no side over ``fine_side``), and a fine
    cell is seen when its whole box, from the table top to ``height`` above
    it, is inside the image.  A look cell's region is the box around its
    unseen fine cells: no region for a cell wholly seen, the whole cell for a
    cell wholly unseen, the unseen part's box otherwise.  Where the image's
    edge crosses a look cell at a slant that box also holds seen fine cells
    (the cautious side).  Regions of different look cells never overlap, and
    the order is fixed (x outer, y inner), so a seed replays."""
    regions = []
    for x0, x1 in _tiles(float(x_range[0]), float(x_range[1]), max_side):
        for y0, y1 in _tiles(float(y_range[0]), float(y_range[1]), max_side):
            box = None
            for fx0, fx1 in _tiles(x0, x1, fine_side):
                for fy0, fy1 in _tiles(y0, y1, fine_side):
                    if box_in_frame(camera_pose, (fx0, fy0, table_z),
                                    (fx1, fy1, table_z + height), margin_px):
                        continue
                    box = ([fx0, fy0, fx1, fy1] if box is None else
                           [min(box[0], fx0), min(box[1], fy0),
                            max(box[2], fx1), max(box[3], fy1)])
            if box is not None:
                regions.append((np.array([box[0], box[1], table_z]),
                                np.array([box[2], box[3], table_z + height])))
    return regions


def unseen_boxels(camera_pose: np.ndarray, x_range: Sequence[float],
                  y_range: Sequence[float], table_z: float, height: float,
                  max_side: float, fine_side: float = UNSEEN_FINE_SIDE_M,
                  margin_px: float = FRAME_MARGIN_PX) -> List[BoxelData]:
    """unseen_regions as hidden-region boxels named unseen_000, unseen_001, ...
    in the regions' fixed order.  They stand on the table and have no parent
    body: nothing the camera saw casts them, the image just ends there."""
    out = []
    for i, (lo, hi) in enumerate(unseen_regions(camera_pose, x_range, y_range, table_z,
                                                height, max_side, fine_side, margin_px)):
        b = BoxelData(boxel_type=BoxelType.SHADOW, min_corner=lo, max_corner=hi,
                      on_surface='table', surface_z=float(table_z))
        b.id = f"unseen_{i:03d}"
        out.append(b)
    return out
