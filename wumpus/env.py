"""The 3-D Wumpus env: a PyBullet scene, a mobile Panda with a head camera.

Axis convention: cell p<i>-<j> spans x in [(i-1)s, i*s], y in [(j-1)s, j*s],
floor at z = 0 (x grows with i, y with j).  Cell centre ((i-.5)s, (j-.5)s).

Robot: a box chassis (0.56 x 0.56 x 0.40 m, floor clearance 0.02 m) with the
Panda on its top at the chassis centre, and a mast on the west edge with a
boom that carries the head camera 1.78 m over the floor, straight above the
chassis centre, looking straight down.  The base is holonomic and driven
KINEMATICALLY in 2.5 cm steps (the pose of the chassis and of the arm's
fixed base are reset together, a physics step after each); it never turns
(yaw 0).  The chassis has no collision shape: nothing blocks it, deaths are
decided by the cell it drives into (see move).

Percepts are physical markers (breeze: light blue tile in the NW quadrant,
stench: green tile in the NE quadrant, glitter: the gold bar on its pedestal
in the SE quadrant) read from the head camera by perception.
detect_objects_from_render.  The camera sees only its own cell (see
WumpusEnv.footprint_half).  Nothing that decides an action may read truth().
"""
import math
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pybullet as p
import pybullet_data

import perception
import robot_utils
from boxel_data import BoxelData, BoxelRegistry, BoxelType

from wumpus.world import WumpusWorld, cell_ij, cell_name

# ---- layout (metres; offsets from the cell centre, scaled by the cell size) ----
CHASSIS_HALF = 0.28
CHASSIS_Z0, CHASSIS_Z1 = 0.02, 0.42
CAM_Z = 1.78                       # eye height over the floor
MAST_XY = (-0.25, 0.0)
BREEZE_OFF = (-0.38, 0.38)
STENCH_OFF = (0.38, 0.38)
GOLD_OFF = (0.38, -0.38)
MARKER_SIDE, MARKER_THICK = 0.12, 0.004
PEDESTAL_HALF, PEDESTAL_H = 0.07, 0.10
BAR_SIZE = (0.10, 0.025, 0.025)    # x, y, z of the bar
BAR_MASS = 0.05
WUMPUS_SIZE = (0.4, 0.4, 0.6)
CELL_HEIGHT = 1.5
SHAFT_DEPTH = 1.5
FOOTPRINT_FRACTION = 0.48          # camera footprint half-width at the floor, in cell sizes
IMG = 192
MIN_PIXELS = 40                    # a percept body needs this many pixels
DRIVE_STEP = 0.025
ARRIVE_POS_TOL, ARRIVE_YAW_TOL_DEG = 0.02, 2.0

# arm stowed (folded toward the south, clear of the markers' lines of sight)
STOW_Q = np.array([-math.pi / 2, -0.4, 0.0, -2.6, 0.0, 2.2, 0.785])
# IK seeds for the grasp: the Panda's default rest pose has no solution this
# low and close to its own mount (the gold lies 0.54 m from the base axis,
# 0.3 m below the shoulder), so the IK starts from reach-down seeds.
GRASP_SEEDS = ([-0.78, 0.5, 0, -1.8, 0, 2.3, 0.785], [-0.78, 0.7, 0, -1.0, 0, 1.7, 0.785],
               list(STOW_Q))
GRASP_QUAT_DOWN = p.getQuaternionFromEuler([0, math.pi, 0])


