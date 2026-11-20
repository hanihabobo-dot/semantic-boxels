"""BF#65 option 1 (D6, model tweak M2): the hiding region under a cover
whose class declares a cavity, its status rule, its carve, and the "seen
under a cover" rule of BF#65 (d).  Registry-level tests: a stub env with an
object table, a table height and a shadow calculator (no simulator)."""
from types import SimpleNamespace

import numpy as np
import pytest

import console_ui
import execution
import interior_regions as ir
from belief import BeliefState
from boxel_data import BoxelData, BoxelRegistry, BoxelType
from boxel_types import ObjectInfo
from perception import ObjectDetection
from shadow_calculator import ShadowCalculator

CUP = (0.0767, 0.0767, 0.0719)          # e_cups_ud's class box (task_spec)
CAVITY = (0.056, 0.057, 0.0624)         # its declared cavity
DIE = (0.0176, 0.0173, 0.0178)


@pytest.fixture(autouse=True)
def switch():
    ir.configure('on')
    yield
    ir.configure('off')


def _info(k, name, size, occluder, cavity=None):
    return ObjectInfo(object_id=k, name=name, position=None, orientation=None,
                      size=np.array(size), is_visible=False, is_occluder=occluder,
                      cavity=None if cavity is None else np.array(cavity))


def _env(cavity=CAVITY, extra=()):
    objects = {'table': _info(0, 'table', (0, 0, 0), False),
               'robot': _info(1, 'robot', (0, 0, 0), False),
               'cup': _info(2, 'cup', CUP, True, cavity),
               'block': _info(3, 'block', (0.06, 0.06, 0.12), True),
               'dice': _info(4, 'dice', DIE, False)}
    for i in extra:
        objects[i.name] = i
    return SimpleNamespace(
        objects=objects, table_surface_height=0.0, shadow_raycast_client=None,
        shadow_calculator=ShadowCalculator(np.array([0.18, 0.05, 0.59]), 0.0))


def _obj(name, x, y, size=CUP):
    lo = np.array([x - size[0] / 2, y - size[1] / 2, 0.0])
    return BoxelData(id=name, boxel_type=BoxelType.OBJECT, min_corner=lo,
                     max_corner=lo + np.array(size), object_name=name,
                     on_surface='table', surface_z=0.0)


def _box(name, kind, lo, hi):
    return BoxelData(id=name, boxel_type=kind, min_corner=np.array(lo, dtype=float),
                     max_corner=np.array(hi, dtype=float), on_surface='table',
                     surface_z=0.0)


def _registry(*boxels):
    reg = BoxelRegistry()
    for b in boxels:
        reg.add_boxel(b)
    return reg


def _det(name, body, lo, hi, px=6):
    return ObjectDetection(name=name, body_id=body, pixel_count=px,
                           est_min=np.array(lo, dtype=float),
                           est_max=np.array(hi, dtype=float))


# ----- the region ------------------------------------------------------------

def test_off_casts_nothing():
    ir.configure('off')
    reg = _registry(_obj('cup', 0.5, 0.0))
    assert ir.cast_first_observation(_env(), reg, ['dice']) == []
    assert [b.id for b in reg.boxels.values()] == ['cup']
    assert ir.standing_cover(reg, [0.5, 0.0, 0.01]) is None
    assert ir.withheld(reg, BeliefState([], 'dice'), ['dice']) == []


def test_a_cover_owns_the_region_under_it():
    cup = _obj('cup', 0.5, 0.1)
    block = _obj('block', 0.4, -0.2, (0.06, 0.06, 0.12))
    reg = _registry(cup, block)
    ids = ir.cast_first_observation(_env(), reg, ['dice'])
    assert ids == ['interior_of_cup']             # the solid block casts none
    r = reg.get_boxel('interior_of_cup')
    assert r.boxel_type == BoxelType.SHADOW and ir.is_interior(r)
    assert r.created_by_boxel_id == 'cup' and r.on_surface == 'table'
    assert r.min_corner == pytest.approx([0.5 - 0.028, 0.1 - 0.0285, 0.0])
    assert r.max_corner == pytest.approx([0.5 + 0.028, 0.1 + 0.0285, 0.0624])
    # Inside its cover's box; listed apart from the lateral fragments.
    assert np.all(r.min_corner >= cup.min_corner) and np.all(r.max_corner <= cup.max_corner)
    assert cup.interior_boxel_ids == ['interior_of_cup'] and cup.shadow_boxel_ids == []
    # The record names the kind only where it is not the default.
    assert r.to_dict()['region_kind'] == 'interior'
    assert 'region_kind' not in cup.to_dict()
    assert cup.to_dict()['interior_boxel_ids'] == ['interior_of_cup']
    assert 'interior_boxel_ids' not in block.to_dict()


