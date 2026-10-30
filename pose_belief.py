"""
pose_belief.py — the pose belief of M8 and M9 (PLAN_P4_POSE_GRASP_SAMPLERS.md
A and B): how uncertain an object's believed centre is (pose_radius), and
how much uncertainty a top-down pinch tolerates (commit_margin).

The planner commits to a pick only when pose_radius <= commit_margin
(obj_pose_known); otherwise it must observe first.  Both sides come from
the belief: the radius from the detection that set the pose, the margin
from the believed extents, never from the simulator.

Pure numpy (no pybullet), like perception.
"""

import math
from typing import Optional

import numpy as np

# A: one pixel of detection noise, declared a priori (not fitted).
DETECTION_PIXEL_NOISE_PX = 1.0

# A: the yaw estimator's noise (rad) per camera, and Q-C's deadband: a
# fitted yaw below its camera's noise is taken as 0, so axis-aligned
# objects keep today's wrist orientation.  PLACE_POSE_TOL (m) is the
# radius a commanded placement leaves.  All are ground-truth calibrations
# on our scenes' objects, a die-class body on our empty table and
# synthetic renders, never on a TAMPURA layout (tools/_calib_pose_noise.py,
# BF#29), each the 95th percentile, the quantile fixed before measuring.
# The eye's value comes from the die-class yaw sweep alone: our scenes'
# objects all stand at yaw 0, where the eye's estimate (which snaps yaws
# within about 10 deg of an axis to 0) is trivially right, so pooling them
# would report 0.06 deg.  The wrist camera looks straight down and has no
# such blind zone.
YAW_NOISE = {'eye': math.radians(9.475), 'wrist': math.radians(0.202)}
YAW_DEADBAND = dict(YAW_NOISE)
# PLACE_POSE_TOL: 36 placements over 20 of our runs (random-pairs seeds 0-4,
# n_occluders 2-4, holding and find-and-tray-stack): p50 1.8 mm, max 5.4 mm.
PLACE_POSE_TOL = 0.003609

# The model tweaks' switches (M8, M9, M10, and M8's aperture rule, which
# changes every pick), set once per run by main().  OFF reproduces the
# pipeline without them: today's domain file, AABB grasps, pick returns
# and retry.  Defaults stay OFF until the Q-F decision entry lands (plan
# step 6).
SWITCHES = {'M8': False, 'M9': False, 'M10': False,
            'pick_aperture_from_pose': False}

# B: the pinch needs this clearance between a pad and the believed face
# (the sampler's 2 mm descent clearance), and Q-B: the pads must cover at
# least half the face across the pinch.
PINCH_CLEARANCE = 0.002
PERP_COMMIT_FRACTION = 0.5


def grasp_axes(yaw: float):
    """Unit xy vectors along and across a yaw."""
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([c, s]), np.array([-s, c])


def pixel_footprint(pixel_steps, yaw: float = 0.0) -> float:
    """The larger world displacement of one pixel step along the grasp
    axes at this yaw (the pinch axis and the one across it)."""
    steps = np.asarray(pixel_steps, dtype=float)
    return float(max(np.max(np.abs(steps @ a)) for a in grasp_axes(yaw)))


def _sorted_xy(v) -> np.ndarray:
    return np.sort(np.asarray(v, dtype=float)[:2])


def completion_term(det, body_extents=None, rigid_ext=None) -> float:
    """0 when the rectangle fit holds (it replaces the completion); else
    half the difference between the completed footprint and the tracked
    rigid extents (body_extents, else the registry's rigid extent, else
    0).  Compared as sorted side lengths: without a valid yaw the
    footprint's axes are unknown.  Never the raw stretch."""
    if det.yaw_valid:
        return 0.0
    known = body_extents if body_extents is not None else rigid_ext
    if known is None:
        return 0.0
    completed = _sorted_xy(det.est_max - det.est_min)
    return float(0.5 * np.max(np.abs(completed - _sorted_xy(known))))


def pose_radius(det, yaw_noise: float, body_extents=None, rigid_ext=None,
                first_partial: bool = False) -> float:
    """A's formula for one detection:
        DETECTION_PIXEL_NOISE_PX * pixel footprint along the grasp axes
      + yaw_noise * the larger xy half-extent
      + the completion term.
    ``first_partial``: a partial detection at an object's FIRST
    registration adds half the square-footprint completion it received,
    so a partly seen object gets a finite but larger radius."""
    yaw = det.yaw if det.yaw_valid else 0.0
    if det.yaw_valid and det.body_extents is not None:
        half = 0.5 * float(np.max(det.body_extents[:2]))
    else:
        half = 0.5 * float(np.max(det.est_max[:2] - det.est_min[:2]))
    r = (DETECTION_PIXEL_NOISE_PX * pixel_footprint(det.pixel_steps, yaw)
         + yaw_noise * half
         + completion_term(det, body_extents, rigid_ext))
    if first_partial and det.raw_xy_ext is not None:
        added = (det.est_max[:2] - det.est_min[:2]) - det.raw_xy_ext
        r += 0.5 * float(np.max(added))
    return float(r)


