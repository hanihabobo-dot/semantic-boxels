"""G-W2: an LW1 execution replayed on the robot (PLAN.md section 7).

The trace holds LW1's actions with LW1's sensed literals (or the actions
alone; then the world's percept rule, which is what LW1's simulator computes
from its hidden state, stands in for them: ``trace.with_rule_obs``).  Each
action runs on the robot through ``lw1_exec.execute``; our observation is
compared with the trace's at every step.  The gate holds when no step
differs and every action succeeded.

    python wumpus/replay.py --size 5 --hidden "(:hidden (wumpus-at p3-3) ...)" \\
        --trace lw1_trace.json --out replay.json [--rule-obs] [--vis 1]
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from wumpus import lw1_exec, trace as tr                       # noqa: E402
from wumpus.world import WumpusWorld, parse_hidden_file         # noqa: E402


def replay(env, expected):
    """Execute the trace's actions on the robot.  Returns {'status': 'ok' |
    'dead' | 'fail', 'why', 'steps': one record per executed action,
    'mismatches': the steps whose observation differs from the trace's,
    'divergence': trace.first_divergence(expected, robot trace), 'robot_trace',
    'wall_s'}.  It stops at the first death or failure; a differing
    observation does not stop it (every difference is listed)."""
    t0 = time.time()
    robot, steps, mismatches = [], [], []
    status, why = 'ok', ''
    for k, st in enumerate(expected):
        r = lw1_exec.execute(env, st['action'])
        robot.append(tr.step(r['action'], r['obs']))
        exp = st.get('obs')
        rec = {'k': k, 'action': list(r['action']), 'status': r['status'], 'why': r['why'],
               'cell': r['cell'], 'obs': r['obs'], 'expected_obs': exp,
               'dead': r['dead'], 'held': r['held'],
               'wall_s': sum(x.get('wall_s', 0.0) for x in r['raw'])}
        steps.append(rec)
        if exp is not None and r['obs'] is not None and any(
                bool(exp[v]) != bool(r['obs'][v]) for v in tr.OBS_VARS):
            mismatches.append(k)
        if r['status'] != 'ok':
            status, why = r['status'], r['why']
            break
    return {'status': status, 'why': why, 'steps': steps, 'mismatches': mismatches,
            'divergence': tr.first_divergence(expected, robot), 'robot_trace': robot,
            'wall_s': time.time() - t0}


def passed(result):
    return result['status'] == 'ok' and result['divergence'] is None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--size', type=int, default=5)
    ap.add_argument('--seed', type=int, default=0, help='random world seed, or the block index of --hidden-file')
    ap.add_argument('--hidden', help='one LW1 hidden block')
    ap.add_argument('--hidden-file', help='a file of LW1 instances; --seed picks the block')
    ap.add_argument('--trace', required=True, help='JSON trace or a text file with one action per line')
    ap.add_argument('--rule-obs', action='store_true',
                    help="fill the trace's observations from the world's percept rule")
    ap.add_argument('--out')
    ap.add_argument('--vis', type=int, default=0)
    a = ap.parse_args(argv)

    if a.hidden:
        world = WumpusWorld.from_hidden(a.size, a.hidden)
    elif a.hidden_file:
        world = WumpusWorld.from_hidden(a.size, parse_hidden_file(a.hidden_file)[a.seed])
    else:
        world = WumpusWorld.random(a.size, a.seed)
    expected = tr.load(a.trace)
    if a.rule_obs:
        expected = tr.with_rule_obs(world, [s['action'] for s in expected])

    from wumpus.env import WumpusEnv
    env = WumpusEnv(world, gui=bool(a.vis))
    try:
        res = replay(env, expected)
    finally:
        env.close()
    ok = passed(res)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, 'w') as f:
            json.dump({'instance': world.to_dict(), 'trace_file': a.trace, 'rule_obs': a.rule_obs,
                       'passed': ok, **res}, f, indent=1, default=float)
    print(f"replay: {'PASS' if ok else 'FAIL'}  {len(res['steps'])}/{len(expected)} actions, "
          f"status {res['status']}{' (' + res['why'] + ')' if res['why'] else ''}, "
          f"mismatches {res['mismatches']}, divergence {res['divergence']}, {res['wall_s']:.1f} s")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
