"""Path 9: ours with the arm camera only (--eye arm).

Design: archive/tampura_bridge_plan_2026-10-25/tracks/look/ARM_ONLY_DESIGN.md.
The overview camera of this mode is the arm camera: at the arm's start
configuration for the first image, and where the arm stands for every later
image.  Hani, 2026-11-14 04:40, via the coordinator (verbatim): "so look
should be an eyle in the hand. no need for a third option".  The look
manager, 2026-11-14: "the first image, the regions and every check come from
the arm camera, and the fixed camera feeds nothing to the robot."

This module holds the switch's rule, the start of an arm-camera run and the
geometry of the mode.  Wired (steps 1 to 3, 2026-11-14): the switch, the
first image, the part of the table that image does not show, and every later
image taken where the arm stands and judged only on what it holds wholly.

  check_mode         the switch's rule: --eye arm needs a look;
  parse_joints       a start configuration from the command line;
  TAMPURA_HOME_JOINTS  the start configuration (and q_home) when neither the
                     caller nor the command line gives one: TAMPURA's home;
  place_arm          scene construction in a world of our own: the arm stands
                     at the start configuration before the first image;
  use_start_view     the env's observation camera becomes the arm camera at
                     the arm's current joints;
  follow_arm         from the first image on, every env render takes
                     use_start_view's camera again first, so it is the arm
                     camera where the arm stands; marks the env;
  following          whether an env is so marked: the one name every path of
                     step 3 outside main() reads the switch through;
  start_camera       the env's observation-camera attributes for the arm
                     camera at the arm's current joints (the hand's forward
                     kinematics times the declared mount: proprioception,
                     never a simulator object read);
  project            world points to pixels of a camera pose, the convention
                     of robot_utils.wrist_camera_matrices;
  box_in_frame       whether a box lies wholly inside the image with a margin;
  view_pose          the camera pose a render's view matrix was made from;
  in_frame           whether boxes lie wholly in a render's image: what a
                     check after an action may judge;
  unseen_fine_cells  the window tiled into fine cells, and which of them the
                     first image does not show: a cell is seen only when its
                     whole volume (up to the hidden target's height) is inside
                     the image.  Bodies inside the image hide what is behind
                     them; that part is the shadow code's, unchanged;
  merge_cells        marked fine cells merged into few boxes: runs in each
                     row, equal runs of consecutive rows stacked;
  box_minus          a plain axis-aligned box difference;
  minus_known        boxes minus what the first scan's boxes claim;
  unseen_regions     the first image's own cut (PLAN 11.16): the unseen fine
                     cells merged, minus the first scan's boxes, cut to no
                     look's size;
  unseen_boxels      those regions as hidden-region boxels with fixed names:
                     what test_full_pipeline.main adds to the first scan.
"""
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pybullet as p

from acting import robot_utils
from world.boxel_data import BoxelData, BoxelType

EYE_MODES = ('fixed', 'arm')
# The env attributes every fixed-camera path reads: boxel_env's
# _view_and_projection_matrices, detect_objects, _depth_buffer_to_meters and
# the oracle's rays; execution.py and world_eye through the env.  The shadow
# calculator keeps its own copy of the position (use_start_view sets both).
CAMERA_ATTRIBUTES = ('camera_position', 'camera_target', 'camera_up', 'fov',
                     'image_width', 'image_height', 'near_plane', 'far_plane')
# The force that holds the arm at the start configuration: the one
# robot_utils.move_robot_smooth and hold_at_config command.
ARM_HOLD_FORCE = 240
_NOT_TASK_BODIES = ('plane', 'table', 'robot')