def commit_margin(ext_xy, gripper_half_open: float, max_span: float,
                  square_tol: float) -> Optional[float]:
    """B: the smallest pose error a top-down pinch tolerates, over the
    grasp families sample_grasp offers for these believed extents (side
    lengths along the pinch-selecting axes): per family
    min(gripper_half_open - pinch_half - PINCH_CLEARANCE,
        PERP_COMMIT_FRACTION * perp_half).
    A near-square footprint gets one family pinching its longer side
    (as the sampler's single yaw sizes it); a family wider than max_span
    is not offered.  None when no family is offered."""
    ex, ey = float(ext_xy[0]), float(ext_xy[1])
    if abs(ex - ey) <= square_tol:
        families = [(max(ex, ey), min(ex, ey))]
    else:
        families = [(ey, ex), (ex, ey)]
    margins = [min(gripper_half_open - pinch / 2.0 - PINCH_CLEARANCE,
                   PERP_COMMIT_FRACTION * perp / 2.0)
               for pinch, perp in families if pinch <= max_span]
    return min(margins) if margins else None


def _wrap(angle: float, period: float) -> float:
    return float((angle + period / 2.0) % period - period / 2.0)


def pad_direction(grasp_yaw: float) -> np.ndarray:
    """Unit xy direction the pads close along for a top-down grasp at this
    yaw (the hand's y axis; robot_utils.pinch_direction)."""
    return np.array([-math.sin(grasp_yaw), math.cos(grasp_yaw)])


def aabb_half_along(pinch_dir_xy, aabb_ext) -> float:
    """Half the registry box's side along the axis the pads close nearest
    to (x when the pinch direction is within 45 deg of it, else y).

    BF#46 (2026-10-30): this was the box's support width along the pinch
    direction, 0.5 (|d.x| ex + |d.y| ey), which for a pinch away from the
    axes adds up to the other side.  A cup is a square 69.6 mm box whose
    fitted yaw is arbitrary (a round footprint), so it read 85 to 98 mm,
    wider than GRASP_MAX_SPAN, and lost every grasp family, with it every
    look configuration and the pose commit: the planner had no way to move
    it (find_dice seed 10 on 1747173593, two of four cups never considered,
    no plan with their shadows unsearched).  The pads close along the
    fitted yaw, where a box's width is its own side and a round body's its
    diameter; the registry box's side along the nearest axis bounds both
    (a box yawed within 45 deg has sides at least its body extents along
    them unless its footprint is thinner than 0.41 of its length).
    """
    d = np.asarray(pinch_dir_xy, dtype=float)[:2]
    axis = 0 if abs(float(d[0])) >= abs(float(d[1])) else 1
    return 0.5 * float(aabb_ext[axis])


def sized_pinch_half(pinch_dir_xy, yaw: float, body_extents, aabb_ext) -> float:
    """Q-H (a), user decision 2026-10-29: M9 keeps the fitted yaw and aim
    but sizes the pinch on the wider of the fitted rectangle and the
    registry AABB along the pads.  The top face can be narrower than the
    body where the pads close (an upturned cup's base, BF#33 seed 0); the
    AABB covers the whole body, its side along the axis nearest the pads
    (aabb_half_along; the support projection used before inflated a yawed
    pinch by up to the other side, BF#46)."""
    fitted = pinch_half_extent(pinch_dir_xy, yaw, body_extents)
    if aabb_ext is None:
        return fitted
    return max(fitted, aabb_half_along(pinch_dir_xy, aabb_ext))


def fitted_grasp_candidates(yaw: float, body_extents,
                            square_tol: float, aabb_ext=None):
    """M9: the top-down grasps of an object with a valid yaw, as (grasp
    yaw, pinch span) pairs.  The pads close along the hand's y axis, so at
    grasp yaw = the object's yaw they pinch across it (span = the second
    extent) and a quarter turn later along it (span = the first).  Each
    yaw is the smallest wrist rotation of its class (the pinch is
    symmetric under a half turn, a near-square footprint under a quarter
    turn); a near-square footprint gets one grasp, a rectangle both, the
    shorter span first, as the AABB sampler orders them.  With
    ``aabb_ext`` each span is sized by sized_pinch_half (Q-H (a))."""
    e0, e1 = float(body_extents[0]), float(body_extents[1])
    if abs(e0 - e1) <= square_tol:
        cands = [(_wrap(yaw, math.pi / 2.0), max(e0, e1))]
    else:
        cands = [(_wrap(yaw, math.pi), e1),
                 (_wrap(yaw + math.pi / 2.0, math.pi), e0)]
    if aabb_ext is not None:
        cands = [(gy, max(span, 2.0 * aabb_half_along(pad_direction(gy), aabb_ext)))
                 for gy, span in cands]
    return sorted(cands, key=lambda c: c[1])


def pinch_half_extent(pinch_dir_xy, yaw: float, body_extents) -> float:
    """Half the width of the yawed rectangle along a pinch direction."""
    d = np.asarray(pinch_dir_xy, dtype=float)[:2]
    d = d / np.linalg.norm(d)
    u, v = grasp_axes(yaw)
    return 0.5 * (abs(float(d @ u)) * float(body_extents[0])
                  + abs(float(d @ v)) * float(body_extents[1]))


