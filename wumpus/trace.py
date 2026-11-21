"""Traces of a Wumpus episode in LW1's terms, for the gates (PLAN.md
section 7).

A trace is a list of steps ``{'action': [name, cell, ...], 'obs': {'stench':
bool, 'breeze': bool, 'glitter': bool} or None}``: the actions in the order
they were executed and the observation each start or move returned.  L (LW1
alone) gets its trace from LW1's own output, P (LW1 driving the robot) from
the driver's record, the replay (G-W2) from the robot.

- G-W2: ``first_divergence(lw1_trace, robot_trace)`` is None when our
  observation equals LW1's sensed literals at every step.
- G-W3: ``first_divergence(L_trace, P_trace)`` is None when P executed L's
  actions, action for action, with the same observations.
"""
import json

OBS_VARS = ('stench', 'breeze', 'glitter')


def step(action, obs=None):
    """One trace step; action as a sequence or 'move p1-1 p1-2'."""
    if isinstance(action, str):
        action = action.split()
    out = {'action': [str(a).lower() for a in action], 'obs': None}
    if obs is not None:
        out['obs'] = {v: bool(obs[v]) for v in OBS_VARS}
    return out


def percept_obs(world, cell):
    """The observation the world's percept rule gives at a cell: what LW1's
    simulator computes from its hidden state with the domain's sensing
    model.  For checks only, never for a controller."""
    return {'stench': world.stench(cell), 'breeze': world.breeze(cell),
            'glitter': world.glitter(cell)}


def with_rule_obs(world, actions):
    """A trace of actions with the percept rule's observations filled in
    (start and move sense at their last cell, grab senses nothing)."""
    out = []
    for a in actions:
        st = step(a)
        if st['action'][0] in ('start', 'move'):
            st['obs'] = percept_obs(world, st['action'][-1])
        out.append(st)
    return out


def first_divergence(a, b):
    """None when the traces agree step for step (same actions, same
    observations, same length); else {'k', 'field', 'a', 'b'} for the first
    difference.  A step whose obs is None on either side compares actions
    only (a trace of actions alone)."""
    for k, (x, y) in enumerate(zip(a, b)):
        if list(x['action']) != list(y['action']):
            return {'k': k, 'field': 'action', 'a': x['action'], 'b': y['action']}
        if x.get('obs') is not None and y.get('obs') is not None:
            for v in OBS_VARS:
                if bool(x['obs'][v]) != bool(y['obs'][v]):
                    return {'k': k, 'field': v, 'a': x['obs'][v], 'b': y['obs'][v],
                            'action': x['action']}
    if len(a) != len(b):
        k = min(len(a), len(b))
        return {'k': k, 'field': 'length', 'a': len(a), 'b': len(b)}
    return None


def load(path):
    """A trace from a JSON file (a list of steps, or {'trace': [...]}) or from
    a text file with one action per line ('#' starts a comment)."""
    with open(path, 'r') as f:
        text = f.read()
    try:
        data = json.loads(text)
    except ValueError:
        acts = [ln.split('#')[0].strip() for ln in text.splitlines()]
        return [step(a) for a in acts if a]
    if isinstance(data, dict):
        data = data['trace']
    return [step(s['action'], s.get('obs')) for s in data]
