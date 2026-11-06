"""Path 4's LW1 driver without LW1 and without physics: a fake LW1 (a script
that speaks the patch's protocol over the two pipes) and a fake env.  The
real LW1 on the robot is the P runs' job (under the pipeline lock); these
tests start no episode.  Linux only (named pipes)."""
import os
import stat
import sys

import pytest

from wumpus import lw1_driver as drv

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='named pipes')

FAKE_LW1 = r'''#!/usr/bin/env python3
import os, sys
MODE = os.environ.get('FAKE_MODE', 'ok')
if MODE == 'fail-early':
    print('calling ff (n=1, acc-time=0)...', flush=True)
    print('\x1b[31;1munable to solve problem: \x1b[0merror during action/plan computation', flush=True)
    print('stats: ff (action-selection) -1 (plan-size) 1 (as-calls) 0.1 (preprocessing-time) 0.01 (as-time) 0 (as-search-time) 0 (inference-time) 0.02 (instance-time) 0.12 (total-acc-time)', flush=True)
    sys.exit(0)
ex = open(os.environ['LW1_EXEC_FIFO'], 'w')
ob = open(os.environ['LW1_OBS_FIFO'])
def say(s):
    ex.write(s + '\n'); ex.flush()
def answer():
    got = []
    for line in ob:
        line = line.strip()
        if line == 'END':
            return got
        if line.startswith(('DEAD', 'FAIL')):
            print('external: ' + line, flush=True)
            sys.exit(3 if line.startswith('DEAD') else 4)
        got.append(line)
    sys.exit(5)
print('calling ff (n=1, acc-time=0)...', flush=True)
say('PLAN start_p1-1;move_p1-1_p1-2;grab_p1-2')
say('EXEC start_p1-1')
a0 = answer()
say('BELIEF [s={(K_not_wumpus-at_p1-2),(K_not_pit-at_p1-2),(K_wumpus-at_p2-2),(K_pit-at_p2-1_UNUSED)}]')
say('EXEC move_p1-1_p1-2')
a1 = answer()
say('EXEC grab_p1-2')
a2 = answer()
print('PLAN:    0 : start_p1-1', flush=True)
print('ANSWERS ' + ' | '.join(a0 + a1 + a2), flush=True)
print('stats: ff (action-selection) 3 (plan-size) 1 (as-calls) 0.1 (preprocessing-time) 0.01 (as-time) 0.001 (as-search-time) 0.0001 (inference-time) 0.02 (instance-time) 0.12 (total-acc-time)', flush=True)
'''


class _Boxel:
    def __init__(self, nb):
        self.neighbor_ids = nb


class _Registry:
    def __init__(self, n):
        self.boxels = {}
        for i in range(1, n + 1):
            for j in range(1, n + 1):
                self.boxels[f'p{i}-{j}'] = _Boxel({'x_pos': [f'p{i + 1}-{j}'] if i < n else [],
                                                   'y_pos': [f'p{i}-{j + 1}'] if j < n else []})

    def get_boxel(self, c):
        return self.boxels[c]


class FakeEnv:
    """The env as the driver sees it, on a 2x2 board: breeze at p1-1, the
    gold at p1-2, optionally a pit."""
    world_size = 2

    def __init__(self, pit=None):
        self.cell, self.pit, self.registry, self.known = 'p1-1', pit, _Registry(2), []

    def cells(self):
        return list(self.registry.boxels)

    def robot_cell(self):
        return self.cell

    def show_knowledge(self, k):
        self.known.append(k)

    def move(self, cell):
        self.cell = cell
        dead = 'pit' if cell == self.pit else None
        return {'ok': True, 'why': 'fell into the pit' if dead else '', 'dead': dead, 'wall_s': 0.0}

    def perceive(self):
        return {'ok': True, 'why': '', 'cell': self.cell, 'stench': False,
                'breeze': self.cell == 'p1-1', 'glitter': self.cell == 'p1-2', 'wall_s': 0.0}

    def grab(self):
        held = self.cell == 'p1-2'
        return {'ok': held, 'held': held, 'why': '' if held else 'no gold here', 'wall_s': 0.0}


class FakeNarrate:
    def __init__(self):
        self.calls = []

    def thinking(self, **kw):
        self.calls.append(('thinking', kw))

    def plan(self, actions, plan_time_s=0.0, plan_no=None):
        self.calls.append(('plan', actions, plan_no))


