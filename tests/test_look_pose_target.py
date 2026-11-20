"""track/evalfinal (2026-11-19, a3fa79c and its review): a pose look (?o a
body other than the target) judges its named regions for the MISSION target.
With the target inside the occluder's shadow the region is found and the
target registered (a replan follows); the old judging for ?o marked that
region not_here with the target in it."""
import look_action
from test_look_views import world                                   # noqa: F401
from test_look_correspondence import _Loop, _look_setup, _add_body, m1_calls   # noqa: F401


def _pose_look(world, blue_xy):
    loop = _Loop(world, target='blue')
    q, v, named = _look_setup(world)
    _add_body(world, 'blue', blue_xy)
    res = loop.look(('occluder', 'occluder', v, q), list(named) + ['occluder'])
    return res, loop


def test_a_pose_look_finds_the_target_in_a_named_region(world, m1_calls):
    res, loop = _pose_look(world, (0.21, 0.0))
    assert 'found_target' in res.outcomes.values()
    assert loop.belief.target_found_in is not None
    assert world.reg.get_boxel('blue') is not None
    assert 'blue' in res.registered


def test_a_pose_look_with_the_target_elsewhere_finds_nothing(world, m1_calls):
    res, loop = _pose_look(world, (0.33, -0.25))
    assert 'found_target' not in res.outcomes.values()
    assert loop.belief.target_found_in is None


def test_the_old_judging_would_have_marked_the_region_empty(world, m1_calls, monkeypatch):
    monkeypatch.setattr(look_action, '_judged_body',
                        lambda env, obj, t: (str(obj), env.objects[obj].object_id))
    res, loop = _pose_look(world, (0.21, 0.0))
    assert loop.belief.target_found_in is None
