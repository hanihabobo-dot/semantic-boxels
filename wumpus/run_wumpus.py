"""One Wumpus episode: python wumpus/run_wumpus.py --size 5 --seed 3 --vis 0.

Writes episode.json into --save-dir: the instance, every step (action,
observation, ground truth beside it, pose, sim steps, times), the outcome and
the wall times.  Controllers get a logging wrapper that has no truth().
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

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
    a = ap.parse_args(argv)

    if a.controller == 'lw1':
        from wumpus import lw1_driver
        if not lw1_driver.AVAILABLE:
            print('run_wumpus: --controller lw1 is not plugged in yet (path 4 fills '
                  'wumpus/lw1_driver.py); use --controller explore', file=sys.stderr)
            return 3
    if a.source == 'hidden':
        if not a.hidden_file:
            print('run_wumpus: --source hidden needs --hidden-file', file=sys.stderr)
            return 2
        blocks = parse_hidden_file(a.hidden_file)
        if a.seed >= len(blocks):
            print(f'run_wumpus: the file has {len(blocks)} blocks, no block {a.seed}', file=sys.stderr)
            return 2
        world = WumpusWorld.from_hidden(a.size, blocks[a.seed])
    else:
        world = WumpusWorld.random(a.size, a.seed)

    from wumpus.env import WumpusEnv
    t0 = time.time()
    env = WumpusEnv(world, gui=bool(a.vis), save_dir=a.save_dir)
    build_s = time.time() - t0
    steps = []
    print(f'wumpus: N={a.size} seed={a.seed} source={a.source} controller={a.controller} '
          f'wumpuses={sorted(world.wumpuses)} pits={sorted(world.pits)} gold={world.gold}')
    outcome = {'outcome': 'error', 'reason': 'not run'}
    t1 = time.time()
    try:
        wrapped = LoggedEnv(env, steps, verbose=not a.quiet)
        if a.controller == 'explore':
            from wumpus.explore import run_explore
            outcome = run_explore(wrapped, max_steps=a.max_steps)
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
    rec = {'instance': world.to_dict(), 'size': a.size, 'seed': a.seed, 'source': a.source,
           'controller': a.controller, 'steps': steps, 'outcome': outcome,
           'n_actions': len(steps), 'sim_steps': env.sim_steps,
           'wall': {'build_s': build_s, 'run_s': run_s,
                    'action_s': sum(s['result'].get('wall_s', 0.0) for s in steps)}}
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
    sys.exit(main())
