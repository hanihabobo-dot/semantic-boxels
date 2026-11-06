"""Path 4's LW1 harness before LW1 is built (PLAN.md sections 5 to 7): the
mapping of LW1's actions onto the robot (lw1_exec), traces and their first
divergence (G-W2, G-W3), the replay on the robot (G-W2), and the problem
written from our registry.  The robot tests are headless; run them under
`flock /root/sb_pipeline.lock`."""
from collections import deque

import pytest

from wumpus import lw1_exec, lw1_problem, trace as tr
from wumpus.replay import replay, passed
from wumpus.world import WumpusWorld, cell_name


# ------------------------------------------------------------ pure checks
def test_parse_action():
    assert lw1_exec.parse_action('(move p1-1 p1-2)') == ('move', 'p1-1', 'p1-2')
    assert lw1_exec.parse_action('MOVE P1-1 P1-2') == ('move', 'p1-1', 'p1-2')
    assert lw1_exec.parse_action('start p1-1') == ('start', 'p1-1')
    assert lw1_exec.parse_action('(GRAB P3-2)') == ('grab', 'p3-2')
    assert lw1_exec.parse_action('move_p1-1_p1-2') == ('move', 'p1-1', 'p1-2')   # LW1's ground name
    assert lw1_exec.parse_action('start_p1-1') == ('start', 'p1-1')
    for bad in ('', 'jump p1-1', 'move p1-1', 'grab p1-1 p1-2', '(start)', 'move_p1-1'):
        with pytest.raises(ValueError):
            lw1_exec.parse_action(bad)


def test_protocol_lines():
    ok = {'action': ('move', 'p1-1', 'p1-2'), 'status': 'ok', 'why': '', 'dead': None,
          'obs': {'stench': False, 'breeze': True, 'glitter': False}}
    assert lw1_exec.protocol_lines(ok) == ['OBS stench p1-2 0', 'OBS breeze p1-2 1',
                                           'OBS glitter p1-2 0', 'END']
    grab = {'action': ('grab', 'p3-2'), 'status': 'ok', 'why': '', 'dead': None, 'obs': None}
    assert lw1_exec.protocol_lines(grab) == ['END']
    assert lw1_exec.protocol_lines({**ok, 'status': 'dead', 'dead': 'pit'}) == ['DEAD pit']
    assert lw1_exec.protocol_lines({**ok, 'status': 'fail', 'why': 'stopped\n 0.3 m off'}) == \
        ['FAIL stopped 0.3 m off']


def test_first_divergence():
    w = WumpusWorld.from_hidden(5, '(:hidden (wumpus-at p3-3) (pit-at p1-4) (gold-at p2-3))')
    acts = ['start p1-1', 'move p1-1 p1-2', 'move p1-2 p1-3', 'move p1-3 p2-3', 'grab p2-3']
    a = tr.with_rule_obs(w, acts)
    assert a[2]['obs'] == {'stench': False, 'breeze': True, 'glitter': False}
    assert a[3]['obs'] == {'stench': True, 'breeze': False, 'glitter': True}
    assert a[4]['obs'] is None
    assert tr.first_divergence(a, [dict(s) for s in a]) is None
    assert tr.first_divergence(a, [tr.step(x) for x in acts]) is None        # actions alone
    b = [dict(s) for s in a]
    b[3] = tr.step(acts[3], {**a[3]['obs'], 'stench': False})
    assert tr.first_divergence(a, b) == {'k': 3, 'field': 'stench', 'a': True, 'b': False,
                                         'action': ['move', 'p1-3', 'p2-3']}
    c = a[:2] + [tr.step('move p1-2 p2-2')] + a[3:]
    assert tr.first_divergence(a, c)['field'] == 'action'
    assert tr.first_divergence(a, a[:3]) == {'k': 3, 'field': 'length', 'a': 5, 'b': 3}


def test_trace_load(tmp_path):
    import json
    f = tmp_path / 't.txt'
    f.write_text('start p1-1   # the start\n\nMOVE P1-1 P2-1\n')
    assert [s['action'] for s in tr.load(str(f))] == [['start', 'p1-1'], ['move', 'p1-1', 'p2-1']]
    g = tmp_path / 't.json'
    steps = [tr.step('start p1-1', {'stench': 0, 'breeze': 1, 'glitter': 0})]
    g.write_text(json.dumps({'trace': steps}))
    assert tr.load(str(g)) == [{'action': ['start', 'p1-1'],
                                'obs': {'stench': False, 'breeze': True, 'glitter': False}}]


def poster_problem(n):
    """The problem in the form of LW1's own listing (AAAI 2014 poster), built
    from (i, j) arithmetic alone: the reference the registry's writer must
    meet until their p.pddl is on this machine."""
    cells = [cell_name(i, j) for i in range(1, n + 1) for j in range(1, n + 1)]
    adj = []
    for i in range(1, n + 1):
        for j in range(1, n + 1):
            if j < n:
                adj += [f'(adj p{i}-{j} p{i}-{j + 1})', f'(adj p{i}-{j + 1} p{i}-{j})']
            if i < n:
                adj += [f'(adj p{i}-{j} p{i + 1}-{j})', f'(adj p{i + 1}-{j} p{i}-{j})']
    return (f'(define (problem p{n}x{n})\n(:domain wumpus)\n(:objects {" ".join(cells)} - pos)\n'
            f'(:init\n{" ".join(adj)}\n(need-start) (not (wumpus-at p1-1)) (not (pit-at p1-1)) '
            f'(at p1-1) (alive)\n)\n(:goal (got-the-treasure))\n'
            f'(:hidden (gold-at p{n}-{n}))\n)\n'), adj


