"""
observe_views.py — M8's observation configurations (PLAN_P4_POSE_GRASP_
SAMPLERS.md C0-C2) and the wrist camera's render.

C0: every observation configuration is computed once per _build_init as a
static init fact (the audit #102 boxel_fits pattern: FastDownward sees an
empty set at once and no stream binding can stand by, F7), each with its
own pseudo-boxel VIEW_PREFIX + config name.  Every candidate is judged by
the executor's own render test: the plan twin posed with resetJointState,
one getCameraImage in the plan client, first_surface_interceptors on the
3 x 3 x 3 lattice of the believed box.  The twin's bodies stand where the
belief puts them (sync_to_plan_client), so nothing here reads the
executing world.

C1, sense configurations: per shadow region, in a fixed order, the current
configuration, q_home, then SENSE_RETRACT_POINTS; a candidate passes when
the robot hides at most SENSE_MARGINAL_BLOCKED_FRACTION of every sense
slice of the region in the twin's EYE render.  A region with no passing
candidate falls back to the current configuration.

C2, look configurations: per registered object whose pose is not known,
the wrist camera straight down over the believed centre at each of
LOOK_STANDOFFS above its top, times LOOK_WRIST_YAWS; IK for the hand,
collision-free in the twin, the whole believed box in the twin's WRIST
render with LOOK_IMAGE_MARGIN_PX to spare, and no lattice point hidden by
any other body or by the robot's own fingers.  Path 9 adds look-at poses
(look_candidates): a camera at a horizontal offset from the centre, aimed at
the centre and certified the same way; the default offsets keep the tag's
straight-down looks exactly.
"""

import math
import time
from typing import Dict, List, NamedTuple, Optional, Tuple

import numpy as np
import pybullet as p

from acting import robot_utils
from sensing.perception import (SENSE_MARGINAL_BLOCKED_FRACTION,
                        detect_objects_from_render, first_surface_interceptors,
                        project_points_to_pixels, sense_ray_slices)
from planning.streams import RobotConfig

# The reserved prefix of an observation configuration's pseudo-boxel; no
# registry boxel may carry it (asserted in _build_init, like "home").
VIEW_PREFIX = 'view__'

# C2, declared before measuring (BF#28 used the same values).
LOOK_STANDOFFS = (0.20, 0.30)
# The centred look's hypothesis regions (path 9): a fragment's box is not
# bounded by an object's size, and the wrist camera sees only 1.23 s by 0.91 s
# metres at s metres over a box's top, so one view from 0.20 or 0.30 m cannot
# always hold all of it (the first smoke, seed 0, 2 occluders: regions of 0.27
# by 0.27 m and 0.10 by 0.33 m had no view).  The second smoke showed the
# straight views over the tall 0.27 by 0.27 by 0.45 m shadow need more height
# than the arm has (no_ik from 0.30 m up), so a region is also looked at from
# the side: the camera at a horizontal offset from the box centre, toward the
# robot base or to either side, aimed at the centre (look_candidates).  The
# first CENTRED_REGION_MAX_CONFIGS poses in that order that the twin certifies
# (all of the box in view and unblocked) are kept.  Declared before the third
# smoke.  Pose looks of registered objects keep the tag's straight-down looks
# (LOOK_STANDOFFS, LOOK_OFFSETS).
CENTRED_REGION_STANDOFFS = (0.20, 0.30, 0.40, 0.50)
CENTRED_REGION_OFFSETS = (0.0, 0.15, 0.25, 0.35)
CENTRED_REGION_MAX_CONFIGS = 4
LOOK_OFFSETS = (0.0,)
LOOK_AZIMUTHS = (0.0, math.pi / 2.0, -math.pi / 2.0)    # from the direction toward the base
LOOK_WRIST_YAWS = (0.0, math.pi / 2)
LOOK_IMAGE_MARGIN_PX = 8
# Path 9 (PLAN 11.12, declared 2026-11-12 before any episode ran on it): in a
# look mode a hidden region is cut into cells one look holds.  The smoke of
# that day (seed 0, centred) had no view of the 0.267 by 0.272 m region where
# the target stood: a region is the whole shadow a block casts from the fixed
# camera, and the arm does not reach the heights from which that fits.  The
# share of the image's short side a cell may fill; the rest is for the arm's
# pose error (the IK's orientation tolerance, a few millimetres of position).
LOOK_CELL_SLACK = 0.85