def believed_margin(boxel, gripper_half_open: float, max_span: float,
                    square_tol: float) -> Optional[float]:
    """B: the commit margin from the belief, over the grasp families the
    sampler would offer this boxel: the fused rectangle when M9 uses it,
    else the registry AABB.  None when no family is offered."""
    aabb = (np.asarray(boxel.max_corner, dtype=float)
            - np.asarray(boxel.min_corner, dtype=float))
    if not uses_fitted_pose(boxel):
        return commit_margin(aabb[:2], gripper_half_open, max_span, square_tol)
    # M9: the fitted families, spans sized as the sampler sizes them
    # (Q-H (a)); the perpendicular half from the fitted rectangle.
    margins = []
    for gy, span in fitted_grasp_candidates(boxel.yaw, boxel.body_extents,
                                            square_tol, aabb):
        if span > max_span:
            continue
        d = pad_direction(gy)
        perp = pinch_half_extent(np.array([d[1], -d[0]]), boxel.yaw,
                                 boxel.body_extents)
        margins.append(min(gripper_half_open - span / 2.0 - PINCH_CLEARANCE,
                           PERP_COMMIT_FRACTION * perp))
    return min(margins) if margins else None


def pose_known(boxel, gripper_half_open: float, max_span: float,
               square_tol: float) -> bool:
    """B's commit rule: pose_radius <= the believed commit margin."""
    m = believed_margin(boxel, gripper_half_open, max_span, square_tol)
    return m is not None and float(boxel.pose_radius) <= m


def uses_fitted_pose(boxel) -> bool:
    """M9 is on and the boxel carries a valid yaw and fused extents."""
    return bool(SWITCHES['M9'] and boxel is not None
                and getattr(boxel, 'yaw_valid', False)
                and getattr(boxel, 'body_extents', None) is not None)

def _any_on() -> bool:
    return any(SWITCHES.values())


def _fuse(boxel, det, camera: str, max_span: float) -> None:
    """M9 fusion of a complete detection's rectangle into the boxel: the
    new yaw is first aligned to the stored one (the k * pi/2 equivalent
    nearest it, extents swapped on an odd quarter turn), then
    body_extents = per-axis max, yaw = latest, capped at max_span in xy.
    An observation larger than the stored extents by more than the pixel
    noise (one pixel each side) is not fused.  Q-C: a yaw within the
    camera's deadband of 0 is stored as 0."""
    ext = np.asarray(det.body_extents, dtype=float).copy()
    yaw = float(det.yaw)
    if boxel.body_extents is not None:
        k = int(round((boxel.yaw - yaw) / (math.pi / 2.0)))
        yaw += k * math.pi / 2.0
        if k % 2:
            ext[:2] = ext[1::-1]
        stored = np.asarray(boxel.body_extents, dtype=float)
        noise = 2.0 * DETECTION_PIXEL_NOISE_PX * pixel_footprint(det.pixel_steps, yaw)
        if np.any(ext[:2] > stored[:2] + noise):
            print(f"    [M9] {boxel.id}: rectangle {np.round(ext[:2] * 1e3, 1)} mm "
                  f"exceeds the fused {np.round(stored[:2] * 1e3, 1)} mm by more "
                  f"than the pixel noise — not fused")
            return
        ext = np.maximum(ext, stored)
    ext[:2] = np.minimum(ext[:2], max_span)
    if abs(yaw) < YAW_DEADBAND[camera]:
        yaw = 0.0
    boxel.body_extents = ext
    boxel.yaw = yaw
    boxel.yaw_valid = True
    boxel.rect_center = np.asarray(det.rect_center, dtype=float).copy()


def record_detection(boxel, det, camera: str, complete: bool,
                     first: bool = False, rigid_ext=None,
                     max_span: float = 0.076) -> None:
    """A's rule for a pose writer that re-poses a boxel from a detection:
    a COMPLETE detection sets the radius by the formula (after fusing its
    rectangle, M9); a partial one leaves the radius and is never fused,
    except at an object's FIRST registration, where it gets the formula
    plus half its completion.  No-op while every switch is OFF."""
    if not _any_on():
        return
    if complete and det.yaw_valid and det.body_extents is not None:
        _fuse(boxel, det, camera, max_span)
    if complete or first:
        boxel.pose_radius = pose_radius(
            det, YAW_NOISE[camera], boxel.body_extents, rigid_ext,
            first_partial=not complete)
    if complete:
        boxel.complete_detections += 1


def mark_pose_unknown(boxel) -> None:
    """A: an inferred or disturbed pose (post-stack occluded re-pose, WP2c
    drop, topple re-init, a failed pick that touched it, grip lost after
    the lift, #P2 disturbed without a complete detection)."""
    if boxel is not None:
        boxel.pose_radius = math.inf


def mark_pose_commanded(boxel) -> None:
    """A: a pose set from a commanded placement, not observed."""
    if boxel is not None and _any_on():
        boxel.pose_radius = PLACE_POSE_TOL