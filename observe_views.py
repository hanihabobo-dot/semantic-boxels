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
any other body or by the robot's own fingers.
"""

import math
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pybullet as p

import robot_utils
from perception import (SENSE_MARGINAL_BLOCKED_FRACTION,
                        detect_objects_from_render, first_surface_interceptors,
                        project_points_to_pixels, sense_ray_slices)
from streams import RobotConfig

# The reserved prefix of an observation configuration's pseudo-boxel; no
# registry boxel may carry it (asserted in _build_init, like "home").
VIEW_PREFIX = 'view__'

# C2, declared before measuring (BF#28 used the same values).
LOOK_STANDOFFS = (0.20, 0.30)
LOOK_WRIST_YAWS = (0.0, math.pi / 2)
LOOK_IMAGE_MARGIN_PX = 8

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
    from visualization import (conceal_overlay_for_observation,
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

    def look_configs(self, boxel) -> List[Tuple[int, RobotConfig]]:
        """The passing look configurations of one object, as (k, config)."""
        lo, hi, cxy = self._look_target(boxel)
        pts = lattice(lo, hi)
        blocking = self._blocking_ids(boxel.id)
        t_ee_cam_inv = np.linalg.inv(self._ee_to_camera())
        w, h = robot_utils.WRIST_CAMERA_WIDTH, robot_utils.WRIST_CAMERA_HEIGHT
        m = LOOK_IMAGE_MARGIN_PX
        out = []
        k = -1
        for so in LOOK_STANDOFFS:
            for wy in LOOK_WRIST_YAWS:
                k += 1
                if (boxel.id, k) in self.removed:
                    continue
                cam = np.eye(4)
                z = np.array([0.0, 0.0, -1.0])
                x = np.array([math.cos(wy), math.sin(wy), 0.0])
                cam[:3, :3] = np.column_stack([x, np.cross(z, x), z])
                cam[:3, 3] = (cxy[0], cxy[1], float(hi[2]) + so)
                ee = cam @ t_ee_cam_inv
                q = robot_utils.solve_ik(self.robot, ee[:3, 3], _quat(ee[:3, :3]),
                                         physics_client=self.client)
                self.last_stats['look_ik'] += 1
                if q is None:
                    continue
                if not robot_utils.is_config_collision_free(
                        self.robot, q, physics_client=self.client,
                        log_collisions=False):
                    continue
                self._set_arm(q)
                t0 = time.perf_counter()
                _, _, depth_m, seg, view, proj = wrist_render(self.client, self.robot)
                self.last_stats['twin_render_s'] += time.perf_counter() - t0
                self.last_stats['twin_renders'] += 1
                rows, cols, _, in_view = project_points_to_pixels(pts, view, proj, w, h)
                inside = bool(np.all(in_view) and rows.min() >= m and cols.min() >= m
                              and rows.max() <= h - 1 - m and cols.max() <= w - 1 - m)
                icp, hids, _ = first_surface_interceptors(pts, depth_m, seg, view, proj)
                if inside and not np.any(icp & np.isin(hids, list(blocking))):
                    out.append((k, RobotConfig(joint_positions=np.asarray(q),
                                               name=look_name(boxel.id, k))))
        return out

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
                   declared_configs) -> Tuple[List[tuple], set]:
        """The static M8 facts and the view pseudo-boxel ids.
        ``declared_configs``: configs init already declares (Config q)."""
        self.last_stats = {'twin_render_s': 0.0, 'twin_renders': 0,
                           'look_ik': 0, 'sense_view': 0, 'look_config': 0,
                           'sense_fallback': 0}
        self.last_fallback = []
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
                for _, q in self.look_configs(b):
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
