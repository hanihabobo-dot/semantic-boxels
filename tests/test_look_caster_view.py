"""Path 9: a hidden cell judged through the block that casts it (PLAN.md
11.14), the plan twin's side, in the fixture.

Why (development run of 2026-11-13, seed 107, --look boxel, track/look
7537e0b, logs/run_2026-11-13_04-43-14): a look stood on the fixed camera's
side of the red block, its plan named the cell straight behind the block, the
image showed the block, the cell was removed as "seen without the target"
with the target in it, and the run ended "all searched".  The old rule on
both sides: a registered body whose box overlaps or touches a region is the
region's content and hides nothing.  A cell that starts at its caster's back
face touches the caster.

The rule now (look_views._content and _evaluate, look_action._judge): a body
standing in or at a region is seen at the endpoints inside its believed box
grown by look_views.LOOK_CONTENT_TOL_M, and hides the endpoints behind it as
any other body does.  The executor's side: tests/test_look_caster_executor.py.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sensing import look_views  # noqa: E402
from world.boxel_data import BoxelType  # noqa: E402
from test_look_views import OCC, _boxel, _render, world  # noqa: E402,F401

# The camera of test_a_body_in_front_is_a_blocker_not_a_loss: on the robot's
# side of the occluder, low, looking through it at the table behind.
EYE, AIM = (-0.05, 0.0, 0.08), (0.21, 0.0, 0.02)
BACK = OCC['centre'][0] + OCC['half'][0]            # the occluder's back face, x = 0.15


def _cell(x0):
    """A cell 0.10 m deep behind the occluder, starting at x0."""
    return _boxel('cell', BoxelType.SHADOW, [x0, -0.05, 0.0], [x0 + 0.10, 0.05, 0.05])


def _around():
    """A region the occluder (x 0.05 to 0.15) stands in: 1 cm of it in front
    of the block, 2 cm behind."""
    return _boxel('cell', BoxelType.SHADOW, [0.04, -0.05, 0.0], [BACK + 0.02, 0.05, 0.05])


def _status(world, cell):
    movable, _ = world.lv._movable(world.reg)
    return world.lv._statuses([look_views.region_goal(cell)], _render(world, EYE, AIM),
                              movable, world.reg)['cell']


def test_a_cell_a_centimetre_behind_the_block_is_hidden_by_it(world):
    """The rule for a cell that does not touch its caster (unchanged)."""
    st = _status(world, _cell(BACK + 0.01))
    assert st.revealed and st.blockers == ['occluder']
    assert st.total_frac > look_views.LOOK_TOL_REGION


def test_a_cell_that_touches_the_block_is_hidden_by_it_all_the_same(world):
    """Where the cell starts makes no difference to what the camera sees of
    it through the block: the endpoints on the block's back face are the
    block, the ones behind it are hidden by it."""
    st = _status(world, _cell(BACK))
    assert st.revealed and st.blockers == ['occluder']
    assert st.total_frac > look_views.LOOK_TOL_REGION


def test_a_body_standing_in_a_region_hides_what_lies_behind_it(world):
    """Seen from its side, the block hides the part of the region behind it;
    the endpoints inside its box are the block, seen, so only the rows
    behind it count."""
    st = _status(world, _around())
    assert st.revealed and st.blockers == ['occluder']
    assert look_views.LOOK_TOL_REGION < st.total_frac < 0.5


def test_stage_one_follows_the_same_rule(world):
    """The analytic score counts what the render counts."""
    _movable, boxes = world.lv._movable(world.reg)
    _d, _s, view, proj = _render(world, EYE, AIM)
    eye = np.array(EYE)
    _hard, total = world.lv._probe(look_views.region_goal(_cell(BACK)), eye, view, proj,
                                   boxes, True)
    assert total > look_views.LOOK_TOL_REGION
    _hard, total = world.lv._probe(look_views.region_goal(_around()), eye, view, proj,
                                   boxes, True)
    assert look_views.LOOK_TOL_REGION < total < 0.5
