"""Path 9: the object-centred look (--look centred), the reference arm that uses
no boxel model in the look.  Hani 2026-11-07, verbatim in tracks/look/PLAN.md
section 11: "so the baseline is not using boxles at all in the look action and
we try to improve on that somehow by using boxels or at least test if that is
possible".

1. The generated domain is current and tight: no sense, no observe, none of the
   boxel look's reveal facts, every declared predicate used, none used but
   undeclared; PDDLStream plans with it.
2. CENTRED_SPEC (look_action.py) is the PDDL action, atom for atom.
3. The planner's init in centred mode: look_for and look_config (the tag's
   observe rule over the object the look is about), no reveal facts, only
   declared predicates, a removed configuration leaves the facts.
4. The handler on a synthetic scene: what the render may write is the one
   named hypothesis and the target, nothing else.
5. What path 8's inspect uses (PLAN section 13): LookResult.reached,
   look_configs and init_facts with a standoff of their own, a pose look at a
   pose that is already known and one from a changed standoff.
"""
import os
import sys
from pathlib import Path

import numpy as np
import pybullet as p
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import look_action  # noqa: E402
import look_domain  # noqa: E402
import m8_domain  # noqa: E402
import observe_views  # noqa: E402
import robot_utils  # noqa: E402
from test_look_correspondence import (_Loop, _add_body, _home, _known,  # noqa: E402,F401
                                      m1_calls)
from boxel_data import BoxelType  # noqa: E402
from test_look_views import _boxel, world  # noqa: E402,F401  (world is a fixture)

CENTRED_TEXT = look_domain.read(look_domain.CENTRED_FILE)
STREAM_TEXT = (ROOT / 'pddl' / 'stream.pddl').read_text(encoding='utf-8')
ACTIONS = {'look', 'move', 'pick', 'place', 'place_hiding', 'stack'}
GONE_WORDS = ('sense', 'observe', 'view_clear', 'blocks_view', 'marginally_blocked',
              'is_shadow', 'is_tray', 'is_view', 'view_blocked', 'reveals',
              'look_clear', 'look_blocked', 'blocks_look_at', 'config_for_boxel ?q ?v')


def _code(text):
    return '\n'.join(line.split(';', 1)[0] for line in text.splitlines())


# ----- 1. the file -------------------------------------------------------------

def test_the_mode_names():
    assert [look_domain.mode_of(v) for v in (None, False, 'off', True, 'on', 'boxel', 'centred')] == \
        ['off', 'off', 'off', 'boxel', 'boxel', 'boxel', 'centred']
    with pytest.raises(ValueError):
        look_domain.mode_of('both')


def test_the_generated_file_is_current():
    assert CENTRED_TEXT == look_domain.generate(look_domain.read(look_domain.LIVE_FILE), 'centred')


def test_domain_file_chooses_by_mode():
    assert look_domain.domain_file('off', True) == m8_domain.domain_file(True)
    assert look_domain.domain_file('boxel', True) == look_domain.GENERATED_FILE
    assert look_domain.domain_file('on', True) == look_domain.GENERATED_FILE
    assert look_domain.domain_file('centred', True) == look_domain.CENTRED_FILE
    with pytest.raises(ValueError):
        look_domain.domain_file('centred', False)


def test_actions_and_no_derived_predicate():
    assert set(look_domain.action_specs(CENTRED_TEXT)) == ACTIONS
    assert look_domain.derived_specs(CENTRED_TEXT) == {}


def test_sense_observe_and_the_boxel_looks_facts_are_gone():
    code = _code(CENTRED_TEXT)
    for word in GONE_WORDS:
        assert word not in code, word
    assert 'look_config' in code and 'look_for' in code


def test_every_declared_predicate_is_used_and_every_used_one_declared():
    uses = look_domain.predicate_uses(CENTRED_TEXT, STREAM_TEXT)
    declared = look_domain.declared_predicates(CENTRED_TEXT)
    assert len(declared) == len(set(declared))
    assert sorted(uses) == sorted(declared), \
        f"used but not declared: {sorted(set(uses) - set(declared))}"
    assert [n for n, c in uses.items() if c == 0] == []


