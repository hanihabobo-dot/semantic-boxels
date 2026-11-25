"""Path 9: the look action's PDDL and its Python say the same thing.

1. Static: LOOK_SPEC (look_action.py) has exactly the precondition and effect
   atoms of the generated domain's `look`, polarity and conditionality
   included, the same parameters, the same `when` condition names.  A PDDL
   edit without a spec entry, or an entry without a PDDL line, fails.
2. The planner's init in look mode emits only predicates the look domain
   declares, and the look facts are there.
3. Dynamic: handle_look_action on a synthetic scene.  The whole before and
   after state (registry, belief, loop counters) is compared: the change must
   be a subset of the writes the spec names, and every named write the render
   supports must be there.  Cases: the target in ?h, the region empty, the
   view blocked, a pose look, and the refusals (no write at all).
4. Flag off: `run.ps1` without -Look builds the command of the tag's run.ps1.
"""
import platform
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pytest

from sensing import look_action
from planning import look_domain
from sensing import look_views
from sensing import observe_views
from sensing import pose_belief
from acting import robot_utils
from sensing.belief import BeliefState
from world.boxel_data import BoxelType
from test_look_views import (DIE, OCC, _boxel, _box, world)    # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]
LOOK_TEXT = look_domain.read(look_domain.GENERATED_FILE)


# ----- 1. static -------------------------------------------------------------

def test_the_spec_is_the_pddl_action():
    spec = look_domain.action_specs(LOOK_TEXT)['look']
    assert spec['parameters'] == look_action.LOOK_SPEC['parameters']
    assert spec['pre'] == {(n, True) for n in look_action.LOOK_SPEC['pre']}
    assert spec['eff'] == set(look_action.LOOK_SPEC['eff'])
    assert spec['eff_cond'] == look_action.LOOK_SPEC['eff_cond']


def test_every_spec_entry_says_what_python_does():
    for key, (kind, text) in look_action.LOOK_SPEC['pre'].items():
        assert kind in ('static', 'check', 'render'), key
        assert text, key
    for key, (kind, text) in look_action.LOOK_SPEC['eff'].items():
        assert kind == 'write' and text, key
    assert set(look_action.LOOK_SPEC['monitor']) == {'M-1'}


def test_the_checks_named_in_the_spec_exist_in_the_handler():
    src = Path(look_action.__file__).read_text()
    for needle in ('held_body_id is not None', 'AT_CONFIG_TOL_RAD', 'LOOK_BOXEL_TOL_M',
                   'sense_shadow_from_render', 'mark_sensed', '_remove_fragment',
                   '_register_target', '_repose', 'register_new_detections'):
        assert needle in src, needle


# ----- helpers for the scene ---------------------------------------------------

def _known(bd):
    return pose_belief.pose_known(bd, 0.04, 0.076, 0.005)


def _home():
    from planning.streams import RobotConfig
    return RobotConfig(joint_positions=np.array(robot_utils.REST_POSES, dtype=float),
                       name='q_home')


