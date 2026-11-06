"""LW1's Wumpus actions executed by our robot (PLAN.md section 6, "Mapping
to our execution").

LW1's domain (their d.pddl, the poster's listing) has three actions:

    start ?j      at the start cell j: sense there
    move ?i ?j    drive from i to the adjacent cell j, then sense at j
    grab ?i       take the gold at i

After start and move, LW1's sensing model gives the values of the
observable variables stench(j), breeze(j) and glitter(j).  ``execute`` runs
one LW1 action on the env and returns that observation from our camera and
perception (env.perceive), never from the world's hidden state: the env a
controller gets has no truth().  The LW1 driver answers LW1's EXEC lines
with it (``protocol_lines``); the replay (G-W2) compares it with LW1's own
sensed literals.
"""
import re

OBS_VARS = ('stench', 'breeze', 'glitter')
ACTIONS = {'start': 1, 'move': 2, 'grab': 1}      # name -> number of cell arguments
_TOKEN = re.compile(r'[^\s()]+')


def parse_action(text):
    """'(move p1-1 p1-2)', 'move p1-1 p1-2' or FF's 'MOVE P1-1 P1-2' ->
    ('move', 'p1-1', 'p1-2').  Raises ValueError for anything else."""
    parts = tuple(t.lower() for t in _TOKEN.findall(str(text)))
    if not parts or parts[0] not in ACTIONS or len(parts) != 1 + ACTIONS[parts[0]]:
        raise ValueError(f'not an LW1 Wumpus action: {text!r}')
    return parts


def action_text(action):
    """('move', 'p1-1', 'p1-2') -> 'move p1-1 p1-2'."""
    return ' '.join(action)


def execute(env, action):
    """Run one LW1 action on the robot.  Returns

        {'action': tuple, 'status': 'ok' | 'dead' | 'fail', 'why': str,
         'cell': the robot's cell after it, 'obs': {stench, breeze, glitter}
         (bools; start and move only), 'dead': None | 'pit' | 'wumpus',
         'held': bool (grab only), 'raw': the env's own results}

    'fail' means the robot could not do what LW1 asked (it is not where LW1
    believes it is, a drive stopped short, perception was ambiguous, the
    grab did not verify); it ends the episode as an error.  'dead' is the
    world's verdict on a move into a pit or a wumpus cell."""
    action = parse_action(action) if isinstance(action, str) else tuple(action)
    name, args = action[0], action[1:]
    res = {'action': action, 'status': 'fail', 'why': '', 'cell': None, 'obs': None,
           'dead': None, 'held': None, 'raw': []}

    def finish(status, why=''):
        res['status'], res['why'] = status, why
        res['cell'] = env.robot_cell()
        return res

    def sense(cell):
        pc = env.perceive()
        res['raw'].append({'call': 'perceive', **pc})
        if not pc['ok']:
            return finish('fail', f"perceive at {cell} failed: {pc['why']}")
        if pc['cell'] != cell:
            return finish('fail', f"perceived at {pc['cell']}, expected {cell}")
        res['obs'] = {v: bool(pc[v]) for v in OBS_VARS}
        return finish('ok')

    here = env.robot_cell()
    if name not in ACTIONS or len(args) != ACTIONS[name]:
        return finish('fail', f'unknown action {action}')
    if here != args[0]:
        return finish('fail', f'{name} at {args[0]}, but the robot is at {here}')
    if name == 'start':
        return sense(args[0])
    if name == 'move':
        target = args[1]
        r = env.move(target)
        res['raw'].append({'call': 'move', **r})
        if r['dead']:
            res['dead'] = r['dead']
            return finish('dead', r['why'])
        if not r['ok']:
            return finish('fail', f"move to {target} failed: {r['why']}")
        if env.robot_cell() != target:
            return finish('fail', f'the robot is at {env.robot_cell()}, not at {target}')
        return sense(target)
    g = env.grab()                                    # name == 'grab'
    res['raw'].append({'call': 'grab', **g})
    res['held'] = bool(g['held'])
    if not g['held']:
        return finish('fail', f"grab at {args[0]} failed: {g['why']}")
    return finish('ok')


def protocol_lines(result):
    """The driver's answer to LW1's EXEC line (the patch's protocol, PLAN.md
    section 6): the observation as 'OBS <var> <cell> <0|1>' lines and 'END',
    or 'DEAD pit|wumpus', or 'FAIL <why>'."""
    if result['status'] == 'dead':
        return [f"DEAD {result['dead']}"]
    if result['status'] != 'ok':
        why = ' '.join(str(result['why']).split()) or 'unknown'
        return [f'FAIL {why}']
    lines = []
    if result['obs'] is not None:
        cell = result['action'][-1]
        lines += [f"OBS {v} {cell} {int(result['obs'][v])}" for v in OBS_VARS]
    return lines + ['END']