# Seen and unseen are told apart on fine cells of at most this side, the
# window tiled from its corner (PLAN 11.16).
UNSEEN_FINE_SIDE_M = 0.05
# A piece of an unseen region with a side under this is dropped: it holds no
# target, and the box arithmetic leaves such slivers where faces meet.
UNSEEN_MIN_SIDE_M = 0.001
# The frame margin of the look's own certification (observe_views: every
# lattice point in the frame "with 8 px to spare").  Step 3's checks after an
# action take the same margin (in_frame).
FRAME_MARGIN_PX = 8
# The switch's mark on an env: set by follow_arm (test_full_pipeline.main,
# under --eye arm alone) and read through following().
FOLLOW_FLAG = 'arm_eye_follows'
# The start configuration of --eye arm, and so its q_home, when neither the
# caller (find_dice passes DEFAULT_ARM_POS) nor --eye-start-joints gives one:
# TAMPURA's home joints, their DEFAULT_ARM_POS in
# tampura_environments/panda_utils/robot.py, as recorded in
# tracks/look/evidence/arm_camera_home_pose_20261112.txt.  Hani's Q2 answer
# (tracks/look/FOR_HANI.md): with the arm camera only, the arm starts at
# TAMPURA's home joints on our tabletop as on find_dice.  A literal, since the
# tabletop run cannot import tampura_environments;
# tampura_bridge/tests/test_arm_eye_home.py checks it against theirs.
TAMPURA_HOME_JOINTS = (-0.0806406098426434, -1.6722951504174777, 0.07069076842695393,
                       -2.7449419709102822, 0.08184716251979611, 1.7516337599063168,
                       0.7849295270972781)


def _focal_px() -> float:
    """Focal length in pixels (square pixels) of the arm camera."""
    return (robot_utils.WRIST_CAMERA_HEIGHT / 2.0) / math.tan(
        math.radians(robot_utils.WRIST_CAMERA_FOV_DEG) / 2.0)


def check_mode(eye: str, look_mode: str) -> None:
    """The switch's rule.  --eye arm needs --look centred or --look boxel:
    sense is the fixed camera's action, so without a look nothing in the
    domain could put the arm camera anywhere."""
    if eye not in EYE_MODES:
        raise ValueError(f"--eye is one of {EYE_MODES}, not {eye!r}")
    if eye == 'arm' and look_mode not in ('boxel', 'centred'):
        raise ValueError(f"--eye arm needs --look centred or --look boxel (got "
                         f"--look {look_mode}): sense is the fixed camera's action")


def parse_joints(text) -> Optional[List[float]]:
    """A start configuration from the command line: one joint angle per arm
    joint, in radians, separated by commas.  Empty or None: None (the caller
    takes the caller's home joints, else TAMPURA_HOME_JOINTS)."""
    if text is None or not str(text).strip():
        return None
    try:
        joints = [float(v) for v in str(text).split(',')]
    except ValueError:
        raise ValueError(f"--eye-start-joints takes joint angles in radians "
                         f"separated by commas, not {text!r}") from None
    if len(joints) != len(robot_utils.REST_POSES):
        raise ValueError(f"--eye-start-joints takes {len(robot_utils.REST_POSES)} "
                         f"joint angles, got {len(joints)}")
    return joints


def place_arm(env, joints: Sequence[float]) -> bool:
    """Scene construction in a world of our own: the arm stands at ``joints``
    in the executing client and in the plan twin before the first image, and
    is held there, as _setup_scene opens the fingers.  A start configuration
    that touches a task body is refused.  An adopted world is its owner's:
    nothing is moved in it (the bridge's arm stands at its home already), and
    the camera is taken from where the arm is.  True when the arm was put."""
    if getattr(env, '_adopted', False):
        return False
    robot = env.objects['robot'].object_id
    arm = robot_utils.robot_model().arm_joints
    if len(joints) != len(arm):
        raise ValueError(f"the start configuration has {len(joints)} joints, "
                         f"the arm has {len(arm)}")
    for j, q in zip(arm, joints):
        p.resetJointState(robot, j, float(q), physicsClientId=env.client_id)
        p.setJointMotorControl2(robot, j, p.POSITION_CONTROL,
                                targetPosition=float(q), force=ARM_HOLD_FORCE,
                                physicsClientId=env.client_id)
        if env.plan_robot_id is not None:
            p.resetJointState(env.plan_robot_id, j, float(q), physicsClientId=env.plan_client_id)
    touched = sorted(
        name for name, info in env.objects.items()
        if name not in _NOT_TASK_BODIES
        and p.getClosestPoints(robot, info.object_id, 0.0,
                               physicsClientId=env.client_id))
    if touched:
        raise ValueError(f"the arm's start configuration touches {touched}: "
                         f"--eye arm needs a start configuration that is free")
    return True


