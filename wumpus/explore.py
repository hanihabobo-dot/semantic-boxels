"""The explore test controller (for the env only, not a result).

It keeps its own propositional knowledge from perceive() alone: a visited
cell without breeze makes its neighbours pit-free, without stench
wumpus-free; a cell proven free of both is safe.  It goes to the nearest
unvisited safe cell over visited or safe cells, grabs on glitter, and stops
('stuck') when no safe unvisited cell is left.  Never reads truth().
"""
import time
from collections import deque


def run_explore(env, max_steps=500, log=print, narrate=None):
    """env: anything with cells(), adjacent(), robot_cell(), perceive(), move(),
    grab() (the runner passes a logging wrapper).  Returns {'outcome', 'reason'}.

    narrate: wumpus/narrate.py (anything with thinking() and plan()).  The
    controller tells it what it knows before it plans and the plan it made,
    and nothing it answers is read: with None the run is the same and silent."""
    nbrs = {}
    for a, b in env.adjacent():
        nbrs.setdefault(a, []).append(b)
    no_pit, no_wumpus, visited = set(), set(), set()
    steps = 0
    cells = list(env.cells())

    def safe(c):
        return c in visited or (c in no_pit and c in no_wumpus)

    def known(gold_at=None):
        """What it knows per cell, in wumpus/knowledge.py's form, for the GUI's
        painter: hazards ruled out by its sets, the gold seen at `gold_at` (a
        visited cell without glitter holds none); nothing read back."""
        out = {}
        for c in cells:
            e = {}
            if c in no_pit or c in visited:
                e['pit'] = 'no'
            if c in no_wumpus or c in visited:
                e['wumpus'] = 'no'
            if c == gold_at:
                e['gold'] = 'yes'
            elif c in visited:
                e['gold'] = 'no'
            if c in visited:
                e['visited'] = True
            if e:
                out[c] = e
        return out

    def thinking(gold=False):
        """The robot starts thinking and says what it knows; returns the start time."""
        if narrate is not None:
            narrate.thinking(visited=len(visited), safe=sum(1 for c in cells if safe(c)),
                             maybe_pit=len(cells) - len(no_pit),
                             maybe_wumpus=len(cells) - len(no_wumpus), gold_known=gold)
        return time.perf_counter()

    def plan(actions, t0):
        """The plan it made ((name, cell) pairs, None for no plan) and the seconds it took."""
        if narrate is not None:
            narrate.plan(actions, time.perf_counter() - t0)

    def observe():
        cell = env.robot_cell()
        pc = env.perceive()
        if not pc['ok']:
            return None, pc
        visited.add(cell)
        if not pc['breeze']:
            no_pit.update(nbrs.get(cell, []))
        if not pc['stench']:
            no_wumpus.update(nbrs.get(cell, []))
        no_pit.add(cell)
        no_wumpus.add(cell)
        if hasattr(env, 'show_knowledge'):
            env.show_knowledge(known(gold_at=cell if pc['glitter'] else None))
        return cell, pc

    t0 = thinking()
    plan([('perceive', env.robot_cell())], t0)
    cell, pc = observe()
    steps += 1
    while True:
        if cell is None:
            return {'outcome': 'error', 'reason': f"perceive failed: {pc['why']}"}
        if pc['glitter']:
            t0 = thinking(gold=True)
            plan([('grab', cell)], t0)
            g = env.grab()
            steps += 1
            if g['held']:
                return {'outcome': 'success', 'reason': 'the gold is held'}
            return {'outcome': 'error', 'reason': f"grab failed: {g['why']}"}
        # nearest unvisited safe cell by BFS over safe cells
        t0 = thinking()
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
            plan(None, t0)
            return {'outcome': 'stuck', 'reason': 'no safe unvisited cell is left'}
        path = []
        c = goal
        while prev[c] is not None:
            path.append(c)
            c = prev[c]
        plan([('move', c) for c in reversed(path)] + [('perceive', goal)], t0)
        for c in reversed(path):
            if steps >= max_steps:
                return {'outcome': 'step_limit', 'reason': f'{max_steps} steps'}
            r = env.move(c)
            steps += 1
            if r['dead']:
                return {'outcome': 'death', 'reason': r['dead']}
            if not r['ok']:
                return {'outcome': 'error', 'reason': f"move to {c} failed: {r['why']}"}
        cell, pc = observe()
        steps += 1