# ---------------------------------------------------------- robot checks
@pytest.fixture
def make_env():
    from wumpus.env import WumpusEnv
    made = []

    def make(world):
        made.append(WumpusEnv(world))
        return made[-1]
    yield make
    for e in made:
        e.close()


@pytest.mark.parametrize('n', [5, 10])
def test_problem_from_registry_equals_poster_form(make_env, n):
    env = make_env(WumpusWorld.random(n, 0))
    start = env.robot_cell()
    text = lw1_problem.write_problem(env.registry, start, hidden=[f'(gold-at p{n}-{n})'])
    ref, adj = poster_problem(n)
    assert lw1_problem.compare(text, ref, hidden=True) == {}
    assert len(adj) == 2 * 2 * n * (n - 1)
    mine = lw1_problem.parse(text)
    assert mine['init'][:len(adj)] == adj                      # the listing's order too
    assert mine['objects'] == env.cells() and mine['goal'] == '(got-the-treasure)'
    other = ref.replace('(alive)', '')
    assert lw1_problem.compare(text, other) == {'init': (['(alive)'], [])}


def oracle_actions(world):
    """Test fixture, not a controller: the shortest path over cells that are
    truly free of pits and wumpuses from the start to the gold, as LW1's
    actions.  None when no such path exists."""
    prev, q = {world.start: None}, deque([world.start])
    while q:
        c = q.popleft()
        if c == world.gold:
            break
        for nb in world.neighbors(c):
            if nb not in prev and nb not in world.pits and nb not in world.wumpuses:
                prev[nb] = c
                q.append(nb)
    if world.gold not in prev:
        return None
    path, c = [], world.gold
    while c is not None:
        path.append(c)
        c = prev[c]
    path.reverse()
    acts = [f'start {world.start}']
    acts += [f'move {a} {b}' for a, b in zip(path, path[1:])]
    return acts + [f'grab {world.gold}']


WORLDS = [(5, s) for s in range(5)] + [
    (5, '(:hidden (wumpus-at p3-3) (pit-at p1-4) (gold-at p2-3))'),
    (10, 0)]


@pytest.mark.parametrize('n,src', WORLDS)
def test_replay_oracle_path(make_env, n, src):
    world = (WumpusWorld.from_hidden(n, src) if isinstance(src, str)
             else WumpusWorld.random(n, src))
    acts = oracle_actions(world)
    if acts is None:
        pytest.skip('no safe path to the gold in this world')
    expected = tr.with_rule_obs(world, acts)
    res = replay(make_env(world), expected)
    assert passed(res), (res['status'], res['why'], res['divergence'])
    assert res['mismatches'] == [] and len(res['steps']) == len(acts)
    assert res['steps'][-1]['held'] is True


def test_replay_catches_a_wrong_observation(make_env):
    world = WumpusWorld.from_hidden(5, '(:hidden (wumpus-at p3-3) (pit-at p1-4) (gold-at p2-3))')
    expected = tr.with_rule_obs(world, oracle_actions(world))
    k = 2
    expected[k]['obs'] = {**expected[k]['obs'], 'breeze': not expected[k]['obs']['breeze']}
    res = replay(make_env(world), expected)
    assert not passed(res) and res['mismatches'] == [k]
    assert res['divergence']['k'] == k and res['divergence']['field'] == 'breeze'
    assert res['status'] == 'ok'                    # every action still ran


def test_replay_death_and_wrong_start(make_env):
    world = WumpusWorld.from_hidden(5, '(:hidden (wumpus-at p5-5) (pit-at p2-1) (gold-at p5-1))')
    res = replay(make_env(world), tr.with_rule_obs(world, ['start p1-1', 'move p1-1 p2-1',
                                                           'move p2-1 p3-1']))
    assert res['status'] == 'dead' and res['steps'][-1]['dead'] == 'pit' and len(res['steps']) == 2
    assert lw1_exec.protocol_lines(lw1_exec.execute(make_env(world), 'move p1-2 p1-3')) == \
        ['FAIL move at p1-2, but the robot is at p1-1']


class NoTruth:
    """The env as the LW1 driver sees it: truth() is not there."""

    def __init__(self, env):
        self._env = env

    def __getattr__(self, name):
        if name in ('truth', 'world'):
            raise AttributeError(f'{name} is not for a controller')
        return getattr(self._env, name)


def test_execute_reads_no_truth(make_env):
    world = WumpusWorld.from_hidden(5, '(:hidden (wumpus-at p3-3) (pit-at p1-4) (gold-at p2-3))')
    acts = oracle_actions(world)
    res = replay(NoTruth(make_env(world)), tr.with_rule_obs(world, acts))
    assert passed(res)
