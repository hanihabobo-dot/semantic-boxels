"""
look_views.py: where the camera goes for a look, and what a look reveals
(path 9 of the dev tracks, BF#68; PLAN.md 3.3 and 3.4 of tracks/look).

A look stands the wrist camera inside a viewpoint boxel, a FREE_SPACE boxel of
the registry, at a pose this module chooses.  The choice is P5 of the plan, in
two stages, with no randomness:

  stage 1 (analytic, no rendering): positions on a lattice inside the boxel,
    clipped to the camera band, plus the point over the goal projected into
    the boxel; per position the orientations at the declared tilts and wrist
    yaws, and the orientation aimed at the goal's centre (LOOK_AT_CENTRE).
    Candidates the arm cannot reach (the planner's own envelope, ``reachable``)
    are dropped here, so the stage 2 tries go to reachable ones.  Each
    candidate is scored by projecting the goal's own ray endpoints into the
    camera and testing the believed boxes in front of them.
  stage 2 (the executor's rule): the best LOOK_TRIES candidates in score
    order get IK, a collision check and one wrist render in the plan twin; the
    first whose render shows the goal passes.  That one render then names
    every region and object the view covers (the static facts below).

The facts, for each certified configuration q inside viewpoint boxel v:
  (Config q) (config_for_boxel q v)
  (reveals q r)             r's ray endpoints (a region) or lattice (an
                            object) are in the frame and not hidden by the
                            robot or a support, up to the sense tolerance
  (blocks_look_at x b q r)  a registered body x, standing at boxel b, hides
                            part of that view: now (b is its own boxel) or
                            were it placed at an on-surface free cell b

Nothing here reads the executing world: the twin's bodies stand where the
belief puts them (BoxelTestEnv.sync_to_plan_client with the registry).
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

import robot_utils
from boxel_data import BoxelType
from observe_views import (LOOK_IMAGE_MARGIN_PX, _quat, lattice, look_at_pose,
                           wrist_render)
from perception import (SENSE_MARGINAL_BLOCKED_FRACTION,
                        first_surface_interceptors, project_points_to_pixels,
                        segment_aabb_hit_mask, sense_ray_slices)
from streams import RobotConfig

# Declared before measuring (PLAN.md 3.4).
LOOK_TILTS = (0.0, math.radians(20.0), math.radians(35.0))   # from straight down
LOOK_YAWS = (0.0, math.pi / 2.0)             # the wrist's roll, as M8's looks
# Declared before the third smoke (the second showed the tilt set cannot look at a
# 0.45 m tall region from a camera held under the 0.45 m band): per position also the
# orientation aimed at the centre of the goal, at both yaws; a position straight over
# the centre adds nothing (that is tilt 0).
LOOK_AT_CENTRE = True
LOOK_LATTICE_FRACTIONS = (0.25, 0.75)        # per axis of the clipped boxel
LOOK_INSET_M = 0.015                         # a pose stays this far inside its boxel
LOOK_BAND_CLEARANCE_M = 0.12                 # over the highest believed body near it
LOOK_BAND_NEAR_M = 0.10                      # what "near" means for that rule
LOOK_BAND_TOP_M = 0.45                       # over the table
LOOK_TRIES = 3                               # stage 2 attempts per (goal, boxel)
LOOK_BOXELS_PER_GOAL = 2                     # distinct viewpoints that reveal a goal
LOOK_BOXELS_RANKED = 4                       # boxels tried per goal to get there
LOOK_BOXEL_TOL_M = 0.01                      # the executor's inflation of the boxel
LOOK_TOL_REGION = SENSE_MARGINAL_BLOCKED_FRACTION
LOOK_TOL_OBJECT = 0.0
# Declared before measuring (PLAN.md 11.13, after the development run of
# 2026-11-13, seed 100).  An object's look goal is its believed box grown in x
# and y by its pose radius; a radius that is not finite, or beyond this cap
# (the gripper's half opening), counts as the cap.
LOOK_OBJECT_GROW_MAX_M = 0.04
# Two camera poses are one view when their positions lie this close and their
# optical axes this near (LookViews.refute).
LOOK_SAME_VIEW_M = 0.01
LOOK_SAME_VIEW_RAD = math.radians(2.0)

_FOV_V_HALF_TAN = 240.0 / 525.0              # the wrist camera, robot_utils


def camera_pose(position, tilt: float, yaw: float, toward_xy) -> np.ndarray:
    """The 4 x 4 wrist-camera pose at ``position``: the optical axis tilted
    ``tilt`` from straight down toward ``toward_xy``, rolled ``yaw`` about it.
    tilt 0 and yaw 0 is observe_views.look_configs' pose."""
    pos = np.asarray(position, dtype=float)
    d = np.asarray(toward_xy, dtype=float)[:2] - pos[:2]
    az = math.atan2(d[1], d[0]) if float(np.hypot(d[0], d[1])) > 1e-3 else 0.0
    f = np.array([math.sin(tilt) * math.cos(az), math.sin(tilt) * math.sin(az),
                  -math.cos(tilt)])
    a = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    x = a - float(a @ f) * f
    x = x / np.linalg.norm(x)
    cam = np.eye(4)
    cam[:3, :3] = np.column_stack([x, np.cross(f, x), f])
    cam[:3, 3] = pos
    return cam


