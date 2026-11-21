"""Path 9: the executor's side of PLAN.md 11.14.  A look judges each named
region against its one render (look_action._judge).  A body standing in or
at the region is seen where it stands (the endpoints inside its believed box,
grown by look_views.LOOK_CONTENT_TOL_M) and hides what lies behind it, so a
region the image does not show beyond the sense tolerance is still_blocked
(a strike), never contains_nontarget or clear_but_empty and removed; a
support (a tray) standing there is such a body too.  The plan twin
(look_views.LookViews._evaluate) counts the same endpoints in this fixture:
the tests compare the two on one render.

The scene and the cameras are the plan twin's tests' (test_look_views,
test_look_caster_view); in this fixture the executing client is the twin's.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import look_action  # noqa: E402
import look_views  # noqa: E402
from boxel_data import BoxelType  # noqa: E402
from execution import sense_shadow_from_render  # noqa: E402
from perception import SENSE_MARGINAL_BLOCKED_FRACTION  # noqa: E402
from test_look_caster_view import AIM, BACK, EYE, _around, _cell  # noqa: E402
from test_look_views import _boxel, _render, world  # noqa: E402,F401

ABOVE = ((0.10, 0.0, 0.35), (0.10, 0.0, 0.0), (1.0, 0.0, 0.0))   # straight over the block


def _ids(world):
    o = world.env.objects
    return o['occluder'].object_id, o['die'].object_id, frozenset({o['plane'].object_id})


def _judged(world, region, render, target=None, as_tray=False):
    occ, die, supports = _ids(world)
    if as_tray:         # the block in supports, as the handler passes a tray
        supports = supports | {occ}
    return look_action._judge(region, die if target is None else target, render,
                              world.reg, world.env, world.robot, supports)


def _sense_alone(world, region, render, as_tray=False):
    """The sense as the look called it before PLAN.md 11.14."""
    occ, die, supports = _ids(world)
    if as_tray:
        supports = supports | {occ}
    depth_m, seg, view, proj = render
    return sense_shadow_from_render(region, die, depth_m, seg, view, proj,
                                    look_action._occluder_ids(world.reg, region, world.env),
                                    robot_id=world.robot, support_body_ids=supports)


def _twin(world, region, render):
    movable, _ = world.lv._movable(world.reg)
    return world.lv._statuses([look_views.region_goal(region)], render, movable,
                              world.reg)[region.id]


def test_a_cell_seen_through_its_caster_is_blocked_not_removed(world):
    """Seed 107's case: the cell starts at the block's back face and the
    camera looks through the block.  The sense alone takes the block for a
    body in the cell; the look counts the endpoints behind it as hidden."""
    cell, render = _cell(BACK), _render(world, EYE, AIM)
    occ = _ids(world)[0]
    alone = _sense_alone(world, cell, render)
    assert alone[0] == 'contains_nontarget' and alone[2] == {occ}
    outcome, frac, bodies, _bbox, _counts = _judged(world, cell, render)
    assert outcome == 'still_blocked' and bodies == set()
    assert frac > SENSE_MARGINAL_BLOCKED_FRACTION
    assert frac == pytest.approx(_twin(world, cell, render).total_frac)


def test_a_cell_a_centimetre_behind_its_caster_is_blocked_as_before(world):
    cell, render = _cell(BACK + 0.01), _render(world, EYE, AIM)
    assert _sense_alone(world, cell, render)[0] == 'still_blocked'
    outcome, frac, *_ = _judged(world, cell, render)
    assert outcome == 'still_blocked'
    assert frac == pytest.approx(_twin(world, cell, render).total_frac)


def test_a_body_in_a_region_hides_what_lies_behind_it(world):
    """The block stands in the region; from its side the rows behind it are
    hidden, the endpoints inside its box are the block."""
    region, render = _around(), _render(world, EYE, AIM)
    outcome, frac, *_ = _judged(world, region, render)
    assert outcome == 'still_blocked'
    assert SENSE_MARGINAL_BLOCKED_FRACTION < frac < 0.5
    assert frac == pytest.approx(_twin(world, region, render).total_frac)


def test_seen_from_straight_above_the_outcomes_stay(world):
    """A region the block fills, seen from straight above: every endpoint is
    inside the block's box, so the outcome is the sense's own; the target
    found and an empty region seen clear are as before.  A region 1 cm wider
    hides a strip beside the block under its top edge: blocked, as the twin
    says."""
    render = _render(world, *ABOVE)
    occ_id = _ids(world)[0]
    occ = world.reg.get_boxel('occluder')
    filled = _boxel('filled', BoxelType.SHADOW, occ.min_corner, [*occ.max_corner[:2], 0.2])
    assert _sense_alone(world, filled, render)[0] == 'contains_nontarget'
    outcome, _frac, bodies, *_ = _judged(world, filled, render)
    assert outcome == 'contains_nontarget' and bodies == {occ_id}
    assert _judged(world, filled, render, target=occ_id)[0] == 'found_target'
    wider = _boxel('wider', BoxelType.SHADOW, [0.04, -0.06, 0.0], [0.16, 0.06, 0.2])
    outcome, frac, *_ = _judged(world, wider, render)
    assert outcome == 'still_blocked'
    assert frac == pytest.approx(_twin(world, wider, render).total_frac)
    over_a = _render(world, (0.21, 0.0, 0.30), (0.21, 0.0, 0.0), up=(1.0, 0.0, 0.0))
    empty = world.reg.get_boxel('shadow_a')
    assert _sense_alone(world, empty, over_a)[0] == 'clear_but_empty'
    assert _judged(world, empty, over_a)[0] == 'clear_but_empty'


def test_a_support_standing_at_a_cell_hides_it_as_any_body_does(world):
    """The block passed as a support, as handle_look_action passes a tray
    (every is_tray body).  The sense ignores a support's surface and sees the
    cell behind the block clear; the look counts the endpoints behind the
    block, outside its box, as hidden, as the twin does: a strike, not
    removed.  Seen from straight above, it hides nothing outside its box in
    the region it fills (the sense's own outcome stands) and a strip of the
    wider region (blocked)."""
    cell, render = _cell(BACK), _render(world, EYE, AIM)
    assert _sense_alone(world, cell, render, as_tray=True)[0] == 'clear_but_empty'
    outcome, frac, bodies, *_ = _judged(world, cell, render, as_tray=True)
    assert outcome == 'still_blocked' and bodies == set()
    st = _twin(world, cell, render)
    assert st.blockers == ['occluder'] and frac == pytest.approx(st.total_frac)
    above = _render(world, *ABOVE)
    occ = world.reg.get_boxel('occluder')
    filled = _boxel('filled', BoxelType.SHADOW, occ.min_corner, [*occ.max_corner[:2], 0.2])
    assert _sense_alone(world, filled, above, as_tray=True)[0] == 'clear_but_empty'
    assert _judged(world, filled, above, as_tray=True)[0] == 'clear_but_empty'
    wider = _boxel('wider', BoxelType.SHADOW, [0.04, -0.06, 0.0], [0.16, 0.06, 0.2])
    outcome, frac, *_ = _judged(world, wider, above, as_tray=True)
    assert outcome == 'still_blocked'
    assert frac == pytest.approx(_twin(world, wider, above).total_frac)
