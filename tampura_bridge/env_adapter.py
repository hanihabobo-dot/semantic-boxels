"""#P4 B2: our env over TAMPURA's executing world (PAPER_AUDIT.txt P4.4 B2).

A subclass of BoxelTestEnv through B3(b)'s adopt-existing-client path: it
adopts their executing client (client 0, BF#4 (d)), registers the bodies of
their World from its identity map (their world.objects and
world.categories, the map their obs_from_camera_image applies, env.py:70-73)
and builds the plan twin in a fresh DIRECT client with their own
construction functions (the URDF, create_default_env, create_ycb).  It
declares the D4 eye and the window W from task_spec, points the shadow
caster at the plan twin (B3(c)), overrides the oracle to raise and
update_object_positions as a counted no-op (G16), and reset() to raise.
It overrides nothing that touches perception, boxel generation or the
plan-twin sync: those run as BoxelTestEnv's own code.

The object table carries no pose, orientation or AABB of any body (G8(a)):
ObjectInfo.size is the CLASS size from task_spec (D8's auto_cell input),
position and orientation stay None, and reading position raises (G16,
PoselessObjectInfo).
"""
from collections import Counter

import numpy as np
from pybullet_utils import bullet_client

from boxel_env import BoxelTestEnv
from boxel_types import ObjectInfo
from tampura_bridge import gate_hooks, task_spec


def _wrap_client(client_id):
    """A BulletClient over an existing connection, without owning it (its
    __del__ disconnects only a client its own process created)."""
    bc = bullet_client.BulletClient.__new__(bullet_client.BulletClient)
    bc._shapes = {}
    bc._pid = None
    bc._client = client_id
    return bc


class PoselessObjectInfo(ObjectInfo):
    """The bridge's object table entry: no pose (G8(a)).  Reading position
    is the oracle path (G2, G16) and raises; it may only be set to None."""

    @property
    def position(self):
        gate_hooks.oracle_called('ObjectInfo.position')

    @position.setter
    def position(self, value):
        if value is not None:
            gate_hooks.oracle_called('ObjectInfo.position set')


def symbol_names(categories):
    """Object symbols from the scene's category labels: the category
    itself when it occurs once, else category_k in scene order."""
    totals = Counter(categories)
    seen = Counter()
    names = []
    for cat in categories:
        if totals[cat] == 1:
            names.append(cat)
        else:
            names.append(f"{cat}_{seen[cat]}")
            seen[cat] += 1
    return names


class TampuraWorldEnv(BoxelTestEnv):
    """BoxelTestEnv adopting the executing world of their FindDiceEnv."""

    def __init__(self, world, gui: bool = False):
        self._world = world
        super().__init__(
            gui=gui,
            camera_position=np.array(task_spec.EYE_POSITION),
            camera_target=np.array(task_spec.EYE_TARGET),
            camera_up=np.array(task_spec.EYE_UP),
            image_width=task_spec.EYE_WIDTH,
            image_height=task_spec.EYE_HEIGHT,
            fov=task_spec.EYE_FOV_DEG,
            near_plane=task_spec.EYE_NEAR,
            far_plane=task_spec.EYE_FAR,
            adopt_client=world.client._client,
        )
        self.shadow_raycast_client = self.plan_client_id
        self.pick_contact_floor = task_spec.PICK_CONTACT_FLOOR
        self.reach_envelope = task_spec.REACH_ENVELOPE

    def _adopt_scene(self):
        from tampura_environments.panda_utils.panda_env_utils import (
            create_default_env, create_ycb)
        from tampura_environments.panda_utils.robot import PANDA_PATH
        w = self._world
        # D8: the window W bounds free space, placement and the shadow
        # caster (lateral shadows are clipped to it as ours are to the
        # table ranges); their table top is z = 0.
        self.table_surface_height = task_spec.TABLE_TOP_Z
        self.table_x_range = tuple(task_spec.WINDOW_X)
        self.table_y_range = tuple(task_spec.WINDOW_Y)
        self._SAFE_TABLE_X_RANGE = tuple(task_spec.WINDOW_X)
        self._SAFE_TABLE_Y_RANGE = tuple(task_spec.WINDOW_Y)
        self._tray_xy = None
        self.categories = {}

        # The plan twin, built in the plan client alone with their own
        # construction code: the table and its frame (static, never
        # synced after this), their Panda from its URDF, one YCB body per
        # task object.
        self._plan_bc = _wrap_client(self.plan_client_id)
        plan_floor, _ = create_default_env(client=self._plan_bc)
        floor = w.floor
        none = np.zeros(3)
        for name in ('plane', 'table'):
            # Their world has no ground plane; main() names both supports,
            # so both names map to their table (one body, one twin).
            self.objects[name] = PoselessObjectInfo(
                object_id=floor, name=name, position=None, orientation=None,
                size=none, is_visible=False, is_occluder=False)
        self._plan_register_twin(floor, plan_floor)
        robot = w.robot.body
        self.objects['robot'] = PoselessObjectInfo(
            object_id=robot, name='robot', position=None, orientation=None,
            size=none, is_visible=False, is_occluder=False)
        self.plan_robot_id = self._plan_load_urdf(robot, PANDA_PATH,
                                                  useFixedBase=True)
        names = symbol_names(list(w.categories))
        for body, cat, name in zip(w.objects, w.categories, names):
            self.objects[name] = PoselessObjectInfo(
                object_id=body, name=name, position=None, orientation=None,
                size=np.array(task_spec.CLASS_EXTENTS[cat]),
                is_visible=False,
                is_occluder=cat != task_spec.TARGET_CATEGORY)
            self.categories[name] = cat
            self._plan_register_twin(
                body, create_ycb(cat, use_concave=True, client=self._plan_bc))

    def target_symbol(self):
        """The one object symbol whose category is task_spec's target
        category (G10's pin)."""
        found = [n for n, c in self.categories.items()
                 if c == task_spec.TARGET_CATEGORY]
        if len(found) != 1:
            raise RuntimeError(f"expected one {task_spec.TARGET_CATEGORY!r} "
                               f"object, found {found}")
        return found[0]

    def task_body_ids(self):
        return frozenset(self.objects[n].object_id for n in self.categories)

    # ----- G16 ------------------------------------------------------------

    def oracle_detect_objects(self, *args, **kwargs):
        gate_hooks.oracle_called('oracle_detect_objects')

    def update_object_positions(self):
        gate_hooks.count_update_object_positions()

    def reset(self, *args, **kwargs):
        raise RuntimeError("the adopted world is TAMPURA's; it is never reset")