class _Loop:
    """The loop state a handler reads and writes, as main() holds it."""

    def __init__(self, world, target='blue'):
        self.world = world
        self.reg = world.reg
        self.belief = BeliefState(['shadow_a'], target)
        self.shadows = ['shadow_a']
        self.occluders = ['occluder', 'die']
        self.som = {'shadow_a': ['occluder']}
        self.blocked_counts = {}
        self.giveup = set()
        self.centres = {b.id: b.center for b in self.reg.boxels.values()}
        self.b2p = {}
        self.obj_ids = {}
        self.target = target

    def snapshot(self):
        reg = self.reg
        return {
            'boxels': {b.id: (b.boxel_type.name, tuple(np.round(b.min_corner, 6)),
                              tuple(np.round(b.max_corner, 6)),
                              float(b.pose_radius), int(b.complete_detections))
                       for b in reg.boxels.values()},
            'status': dict(self.belief.shadow_status),
            'found': self.belief.target_found_in,
            'shadows': list(self.shadows), 'som': {k: list(v) for k, v in self.som.items()},
            'blocked': dict(self.blocked_counts), 'giveup': set(self.giveup),
            'centres': set(self.centres), 'obj_ids': set(self.obj_ids),
        }

    def look(self, params, named, held=None):
        w = self.world
        return look_action.handle_look_action(
            action_params=params, named=named, env=w.env, registry=self.reg,
            belief=self.belief, viz=None, robot_id=w.robot, held_body_id=held,
            support_body_ids=frozenset(), shadows=self.shadows,
            occluders=self.occluders, shadow_occluder_map=self.som,
            blocked_counts=self.blocked_counts,
            blocked_giveup_shadows=self.giveup, boxel_centers=self.centres,
            boxel_to_pybullet=self.b2p, object_body_ids=self.obj_ids,
            pose_known=_known, target_name=self.target)


def _look_setup(world, regions=('shadow_a',), objects=()):
    """The planner's facts for the scene, the arm moved to the first
    configuration that reveals the first region (or object), and the
    arguments of the look that the plan would hold."""
    facts, _ = world.lv.facts(world.reg, [world.reg.get_boxel(r) for r in regions],
                              [world.reg.get_boxel(o) for o in objects], _home())
    goal = (regions + objects)[0]
    q = next(f[1] for f in facts if f[0] == 'reveals' and f[2] == goal)
    v = next(f[2] for f in facts if f[0] == 'config_for_boxel' and f[1] is q)
    named = [f[2] for f in facts if f[0] == 'reveals' and f[1] is q]
    world.views._set_arm(q.joint_positions)
    return q, v, named


def _add_body(world, name, xy, half=(0.015, 0.015, 0.015)):
    body = _box(world.cid, xy, half)
    world.env.objects[name] = SimpleNamespace(object_id=body)
    world.env._gui_to_plan[body] = body
    world.env.plan_body_id = lambda gid: gid
    return body


@pytest.fixture
def m1_calls(monkeypatch):
    """Monitor rule M-1 is the shared register_new_detections (tested with
    sense); here it is recorded, not run."""
    calls = []

    def fake(**kw):
        calls.append(kw)
        return []

    monkeypatch.setattr(look_action, 'register_new_detections', fake)
    return calls


# ----- 3. dynamic --------------------------------------------------------------

def test_the_target_in_h_is_registered_posed_and_the_plan_goes_on(world, m1_calls):
    loop = _Loop(world)
    q, v, named = _look_setup(world)
    _add_body(world, 'blue', (0.21, 0.0))
    before = loop.snapshot()
    res = loop.look(('blue', 'shadow_a', v, q), named)
    after = loop.snapshot()
    assert res.continue_ and res.reason == 'look_ok' and res.found_in == 'shadow_a'
    changed = {k for k in after if after[k] != before[k]}
    # the named writes: the target's boxel and the loop's maps that mirror it,
    # mark_sensed(found); nothing else
    assert changed == {'boxels', 'status', 'found', 'centres', 'obj_ids'}, changed
    assert after['centres'] - before['centres'] == {'blue'}
    assert after['obj_ids'] - before['obj_ids'] == {'blue'}
    assert set(after['boxels']) - set(before['boxels']) == {'blue'}
    assert {k for k in before['boxels'] if before['boxels'][k] != after['boxels'].get(k)} == set()
    assert after['found'] == 'shadow_a' and 'shadow_a' in after['shadows']
    assert _known(world.reg.get_boxel('blue'))
    assert len(m1_calls) == 1                              # M-1, once