def test_the_other_actions_are_the_boxel_looks():
    boxel = look_domain.action_specs(look_domain.read(look_domain.GENERATED_FILE))
    centred = look_domain.action_specs(CENTRED_TEXT)
    for name in ACTIONS - {'look'}:
        assert centred[name] == boxel[name], name


def test_the_centred_look_is_sense_and_observe_in_one_without_a_viewpoint_boxel():
    spec = look_domain.action_specs(CENTRED_TEXT)['look']
    assert spec['parameters'] == ['?o', '?h', '?q']
    assert spec['pre'] == {(n, True) for n in
                           ('look_for', 'Config', 'handempty', 'at_config', 'look_config')}
    assert spec['eff'] == {('obj_at_boxel', True, False), ('obj_at_boxel_KIF', True, False),
                           ('obj_pose_known', True, False)}
    assert spec['eff_cond'] == set()


# ----- 2. the contract ---------------------------------------------------------

def test_the_spec_is_the_pddl_action():
    spec = look_domain.action_specs(CENTRED_TEXT)['look']
    c = look_action.CENTRED_SPEC
    assert spec['parameters'] == c['parameters']
    assert spec['pre'] == {(n, True) for n in c['pre']}
    assert spec['eff'] == set(c['eff'])
    assert spec['eff_cond'] == c['eff_cond']
    assert look_action.SPECS == {'boxel': look_action.LOOK_SPEC, 'centred': c}


def test_every_spec_entry_says_what_python_does():
    c = look_action.CENTRED_SPEC
    for key, (kind, text) in c['pre'].items():
        assert kind in ('static', 'check', 'render'), key
        assert text, key
    for key, (kind, text) in c['eff'].items():
        assert kind == 'write' and text, key
    assert set(c['monitor']) == {'M-1'}


# ----- PDDLStream plans with it ------------------------------------------------

PDDLSTREAM = Path(os.environ.get('PDDLSTREAM_PATH', str(ROOT.parent / 'pddlstream_lib')))
needs_solver = pytest.mark.skipif(not (PDDLSTREAM / 'downward' / 'builds').is_dir(),
                                  reason="FastDownward is not built")


def _solve(init, goal, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(PDDLSTREAM))
    from pddlstream.algorithms.meta import solve
    from pddlstream.language.constants import PDDLProblem
    from pddlstream.language.generator import from_gen_fn
    stream_map = {
        'sample-grasp': from_gen_fn(lambda o: iter([('g_' + o,)])),
        'plan-motion': from_gen_fn(lambda q1, q2: iter([(f't_{q1}_{q2}',)])),
        'compute-kin': from_gen_fn(lambda o, b, g: iter([])),
        'compute-stack-kin': from_gen_fn(lambda o, on, g: iter([])),
    }
    problem = PDDLProblem(CENTRED_TEXT, {}, STREAM_TEXT, stream_map, init, goal)
    plan, _cost, _cert = solve(problem, algorithm='adaptive', max_time=60, verbose=False)
    return None if plan is None else [(a.name, tuple(a.args)) for a in plan]


def _toy(extra=(), skip=()):
    """The arm is at q0; qv is straight over the occluder; the target may be at region."""
    init = [
        ('Boxel', 'view__qv'), ('Boxel', 'home'), ('Boxel', 'region'), ('Boxel', 'target'),
        ('Obj', 'target'), ('Config', 'q0'), ('Config', 'qv'), ('at_config', 'q0'),
        ('handempty',), ('config_for_boxel', 'q0', 'home'),
        ('config_for_boxel', 'qv', 'view__qv'),
        ('look_for', 'target', 'region'), ('look_config', 'qv', 'region'),
    ]
    return [f for f in init if f not in skip] + list(extra)