def use_start_view(env, robot_id: Optional[int] = None) -> Dict[str, object]:
    """The env's observation camera becomes the arm camera at the arm's
    current joints in the executing client: its pose and its own image
    (CAMERA_ATTRIBUTES), and the shadow calculator's copy of the position.
    Every path that renders or casts from the env's camera does so from this
    view, with today's code, until the arm moves; follow_arm takes the view
    again before every env render.  Returns start_camera's dict."""
    if robot_id is None:
        robot_id = env.objects['robot'].object_id
    cam = start_camera(robot_id, env.client_id)
    for name in CAMERA_ATTRIBUTES:
        setattr(env, name, cam[name])
    env.shadow_calculator.camera_position = cam['camera_position']
    return cam


def follow_arm(env, robot_id: Optional[int] = None) -> None:
    """--eye arm, once the first image's camera is set (step 3): every env
    render from here on is the arm camera where the arm stands.  Each env
    render computes its matrices with env._view_and_projection_matrices()
    just before pybullet.getCameraImage (BoxelTestEnv's detect_objects,
    get_camera_observation and refresh_debug_camera_views, and every caller
    that renders with the env's matrices).  On this env alone that method
    first takes use_start_view's camera again at the arm's current joints,
    so the env's camera attributes and the shadow calculator's position
    follow the arm; the class's method then computes the matrices from the
    attributes as before.  Marks the env (following)."""
    if robot_id is None:
        robot_id = env.objects['robot'].object_id
    matrices = type(env)._view_and_projection_matrices

    def view_and_projection_matrices():
        use_start_view(env, robot_id)
        return matrices(env)

    env._view_and_projection_matrices = view_and_projection_matrices
    setattr(env, FOLLOW_FLAG, True)


def following(env) -> bool:
    """True on an env follow_arm marked (--eye arm), False on any other (None
    included).  Every path of step 3 outside main() reads the switch through
    this name."""
    return bool(getattr(env, FOLLOW_FLAG, False))


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


def view_pose(view) -> np.ndarray:
    """The camera pose (4 x 4, project's convention) a render's view matrix
    was made from.  p.computeViewMatrix gives 16 numbers in column order; the
    rows of the matrix's rotation R are image right, image up and the optical
    axis backwards, and the camera sits at -R^T t.  The pose's +y column is
    image down: the up vector wrist_camera_matrices and start_camera pass is
    the pose's -y."""
    m = np.asarray(view, dtype=float).reshape(4, 4).T
    r = m[:3, :3]
    pose = np.eye(4)
    pose[:3, 0] = r[0]
    pose[:3, 1] = -r[1]
    pose[:3, 2] = -r[2]
    pose[:3, 3] = -r.T @ m[:3, 3]
    return pose


def in_frame(view, *boxes, margin_px: float = FRAME_MARGIN_PX) -> bool:
    """True when every box (lo, hi) lies wholly in the image of the render
    whose view matrix is ``view``: box_in_frame on view_pose's pose, with the
    arm camera's own image and the look's frame margin.  A check after an
    action gives an absence verdict (lost, a fragment observed empty) only
    when this holds for the believed box, and a presence verdict (re-pose,
    disturbed, toppled, a registration) only when it holds for the
    detection's box (execution.frame_judgement)."""
    pose = view_pose(view)
    return all(box_in_frame(pose, lo, hi, margin_px) for lo, hi in boxes)


