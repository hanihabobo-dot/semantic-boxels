"""The F15(b) sliver path of execution.handle_sense_action with the pose
switches on (review A-02).  A body that renders under DETECTION_MIN_PIXELS
inside the sensed fragment is localized at min_pixels=1 and registered as
a first detection, and that registration must set a radius, not raise.

The real handler runs on a hand-made depth and segmentation buffer under a
top-down eye, with a stand-in env: no simulator body, no render.  The image
is coarse (64 x 48, about 19 mm a pixel on the table), so the sense grid's
12 mm spacing is sure to put an endpoint on each of the sliver's pixels."""
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pytest

from acting import execution
from sensing import perception
from sensing import pose_belief
from acting import slip_fixes
from sensing.belief import BeliefState
from world.boxel_data import BoxelData, BoxelRegistry, BoxelType

W, H = 64, 48
NEAR, FAR = 0.02, 5.0
EYE = (0.5, 0.0, 1.0)                 # straight above the table (z = 0)
TABLE, BLUE, TARGET = 0, 7, 9         # seg ids; the target is not in the image
BLUE_TOP = 0.04                       # the height of blue's visible pixels
NAMES = {BLUE: 'blue', TARGET: 'target'}


@pytest.fixture
def main_defaults():
    """The switches as main() sets them when no flag is given: M8, M9, M10
    and the aperture rule on, the slip fixes at their defaults."""
    saved, enabled = dict(pose_belief.SWITCHES), slip_fixes.ENABLED
    pose_belief.SWITCHES.update({k: True for k in saved})
    slip_fixes.configure('')
    yield
    pose_belief.SWITCHES.clear()
    pose_belief.SWITCHES.update(saved)
    slip_fixes.ENABLED = enabled


def _buffer(depth_m: float) -> float:
    """The raw depth buffer value of a metric depth (the inverse of _meters)."""
    return FAR * (1.0 - NEAR / depth_m) / (FAR - NEAR)


def _meters(buf):
    """BoxelTestEnv._depth_buffer_to_meters for this camera."""
    return FAR * NEAR / (FAR - (FAR - NEAR) * buf)


def _render(cols):
    """The table everywhere, and blue on row 24 at ``cols``."""
    view = p.computeViewMatrix(list(EYE), [EYE[0], EYE[1], 0.0], [0.0, 1.0, 0.0])
    proj = p.computeProjectionMatrixFOV(50.0, W / H, NEAR, FAR)
    seg = np.full((H, W), TABLE, dtype=int)
    buf = np.full((H, W), _buffer(EYE[2]))
    seg[24, cols] = BLUE
    buf[24, cols] = _buffer(EYE[2] - BLUE_TOP)
    return seg, buf, view, proj


def _env(seg, buf, view, proj):
    """What handle_sense_action asks of the env on this path."""
    def detect_objects():
        dets = perception.detect_objects_from_render(
            seg, buf, view, proj, NAMES, EYE[:2], 0.0)
        return dets, None, buf, seg
    return SimpleNamespace(
        objects={'blue': SimpleNamespace(object_id=BLUE),
                 'target': SimpleNamespace(object_id=TARGET)},
        detect_objects=detect_objects,
        _depth_buffer_to_meters=_meters,
        _view_and_projection_matrices=lambda: (view, proj),
        camera_position=np.array(EYE), table_surface_height=0.0,
        plan_body_id=lambda body: body, shadow_raycast_client=None,
        shadow_calculator=SimpleNamespace(
            calculate_shadow_boxel=lambda bd, solids, physics_client=None: []),
        # reboxelize_free_space: no free cells to carve here.
        generate_free_space=lambda obstacles, visualize=False: [],
        use_uniform_grid=True,
        annotate_free_space_surface=lambda cells: None)


@pytest.mark.parametrize('cols', [[32], [31, 32, 33]], ids=['1px', '3px'])
def test_a_sliver_discovery_is_registered_with_a_radius(main_defaults, cols):
    seg, buf, view, proj = _render(cols)
    env = _env(seg, buf, view, proj)
    assert env.detect_objects()[0] == {}              # under the detection minimum
    sliver = perception.detect_objects_from_render(
        seg, buf, view, proj, {BLUE: 'blue'}, EYE[:2], 0.0, min_pixels=1)['blue']
    assert sliver.pixel_count == len(cols) < perception.DETECTION_MIN_PIXELS
    c = sliver.est_center
    reg = BoxelRegistry()
    reg.add_boxel(BoxelData(id='shadow_000', boxel_type=BoxelType.SHADOW,
                            min_corner=np.array([c[0] - 0.06, c[1] - 0.06, 0.0]),
                            max_corner=np.array([c[0] + 0.06, c[1] + 0.06, 0.06])))

    result = execution.handle_sense_action(
        action_params=('target', 'shadow_000'), env=env, registry=reg,
        belief=BeliefState(['shadow_000'], 'target'), viz=None,
        target_name='target', robot_id=None,
        support_body_ids=frozenset({TABLE}), shadows=['shadow_000'],
        occluders=[], shadow_occluder_map={}, blocked_counts={},
        blocked_giveup_shadows=set(), nontarget_rediscovery_counts={},
        boxel_centers={}, boxel_to_pybullet={}, object_body_ids={},
        body_id_to_name=NAMES, show_free=False)

    assert result.reason == 'sense_contains_nontarget'
    blue = reg.get_boxel('blue')
    assert blue is not None and blue.boxel_type == BoxelType.OBJECT
    # A's formula with the sliver's own pixel step, and nothing else: no
    # yaw fit, no completion term (the rebuilt detection carries neither).
    half = 0.5 * float(np.max(blue.max_corner[:2] - blue.min_corner[:2]))
    assert blue.pose_radius == pytest.approx(
        pose_belief.DETECTION_PIXEL_NOISE_PX
        * pose_belief.pixel_footprint(sliver.pixel_steps)
        + pose_belief.YAW_NOISE['eye'] * half)
    assert not blue.yaw_valid and blue.body_extents is None