@needs_solver
def test_a_look_finds_the_target_at_the_hypothesis(tmp_path, monkeypatch):
    goal = ('and', ('obj_at_boxel', 'target', 'region'),
            ('obj_at_boxel_KIF', 'target', 'region'), ('obj_pose_known', 'target'))
    plan = _solve(_toy(), goal, tmp_path, monkeypatch)
    assert plan is not None and [n for n, _ in plan] == ['move', 'look']
    assert plan[1][1] == ('target', 'region', 'qv')


@needs_solver
def test_a_hypothesis_without_a_look_configuration_cannot_be_looked_at(tmp_path, monkeypatch):
    plan = _solve(_toy(skip=[('look_config', 'qv', 'region')]),
                  ('obj_at_boxel', 'target', 'region'), tmp_path, monkeypatch)
    assert plan is None


@needs_solver
def test_the_pose_look_is_the_same_action(tmp_path, monkeypatch):
    init = _toy([('look_for', 'target', 'target'), ('look_config', 'qv', 'target'),
                 ('obj_at_boxel', 'target', 'target'),
                 ('obj_at_boxel_KIF', 'target', 'target')],
                skip=[('look_for', 'target', 'region'), ('look_config', 'qv', 'region')])
    plan = _solve(init, ('obj_pose_known', 'target'), tmp_path, monkeypatch)
    assert plan is not None and [n for n, _ in plan] == ['move', 'look']
    assert plan[1][1][:2] == ('target', 'target')


@needs_solver
def test_a_look_says_nothing_about_other_regions(tmp_path, monkeypatch):
    """No reveal facts: a look at one region does not make another known."""
    init = _toy([('Boxel', 'region2'), ('look_for', 'target', 'region2')])
    goal = ('obj_at_boxel_KIF', 'target', 'region2')
    plan = _solve(init, goal, tmp_path, monkeypatch)
    # region2 has no look_config, so only a look at region2 itself could do it
    assert plan is None


# ----- 3. the planner's init in centred mode --------------------------------------

def _planner(world, mode='centred'):
    from pddlstream_planner import PDDLStreamPlanner
    reg = world.reg
    objects = {n: world.env.objects[n].object_id for n in ('occluder', 'die')}
    pl = PDDLStreamPlanner(
        reg, robot_id=world.robot, shadow_occluder_map={}, physics_client=world.cid,
        object_body_ids=objects, support_body_ids=frozenset(),
        camera_pos=np.array([0.5, 0.0, 1.0]),
        domain_file=look_domain.GENERATED_FILES[mode])
    pl.m8_views = world.views
    pl.look_on = True
    pl.look_mode = mode
    pl.goal_config = None
    return pl


def _init(pl):
    return pl._build_init(['blue'], _home(), known_empty_shadows=[],
                          moved_occluders={}, observed_clear_regions=None)


def test_the_centred_init_names_only_declared_predicates_and_no_reveal(world):
    pl = _planner(world)
    init = _init(pl)
    declared = set(look_domain.declared_predicates(pl.domain_pddl))
    kinds = {f[0] for f in init}
    assert kinds <= declared
    assert {'look_for', 'look_config', 'config_for_boxel', 'Config'} <= kinds
    assert not kinds & {'reveals', 'blocks_look_at', 'is_view', 'sense_view',
                        'is_shadow', 'is_object', 'is_tray', 'blocks_view_at',
                        'marginally_blocked'}
    assert ('look_for', 'blue', 'shadow_a') in init
    assert pl.last_look_stats['look_for'] >= 1


def test_the_camera_goes_straight_over_the_hypothesis(world):
    pl = _planner(world)
    init = _init(pl)
    qs = [f[1] for f in init if f[0] == 'look_config' and f[2] == 'shadow_a']
    assert qs, "a hypothesised fragment gets look configurations"
    assert all(q.name.startswith('look_shadow_a_') for q in qs)
    assert 'shadow_a' not in pl.last_look_stats['no_view']
    # the tag's observe rule at the region heights (a fragment is not bounded by an object)
    want = {q.name for _, q in world.views.look_configs(
        world.reg.get_boxel('shadow_a'), observe_views.CENTRED_REGION_STANDOFFS)}
    assert {q.name for q in qs} == want
    # a move can reach each one: the tag's view pseudo-boxel, as for observe
    views = {f[2] for f in init if f[0] == 'config_for_boxel' and f[1] in qs}
    assert views == {observe_views.view_boxel(q) for q in qs}