def test_a_cavity_that_holds_no_target_class_casts_nothing():
    reg = _registry(_obj('cup', 0.5, 0.1))
    assert ir.cast_first_observation(_env(cavity=(0.015, 0.015, 0.06)), reg, ['dice']) == []
    assert ir.cast_first_observation(_env(cavity=(0.056, 0.057, 0.010)), reg, ['dice']) == []
    # No target named yet (our scenes choose it later): every non-occluder
    # class is a candidate.
    assert ir.cast_first_observation(_env(), reg, [None]) == ['interior_of_cup']


def test_holds_takes_either_quarter_turn():
    assert ir.holds((0.03, 0.05, 0.05), (0.045, 0.025, 0.04))
    assert not ir.holds((0.03, 0.05, 0.05), (0.045, 0.035, 0.04))
    assert not ir.holds((0.03, 0.05, 0.05), (0.02, 0.02, 0.06))


def test_status_rule_free_space_seen_before_gets_no_region():
    env = _env()
    cup = _obj('cup', 0.5, 0.1)
    # The whole footprint in a free cell: observed empty before the cup
    # came to stand there.
    reg = _registry(cup, _box('', BoxelType.FREE_SPACE, [0.4, 0.0, 0.0], [0.6, 0.2, 0.25]))
    assert ir.cast_for(env, reg, cup, ['dice'], first_observation=False) == []
    assert cup.interior_boxel_ids == []
    # The first observation has seen nothing before: unknown all the same.
    assert [p.id for p in ir.cast_for(env, reg, cup, ['dice'], first_observation=True)] \
        == ['interior_of_cup']
    # A footprint only partly in free space: unknown.
    cup2 = _obj('cup', 0.5, 0.1)
    reg2 = _registry(cup2, _box('', BoxelType.FREE_SPACE, [0.4, 0.0, 0.0], [0.5, 0.2, 0.25]))
    assert [p.id for p in ir.cast_for(env, reg2, cup2, ['dice'], first_observation=False)] \
        == ['interior_of_cup']


def test_a_held_or_stacked_body_casts_nothing():
    env = _env()
    cup = _obj('cup', 0.5, 0.1)
    cup.min_corner[2] += 0.2
    cup.max_corner[2] += 0.2
    assert ir.cast_for(env, _registry(cup), cup, ['dice'], first_observation=True) == []


def test_carve_keeps_one_region_per_point():
    env = _env()
    cup = _obj('cup', 0.5, 0.1)
    # An existing fragment takes the +x half of the cavity's footprint.
    frag = _box('shadow_of_block', BoxelType.SHADOW, [0.5, 0.0, 0.0], [0.7, 0.2, 0.2])
    reg = _registry(cup, frag)
    new = ir.cast_for(env, reg, cup, ['dice'], first_observation=True)
    assert len(new) == 1
    assert new[0].max_corner[0] == pytest.approx(0.5)
    assert new[0].min_corner[0] == pytest.approx(0.5 - 0.028)
    # A second cast for the same object (re-registered where it stood): the
    # first region already holds that space, nothing new.
    assert ir.cast_for(env, reg, cup, ['dice'], first_observation=True) == []
    # Re-registered 4 mm off: the remainder is a sliver, not a region.
    cup.min_corner[1] += 0.004
    cup.max_corner[1] += 0.004
    assert ir.cast_for(env, reg, cup, ['dice'], first_observation=True) == []


