"""The controller-neutral per-cell knowledge (wumpus/knowledge.py) and the
explore controller's feed of it.  Pure: no simulator, no planner, no episode."""
import pytest

from wumpus import knowledge as kn
from wumpus.explore import run_explore

FLOOR_GREYS = ((0.62, 0.62, 0.62, 1), (0.45, 0.45, 0.47, 1))     # env.py's checkerboard


def test_entry_and_normalize():
    cells = ['p1-1', 'p1-2', 'p2-1']
    view = kn.normalize({'p1-1': {'pit': 'no', 'wumpus': 'no', 'visited': True}, 'p1-2': 'safe'}, cells)
    assert view['p1-1'] == {'wumpus': 'no', 'pit': 'no', 'gold': 'maybe', 'visited': True, 'danger': False}
    assert view['p1-2'] == {'wumpus': 'no', 'pit': 'no', 'gold': 'maybe', 'visited': False, 'danger': False}
    assert view['p2-1'] == {'wumpus': 'maybe', 'pit': 'maybe', 'gold': 'maybe', 'visited': False, 'danger': False}
    assert kn.normalize(None, cells) == kn.normalize({}, cells)
    with pytest.raises(ValueError):
        kn.normalize({'p9-9': {}}, cells)
    with pytest.raises(ValueError):
        kn.entry({'pit': 'probably'})
    with pytest.raises(ValueError):
        kn.entry('fine')


@pytest.mark.parametrize('value, state, label', [
    ({}, 'unknown', 'c W? P? G?'),
    ({'gold': 'no'}, 'unknown', 'c W? P?'),
    ({'pit': 'no'}, 'possible', 'c W? G?'),
    ({'wumpus': 'no', 'gold': 'no'}, 'possible', 'c P?'),
    ({'wumpus': 'no', 'pit': 'no'}, 'safe', 'c G?'),
    ({'wumpus': 'no', 'pit': 'no', 'gold': 'no', 'visited': True}, 'visited', 'c'),
    ({'wumpus': 'no', 'pit': 'no', 'gold': 'yes', 'visited': True}, 'visited', 'c G!'),
    ({'wumpus': 'yes', 'pit': 'no', 'gold': 'no'}, 'danger', 'c W!'),
    ({'pit': 'yes'}, 'danger', 'c W? P! G?'),
    ('danger', 'danger', 'c ! W? P? G?'),
    ('unknown', 'unknown', 'c W? P? G?'),
])
def test_tile_state_and_label(value, state, label):
    e = kn.entry(value)
    assert kn.tile_state(e) == state
    assert kn.label('c', e) == label


def test_colours_differ_from_the_floor_and_each_other():
    states = ('danger', 'visited', 'safe', 'possible', 'unknown')
    assert set(kn.TILE_RGBA) == set(states)
    assert len({kn.TILE_RGBA[s] for s in states}) == len(states)
    for s in states:
        assert kn.TILE_RGBA[s] not in FLOOR_GREYS


def test_counts():
    cells = ['p1-1', 'p1-2', 'p2-1', 'p2-2']
    k = {'p1-1': {'wumpus': 'no', 'pit': 'no', 'gold': 'no', 'visited': True},
         'p1-2': {'wumpus': 'no', 'pit': 'no'}, 'p2-1': {'pit': 'no'}, 'p2-2': {'gold': 'yes'}}
    assert kn.counts(k, cells) == {'visited': 1, 'safe': 2, 'maybe_pit': 1, 'maybe_wumpus': 2,
                                   'gold_known': True}


class _Env:
    """A 2x2 board for the explore controller, no physics: a breeze in the
    cells of `breeze` (no pit is needed for one here), the gold at `gold`."""
    def __init__(self, breeze=('p1-1',), gold='p2-2'):
        self.cell, self.known = 'p1-1', []
        self.breeze, self.gold = tuple(breeze), gold

    def cells(self):
        return ['p1-1', 'p1-2', 'p2-1', 'p2-2']

    def adjacent(self):
        pairs = [('p1-1', 'p1-2'), ('p1-1', 'p2-1'), ('p1-2', 'p2-2'), ('p2-1', 'p2-2')]
        return pairs + [(b, a) for a, b in pairs]

    def robot_cell(self):
        return self.cell

    def show_knowledge(self, k):
        self.known.append(k)

    def perceive(self):
        return {'ok': True, 'why': '', 'cell': self.cell, 'stench': False,
                'breeze': self.cell in self.breeze, 'glitter': self.cell == self.gold}

    def move(self, cell):
        self.cell = cell
        return {'ok': True, 'why': '', 'dead': None}

    def grab(self):
        return {'ok': self.cell == self.gold, 'held': self.cell == self.gold, 'why': ''}


def test_explore_feeds_the_painter():
    env = _Env(breeze=('p1-1',), gold='p2-2')
    res = run_explore(env, log=lambda *a: None)
    # a breeze at the start: nothing is safe but p1-1, so the explore controller is stuck,
    # and what it painted says exactly what it knew: p1-1 visited, its neighbours wumpus-free
    assert res['outcome'] == 'stuck'
    assert env.known == [{'p1-1': {'pit': 'no', 'wumpus': 'no', 'gold': 'no', 'visited': True},
                          'p1-2': {'wumpus': 'no'}, 'p2-1': {'wumpus': 'no'}}]
    view = kn.normalize(env.known[0], env.cells())
    assert [kn.tile_state(view[c]) for c in env.cells()] == ['visited', 'possible', 'possible', 'unknown']


def test_explore_paints_the_gold_where_it_sees_glitter():
    env = _Env(breeze=(), gold='p1-2')
    res = run_explore(env, log=lambda *a: None)
    # no breeze: p1-1's neighbours are safe, the nearest is p1-2, where the glitter is
    assert res['outcome'] == 'success', res
    last = env.known[-1]
    assert last['p1-2'] == {'pit': 'no', 'wumpus': 'no', 'gold': 'yes', 'visited': True}
    # a visited cell without glitter holds no gold
    assert last['p1-1']['gold'] == 'no' and last['p1-1']['visited'] is True
    assert kn.label('p1-2', kn.normalize(last, env.cells())['p1-2']) == 'p1-2 G!'