def test_a_removed_configuration_leaves_the_facts(world):
    pl = _planner(world)
    first = [f[1].name for f in _init(pl) if f[0] == 'look_config' and f[2] == 'shadow_a']
    assert first
    gone = first[0]
    world.views.removed.add(('shadow_a', observe_views.look_index(gone, 'shadow_a')))
    again = [f[1].name for f in _init(pl) if f[0] == 'look_config' and f[2] == 'shadow_a']
    assert gone not in again and set(again) == set(first) - {gone}


def test_a_hypothesis_with_no_passing_configuration_has_no_look(world):
    pl = _planner(world)
    n = len(observe_views.CENTRED_REGION_STANDOFFS) * len(observe_views.LOOK_WRIST_YAWS)
    world.views.removed.update(('shadow_a', k) for k in range(n))
    init = _init(pl)
    assert ('look_for', 'blue', 'shadow_a') in init
    assert not [f for f in init if f[0] == 'look_config' and f[2] == 'shadow_a']
    assert 'shadow_a' in pl.last_look_stats['no_view']


def test_an_undeclared_emission_is_refused_in_centred_mode(world, monkeypatch):
    pl = _planner(world)
    real = pl._look_facts_centred

    def bad(init, *a, **k):
        init.append(('reveals', 'q', 'r'))
        return real(init, *a, **k)

    monkeypatch.setattr(pl, '_look_facts_centred', bad)
    with pytest.raises(ValueError, match='undeclared|does not declare'):
        _init(pl)


# ----- 4. the handler -------------------------------------------------------------

def _centred_setup(world, centre='shadow_a', k=0):
    """The arm at the k-th look configuration of what the look is about."""
    world.views.last_stats = {'twin_render_s': 0.0, 'twin_renders': 0, 'look_ik': 0,
                              'sense_view': 0, 'look_config': 0, 'sense_fallback': 0}
    cfgs = dict(world.views.look_configs(world.reg.get_boxel(centre)))
    q = cfgs[k] if k in cfgs else next(iter(cfgs.values()))
    world.views._set_arm(q.joint_positions)
    return q


def _look(loop, params, named, held=None):
    w = loop.world
    return look_action.handle_look_action(
        action_params=params, named=named, env=w.env, registry=loop.reg,
        belief=loop.belief, viz=None, robot_id=w.robot, held_body_id=held,
        support_body_ids=frozenset(), shadows=loop.shadows,
        occluders=loop.occluders, shadow_occluder_map=loop.som,
        blocked_counts=loop.blocked_counts, blocked_giveup_shadows=loop.giveup,
        boxel_centers=loop.centres, boxel_to_pybullet=loop.b2p,
        object_body_ids=loop.obj_ids, pose_known=_known,
        target_name=loop.target, mode='centred')


def test_the_target_at_the_hypothesis_is_registered_and_the_plan_goes_on(world, m1_calls):
    loop = _Loop(world)
    q = _centred_setup(world)
    _add_body(world, 'blue', (0.21, 0.0))
    before = loop.snapshot()
    res = _look(loop, ('blue', 'shadow_a', q), ['shadow_a'])
    after = loop.snapshot()
    assert res.continue_ and res.reason == 'look_ok' and res.found_in == 'shadow_a'
    assert res.reached
    assert {k for k in after if after[k] != before[k]} == \
        {'boxels', 'status', 'found', 'centres', 'obj_ids'}
    assert set(after['boxels']) - set(before['boxels']) == {'blue'}
    assert _known(world.reg.get_boxel('blue'))
    assert len(m1_calls) == 1


