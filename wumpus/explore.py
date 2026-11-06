"""The explore test controller (for the env only, not a result).

It keeps its own propositional knowledge from perceive() alone: a visited
cell without breeze makes its neighbours pit-free, without stench
wumpus-free; a cell proven free of both is safe.  It goes to the nearest
unvisited safe cell over visited or safe cells, grabs on glitter, and stops
('stuck') when no safe unvisited cell is left.  Never reads truth().
"""
from collections import deque


def run_explore(env, max_steps=500, log=print):
    """env: anything with cells(), adjacent(), robot_cell(), perceive(), move(),
    grab() (the runner passes a logging wrapper).  Returns {'outcome', 'reason'}."""
    nbrs = {}
    for a, b in env.adjacent():
        nbrs.setdefault(a, []).append(b)
    no_pit, no_wumpus, visited = set(), set(), set()
    steps = 0

    def safe(c):
        return c in visited or (c in no_pit and c in no_wumpus)

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
            env.show_knowledge({c: ('safe' if safe(c) else 'unknown') for c in env.cells()})
        return cell, pc

    cell, pc = observe()
    steps += 1
    while True:
        if cell is None:
            return {'outcome': 'error', 'reason': f"perceive failed: {pc['why']}"}
        if pc['glitter']:
            g = env.grab()
            steps += 1
            if g['held']:
                return {'outcome': 'success', 'reason': 'the gold is held'}
            return {'outcome': 'error', 'reason': f"grab failed: {g['why']}"}
        # nearest unvisited safe cell by BFS over safe cells
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
            return {'outcome': 'stuck', 'reason': 'no safe unvisited cell is left'}
        path = []
        c = goal
        while prev[c] is not None:
            path.append(c)
            c = prev[c]
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
