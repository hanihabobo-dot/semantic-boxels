"""One Wumpus episode: python wumpus/run_wumpus.py --size 5 --seed 3 --vis 0.

Writes episode.json into --save-dir: the instance, every step (action,
observation, ground truth beside it, pose, sim steps, times), the outcome and
the wall times.  Controllers get a logging wrapper that has no truth().

At --log-level smart (the default) the terminal shows the curated console that
run boxels and run tampura use: the robot says what it knows and what it will
do, every action has its drawing and one line, and the raw output of the whole
process goes to <run_dir>/console_debug.log.  wumpus/narrate.py is what a
controller tells that console; it never feeds a decision.
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import console_ui                                          # noqa: E402
console_ui.install_early(__name__)     # before pybullet's import banner, like the other entry points

from wumpus.world import WumpusWorld, parse_hidden_file   # noqa: E402


class LoggedEnv:
    """The env as a controller sees it: same calls, every one recorded, no truth()."""

    def __init__(self, env, steps, verbose=True):
        self._env, self.steps, self.verbose = env, steps, verbose

    def cells(self): return self._env.cells()
    def adjacent(self): return self._env.adjacent()
    def robot_cell(self): return self._env.robot_cell()
    @property
    def registry(self): return self._env.registry
    @property
    def world_size(self): return self._env.world.n
    def show_knowledge(self, k): return self._env.show_knowledge(k)

    def _rec(self, action, arg, res, cell_before):
        env = self._env
        here = env.robot_cell()
        truth = env.truth(here) if here else None
        self.steps.append({'k': len(self.steps), 'action': action, 'arg': arg,
                           'from': cell_before, 'cell': here, 'result': res,
                           'truth_here': truth, 'pose': env.pose()})
        if self.verbose:
            print(f"  [{len(self.steps) - 1:3d}] {action:8s} {arg or '':6s} -> {here}  "
                  f"{ {k: v for k, v in res.items() if k in ('ok', 'why', 'dead', 'held', 'stench', 'breeze', 'glitter')} }")

    def perceive(self):
        b = self._env.robot_cell()
        r = self._env.perceive()
        self._rec('perceive', None, r, b)
        return r

    def move(self, cell):
        b = self._env.robot_cell()
        r = self._env.move(cell)
        self._rec('move', cell, r, b)
        return r

    def grab(self):
        b = self._env.robot_cell()
        r = self._env.grab()
        self._rec('grab', None, r, b)
        return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--size', type=int, default=5)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--source', choices=['hidden', 'random'], default='random')
    ap.add_argument('--hidden-file')
    ap.add_argument('--controller', choices=['explore', 'lw1'], default='explore')
    ap.add_argument('--vis', type=int, default=0)
    ap.add_argument('--save-dir')
    ap.add_argument('--max-steps', type=int, default=500)
    ap.add_argument('--hold', type=float, default=None, help='seconds the GUI stays open at the end')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--log-level', choices=['smart', 'normal', 'quiet', 'verbose'], default='smart',
                    help='Console verbosity. "smart" (default) is the curated console (the robot says '
                         'what it knows, what it will do and what happened) and sends the raw output of '
                         'the whole process to <run_dir>/console_debug.log. "normal", "quiet" and '
                         '"verbose" leave stdout untouched.')
    ap.add_argument('--log-dir', default='logs', help='where the run directory goes (default logs)')
    ap.add_argument('--pace', type=float, default=None,
                    help='seconds each action, thought and percept stays on the console at least, so '
                         'that a human can follow it (default 1.0 with the GUI, 0 without; a pause of '
                         'the presentation only, never part of a decision)')
    a = ap.parse_args(argv)

    if a.controller == 'lw1':
        from wumpus import lw1_driver
        if not lw1_driver.AVAILABLE:
            return _refuse('run_wumpus: --controller lw1 is not plugged in yet (path 4 fills '
                           'wumpus/lw1_driver.py); use --controller explore', 3)
    if a.source == 'hidden':
        if not a.hidden_file:
            return _refuse('run_wumpus: --source hidden needs --hidden-file', 2)
        blocks = parse_hidden_file(a.hidden_file)
        if a.seed >= len(blocks):
            return _refuse(f'run_wumpus: the file has {len(blocks)} blocks, no block {a.seed}', 2)
        world = WumpusWorld.from_hidden(a.size, blocks[a.seed])
    else:
        world = WumpusWorld.random(a.size, a.seed)

    from run_logger import RunLogger
    logger = RunLogger(verbosity=a.log_level, log_dir=a.log_dir)
    try:
        return _episode(a, world, logger)
    finally:
        logger.close()


def _refuse(message, code):
    """A start that cannot go on: on stderr as before, and on the curated
    console (where stderr goes to console_debug.log)."""
    print(message, file=sys.stderr)
    console_ui.warn(message)
    return code


def _episode(a, world, logger):
    """One episode on the built world; the run logger (the curated console
    with it) is open."""
    from wumpus import narrate
    from wumpus.env import WumpusEnv
    console_ui.startup(f'Building the {a.size}x{a.size} world, seed {a.seed}')
    t0 = time.time()
    env = WumpusEnv(world, gui=bool(a.vis), save_dir=a.save_dir)
    build_s = time.time() - t0
    steps = []
    print(f'wumpus: N={a.size} seed={a.seed} source={a.source} controller={a.controller} '
          f'wumpuses={sorted(world.wumpuses)} pits={sorted(world.pits)} gold={world.gold}')
    narrate.begin(a.size, a.seed, controller=a.controller, source=a.source, start=world.start,
                  wumpuses=world.wumpuses, pits=world.pits, pace=a.pace, gui=bool(a.vis))
    outcome = {'outcome': 'error', 'reason': 'not run'}
    t1 = time.time()
    try:
        # narrated outermost: the action's rows (and with them its drawing) open
        # before LoggedEnv's record and close after it
        wrapped = narrate.NarratedEnv(LoggedEnv(env, steps, verbose=not a.quiet and not console_ui.installed()))
        if a.controller == 'explore':
            from wumpus.explore import run_explore
            outcome = run_explore(wrapped, max_steps=a.max_steps, narrate=narrate)
        else:
            from wumpus.lw1_driver import run_lw1
            outcome = run_lw1(wrapped, max_steps=a.max_steps)
    except Exception as ex:      # recorded, never hidden
        import traceback
        traceback.print_exc()
        outcome = {'outcome': 'error', 'reason': f'{type(ex).__name__}: {ex}'}
    run_s = time.time() - t1
    if env.dead and outcome['outcome'] != 'death':
        outcome = {'outcome': 'death', 'reason': env.dead}
    visited = len({s['cell'] for s in steps if s['action'] == 'perceive' and s['result'].get('ok')})
    narrate.outcome(outcome['outcome'], outcome['reason'], cell=env.robot_cell(), visited=visited,
                    held=outcome['outcome'] == 'success')
    rec = {'instance': world.to_dict(), 'size': a.size, 'seed': a.seed, 'source': a.source,
           'controller': a.controller, 'steps': steps, 'outcome': outcome,
           'n_actions': len(steps), 'sim_steps': env.sim_steps,
           'wall': {'build_s': build_s, 'run_s': run_s,
                    'action_s': sum(s['result'].get('wall_s', 0.0) for s in steps),
                    'pace_s': narrate.pace_s(), 'paced_s': narrate.paced_s()},
           'run_dir': str(logger.run_dir)}
    if a.save_dir:
        os.makedirs(a.save_dir, exist_ok=True)
        with open(os.path.join(a.save_dir, 'episode.json'), 'w') as f:
            json.dump(rec, f, indent=1, default=float)
    print(f"wumpus: outcome {outcome['outcome']} ({outcome['reason']}), {len(steps)} actions, "
          f"{run_s:.1f} s")
    if a.vis:
        time.sleep(a.hold if a.hold is not None else 10.0)
    env.close()
    return 0 if outcome['outcome'] == 'success' else 1


if __name__ == '__main__':
    # sys.exit(main()), except that with the console installed the process ends
    # right after the flush (pybullet's GUI teardown must not print a
    # segmentation fault under the console's last line).
    console_ui.finish(main())