@pytest.fixture
def setup(tmp_path):
    lw1 = tmp_path / 'fake_lw1'
    lw1.write_text(FAKE_LW1)
    lw1.chmod(lw1.stat().st_mode | stat.S_IEXEC)
    bench = tmp_path / 'bench'
    (bench / 'p02-1f').mkdir(parents=True)
    (bench / 'p02-1f' / 'd2.pddl').write_text('(define (domain wumpus))\n')
    return {'lw1': str(lw1), 'bench': str(bench), 'runs_dir': str(tmp_path / 'runs')}


def _run(setup, env, mode='ok'):
    os.environ['FAKE_MODE'] = mode
    nar = FakeNarrate()
    try:
        res = drv.run_lw1(env, lw1=setup['lw1'], bench=setup['bench'], runs_dir=setup['runs_dir'],
                          narrate=nar, log=lambda *a: None, max_time=60)
    finally:
        os.environ.pop('FAKE_MODE', None)
    return res, nar


def test_success_through_the_pipes(setup):
    env = FakeEnv()
    res, nar = _run(setup, env)
    assert res['outcome'] == 'success', res
    assert [s['action'] for s in res['trace']] == [['start', 'p1-1'], ['move', 'p1-1', 'p1-2'], ['grab', 'p1-2']]
    assert res['trace'][0]['obs'] == {'stench': False, 'breeze': True, 'glitter': False}
    assert res['trace'][1]['obs'] == {'stench': False, 'breeze': False, 'glitter': True}
    assert res['trace'][2]['obs'] is None
    assert res['lw1']['exit'] == 0 and res['lw1']['stats']['plan'] == 3 and res['lw1']['beliefs'] == 1
    assert res['plans'][0]['actions'] == [['start', 'p1-1'], ['move', 'p1-1', 'p1-2'], ['grab', 'p1-2']]
    # the fake LW1 got exactly the OBS lines of protocol_lines
    out = open(os.path.join(res['lw1']['run_dir'], 'lw1_out.txt')).read()
    assert 'ANSWERS OBS stench p1-1 0 | OBS breeze p1-1 1 | OBS glitter p1-1 0 | OBS stench p1-2 0 | ' \
           'OBS breeze p1-2 0 | OBS glitter p1-2 1' in out
    # the overlay: p1-2 known safe, p2-2 known wumpus, the _UNUSED atom ignored
    assert env.known[0] == {'p1-1': 'unknown', 'p1-2': 'safe', 'p2-1': 'unknown', 'p2-2': 'danger'}
    assert nar.calls[0][0] == 'thinking' and nar.calls[0][1]['plan_no'] == 1
    assert nar.calls[1] == ('plan', [('perceive', 'p1-1'), ('move', 'p1-2'), ('perceive', 'p1-2'),
                                     ('grab', 'p1-2')], 1)
    # the pipes are gone, the record stays
    assert not any(f.endswith('.fifo') for f in os.listdir(res['lw1']['run_dir']))
    assert open(os.path.join(res['lw1']['run_dir'], 'hidden.pddl')).read().count('(gold-at p1-1)') == 1


def test_death_ends_lw1(setup):
    res, _ = _run(setup, FakeEnv(pit='p1-2'))
    assert res['outcome'] == 'death' and res['reason'] == 'pit'
    assert res['lw1']['exit'] == 3 and res['lw1']['external'].startswith('DEAD pit')
    assert len(res['steps']) == 2


def test_lw1_failing_before_any_action(setup):
    res, _ = _run(setup, FakeEnv(), mode='fail-early')
    assert res['outcome'] == 'error' and res['reason'] == 'error during action/plan computation'
    assert res['steps'] == [] and res['lw1']['calls'] == [1]


def test_pure_helpers():
    cells = ['p1-1', 'p1-2', 'p1-12']
    state, counts = drv.knowledge('(K_not_wumpus-at_p1-12),(K_not_pit-at_p1-12),(K_not_pit-at_p1-1),'
                                  '(K_gold-at_p1-2),(K_wumpus-at_p1-2_UNUSED)', cells)
    assert state == {'p1-1': 'unknown', 'p1-2': 'unknown', 'p1-12': 'safe'}
    assert counts == {'safe': 1, 'maybe_pit': 1, 'maybe_wumpus': 2, 'gold_known': True}
    assert drv.our_calls([('start', 'p1-1'), ('move', 'p1-1', 'p2-1')]) == [
        ('perceive', 'p1-1'), ('move', 'p2-1'), ('perceive', 'p2-1')]
    p = drv.parse_stdout(['\x1b[31;1munable to solve problem: \x1b[0mproblem has no solution!'])
    assert drv.classify([], 0, p) == ('stuck', 'problem has no solution!')
    assert drv.classify([], 255, drv.parse_stdout([])) == ('error', 'LW1 exited with code 255')