@dataclass
class LookGoal:
    """A region a look may hypothesise a target in, or an object whose pose a
    look may re-measure."""
    id: str
    kind: str                       # 'region' or 'object'
    lo: np.ndarray
    hi: np.ndarray
    slices: List[np.ndarray]        # ray endpoints, one array per slice
    tol: float                      # the blocked fraction a view may lose
    margin_px: int                  # the image margin an endpoint needs
    probe: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))

    @property
    def centre(self) -> np.ndarray:
        return (self.lo + self.hi) / 2.0


def config_name(goal_id: str, boxel_id: str, q) -> str:
    """look_<goal>_<boxel>_<digest of the joints>.  A RobotConfig is compared
    and hashed by its name (streams.RobotConfig), and the configuration the
    arm stands in keeps its name over plan calls.  A name numbered within one
    plan call can therefore come back in the next call on other joints, and
    the planner then takes the new configuration for the one the arm is in:
    no move, and the look runs from the old pose (development run of
    2026-11-13, seed 103, track/look c3d0375).  With the joints in the name,
    equal names are equal configurations."""
    joints = np.round(np.asarray(q, dtype=float), 6) + 0.0      # no negative zero
    return f"look_{goal_id}_{boxel_id}_{hashlib.sha1(joints.tobytes()).hexdigest()[:8]}"


def _corners_and_centre(lo, hi) -> np.ndarray:
    pts = [[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1])
           for z in (lo[2], hi[2])]
    pts.append(((np.asarray(lo) + np.asarray(hi)) / 2.0).tolist())
    return np.array(pts, dtype=float)


def region_goal(boxel) -> LookGoal:
    lo = np.asarray(boxel.min_corner, dtype=float)
    hi = np.asarray(boxel.max_corner, dtype=float)
    slices, _ = sense_ray_slices(lo, hi)
    return LookGoal(boxel.id, 'region', lo, hi, [s.points for s in slices],
                    LOOK_TOL_REGION, 0, _corners_and_centre(lo, hi))


def object_goal(boxel) -> LookGoal:
    """The believed box grown in x and y by the pose radius: a view of the
    goal holds the body wherever the belief allows it.  A body registered on
    a sliver (a look past the edge of a block) has a box that the same view
    sees whole by construction; the body it belongs to may reach behind the
    block (PLAN.md 11.13)."""
    lo = np.array(boxel.min_corner, dtype=float)
    hi = np.array(boxel.max_corner, dtype=float)
    r = float(getattr(boxel, 'pose_radius', 0.0))
    grow = (LOOK_OBJECT_GROW_MAX_M if not math.isfinite(r)
            else min(max(r, 0.0), LOOK_OBJECT_GROW_MAX_M))
    lo[:2] -= grow
    hi[:2] += grow
    return LookGoal(boxel.id, 'object', lo, hi, [lattice(lo, hi)],
                    LOOK_TOL_OBJECT, LOOK_IMAGE_MARGIN_PX,
                    _corners_and_centre(lo, hi))