def test_bookkeep_enters_the_loops_lists():
    env = _env()
    cup = _obj('cup', 0.5, 0.1)
    reg = _registry(cup)
    belief = BeliefState([], 'dice')
    shadows, occ_map, centers = [], {}, {}
    ids = ir.bookkeep(ir.cast_for(env, reg, cup, ['dice'], first_observation=False),
                      shadows=shadows, shadow_occluder_map=occ_map,
                      boxel_centers=centers, belief=belief)
    assert ids == shadows == ['interior_of_cup']
    assert occ_map == {'interior_of_cup': ['cup']}
    assert belief.get_unknown_shadows() == ['interior_of_cup']
    assert centers['interior_of_cup'] == pytest.approx([0.5, 0.1, 0.0312])


# ----- seen under a cover (BF#65 (d)) -----------------------------------------

def _scene_104():
    """Scene 104's shape: the die's sliver estimate inside the cup's box."""
    env = _env()
    cup = _obj('cup', 0.31, -0.06)
    dice = _box('dice', BoxelType.OBJECT, [0.320, -0.057, 0.0], [0.322, -0.055, 0.019])
    dice.object_name = 'dice'
    reg = _registry(cup, dice)
    ir.cast_first_observation(env, reg, ['dice'])
    return env, reg, cup


def test_a_target_inside_a_standing_covers_box_is_not_an_object():
    env, reg, cup = _scene_104()
    # Taken out before the cast: the die's sliver box carved nothing.
    assert cup.interior_boxel_ids == ['interior_of_cup']
    assert reg.get_boxel('dice') is None and reg.dirty
    assert ir.seen_under('dice') == 'interior_of_cup'
    # The planner is offered that region alone.
    belief = BeliefState(['shadow_of_cup', 'shadow_of_block', 'interior_of_cup'], 'dice')
    assert sorted(ir.withheld(reg, belief, ['dice'])) == ['shadow_of_block', 'shadow_of_cup']
    # The record ends when the region was looked at ...
    belief.mark_sensed('interior_of_cup', found=False)
    assert ir.withheld(reg, belief, ['dice']) == []
    assert ir.seen_under('dice') is None


def test_the_record_ends_when_the_target_has_its_own_boxel():
    env, reg, cup = _scene_104()
    belief = BeliefState(['shadow_of_cup', 'interior_of_cup'], 'dice')
    reg.add_boxel(_obj('dice', 0.31, -0.06, DIE))
    assert ir.withheld(reg, belief, ['dice']) == []


def test_no_plan_through_the_one_region_releases_the_record():
    """The main loop's net: no plan while only the seen-under region was on
    offer ends the record for good, so every unknown region is offered; the
    target stays unregistered while the cover stands."""
    env, reg, cup = _scene_104()
    belief = BeliefState(['shadow_of_cup', 'interior_of_cup'], 'dice')
    assert ir.withheld(reg, belief, ['dice']) == ['shadow_of_cup']
    assert ir.release(['dice']) == ['interior_of_cup']
    assert ir.seen_under('dice') is None
    assert ir.withheld(reg, belief, ['dice']) == []
    assert ir.release(['dice']) == []                   # nothing left to end
    # A later frame shows the die under the cup again: still no object, and
    # no new record for the region that had no plan.
    dets = {'dice': _det('dice', 4, [0.320, -0.057, 0.0], [0.322, -0.055, 0.019])}
    assert execution.register_new_detections(
        env=env, registry=reg, belief=belief, viz=None, detections=dets,
        target_name='dice', shadows=[], occluders=[], shadow_occluder_map={},
        boxel_centers={}, boxel_to_pybullet={}, object_body_ids={}) == []
    assert reg.get_boxel('dice') is None
    assert ir.seen_under('dice') is None
    assert ir.withheld(reg, belief, ['dice']) == []
    # A new run starts clean.
    ir.configure('on')
    ir.note_seen_under('dice', cup, reg.get_boxel('interior_of_cup'))
    assert ir.seen_under('dice') == 'interior_of_cup'