def test_an_empty_region_leaves_the_registry_and_the_plan_replans(world, m1_calls):
    loop = _Loop(world)
    q, v, named = _look_setup(world)
    _add_body(world, 'blue', (0.33, -0.25))                # elsewhere, outside the view
    before = loop.snapshot()
    res = loop.look(('blue', 'shadow_a', v, q), named)
    after = loop.snapshot()
    assert not res.continue_ and res.reason == 'look_not_found'
    assert res.outcomes['shadow_a'] == 'clear_but_empty'
    assert 'shadow_a' not in after['boxels'] and 'shadow_a' not in after['shadows']
    assert after['status']['shadow_a'] == 'sensed_empty' or 'shadow_a' not in after['status'] \
        or after['status']['shadow_a'] != before['status'].get('shadow_a')
    # nothing else moved: the other boxels are exactly as before
    kept = {k: after['boxels'][k] for k in after['boxels']}
    assert kept == {k: before['boxels'][k] for k in before['boxels'] if k != 'shadow_a'}
    assert after['blocked'] == before['blocked']


def test_a_blocked_view_writes_nothing_but_a_strike(world, m1_calls):
    loop = _Loop(world)
    q, v, named = _look_setup(world)
    _add_body(world, 'blue', (0.21, 0.0))
    occ = world.env.objects['occluder'].object_id
    p.resetBasePositionAndOrientation(occ, [0.21, 0.0, 0.30], [0, 0, 0, 1],
                                      physicsClientId=world.cid)    # in front of the lens
    before = loop.snapshot()
    res = loop.look(('blue', 'shadow_a', v, q), named)
    after = loop.snapshot()
    assert not res.continue_ and res.reason == 'look_blocked'
    assert res.outcomes['shadow_a'] == 'still_blocked' and res.blocked == ['shadow_a']
    changed = {k for k in after if after[k] != before[k]}
    assert changed == {'blocked'}, changed
    assert after['blocked'] == {'shadow_a': 1}


def test_three_blocked_looks_park_the_region(world, m1_calls):
    loop = _Loop(world)
    q, v, named = _look_setup(world)
    _add_body(world, 'blue', (0.21, 0.0))
    occ = world.env.objects['occluder'].object_id
    p.resetBasePositionAndOrientation(occ, [0.21, 0.0, 0.30], [0, 0, 0, 1],
                                      physicsClientId=world.cid)
    for _ in range(3):
        res = loop.look(('blue', 'shadow_a', v, q), named)
    assert res.parked == ['shadow_a'] and loop.giveup == {'shadow_a'}
    assert loop.belief.shadow_status['shadow_a'] == 'unresolved'


def test_a_pose_look_reposes_the_named_object_only(world, m1_calls):
    loop = _Loop(world, target='die')
    die = world.reg.get_boxel('die')
    die.min_corner = die.min_corner + np.array([0.003, 0.0, 0.0])
    die.max_corner = die.max_corner + np.array([0.003, 0.0, 0.0])
    q, v, named = _look_setup(world, regions=(), objects=('die',))
    assert named == ['die'] or 'die' in named
    before = loop.snapshot()
    res = loop.look(('die', 'die', v, q), ['die'])
    after = loop.snapshot()
    assert res.continue_ and res.reposed == ['die']
    changed = {k for k in after if after[k] != before[k]}
    assert changed == {'boxels'}, changed
    assert {k for k in before['boxels'] if before['boxels'][k] != after['boxels'][k]} == {'die'}
    assert _known(world.reg.get_boxel('die'))


def test_an_object_not_named_is_not_reposed(world, m1_calls):
    loop = _Loop(world, target='die')
    die = world.reg.get_boxel('die')
    die.min_corner = die.min_corner + np.array([0.003, 0.0, 0.0])
    die.max_corner = die.max_corner + np.array([0.003, 0.0, 0.0])
    q, v, _named = _look_setup(world, regions=(), objects=('die',))
    before = loop.snapshot()
    res = loop.look(('die', 'die', v, q), [])
    assert res.reposed == [] and loop.snapshot()['boxels'] == before['boxels']
    assert not res.continue_ and res.reason == 'look_pose_incomplete'