def test_an_empty_hypothesis_leaves_the_registry_and_the_plan_replans(world, m1_calls):
    loop = _Loop(world)
    q = _centred_setup(world)
    _add_body(world, 'blue', (0.33, -0.25))                  # elsewhere
    before = loop.snapshot()
    res = _look(loop, ('blue', 'shadow_a', q), ['shadow_a'])
    after = loop.snapshot()
    assert not res.continue_ and res.reason == 'look_not_found'
    assert res.reached                                   # the look was made, nothing was there
    assert 'shadow_a' not in after['boxels'] and 'shadow_a' not in after['shadows']
    assert after['blocked'] == before['blocked']
    assert {k: after['boxels'][k] for k in after['boxels']} == \
        {k: before['boxels'][k] for k in before['boxels'] if k != 'shadow_a'}


def test_a_view_that_does_not_cover_the_hypothesis_is_a_strike_and_nothing_else(world, m1_calls):
    loop = _Loop(world)
    q = _centred_setup(world)
    _add_body(world, 'blue', (0.21, 0.0))
    occ = world.env.objects['occluder'].object_id
    p.resetBasePositionAndOrientation(occ, [0.21, 0.0, 0.15], [0, 0, 0, 1],
                                      physicsClientId=world.cid)      # between the lens and the region
    before = loop.snapshot()
    res = _look(loop, ('blue', 'shadow_a', q), ['shadow_a'])
    after = loop.snapshot()
    assert not res.continue_ and res.reason == 'look_blocked' and res.blocked == ['shadow_a']
    assert res.reached                                   # a blocked look is still a look
    assert {k for k in after if after[k] != before[k]} == {'blocked'}
    assert after['blocked'] == {'shadow_a': 1}


def test_a_pose_look_reposes_the_object_it_is_about_and_no_other(world, m1_calls):
    loop = _Loop(world, target='die')
    die = world.reg.get_boxel('die')
    die.min_corner = die.min_corner + np.array([0.003, 0.0, 0.0])
    die.max_corner = die.max_corner + np.array([0.003, 0.0, 0.0])
    q = _centred_setup(world, centre='die')
    before = loop.snapshot()
    res = _look(loop, ('die', 'die', q), ['die'])
    after = loop.snapshot()
    assert res.continue_ and res.reposed == ['die'] and res.reached
    assert {k for k in after if after[k] != before[k]} == {'boxels'}
    assert {k for k in before['boxels'] if before['boxels'][k] != after['boxels'][k]} == {'die'}
    assert _known(world.reg.get_boxel('die'))


def test_the_centred_look_has_no_viewpoint_boxel_to_check(world, m1_calls):
    """The boxel look refuses a camera outside ?v; the centred look has no ?v."""
    loop = _Loop(world)
    q = _centred_setup(world)
    _add_body(world, 'blue', (0.21, 0.0))
    res = _look(loop, ('blue', 'shadow_a', q), ['shadow_a'])
    assert not res.stale
    assert look_action.check_preconditions(
        env=world.env, registry=world.reg, robot_id=world.robot, held_body_id=None,
        params=('blue', 'shadow_a', q), mode='centred') is None


@pytest.mark.parametrize('why', ['held', 'region', 'arm'])
def test_a_failed_check_writes_nothing(world, m1_calls, why):
    loop = _Loop(world)
    q = _centred_setup(world)
    _add_body(world, 'blue', (0.21, 0.0))
    held, h = None, 'shadow_a'
    if why == 'held':
        held = world.env.objects['blue'].object_id
    elif why == 'region':
        h = 'shadow_gone'
    elif why == 'arm':
        import robot_utils
        world.views._set_arm(np.array(robot_utils.REST_POSES, dtype=float))
    before = loop.snapshot()
    res = _look(loop, ('blue', h, q), [h], held=held)
    assert res.stale and res.reason == 'look_stale_precondition' and not res.continue_
    assert not res.reached
    assert loop.snapshot() == before
    assert m1_calls == []


# ----- 5. what path 8 uses (tracks/look/PLAN.md section 13) ----------------------------

_STATS = {'twin_render_s': 0.0, 'twin_renders': 0, 'look_ik': 0, 'sense_view': 0,
          'look_config': 0, 'sense_fallback': 0}


