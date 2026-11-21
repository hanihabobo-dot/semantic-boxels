"""What a Wumpus controller tells the curated console, and the run ledger.

The explore test controller calls these functions; path 4's LW1 driver calls
the same ones with LW1's plans and beliefs.  Nothing here knows a controller
or decides anything: every function writes one run_logger ledger row (so the
ledger and the console see the same events) and returns.  Without an open
RunLogger (a unit test, a script) every call is a no-op, and without the
curated console (--log-level normal) the rows are still written.

    begin(size=5, seed=3, ...)                     the run starts (the runner)
    thinking(visited=3, safe=5, maybe_pit=20, ...) the robot thinks about the next plan
    plan([('move', 'p1-2'), ('perceive', 'p1-2')], 0.01)
    action_begin('move', 'p1-2') / action_end(ok=True)
    percept('p1-2', stench=False, breeze=True, glitter=False)
    outcome('success', 'the gold is held')         the run ends (the runner)
    episode_files('runs/x', seed=3, outcome='success', actions=30)   the closing line (the runner)

NarratedEnv wraps anything with the env's move / perceive / grab and makes
the action and percept calls for it, so a controller that only talks to the
env needs to call thinking() and plan() and nothing else.

Words, sprites and sound for these rows are wumpus/console_words.py's.
"""
import time

import console_ui
import run_logger

_S = {'plan': 0, 'step': 0, 'plans': 0, 'cur': None, 'plan_times': [], 'task': None,
      'cells': None, 'size': None}


def _count(x):
    """A number, or the size of a collection, or None."""
    if x is None:
        return None
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, (int, float)):
        return int(x)
    try:
        return len(x)
    except TypeError:
        return None


def reset():
    """Forget the run's counters (a new run in the same process)."""
    _S.update(plan=0, step=0, plans=0, cur=None, plan_times=[], task=None, cells=None, size=None)


def begin(size, seed, controller='explore', source='random', start='p1-1',
          wumpuses=None, pits=None, pace=None, gui=False):
    """The run starts: the mission line and what the world is.  `wumpuses`
    and `pits` are the setup's counts (what the human is shown; the
    controller is never told).  `pace` is the minimum seconds an action's
    drawing stays on screen (a presentation pause, never a decision): None
    means 1.0 with the GUI on and 0.0 without it.  Registers the Wumpus
    words with the console when one is installed."""
    reset()
    pace = (1.0 if gui else 0.0) if pace is None else float(pace)
    try:
        from wumpus import console_words
        task = console_words.WumpusTask(pace=pace)
        _S['task'] = task
        console_ui.set_task(task)
    except Exception:
        pass
    _S['size'] = int(size)
    _S['cells'] = int(size) * int(size)
    run_logger.ledger_event('wumpus_mission', size=int(size), seed=int(seed),
                            controller=str(controller), source=str(source), start=str(start),
                            wumpuses=_count(wumpuses), pits=_count(pits), pace_s=pace,
                            cells=_S['cells'])


def thinking(plan_no=None, visited=None, safe=None, maybe_pit=None, maybe_wumpus=None,
             gold_known=False, cells=None):
    """The robot starts thinking about its next plan and says what it knows.
    visited, safe, maybe_pit and maybe_wumpus are the numbers of cells (or
    the collections of them): where it has been, the cells known safe, the
    cells that may still hold a pit, the cells the wumpus may be in.
    gold_known: it knows where the gold is."""
    pid = int(plan_no) if plan_no is not None else _S['plans'] + 1
    _S['cur'] = pid
    run_logger.ledger_event('wumpus_think', plan_no=pid, visited=_count(visited),
                            safe=_count(safe), maybe_pit=_count(maybe_pit),
                            maybe_wumpus=_count(maybe_wumpus), gold_known=bool(gold_known),
                            cells=_count(cells) if cells is not None else _S['cells'])
    return pid


