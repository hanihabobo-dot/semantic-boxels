"""
Boxel Test Environment for Semantic POD-TAMP Research.

This module implements the main PyBullet simulation environment for testing
Semantic Partitioning for Partially Observable Deterministic Task and Motion Planning.
"""

import numpy as np
import pybullet as p
import pybullet_data
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

from acting import robot_utils
from acting import slip_fixes
from console import telemetry          # #P1 F17 world telemetry (no-op unless armed)
from console import gui_page           # the page beside our own window (display only; off unless started)
from world.boxel_types import ObjectInfo, CameraObservation
from world.boxel_data import BoxelData, BoxelType
from sensing.perception import ObjectDetection, detect_objects_from_render
from world.shadow_calculator import ShadowCalculator
from world.free_space import FreeSpaceGenerator
from world.uniform_grid import UniformGridGenerator
from console.visualization import (BoxelVisualizer,
                           conceal_overlay_for_observation,
                           restore_overlay_after_observation)
# The scene types and the five preset scenes live in world_scenes.py since the
# readable migration (P2).  Every name stays importable from here.
from world.world_scenes import (ObjectShape, OBJECT_COLORS, ObjectSpec, SceneConfig,
                          default_scene, mixed_shapes_scene, stack_scene,
                          scalability_scene, random_pairs_scene)
from world.world_placement import WorldPlacement

# BF#59 solver_iters: the switch of the executing world's solver iterations
# (robot_utils.SOLVER_ITERATIONS), read here for our own world and in
# tampura_bridge/policy.py d9_setup for theirs.
slip_fixes.register('solver_iters',
                    '200 contact-solver iterations per step on the executing '
                    'world (d9_setup and boxel_env, re-applied after reset)')


# ---------------------------------------------------------------------------
# Debug visualizer (main GL view) — fixed defaults only
# ---------------------------------------------------------------------------
# ``getCameraImage`` uses ``computeViewMatrix(eye, target, up)``.  The
# ExampleBrowser view only supports ``resetDebugVisualizerCamera(distance,
# yaw, pitch, target)``.  Values below were **precomputed once** (see
# ``tools/calibrate_debug_camera.py``) by grid-matching
# ``computeViewMatrixFromYawPitchRoll`` to the default semantic camera:
#   eye (0.1, -0.8, 0.7), target (0.1, 0.0, 0.5), up (0, 0, 1).

_DEFAULT_DEBUG_VIS_TARGET = [0.1, 0.0, 0.5]
_DEFAULT_DEBUG_VIS_DISTANCE = 0.8246211251235323
_DEFAULT_DEBUG_VIS_YAW = 0.0
_DEFAULT_DEBUG_VIS_PITCH = -14.04

_DEFAULT_SEMANTIC_EYE = np.array([0.1, -0.8, 0.7])
_DEFAULT_SEMANTIC_TARGET = np.array([0.1, 0.0, 0.5])


class _ObjectBoxLookup:
    """The one registry method sync_to_plan_client reads (get_boxel),
    over OBJECT boxels that are not in a registry yet (#P4 B3(c): the
    first observation's estimates, posed in the plan twin before the
    first shadow cast)."""

    def __init__(self, boxels):
        self._by_id = {b.id: b for b in boxels}

    def get_boxel(self, boxel_id):
        return self._by_id.get(boxel_id)