@pytest.mark.parametrize('why', ['held', 'region', 'config', 'boxel', 'arm'])
def test_a_failed_check_writes_nothing(world, m1_calls, why):
    loop = _Loop(world)
    q, v, named = _look_setup(world)
    _add_body(world, 'blue', (0.21, 0.0))
    held, h = None, 'shadow_a'
    if why == 'held':
        held = world.env.objects['blue'].object_id
    elif why == 'region':
        h = 'shadow_gone'
    elif why == 'boxel':
        v = 'free_gone'
    elif why == 'arm':
        world.views._set_arm(np.array(robot_utils.REST_POSES, dtype=float))
    elif why == 'config':
        v = 'free_side'                                    # the camera is not in it
    before = loop.snapshot()
    res = loop.look(('blue', h, v, q), named, held=held)
    assert res.stale and res.reason == 'look_stale_precondition' and not res.continue_
    assert loop.snapshot() == before
    assert m1_calls == []                                  # no render, no M-1


# ----- 2. the planner's init in look mode ---------------------------------------

def _planner(world):
    from planning.pddlstream_planner import PDDLStreamPlanner
    reg = world.reg
    objects = {n: world.env.objects[n].object_id for n in ('occluder', 'die')}
    pl = PDDLStreamPlanner(
        reg, robot_id=world.robot, shadow_occluder_map={}, physics_client=world.cid,
        object_body_ids=objects, support_body_ids=frozenset(),
        camera_pos=np.array([0.5, 0.0, 1.0]), domain_file=look_domain.GENERATED_FILE)
    pl.m8_views = world.views
    pl.look_views = world.lv
    pl.look_on = True
    pl.goal_config = None
    return pl


def test_the_look_init_names_only_declared_predicates(world):
    pl = _planner(world)
    init = pl._build_init(['blue'], _home(), known_empty_shadows=[],
                          moved_occluders={}, observed_clear_regions=None)
    declared = set(look_domain.declared_predicates(pl.domain_pddl))
    assert {f[0] for f in init} <= declared
    kinds = {f[0] for f in init}
    assert {'look_for', 'reveals', 'config_for_boxel', 'Config'} <= kinds
    assert not kinds & {'is_shadow', 'is_object', 'is_tray', 'sense_view', 'look_config',
                        'is_view', 'blocks_view_at', 'marginally_blocked'}
    assert ('look_for', 'blue', 'shadow_a') in init
    # a hidden target gets no look_for at its own boxel; a known pose none at all
    assert ('look_for', 'blue', 'blue') not in init
    assert all(f[2] != 'die' or f[0] != 'look_for' or f[1] == 'die' for f in init
               if f[0] == 'look_for')


def test_an_undeclared_emission_is_refused(world, monkeypatch):
    pl = _planner(world)
    real = pl._look_facts

    def bad(init, *a, **k):
        init.append(('sense_view', 'q', 'r'))
        return real(init, *a, **k)

    monkeypatch.setattr(pl, '_look_facts', bad)
    with pytest.raises(ValueError, match='undeclared|does not declare'):
        pl._build_init(['blue'], _home(), known_empty_shadows=[], moved_occluders={})


def test_look_off_builds_the_tags_init(world):
    """With look_on False the planner reads what it read before: the same
    block of code, no look fact."""
    from planning.pddlstream_planner import PDDLStreamPlanner
    pl = PDDLStreamPlanner(
        world.reg, robot_id=world.robot, shadow_occluder_map={},
        physics_client=world.cid,
        object_body_ids={n: world.env.objects[n].object_id for n in ('occluder', 'die')},
        support_body_ids=frozenset(), camera_pos=np.array([0.5, 0.0, 1.0]))
    assert pl.look_on is False and pl.look_views is None
    init = pl._build_init(['blue'], _home(), known_empty_shadows=[], moved_occluders={})
    kinds = {f[0] for f in init}
    assert 'is_shadow' in kinds and 'is_object' in kinds
    assert not kinds & {'look_for', 'reveals', 'blocks_look_at'}
    assert pl.last_look_stats == {}


