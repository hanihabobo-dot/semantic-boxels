"""Path 9: the look-mode domain file.

The generated pddl/domain_pddlstream_look.pddl is the live domain plus M8's
delta plus the look delta; it must be current, tight (no sense, no observe, no
predicate nobody uses, none used but undeclared), and PDDLStream must plan with
it: the toy problems at the end solve the look action itself, with dummy
streams, in a temporary working directory.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import look_domain  # noqa: E402
import m8_domain  # noqa: E402

LOOK_TEXT = look_domain.read(look_domain.GENERATED_FILE)
STREAM_TEXT = (ROOT / 'pddl' / 'stream.pddl').read_text(encoding='utf-8')
ACTIONS = {'look', 'move', 'pick', 'place', 'place_hiding', 'stack'}
GONE_WORDS = ('sense', 'observe', 'view_clear', 'blocks_view', 'marginally_blocked',
              'is_shadow', 'is_tray', 'is_view', 'look_config', 'view_blocked')


def _code(text):
    """The domain text without its comments."""
    return '\n'.join(line.split(';', 1)[0] for line in text.splitlines())


# --- the file ---------------------------------------------------------------

def test_generated_file_is_current():
    assert look_domain.read(look_domain.GENERATED_FILE) == \
        look_domain.generate(look_domain.read(look_domain.LIVE_FILE))


def test_domain_file_chooses_by_flag():
    assert look_domain.domain_file(False, True) == m8_domain.domain_file(True)
    assert look_domain.domain_file(False, False) == m8_domain.domain_file(False)
    assert look_domain.domain_file(True, True) == look_domain.GENERATED_FILE


def test_look_needs_m8():
    with pytest.raises(ValueError):
        look_domain.domain_file(True, False)


def test_generation_refuses_a_moved_anchor():
    live = look_domain.read(look_domain.LIVE_FILE)
    with pytest.raises(ValueError):
        look_domain.generate(live.replace(
            ";; DERIVED PREDICATES: Visibility from object positions",
            ";; DERIVED PREDICATES: Visibility moved"))


# --- tight ------------------------------------------------------------------

def test_actions_and_derived_predicates_are_the_expected_set():
    assert set(look_domain.action_specs(LOOK_TEXT)) == ACTIONS
    assert set(look_domain.derived_specs(LOOK_TEXT)) == {'look_blocked', 'look_clear'}


def test_sense_and_observe_and_their_predicates_are_gone():
    code = _code(LOOK_TEXT)
    for word in GONE_WORDS:
        assert word not in code, word


def test_every_declared_predicate_is_used_and_every_used_one_declared():
    uses = look_domain.predicate_uses(LOOK_TEXT, STREAM_TEXT)
    declared = look_domain.declared_predicates(LOOK_TEXT)
    assert len(declared) == len(set(declared))
    assert sorted(uses) == sorted(declared), \
        f"used but not declared: {sorted(set(uses) - set(declared))}"
    assert [n for n, c in uses.items() if c == 0] == []


def test_the_other_actions_are_the_live_text():
    """move, pick, place, place_hiding and stack read as M8's domain has them."""
    m8 = look_domain.action_specs(look_domain.read(m8_domain.GENERATED_FILE))
    look = look_domain.action_specs(LOOK_TEXT)
    for name in ACTIONS - {'look'}:
        assert look[name] == m8[name], name


def test_the_parser_reads_a_when_effect():
    text = """(define (domain d)
      (:predicates (p ?x) (q ?x) (r ?x))
      (:action a :parameters (?x ?y)
        :precondition (and (p ?x) (not (q ?y)))
        :effect (and (r ?x) (forall (?z) (when (and (p ?z) (q ?z)) (not (r ?z)))))))"""
    spec = look_domain.action_specs(text)['a']
    assert spec['pre'] == {('p', True), ('q', False)}
    assert spec['eff'] == {('r', True, False), ('r', False, True)}
    assert spec['eff_cond'] == {'p', 'q'}


# --- PDDLStream plans with it ---------------------------------------------