class BoxelTestEnv(WorldPlacement):
    """
    PyBullet environment for testing Semantic Boxel-based POD-TAMP.
    
    This environment creates a scene with:
    - A Franka Panda arm (fixed base)
    - Multiple occluder cubes (larger, can hide objects)
    - Multiple target cubes (smaller, may be hidden)
    - A fixed depth camera for perception
    - Oracle functions for object detection and pose estimation
    """
    
    # The page beside our own window (gui_page), when the run started one
    # and this env opened the window; None otherwise (headless, an adopted
    # world, a window without the page): then nothing below differs.
    _page = None

    # Camera defaults (image_width to far_plane): origin not known; the bridge overrides all five.
    def __init__(
        self,
        gui: bool = True,
        scene_config: Optional[SceneConfig] = None,
        camera_position: Optional[np.ndarray] = None,
        camera_target: Optional[np.ndarray] = None,
        camera_up: Optional[np.ndarray] = None,
        image_width: int = 640,
        image_height: int = 480,
        fov: float = 60.0,
        near_plane: float = 0.01,
        far_plane: float = 5.0,
        window_width: int = 1280,
        window_height: int = 720,
        adopt_client: Optional[int] = None,
    ):
        """
        Initialize the Boxel test environment.

        #P4 B3(b): with ``adopt_client`` the env ADOPTS an existing
        executing world instead of building one: it connects nothing,
        never calls resetSimulation or setGravity there and never runs
        _setup_scene; a subclass's _adopt_scene() registers the world's
        bodies from its name-to-id table and builds their plan-twin
        copies with the plan-client-only helpers (_plan_load_urdf,
        _plan_spawn_object, _plan_register_twin).  The executing client's
        body count is asserted unchanged, and close() disconnects only
        the plan twin.  The caller does the world's physics set-up.

        Args:
            gui: Whether to show the PyBullet GUI
            scene_config: Scene layout and object specifications.
                ``None`` → ``default_scene()`` (original hardcoded layout).
            camera_position: Position of the camera [x, y, z]
            camera_target: Point the camera looks at [x, y, z]
            camera_up: Camera up vector [x, y, z]
            image_width: Width of camera images in pixels
            image_height: Height of camera images in pixels
            fov: Field of view in degrees
            near_plane: Near clipping plane distance
            far_plane: Far clipping plane distance
            window_width: Width of the PyBullet GUI window
            window_height: Height of the PyBullet GUI window.  PyBullet
                stacks its three camera panes at fixed places down the
                left edge; the third one ends at y = 695 and the status
                bar takes 22 px, so 717 is the least that shows all three
                in full and 720 the round number.  Under about 700 the
                third pane is pushed up over the depth pane.
            adopt_client: An existing physics client to adopt as the
                executing world (None: build our own scene, as always).
        """
        self.scene_config = scene_config or default_scene()
        # Store camera parameters
        self.image_width = image_width
        self.image_height = image_height
        self.fov = fov
        self.near_plane = near_plane
        self.far_plane = far_plane
        
        # Set default camera position
        # Origin not known.  Also _DEFAULT_SEMANTIC_EYE and its comment; they must stay equal.
        if camera_position is None:
            camera_position = np.array([0.1, -0.8, 0.7])
        # Origin not known.  Also _DEFAULT_SEMANTIC_TARGET and its comment; they must stay equal.
        if camera_target is None:
            camera_target = np.array([0.1, 0.0, 0.5])
        if camera_up is None:
            camera_up = np.array([0, 0, 1])
        
        self.camera_position = camera_position
        self.camera_target = camera_target
        self.camera_up = camera_up

        # #P4 B3(c): the client every shadow cast raycasts.  None keeps
        # today's default-client rays (PAPER_AUDIT item (h) unchanged on
        # our scenes); set to the plan twin, the twin is synced to the
        # OBJECT boxes known at that moment before each cast.
        self.shadow_raycast_client: Optional[int] = None
        # #P4 B3(d) / D8: task inputs a scene may declare.  The lowest
        # pinch contact above the table (None: execution.py's 35 mm
        # finger-tip depth) and the arm's reach envelope as (flat limit,
        # sphere centre world z, sphere radius) (None: streams.REACH_*).
        self.pick_contact_floor: Optional[float] = None
        self.reach_envelope: Optional[Tuple[float, float, float]] = None

        self._adopted = adopt_client is not None
        # Connect to PyBullet with window size options
        if self._adopted:
            self.client_id = adopt_client
            _adopted_bodies = p.getNumBodies(physicsClientId=adopt_client)
        elif gui:
            self.client_id = p.connect(p.GUI, options=f"--width={window_width} --height={window_height}")
            # Disable mouse picking so left-click rotates camera instead of grabbing objects
            p.configureDebugVisualizer(p.COV_ENABLE_MOUSE_PICKING, 0)
            # The three camera panes (RGB, depth, segmentation mask) stay on,
            # as PyBullet opens the window (Hani, 2026-11-21).
            # With the page beside the window (gui_page, --gui-page on; Hani,
            # 2026-11-22) PyBullet's own panels go instead: its menu, tabs,
            # Params column, white strip, status bar and grid, and the three
            # panes with them (one switch for all of it, the same as the key
            # g, which brings them back).  The page shows the pictures.
            self._page = gui_page.active()
            if self._page is not None:
                p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0)
            # Main view: match fixed semantic camera immediately (before resetSimulation).
            if np.allclose(self.camera_position, _DEFAULT_SEMANTIC_EYE) and np.allclose(
                self.camera_target, _DEFAULT_SEMANTIC_TARGET
            ):
                p.resetDebugVisualizerCamera(
                    cameraDistance=_DEFAULT_DEBUG_VIS_DISTANCE,
                    cameraYaw=_DEFAULT_DEBUG_VIS_YAW,
                    cameraPitch=_DEFAULT_DEBUG_VIS_PITCH,
                    cameraTargetPosition=list(_DEFAULT_DEBUG_VIS_TARGET),
                )
        else:
            self.client_id = p.connect(p.DIRECT)
        self._gui = gui

        # Reset simulation (our own world only; an adopted one is the
        # caller's)
        if not self._adopted:
            p.resetSimulation(physicsClientId=self.client_id)
            # Standard value.  Also the plan client below and reset(); they must stay equal.
            p.setGravity(0, 0, -9.81, physicsClientId=self.client_id)
            p.setRealTimeSimulation(0, physicsClientId=self.client_id)
            p.setAdditionalSearchPath(pybullet_data.getDataPath(),
                                      physicsClientId=self.client_id)
        if gui and not self._adopted:
            # Display only.  PyBullet opens its three camera panes empty (a
            # white field with a diagonal line) and fills them at the first
            # camera render, which is the first observation, seconds later,
            # once the scene has loaded.  One render of the still empty
            # world fills them now.  Never on an adopted world, whose
            # renders are its owner's.
            self.refresh_debug_camera_views()
        # BF#59 solver_iters: our own world's solver iterations, the same
        # value as the bridge's executing world (an adopted world is set
        # by d9_setup).  The plan client never steps and keeps the default.
        if not self._adopted and slip_fixes.on('solver_iters'):
            p.setPhysicsEngineParameter(
                numSolverIterations=robot_utils.SOLVER_ITERATIONS,
                physicsClientId=self.client_id)
            _n = p.getPhysicsEngineParameters(
                physicsClientId=self.client_id)['numSolverIterations']
            print(f"  solver_iters: numSolverIterations {_n} on our world "
                  f"(client {self.client_id})")

        # Plan client (audit #46): a separate DIRECT-mode PyBullet world that
        # mirrors the live scene.  All planning-time work — IK, RRT-Connect,
        # plan_motion, and is_config_collision_free — runs against this client
        # so the visible arm in self.client_id is never teleported during
        # planner.plan().  The GUI no longer freezes; the per-IK rendering
        # toggle is moot on a DIRECT client.  Body ids do NOT match between
        # clients, so we keep self._gui_to_plan to translate at the planner
        # boundary; execution-side code keeps using the GUI ids unchanged.
        self.plan_client_id = p.connect(p.DIRECT)
        p.resetSimulation(physicsClientId=self.plan_client_id)
        # Standard value.  Also our own world above and reset(); they must stay equal.
        p.setGravity(0, 0, -9.81, physicsClientId=self.plan_client_id)
        p.setRealTimeSimulation(0, physicsClientId=self.plan_client_id)
        p.setAdditionalSearchPath(pybullet_data.getDataPath(),
                                  physicsClientId=self.plan_client_id)
        self._gui_to_plan: Dict[int, int] = {}
        self.plan_robot_id: Optional[int] = None

        # Store object information
        self.objects: Dict[str, ObjectInfo] = {}

        # Initialize the scene.  If placement fails partway (e.g. the
        # hidden-target budget is exhausted at an unlucky seed) we'd
        # otherwise leak the two PyBullet clients already opened above;
        # disconnect them so the caller's retry layer can reseed and
        # rebuild without accumulating dead physics servers.  (An
        # adopted executing client is never disconnected, B3(b).)
        try:
            if self._adopted:
                self._adopt_scene()
                self._finish_adoption(_adopted_bodies)
            else:
                self._setup_scene()
        except Exception:
            self.close()
            raise
        
        # Initialize helper components
        self.shadow_calculator = ShadowCalculator(
            self.camera_position, self.table_surface_height,
            table_x_range=self.table_x_range, table_y_range=self.table_y_range
        )
        # Free-space workspace matches the safe placement footprint —
        # intersection of the physical table mesh and the Panda reach
        # disk (_SAFE_TABLE_*_RANGE, the same window used for spawning).
        # NOT the wider logical voxel grid (self.table_*_range), which is
        # deliberately extended past the near table edge for SHADOW
        # coverage only.  Generating free boxels over that wider volume
        # created cells overhanging the physical table edge (audit #44):
        # #43 made them unplaceable, but the wireframes still extended
        # into empty air past the near edge.  ShadowCalculator above
        # keeps the wider range so near-field shadow volumes behind
        # occluders remain covered.
        self.free_space_generator = FreeSpaceGenerator(
            self.table_surface_height,
            table_x_range=self._SAFE_TABLE_X_RANGE,
            table_y_range=self._SAFE_TABLE_Y_RANGE,
        )
        # audit #10 — uniform-grid baseline: drop-in replacement for the
        # octree-based FreeSpaceGenerator.  Default off (semantic);
        # enabled by setting ``use_uniform_grid=True`` after construction
        # (test_full_pipeline.main does this when --baseline=uniform).
        # Cell size is reassignable via ``set_uniform_cell_size`` so the
        # eval matrix can sweep it without recreating BoxelTestEnv.
        self.use_uniform_grid: bool = False
        self.uniform_grid_generator = UniformGridGenerator(
            self.table_surface_height,
            cell_size=0.05,
            table_x_range=self._SAFE_TABLE_X_RANGE,
            table_y_range=self._SAFE_TABLE_Y_RANGE,
        )
        self.visualizer = BoxelVisualizer()

        if self._gui and np.allclose(
            self.camera_position, _DEFAULT_SEMANTIC_EYE
        ) and np.allclose(self.camera_target, _DEFAULT_SEMANTIC_TARGET):
            # resetSimulation can reset the debug camera — re-apply fixed view after scene load.
            p.resetDebugVisualizerCamera(
                cameraDistance=_DEFAULT_DEBUG_VIS_DISTANCE,
                cameraYaw=_DEFAULT_DEBUG_VIS_YAW,
                cameraPitch=_DEFAULT_DEBUG_VIS_PITCH,
                cameraTargetPosition=list(_DEFAULT_DEBUG_VIS_TARGET),
            )
            self.debug_camera_distance = _DEFAULT_DEBUG_VIS_DISTANCE
            self.debug_camera_yaw = _DEFAULT_DEBUG_VIS_YAW
            self.debug_camera_pitch = _DEFAULT_DEBUG_VIS_PITCH
            self.debug_camera_target = np.array(_DEFAULT_DEBUG_VIS_TARGET, dtype=float)
        else:
            # Fallback debug view (distance, yaw, pitch below): origin not known.
            self.debug_camera_distance = 1.5
            self.debug_camera_yaw = 45.0
            self.debug_camera_pitch = -30.0
            self.debug_camera_target = np.array(
                [0.1, 0.0, self.table_surface_height], dtype=float
            )

        occ_shapes = [s.shape.value for s in self.scene_config.occluders]
        tgt_shapes = [s.shape.value for s in self.scene_config.targets]
        print("Boxel Test Environment initialized successfully!")
        print(f"Camera position: {self.camera_position}")
        print(f"Camera target: {self.camera_target}")
        if self._adopted:
            print(f"Adopted executing client {self.client_id}; plan twin "
                  f"client {self.plan_client_id}")
        else:
            print(f"Occluders: {len(occ_shapes)} ({', '.join(occ_shapes)})")
            print(f"Targets:   {len(tgt_shapes)} ({', '.join(tgt_shapes)})")
        print(f"Objects in scene: {list(self.objects.keys())}")

    # ------------------------------------------------------------------
    # Plan-client mirroring helpers (audit #46)
    # ------------------------------------------------------------------
    # _mirror_load_urdf and _mirror_spawn_object load/create the same body
    # in BOTH clients so motion planning sees the same scene as physics
    # execution.  Both helpers register the gui→plan body-id mapping so
    # callers that need to translate at the planner boundary can use
    # self.plan_body_id(gui_id).

    def _mirror_load_urdf(self, *args, **kwargs) -> int:
        """Load the same URDF in self.client_id and self.plan_client_id.

        Returns the GUI body id (callers store this in ObjectInfo and pass
        it to execution code unchanged).  The plan-side body id is recorded
        in self._gui_to_plan and looked up via plan_body_id().
        """
        kwargs.pop("physicsClientId", None)
        gid = p.loadURDF(*args, **kwargs, physicsClientId=self.client_id)
        pid = p.loadURDF(*args, **kwargs, physicsClientId=self.plan_client_id)
        self._gui_to_plan[gid] = pid
        return gid

    def _mirror_spawn_object(self, spec: 'ObjectSpec',
                             position: List[float]) -> int:
        """Create an ObjectSpec body in both clients; return the GUI body id."""
        gid = pid = None
        for cid in (self.client_id, self.plan_client_id):
            shape = spec.shape
            if shape == ObjectShape.BOX:
                half = list(spec.size)
                vis = p.createVisualShape(p.GEOM_BOX, halfExtents=half,
                                          rgbaColor=spec.color,
                                          physicsClientId=cid)
                col = p.createCollisionShape(p.GEOM_BOX, halfExtents=half,
                                             physicsClientId=cid)
            elif shape == ObjectShape.CYLINDER:
                r, hz = spec.size
                vis = p.createVisualShape(p.GEOM_CYLINDER, radius=r,
                                          length=hz * 2,
                                          rgbaColor=spec.color,
                                          physicsClientId=cid)
                col = p.createCollisionShape(p.GEOM_CYLINDER, radius=r,
                                             height=hz * 2,
                                             physicsClientId=cid)
            elif shape == ObjectShape.SPHERE:
                r = spec.size[0]
                vis = p.createVisualShape(p.GEOM_SPHERE, radius=r,
                                          rgbaColor=spec.color,
                                          physicsClientId=cid)
                col = p.createCollisionShape(p.GEOM_SPHERE, radius=r,
                                             physicsClientId=cid)
            else:
                raise ValueError(f"Unsupported shape: {shape}")
            body_id = p.createMultiBody(
                baseMass=spec.mass,
                baseCollisionShapeIndex=col,
                baseVisualShapeIndex=vis,
                basePosition=position,
                physicsClientId=cid,
            )
            if spec.lateral_friction != 0.5:
                p.changeDynamics(body_id, -1,
                                 lateralFriction=spec.lateral_friction,
                                 physicsClientId=cid)
            if cid == self.client_id:
                gid = body_id
            else:
                pid = body_id
        self._gui_to_plan[gid] = pid
        return gid

    # #P4 B3(b): plan-client-only variants for an ADOPTED executing world,
    # whose bodies exist already: the twin is created in the plan client
    # alone and recorded against the executing body's id.  The mirror
    # helpers above would add a second copy to the executing world.

    def _plan_load_urdf(self, gui_id: int, *args, **kwargs) -> int:
        """Load a URDF into the plan client only, as the twin of the
        executing-client body ``gui_id``; returns the plan-side id."""
        kwargs.pop("physicsClientId", None)
        pid = p.loadURDF(*args, **kwargs, physicsClientId=self.plan_client_id)
        self._gui_to_plan[gui_id] = pid
        return pid

    def _plan_register_twin(self, gui_id: int, plan_id: int) -> None:
        """Record ``plan_id``, a body the caller created in the plan
        client, as the twin of the executing-client body ``gui_id``."""
        self._gui_to_plan[gui_id] = plan_id

    def _adopt_scene(self) -> None:
        """Register an adopted world's bodies (B3(b)).  The adopting
        subclass implements it: self.objects from its name-to-id table
        (plane, table and robot by those names), the plan twin through
        the plan-client-only helpers, self.plan_robot_id, the table
        surface and the table / safe workspace ranges."""
        raise NotImplementedError(
            "adopt_client needs a subclass that registers the adopted "
            "world's bodies (_adopt_scene)")

    def _finish_adoption(self, bodies_before: int) -> None:
        """Checks after _adopt_scene: the executing world gained or lost
        no body, and both robots resolve by name to the same model,
        which is installed for every index consumer."""
        after = p.getNumBodies(physicsClientId=self.client_id)
        if after != bodies_before:
            raise RuntimeError(
                f"adopting client {self.client_id} changed its body count "
                f"from {bodies_before} to {after}")
        model = robot_utils.resolve_robot_model(
            self.objects["robot"].object_id, self.client_id)
        twin = robot_utils.resolve_robot_model(
            self.plan_robot_id, self.plan_client_id)
        if twin != model:
            raise RuntimeError("the plan-twin robot resolves to a different "
                               "robot model than the executing robot")
        robot_utils.use_robot_model(model)

    def plan_body_id(self, gui_id: int) -> int:
        """Translate a GUI-client body id to the plan client's body id.

        Raises KeyError if gui_id wasn't created via the mirror helpers
        (i.e. exists only in the GUI world).  Use this at the planner
        boundary to build object_body_ids / support_body_ids.
        """
        return self._gui_to_plan[gui_id]

    # Where the plan client parks a body the belief does not hold (#P1
    # WP2c): far below the workspace, out of every reachable pose.
    # The reason is above; no measurement on record.
    _PLAN_CLIENT_PARK = [5.0, 5.0, -5.0]

    def sync_to_plan_client(self, held_body_id: Optional[int] = None,
                            registry=None) -> None:
        """Mirror the robot's state into the plan client.

        Call this once per replan (right before planner.plan()).  Cheap —
        a few dozen p.* calls — and avoids the per-IK save/restore handshake
        that the single-client design needed.

        #P1 WP2c (2026-09-19): with ``registry`` given, the plan client —
        the motion planner's collision world — is posed from the robot's
        BELIEF, not from the simulator (#P1 inventory item (j)):
          * the robot: every joint state from the executing robot
            (proprioception);
          * the plane, the table and the tray: their true poses (static
            bodies known at design time, like their sizes);
          * every other body: the centre of its registry boxel (the
            perception estimate), upright; a body with NO boxel (a hidden
            target the robot has never seen, a retired lost object) is
            parked at _PLAN_CLIENT_PARK — the planner cannot avoid what
            the robot does not know is there, and a motion that hits it
            is a physical failure the world-integrity monitor reports;
          * the held body: at the end effector (proprioception);
            planning-time collision checks reposition it to each
            hypothetical EE config in is_config_collision_free anyway.
        Without ``registry`` the pre-WP2c behaviour remains (every body's
        simulator pose) for probes and tools that have no belief.
        """
        if registry is None:
            for gid, pid in self._gui_to_plan.items():
                pos, orn = p.getBasePositionAndOrientation(
                    gid, physicsClientId=self.client_id)
                p.resetBasePositionAndOrientation(
                    pid, pos, orn, physicsClientId=self.plan_client_id)
        else:
            static = {"plane", "table", "robot"}
            ee_pos = None
            if held_body_id is not None and "robot" in self.objects:
                ee_pos = p.getLinkState(self.objects["robot"].object_id,
                                        robot_utils.robot_model().ee_link,
                                        physicsClientId=self.client_id)[0]
            for name, info in self.objects.items():
                gid = info.object_id
                pid = self._gui_to_plan.get(gid)
                if pid is None:
                    continue
                if name in static or getattr(info, "is_tray", False):
                    pos, orn = p.getBasePositionAndOrientation(
                        gid, physicsClientId=self.client_id)
                    p.resetBasePositionAndOrientation(
                        pid, pos, orn, physicsClientId=self.plan_client_id)
                    continue
                if gid == held_body_id and ee_pos is not None:
                    pos = [float(v) for v in ee_pos]
                else:
                    bd = registry.get_boxel(name)
                    pos = ([float(v) for v in bd.center] if bd is not None
                           else list(self._PLAN_CLIENT_PARK))
                p.resetBasePositionAndOrientation(
                    pid, pos, [0.0, 0.0, 0.0, 1.0],
                    physicsClientId=self.plan_client_id)
        if self.plan_robot_id is not None:
            gui_robot = self.objects["robot"].object_id
            n_joints = p.getNumJoints(gui_robot,
                                      physicsClientId=self.client_id)
            for j in range(n_joints):
                angle, vel = p.getJointState(
                    gui_robot, j, physicsClientId=self.client_id)[:2]
                p.resetJointState(self.plan_robot_id, j, angle,
                                  targetVelocity=vel,
                                  physicsClientId=self.plan_client_id)

    def _setup_scene(self):
        """Set up the simulation scene with plane, table, robot, and objects."""
        # Load ground plane
        plane_id = self._mirror_load_urdf("plane.urdf", [0, 0, 0], [0, 0, 0, 1])
        # The plane's size (10, 10, 0.1) is a record size, origin not known.
        self.objects["plane"] = ObjectInfo(
            object_id=plane_id, name="plane",
            position=np.array([0, 0, 0]), orientation=np.array([0, 0, 0, 1]),
            size=np.array([10, 10, 0.1]), is_visible=True, is_occluder=False
        )

        # Load table
        # Table at (0.5, 0.0) lowered by 0.3: origin of the offset not known.
        table_z_offset = -0.3
        table_position = [0.5, 0.0, table_z_offset]
        table_id = self._mirror_load_urdf("table/table.urdf", table_position,
                                          [0, 0, 0, 1], useFixedBase=True)
        # 0.625 is the height of pybullet_data's table mesh.
        self.table_surface_height = 0.625 + table_z_offset

        # XY bounds for voxelization / shadows / free-space (logical workspace).
        # Table mesh stays centered at [0.5, 0]; this window is shifted −0.4 m
        # in X so the voxel grid encloses objects near the robot without clipping.
        # The reason is above (the shift toward the robot, fix #17); no measurement on record.
        self.table_x_range = (-0.4, 0.6)
        self.table_y_range = (-0.5, 0.5)

        # The table's size (1.0, 1.0, 0.8) is a record size, origin not known.
        self.objects["table"] = ObjectInfo(
            object_id=table_id, name="table",
            position=np.array(table_position), orientation=np.array([0, 0, 0, 1]),
            size=np.array([1.0, 1.0, 0.8]), is_visible=True, is_occluder=False
        )

        # Load robot
        # Reason as for the window above.  Also _ROBOT_BASE_XY; they must stay equal.
        robot_pos = [-0.4, 0.0, 0.0]
        robot_id = self._mirror_load_urdf("franka_panda/panda.urdf", robot_pos,
                                          [0, 0, 0, 1], useFixedBase=True)
        self.plan_robot_id = self._gui_to_plan[robot_id]
        # #P4 B3(a): the robot model by name; pybullet_data's Panda must
        # resolve to the indices this pipeline always used.
        model = robot_utils.resolve_robot_model(robot_id, self.client_id)
        assert model == robot_utils.PANDA_PYBULLET_DATA, model
        robot_utils.use_robot_model(model)
        fingers = model.finger_joints
        # #P1 friction grasp: the finger pads are the load path now — the
        # JOINT_FIXED weld that used to carry the held object is gone, so
        # the pad–object friction cone must hold the grasp on its own.
        # Bullet combines friction multiplicatively: pad 1.2 × object 1.0
        # (ObjectSpec default) → μ = 1.2 at the contact, ~48 N tangential
        # capacity per pad under the 40 N close force, against ≤ 5 N of
        # object weight.  Physics client only — the DIRECT plan client is
        # used for collision queries, never contact simulation.
        # Derived above.  Also tampura_bridge/task_spec.py (pad friction); they must stay equal.
        for finger_link in fingers:
            p.changeDynamics(robot_id, finger_link, lateralFriction=1.2,
                             physicsClientId=self.client_id)
        # #P1 F1 (field bug, archive/p1_field_reports_2026-08-20/
        # grip_loss.md): panda.urdf's prismatic finger joints have
        # lower=0.0 and loadURDF zeroes every joint, so the fingers
        # SPAWN FULLY CLOSED while the PDDL convention assumes init =
        # open (execution.py execute_pick).  Without this reset the
        # episode's FIRST descent grinds the closed fingertips into the
        # object top (500-800 N servo grind) and grip verification
        # passes on a phantom hold.  Scene construction, not a
        # grasp-path teleport.  sync_to_plan_client copies finger
        # joints before every plan; the plan client is mirrored here
        # anyway so the two worlds never start divergent.
        # Reason above (the finger limit).  Also tampura_bridge/task_spec.py; they must stay equal.
        for fj in fingers:
            p.resetJointState(robot_id, fj, 0.04,
                              physicsClientId=self.client_id)
            p.resetJointState(self.plan_robot_id, fj, 0.04,
                              physicsClientId=self.plan_client_id)
        # BF#59 force_hold (slip_fixes.py; finger_gear folded in): the same
        # JOINT_GEAR constraint d9_setup creates on the bridge's executing
        # client, here on our physics client at robot load; reset() runs
        # resetSimulation (which removes constraints) and then this method
        # again, so a reset world gets it back.  pybullet_data's URDF declares
        # the coupling too (panda.urdf line 323, <mimic>), which PyBullet
        # ignores.  The DIRECT plan client never steps and gets none.
        from acting import slip_fixes
        if slip_fixes.on('force_hold'):
            robot_utils.force_hold_requires_solver_iters('boxel_env._setup_scene')
            f1, f2 = fingers
            gear = p.createConstraint(robot_id, f1, robot_id, f2,
                                      jointType=p.JOINT_GEAR, jointAxis=[1, 0, 0],
                                      parentFramePosition=[0, 0, 0],
                                      childFramePosition=[0, 0, 0],
                                      physicsClientId=self.client_id)
            p.changeConstraint(gear, gearRatio=robot_utils.FINGER_GEAR_RATIO,
                               erp=robot_utils.FINGER_GEAR_ERP,
                               maxForce=robot_utils.FINGER_GEAR_MAX_FORCE,
                               physicsClientId=self.client_id)
            import logging
            logging.getLogger('boxel_env').info(
                "force_hold: finger gear constraint %d on client %d (joints %d, "
                "%d, gearRatio %g, erp %g, maxForce %g N)", gear, self.client_id,
                f1, f2, robot_utils.FINGER_GEAR_RATIO, robot_utils.FINGER_GEAR_ERP,
                robot_utils.FINGER_GEAR_MAX_FORCE)
        # The robot's size (0.5, 0.5, 0.8) is a record size, origin not known.
        self.objects["robot"] = ObjectInfo(
            object_id=robot_id, name="robot",
            position=np.array(robot_pos), orientation=np.array([0, 0, 0, 1]),
            size=np.array([0.5, 0.5, 0.8]), is_visible=True, is_occluder=False
        )

        # Tray (audit #49) — fixed-base support surface, only spawned when
        # the scene_config opts in.  Created BEFORE occluders/targets so its
        # XY can be reserved against random-placement collisions.
        self._tray_xy: Optional[List[float]] = None
        if self.scene_config.enable_tray:
            self._create_tray()

        # Create occluders
        self._create_occluders()

        # Create targets
        self._create_targets()

        # Let objects settle under gravity after placement.
        # 10 steps at 240 Hz ≈ 0.04 s — sufficient for cubes on a flat
        # table to reach static equilibrium.
        # The reason is above; no measurement on record for the 10 steps.
        for _ in range(10):
            p.stepSimulation(physicsClientId=self.client_id)
            telemetry.tick()

        self.update_object_positions()
    
    # ------------------------------------------------------------------
    # Object spawning (supports BOX, CYLINDER, SPHERE via ObjectSpec)
    # ------------------------------------------------------------------

    @staticmethod
    def _spawn_object(spec: ObjectSpec, position: List[float]) -> int:
        """
        Create a PyBullet rigid body from an ObjectSpec.

        Returns the PyBullet body ID.
        """
        shape = spec.shape
        if shape == ObjectShape.BOX:
            half = list(spec.size)
            vis = p.createVisualShape(p.GEOM_BOX, halfExtents=half,
                                      rgbaColor=spec.color)
            col = p.createCollisionShape(p.GEOM_BOX, halfExtents=half)
        elif shape == ObjectShape.CYLINDER:
            r, hz = spec.size
            vis = p.createVisualShape(p.GEOM_CYLINDER, radius=r,
                                      length=hz * 2, rgbaColor=spec.color)
            col = p.createCollisionShape(p.GEOM_CYLINDER, radius=r,
                                         height=hz * 2)
        elif shape == ObjectShape.SPHERE:
            r = spec.size[0]
            vis = p.createVisualShape(p.GEOM_SPHERE, radius=r,
                                      rgbaColor=spec.color)
            col = p.createCollisionShape(p.GEOM_SPHERE, radius=r)
        else:
            raise ValueError(f"Unsupported shape: {shape}")

        body_id = p.createMultiBody(baseMass=spec.mass,
                                    baseCollisionShapeIndex=col,
                                    baseVisualShapeIndex=vis,
                                    basePosition=position)
        if spec.lateral_friction != 0.5:
            p.changeDynamics(body_id, -1,
                             lateralFriction=spec.lateral_friction)
        return body_id

    # Robot base XY (matches franka_panda spawn in _setup_scene) and the
    # Panda's effective tabletop reach radius.  Used to keep random
    # placements inside the arm's workspace when constrain_to_reach=True.
    _ROBOT_BASE_XY = (-0.4, 0.0)
    # The radius has a reason only (effective tabletop reach), no source on record.
    _PANDA_REACH_RADIUS = 0.65

    # Reach-constrained on-table window: intersection of the actual
    # table mesh, the Panda reach disk, and a small edge buffer.  Used
    # by ``stack_scene`` (and any scene with ``constrain_to_reach=True``)
    # where every cube must be both pickable AND a viable stack target.
    # The derivation is above; no numbers on record for the two ranges.
    _SAFE_TABLE_X_RANGE = (-0.1, 0.70)
    _SAFE_TABLE_Y_RANGE = (-0.40, 0.40)

    # Random-placement window for scenes that DO NOT constrain to reach
    # (scalability / random-pairs / scalability-derived).  Contained
    # inside the actual table mesh footprint (probed AABB ≈ x ∈ [-0.251,
    # 1.251], y ∈ [-0.501, 0.501] for the standard pybullet_data table
    # at [0.5, 0]) with an edge buffer that survives the additional
    # 0.10 m intra-object margin.  Lower x bound shifted from the old
    # voxel-grid value (-0.4) inward to -0.20 because anything at
    # x < -0.251 sat off the mesh and tipped off when physics started
    # (this was the "object placed outside the table" bug).  The wider
    # ``table_x_range`` / ``table_y_range`` describe the LOGICAL
    # voxel-grid workspace (extended back to x=-0.4 to enclose the
    # robot's near field for boxelization), NOT a valid spawn area.
    _TABLE_PLACE_X_RANGE = (-0.20, 0.60)
    _TABLE_PLACE_Y_RANGE = (-0.50, 0.50)

    # audit #49 — tray (fixed-base support surface, default-off).
    # Uses the built-in pybullet_data tray/traybox.urdf (textured mesh
    # visual, box-primitive collision, mass=0).  At globalScaling=0.4
    # the footprint is ~0.24 x 0.24 m with angled walls ~0.03 m high.
    # Position (0.10, 0.40) sits in the back-left corner of the table,
    # closest to the Panda base; for default_scene the (0.10, 0.40)
    # yellow target slot conflicts with this and needs to be moved when
    # enable_tray is opted in (random-placement scenes auto-reserve
    # via _create_targets).
    # Correction: the tray stands at _TRAY_XY below today, not at (0.10, 0.40).
    _TRAY_XY = (-0.130, 0.380)
    _TRAY_SCALE = 0.4
    _TRAY_NAME = "tray"

    def _create_tray(self):
        """Spawn the built-in traybox URDF as a non-pickable support (audit #49).

        Loaded via ``_mirror_load_urdf`` so both GUI and plan clients see
        it.  Registered in ``self.objects`` with ``is_tray=True`` so
        downstream filters (oracle_detect_objects, shadow loop, planner
        init) can recognise it.  ``self._tray_xy`` is exposed so random-
        placement helpers can reserve the footprint.
        """
        cx, cy = self._TRAY_XY
        cz = self.table_surface_height

        body_id = self._mirror_load_urdf(
            "tray/traybox.urdf",
            [cx, cy, cz],
            [0, 0, 0, 1],
            useFixedBase=True,
            globalScaling=self._TRAY_SCALE,
        )

        aabb_min, aabb_max = p.getAABB(body_id,
                                        physicsClientId=self.client_id)
        size = np.array([aabb_max[0] - aabb_min[0],
                         aabb_max[1] - aabb_min[1],
                         aabb_max[2] - aabb_min[2]])

        self.objects[self._TRAY_NAME] = ObjectInfo(
            object_id=body_id,
            name=self._TRAY_NAME,
            position=np.array([cx, cy, cz]),
            orientation=np.array([0, 0, 0, 1]),
            size=size,
            is_visible=True,
            is_occluder=False,
            is_tray=True,
        )
        self._tray_xy = [float(cx), float(cy)]

    def _create_occluders(self):
        """Create occluder objects on the table from scene_config."""
        cfg = self.scene_config
        rng = np.random.RandomState(cfg.seed)

        if cfg.occluder_positions is not None:
            xys = cfg.occluder_positions
        else:
            reserved = ([list(self._tray_xy)]
                        if self._tray_xy is not None else None)
            xys = self._random_xy_positions(
                len(cfg.occluders), rng,
                constrain_to_reach=cfg.constrain_to_reach,
                reserved_xys=reserved,
            )

        # audit #70 (reopened 2026-05-12) hardening — defends against
        # caller-supplied cfg.occluder_positions sidestepping the reach
        # filter.  _random_xy_positions already filters by reach when
        # constrain_to_reach=True; the assert is the safety net for
        # the pre-baked-positions path.  Gated so non-reach-bound
        # scenes stay on the wide _TABLE_PLACE_* window.
        if cfg.constrain_to_reach:
            self._assert_xys_in_reach(xys, "occluder")

        for i, (spec, xy) in enumerate(zip(cfg.occluders, xys)):
            he = spec.aabb_half_extents
            z = self.table_surface_height + float(he[2])
            pos = [xy[0], xy[1], z]

            body_id = self._mirror_spawn_object(spec, pos)
            name = spec.name if spec.name is not None else f"occluder_{i + 1}"
            self.objects[name] = ObjectInfo(
                object_id=body_id, name=name,
                position=np.array(pos), orientation=np.array([0, 0, 0, 1]),
                size=spec.full_extents, is_visible=True, is_occluder=True
            )

    def _create_targets(self):
        """Create target objects on the table from scene_config."""
        cfg = self.scene_config
        rng = np.random.RandomState(
            cfg.seed + 1000 if cfg.seed is not None else None
        )

        if cfg.target_positions is not None:
            xys = cfg.target_positions
        else:
            n_total = len(cfg.targets)
            n_hidden = max(0, min(int(cfg.n_hidden_targets), n_total))

            # Pull live occluder XYs + horizontal half-extents from the
            # already-spawned ObjectInfo records instead of threading a
            # second data stream through SceneConfig.
            occluder_info = [
                ((float(info.position[0]), float(info.position[1])),
                 float(max(info.size[0], info.size[1]) / 2.0))
                for info in self.objects.values() if info.is_occluder
            ]
            reserved_xys: List[List[float]] = [
                list(xy) for xy, _ in occluder_info
            ]
            # audit #49 — also reserve the tray footprint when present so
            # random target placement does not spawn cubes inside the tray.
            if self._tray_xy is not None:
                reserved_xys.append(list(self._tray_xy))

            hidden_xys: List[List[float]] = []
            if n_hidden > 0 and occluder_info:
                result = self._hidden_xy_positions(
                    target_specs=cfg.targets[:n_hidden],
                    occluder_info=occluder_info,
                    rng=rng,
                    hidden_margin=0.10,
                    reserved_xys=reserved_xys,
                    constrain_to_reach=cfg.constrain_to_reach,
                )
                if result is None:
                    # Single-shot contract: if the raycast-verified
                    # placement helper cannot satisfy the request, fail
                    # immediately with an actionable error.  No silent
                    # fallback to random placement — that would produce
                    # a scene that does not match the --n-hidden promise
                    # (audit #29).
                    raise RuntimeError(
                        f"Could not place {n_hidden} hidden targets "
                        f"with {len(occluder_info)} occluders at "
                        f"seed={cfg.seed}. Try --n-occluders higher, "
                        f"--n-hidden lower, or a different --seed."
                    )
                hidden_xys = result
                reserved_xys = reserved_xys + hidden_xys

            n_remaining = n_total - len(hidden_xys)
            if n_remaining > 0:
                visible_xys = self._random_xy_positions(
                    n_remaining, rng,
                    constrain_to_reach=cfg.constrain_to_reach,
                    reserved_xys=reserved_xys,
                )
            else:
                visible_xys = []

            xys = hidden_xys + visible_xys

        # audit #70 (reopened 2026-05-12) hardening — _hidden_xy_-
        # positions is reach-disk-unaware (samples behind occluders
        # without filtering), so a hidden target whose parent occluder
        # sits at the back of the reach disk can land beyond it.  This
        # assert catches that case (and any caller-supplied
        # cfg.target_positions sidestepping the filter).  RuntimeError
        # fails the pre-flight loud in test_full_pipeline.main()
        # (audit #29 mechanism; seed retry removed 2026-08-23).
        if cfg.constrain_to_reach:
            self._assert_xys_in_reach(xys, "target")

        for i, (spec, xy) in enumerate(zip(cfg.targets, xys)):
            he = spec.aabb_half_extents
            z = self.table_surface_height + float(he[2])
            pos = [xy[0], xy[1], z]

            body_id = self._mirror_spawn_object(spec, pos)
            name = spec.name if spec.name is not None else f"target_{i + 1}"
            self.objects[name] = ObjectInfo(
                object_id=body_id, name=name,
                position=np.array(pos), orientation=np.array([0, 0, 0, 1]),
                size=spec.full_extents, is_visible=False, is_occluder=False
            )
    
    def generate_boxels(self, est_aabbs: Dict[str, Tuple[np.ndarray, np.ndarray]]
                        ) -> List[BoxelData]:
        """
        Generate Semantic BoxelData for detected objects and their shadows.

        Object boxels get ``id=<object_name>`` (e.g. "red_object") so the
        planner can reference them with their human-readable label.
        Shadow boxels get ``id=shadow_of_<object_name>`` and
        ``created_by_boxel_id`` / ``created_by_object`` set to the parent
        object name (which is also the parent's boxel ID).

        #P1 step (2): geometry comes from the caller's perception
        ESTIMATES, not p.getAABB — an object without an estimate (hidden,
        undetected) gets no boxel, which is the structural mechanism that
        keeps hidden objects out of the planner's world.

        Args:
            est_aabbs: detected object name -> (aabb_min, aabb_max)
                estimated world-frame AABB corners.

        Returns:
            List of OBJECT + SHADOW BoxelData with semantic IDs and parent
            relationships fully populated, ready to be added to a registry.
        """
        table_z = self.table_surface_height
        on_surface_tol = 0.01  # PyBullet contact margin + AABB rounding

        object_boxels: List[BoxelData] = []
        # Iterate in self.objects (spawn) order, not dict/sorted order of
        # the estimates: boxel list order feeds free-space generation and
        # PDDL grounding order, and equal-cost plans tie-break on it — the
        # pre-step-2 oracle iterated spawn order, so keep that behaviour.
        for obj_name in self.objects:
            if obj_name not in est_aabbs:
                continue

            aabb_min = np.asarray(est_aabbs[obj_name][0], dtype=float)
            aabb_max = np.asarray(est_aabbs[obj_name][1], dtype=float)

            object_boxels.append(BoxelData(
                id=obj_name,
                boxel_type=BoxelType.OBJECT,
                min_corner=aabb_min,
                max_corner=aabb_max,
                object_name=obj_name,
                is_occluder=False,  # set below if any shadow is cast
                on_surface="table" if aabb_min[2] <= table_z + on_surface_tol else None,
                surface_z=table_z,
            ))

        # Compute shadows; mark casters as occluders.
        # audit #49 — tray (is_tray=True) is a support surface, not an
        # occluder.  Skip it as a shadow CASTER so no shadow_of_tray
        # boxel is generated and no blocks_view_at facts emit for it.
        # The tray remains in obstacles for OTHER objects' shadow rays
        # (its 3 cm walls barely obstruct anything anyway).
        #
        # Audit #68 follow-up — previously-computed shadows are passed
        # in as obstacles too, so overlap regions get carved out of the
        # later shadow and each table point belongs to at most one
        # SHADOW boxel.  Without this, two shadows that overlap both
        # claim "target might be here", and sensing one leaves the
        # other's overlap region still flagged unknown — the planner
        # then re-plans to sense the same physical volume from the
        # other shadow's name.  Iteration order is sorted by parent
        # object name so the carve is deterministic across runs.
        shadow_boxels: List[BoxelData] = []
        # #P4 B3(c): with a shadow-raycast client the rays hit the plan
        # twin, posed from these estimates (boxel-less bodies parked),
        # never the executing world.  Nothing moves between the casts.
        if self.shadow_raycast_client is not None:
            self.sync_to_plan_client(registry=_ObjectBoxLookup(object_boxels))
        for obj_boxel in sorted(object_boxels, key=lambda b: b.id):
            obj_info = self.objects.get(obj_boxel.id)
            if obj_info is not None and obj_info.is_tray:
                continue
            obstacles = [b for b in object_boxels if b.id != obj_boxel.id]
            obstacles.extend(shadow_boxels)
            shadow_parts = self.shadow_calculator.calculate_shadow_boxel(
                obj_boxel, obstacles,
                physics_client=self.shadow_raycast_client)

            if shadow_parts:
                obj_boxel.is_occluder = True

            for idx, sp in enumerate(shadow_parts):
                # ShadowCalculator leaves ID empty; assign a stable
                # "shadow_of_<parent>" name and link parent ↔ shadow IDs
                # so downstream consumers (planner, visualizer) can
                # rely on the relationship.  Audit #72: shadow_parts is
                # 2+ slabs per occluder (option C two-slab carve, plus
                # any obstacle-subtraction fragments).  Suffix the ID
                # with __NN when more than one slab exists so the
                # registry's id-keyed dict doesn't overwrite earlier
                # slabs.  Single-slab case keeps the bare name for
                # backward compat.
                suffix = f"__{idx:02d}" if len(shadow_parts) > 1 else ""
                sp.id = f"shadow_of_{obj_boxel.id}{suffix}"
                sp.created_by_boxel_id = obj_boxel.id
                sp.on_surface = (
                    "table"
                    if sp.min_corner[2] <= table_z + on_surface_tol
                    else None
                )
                sp.surface_z = table_z
                obj_boxel.shadow_boxel_ids.append(sp.id)
                shadow_boxels.append(sp)

        return object_boxels + shadow_boxels

    def generate_free_space(self, known_boxels: List[BoxelData],
                            visualize: bool = False) -> List[BoxelData]:
        """
        Discretize the free space using octree subdivision.

        Args:
            known_boxels: List of OBJECT + SHADOW BoxelData (the obstacles).
            visualize: If True, animates the generation process.

        Returns:
            List of FREE_SPACE BoxelData fragments (with empty IDs).
            ``on_surface`` / ``surface_z`` are NOT populated here — the
            execution layer annotates them after cell merging because
            CellMerger emits fresh BoxelData copies that would otherwise
            strip these fields.

        Under the uniform-grid baseline (``use_uniform_grid=True``,
        audit #10) the call dispatches to UniformGridGenerator instead;
        the static lattice replaces the adaptive octree, only the labels
        on each cell flip as objects are revealed/moved.
        """
        if self.use_uniform_grid:
            return self.uniform_grid_generator.generate(
                known_boxels, visualize
            )
        return self.free_space_generator.generate(known_boxels, visualize)

    def set_uniform_cell_size(self, cell_size: float) -> None:
        """Recreate the uniform-grid generator with a new cell size.

        Used by ``test_full_pipeline`` when --uniform-cell-size is passed
        on the CLI; cell size is hyperparameter-scope, not run-scope, so
        rebuilding the lattice once at startup is fine.
        """
        self.uniform_grid_generator = UniformGridGenerator(
            self.table_surface_height,
            cell_size=cell_size,
            table_x_range=self._SAFE_TABLE_X_RANGE,
            table_y_range=self._SAFE_TABLE_Y_RANGE,
        )

    def annotate_free_space_surface(self, free_boxels: List[BoxelData]) -> None:
        """
        Set ``on_surface`` / ``surface_z`` on FREE_SPACE BoxelData.

        Free-space cells flow through stateless geometry stages
        (FreeSpaceGenerator → CellMerger) before reaching the registry.
        Those stages don't know the table height, so this helper carries
        that knowledge to the call site.  Required by the planner so
        ``place`` actions (precondition: ``(on_surface ?b)``) can fire.

        A free boxel is "on the table" only when BOTH:
          (a) its bottom is within 0.01 m of the table z (existing test), AND
          (b) its XY CENTRE lies within ``_SAFE_TABLE_*_RANGE`` — the
              intersection of the physical table mesh and the Panda's
              reach disk (same window used for spawning).
        The logical voxel grid extends to x=-0.4 m (behind the robot) so
        shadow volumes cover the near field; without (b) the planner
        would pick FREE boxels whose centre is off the table mesh, and
        execute_place (which drops at boxel.center) would release the
        object over empty air.  Observed 2026-04-26: cubes falling off
        the near edge in front of the robot (audit #43).

        Mutates ``free_boxels`` in place.  The 0.01 m tolerance accounts
        for PyBullet contact margin and AABB rounding.
        """
        table_z = self.table_surface_height
        x_lo, x_hi = self._SAFE_TABLE_X_RANGE
        y_lo, y_hi = self._SAFE_TABLE_Y_RANGE
        for b in free_boxels:
            on_z = b.min_corner[2] <= table_z + 0.01
            cx = 0.5 * (b.min_corner[0] + b.max_corner[0])
            cy = 0.5 * (b.min_corner[1] + b.max_corner[1])
            on_xy = (x_lo <= cx <= x_hi) and (y_lo <= cy <= y_hi)
            b.on_surface = "table" if (on_z and on_xy) else None
            b.surface_z = table_z

    def _view_and_projection_matrices(self):
        """View and projection matrices for the semantic camera (matches oracle rays)."""
        view_matrix = p.computeViewMatrix(
            cameraEyePosition=self.camera_position,
            cameraTargetPosition=self.camera_target,
            cameraUpVector=self.camera_up,
        )
        projection_matrix = p.computeProjectionMatrixFOV(
            fov=self.fov,
            aspect=self.image_width / self.image_height,
            nearVal=self.near_plane,
            farVal=self.far_plane,
        )
        return view_matrix, projection_matrix

    def refresh_debug_camera_views(self) -> None:
        """
        Render the robot's camera once more for the window's camera panes
        (display only: nothing is returned or kept).

        PyBullet copies every camera render on the window's client into the
        three panes on the left (RGB, depth, segmentation mask), whichever
        renderer made it.  Between observations the panes go stale, so this
        is called after a plan, after an executed action and after
        world_eye's window screenshot (TB-40); and once by __init__ when
        our own window opens, on the still empty world, so that the panes
        do not start as PyBullet's empty placeholders.  The hardware
        renderer draws only while COV_ENABLE_RENDERING is on: call it
        after leaving a RenderingLock.

        The boxel overlay's bodies are put out of view for the render, as
        for every observation (#P1 F19), so the panes show what the robot's
        camera sees and nothing else (TB-48; Hani, 2026-11-15 and
        2026-11-21).  Where no overlay body exists (the bridge draws lines
        only) the two calls move nothing.

        With the page beside our own window (gui_page) the panes are off
        and the same render, made at the same moments, is handed to the
        page instead of being dropped.
        """
        if not self._gui:
            return
        view_matrix, projection_matrix = self._view_and_projection_matrices()
        conceal_overlay_for_observation()
        try:
            render = p.getCameraImage(
                width=self.image_width,
                height=self.image_height,
                viewMatrix=view_matrix,
                projectionMatrix=projection_matrix,
                renderer=p.ER_BULLET_HARDWARE_OPENGL,
            )
        finally:
            restore_overlay_after_observation()
        if self._page is not None:
            self._page.offer_render(self.image_width, self.image_height,
                                    render[2], render[3], render[4],
                                    self.near_plane, self.far_plane, 'display')

    def get_camera_observation(self) -> CameraObservation:
        """
        Capture an observation from the camera.

        #P1 step (2): detection is REAL perception now — the fixed camera
        renders RGB + depth + instance segmentation and
        perception.detect_objects_from_render turns the segmented depth
        pixels into per-object AABB/pose ESTIMATES; boxels (and everything
        the planner sees) are built from those estimates.  The detection
        render uses ER_TINY_RENDERER in BOTH GUI and DIRECT mode so GUI
        twins and headless runs perceive bit-identical pixels (audit #56's
        DIRECT render-skip fast path is retired by design: detection
        requires the render).  oracle_detect_objects survives only for the
        eval harness's ground-truth checks (Phase-1 settle sanity, Phase-4
        hidden/visible split) — it no longer feeds this observation.
        """
        view_matrix, projection_matrix = self._view_and_projection_matrices()
        if self._gui:
            # Display-only side effect, kept from before #56: a hardware
            # render for the window's panes.  Detection ignores this
            # image, and it does not stay in the panes: PyBullet copies
            # the TinyRenderer render of detect_objects below into them
            # as soon as that is made, so this one shows only for the
            # time that render takes.  The overlay's bodies are out of
            # view for it, as in refresh_debug_camera_views (TB-48).
            # With the page beside the window (gui_page) the panes are
            # off and this render shows nowhere; it stays, so that a run
            # with the page makes the renders of a run without it.
            conceal_overlay_for_observation()
            try:
                p.getCameraImage(
                    width=self.image_width,
                    height=self.image_height,
                    viewMatrix=view_matrix,
                    projectionMatrix=projection_matrix,
                    renderer=p.ER_BULLET_HARDWARE_OPENGL,
                )
            finally:
                restore_overlay_after_observation()
        detections, rgb_image, depth_buffer, seg_mask = self.detect_objects()
        depth_image = self._depth_buffer_to_meters(depth_buffer)
        # Full-frame point cloud stays disabled (no consumer);
        # perception.unproject_depth_pixels does the per-object clouds.

        # Spawn order, matching the oracle's historical iteration order
        # (order feeds nothing planner-critical here, but keep it stable).
        visible_objects = [n for n in self.objects if n in detections]
        object_poses = {
            n: (detections[n].est_center, np.array([0.0, 0.0, 0.0, 1.0]))
            for n in visible_objects
        }
        boxels = self.generate_boxels(
            {name: (det.est_min, det.est_max)
             for name, det in detections.items()})

        return CameraObservation(
            rgb_image=rgb_image,
            depth_image=depth_image,
            visible_objects=visible_objects,
            object_poses=object_poses,
            boxels=boxels,
            seg_mask=seg_mask,
        )
    
    def detect_objects(self) -> Tuple[Dict[str, 'ObjectDetection'],
                                      np.ndarray, np.ndarray, np.ndarray]:
        """Render the fixed camera and estimate per-object AABBs (#P1 step 2).

        The light detection path shared by get_camera_observation and
        execution.refresh_object_aabbs: one ER_TINY_RENDERER pass
        (identical on GUI and DIRECT clients) +
        perception.detect_objects_from_render.  No boxel or shadow
        generation, no ExampleBrowser pane refresh.

        Returns (detections, rgb_image, depth_buffer, seg_mask) where
        detections maps detected object name -> perception.ObjectDetection
        and depth_buffer holds RAW [0,1] buffer values (metres conversion
        is the caller's concern).
        """
        view_matrix, projection_matrix = self._view_and_projection_matrices()
        # #P1 F19: the observation must not contain the debug overlay.
        # The boxel visualizer's phantom AABB fills are visual-only bodies
        # that TinyRenderer renders like any surface — under the GUI, a
        # shadow fragment's own translucent box intercepted its own sense
        # endpoints and hid objects from this very render.  Conceal the
        # overlay for exactly the duration of the camera pass.
        conceal_overlay_for_observation()
        try:
            _, _, rgb_array, depth_array, seg_array = p.getCameraImage(
                width=self.image_width,
                height=self.image_height,
                viewMatrix=view_matrix,
                projectionMatrix=projection_matrix,
                renderer=p.ER_TINY_RENDERER,
                physicsClientId=self.client_id,
            )
        finally:
            restore_overlay_after_observation()
        if self._page is not None:
            # Display only: a copy of what the robot sees, for the page
            # beside our own window (it shows what PyBullet's panes showed).
            self._page.offer_render(self.image_width, self.image_height,
                                    rgb_array, depth_array, seg_array,
                                    self.near_plane, self.far_plane, 'observation')
        rgb_image = np.array(rgb_array, dtype=np.uint8).reshape(
            (self.image_height, self.image_width, 4)
        )[:, :, :3]
        depth_buffer = np.asarray(depth_array, dtype=float).reshape(
            (self.image_height, self.image_width))
        seg_mask = np.asarray(seg_array).reshape(
            (self.image_height, self.image_width))
        body_id_to_name = {
            info.object_id: name for name, info in self.objects.items()
            if name not in ("plane", "table", "robot")
        }
        trays = frozenset(
            name for name, info in self.objects.items()
            if getattr(info, "is_tray", False))
        detections = detect_objects_from_render(
            seg_mask, depth_buffer, view_matrix, projection_matrix,
            body_id_to_name, self.camera_position[:2],
            self.table_surface_height,
            no_footprint_completion=trays)
        return detections, rgb_image, depth_buffer, seg_mask

    def _depth_buffer_to_meters(self, depth_buffer: np.ndarray) -> np.ndarray:
        """Convert depth buffer values to meters."""
        return self.far_plane * self.near_plane / (
            self.far_plane - (self.far_plane - self.near_plane) * depth_buffer
        )
    
    def oracle_detect_objects(self, check_occlusion: bool = True,
                              physics_client: Optional[int] = None
                              ) -> Tuple[List[str], Dict[str, Tuple[np.ndarray, np.ndarray]]]:
        """
        Oracle function to detect visible objects and their poses.

        Visibility is determined by casting rays from the camera to the
        8 corners of each object's AABB.  An object is visible if ANY ray
        reaches it (hit body == object body).  This catches partial
        visibility where an object edge sticks out from behind an occluder.

        Only used for initial scene observation — the sensing action uses
        ``sense_shadow_from_render()`` against the rendered observation.
        
        Returns:
            Tuple of (visible object names, dict of all object poses)
        """
        # Phase 3-B (TAMPURA bridge, P1): optionally target a specific pybullet
        # client.  None -> call p.* with NO physicsClientId, i.e. the EXACT
        # default-client path used on our own env (unchanged).  The find_dice
        # adapter passes their state-world client id so the oracle reads THEIR world.
        _pc = {} if physics_client is None else {"physicsClientId": physics_client}

        visible_objects = []
        object_poses = {}
        
        for name, obj_info in self.objects.items():
            if name in ["plane", "table", "robot"]:
                continue
            
            pos, orn = p.getBasePositionAndOrientation(obj_info.object_id, **_pc)
            position = np.array(pos)
            orientation = np.array(orn)
            
            obj_info.position = position
            obj_info.orientation = orientation
            
            is_visible = True
            if check_occlusion:
                aabb_min, aabb_max = p.getAABB(obj_info.object_id, **_pc)
                ray_targets = []
                for x in (aabb_min[0], aabb_max[0]):
                    for y in (aabb_min[1], aabb_max[1]):
                        for z in (aabb_min[2], aabb_max[2]):
                            ray_targets.append([x, y, z])

                cam = self.camera_position.tolist()
                # rayTestBatch numThreads=0: let Bullet pick max threads
                # (audit #69). Safe — Phase 1/4 calls are sequential w.r.t.
                # stepSimulation on this client.
                results = p.rayTestBatch(
                    [cam] * len(ray_targets), ray_targets, numThreads=0, **_pc
                )
                is_visible = any(
                    r[0] == obj_info.object_id for r in results
                )
            
            obj_info.is_visible = is_visible
            if is_visible:
                visible_objects.append(name)
            object_poses[name] = (position.copy(), orientation.copy())
        
        return visible_objects, object_poses

    def update_object_positions(self):
        """
        Synchronise every dynamic object's ObjectInfo with its current PyBullet
        pose.  Call this after any batch of physics steps (settling, pushing,
        etc.) so that downstream code never uses stale spawn-time positions.

        Static bodies (plane, table, robot) are skipped — they cannot move.
        """
        for name, obj_info in self.objects.items():
            if name in ("plane", "table", "robot"):
                continue
            pos, orn = p.getBasePositionAndOrientation(obj_info.object_id)
            obj_info.position = np.array(pos)
            obj_info.orientation = np.array(orn)

    def step_simulation(self, num_steps: int = 1):
        """Step the simulation forward (GUI client only — physics lives there)."""
        for _ in range(num_steps):
            p.stepSimulation(physicsClientId=self.client_id)
            telemetry.tick()

    def reset(self, scene_config: Optional[SceneConfig] = None):
        """
        Reset the environment to initial state.

        Args:
            scene_config: New scene layout.  ``None`` → reuse the config
                from ``__init__``.
        """
        if scene_config is not None:
            self.scene_config = scene_config
        for cid in (self.client_id, self.plan_client_id):
            p.resetSimulation(physicsClientId=cid)
            # Standard value.  Also twice in __init__ (both clients); they must stay equal.
            p.setGravity(0, 0, -9.81, physicsClientId=cid)
            p.setRealTimeSimulation(0, physicsClientId=cid)
            p.setAdditionalSearchPath(pybullet_data.getDataPath(),
                                      physicsClientId=cid)
        # BF#59 solver_iters: resetSimulation sets the iterations back to
        # PyBullet's 50 (measured by the hold_physics review), so the switch
        # re-applies them on our physics client after every reset.
        if slip_fixes.on('solver_iters'):
            p.setPhysicsEngineParameter(
                numSolverIterations=robot_utils.SOLVER_ITERATIONS,
                physicsClientId=self.client_id)
            _n = p.getPhysicsEngineParameters(
                physicsClientId=self.client_id)['numSolverIterations']
            print(f"  solver_iters: numSolverIterations {_n} on our world "
                  f"after reset (client {self.client_id})")
        self._gui_to_plan.clear()
        self.plan_robot_id = None
        self.objects.clear()
        self._setup_scene()

    def close(self):
        """Close both PyBullet connections (GUI + plan client).  An
        adopted executing client (B3(b)) belongs to the caller and stays
        connected; only the plan twin is closed."""
        if not getattr(self, "_adopted", False):
            try:
                p.disconnect(self.client_id)
            except Exception:
                pass
        try:
            p.disconnect(self.plan_client_id)
        except Exception:
            pass
