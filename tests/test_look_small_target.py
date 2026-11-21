"""Path 9, item L-10 (tracks/look/MANAGER_PLAN.md, section (d)): the look's
judgement does not see a target of the die's height.  A reproduction on the
fixture; the fix is NOT built (its design comes first), so the test that
states the right outcome is an expected failure.  When the fix lands the
marker goes, and the test that pins today's outcome with it.

Why.  look_action.handle_look_action judges every named region with
execution.sense_shadow_from_render, which takes its points from
perception.sense_ray_slices: the lowest layer lies SENSE_LOW_SLICE_OFFSET
(0.02 m) above the region's base, made for targets of 3 cm and more.  A point
is hidden only by a surface in front of it.  The die of find_dice is 17.8 mm
tall (tampura_bridge/task_spec.py:20, CLASS_EXTENTS['dice']): it stands under
every point, hides none, and its region is judged clear_but_empty and leaves
the belief with the target in it.  The image shows the die all the same: the
render's detections hold it, and today it is found only if monitor rule M-1
registers it from them (recorded here, not run).
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import perception  # noqa: E402
from tampura_bridge import task_spec  # noqa: E402
from test_look_centred import _centred_setup, _look  # noqa: E402
from test_look_correspondence import _Loop, _add_body, m1_calls  # noqa: E402,F401
from test_look_views import world  # noqa: E402,F401  (world is a fixture)

DIE = task_spec.CLASS_EXTENTS[task_spec.TARGET_CATEGORY]      # x, y, z in metres
CONTROL = (0.035, 0.035, 0.035)
REGION, CENTRE = 'shadow_a', (0.21, 0.0)                      # the fixture's hidden region


def _judge(world, extents):
    """One centred look at the region, with a box of ``extents`` standing at
    its centre as the target.  The look's result and the loop's state."""
    loop = _Loop(world)
    q = _centred_setup(world)
    _add_body(world, 'blue', CENTRE, half=tuple(e / 2.0 for e in extents))
    return _look(loop, ('blue', REGION, q), [REGION]), loop


def test_today_a_target_of_the_dies_height_leaves_its_region_judged_empty(world, m1_calls):
    """The defect, pinned: the die stands in the region and in the image,
    under every point of the grid; the region is judged empty and removed."""
    region = world.reg.get_boxel(REGION)
    slices, _ = perception.sense_ray_slices(region.min_corner, region.max_corner)
    assert min(s.z for s in slices) - region.min_corner[2] > DIE[2]      # the premise
    res, loop = _judge(world, DIE)
    assert res.reached
    assert res.outcomes[REGION] == 'clear_but_empty'
    assert res.found_in is None and res.reason == 'look_not_found' and not res.continue_
    assert world.reg.get_boxel(REGION) is None and REGION not in loop.shadows
    assert world.reg.get_boxel('blue') is None
    # the image did show it: rule M-1 is handed a detection of the target
    assert len(m1_calls) == 1 and 'blue' in m1_calls[0]['detections']


@pytest.mark.xfail(strict=True,
                   reason="L-10: the look's judgement does not see a target under 2 cm")
def test_a_target_of_the_dies_height_is_found_in_its_region(world, m1_calls):
    """The right outcome: a look at the region the die stands in finds it."""
    res, _ = _judge(world, DIE)
    assert res.outcomes[REGION] == 'found_target'
    assert res.found_in == REGION


def test_a_target_of_35_mm_is_found_in_its_region(world, m1_calls):
    """The control: the same look, the same place, a target the grid was made for."""
    res, _ = _judge(world, CONTROL)
    assert res.outcomes[REGION] == 'found_target'
    assert res.found_in == REGION