def _tiles(lo: float, hi: float, max_side: float) -> List[Tuple[float, float]]:
    n = max(1, int(math.ceil((hi - lo) / max_side - 1e-9)))
    step = (hi - lo) / n
    return [(lo + i * step, lo + (i + 1) * step) for i in range(n)]


def unseen_fine_cells(camera_pose: np.ndarray, x_range: Sequence[float],
                      y_range: Sequence[float], table_z: float, height: float,
                      fine_side: float = UNSEEN_FINE_SIDE_M,
                      margin_px: float = FRAME_MARGIN_PX
                      ) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]],
                                 List[List[bool]]]:
    """The window tiled into equal fine cells no longer than ``fine_side``
    and which of them the first image does not show: (x tiles, y tiles,
    unseen), unseen[i][j] for x tile i and y tile j.  A cell is seen only
    when its whole box, from the table top to ``height`` above it, is inside
    the image with ``margin_px`` to spare (box_in_frame); a cell the image's
    edge cuts counts as unseen (the cautious side)."""
    xs = _tiles(float(x_range[0]), float(x_range[1]), fine_side)
    ys = _tiles(float(y_range[0]), float(y_range[1]), fine_side)
    top = float(table_z) + float(height)
    unseen = [[not box_in_frame(camera_pose, (x0, y0, table_z), (x1, y1, top), margin_px)
               for y0, y1 in ys]
              for x0, x1 in xs]
    return xs, ys, unseen


def merge_cells(xs: Sequence[Tuple[float, float]], ys: Sequence[Tuple[float, float]],
                marked: Sequence[Sequence[bool]], table_z: float, height: float
                ) -> List[Tuple[np.ndarray, np.ndarray]]:
    """The marked fine cells merged into boxes from the table top to
    ``height`` above it.  In each row (one x tile) consecutive marked cells
    are joined into runs along y; a run that is the same in consecutive rows
    is stacked into one box along x.  So every box holds marked cells only,
    no two boxes share a volume, and the boxes' union is the marked cells'
    union.  The order is fixed (by a box's first row, then its first y
    tile), so the same cells give the same list."""
    spans = []          # (first row, last row, first y tile, last y tile)
    open_runs = {}      # (first y tile, last y tile) -> first row
    for i, row in enumerate(marked):
        runs, start = [], None
        for j, mark in enumerate(row):
            if mark and start is None:
                start = j
            if not mark and start is not None:
                runs.append((start, j - 1))
                start = None
        if start is not None:
            runs.append((start, len(row) - 1))
        for run in [r for r in open_runs if r not in runs]:
            spans.append((open_runs.pop(run), i - 1) + run)
        for run in runs:
            open_runs.setdefault(run, i)
    for run, first in open_runs.items():
        spans.append((first, len(marked) - 1) + run)
    spans.sort(key=lambda s: (s[0], s[2]))
    bottom = float(table_z)
    top = float(table_z) + float(height)
    return [(np.array([xs[i0][0], ys[j0][0], bottom]),
             np.array([xs[i1][1], ys[j1][1], top]))
            for i0, i1, j0, j1 in spans]


def box_minus(lo: Sequence[float], hi: Sequence[float], other_lo: Sequence[float],
              other_hi: Sequence[float], min_side: float = UNSEEN_MIN_SIDE_M
              ) -> List[Tuple[np.ndarray, np.ndarray]]:
    """The box [lo, hi] minus the box [other_lo, other_hi], a plain
    axis-aligned difference (the idea of ShadowCalculator._subtract_aabb):
    up to six boxes, made in a fixed order, below and above the other box in
    x, then in y, then in z.  Boxes that share no volume (touching faces
    included) leave [lo, hi] whole.  A remainder with a side under
    ``min_side`` is dropped."""
    lo = np.array(lo, dtype=float)
    hi = np.array(hi, dtype=float)
    o_lo = np.asarray(other_lo, dtype=float)
    o_hi = np.asarray(other_hi, dtype=float)
    if not np.all(np.minimum(hi, o_hi) - np.maximum(lo, o_lo) > 0.0):
        return [(lo, hi)]
    out = []
    for axis in range(3):
        if lo[axis] < o_lo[axis]:
            part_hi = hi.copy()
            part_hi[axis] = o_lo[axis]
            out.append((lo.copy(), part_hi))
            lo[axis] = o_lo[axis]
        if hi[axis] > o_hi[axis]:
            part_lo = lo.copy()
            part_lo[axis] = o_hi[axis]
            out.append((part_lo, hi.copy()))
            hi[axis] = o_hi[axis]
    return [(a, b) for a, b in out if np.all(b - a >= min_side)]