# ----- 4. flag off -------------------------------------------------------------

_IN_WSL = 'microsoft' in platform.uname().release.lower()
_ON_DRIVE = re.match(r'^/mnt/[a-z]/', str(ROOT)) is not None
_PWSH = shutil.which('pwsh.exe') if _IN_WSL and _ON_DRIVE else None
# The base the look code sits on: track/freeze since the merge of 2026-11-12
# (aabc70a), checked out as ..\sb-freeze; before that the tag in ..\sb-stable,
# whose launcher has no lock wrapper (TB-17) and no -Draw.  If sb-freeze's
# launcher moves on, this test fails until track/freeze is merged again.
_BASE = ROOT.parent / 'sb-freeze'
needs_pwsh = pytest.mark.skipif(_PWSH is None, reason='needs pwsh.exe through WSL interop')


def _dry(ps1: Path, args: str) -> str:
    win = subprocess.run(['wslpath', '-w', str(ps1)], capture_output=True, text=True,
                         check=True).stdout.strip()
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command',
                           f"& '{win}' {args} -DryRun"], capture_output=True, text=True,
                          timeout=120, cwd=str(ps1.parent))
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip().replace(str(ps1.parent), '<S>')
    return re.sub(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}', '<T>', out)   # the run's stamp


@needs_pwsh
@pytest.mark.parametrize('args', ['boxels -Seed 3 -Headless', 'boxels -Seed 0',
                                  'tampura -Seed 118 -Gen -Headless', 'tampura -Seed 5',
                                  'boxels -Seed 3 -Headless -Off'])
def test_without_look_the_command_is_the_bases(args):
    mine = _dry(ROOT / 'run.ps1', args)
    assert '--look' not in mine
    # A window run of boxels also asks for the page beside the window (Hani,
    # 2026-11-22; gui_page.py): one word of its own and one flag, and nothing
    # else (tests/test_run_page_launcher.py holds that).  They are the page's,
    # not the look's: taken out here, the rest must still be the base's, and
    # no other run may carry them.  Since the split of the screen (Hani,
    # 2026-11-25) that run is also asked for a window of the size measured,
    # at most once (tests/test_page_split.py): the page's too, taken out too.
    if args.startswith('boxels') and '-Headless' not in args:
        word = re.compile(r'export SB_GUI_PAGE_TOKEN=[0-9a-f]{12}; ')
        size = re.compile(r'export SB_GUI_WINDOW=\d+x\d+; ')
        assert len(word.findall(mine)) == 1 and mine.count(' --gui-page on') == 1
        assert len(size.findall(mine)) <= 1
        mine = word.sub('', size.sub('', mine)).replace(' --gui-page on', '')
    else:
        assert 'SB_GUI_' not in mine and '--gui-page' not in mine
    if (_BASE / 'run.ps1').is_file():
        theirs = _dry(_BASE / 'run.ps1', args)
        norm = lambda s: s.replace('/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels', '<S>')
        assert norm(mine) == norm(theirs)


@needs_pwsh
@pytest.mark.parametrize('value', ['boxel', 'centred'])
def test_the_look_switch_appends_one_flag(value):
    # The pipeline command sits inside the lock wrapper's quoted bash -c
    # (TB-17), so the flag is the one thing added, not the string's tail.
    off = _dry(ROOT / 'run.ps1', 'boxels -Seed 3 -Headless')
    on = _dry(ROOT / 'run.ps1', f'boxels -Seed 3 -Headless -Look {value}')
    assert on.count('--look') == 1
    assert on.replace(f' --look {value}', '', 1) == off
    assert f"--n-occluders 2 --look {value}'" in on