def _configs(world, boxel, standoffs=None):
    """look_configs as path 8 calls it; the arm is put back afterwards."""
    world.views.last_stats = dict(_STATS)
    start = world.views._arm()
    try:
        return world.views.look_configs(boxel, standoffs)
    finally:
        world.views._set_arm(start)


def _camera(world, q):
    world.views._set_arm(q.joint_positions)
    return robot_utils.wrist_camera_pose(world.robot, world.cid)


def _names(configs):
    return [(k, q.name) for k, q in configs]


def test_a_look_result_is_reached_when_the_look_was_made():
    assert look_action.LookResult(True, 'look_ok').reached
    assert look_action.LookResult(False, 'look_not_found').reached      # looked, nothing there
    assert look_action.LookResult(False, 'look_blocked', blocked=['r']).reached
    stale = look_action._stale('the hand is not empty (handempty)')
    assert stale.stale and not stale.reached


def test_no_standoffs_and_the_default_tuple_are_the_same_look_configurations(world):
    box = world.reg.get_boxel('shadow_a')
    default = _names(_configs(world, box))
    assert default
    assert _names(_configs(world, box, None)) == default
    assert _names(_configs(world, box, observe_views.LOOK_STANDOFFS)) == default


def test_a_changed_standoff_puts_the_camera_over_the_box_at_that_height(world):
    box = world.reg.get_boxel('shadow_a')
    _, _, cxy = world.views._look_target(box)
    top = float(box.max_corner[2])
    cfgs = _configs(world, box, (0.25,))
    assert cfgs
    assert {k for k, _ in cfgs} <= set(range(len(observe_views.LOOK_WRIST_YAWS)))
    for k, q in cfgs:
        assert q.name == observe_views.look_name('shadow_a', k)
        cam = _camera(world, q)
        assert abs(cam[2, 3] - (top + 0.25)) < 0.01
        assert np.allclose(cam[:2, 3], cxy, atol=0.01)


def test_k_counts_the_standoff_and_yaw_pairs_in_the_order_given(world):
    box = world.reg.get_boxel('shadow_a')
    n_yaw = len(observe_views.LOOK_WRIST_YAWS)
    default = dict(_configs(world, box))                    # (0.20, each yaw), then (0.30, ...)
    swapped = dict(_configs(world, box, (0.30, 0.20)))
    assert default and len(default) == len(swapped)
    for k, q in default.items():
        k2 = k + n_yaw if k < n_yaw else k - n_yaw          # the same pair in the other slot
        assert k2 in swapped, (k, k2)
        assert np.allclose(swapped[k2].joint_positions, q.joint_positions, atol=1e-6)
    assert all(q.name == observe_views.look_name('shadow_a', k) for k, q in swapped.items())


def test_a_removed_pair_follows_the_tuple(world):
    box = world.reg.get_boxel('shadow_a')
    ks = [k for k, _ in _configs(world, box, (0.25,))]
    assert ks
    world.views.removed.add(('shadow_a', ks[0]))
    assert [k for k, _ in _configs(world, box, (0.25,))] == ks[1:]


def test_init_facts_gives_an_objects_standoffs_to_its_look_configurations(world):
    box = world.reg.get_boxel('shadow_a')
    top = float(box.max_corner[2])
    facts, view_ids = world.views.init_facts(_home(), _home(), [], [box], [],
                                             standoffs={'shadow_a': (0.25,)})
    qs = [f[1] for f in facts if f[0] == 'look_config' and f[2] == 'shadow_a']
    assert qs
    assert {q.name for q in qs} == {q.name for _, q in _configs(world, box, (0.25,))}
    for q in qs:
        assert abs(_camera(world, q)[2, 3] - (top + 0.25)) < 0.01
    assert {observe_views.view_boxel(q) for q in qs} <= view_ids
    default, _ = world.views.init_facts(_home(), _home(), [], [box], [])    # no standoffs: as before
    assert {f[1].name for f in default if f[0] == 'look_config'} == \
        {q.name for _, q in _configs(world, box)}


