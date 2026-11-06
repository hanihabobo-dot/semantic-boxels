"""A Wumpus episode on the curated console without PyBullet.

    python wumpus/narrate_demo.py --size 5 --seed 3 [--pace 0.5] [--emulate]

The world's own percept rules (wumpus/world.py) answer through StandInEnv,
which has the env's calls and result dicts but no physics; a small explore
controller (the same logic as wumpus/explore.py, with the narrate calls) plays
it.  The console, the ledger and the sound behave as in `run wumpus`: this is
how the words, drawings and pace are looked at without a simulator, and the
fixture of tests/test_wumpus_narrate.py.  --emulate sleeps for about as long
as the real env's actions take (move 0.02 s, perceive 0.12 s, grab 1.3 s).
"""
import argparse
import os
import sys
import time
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import console_ui                                       # noqa: E402
console_ui.install_early(__name__)

from wumpus import narrate                              # noqa: E402
from wumpus.world import WumpusWorld                    # noqa: E402


class StandInEnv:
    """The env's calls and result dicts from the world's rules alone."""

    def __init__(self, world, emulate=False):
        self.world, self.emulate = world, emulate
        self.cell, self.dead, self.held = world.start, None, False

    def _nap(self, s):
        if self.emulate:
            time.sleep(s)

    def cells(self):
        return self.world.cells()

    def adjacent(self):
        return [(a, b) for a in self.world.cells() for b in self.world.neighbors(a)]

    def robot_cell(self):
        return self.cell

    def show_knowledge(self, k):
        return None

    def perceive(self):
        self._nap(0.12)
        w, c = self.world, self.cell
        return {'ok': True, 'why': '', 'cell': c, 'stench': w.stench(c), 'breeze': w.breeze(c),
                'glitter': w.glitter(c), 'pixels': {}, 'wall_s': 0.12}

    def move(self, cell):
        self._nap(0.02)
        res = {'ok': False, 'why': '', 'arrived': False, 'dead': None, 'wall_s': 0.02}
        if cell not in self.world.neighbors(self.cell):
            res['why'] = f'{cell} is not adjacent to {self.cell}'
            return res
        self.cell = cell
        res.update(ok=True, arrived=True)
        if cell in self.world.wumpuses:
            self.dead, res['dead'], res['why'] = 'wumpus', 'wumpus', 'killed by the wumpus'
        elif cell in self.world.pits:
            self.dead, res['dead'], res['why'] = 'pit', 'pit', 'fell into the pit'
        return res

    def grab(self):
        self._nap(1.3)
        ok = self.world.glitter(self.cell)
        self.held = self.held or ok
        return {'ok': ok, 'why': '' if ok else 'no gold seen in this cell', 'held': self.held,
                'wall_s': 1.3}