# C1: retracted configurations, top-down, on an arc near the robot base:
# (radius from the base in xy, bearing from the base's +x axis, height
# above the table top).  Declared, scene-independent.
SENSE_RETRACT_POINTS = ((0.30, -math.pi / 3, 0.40),
                        (0.30, 0.0, 0.45),
                        (0.30, math.pi / 3, 0.40))

# Bodies a lattice point may stand behind without the view being blocked.
_SUPPORTS = ("plane", "table")


def view_boxel(config) -> str:
    return VIEW_PREFIX + str(config.name)


def look_cell_side() -> float:
    """The longest side (m) of a region that one look holds from the lowest
    look standoff at either wrist yaw: the image's short side at that distance
    over the region's top, less the certification margin on both edges, times
    LOOK_CELL_SLACK.  It follows from the camera and the look heights; no
    scene enters it."""
    h = robot_utils.WRIST_CAMERA_HEIGHT
    f = (h / 2.0) / math.tan(math.radians(robot_utils.WRIST_CAMERA_FOV_DEG) / 2.0)
    held = 2.0 * min(LOOK_STANDOFFS) * ((h - 1) / 2.0 - LOOK_IMAGE_MARGIN_PX) / f
    return LOOK_CELL_SLACK * held


def look_name(obj: str, k: int) -> str:
    return f"look_{obj}_{k}"


def look_index(config_name: str, obj: str) -> Optional[int]:
    """k of a look configuration named look_<obj>_<k>, else None."""
    head = f"look_{obj}_"
    if not str(config_name).startswith(head):
        return None
    try:
        return int(str(config_name)[len(head):])
    except ValueError:
        return None


def lattice(lo, hi, n: int = 3) -> np.ndarray:
    g = [np.linspace(float(lo[k]), float(hi[k]), n) for k in range(3)]
    return np.array([[x, y, z] for x in g[0] for y in g[1] for z in g[2]])


def look_candidates(standoffs=LOOK_STANDOFFS, offsets=LOOK_OFFSETS,
                    yaws=LOOK_WRIST_YAWS, azimuths=LOOK_AZIMUTHS
                    ) -> List[Tuple[float, float, float, float]]:
    """The camera poses a look tries, as (standoff, offset, azimuth, yaw) in
    the order that numbers them (k is the position in this list): standoffs
    outermost, then offsets, azimuths and wrist yaws.  An offset of 0 is
    straight over the centre and has the one azimuth 0.0; a larger offset is
    tried at every azimuth.  With the default offsets this is the tag's
    (standoff, yaw) order."""
    out = []
    for so in standoffs:
        for off in offsets:
            for az in ((0.0,) if float(off) == 0.0 else azimuths):
                for wy in yaws:
                    out.append((float(so), float(off), float(az), float(wy)))
    return out


def look_at_pose(position, target, yaw: float) -> np.ndarray:
    """The 4 x 4 wrist-camera pose at ``position`` with its optical axis
    through ``target``, rolled so that the image's x axis is the world
    direction (cos yaw, sin yaw, 0) made perpendicular to the axis.  Straight
    over the target (the axis straight down) it is exactly the tag's look
    pose, the construction C2 has always used."""
    pos = np.asarray(position, dtype=float)
    d = np.asarray(target, dtype=float) - pos
    if d[0] == 0.0 and d[1] == 0.0:                     # straight down: the tag's pose
        f = np.array([0.0, 0.0, -1.0])
        x = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    else:
        f = d / float(np.linalg.norm(d))
        a = np.array([math.cos(yaw), math.sin(yaw), 0.0])
        x = a - float(a @ f) * f
        x = x / float(np.linalg.norm(x))
    cam = np.eye(4)
    cam[:3, :3] = np.column_stack([x, np.cross(f, x), f])
    cam[:3, 3] = pos
    return cam