def plan(actions, plan_time_s=0.0, plan_no=None, goal='gold'):
    """A plan: `actions` is a list of (name, arg) in our names: ('move',
    'p1-2'), ('perceive', 'p1-2'), ('grab', 'p3-2'); None means no plan was
    found.  plan_time_s is the seconds the planner took.  Opens the plan
    that action_begin numbers its steps in."""
    if plan_no is not None:
        pid = int(plan_no)
    elif _S['cur'] is not None:
        pid = _S['cur']
    else:
        pid = _S['plans'] + 1
    _S['cur'] = None
    _S['plans'] = max(_S['plans'], pid)
    _S['plan'], _S['step'] = pid, 0
    dt = float(plan_time_s or 0.0)
    _S['plan_times'].append(dt)
    rows = None if actions is None else [[str(a[0])] + [str(x) for x in a[1:]] for a in actions]
    run_logger.ledger_event('plan', plan_id=pid, call='mission', goal=goal, actions=rows,
                            plan_time_s=dt)
    return pid


def action_begin(action, *args):
    """An action starts (the animation and its line appear).  Returns the
    step number in the plan."""
    _S['step'] += 1
    run_logger.dispatch_begin(_S['plan'], _S['step'], str(action), [str(a) for a in args])
    return _S['step']


def action_end(ok=True, why='', dead=None, wall_s=None):
    """The action ended: ok, failed with `why`, or dead ('pit' or 'wumpus').
    wall_s is the seconds the env reports for it."""
    run_logger.ledger_event('wumpus_action_result', ok=bool(ok), why=str(why or ''),
                            dead=dead, wall_s=wall_s)
    run_logger.dispatch_end('dead' if dead else ('ok' if ok else 'action_failed'))


def percept(cell, stench=False, breeze=False, glitter=False):
    """What the robot perceived in `cell` (call it before the perceive
    action ends, so the console shows it while the action is on)."""
    run_logger.ledger_event('wumpus_percept', cell=str(cell), stench=bool(stench),
                            breeze=bool(breeze), glitter=bool(glitter))


def outcome(outcome, reason='', cell=None, visited=None, held=False):
    """The run ends: 'success' (the gold is held), 'death' (reason 'pit' or
    'wumpus', `cell` where), 'stuck', 'step_limit' or 'error'.  Writes the
    row and closes the console's story with its verdict."""
    run_logger.ledger_event('wumpus_result', outcome=str(outcome), reason=str(reason or ''),
                            cell=cell, visited=_count(visited), cells=_S['cells'],
                            held=bool(held), plans=_S['plans'])
    console_ui.summary(success=(outcome == 'success'),
                       exit_reason=None if outcome == 'success' else str(outcome),
                       plan_count=_S['plans'], plan_times=list(_S['plan_times']),
                       total_plan_time=float(sum(_S['plan_times'])))


def episode_files(where, seed=None, outcome=None, actions=None):
    """The closing line after the verdict, as the bridge prints its outcome
    line: which seed ended how and where the episode's files are.  Call it
    when the files are written (the runner does)."""
    run_logger.ledger_event('wumpus_files', where=str(where), seed=seed, outcome=outcome,
                            actions=actions)


def paced_s():
    """Seconds the presentation pace has held the run so far (subtract them
    from wall times; 0.0 without pace or console)."""
    task = _S.get('task')
    return float(getattr(task, 'paced', 0.0)) if task is not None else 0.0


def pace_s():
    """The pace this run was begun with (seconds an action's drawing stays
    on screen at least; 0.0 when none or no console)."""
    task = _S.get('task')
    return float(getattr(task, 'pace', 0.0)) if task is not None else 0.0


class NarratedEnv:
    """The env as a controller sees it, with every move / perceive / grab
    narrated; everything else (cells, adjacent, robot_cell, registry, ...)
    passes straight through."""

    def __init__(self, env):
        self._env = env

    def __getattr__(self, name):
        return getattr(self._env, name)

    def _run(self, action, cell, call, show):
        action_begin(action, cell)
        try:
            res = call()
        except BaseException as ex:
            action_end(ok=False, why=f'{type(ex).__name__}: {ex}')
            raise
        show(res)
        action_end(ok=bool(res.get('ok')), why=res.get('why', ''), dead=res.get('dead'),
                   wall_s=res.get('wall_s'))
        return res

    def move(self, cell):
        return self._run('move', cell, lambda: self._env.move(cell), lambda r: None)

    def perceive(self):
        here = self._env.robot_cell()

        def show(r):
            if r.get('ok'):
                percept(r.get('cell') or here, r.get('stench'), r.get('breeze'), r.get('glitter'))
        return self._run('perceive', here, self._env.perceive, show)

    def grab(self):
        return self._run('grab', self._env.robot_cell(), self._env.grab, lambda r: None)
