"""The 3-D Wumpus env (path 4): parser, percept rule, locality gate, driving,
deaths, the grab and perceive() against the ground truth.  Headless; run
under `flock /root/sb_pipeline.lock`."""
import math

import numpy as np
import pytest

from wumpus.world import WumpusWorld, parse_hidden_file, default_counts, cell_ij
from wumpus.env import WumpusEnv, MIN_PIXELS

BLOCK = "(:hidden (wumpus-at p2-3) (pit-at p7-3) (gold-at p9-3) (wumpus-at p6-5) (pit-at p8-5))"


def teleport(env, cell):
    """Place the base on a cell's centre (the checks stand the robot where
    the gate wants it; the controller never does this)."""
    c = env.cell_center(cell)
    env._place_base([c[0], c[1], 0.0])
    env._tick(2)


# ---------------------------------------------------------------- the world
def test_hidden_block_parser():
    w = WumpusWorld.from_hidden(10, BLOCK)
    assert w.n == 10 and w.start == 'p1-1'
    assert w.wumpuses == {'p2-3', 'p6-5'} and w.pits == {'p7-3', 'p8-5'} and w.gold == 'p9-3'


def test_hidden_block_rejects_bad_input():
    with pytest.raises(ValueError):
        WumpusWorld.from_hidden(5, "(:hidden (wumpus-at p2-3))")           # no gold
    with pytest.raises(ValueError):
        WumpusWorld.from_hidden(5, "(:hidden (gold-at p9-9))")             # off the grid
    with pytest.raises(ValueError):
        WumpusWorld.from_hidden(5, "(:hidden (gold-at p3-3) (pit-at p3-3))")   # shared cell


def test_hidden_file_blocks(tmp_path):
    f = tmp_path / 'inst.txt'
    f.write_text("(define (problem a)\n (:hidden (wumpus-at p2-3) (gold-at p3-3))\n)\n"
                 "(define (problem b)\n (:hidden (pit-at p4-4) (gold-at p5-5))\n)\n")
    blocks = parse_hidden_file(str(f))
    assert len(blocks) == 2
    assert WumpusWorld.from_hidden(5, blocks[1]).pits == {'p4-4'}


def test_random_world_rules_and_counts():
    assert default_counts(5) == (1, 1) and default_counts(10) == (2, 2) and default_counts(15) == (4, 4)
    for n in (5, 10, 15):
        for seed in range(20):
            w = WumpusWorld.random(n, seed)
            nw, npit = default_counts(n)
            assert len(w.wumpuses) == nw and len(w.pits) == npit
            bad = {'p1-1', 'p1-2', 'p2-1', 'p2-2'}
            assert not (w.wumpuses | w.pits) & bad
            assert w.gold != 'p1-1'
            assert len(w.wumpuses | w.pits | {w.gold}) == nw + npit + 1
            assert WumpusWorld.random(n, seed).to_dict() == w.to_dict()
    assert len(WumpusWorld.random(5, 0, n_wumpus=2, n_pits=3).pits) == 3


def test_percept_rule():
    w = WumpusWorld.from_hidden(5, "(:hidden (wumpus-at p3-3) (pit-at p1-4) (gold-at p5-5))")
    assert w.stench('p3-2') and w.stench('p2-3') and not w.stench('p3-3') and not w.stench('p2-2')
    assert w.breeze('p1-3') and w.breeze('p2-4') and w.breeze('p1-5') and not w.breeze('p2-3')
    assert w.glitter('p5-5') and not w.glitter('p5-4')
    assert sorted(w.neighbors('p1-1')) == ['p1-2', 'p2-1']


# ----------------------------------------------------------------- the env
def test_cells_adjacency_registry():
    w = WumpusWorld.random(5, 0)
    env = WumpusEnv(w)
    try:
        cells = env.cells()
        assert cells[:3] == ['p1-1', 'p1-2', 'p1-3'] and len(cells) == 25
        adj = env.adjacent()
        assert ('p1-1', 'p1-2') in adj and ('p1-2', 'p1-1') in adj and ('p1-1', 'p2-2') not in adj
        assert len(adj) == 2 * 2 * 5 * 4
        assert set(env.registry.boxels) == set(cells)
        b = env.registry.get_boxel('p2-3')
        assert np.allclose(b.min_corner[:2], [1, 2]) and np.allclose(b.max_corner[:2], [2, 3])
        assert b.neighbor_ids['x_pos'] == ['p3-3'] and b.neighbor_ids['y_neg'] == ['p2-2']
        assert env.robot_cell() == 'p1-1'
    finally:
        env.close()