def test_a_pose_look_at_a_known_pose_is_not_refused(world, m1_calls):
    """Path 8's inspect: the fixed eye has seen the object, so its pose is known
    before the look; the look still runs and re-poses it."""
    loop = _Loop(world, target='die')
    die = world.reg.get_boxel('die')
    die.pose_radius = 0.002
    assert _known(die)
    q = _centred_setup(world, centre='die')
    before = loop.snapshot()
    res = _look(loop, ('die', 'die', q), ['die'])
    after = loop.snapshot()
    assert res.reached and res.continue_ and res.reposed == ['die']
    assert {k for k in after if after[k] != before[k]} <= {'boxels'}
    assert {k for k in before['boxels'] if before['boxels'][k] != after['boxels'][k]} <= {'die'}
    assert _known(world.reg.get_boxel('die'))


@pytest.mark.parametrize('standoff', [0.25, 0.14])
def test_a_pose_look_from_a_changed_standoff(world, m1_calls, standoff):
    """0.14 m is about path 8's gripper height (0.1 m plus the camera's offset
    behind the finger tips, minus the die's half height)."""
    loop = _Loop(world, target='die')
    die = world.reg.get_boxel('die')
    die.min_corner = die.min_corner + np.array([0.003, 0.0, 0.0])
    die.max_corner = die.max_corner + np.array([0.003, 0.0, 0.0])
    cfgs = _configs(world, die, (standoff,))
    assert cfgs, f"no look configuration passes at {standoff} m"
    _, q = cfgs[0]
    world.views._set_arm(q.joint_positions)
    before = loop.snapshot()
    res = _look(loop, ('die', 'die', q), ['die'])
    after = loop.snapshot()
    assert res.reached and res.continue_ and res.reposed == ['die']
    assert {k for k in before['boxels'] if before['boxels'][k] != after['boxels'][k]} == {'die'}
    assert _known(world.reg.get_boxel('die'))


# ----- 6. a region larger than one view (the first smoke, seed 0) ----------------------

def _big_region(world):
    """0.30 by 0.30 m: more than the wrist camera holds from 0.20 or 0.30 m over its
    top (it sees 0.91 s metres along its short image side), clear of the other bodies."""
    world.reg.add_boxel(_boxel('shadow_big', BoxelType.SHADOW, [-0.05, 0.10, 0.0],
                               [0.25, 0.40, 0.05]))
    return world.reg.get_boxel('shadow_big')


def test_a_region_larger_than_the_view_has_no_configuration_at_the_default_heights(world):
    big = _big_region(world)
    assert _configs(world, big) == []
    notes = world.views.last_look_notes['shadow_big']
    assert len(notes) == len(observe_views.LOOK_STANDOFFS) * len(observe_views.LOOK_WRIST_YAWS)
    verdicts = {v for _, _, _, v, _ in notes}
    assert 'frame' in verdicts and verdicts <= {'frame', 'no_ik', 'collision'}
    assert all('rows' in d and 'cols' in d for _, _, _, v, d in notes if v == 'frame')


def test_the_region_heights_reach_a_view_that_holds_the_whole_region(world):
    big = _big_region(world)
    cfgs = _configs(world, big, observe_views.CENTRED_REGION_STANDOFFS)
    assert cfgs
    ks = [k for k, _ in cfgs]
    assert min(ks) >= 2 * len(observe_views.LOOK_WRIST_YAWS)     # none at 0.20 or 0.30 m
    verdict = {k: v for k, _, _, v, _ in world.views.last_look_notes['shadow_big']}
    assert all(verdict[k] == 'ok' for k in ks)


def test_a_region_with_no_view_is_explained_in_the_log(world, capsys):
    pl = _planner(world)
    n = len(observe_views.CENTRED_REGION_STANDOFFS) * len(observe_views.LOOK_WRIST_YAWS)
    world.views.removed.update(('shadow_a', k) for k in range(n))
    _init(pl)
    out = capsys.readouterr().out
    assert 'no view of shadow_a' in out and 'removed' in out