def explore(env, max_steps=500, die=None):
    """wumpus/explore.py's logic with the narrate calls (thinking, plan).
    die='pit' or 'wumpus': after the first look the controller walks
    straight to that hazard (a demo of the death words and drawings, which
    the careful explore never reaches)."""
    nbrs = {}
    for a, b in env.adjacent():
        nbrs.setdefault(a, []).append(b)
    cells = env.cells()
    no_pit, no_wumpus, visited = set(), set(), set()
    steps = 0

    def safe(c):
        return c in visited or (c in no_pit and c in no_wumpus)

    def done(outcome, reason):
        return {'outcome': outcome, 'reason': reason, 'visited': len(visited)}

    def knowledge(gold=False):
        return dict(visited=len(visited), safe=sum(1 for c in cells if safe(c)),
                    maybe_pit=len(cells) - len(no_pit), maybe_wumpus=len(cells) - len(no_wumpus),
                    gold_known=gold)

    def look(here):
        narrate.thinking(**knowledge())
        t0 = time.perf_counter()
        narrate.plan([('perceive', here)], time.perf_counter() - t0)
        pc = env.perceive()
        if not pc['ok']:
            return None, pc
        visited.add(here)
        if not pc['breeze']:
            no_pit.update(nbrs.get(here, []))
        if not pc['stench']:
            no_wumpus.update(nbrs.get(here, []))
        no_pit.add(here)
        no_wumpus.add(here)
        return here, pc

    cell, pc = look(env.robot_cell())
    steps += 1
    if die:
        hazard = next(iter(env.world.pits if die == 'pit' else env.world.wumpuses))
        prev, q = {cell: None}, deque([cell])
        while q:
            c = q.popleft()
            for n in nbrs.get(c, []):
                if n not in prev:
                    prev[n] = c
                    q.append(n)
        path, c = [], hazard
        while prev[c] is not None:
            path.append(c)
            c = prev[c]
        path.reverse()
        narrate.thinking(**knowledge())
        narrate.plan([('move', c) for c in path], 0.0)
        for c in path:
            r = env.move(c)
            if r['dead']:
                return done('death', r['dead'])
    while True:
        if cell is None:
            return done('error', f"perceive failed: {pc['why']}")
        if pc['glitter']:
            narrate.thinking(**knowledge(gold=True))
            t0 = time.perf_counter()
            narrate.plan([('grab', cell)], time.perf_counter() - t0)
            g = env.grab()
            if g['held']:
                return done('success', 'the gold is held')
            return done('error', f"grab failed: {g['why']}")
        narrate.thinking(**knowledge())
        t0 = time.perf_counter()
        prev, seen, q, goal = {cell: None}, {cell}, deque([cell]), None
        while q:
            c = q.popleft()
            if c not in visited:
                goal = c
                break
            for n in nbrs.get(c, []):
                if n not in seen and safe(n):
                    seen.add(n)
                    prev[n] = c
                    q.append(n)
        if goal is None:
            narrate.plan(None, time.perf_counter() - t0)
            return done('stuck', 'no safe unvisited cell is left')
        path = []
        c = goal
        while prev[c] is not None:
            path.append(c)
            c = prev[c]
        path.reverse()
        narrate.plan([('move', c) for c in path] + [('perceive', goal)], time.perf_counter() - t0)
        for c in path:
            if steps >= max_steps:
                return done('step_limit', f'{max_steps} steps')
            r = env.move(c)
            steps += 1
            if r['dead']:
                return done('death', r['dead'])
            if not r['ok']:
                return done('error', f"move to {c} failed: {r['why']}")
        pc = env.perceive()
        steps += 1
        if not pc['ok']:
            return done('error', f"perceive failed: {pc['why']}")
        visited.add(goal)
        if not pc['breeze']:
            no_pit.update(nbrs.get(goal, []))
        if not pc['stench']:
            no_wumpus.update(nbrs.get(goal, []))
        no_pit.add(goal)
        no_wumpus.add(goal)
        cell = goal


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--size', type=int, default=5)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--pace', type=float, default=0.0)
    ap.add_argument('--emulate', action='store_true')
    ap.add_argument('--die', choices=['pit', 'wumpus'], help='walk into that hazard (a demo of the death words)')
    ap.add_argument('--log-level', default='smart', choices=['smart', 'normal', 'quiet', 'verbose'])
    ap.add_argument('--log-dir', default='logs')
    a = ap.parse_args(argv)
    from run_logger import RunLogger
    world = WumpusWorld.random(a.size, a.seed)
    logger = RunLogger(verbosity=a.log_level, log_dir=a.log_dir)
    code = 1
    try:
        narrate.begin(a.size, a.seed, controller='explore', source='random',
                      start=world.start, wumpuses=world.wumpuses, pits=world.pits, pace=a.pace)
        env = narrate.NarratedEnv(StandInEnv(world, emulate=a.emulate))
        out = explore(env, die=a.die)
        narrate.outcome(out['outcome'], out['reason'], cell=env.robot_cell(),
                        visited=out['visited'], held=out['outcome'] == 'success')
        code = 0 if out['outcome'] == 'success' else 1
    finally:
        logger.close()
    console_ui.finish(code)


if __name__ == '__main__':
    main()
