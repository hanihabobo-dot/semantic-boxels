"""Path 9: a hidden cell judged through the block that casts it (PLAN.md
11.14).  A reproduction of the plan twin's side of the defect in the fixture;
the fix is NOT built (it waits for a decision), so the test that states the
right rule is an expected failure.  When the fix lands the marker goes, and
the test that pins today's behaviour with it.

Why (development run of 2026-11-13, seed 107, --look boxel, track/look
7537e0b, logs/run_2026-11-13_04-43-14): a look stood on the fixed camera's
side of the red block, its plan named the cell straight behind the block, the
image showed the block, the cell was removed as "seen without the target"
with the target in it, and the run ended "all searched".  The rule on both
sides: a registered body whose box overlaps or touches a region is the
region's content and hides nothing (look_views._content,
look_action._occluder_ids).  A cell that starts at its caster's back face
touches the caster.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import look_views  # noqa: E402
from boxel_data import BoxelType  # noqa: E402
from test_look_views import OCC, _boxel, _render, world  # noqa: E402,F401

# The camera of test_a_body_in_front_is_a_blocker_not_a_loss: on the robot's
# side of the occluder, low, looking through it at the table behind.
EYE, AIM = (-0.05, 0.0, 0.08), (0.21, 0.0, 0.02)
BACK = OCC['centre'][0] + OCC['half'][0]            # the occluder's back face, x = 0.15


def _cell(x0):
    """A cell 0.10 m deep behind the occluder, starting at x0."""
    return _boxel('cell', BoxelType.SHADOW, [x0, -0.05, 0.0], [x0 + 0.10, 0.05, 0.05])


def _status(world, cell):
    movable, _ = world.lv._movable(world.reg)
    return world.lv._statuses([look_views.region_goal(cell)], _render(world, EYE, AIM),
                              movable, world.reg)['cell']


def test_a_cell_a_centimetre_behind_the_block_is_hidden_by_it(world):
    """The rule as it holds today for a cell that does not touch its caster."""
    st = _status(world, _cell(BACK + 0.01))
    assert st.revealed and st.blockers == ['occluder']
    assert st.total_frac > look_views.LOOK_TOL_REGION


def test_today_the_same_view_of_a_cell_that_touches_the_block_counts_as_clear(world):
    """The defect, pinned: move the cell 1 cm so that it starts at the block's
    back face, and the block in front of it hides nothing."""
    st = _status(world, _cell(BACK))
    assert st.revealed and st.blockers == [] and st.total_frac <= look_views.LOOK_TOL_REGION


@pytest.mark.xfail(strict=True, reason="PLAN.md 11.14: not built; a body that touches a "
                                       "region counts as content and hides nothing")
def test_a_cell_that_touches_the_block_is_hidden_by_it_all_the_same(world):
    """The right rule: where the cell starts makes no difference to what the
    camera sees of it through the block."""
    st = _status(world, _cell(BACK))
    assert st.revealed and st.blockers == ['occluder']
    assert st.total_frac > look_views.LOOK_TOL_REGION
