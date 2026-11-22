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
# The root first, always: wumpus/world.py shares its name with the package
# world/, and a script started as a file has its own folder ahead of a root
# that came in through PYTHONPATH.
if ROOT in sys.path:
    sys.path.remove(ROOT)
sys.path.insert(0, ROOT)

from wumpus import incidents, lw1_exec, trace as tr            # noqa: E402
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


BENCH = '/root/lw1-work/cp2fsc-and-replanner/benchmarks/lw1/wumpus'


def _blocks(text):
    out = []
    for part in text.split(','):
        a, _, b = part.partition('-')
        out += list(range(int(a), int(b or a) + 1))
    return out


def batch(size, blocks, traces, out_dir, bench=BENCH, vis=False):
    """G-W2 over LW1's own hidden blocks: for block k, the world from
    broken-hidden/h<k>.pddl and L's trace for it (traces: gw1_summary.py's
    --traces JSON, keyed 'h<k>.txt') replayed on the robot.  Writes one
    record per block and a summary; returns the summary rows."""
    from wumpus.env import WumpusEnv
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for k in blocks:
        key = f'h{k:03d}.txt'
        if not traces.get(key):        # absent, or empty: L made no move (it failed), nothing to replay
            rows.append({'block': k, 'passed': False, 'why': 'no L trace' if key not in traces else 'L trace empty'})
            print(f"G-W2 {size}x{size} h{k:03d}: FAIL, {rows[-1]['why']}", flush=True)
            continue
        with open(os.path.join(bench, f'p{size:02d}-1f', 'broken-hidden', f'h{k:03d}.pddl')) as f:
            world = WumpusWorld.from_hidden(size, f.read())
        expected = [tr.step(s['action'], s.get('obs')) for s in traces[key]]
        env = WumpusEnv(world, gui=bool(vis))
        try:
            res = replay(env, expected)
        finally:
            env.close()
        ok = passed(res)
        row = {'block': k, 'passed': ok, 'status': res['status'], 'why': res['why'],
               'actions': len(res['steps']), 'expected': len(expected),
               'observations': sum(1 for s in expected if s['obs'] is not None),
               'mismatches': res['mismatches'], 'divergence': res['divergence'], 'wall_s': res['wall_s']}
        row.update(incidents.record(env, ok))          # rule 18: a pass is the success here
        rows.append(row)
        with open(os.path.join(out_dir, f'gw2_p{size:02d}_h{k:03d}.json'), 'w') as f:
            json.dump({'instance': world.to_dict(), **row, 'steps': res['steps']}, f, indent=1, default=float)
        print(f"G-W2 {size}x{size} h{k:03d}: {'PASS' if ok else 'FAIL'}  {row['actions']}/{row['expected']} "
              f"actions, {row['observations']} observations, status {res['status']}, mismatches "
              f"{res['mismatches']}, divergence {res['divergence']}, {incidents.line(row)}", flush=True)
    with open(os.path.join(out_dir, f'gw2_p{size:02d}_summary.json'), 'w') as f:
        json.dump(rows, f, indent=1, default=float)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--batch-traces', help="G-W2 batch: gw1_summary.py's traces JSON (with --blocks, --out-dir)")
    ap.add_argument('--blocks', default='1', help="LW1's hidden blocks for the batch: '1-10' or '1,4'")
    ap.add_argument('--out-dir')
    ap.add_argument('--size', type=int, default=5)
    ap.add_argument('--seed', type=int, default=0, help='random world seed, or the block index of --hidden-file')
    ap.add_argument('--hidden', help='one LW1 hidden block')
    ap.add_argument('--hidden-file', help='a file of LW1 instances; --seed picks the block')
    ap.add_argument('--trace', help='JSON trace or a text file with one action per line')
    ap.add_argument('--rule-obs', action='store_true',
                    help="fill the trace's observations from the world's percept rule")
    ap.add_argument('--out')
    ap.add_argument('--vis', type=int, default=0)
    a = ap.parse_args(argv)

    if a.batch_traces:
        if not a.out_dir:
            ap.error('--batch-traces needs --out-dir')
        with open(a.batch_traces) as f:
            rows = batch(a.size, _blocks(a.blocks), json.load(f), a.out_dir, vis=a.vis)
        return 0 if rows and all(r['passed'] for r in rows) else 1
    if not a.trace:
        ap.error('--trace is required (or --batch-traces)')
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
    res.update(incidents.record(env, ok))              # rule 18
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, 'w') as f:
            json.dump({'instance': world.to_dict(), 'trace_file': a.trace, 'rule_obs': a.rule_obs,
                       'passed': ok, **res}, f, indent=1, default=float)
    print(f"replay: {'PASS' if ok else 'FAIL'}  {len(res['steps'])}/{len(expected)} actions, "
          f"status {res['status']}{' (' + res['why'] + ')' if res['why'] else ''}, "
          f"mismatches {res['mismatches']}, divergence {res['divergence']}, {res['wall_s']:.1f} s, "
          f"{incidents.line(res)}")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
