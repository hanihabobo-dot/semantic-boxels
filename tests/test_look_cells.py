"""Path 9: in a look mode a hidden region is cut into cells one look can hold.

Why (smoke of 2026-11-12, seed 0, --look centred, track/look fb02d51): the
target's region, the shadow of the green block, is 0.267 by 0.272 m.  No
reachable arm-camera view holds all of it (80 poses tried: 62 no_ik, 10 out of
frame, 8 hidden by the block itself), so the region had no look and the
planner had no plan.  A look can only be planned for a region its image
holds, so the regions follow the camera: ShadowCalculator.max_fragment_side,
set to observe_views.look_cell_side() when --look is on, None otherwise.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sensing import observe_views  # noqa: E402
from acting import robot_utils  # noqa: E402
from world.boxel_data import BoxelData, BoxelType  # noqa: E402
from world.shadow_calculator import ShadowCalculator  # noqa: E402
from test_look_views import _boxel, world  # noqa: E402,F401

# Seed 0's two regions as the first scan made them (run_2026-11-12_23-37-29).
GREEN_LO, GREEN_HI = (-0.226, 0.228, 0.325), (0.041, 0.500, 0.453)
RED_LO, RED_HI = (-0.033, -0.220, 0.325), (0.071, 0.112, 0.461)


def _calc():
    return ShadowCalculator(np.array([0.1, -0.8, 0.7]), 0.325,
                            table_x_range=(-0.4, 0.6), table_y_range=(-0.5, 0.5))


def _frag(lo, hi, parent='green_object'):
    return BoxelData(boxel_type=BoxelType.SHADOW, min_corner=np.array(lo, dtype=float),
                     max_corner=np.array(hi, dtype=float), created_by_object=parent)


def _tiles(cells, lo, hi):
    """The cells cover the box [lo, hi] exactly, with no overlap."""
    lo, hi = np.array(lo, dtype=float), np.array(hi, dtype=float)
    assert np.allclose(np.min([c.min_corner for c in cells], axis=0), lo)
    assert np.allclose(np.max([c.max_corner for c in cells], axis=0), hi)
    vol = sum(float(np.prod(c.max_corner - c.min_corner)) for c in cells)
    assert vol == pytest.approx(float(np.prod(hi - lo)))
    for i, a in enumerate(cells):
        for b in cells[i + 1:]:
            overlap = np.minimum(a.max_corner, b.max_corner) - np.maximum(a.min_corner, b.min_corner)
            assert not np.all(overlap > 1e-9)


def test_the_cell_side_is_what_one_look_holds_from_the_lowest_standoff():
    h = robot_utils.WRIST_CAMERA_HEIGHT
    f = (h / 2.0) / math.tan(math.radians(robot_utils.WRIST_CAMERA_FOV_DEG) / 2.0)
    held = 2.0 * min(observe_views.LOOK_STANDOFFS) * ((h - 1) / 2.0 - observe_views.LOOK_IMAGE_MARGIN_PX) / f
    assert observe_views.look_cell_side() == pytest.approx(held * observe_views.LOOK_CELL_SLACK)
    assert 0.0 < observe_views.LOOK_CELL_SLACK <= 1.0
    assert 0.14 < observe_views.look_cell_side() < held


def test_without_a_cap_the_fragments_are_returned_as_they_are():
    calc = _calc()
    assert calc.max_fragment_side is None
    frags = [_frag(GREEN_LO, GREEN_HI), _frag(RED_LO, RED_HI, 'red_object')]
    assert calc._cap_fragments(frags) is frags


def test_a_region_over_the_cap_is_cut_into_equal_cells_that_tile_it():
    calc = _calc()
    calc.max_fragment_side = cap = observe_views.look_cell_side()
    cells = calc._cap_fragments([_frag(GREEN_LO, GREEN_HI)])
    assert len(cells) == 4
    _tiles(cells, GREEN_LO, GREEN_HI)
    for c in cells:
        size = c.max_corner - c.min_corner
        assert size[0] <= cap + 1e-9 and size[1] <= cap + 1e-9
        assert size[0] == pytest.approx(0.267 / 2) and size[1] == pytest.approx(0.272 / 2)
        assert c.min_corner[2] == GREEN_LO[2] and c.max_corner[2] == GREEN_HI[2]
        assert c.boxel_type == BoxelType.SHADOW and c.created_by_object == 'green_object'
        assert c.id == ''                       # the callers name the fragments, as before
    # A fixed order (x outer, y inner), so the fragments' names replay.
    keys = [(round(float(c.min_corner[0]), 6), round(float(c.min_corner[1]), 6)) for c in cells]
    assert keys == sorted(keys)


def test_only_a_side_over_the_cap_is_cut():
    calc = _calc()
    calc.max_fragment_side = cap = observe_views.look_cell_side()
    cells = calc._cap_fragments([_frag(RED_LO, RED_HI, 'red_object')])
    n_y = int(math.ceil((RED_HI[1] - RED_LO[1]) / cap - 1e-9))
    assert len(cells) == n_y and n_y >= 2
    _tiles(cells, RED_LO, RED_HI)
    for c in cells:
        assert c.min_corner[0] == RED_LO[0] and c.max_corner[0] == RED_HI[0]
        assert c.created_by_object == 'red_object'


def test_a_region_within_the_cap_stays_the_same_object():
    calc = _calc()
    calc.max_fragment_side = observe_views.look_cell_side()
    small = _frag((0.0, 0.0, 0.325), (0.10, 0.12, 0.40))
    big = _frag(GREEN_LO, GREEN_HI)
    out = calc._cap_fragments([small, big])
    assert out[0] is small and len(out) == 5


def test_the_shadow_code_returns_the_same_region_cut_or_whole(world):
    """calculate_shadow_boxel with the cap returns cells that tile exactly the
    fragments it returns without it."""
    occ = _boxel('occluder', BoxelType.OBJECT, [0.05, -0.05, 0.0], [0.15, 0.05, 0.15])
    occ.object_name = 'occluder'
    calc = ShadowCalculator(np.array([-0.9, 0.0, 0.5]), 0.0,
                            table_x_range=(-0.4, 0.6), table_y_range=(-0.5, 0.5))
    whole = calc.calculate_shadow_boxel(occ, [], physics_client=world.cid)
    assert len(whole) == 1
    size = whole[0].max_corner - whole[0].min_corner
    calc.max_fragment_side = cap = observe_views.look_cell_side()
    cells = calc.calculate_shadow_boxel(occ, [], physics_client=world.cid)
    assert max(size[0], size[1]) > cap, "the test needs a shadow longer than one cell"
    assert len(cells) > 1
    _tiles(cells, whole[0].min_corner, whole[0].max_corner)
    for c in cells:
        s = c.max_corner - c.min_corner
        assert s[0] <= cap + 1e-9 and s[1] <= cap + 1e-9
        assert c.created_by_object == whole[0].created_by_object


def test_a_cell_has_a_straight_look_and_the_uncut_region_has_none(world):
    """One cell under the camera at the lowest standoff passes at both wrist
    yaws, the fingers in the image included; a 0.27 m region there is out of
    the frame at both.  The cell starts 1.5 cm behind the fixture's occluder
    (x 0.05 to 0.15, 0.15 m tall), so no ray from straight above meets it."""
    side = observe_views.look_cell_side()
    cx = 0.165 + side / 2
    start = world.views._arm()
    world.views.last_stats = {'twin_render_s': 0.0, 'twin_renders': 0, 'look_ik': 0,
                              'sense_view': 0, 'look_config': 0, 'sense_fallback': 0}
    lowest = (min(observe_views.LOOK_STANDOFFS),)
    world.reg.add_boxel(_boxel('shadow_cell', BoxelType.SHADOW,
                               [cx - side / 2, -side / 2, 0.0], [cx + side / 2, side / 2, 0.05]))
    cell = world.reg.get_boxel('shadow_cell')
    ok = world.views.look_configs(cell, lowest, (0.0,), None)
    world.views._set_arm(start)
    notes = world.views.last_look_notes['shadow_cell']
    assert [n.verdict for n in notes] == ['ok', 'ok'], notes
    assert len(ok) == 2
    world.reg.add_boxel(_boxel('shadow_whole', BoxelType.SHADOW,
                               [cx - 0.135, -0.135, 0.0], [cx + 0.135, 0.135, 0.05]))
    whole = world.reg.get_boxel('shadow_whole')
    none = world.views.look_configs(whole, lowest, (0.0,), None)
    world.views._set_arm(start)
    assert none == []
    assert {n.verdict for n in world.views.last_look_notes['shadow_whole']} == {'frame'}