def test_a_target_in_the_open_stays_registered():
    env = _env()
    cup = _obj('cup', 0.31, -0.06)
    dice = _obj('dice', 0.45, 0.10, DIE)
    reg = _registry(cup, dice)
    assert ir.cast_first_observation(env, reg, ['dice']) == ['interior_of_cup']
    assert reg.get_boxel('dice') is not None and ir.seen_under('dice') is None
    # Nor is a body inside a SOLID object's box taken out (no cavity).
    env2 = _env(cavity=None)
    cup2 = _obj('cup', 0.31, -0.06)
    dice2 = _box('dice', BoxelType.OBJECT, [0.320, -0.057, 0.0], [0.322, -0.055, 0.019])
    reg2 = _registry(cup2, dice2)
    assert ir.cast_first_observation(env2, reg2, ['dice']) == []
    assert reg2.get_boxel('dice') is not None


def test_standing_cover_needs_the_cover_over_its_region():
    env, reg, cup = _scene_104()
    pt = [0.321, -0.056, 0.0095]
    assert ir.standing_cover(reg, pt)[0] is cup
    # The held cover is not standing.
    assert ir.standing_cover(reg, pt, exclude={'cup'}) is None
    # Moved away (the placement re-poses its boxel): the region stays, the
    # point is in the open.
    cup.min_corner = cup.min_corner + np.array([0.2, 0.2, 0.0])
    cup.max_corner = cup.max_corner + np.array([0.2, 0.2, 0.0])
    assert ir.standing_cover(reg, pt) is None
    assert reg.get_boxel('interior_of_cup') is not None


def test_register_new_detections_keeps_a_covered_target_out():
    """The frame's registration (F20): the target seen inside a standing
    cover's box is recorded, not registered; with the cover held it is
    registered as before."""
    env, reg, cup = _scene_104()
    ir.configure('on')                                  # clears the record
    dets = {'dice': _det('dice', 4, [0.320, -0.057, 0.0], [0.322, -0.055, 0.019])}
    kw = dict(env=env, registry=reg, belief=BeliefState([], 'dice'), viz=None,
              detections=dets, target_name='dice', shadows=[], occluders=[],
              shadow_occluder_map={}, boxel_centers={}, boxel_to_pybullet={},
              object_body_ids={})
    assert execution.register_new_detections(**kw) == []
    assert reg.get_boxel('dice') is None
    assert ir.seen_under('dice') == 'interior_of_cup'
    # With the cup in the hand the die is in the open: registered.  (The
    # stub env has no simulator; stop before the census refresh.)
    env.plan_body_id = lambda body: body
    with pytest.raises(AttributeError):                 # compute_shadow_blockers
        execution.register_new_detections(**dict(kw, skip_names=frozenset({'cup'})))
    assert reg.get_boxel('dice') is not None


# ----- the truthful record ------------------------------------------------------

def test_holds_detection_only_for_interior_regions():
    env, reg, cup = _scene_104()
    region = reg.get_boxel('interior_of_cup')
    inside = _det('dice', 4, [0.30, -0.07, 0.0], [0.318, -0.052, 0.018], px=60)
    outside = _det('dice', 4, [0.40, 0.10, 0.0], [0.418, 0.118, 0.018], px=60)
    assert ir.holds_detection(region, inside)
    assert not ir.holds_detection(region, outside)
    assert not ir.holds_detection(region, None)
    lateral = _box('shadow_of_cup', BoxelType.SHADOW, [0.29, -0.08, 0.0], [0.33, -0.04, 0.07])
    assert not ir.holds_detection(lateral, inside)


def test_console_names_the_space_under_a_cover():
    assert console_ui._place('interior_of_e_cups_ud') == 'the space under `e_cups_ud`'
    assert console_ui._place('interior_of_e_cups_ud__r1') == 'the space under `e_cups_ud`'
    assert console_ui._place('shadow_of_e_cups_ud__03') == 'the space behind `e_cups_ud`'
    assert console_ui.describe_step('sense', ['dice', 'interior_of_cup', 'cfg:q']) \
        == 'Looking into the space under `cup` for `dice`'