def minus_known(boxes: Sequence[Tuple[np.ndarray, np.ndarray]],
                known: Sequence[BoxelData], min_side: float = UNSEEN_MIN_SIDE_M
                ) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Each box minus every OBJECT box and SHADOW fragment in ``known``, in
    the order of ``known``, so no box shares a volume with what the first
    scan claims and every table point is in at most one hidden region (audit
    #68's rule).  The pieces of a box take its place in the list, in the
    order box_minus makes them."""
    claimed = [(np.asarray(b.min_corner, dtype=float), np.asarray(b.max_corner, dtype=float))
               for b in known if b.boxel_type in (BoxelType.OBJECT, BoxelType.SHADOW)]
    out = []
    for lo, hi in boxes:
        pieces = [(lo, hi)]
        for o_lo, o_hi in claimed:
            pieces = [part for a, b in pieces
                      for part in box_minus(a, b, o_lo, o_hi, min_side)]
        out.extend(pieces)
    return out


def unseen_regions(camera_pose: np.ndarray, x_range: Sequence[float],
                   y_range: Sequence[float], table_z: float, height: float, *,
                   known: Sequence[BoxelData] = (),
                   fine_side: float = UNSEEN_FINE_SIDE_M,
                   margin_px: float = FRAME_MARGIN_PX,
                   min_side: float = UNSEEN_MIN_SIDE_M
                   ) -> List[Tuple[np.ndarray, np.ndarray]]:
    """The part of the window the first image does not show, as that image's
    own cut (PLAN 11.16): the unseen fine cells merged into boxes
    (merge_cells), each minus what an object box or a shadow fragment of the
    first scan claims (minus_known).  No box is cut to a look's size (PLAN
    11.16: a region is cut only by what an image saw).  The boxes lie between
    the table top and ``height`` above it (a piece over a known box lower than
    that starts at the known box's top), in a fixed order, so a seed replays."""
    xs, ys, unseen = unseen_fine_cells(camera_pose, x_range, y_range, table_z, height,
                                       fine_side, margin_px)
    return minus_known(merge_cells(xs, ys, unseen, table_z, height), known, min_side)


def unseen_boxels(camera_pose: np.ndarray, x_range: Sequence[float],
                  y_range: Sequence[float], table_z: float, height: float, *,
                  known: Sequence[BoxelData] = (),
                  fine_side: float = UNSEEN_FINE_SIDE_M,
                  margin_px: float = FRAME_MARGIN_PX,
                  min_side: float = UNSEEN_MIN_SIDE_M) -> List[BoxelData]:
    """unseen_regions as hidden-region boxels named unseen_000, unseen_001, ...
    in the regions' fixed order.  Each carries the table as its surface
    (on_surface 'table'; a piece over a lower known box starts at that box's
    top) and has no parent body: nothing the camera saw casts it, the image
    just ends there."""
    regions = unseen_regions(camera_pose, x_range, y_range, table_z, height, known=known,
                             fine_side=fine_side, margin_px=margin_px, min_side=min_side)
    return [BoxelData(id=f"unseen_{i:03d}", boxel_type=BoxelType.SHADOW,
                      min_corner=lo, max_corner=hi,
                      on_surface='table', surface_z=float(table_z))
            for i, (lo, hi) in enumerate(regions)]
