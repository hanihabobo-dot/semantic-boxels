"""BF#65 x path 9 (track/evalfinal, 2026-11-19): the cover standing over an
interior region hides it from a look and is never its content, so a look
waits until a plan has moved the cover away, as the sense does.  Before the
fix a look from beside the cup "saw" the cup inside the region's box and
removed the region as contains_nontarget (find_dice seed 140, --look boxel
--eye arm --interior-regions on)."""
from types import SimpleNamespace

import numpy as np
import pytest

import interior_regions
import look_action
import look_views
from boxel_data import BoxelType


def _bd(id_, lo, hi, kind=BoxelType.OBJECT, **kw):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    return SimpleNamespace(id=id_, boxel_type=kind, min_corner=lo, max_corner=hi,
                           center=(lo + hi) / 2, object_name=id_, **kw)


class _Reg:
    def __init__(self, boxels):
        self.b = {x.id: x for x in boxels}

    def get_boxel(self, i):
        return self.b.get(i)

    def get_boxels_by_type(self, t):
        return [x for x in self.b.values() if x.boxel_type == t]

    def get_shadow_boxels(self):
        return self.get_boxels_by_type(BoxelType.SHADOW)


@pytest.fixture
def scene(monkeypatch):
    monkeypatch.setattr(interior_regions, 'ENABLED', True)
    cup = _bd('cup', (0.48, -0.26, 0.0), (0.54, -0.20, 0.06))
    inside = _bd('interior_of_cup', (0.495, -0.245, 0.0), (0.525, -0.215, 0.05),
                 kind=BoxelType.SHADOW, region_kind=interior_regions.KIND,
                 created_by_boxel_id='cup', created_by_object='cup')
    env = SimpleNamespace(objects={'cup': SimpleNamespace(object_id=7)})
    return cup, inside, _Reg([cup, inside]), env


def test_a_standing_cover_is_its_regions_cover(scene):
    cup, inside, reg, _ = scene
    assert interior_regions.standing_cover_of(reg, inside) is cup


def test_a_moved_cover_is_not(scene):
    cup, inside, reg, _ = scene
    cup.min_corner = cup.min_corner + 0.3
    cup.max_corner = cup.max_corner + 0.3
    assert interior_regions.standing_cover_of(reg, inside) is None


def test_off_means_no_cover(scene, monkeypatch):
    _, inside, reg, _ = scene
    monkeypatch.setattr(interior_regions, 'ENABLED', False)
    assert interior_regions.standing_cover_of(reg, inside) is None


def test_the_executor_counts_the_cover_as_an_occluder_not_as_content(scene):
    _, inside, reg, env = scene
    assert 7 in look_action._occluder_ids(reg, inside, env)
    assert 7 not in look_action._content_boxes(reg, inside, env)


def test_a_look_elsewhere_does_not_strike_an_interior_under_its_cover(scene):
    _, inside, reg, _ = scene
    lateral = _bd('shadow_of_cup', (0.54, -0.26, 0.0), (0.60, -0.20, 0.06), kind=BoxelType.SHADOW)
    reg.b[lateral.id] = lateral
    assert look_action._struck(['interior_of_cup', 'shadow_of_cup'], 'shadow_of_cup', reg) == ['shadow_of_cup']
    assert look_action._struck(['interior_of_cup'], 'interior_of_cup', reg) == ['interior_of_cup']


def test_a_moved_cover_lets_the_interior_take_strikes_again(scene):
    cup, inside, reg, _ = scene
    cup.min_corner = cup.min_corner + 0.3
    cup.max_corner = cup.max_corner + 0.3
    assert look_action._struck(['interior_of_cup'], 'elsewhere', reg) == ['interior_of_cup']


def test_off_strikes_as_before(scene, monkeypatch):
    _, inside, reg, _ = scene
    monkeypatch.setattr(interior_regions, 'ENABLED', False)
    assert look_action._struck(['interior_of_cup'], 'elsewhere', reg) == ['interior_of_cup']


def test_the_plan_twin_leaves_the_cover_out_of_the_regions_content(scene):
    _, inside, reg, _ = scene
    goal = SimpleNamespace(id='interior_of_cup', kind='region', lo=inside.min_corner,
                           hi=inside.max_corner)
    assert look_views.LookViews._content(goal, {7: 'cup'}, reg) == {}