class WumpusEnv:
    def __init__(self, world: WumpusWorld, gui: bool = False, cell_size: float = 1.0,
                 save_dir: Optional[str] = None, real_time: Optional[bool] = None):
        self.world = world
        self.s = float(cell_size)
        self.gui = bool(gui)
        self.save_dir = save_dir
        self.realtime = self.gui if real_time is None else real_time
        self.dead: Optional[str] = None
        self.held = False
        self.sim_steps = 0
        self.cid = p.connect(p.GUI if gui else p.DIRECT)
        c = self.cid
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=c)
        p.setGravity(0, 0, -9.81, physicsClientId=c)
        p.setPhysicsEngineParameter(numSolverIterations=robot_utils.SOLVER_ITERATIONS,
                                    physicsClientId=c)
        if gui:
            p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0, physicsClientId=c)
        self._cells = world.cells()
        self.registry = BoxelRegistry()
        self._build_registry()
        # body bookkeeping: id -> (kind, cell)
        self.bodies: Dict[int, Tuple[str, str]] = {}
        self.floor_tile: Dict[str, int] = {}
        self._build_scene()
        self._build_robot()
        self._label_ids: List[int] = []
        self._stamp_knowledge = None
        if gui:
            half = self.world.n * self.s / 2
            p.resetDebugVisualizerCamera(cameraDistance=1.5 * self.world.n * self.s + 2,
                                         cameraYaw=0, cameraPitch=-60,
                                         cameraTargetPosition=[half, half, 0],
                                         physicsClientId=c)
        for _ in range(60):          # let the bar settle on its pedestal
            self._tick()

    # ------------------------------------------------------------ geometry
    def cell_center(self, cell: str) -> np.ndarray:
        i, j = cell_ij(cell)
        return np.array([(i - 0.5) * self.s, (j - 0.5) * self.s])

    def cell_of_xy(self, x: float, y: float) -> Optional[str]:
        i, j = int(math.floor(x / self.s)) + 1, int(math.floor(y / self.s)) + 1
        n = self.world.n
        return cell_name(i, j) if 1 <= i <= n and 1 <= j <= n else None

    @property
    def footprint_half(self) -> float:
        return FOOTPRINT_FRACTION * self.s

    def cells(self) -> List[str]:
        return list(self._cells)

    def adjacent(self) -> List[Tuple[str, str]]:
        idx = {c: k for k, c in enumerate(self._cells)}
        out = []
        for a in self._cells:
            for b in self.world.neighbors(a):
                if idx[b] > idx[a]:
                    out += [(a, b), (b, a)]
        return out

    def _build_registry(self):
        s = self.s
        for c in self._cells:
            i, j = cell_ij(c)
            nb = {'x_pos': [], 'x_neg': [], 'y_pos': [], 'y_neg': [], 'z_pos': [], 'z_neg': []}
            n = self.world.n
            if i < n: nb['x_pos'].append(cell_name(i + 1, j))
            if i > 1: nb['x_neg'].append(cell_name(i - 1, j))
            if j < n: nb['y_pos'].append(cell_name(i, j + 1))
            if j > 1: nb['y_neg'].append(cell_name(i, j - 1))
            self.registry.add_boxel(BoxelData(
                id=c, boxel_type=BoxelType.SHADOW,
                min_corner=np.array([(i - 1) * s, (j - 1) * s, 0.0]),
                max_corner=np.array([i * s, j * s, CELL_HEIGHT]),
                neighbor_ids=nb))

    # --------------------------------------------------------------- scene
    def _box(self, half, pos, rgba, mass=0.0, collide=True, kind='', cell=''):
        c = self.cid
        vis = p.createVisualShape(p.GEOM_BOX, halfExtents=half, rgbaColor=rgba, physicsClientId=c)
        col = (p.createCollisionShape(p.GEOM_BOX, halfExtents=half, physicsClientId=c)
               if collide else -1)
        bid = p.createMultiBody(baseMass=mass, baseCollisionShapeIndex=col,
                                baseVisualShapeIndex=vis, basePosition=list(pos), physicsClientId=c)
        if kind:
            self.bodies[bid] = (kind, cell)
        return bid

    def _build_scene(self):
        s, w, c = self.s, self.world, self.cid
        self.marker_body: Dict[str, int] = {}     # 'breeze@p1-2' -> body id
        for cell in self._cells:
            i, j = cell_ij(cell)
            ctr = self.cell_center(cell)
            grey = (0.62, 0.62, 0.62, 1) if (i + j) % 2 == 0 else (0.45, 0.45, 0.47, 1)
            if cell in w.pits:
                # no tile: a shaft (four walls and a dark bottom) below the floor
                self._box([s / 2, s / 2, 0.01], [ctr[0], ctr[1], -SHAFT_DEPTH - 0.01],
                          (0.03, 0.03, 0.03, 1), kind='shaft', cell=cell)
                for dx, dy, hx, hy in ((s / 2 - 0.01, 0, 0.01, s / 2), (-s / 2 + 0.01, 0, 0.01, s / 2),
                                       (0, s / 2 - 0.01, s / 2, 0.01), (0, -s / 2 + 0.01, s / 2, 0.01)):
                    self._box([hx, hy, SHAFT_DEPTH / 2], [ctr[0] + dx, ctr[1] + dy, -SHAFT_DEPTH / 2],
                              (0.12, 0.12, 0.12, 1), kind='shaft', cell=cell)
            else:
                self.floor_tile[cell] = self._box([s / 2, s / 2, 0.01], [ctr[0], ctr[1], -0.01],
                                                  grey, kind='floor', cell=cell)
            if w.breeze(cell):
                self.marker_body[f'breeze@{cell}'] = self._box(
                    [MARKER_SIDE / 2, MARKER_SIDE / 2, MARKER_THICK / 2],
                    [ctr[0] + BREEZE_OFF[0] * s, ctr[1] + BREEZE_OFF[1] * s, MARKER_THICK / 2],
                    (0.55, 0.82, 1.0, 1), kind='breeze', cell=cell)
            if w.stench(cell):
                self.marker_body[f'stench@{cell}'] = self._box(
                    [MARKER_SIDE / 2, MARKER_SIDE / 2, MARKER_THICK / 2],
                    [ctr[0] + STENCH_OFF[0] * s, ctr[1] + STENCH_OFF[1] * s, MARKER_THICK / 2],
                    (0.15, 0.75, 0.2, 1), kind='stench', cell=cell)
            if cell in w.wumpuses:
                self._build_wumpus(cell, ctr)
        # gold on a pedestal
        g = self.cell_center(w.gold) + np.array(GOLD_OFF) * s
        self.pedestal = self._box([PEDESTAL_HALF] * 2 + [PEDESTAL_H / 2], [g[0], g[1], PEDESTAL_H / 2],
                                  (0.45, 0.3, 0.2, 1), kind='pedestal', cell=w.gold)
        bz = PEDESTAL_H + BAR_SIZE[2] / 2 + 0.0005
        self.bar = self._box([v / 2 for v in BAR_SIZE], [g[0], g[1], bz], (1.0, 0.85, 0.0, 1),
                             mass=BAR_MASS, kind='gold', cell=w.gold)
        p.changeDynamics(self.bar, -1, lateralFriction=1.0, physicsClientId=c)
        self.marker_body[f'glitter@{w.gold}'] = self.bar
        # outer wall, 0.3 m high, just outside the grid
        L, t, h = w.n * s, 0.03, 0.15
        for pos, half in (([L / 2, -t, h], [L / 2 + t, t, h]), ([L / 2, L + t, h], [L / 2 + t, t, h]),
                          ([-t, L / 2, h], [t, L / 2, h]), ([L + t, L / 2, h], [t, L / 2, h])):
            self._box(half, pos, (0.3, 0.2, 0.15, 1), kind='wall', cell='')

    def _build_wumpus(self, cell, ctr):
        c = self.cid
        hx, hy, hz = [v / 2 for v in WUMPUS_SIZE]
        shapes = [(p.GEOM_BOX, [hx, hy, hz], [0, 0, 0], (0.55, 0.05, 0.05, 1)),
                  (p.GEOM_BOX, [0.03, 0.01, 0.03], [-0.08, hy, hz * 0.5], (1, 1, 1, 1)),
                  (p.GEOM_BOX, [0.03, 0.01, 0.03], [0.08, hy, hz * 0.5], (1, 1, 1, 1))]
        vis = p.createVisualShapeArray(
            shapeTypes=[a[0] for a in shapes], halfExtents=[a[1] for a in shapes],
            visualFramePositions=[a[2] for a in shapes], rgbaColors=[a[3] for a in shapes],
            physicsClientId=c)
        col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[hx, hy, hz], physicsClientId=c)
        bid = p.createMultiBody(0, col, vis, [ctr[0], ctr[1], hz], physicsClientId=c)
        self.bodies[bid] = ('wumpus', cell)
        self.wumpus_body = getattr(self, 'wumpus_body', {})
        self.wumpus_body[cell] = bid

    # --------------------------------------------------------------- robot
    def _build_robot(self):
        c = self.cid
        # chassis as one visual-only body: base box, mast, boom, head
        parts = [([CHASSIS_HALF, CHASSIS_HALF, (CHASSIS_Z1 - CHASSIS_Z0) / 2],
                  [0, 0, (CHASSIS_Z1 + CHASSIS_Z0) / 2], (0.1, 0.25, 0.6, 1)),
                 ([0.02, 0.02, (CAM_Z + 0.02 - CHASSIS_Z1) / 2],
                  [MAST_XY[0], MAST_XY[1], (CAM_Z + 0.02 + CHASSIS_Z1) / 2], (0.2, 0.2, 0.2, 1)),
                 ([abs(MAST_XY[0]) / 2 + 0.03, 0.02, 0.01],
                  [MAST_XY[0] / 2, 0, CAM_Z + 0.03], (0.2, 0.2, 0.2, 1)),
                 ([0.04, 0.04, 0.02], [0, 0, CAM_Z + 0.03], (0.05, 0.05, 0.05, 1))]
        vis = p.createVisualShapeArray(
            shapeTypes=[p.GEOM_BOX] * len(parts), halfExtents=[a[0] for a in parts],
            visualFramePositions=[a[1] for a in parts], rgbaColors=[a[2] for a in parts],
            physicsClientId=c)
        start = self.cell_center(self.world.start)
        self.chassis = p.createMultiBody(0, -1, vis, [start[0], start[1], 0.0], physicsClientId=c)
        self.panda = p.loadURDF('franka_panda/panda.urdf', [start[0], start[1], CHASSIS_Z1],
                                useFixedBase=True, physicsClientId=c)
        self.model = robot_utils.resolve_robot_model(self.panda, c)
        robot_utils.use_robot_model(self.model)
        for fj in self.model.finger_joints:
            p.changeDynamics(self.panda, fj, lateralFriction=1.2, physicsClientId=c)
            p.resetJointState(self.panda, fj, 0.04, physicsClientId=c)
        self._set_arm(STOW_Q)
        self.base_xyz = np.array([start[0], start[1], 0.0])
        self._place_base(self.base_xyz)

    def _set_arm(self, q, reset=True):
        for j, v in zip(self.model.arm_joints, q):
            if reset:
                p.resetJointState(self.panda, j, float(v), physicsClientId=self.cid)
            p.setJointMotorControl2(self.panda, j, p.POSITION_CONTROL, targetPosition=float(v),
                                    force=240, physicsClientId=self.cid)

    def _place_base(self, xyz):
        c = self.cid
        self.base_xyz = np.asarray(xyz, dtype=float)
        x, y, z = self.base_xyz
        p.resetBasePositionAndOrientation(self.chassis, [x, y, z], [0, 0, 0, 1], physicsClientId=c)
        p.resetBasePositionAndOrientation(self.panda, [x, y, z + CHASSIS_Z1], [0, 0, 0, 1],
                                          physicsClientId=c)

    def _tick(self, n=1):
        for _ in range(n):
            p.stepSimulation(physicsClientId=self.cid)
            self.sim_steps += 1
            if self.realtime:
                time.sleep(1 / 240)

    def pose(self):
        pos, orn = p.getBasePositionAndOrientation(self.chassis, physicsClientId=self.cid)
        yaw = p.getEulerFromQuaternion(orn)[2]
        return {'x': pos[0], 'y': pos[1], 'z': pos[2], 'yaw_deg': math.degrees(yaw)}

    def robot_cell(self) -> Optional[str]:
        pos, _ = p.getBasePositionAndOrientation(self.chassis, physicsClientId=self.cid)
        return self.cell_of_xy(pos[0], pos[1])

    # ------------------------------------------------------------ perceive
    def _camera(self):
        pos, _ = p.getBasePositionAndOrientation(self.chassis, physicsClientId=self.cid)
        eye = [pos[0], pos[1], pos[2] + CAM_Z]
        view = p.computeViewMatrix(eye, [pos[0], pos[1], pos[2]], [0, 1, 0])
        fov = 2 * math.degrees(math.atan(self.footprint_half / CAM_Z))
        proj = p.computeProjectionMatrixFOV(fov=fov, aspect=1.0, nearVal=0.05, farVal=4.0)
        return eye, view, proj

    def render(self):
        eye, view, proj = self._camera()
        _, _, rgb, depth, seg = p.getCameraImage(IMG, IMG, viewMatrix=view, projectionMatrix=proj,
                                                 renderer=p.ER_TINY_RENDERER, physicsClientId=self.cid)
        rgb = np.array(rgb, dtype=np.uint8).reshape(IMG, IMG, 4)[:, :, :3]
        depth = np.asarray(depth, dtype=float).reshape(IMG, IMG)
        seg = np.asarray(seg).reshape(IMG, IMG)
        return eye, view, proj, rgb, depth, seg

    def perceive(self) -> dict:
        t0 = time.time()
        cell = self.robot_cell()
        res = {'ok': False, 'why': '', 'cell': cell, 'stench': None, 'breeze': None,
               'glitter': None, 'pixels': {}, 'wall_s': 0.0}
        if self.dead:
            res['why'] = f'dead ({self.dead})'
            return res
        if cell is None:
            res['why'] = 'robot outside the grid'
            return res
        eye, view, proj, rgb, depth, seg = self.render()
        self._last_image = (rgb, depth, seg)
        names = {bid: name for name, bid in self.marker_body.items()}
        pixels = {names[b]: int((seg == b).sum()) for b in names}
        pixels = {k: v for k, v in pixels.items() if v > 0}
        res['pixels'] = pixels
        bd = self.registry.get_boxel(cell)
        for name, n in pixels.items():
            if n < MIN_PIXELS:
                res['why'] = f'{name} has only {n} pixels (ambiguous)'
                res['wall_s'] = time.time() - t0
                return res
            b = self.marker_body[name]
            rows, cols = np.nonzero(seg == b)
            if rows.min() == 0 or cols.min() == 0 or rows.max() == IMG - 1 or cols.max() == IMG - 1:
                res['why'] = f'{name} is cut by the image border (ambiguous)'
                res['wall_s'] = time.time() - t0
                return res
        dets = perception.detect_objects_from_render(
            seg, depth, view, proj, {self.marker_body[n]: n for n in pixels}, eye[:2],
            0.0, min_pixels=MIN_PIXELS, no_footprint_completion=frozenset(pixels))
        found = {'breeze': False, 'stench': False, 'glitter': False}
        for name, det in dets.items():
            ctr = (det.est_min + det.est_max) / 2
            if not (bd.min_corner[0] <= ctr[0] <= bd.max_corner[0]
                    and bd.min_corner[1] <= ctr[1] <= bd.max_corner[1]):
                res['why'] = f'{name} is detected outside the own cell (locality)'
                res['wall_s'] = time.time() - t0
                return res
            found[name.split('@')[0]] = True
        self._dets = dets
        res.update(ok=True, why='', **found)
        if bd.boxel_type == BoxelType.SHADOW:
            bd.boxel_type = BoxelType.FREE_SPACE
        res['wall_s'] = time.time() - t0
        return res

    # ---------------------------------------------------------------- move
    def move(self, cell: str) -> dict:
        t0, s0 = time.time(), self.sim_steps
        res = {'ok': False, 'why': '', 'arrived': False, 'dead': None, 'pose': None,
               'sim_steps': 0, 'wall_s': 0.0}

        def done():
            res['pose'] = self.pose()
            res['sim_steps'] = self.sim_steps - s0
            res['wall_s'] = time.time() - t0
            return res
        if self.dead:
            res['why'] = f'dead ({self.dead})'
            return done()
        here = self.robot_cell()
        if cell not in self.world.neighbors(here):
            res['why'] = f'{cell} is not adjacent to {here}'
            return done()
        tgt = self.cell_center(cell)
        cur = self.base_xyz.copy()
        vec = tgt - cur[:2]
        dist = float(np.linalg.norm(vec))
        unit = vec / dist
        w = self.world
        stop_at = dist
        if cell in w.wumpuses:        # bumps into the wumpus (its half 0.2 + chassis half 0.28)
            stop_at = dist - (WUMPUS_SIZE[0] / 2 + CHASSIS_HALF + 0.005)
        k = max(1, int(math.ceil(stop_at / DRIVE_STEP)))
        for t in range(1, k + 1):
            d = stop_at * t / k
            self._place_base([cur[0] + unit[0] * d, cur[1] + unit[1] * d, 0.0])
            self._tick()
        if cell in w.wumpuses:
            self.dead = 'wumpus'
            p.changeVisualShape(self.chassis, -1, rgbaColor=[0.6, 0.1, 0.1, 1], physicsClientId=self.cid)
            self._tick(30)
            res.update(ok=True, why='killed by the wumpus', arrived=True, dead='wumpus')
            return done()
        if cell in w.pits:
            v, z = 0.0, 0.0
            for _ in range(400):
                v += 9.81 / 240
                z -= v / 240
                if z < -(SHAFT_DEPTH - 0.01):
                    z = -(SHAFT_DEPTH - 0.01)
                self._place_base([tgt[0], tgt[1], z])
                self._tick()
                if z <= -(SHAFT_DEPTH - 0.01):
                    break
            self.dead = 'pit'
            self._tick(30)
            res.update(ok=True, why='fell into the pit', arrived=True, dead='pit')
            return done()
        pose = self.pose()
        err = math.hypot(pose['x'] - tgt[0], pose['y'] - tgt[1])
        arrived = err <= ARRIVE_POS_TOL and abs(pose['yaw_deg']) <= ARRIVE_YAW_TOL_DEG
        res.update(ok=arrived, arrived=arrived, why='' if arrived else f'stopped {err:.3f} m off')
        return done()

    # ---------------------------------------------------------------- grab
    def _move_arm(self, q, min_steps=60):
        cur = np.array([p.getJointState(self.panda, j, physicsClientId=self.cid)[0]
                        for j in self.model.arm_joints])
        q = np.asarray(q, dtype=float)
        need = int(math.ceil(np.max(np.abs(q - cur) / (robot_utils.JOINT_VELOCITY_LIMITS
                                                       * robot_utils.SIM_TIMESTEP))))
        steps = max(min_steps, need)
        for t in range(steps):
            a = (t + 1) / steps
            self._set_arm((1 - a) * cur + a * q, reset=False)
            self._tick()
        for _ in range(120):
            now = np.array([p.getJointState(self.panda, j, physicsClientId=self.cid)[0]
                            for j in self.model.arm_joints])
            if np.max(np.abs(now - q)) < 2e-3:
                break
            self._set_arm(q, reset=False)
            self._tick()

    def _fingers(self, target, force):
        for fj in self.model.finger_joints:
            p.setJointMotorControl2(self.panda, fj, p.POSITION_CONTROL, targetPosition=target,
                                    force=force, physicsClientId=self.cid)

    def _open(self):
        for _ in range(100):
            self._fingers(0.04, 200)
            self._tick()

    def _ee_pose(self):
        st = p.getLinkState(self.panda, self.model.ee_link, computeForwardKinematics=True,
                            physicsClientId=self.cid)
        return np.array(st[0])

    def _finger_contacts(self, body):
        got = set()
        for ct in p.getContactPoints(bodyA=self.panda, bodyB=body, physicsClientId=self.cid):
            if ct[3] in self.model.finger_joints:
                got.add(ct[3])
        return got

    def _close_until_contact(self, ignore):
        fingers = self.model.finger_joints
        target = min(p.getJointState(self.panda, f, physicsClientId=self.cid)[0] for f in fingers)
        for _ in range(240):
            target = max(0.0, target - 0.0005)
            self._fingers(target, 60.0)
            self._tick()
            pads = set()
            for ct in p.getContactPoints(bodyA=self.panda, physicsClientId=self.cid):
                if ct[3] in fingers and ct[2] != self.panda and ct[2] not in ignore and ct[8] <= 0.0005:
                    pads.add(ct[3])
            if pads == set(fingers):
                width = float(np.mean([p.getJointState(self.panda, f, physicsClientId=self.cid)[0]
                                       for f in fingers]))
                hold = max(0.0, width - robot_utils.GRIP_SQUEEZE)
                for _ in range(60):
                    self._fingers(hold, 60.0)
                    self._tick()
                return width
        return None

    def grab(self) -> dict:
        t0, s0 = time.time(), self.sim_steps
        res = {'ok': False, 'why': '', 'held': False, 'sim_steps': 0, 'wall_s': 0.0}

        def done():
            res['sim_steps'] = self.sim_steps - s0
            res['wall_s'] = time.time() - t0
            return res
        if self.dead:
            res['why'] = f'dead ({self.dead})'
            return done()
        if self.held:
            res.update(ok=True, why='already holding', held=True)
            return done()
        pc = self.perceive()
        if not pc['ok']:
            res['why'] = f"cannot perceive: {pc['why']}"
            return done()
        if not pc['glitter']:
            res['why'] = 'no gold seen in this cell'
            return done()
        det = self._dets[f'glitter@{self.robot_cell()}']
        top = float(det.est_max[2])
        ctr = (det.est_min + det.est_max) / 2
        ex = det.est_max - det.est_min
        yaw = 0.0 if ex[0] >= ex[1] else math.pi / 2   # fingers close across the narrow side
        orn = p.getQuaternionFromEuler([0, math.pi, yaw])
        cx, cy = float(ctr[0]), float(ctr[1])
        q_pre = None
        for sd in GRASP_SEEDS:
            q_pre = robot_utils.solve_ik(self.panda, np.array([cx, cy, top + 0.15]), orn,
                                         self.cid, seed=sd)
            if q_pre is not None:
                break
        q_low = robot_utils.solve_ik(self.panda, np.array([cx, cy, top - 0.012]), orn, self.cid,
                                     seed=q_pre) if q_pre is not None else None
        q_up = robot_utils.solve_ik(self.panda, np.array([cx, cy, top + 0.15]), orn, self.cid,
                                    seed=q_pre) if q_pre is not None else None
        if q_pre is None or q_low is None or q_up is None:
            res['why'] = 'no IK for the grasp'
            return done()
        self._open()
        self._move_arm(q_pre)
        self._move_arm(q_low)
        ignore = set(self.floor_tile.values()) | {self.pedestal}
        width = self._close_until_contact(ignore)
        if width is None:
            self._open()
            self._move_arm(STOW_Q)
            res['why'] = 'the fingers closed on nothing'
            return done()
        self._move_arm(q_up)
        self._tick(60)
        touching = self._finger_contacts(self.bar)
        z_bar = p.getBasePositionAndOrientation(self.bar, physicsClientId=self.cid)[0][2]
        lifted = z_bar > PEDESTAL_H + 0.05
        if touching == set(self.model.finger_joints) and lifted:
            self.held = True
            self._move_arm(STOW_Q)
            self._tick(30)
            z_bar = p.getBasePositionAndOrientation(self.bar, physicsClientId=self.cid)[0][2]
            touching = self._finger_contacts(self.bar)
            self.held = touching == set(self.model.finger_joints) and z_bar > PEDESTAL_H + 0.05
        res['held'] = self.held
        res['ok'] = self.held
        res['why'] = '' if self.held else 'the bar is not held (contacts %s, bar z %.3f)' % (sorted(touching), z_bar)
        return done()

    # ------------------------------------------------------------ for checks
    def truth(self, cell: str) -> dict:
        w = self.world
        return {'pit': cell in w.pits, 'wumpus': cell in w.wumpuses, 'gold': cell == w.gold,
                'stench': w.stench(cell), 'breeze': w.breeze(cell), 'glitter': w.glitter(cell)}

    # ------------------------------------------------------------------ GUI
    def show_knowledge(self, knowledge: Dict[str, str]):
        """GUI only: colour the floor tiles (safe green, unknown grey, danger red)
        and write the label over each cell.  Tiles are no percept."""
        if not self.gui:
            return
        col = {'safe': (0.3, 0.75, 0.3, 1), 'danger': (0.85, 0.2, 0.2, 1), 'unknown': None}
        for lid in self._label_ids:
            p.removeUserDebugItem(lid, physicsClientId=self.cid)
        self._label_ids = []
        for cell, st in knowledge.items():
            tile = self.floor_tile.get(cell)
            if tile is not None:
                i, j = cell_ij(cell)
                rgba = col.get(st) or ((0.62, 0.62, 0.62, 1) if (i + j) % 2 == 0 else (0.45, 0.45, 0.47, 1))
                p.changeVisualShape(tile, -1, rgbaColor=rgba, physicsClientId=self.cid)
            ctr = self.cell_center(cell)
            self._label_ids.append(p.addUserDebugText(
                f'{cell} {st}', [ctr[0] - 0.3, ctr[1], 0.02], textColorRGB=[0, 0, 0],
                textSize=1.0, physicsClientId=self.cid))

    def close(self):
        if self.gui:
            # p.disconnect on a GUI client segfaults in this WSLg setup; the
            # process ends right after, which frees the client.
            return
        try:
            p.disconnect(physicsClientId=self.cid)
        except Exception:
            pass