def _overlaps(lo_a, hi_a, lo_b, hi_b) -> bool:
    return bool(np.all(np.asarray(lo_a) <= np.asarray(hi_b))
                and np.all(np.asarray(hi_a) >= np.asarray(lo_b)))


@dataclass
class Reveal:
    """What one view shows of one goal: whether it reveals it (the hard
    losses are within the tolerance) and which registered bodies hide part of
    it, so a plan may clear them first."""
    hard_frac: float
    total_frac: float
    revealed: bool
    blockers: List[str]


@dataclass
class Cert:
    """A certified look configuration."""
    config: RobotConfig
    boxel: str
    goal: Optional[str]
    reveals: Dict[str, Reveal]
    camera: np.ndarray


class LookViews:
    """The static look facts of one plan call, computed in the plan twin."""

    def __init__(self, views, reachable: Optional[Callable] = None):
        self.views = views                       # observe_views.ObserveViews
        self.env = views.env
        self.client = views.client
        self.robot = views.robot
        self.reachable = reachable               # callable(ee xyz) -> bool
        self.last_stats: Dict[str, object] = {}
        self.last_certs: List[Cert] = []
        # {goal id: camera poses whose executed image did not give its pose}
        self.refuted: Dict[str, List[np.ndarray]] = {}

    # ----- views the executor's image refuted -----------------------------

    def refute(self, goal_id: str, q) -> None:
        """The executor's image from joint positions ``q`` did not give
        ``goal_id``'s pose: that view no longer counts as revealing it, until
        forget().  The counterpart of the centred look removing its own
        configuration (PLAN.md 11.13)."""
        self.refuted.setdefault(str(goal_id), []).append(self._camera_pose_at(q))

    def forget(self, goal_id: str) -> None:
        """The body was re-registered or re-posed: its views count again."""
        self.refuted.pop(str(goal_id), None)

    def _is_refuted(self, goal_id: str, cam) -> bool:
        for old in self.refuted.get(str(goal_id), ()):
            if (float(np.linalg.norm(cam[:3, 3] - old[:3, 3])) <= LOOK_SAME_VIEW_M
                    and float(cam[:3, 2] @ old[:3, 2]) >= math.cos(LOOK_SAME_VIEW_RAD)):
                return True
        return False

    def _withdraw(self, reveals: Dict[str, Reveal], cam) -> None:
        """A refuted view does not reveal the goal it failed on."""
        for gid, rv in list(reveals.items()):
            if rv.revealed and self._is_refuted(gid, cam):
                reveals[gid] = Reveal(rv.hard_frac, rv.total_frac, False, [])
                self.last_stats['refuted'] = int(self.last_stats.get('refuted', 0)) + 1

    # ----- the render's rule ----------------------------------------------

    def _evaluate(self, goal: LookGoal, depth_m, seg, view, proj,
                  movable: Dict[int, str], content: Iterable[int]) -> Reveal:
        """The executor's own render rule for one goal: an endpoint is lost
        when it is outside the frame (or the margin) or a surface other than
        a registered body stands in front of it; a registered body in front
        is a blocker (a plan may relocate it); the goal's own content is
        seen.  The worst slice decides, as sense_shadow_from_render does."""
        h, w = np.asarray(depth_m).shape
        content = set(content)
        worst_hard = worst_total = 0.0
        counts: Dict[int, int] = {}
        needed: set = set()
        per_slice = []
        for pts in goal.slices:
            n = len(pts)
            rows, cols, _d, in_view = project_points_to_pixels(pts, view, proj, w, h)
            m = goal.margin_px
            inside = in_view.copy()
            if m:
                inside &= ((rows >= m) & (cols >= m)
                           & (rows <= h - 1 - m) & (cols <= w - 1 - m))
            icp, hids, _ = first_surface_interceptors(pts, depth_m, seg, view, proj)
            hard = ~inside
            mov = np.zeros(n, dtype=bool)
            slice_counts: Dict[int, int] = {}
            for i in np.nonzero(inside & icp)[0]:
                hid = int(hids[i])
                if hid in content:
                    continue
                if hid in movable:
                    mov[i] = True
                    slice_counts[hid] = slice_counts.get(hid, 0) + 1
                else:
                    hard[i] = True
            n_hard = int(np.count_nonzero(hard))
            n_mov = int(np.count_nonzero(mov))
            worst_hard = max(worst_hard, n_hard / n)
            worst_total = max(worst_total, (n_hard + n_mov) / n)
            per_slice.append((n, n_hard, n_mov, slice_counts))
        revealed = worst_hard <= goal.tol
        if revealed and worst_total > goal.tol:
            # The census rule (compute_shadow_blockers): list a body only as
            # far as removing it is needed to bring the slice under tolerance.
            for n, n_hard, n_mov, slice_counts in per_slice:
                remaining = n_hard + n_mov
                if remaining / n <= goal.tol:
                    continue
                for hid, cnt in sorted(slice_counts.items(), key=lambda kv: -kv[1]):
                    needed.add(hid)
                    remaining -= cnt
                    if remaining / n <= goal.tol:
                        break
        return Reveal(worst_hard, worst_total, revealed,
                      sorted(movable[b] for b in needed))

    def _probe(self, goal: LookGoal, cam_pos, view, proj, boxes,
               full: bool) -> Tuple[float, float]:
        """Stage 1's analytic rule: (hard fraction, total fraction) from the
        projection and the believed boxes alone.  ``boxes`` are the
        registered bodies; the goal's own content does not hide it: for a
        region every body that overlaps it, for an object the body itself
        (the render's rule, _content)."""
        h, w = robot_utils.WRIST_CAMERA_HEIGHT, robot_utils.WRIST_CAMERA_WIDTH
        slices = goal.slices if full else [goal.probe]
        worst_hard = worst_total = 0.0
        for pts in slices:
            rows, cols, _d, in_view = project_points_to_pixels(pts, view, proj, w, h)
            m = goal.margin_px
            inside = in_view.copy()
            if m:
                inside &= ((rows >= m) & (cols >= m)
                           & (rows <= h - 1 - m) & (cols <= w - 1 - m))
            hit = np.zeros(len(pts), dtype=bool)
            for bid, lo, hi in boxes:
                own = (bid == goal.id if goal.kind == 'object'
                       else _overlaps(lo, hi, goal.lo, goal.hi))
                if own:
                    continue
                hit |= segment_aabb_hit_mask(cam_pos, pts, lo, hi)
            n = len(pts)
            worst_hard = max(worst_hard, float(np.count_nonzero(~inside)) / n)
            worst_total = max(worst_total,
                              float(np.count_nonzero(~inside | hit)) / n)
        return worst_hard, worst_total

    # ----- the plan twin --------------------------------------------------

    def _movable(self, registry) -> Tuple[Dict[int, str], List[tuple]]:
        """{twin id: boxel id} and [(boxel id, lo, hi)] of the registered
        bodies: what stands in front of a view and may be relocated."""
        ids, boxes = {}, []
        for bd in registry.get_boxels_by_type(BoxelType.OBJECT):
            name = bd.object_name or bd.id
            tid = self.views._twin_id(name)
            if tid is None:
                continue
            ids[tid] = bd.id
            boxes.append((bd.id, np.asarray(bd.min_corner, dtype=float),
                          np.asarray(bd.max_corner, dtype=float)))
        return ids, boxes

    def _floor_at(self, xy, boxes, table_z: float) -> float:
        z = table_z
        for _bid, lo, hi in boxes:
            if (lo[0] - LOOK_BAND_NEAR_M <= xy[0] <= hi[0] + LOOK_BAND_NEAR_M
                    and lo[1] - LOOK_BAND_NEAR_M <= xy[1] <= hi[1] + LOOK_BAND_NEAR_M):
                z = max(z, float(hi[2]))
        return z

    def _ideal_height(self, goal: LookGoal) -> float:
        """Standoff over the goal's top that frames its larger side."""
        ext = goal.hi - goal.lo
        half = 0.5 * float(max(ext[0], ext[1]))
        return float(np.clip(1.15 * half / _FOV_V_HALF_TAN + 0.03, 0.18, 0.40))

    def _positions(self, goal: LookGoal, v, boxes, table_z: float) -> List[np.ndarray]:
        lo = np.asarray(v.min_corner, dtype=float)
        hi = np.asarray(v.max_corner, dtype=float)
        ilo = lo[:2] + np.where(hi[:2] - lo[:2] > 2 * LOOK_INSET_M, LOOK_INSET_M, 0.0)
        ihi = hi[:2] - np.where(hi[:2] - lo[:2] > 2 * LOOK_INSET_M, LOOK_INSET_M, 0.0)
        z_top = table_z + LOOK_BAND_TOP_M
        out: List[np.ndarray] = []

        def levels(xy, ideal: bool):
            z_lo = max(float(lo[2]), self._floor_at(xy, boxes, table_z) + LOOK_BAND_CLEARANCE_M)
            z_hi = min(float(hi[2]), z_top)
            if z_hi < z_lo:
                return []
            if ideal:
                return [float(np.clip(float(goal.hi[2]) + self._ideal_height(goal), z_lo, z_hi))]
            if z_hi - z_lo < 0.02:
                return [(z_lo + z_hi) / 2.0]
            return [z_lo + f * (z_hi - z_lo) for f in LOOK_LATTICE_FRACTIONS]

        for fx in LOOK_LATTICE_FRACTIONS:
            for fy in LOOK_LATTICE_FRACTIONS:
                xy = ilo + np.array([fx, fy]) * (ihi - ilo)
                if np.all(ihi - ilo < 1e-9):
                    xy = (ilo + ihi) / 2.0
                for z in levels(xy, False):
                    out.append(np.array([xy[0], xy[1], z]))
        xy = np.clip(goal.centre[:2], ilo, ihi)
        for z in levels(xy, True):
            out.append(np.array([xy[0], xy[1], z]))
        # Boxels thinner than a lattice step collapse onto the same points.
        uniq, seen = [], set()
        for pnt in out:
            key = tuple(np.round(pnt, 4))
            if key not in seen:
                seen.add(key)
                uniq.append(pnt)
        return uniq

    def _candidates(self, goal: LookGoal, v, boxes, table_z: float):
        """Stage 1: the candidate poses of one (goal, boxel) pair, as camera
        poses.  Tilt 0 is one pose per yaw whatever the azimuth; the pose aimed
        at the goal's centre follows each position's tilted ones."""
        cands = []
        centre = np.asarray(goal.centre, dtype=float)
        for pos in self._positions(goal, v, boxes, table_z):
            for tilt in LOOK_TILTS:
                for yaw in LOOK_YAWS:
                    cands.append(camera_pose(pos, tilt, yaw, goal.centre[:2]))
            if LOOK_AT_CENTRE and float(np.hypot(*(pos[:2] - centre[:2]))) > 1e-3:
                for yaw in LOOK_YAWS:
                    cands.append(look_at_pose(pos, centre, yaw))
        return cands

    def _reachable_cam(self, cam, ee_inv) -> bool:
        """The planner's reach envelope for the hand that carries ``cam``."""
        if self.reachable is None:
            return True
        return bool(self.reachable((cam @ ee_inv)[:3, 3]))

    def _score(self, cam, goal: LookGoal, others: Sequence[LookGoal], boxes,
               here: np.ndarray):
        view, proj = robot_utils.wrist_camera_matrices(cam)
        hard, total = self._probe(goal, cam[:3, 3], view, proj, boxes, True)
        n_reg = n_obj = 0
        for g in others:
            ph, pt = self._probe(g, cam[:3, 3], view, proj, boxes, False)
            if ph <= g.tol and pt <= g.tol:
                if g.kind == 'region':
                    n_reg += 1
                else:
                    n_obj += 1
        dist = float(np.linalg.norm(cam[:3, 3] - here))
        key = (hard <= goal.tol, total <= goal.tol, -round(total, 2),
               n_reg, n_obj, -round(dist, 2))
        return key, hard <= goal.tol

    def _camera_in(self, cam_xyz, v, tol: float) -> bool:
        lo = np.asarray(v.min_corner, dtype=float) - tol
        hi = np.asarray(v.max_corner, dtype=float) + tol
        return bool(np.all(cam_xyz >= lo) and np.all(cam_xyz <= hi))

    def _render_at(self, q) -> Tuple[np.ndarray, tuple]:
        self.views._set_arm(q)
        t0 = time.perf_counter()
        cam, _buf, depth_m, seg, view, proj = wrist_render(self.client, self.robot)
        self.last_stats['twin_render_s'] += time.perf_counter() - t0
        self.last_stats['twin_renders'] += 1
        return cam, (depth_m, seg, view, proj)

    @staticmethod
    def _content(goal: LookGoal, movable: Dict[int, str], registry) -> List[int]:
        """Twin ids of the registered bodies that are the goal's own content:
        the object itself, or a body standing inside the region.  A view sees
        them; they do not hide it."""
        out = []
        for tid, bid in movable.items():
            if goal.kind == 'object':
                inside = bid == goal.id
            else:
                bd = registry.get_boxel(bid)
                inside = _overlaps(bd.min_corner, bd.max_corner, goal.lo, goal.hi)
            if inside:
                out.append(tid)
        return out

    def _statuses(self, goals, render, movable, registry) -> Dict[str, Reveal]:
        depth_m, seg, view, proj = render
        out = {}
        for g in goals:
            content = self._content(g, movable, registry)
            mov = {t: b for t, b in movable.items() if t not in content}
            out[g.id] = self._evaluate(g, depth_m, seg, view, proj, mov, content)
        return out

    def _certify(self, cam, goal: LookGoal, v, goals, movable, registry,
                 require_clear: bool = False) -> Optional[Cert]:
        """Stage 2 for one candidate pose: IK, collision, one render.
        ``require_clear``: the goal already has a clear view, so a further
        viewpoint is only worth having if it is clear too.  The
        configuration is named after its joints (config_name)."""
        ee = cam @ np.linalg.inv(self.views._ee_to_camera())
        if self.reachable is not None and not self.reachable(ee[:3, 3]):
            self.last_stats['unreachable'] += 1
            return None
        q = robot_utils.solve_ik(self.robot, ee[:3, 3], _quat(ee[:3, :3]),
                                 physics_client=self.client)
        self.last_stats['look_ik'] += 1
        if q is None:
            self.last_stats['ik_fail'] += 1
            return None
        if not robot_utils.is_config_collision_free(
                self.robot, q, physics_client=self.client, log_collisions=False):
            self.last_stats['collide'] += 1
            return None
        cam_real, render = self._render_at(q)
        if not self._camera_in(cam_real[:3, 3], v, LOOK_BOXEL_TOL_M / 2.0):
            self.last_stats['left_boxel'] += 1
            return None
        reveals = self._statuses(goals, render, movable, registry)
        self._withdraw(reveals, cam_real)
        if not reveals[goal.id].revealed or (
                require_clear and reveals[goal.id].total_frac > goal.tol):
            self.last_stats['render_rejected'] += 1
            return None
        return Cert(RobotConfig(joint_positions=np.asarray(q),
                                name=config_name(goal.id, v.id, q)),
                    v.id, goal.id, reveals, cam_real)

    def _free_boxels(self, registry, table_z: float):
        out = []
        for b in registry.get_boxels_by_type(BoxelType.FREE_SPACE):
            if float(b.max_corner[2]) < table_z + LOOK_BAND_CLEARANCE_M:
                continue
            if float(b.min_corner[2]) > table_z + LOOK_BAND_TOP_M:
                continue
            out.append(b)
        return out

    def _rank(self, goal: LookGoal, free, used: set):
        def key(b):
            lo, hi = np.asarray(b.min_corner), np.asarray(b.max_corner)
            d = np.maximum(np.maximum(lo[:2] - goal.centre[:2], goal.centre[:2] - hi[:2]), 0.0)
            vol = float(np.prod(hi - lo))
            return (round(float(np.hypot(d[0], d[1])), 3), -round(vol, 6), b.id)
        return sorted((b for b in free if b.id not in used), key=key)

    # ----- the facts ------------------------------------------------------

    def facts(self, registry, regions, objects, current_config,
              extent_classes: Optional[Dict[tuple, List[str]]] = None,
              place_cells: Optional[Sequence] = None) -> Tuple[List[tuple], Dict]:
        """The static look facts for this plan call (module docstring).
        ``regions``: SHADOW BoxelData a target may be hypothesised in.
        ``objects``: OBJECT BoxelData whose pose a look may re-measure.
        ``extent_classes``: {mm extents: [object ids]} of the bodies a plan may
        relocate; ``place_cells``: the on-surface free BoxelData they may be
        placed at (the placement facts)."""
        self.last_stats = {'twin_render_s': 0.0, 'twin_renders': 0, 'look_ik': 0,
                           'ik_fail': 0, 'collide': 0, 'unreachable': 0,
                           'left_boxel': 0, 'render_rejected': 0, 'refuted': 0,
                           'stage1': 0,
                           'goals': 0, 'certified': 0, 'no_view': [],
                           'placement_facts': 0, 'build_s': 0.0}
        t_start = time.perf_counter()
        table_z = float(self.env.table_surface_height)
        goals: List[LookGoal] = ([region_goal(b) for b in sorted(regions, key=lambda b: b.id)]
                                 + [object_goal(b) for b in sorted(objects, key=lambda b: b.id)])
        self.last_stats['goals'] = len(goals)
        movable, boxes = self._movable(registry)
        saved = self.views._arm()
        certs: List[Cert] = []
        try:
            here_cam = self._camera_at(current_config.joint_positions)
            ee_inv = np.linalg.inv(self.views._ee_to_camera())
            free = self._free_boxels(registry, table_z)
            # The configuration the arm is in: a look from where it stands
            # needs no move.
            cur = self._certify_current(current_config, free, goals, movable, registry)
            if cur is not None:
                certs.append(cur)
            for goal in goals:
                def clear_boxels(goal=goal):
                    return {c.boxel for c in certs
                            if c.reveals[goal.id].revealed
                            and c.reveals[goal.id].total_frac <= goal.tol}
                used = {c.boxel for c in certs if c.reveals[goal.id].revealed}
                others = [g for g in goals if g.id != goal.id]
                tried = 0
                for v in self._rank(goal, free, used):
                    if len(clear_boxels()) >= LOOK_BOXELS_PER_GOAL or tried >= LOOK_BOXELS_RANKED:
                        break
                    tried += 1
                    require_clear = bool(clear_boxels())
                    cands = self._candidates(goal, v, boxes, table_z)
                    self.last_stats['stage1'] += len(cands)
                    scored = []
                    for i, cam in enumerate(cands):
                        if not self._reachable_cam(cam, ee_inv):
                            self.last_stats['unreachable'] += 1     # never reaches stage 2
                            continue
                        key, ok = self._score(cam, goal, others, boxes, here_cam)
                        if ok and (key[1] or not require_clear):
                            scored.append((key, i))
                    scored.sort(key=lambda t: t[0], reverse=True)   # stable: ties keep order
                    got = None
                    for _key, i in scored[:LOOK_TRIES]:
                        got = self._certify(cands[i], goal, v, goals, movable, registry,
                                            require_clear)
                        if got is not None:
                            break
                    if got is not None:
                        certs.append(got)
                if not any(c.reveals[goal.id].revealed for c in certs):
                    self.last_stats['no_view'].append(goal.id)
        finally:
            self.views._set_arm(saved)
        self.last_certs = certs
        self.last_stats['certified'] = len(certs)
        facts = self._facts_of(certs, goals, current_config, registry,
                               extent_classes or {}, place_cells or [])
        self.last_stats['build_s'] = time.perf_counter() - t_start
        return facts, self.last_stats

    def _camera_pose_at(self, q) -> np.ndarray:
        saved = self.views._arm()
        try:
            self.views._set_arm(q)
            return robot_utils.wrist_camera_pose(self.robot, self.client)
        finally:
            self.views._set_arm(saved)

    def _camera_at(self, q) -> np.ndarray:
        return self._camera_pose_at(q)[:3, 3]

    def _certify_current(self, current_config, free, goals, movable, registry):
        cam_real, render = self._render_at(current_config.joint_positions)
        v = next((b for b in free if self._camera_in(cam_real[:3, 3], b, 0.0)), None)
        if v is None:
            return None
        reveals = self._statuses(goals, render, movable, registry)
        self._withdraw(reveals, cam_real)
        if not any(r.revealed for r in reveals.values()):
            return None
        return Cert(current_config, v.id, None, reveals, cam_real)

    def _facts_of(self, certs, goals, current_config, registry, extent_classes,
                  place_cells) -> List[tuple]:
        facts: List[tuple] = []
        goal_by_id = {g.id: g for g in goals}
        for c in certs:
            if c.config is not current_config:
                facts.append(('Config', c.config))
            facts.append(('config_for_boxel', c.config, c.boxel))
            for gid, rv in c.reveals.items():
                if not rv.revealed:
                    continue
                facts.append(('reveals', c.config, gid))
                for x in rv.blockers:
                    facts.append(('blocks_look_at', x, x, c.config, gid))
                g = goal_by_id[gid]
                cam = c.camera[:3, 3]
                for key, members in sorted(extent_classes.items()):
                    ext = np.asarray(key, dtype=float) / 1000.0
                    for cell in place_cells:
                        cx, cy = float(cell.center[0]), float(cell.center[1])
                        floor_z = float(cell.min_corner[2])
                        vmin = np.array([cx - ext[0] / 2.0, cy - ext[1] / 2.0, floor_z])
                        vmax = np.array([cx + ext[0] / 2.0, cy + ext[1] / 2.0, floor_z + ext[2]])
                        if _overlaps(vmin, vmax, g.lo, g.hi):
                            continue
                        if self._placed_blocks(cam, g, vmin, vmax):
                            for x in members:
                                if x != gid:
                                    facts.append(('blocks_look_at', x, cell.id, c.config, gid))
                                    self.last_stats['placement_facts'] += 1
        return facts

    @staticmethod
    def _placed_blocks(cam, goal: LookGoal, vmin, vmax) -> bool:
        """Would a body filling [vmin, vmax] hide more of the goal than the
        view may lose?  Analytic, from the camera position."""
        for pts in goal.slices:
            hits = segment_aabb_hit_mask(cam, pts, vmin, vmax)
            if float(np.count_nonzero(hits)) / len(pts) > goal.tol:
                return True
        return False