class LookNote(NamedTuple):
    """Why one candidate pose of a look_configs call did or did not pass."""
    k: int
    standoff: float
    offset: float
    azimuth: float
    yaw: float
    verdict: str        # removed | no_ik | collision | frame | blocked | ok
    detail: str = ''


def explain_notes(notes) -> str:
    """One line for a log: how many poses ended in which verdict, with the
    first example of the ones that say why a view fails."""
    if not notes:
        return ''
    by: Dict[str, list] = {}
    for n in notes:
        by.setdefault(n.verdict, []).append(n)
    parts = []
    for v in ('ok', 'blocked', 'frame', 'collision', 'no_ik', 'removed'):
        if v not in by:
            continue
        ex = by[v][0]
        tail = ''
        if v in ('blocked', 'frame'):
            tail = (f", e.g. {ex.standoff:.2f} m up, {ex.offset:.2f} m out at "
                    f"{math.degrees(ex.azimuth):.0f} deg, yaw {math.degrees(ex.yaw):.0f}"
                    f"{': ' + ex.detail if ex.detail else ''}")
        parts.append(f"{len(by[v])} {v}{tail}")
    return f"{len(notes)} poses tried: " + '; '.join(parts)


def _render(client: int, view, proj, width: int, height: int,
            near: float, far: float):
    """One TinyRenderer pass: (depth in metres, seg mask)."""
    _, _, _, depth, seg = p.getCameraImage(
        width=width, height=height, viewMatrix=view, projectionMatrix=proj,
        renderer=p.ER_TINY_RENDERER, physicsClientId=client)
    buf = np.asarray(depth, dtype=float).reshape((height, width))
    depth_m = far * near / (far - (far - near) * buf)
    return buf, depth_m, np.asarray(seg).reshape((height, width))


def wrist_render(client: int, robot_id: int):
    """The wrist camera at the robot's current joints (hand FK times the
    declared mount): (camera pose, raw depth buffer, depth in metres, seg,
    view, proj)."""
    cam = robot_utils.wrist_camera_pose(robot_id, client)
    view, proj = robot_utils.wrist_camera_matrices(cam)
    buf, depth_m, seg = _render(
        client, view, proj, robot_utils.WRIST_CAMERA_WIDTH,
        robot_utils.WRIST_CAMERA_HEIGHT, robot_utils.WRIST_CAMERA_NEAR,
        robot_utils.WRIST_CAMERA_FAR)
    return cam, buf, depth_m, seg, view, proj


def wrist_observation(env, robot_id: int):
    """C2's executor render: the wrist camera in the executing client,
    detections of every registered-or-not task body (the caller decides
    which it uses), the square-footprint completion off (a straight-down
    view sees the whole footprint).  Returns (detections, render) with
    render = (depth_m, seg, view, proj) as refresh_object_aabbs takes it."""
    from console.visualization import (conceal_overlay_for_observation,
                               restore_overlay_after_observation)
    conceal_overlay_for_observation()
    try:
        cam, buf, depth_m, seg, view, proj = wrist_render(env.client_id, robot_id)
    finally:
        restore_overlay_after_observation()
    names = {info.object_id: n for n, info in env.objects.items()
             if n not in ("plane", "table", "robot")}
    dets = detect_objects_from_render(
        seg, buf, view, proj, names, cam[:2, 3], env.table_surface_height,
        no_footprint_completion=frozenset(names.values()))
    return dets, (depth_m, seg, view, proj)