def locality_check(env):
    w = env.world
    for cell in env.cells():
        teleport(env, cell)
        assert env.robot_cell() == cell
        _, _, _, _, _, seg = env.render()
        for bid in np.unique(seg):
            bid = int(bid)
            if bid in (env.chassis, env.panda):
                continue
            kind, own = env.bodies.get(bid, (None, None))
            assert kind is not None, f'unknown body {bid} seen at {cell}'
            if kind in ('floor', 'wall'):
                assert kind != 'floor' or own == cell, f'floor of {own} seen at {cell}'
                continue
            assert own == cell, f'{kind} of {own} seen from {cell}'


@pytest.mark.parametrize('n,seed', [(5, 0), (5, 1), (5, 2), (10, 0)])
def test_locality_gate(n, seed):
    env = WumpusEnv(WumpusWorld.random(n, seed))
    try:
        locality_check(env)
    finally:
        env.close()


@pytest.mark.parametrize('seed', [0, 1, 2])
def test_perceive_equals_truth_everywhere(seed):
    env = WumpusEnv(WumpusWorld.random(5, seed))
    try:
        for cell in env.cells():
            teleport(env, cell)
            pc = env.perceive()
            assert pc['ok'], (cell, pc['why'])
            t = env.truth(cell)
            assert (pc['stench'], pc['breeze'], pc['glitter']) == (t['stench'], t['breeze'], t['glitter']), cell
            assert pc['cell'] == cell
            for name, n in pc['pixels'].items():
                assert n >= MIN_PIXELS, (cell, name, n)
    finally:
        env.close()


def test_registry_types_follow_perception():
    from boxel_data import BoxelType
    env = WumpusEnv(WumpusWorld.random(5, 0))
    try:
        assert env.registry.get_boxel('p1-1').boxel_type == BoxelType.SHADOW
        env.perceive()
        assert env.registry.get_boxel('p1-1').boxel_type == BoxelType.FREE_SPACE
        assert env.registry.get_boxel('p1-2').boxel_type == BoxelType.SHADOW
    finally:
        env.close()


def test_drive_accuracy():
    w = WumpusWorld.from_hidden(5, "(:hidden (wumpus-at p5-5) (pit-at p4-4) (gold-at p5-1))")
    env = WumpusEnv(w)
    try:
        path = ['p1-2', 'p1-3', 'p2-3', 'p3-3', 'p3-2', 'p3-1', 'p2-1', 'p1-1']
        for c in path:
            r = env.move(c)
            assert r['ok'] and r['arrived'] and r['dead'] is None, r
            ctr = env.cell_center(c)
            assert math.hypot(r['pose']['x'] - ctr[0], r['pose']['y'] - ctr[1]) < 0.02
            assert abs(r['pose']['yaw_deg']) < 2.0
            assert env.robot_cell() == c
        r = env.move('p3-3')                       # not adjacent: refused, no motion
        assert not r['ok'] and 'not adjacent' in r['why'] and env.robot_cell() == 'p1-1'
    finally:
        env.close()


def test_pit_death():
    w = WumpusWorld.from_hidden(5, "(:hidden (wumpus-at p5-5) (pit-at p2-1) (gold-at p5-1))")
    env = WumpusEnv(w)
    try:
        r = env.move('p2-1')
        assert r['dead'] == 'pit' and env.dead == 'pit'
        assert r['pose']['z'] < -1.0
        assert not env.perceive()['ok'] and not env.move('p1-1')['ok']
    finally:
        env.close()


def test_wumpus_death():
    w = WumpusWorld.from_hidden(5, "(:hidden (wumpus-at p1-2) (pit-at p5-4) (gold-at p5-1))")
    env = WumpusEnv(w)
    try:
        r = env.move('p1-2')
        assert r['dead'] == 'wumpus' and env.dead == 'wumpus'
        assert not env.perceive()['ok']
    finally:
        env.close()


@pytest.mark.parametrize('seed', [0, 1, 2, 3, 4])
def test_grab_on_five_seeds(seed):
    w = WumpusWorld.random(5, seed)
    env = WumpusEnv(w)
    try:
        # nothing to grab away from the gold
        r = env.grab()
        assert not r['ok'] and not r['held']
        teleport(env, w.gold)
        r = env.grab()
        assert r['ok'] and r['held'], r
        import pybullet as p
        z = p.getBasePositionAndOrientation(env.bar, physicsClientId=env.cid)[0][2]
        assert z > 0.15
    finally:
        env.close()
