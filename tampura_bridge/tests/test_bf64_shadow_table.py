"""BF#64 (TB-1): the shadow caster takes their shortened table, not D8's
window W.

D8's window W (task_spec.WINDOW_X/Y) bounds free space and placement.  The
adapter also passed it to the shadow caster as its table, and
ShadowCalculator clamps every ray hit and the shadow box to its table
(shadow_calculator.py, Step 1 and Step 2).  Their generator samples cup
centres in y -0.4..0.4 (find_dice/env_generator.py) while W ends at y -0.28,
so a cup outside W got a shadow that was reversed or 0 thick, the F3 guard
dropped it, the plan never looked behind that cup and the die under it was
never found: 16 of the 17 all_searched runs of BF#63.  Seed 118: b_cups_ud
at (0.388, -0.304), its believed box y -0.334..-0.274.

The caster now takes their shortened table (panda_env_utils
get_shortened_table_dims, the table W was cut from, BF#11 (e)), as our own
env gives the caster the logical table; free space and placement keep W.
"""
import types

import numpy as np
import pybullet as p
import pytest

import robot_utils
from boxel_data import BoxelData, BoxelType
from shadow_calculator import ShadowCalculator
from tampura_bridge import env_adapter, task_spec

# Seed 118 (BF#63's generated scenes): the eye as logged
# (bf/BF64_shadow_table/s118_run.log:15) and b_cups_ud's believed box.
EYE_118 = np.array([0.17861445, 0.04880322, 0.58831882])
CUP_MIN = np.array([0.358, -0.334, 0.0])
CUP_MAX = np.array([0.418, -0.274, 0.065])


def _cup_shadows(table_x, table_y):
    c = p.connect(p.DIRECT)
    try:
        # A support for the rays at their table top (z = 0).
        col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[3, 3, 0.01],
                                     physicsClientId=c)
        p.createMultiBody(0, col, basePosition=[0.5, 0, -0.01],
                          physicsClientId=c)
        calc = ShadowCalculator(EYE_118, task_spec.TABLE_TOP_Z,
                                table_x_range=table_x, table_y_range=table_y)
        cup = BoxelData(boxel_type=BoxelType.OBJECT, min_corner=CUP_MIN.copy(),
                        max_corner=CUP_MAX.copy(), object_name='b_cups_ud')
        return calc.calculate_shadow_boxel(cup, [], physics_client=c)
    finally:
        p.disconnect(c)


def test_the_eye_is_the_one_seed_118_logged():
    assert np.allclose(task_spec.EYE_POSITION, EYE_118, atol=1e-6)


def test_the_shadow_table_is_their_shortened_table_and_holds_w():
    from tampura_environments.panda_utils.panda_env_utils import (
        get_shortened_table_dims)
    pose, width, length, _ = get_shortened_table_dims()
    (x0, x1), (y0, y1) = env_adapter.shadow_table_ranges()
    assert (x0, x1) == pytest.approx((pose[0][0] - width / 2,
                                      pose[0][0] + width / 2))
    assert (y0, y1) == pytest.approx((pose[0][1] - length / 2,
                                      pose[0][1] + length / 2))
    wx, wy = task_spec.WINDOW_X, task_spec.WINDOW_Y
    assert x0 <= wx[0] and wx[1] <= x1 and y0 <= wy[0] and wy[1] <= y1


def test_w_as_the_table_loses_the_shadow_of_seed_118s_cup():
    # The bug, kept as a statement about the caster: W cuts it to nothing.
    assert _cup_shadows(tuple(task_spec.WINDOW_X),
                        tuple(task_spec.WINDOW_Y)) == []


def test_their_table_keeps_it_behind_the_cup():
    xr, yr = env_adapter.shadow_table_ranges()
    shadows = _cup_shadows(xr, yr)
    assert len(shadows) == 1
    lo, hi = shadows[0].min_corner, shadows[0].max_corner
    # Behind the cup as the eye sees it: from its back face (y -0.334) away
    # from the camera, at least 3 cm deep, over the cup's x range.
    assert hi[1] == pytest.approx(CUP_MIN[1])
    assert lo[1] < CUP_MIN[1] - 0.03
    assert lo[0] <= CUP_MIN[0] + 1e-9 and hi[0] >= CUP_MAX[0] - 1e-9


def test_the_adopted_env_gives_the_caster_their_table_and_free_space_w():
    """TampuraWorldEnv on a world with their table and Panda and no task
    objects: the caster gets shadow_table_ranges(), free space keeps W."""
    from tampura_environments.panda_utils.panda_env_utils import (
        create_default_env)
    from tampura_environments.panda_utils.robot import PANDA_PATH
    before = robot_utils.robot_model()
    c = p.connect(p.DIRECT)
    env = None
    try:
        floor, _ = create_default_env(client=env_adapter._wrap_client(c))
        robot = p.loadURDF(PANDA_PATH, useFixedBase=True, physicsClientId=c)
        world = types.SimpleNamespace(
            client=types.SimpleNamespace(_client=c), floor=floor,
            robot=types.SimpleNamespace(body=robot), objects=[],
            categories=[])
        env = env_adapter.TampuraWorldEnv(world)
        (x0, x1), (y0, y1) = env_adapter.shadow_table_ranges()
        sc = env.shadow_calculator
        assert (sc.table_x_min, sc.table_x_max) == (x0, x1)
        assert (sc.table_y_min, sc.table_y_max) == (y0, y1)
        assert env._SAFE_TABLE_X_RANGE == tuple(task_spec.WINDOW_X)
        assert env._SAFE_TABLE_Y_RANGE == tuple(task_spec.WINDOW_Y)
    finally:
        if env is not None:
            p.disconnect(env.plan_client_id)
        p.disconnect(c)
        robot_utils.use_robot_model(before)