def _quat(r: np.ndarray):
    """Quaternion [x, y, z, w] of a rotation matrix."""
    m = np.asarray(r, dtype=float)
    t = float(np.trace(m))
    if t > 0.0:
        s = math.sqrt(t + 1.0) * 2.0
        return [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s,
                (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    i = int(np.argmax(np.diag(m)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(1.0 + m[i, i] - m[j, j] - m[k, k]) * 2.0
    q = [0.0, 0.0, 0.0, (m[k, j] - m[j, k]) / s]
    q[i] = 0.25 * s
    q[j] = (m[j, i] + m[i, j]) / s
    q[k] = (m[k, i] + m[i, k]) / s
    return q


class ObserveViews:
    """M8's static observation facts, computed in the plan twin."""

    def __init__(self, env, base_xy):
        self.env = env
        self.client = env.plan_client_id
        self.robot = env.plan_robot_id
        self.base_xy = np.asarray(base_xy, dtype=float)[:2]
        # The observe bound (C2): (object, look index) pairs removed by a
        # strike, and objects parked after 3 strikes or with every pair
        # removed.  Owned by the dispatcher, read here.
        self.removed: set = set()
        self.parked: set = set()
        self._t_ee_cam = None
        self._retract_q: Optional[List[Optional[np.ndarray]]] = None
        self.last_stats: Dict[str, float] = {}
        self.last_fallback: List[str] = []
        # Path 9: per look boxel, why each candidate pose of its last
        # look_configs call did or did not pass: LookNote(k, standoff, offset,
        # azimuth, yaw, verdict, detail), verdict removed | no_ik | collision |
        # frame | blocked | ok.
        self.last_look_notes: Dict[str, list] = {}
        # BF#52: sense_view_test's renders of this init, one per
        # configuration name, and its counters (reset by init_facts).
        self._test_renders: Dict[str, tuple] = {}
        self.test_stats: Dict[str, float] = self._fresh_test_stats()

    @staticmethod
    def _fresh_test_stats() -> Dict[str, float]:
        return {'tests': 0, 'passes': 0, 'renders': 0, 'render_s': 0.0}

    # ----- the plan twin ------------------------------------------------

    def _twin_id(self, name: str) -> Optional[int]:
        info = self.env.objects.get(name)
        return None if info is None else self.env._gui_to_plan.get(info.object_id)

    def _arm(self) -> List[float]:
        return [p.getJointState(self.robot, j, physicsClientId=self.client)[0]
                for j in robot_utils.robot_model().arm_joints]

    def _set_arm(self, q) -> None:
        for j, v in zip(robot_utils.robot_model().arm_joints, q):
            p.resetJointState(self.robot, j, float(v), physicsClientId=self.client)

    def _ee_to_camera(self) -> np.ndarray:
        """The fixed transform from the IK link to the wrist camera."""
        if self._t_ee_cam is None:
            s = p.getLinkState(self.robot, robot_utils.robot_model().ee_link,
                               computeForwardKinematics=True,
                               physicsClientId=self.client)
            ee = np.eye(4)
            ee[:3, :3] = np.array(p.getMatrixFromQuaternion(s[5])).reshape(3, 3)
            ee[:3, 3] = s[4]
            self._t_ee_cam = (np.linalg.inv(ee)
                              @ robot_utils.wrist_camera_pose(self.robot, self.client))
        return self._t_ee_cam

    def _blocking_ids(self, own: Optional[str]) -> set:
        """Twin ids whose surface in front of a lattice point blocks it:
        every body but the supports and the object itself (robot
        included)."""
        ids = set()
        for n in self.env.objects:
            if n in _SUPPORTS or n == own:
                continue
            t = self._twin_id(n)
            if t is not None:
                ids.add(t)
        return ids

    # ----- C2 -----------------------------------------------------------

    def _look_target(self, boxel):
        lo = np.asarray(boxel.min_corner, dtype=float)
        hi = np.asarray(boxel.max_corner, dtype=float)
        if getattr(boxel, 'rect_center', None) is not None and \
                getattr(boxel, 'yaw_valid', False):
            cxy = np.asarray(boxel.rect_center, dtype=float)[:2]
        else:
            cxy = (lo[:2] + hi[:2]) / 2.0
        return lo, hi, cxy

    def look_configs(self, boxel, standoffs=None, offsets=None,
                     max_configs=None) -> List[Tuple[int, RobotConfig]]:
        """The passing look configurations of one box, as (k, config).

        The camera poses tried are look_candidates(standoffs, offsets), each
        aimed at the centre of the box.  ``standoffs``: the camera's heights
        over the top of the box; ``offsets``: its horizontal distances from the
        centre (toward the robot base or to either side; 0 is straight over
        it), both in the order tried (None: LOOK_STANDOFFS and LOOK_OFFSETS,
        the tag's straight-down looks).  k counts the candidates in that
        order, so a configuration's name look_<id>_<k> and its strike key
        (id, k) follow the tuples: give a box one pair of tuples and the same
        pair on every call (other tuples would reuse the names).
        ``max_configs``: stop at that many passing configurations (None: try
        every candidate).  Why each candidate tried passed or not is in
        last_look_notes[boxel.id]."""
        standoffs = (LOOK_STANDOFFS if standoffs is None
                     else tuple(float(s) for s in standoffs))
        offsets = (LOOK_OFFSETS if offsets is None
                   else tuple(float(o) for o in offsets))
        lo, hi, cxy = self._look_target(boxel)
        target = np.array([cxy[0], cxy[1], (float(lo[2]) + float(hi[2])) / 2.0])
        to_base = self.base_xy - cxy
        to_base = (to_base / float(np.linalg.norm(to_base))
                   if float(np.linalg.norm(to_base)) > 1e-6 else np.array([1.0, 0.0]))
        pts = lattice(lo, hi)
        blocking = self._blocking_ids(boxel.id)
        t_ee_cam_inv = np.linalg.inv(self._ee_to_camera())
        w, h = robot_utils.WRIST_CAMERA_WIDTH, robot_utils.WRIST_CAMERA_HEIGHT
        m = LOOK_IMAGE_MARGIN_PX
        out = []
        notes: List[LookNote] = []
        self.last_look_notes[boxel.id] = notes
        for k, (so, off, az, wy) in enumerate(look_candidates(standoffs, offsets)):
            if max_configs is not None and len(out) >= max_configs:
                break
            if (boxel.id, k) in self.removed:
                notes.append(LookNote(k, so, off, az, wy, 'removed'))
                continue
            direction = np.array([to_base[0] * math.cos(az) - to_base[1] * math.sin(az),
                                  to_base[0] * math.sin(az) + to_base[1] * math.cos(az)])
            pos = np.array([cxy[0] + off * direction[0], cxy[1] + off * direction[1],
                            float(hi[2]) + so])
            cam = look_at_pose(pos, target, wy)
            ee = cam @ t_ee_cam_inv
            q = robot_utils.solve_ik(self.robot, ee[:3, 3], _quat(ee[:3, :3]),
                                     physics_client=self.client)
            self.last_stats['look_ik'] += 1
            if q is None:
                notes.append(LookNote(k, so, off, az, wy, 'no_ik'))
                continue
            if not robot_utils.is_config_collision_free(
                    self.robot, q, physics_client=self.client,
                    log_collisions=False):
                notes.append(LookNote(k, so, off, az, wy, 'collision'))
                continue
            # The frame test needs the camera only, so it runs before the render
            # (a pose that does not hold the box in view is not rendered).
            self._set_arm(q)
            view, proj = robot_utils.wrist_camera_matrices(
                robot_utils.wrist_camera_pose(self.robot, self.client))
            rows, cols, _, in_view = project_points_to_pixels(pts, view, proj, w, h)
            inside = bool(np.all(in_view) and rows.min() >= m and cols.min() >= m
                          and rows.max() <= h - 1 - m and cols.max() <= w - 1 - m)
            if not inside:
                notes.append(LookNote(
                    k, so, off, az, wy, 'frame',
                    f"rows {rows.min():.0f}..{rows.max():.0f} of {h}, "
                    f"cols {cols.min():.0f}..{cols.max():.0f} of {w}"))
                continue
            t0 = time.perf_counter()
            _, depth_m, seg = _render(
                self.client, view, proj, w, h, robot_utils.WRIST_CAMERA_NEAR,
                robot_utils.WRIST_CAMERA_FAR)
            self.last_stats['twin_render_s'] += time.perf_counter() - t0
            self.last_stats['twin_renders'] += 1
            icp, hids, _ = first_surface_interceptors(pts, depth_m, seg, view, proj)
            hit = icp & np.isin(hids, list(blocking))
            if np.any(hit):
                who = sorted({self._body_name(b) for b in np.asarray(hids)[hit].tolist()})
                notes.append(LookNote(
                    k, so, off, az, wy, 'blocked',
                    f"{int(np.sum(hit))} of {len(pts)} points hidden by {who}"))
            else:
                notes.append(LookNote(k, so, off, az, wy, 'ok'))
                out.append((k, RobotConfig(joint_positions=np.asarray(q),
                                           name=look_name(boxel.id, k))))
        return out

    def _body_name(self, twin_id) -> str:
        """The task body a plan-twin id belongs to (else the id as text)."""
        for n in self.env.objects:
            if self._twin_id(n) == twin_id:
                return n
        return str(twin_id)

    # ----- C1 -----------------------------------------------------------

    def _retract_configs(self) -> List[Optional[np.ndarray]]:
        if self._retract_q is None:
            z0 = float(self.env.table_surface_height)
            self._retract_q = []
            for r, b, dz in SENSE_RETRACT_POINTS:
                xyz = np.array([self.base_xy[0] + r * math.cos(b),
                                self.base_xy[1] + r * math.sin(b), z0 + dz])
                q = robot_utils.solve_ik(self.robot, xyz, physics_client=self.client)
                self._retract_q.append(None if q is None else np.asarray(q))
        return self._retract_q

    def _robot_blocked(self, shadow, depth_m, seg, view, proj) -> float:
        """The worst sense slice's fraction of endpoints the robot hides."""
        slices, _ = sense_ray_slices(shadow.min_corner, shadow.max_corner)
        worst = 0.0
        for sl in slices:
            icp, hids, _ = first_surface_interceptors(sl.points, depth_m, seg,
                                                      view, proj)
            worst = max(worst, float(np.count_nonzero(icp & (hids == self.robot)))
                        / max(1, len(sl.points)))
        return worst

    def sense_views(self, shadows, current_config, home_config):
        """{shadow id: [configs]} in the fixed order, plus the ids that fell
        back to the current configuration."""
        env = self.env
        view, proj = env._view_and_projection_matrices()
        cands = [current_config]
        if home_config is not None and home_config != current_config:
            cands.append(home_config)
        retract = [RobotConfig(joint_positions=q, name=f"sense_retract_{k}")
                   for k, q in enumerate(self._retract_configs()) if q is not None]
        passing = {s.id: [] for s in shadows}
        for ci, q in enumerate(cands + retract):
            todo = [s for s in shadows
                    if ci < len(cands) or not passing[s.id]]
            if not todo:
                continue
            if ci >= len(cands) and not robot_utils.is_config_collision_free(
                    self.robot, q.joint_positions, physics_client=self.client,
                    log_collisions=False):
                continue
            self._set_arm(q.joint_positions)
            t0 = time.perf_counter()
            _, depth_m, seg = _render(self.client, view, proj, env.image_width,
                                      env.image_height, env.near_plane,
                                      env.far_plane)
            self.last_stats['twin_render_s'] += time.perf_counter() - t0
            self.last_stats['twin_renders'] += 1
            for s in todo:
                if self._robot_blocked(s, depth_m, seg, view, proj) \
                        <= SENSE_MARGINAL_BLOCKED_FRACTION:
                    passing[s.id].append(q)
        fallback = sorted(sid for sid, qs in passing.items() if not qs)
        for sid in fallback:
            passing[sid].append(current_config)
        return passing, fallback

    def sense_view_test(self, q, shadow) -> bool:
        """BF#52, the fold's rule (pddlstream_planner.over_region_facts):
        at ``q`` the robot hides at most SENSE_MARGINAL_BLOCKED_FRACTION of
        every sense slice of ``shadow`` in the twin's EYE render (C1's rule
        on any configuration).  One render per configuration name per init,
        the twin's bodies as the last _build_init left them; the arm is put
        back after."""
        key = str(getattr(q, 'name', q))
        rend = self._test_renders.get(key)
        if rend is None:
            env = self.env
            view, proj = env._view_and_projection_matrices()
            saved = self._arm()
            try:
                self._set_arm(q.joint_positions)
                t0 = time.perf_counter()
                _, depth_m, seg = _render(self.client, view, proj, env.image_width,
                                          env.image_height, env.near_plane,
                                          env.far_plane)
                self.test_stats['render_s'] += time.perf_counter() - t0
                self.test_stats['renders'] += 1
            finally:
                self._set_arm(saved)
            rend = (depth_m, seg, view, proj)
            self._test_renders[key] = rend
        ok = self._robot_blocked(shadow, *rend) <= SENSE_MARGINAL_BLOCKED_FRACTION
        self.test_stats['tests'] += 1
        self.test_stats['passes'] += int(ok)
        return ok

    # ----- init facts ---------------------------------------------------

    def init_facts(self, current_config, home_config, shadows, look_boxels,
                   declared_configs, standoffs=None, offsets=None,
                   max_configs=None) -> Tuple[List[tuple], set]:
        """The static M8 facts and the view pseudo-boxel ids.
        ``declared_configs``: configs init already declares (Config q).
        ``standoffs``, ``offsets``, ``max_configs``: optional {boxel id: value}
        for the look configurations of those boxes (see look_configs); a box
        not in a dict keeps the default (LOOK_STANDOFFS, LOOK_OFFSETS, no
        cap)."""
        self.last_stats = {'twin_render_s': 0.0, 'twin_renders': 0,
                           'look_ik': 0, 'sense_view': 0, 'look_config': 0,
                           'sense_fallback': 0}
        self.last_fallback = []
        self.last_look_notes = {}
        self._test_renders = {}                 # BF#52: a new twin state
        self.test_stats = self._fresh_test_stats()
        saved = self._arm()
        facts: List[tuple] = []
        configs = {}
        try:
            if shadows:
                passing, fallback = self.sense_views(shadows, current_config,
                                                     home_config)
                self.last_stats['sense_fallback'] = len(fallback)
                self.last_fallback = fallback
                for sid, qs in passing.items():
                    for q in qs:
                        configs[q.name] = q
                        facts.append(('sense_view', q, sid))
                        self.last_stats['sense_view'] += 1
            for b in look_boxels:
                if b.id in self.parked:
                    continue
                for _, q in self.look_configs(b, (standoffs or {}).get(b.id),
                                              (offsets or {}).get(b.id),
                                              (max_configs or {}).get(b.id)):
                    configs[q.name] = q
                    facts.append(('look_config', q, b.id))
                    self.last_stats['look_config'] += 1
        finally:
            self._set_arm(saved)
        if home_config is not None:
            configs.setdefault(home_config.name, home_config)
        view_ids = set()
        declared = {q.name for q in declared_configs}
        for name, q in sorted(configs.items()):
            if name not in declared:
                facts.append(('Config', q))
            v = view_boxel(q)
            view_ids.add(v)
            facts += [('Boxel', v), ('is_view', v), ('config_for_boxel', q, v)]
        return facts, view_ids