PDDLSTREAM = Path(os.environ.get('PDDLSTREAM_PATH', str(ROOT.parent / 'pddlstream_lib')))
needs_solver = pytest.mark.skipif(not (PDDLSTREAM / 'downward' / 'builds').is_dir(),
                                  reason="FastDownward is not built")


def _solve(init, goal, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                    # pddlstream writes ./temp
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
    problem = PDDLProblem(LOOK_TEXT, {}, STREAM_TEXT, stream_map, init, goal)
    plan, _cost, _cert = solve(problem, algorithm='adaptive', max_time=60,
                               verbose=False)
    return None if plan is None else [(a.name, tuple(a.args)) for a in plan]


def _toy(extra=(), skip=()):
    """The arm is at q0; qv looks from the free boxel `cell` at `region`."""
    init = [
        ('Boxel', 'home'), ('Boxel', 'cell'), ('Boxel', 'region'),
        ('Boxel', 'region2'), ('Boxel', 'target'), ('Boxel', 'other'),
        ('Obj', 'target'), ('Obj', 'other'),
        ('Config', 'q0'), ('Config', 'qv'), ('at_config', 'q0'), ('handempty',),
        ('config_for_boxel', 'q0', 'home'), ('config_for_boxel', 'qv', 'cell'),
        ('is_free_space', 'cell'),
        ('look_for', 'target', 'region'),
        ('reveals', 'qv', 'region'),
    ]
    return [f for f in init if f not in skip] + list(extra)


def _names(plan):
    return [name for name, _args in plan]


@needs_solver
def test_a_look_finds_the_target_in_a_revealed_region(tmp_path, monkeypatch):
    goal = ('and', ('obj_at_boxel', 'target', 'region'),
            ('obj_at_boxel_KIF', 'target', 'region'),
            ('obj_pose_known', 'target'))
    plan = _solve(_toy(), goal, tmp_path, monkeypatch)
    assert plan is not None and _names(plan) == ['move', 'look']
    assert plan[1][1][:3] == ('target', 'region', 'cell')


@needs_solver
def test_a_look_clears_the_other_regions_it_covers(tmp_path, monkeypatch):
    """The optimistic outcome (the target at ?h) makes every other revealed
    region known not to hold it, and shows other bodies' poses."""
    init = _toy([('reveals', 'qv', 'region2'), ('reveals', 'qv', 'other')])
    goal = ('and', ('obj_at_boxel_KIF', 'target', 'region2'),
            ('obj_pose_known', 'other'))
    plan = _solve(init, goal, tmp_path, monkeypatch)
    assert plan is not None and _names(plan) == ['move', 'look']


@needs_solver
def test_a_look_at_the_objects_own_boxel_is_the_pose_look(tmp_path, monkeypatch):
    init = _toy([('look_for', 'target', 'target'), ('reveals', 'qv', 'target'),
                 ('obj_at_boxel', 'target', 'target'),
                 ('obj_at_boxel_KIF', 'target', 'target')],
                skip=[('look_for', 'target', 'region'), ('reveals', 'qv', 'region')])
    plan = _solve(init, ('obj_pose_known', 'target'), tmp_path, monkeypatch)
    assert plan is not None and _names(plan) == ['move', 'look']
    assert plan[1][1][:2] == ('target', 'target')


@needs_solver
def test_a_region_the_view_does_not_cover_cannot_be_looked_at(tmp_path, monkeypatch):
    init = _toy(skip=[('reveals', 'qv', 'region')])
    goal = ('obj_at_boxel', 'target', 'region')
    assert _solve(init, goal, tmp_path, monkeypatch) is None


@needs_solver
def test_a_body_that_hides_the_view_blocks_the_look_until_it_moves(tmp_path, monkeypatch):
    hidden = _toy([('obj_at_boxel', 'other', 'other'),
                   ('blocks_look_at', 'other', 'other', 'qv', 'region')])
    goal = ('obj_at_boxel', 'target', 'region')
    assert _solve(hidden, goal, tmp_path, monkeypatch) is None
    moved = _toy([('obj_at_boxel', 'other', 'region2'),
                  ('blocks_look_at', 'other', 'other', 'qv', 'region')])
    plan = _solve(moved, goal, tmp_path, monkeypatch)
    assert plan is not None and _names(plan) == ['move', 'look']
