"""P: LW1 drives our robot (PLAN.md section 6; gate G-W3 and the P runs).

LW1 (Bonet and Geffner, AAAI 2014) runs with path 4's patch (option
lw1:external-observations, tracks/wumpus/lw1/lw1_external.patch in the
trunk): each original action it executes comes here as an EXEC line, the
robot runs it (lw1_exec.execute: drive, camera, perception, grasp) and the
answer goes back as OBS lines.  LW1's sensed literals come from that answer
and LW1 never reads a hidden state.  The problem is written from our
registry (lw1_problem.write_problem, compared with LW1's own p.pddl) with a
decoy hidden block: gold at the start cell, which none of LW1's instances
has, and no hazards.  A leak of the hidden state into LW1's choices would
show as a divergence from LW1 alone (G-W3).

    run_lw1(env, max_steps=500)   the controller (run_wumpus.py --controller lw1)
    python wumpus/lw1_driver.py --size 5 --blocks 1-10 --out-dir DIR [--expect traces.json]
                                  P runs on LW1's own hidden blocks, the ground
                                  truth beside each step, G-W3 against L's traces

The protocol (one line each; the patch's comment has it too):
    LW1 -> here:  PLAN a1;a2;...   after each planner call (print only)
                  EXEC <action>    an original action (start, move, grab)
                  BELIEF <state>   LW1's K-literals after inference
    here -> LW1:  OBS <var> <cell> <0|1> ... END, or DEAD <why>, or FAIL <why>
LW1's stdout is read too: 'calling ff (n=k, ...)' opens a thinking block on
the console (wumpus/narrate.py) and the stats line closes the record.
"""
import argparse
import json
import os
import re
import select
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from wumpus import lw1_exec, lw1_problem, trace as tr      # noqa: E402
from wumpus.world import cell_ij                            # noqa: E402

W = '/root/lw1-work'
LW1_EXT = f'{W}/lw1-ext/src/lw1'                 # tracks/wumpus/lw1/build_ext.sh
FF_DIR = f'{W}/ff/FF-v2.3'                       # tracks/wumpus/lw1/build.sh
BENCH = f'{W}/cp2fsc-and-replanner/benchmarks/lw1/wumpus'
RUNS = f'{W}/runs/p'
OPTIONS = 'lw1:strict,lw1:external-observations,solver:print:sensed-literals'
DECOY = ('(gold-at p1-1)',)
AVAILABLE = os.path.isfile(LW1_EXT) and os.access(LW1_EXT, os.X_OK)

_ANSI = re.compile(r'\x1b\[[0-9;]*m')
_CALL = re.compile(r'^calling (\S+) \(n=(\d+), acc-time=([^)]*)\)')
_STATS = re.compile(
    r'^stats:\s+(?P<as>\S+) \(action-selection\) (?P<plan>-?\d+) \(plan-size\) (?P<calls>\d+) \(as-calls\) '
    r'(?P<prep>\S+) \(preprocessing-time\) (?P<as_time>\S+) \(as-time\) (?P<as_search>\S+) \(as-search-time\) '
    r'(?P<inference>\S+) \(inference-time\) (?P<instance>\S+) \(instance-time\) (?P<total>\S+) \(total-acc-time\)')
_UNSOLVED = re.compile(r'unable to solve problem:\s*(.*)$')
_EXTERNAL = re.compile(r'^external:\s*(.*)$')
_K = re.compile(r'K_(not_)?(wumpus-at|pit-at|gold-at)_(p\d+-\d+)(?![\w-])')
STUCK = ('problem has no solution', 'reached time limit', 'reached limit of')


# ------------------------------------------------------------ pure helpers
def knowledge(belief, cells, visited=()):
    """LW1's K-literals (a BELIEF line) -> (per cell what LW1 knows, in
    wumpus/knowledge.py's form, for the GUI's painter; the counts the
    console's thinking block shows).  Per content: K <x>-at = 'yes', K not
    <x>-at = 'no', neither = 'maybe'.  `visited`: the cells the robot has
    perceived at (the driver's own record)."""
    k = {(p, v): set() for p in ('wumpus-at', 'pit-at', 'gold-at') for v in (True, False)}
    for neg, pred, cell in _K.findall(belief or ''):
        k[(pred, not neg)].add(cell)
    safe = {c for c in cells if c in k[('wumpus-at', False)] and c in k[('pit-at', False)]}

    def v(pred, c):
        return 'yes' if c in k[(pred, True)] else 'no' if c in k[(pred, False)] else 'maybe'
    state = {c: {'wumpus': v('wumpus-at', c), 'pit': v('pit-at', c), 'gold': v('gold-at', c),
                 'visited': c in visited} for c in cells}
    counts = {'safe': len(safe),
              'maybe_pit': sum(1 for c in cells if c not in k[('pit-at', False)]),
              'maybe_wumpus': sum(1 for c in cells if c not in k[('wumpus-at', False)]),
              'gold_known': bool(k[('gold-at', True)])}
    return state, counts


def our_calls(actions):
    """LW1's actions -> the env calls the console numbers: start p = perceive
    at p; move p q = move to q, perceive at q; grab p = grab."""
    out = []
    for a in actions:
        if a[0] == 'start':
            out.append(('perceive', a[1]))
        elif a[0] == 'move':
            out += [('move', a[2]), ('perceive', a[2])]
        elif a[0] == 'grab':
            out.append(('grab', a[1]))
    return out


def parse_stdout(lines):
    """LW1's stdout -> {'stats': dict or None, 'unsolved': str or None,
    'external': str or None, 'calls': [k, ...]}."""
    out = {'stats': None, 'unsolved': None, 'external': None, 'calls': []}
    for raw in lines:
        line = _ANSI.sub('', raw).strip()
        m = _STATS.match(line)
        if m:
            out['stats'] = {k: (int(v) if k in ('plan', 'calls') else v if k == 'as' else float(v))
                            for k, v in m.groupdict().items()}
            continue
        m = _UNSOLVED.search(line)
        if m:
            out['unsolved'] = m.group(1).strip()
            continue
        m = _EXTERNAL.match(line)
        if m:
            out['external'] = m.group(1).strip()
            continue
        m = _CALL.match(line)
        if m:
            out['calls'].append(int(m.group(2)))
    return out


def classify(steps, exit_code, parsed):
    """The episode's outcome from what the robot did and how LW1 ended."""
    for s in steps:
        if s['status'] == 'dead':
            return 'death', str(s['dead'])
    for s in steps:
        if s['status'] != 'ok':
            return 'error', s['why']
    st = parsed['stats']
    if exit_code == 0 and st is not None and st['plan'] >= 0 and parsed['unsolved'] is None:
        if steps and steps[-1]['action'][0] == 'grab' and steps[-1]['held']:
            return 'success', 'the gold is held'
        return 'error', 'LW1 reached its goal but the last action is no verified grab'
    if parsed['unsolved'] and any(s in parsed['unsolved'] for s in STUCK):
        return 'stuck', parsed['unsolved']
    if parsed['external']:
        return 'error', parsed['external']
    if parsed['unsolved']:
        return 'error', parsed['unsolved']
    return 'error', f'LW1 exited with code {exit_code}'


# ------------------------------------------------------------ the controller
class _Episode:
    def __init__(self, env, narrate, max_steps, log):
        self.env, self.narrate, self.max_steps, self.log = env, narrate, max_steps, log
        self.n = int(env.world_size)
        self.cells = sorted(env.cells(), key=cell_ij)
        self.steps, self.trace, self.plans, self.out_lines, self.other = [], [], [], [], []
        self.beliefs, self.counts, self.belief_text = 0, None, None
        self.visited = set()
        self.think_t, self.call_no = None, 0
        self.stop = None

    # LW1's stdout
    def on_stdout(self, line):
        self.out_lines.append(line)
        m = _CALL.match(_ANSI.sub('', line).strip())
        if not m:
            return
        self.call_no, self.think_t = int(m.group(2)), time.time()
        c = self.counts or {'safe': 1, 'maybe_pit': self.n * self.n - 1,
                            'maybe_wumpus': self.n * self.n - 1, 'gold_known': False}
        self.narrate.thinking(plan_no=self.call_no, visited=len(self.visited), safe=c['safe'],
                              maybe_pit=c['maybe_pit'], maybe_wumpus=c['maybe_wumpus'],
                              gold_known=c['gold_known'], cells=self.n * self.n)

    # the pipe from LW1; returns the answer lines for an EXEC, else None
    def on_pipe(self, line):
        tag, _, text = line.partition(' ')
        if tag == 'PLAN':
            acts = []
            for a in filter(None, (x.strip() for x in text.split(';'))):
                try:
                    acts.append(lw1_exec.parse_action(a))
                except ValueError:
                    acts.append(('?', a))
            dt = time.time() - self.think_t if self.think_t is not None else 0.0
            self.think_t = None
            self.plans.append({'call': self.call_no, 'actions': [list(a) for a in acts], 'time_s': dt,
                               'at_step': len(self.steps)})
            self.narrate.plan(our_calls(acts), plan_time_s=dt, plan_no=self.call_no or None)
            return None
        if tag == 'BELIEF':
            self.beliefs += 1
            self.belief_text = text
            state, self.counts = knowledge(text, self.cells, self.visited)
            self.env.show_knowledge(state)
            return None
        if tag != 'EXEC':
            self.other.append(line)
            return None
        if len(self.steps) >= self.max_steps:
            self.stop = ('step_limit', f'{self.max_steps} actions')
            return ['FAIL step limit']
        try:
            action = lw1_exec.parse_action(text)
        except ValueError as ex:
            self.stop = ('error', str(ex))
            return [f'FAIL {ex}']
        t = time.time()
        r = lw1_exec.execute(self.env, action)
        rec = {'k': len(self.steps), 'action': list(r['action']), 'status': r['status'],
               'why': r['why'], 'cell': r['cell'], 'obs': r['obs'], 'dead': r['dead'],
               'held': r['held'], 'wall_s': time.time() - t,
               'env_s': sum(float(x.get('wall_s', 0.0) or 0.0) for x in r['raw'])}
        self.steps.append(rec)
        self.trace.append(tr.step(r['action'], r['obs']))
        if r['obs'] is not None:
            self.visited.add(r['cell'])
        if r['status'] != 'ok':
            self.stop = ('death' if r['status'] == 'dead' else 'error', r['dead'] or r['why'])
        return lw1_exec.protocol_lines(r)


def run_lw1(env, max_steps=500, log=print, lw1=LW1_EXT, ff=FF_DIR, bench=BENCH, domain='d2',
            max_time=10800, runs_dir=RUNS, options=OPTIONS, decoy=DECOY, narrate=None):
    """The LW1 controller.  env: the WumpusEnv interface without truth()
    (world_size, cells, registry, robot_cell, move, perceive, grab,
    show_knowledge).  Returns {'outcome': 'success' | 'death' | 'stuck' |
    'step_limit' | 'error', 'reason', 'trace' (path 4's form), 'steps',
    'plans', 'lw1': its exit code, stats, run folder, ...}."""
    if narrate is None:
        from wumpus import narrate             # every call a no-op without a RunLogger
    ep = _Episode(env, narrate, max_steps, log)
    n = ep.n
    start = env.robot_cell()
    run_dir = os.path.join(runs_dir, f'{n:02d}x{n:02d}_{time.strftime("%Y%m%d_%H%M%S")}_{os.getpid()}')
    os.makedirs(os.path.join(run_dir, 'tmp'))
    dom = os.path.join(bench, f'p{n:02d}-1f', f'{domain}.pddl')
    prob, hid = os.path.join(run_dir, 'problem.pddl'), os.path.join(run_dir, 'hidden.pddl')
    text = lw1_problem.write_problem(env.registry, start)
    with open(prob, 'w') as f:
        f.write(text)
    with open(hid, 'w') as f:
        f.write('(define (problem x)\n    (:hidden ' + ' '.join(decoy) + ')\n)\n')
    theirs = os.path.join(bench, f'p{n:02d}-1f', 'p.pddl')
    problem_diff = None
    if os.path.exists(theirs):
        with open(theirs) as f:
            problem_diff = lw1_problem.compare(text, f.read())
    exec_fifo, obs_fifo = os.path.join(run_dir, 'exec.fifo'), os.path.join(run_dir, 'obs.fifo')
    os.mkfifo(exec_fifo)
    os.mkfifo(obs_fifo)
    # read-write ends: neither open blocks, and a read never sees EOF while LW1 starts
    exec_fd = os.open(exec_fifo, os.O_RDWR | os.O_NONBLOCK)
    obs_fd = os.open(obs_fifo, os.O_RDWR)
    cmd = [lw1, '--max-time', str(int(max_time)), '--planner-path', ff,
           '--tmpfile-path', os.path.join(run_dir, 'tmp'), f'--options={options}', dom, prob, hid]
    penv = dict(os.environ, LW1_EXEC_FIFO=exec_fifo, LW1_OBS_FIFO=obs_fifo)
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, cwd=run_dir, env=penv)
    out_fd = proc.stdout.fileno()
    os.set_blocking(out_fd, False)
    bufs = {exec_fd: b'', out_fd: b''}
    out_open, killed = True, None
    try:
        with open(os.path.join(run_dir, 'lw1_out.txt'), 'w') as out_file:
            while True:
                ready, _, _ = select.select([exec_fd] + ([out_fd] if out_open else []), [], [], 0.5)
                # stdout first: its 'calling ff' line opens the thinking block the PLAN line closes
                for fd in sorted(ready, key=lambda x: x != out_fd):
                    try:
                        data = os.read(fd, 1 << 16)
                    except BlockingIOError:
                        continue
                    if not data:
                        if fd == out_fd:
                            out_open = False
                        continue
                    bufs[fd] += data
                    *lines, bufs[fd] = bufs[fd].split(b'\n')
                    for raw in lines:
                        line = raw.decode('utf-8', 'replace')
                        if fd == out_fd:
                            out_file.write(line + '\n')
                            ep.on_stdout(line)
                            continue
                        answer = ep.on_pipe(line)
                        if answer is not None:
                            os.write(obs_fd, ('\n'.join(answer) + '\n').encode())
                if proc.poll() is not None and not out_open:
                    break
                if killed is None and time.time() - t0 > max_time + 300:
                    killed = f'wall time over {max_time + 300} s'
                    proc.kill()                   # our own child
            for line in filter(None, bufs[exec_fd].decode('utf-8', 'replace').split('\n')):
                ep.on_pipe(line) if not line.startswith('EXEC') else ep.other.append(line)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        os.close(exec_fd)
        os.close(obs_fd)
        for p in (exec_fifo, obs_fifo):
            if os.path.exists(p):
                os.remove(p)
        tmp = os.path.join(run_dir, 'tmp')
        if os.path.isdir(tmp) and not os.listdir(tmp):
            os.rmdir(tmp)
    wall = time.time() - t0
    parsed = parse_stdout(ep.out_lines)
    outcome, reason = classify(ep.steps, proc.returncode, parsed)
    if killed:
        outcome, reason = 'stuck', killed
    elif ep.stop and ep.stop[0] == 'step_limit':
        outcome, reason = ep.stop
    log(f'lw1: {outcome} ({reason}), {len(ep.steps)} actions, {len(ep.plans)} plans, '
        f'exit {proc.returncode}, {wall:.1f} s, {run_dir}')
    return {'outcome': outcome, 'reason': reason, 'trace': ep.trace, 'steps': ep.steps,
            'plans': ep.plans,
            'lw1': {'exit': proc.returncode, 'stats': parsed['stats'], 'unsolved': parsed['unsolved'],
                    'external': parsed['external'], 'calls': parsed['calls'], 'beliefs': ep.beliefs,
                    'last_counts': ep.counts, 'other_lines': ep.other, 'run_dir': run_dir,
                    'cmd': cmd, 'problem_diff': problem_diff, 'wall_s': wall}}


# ------------------------------------------------------------ P runs (CLI)
class _Recorded:
    """The env as LW1's driver sees it (no truth()), every call recorded."""

    def __init__(self, env):
        self._env, self.calls = env, []

    def cells(self): return self._env.cells()
    def adjacent(self): return self._env.adjacent()
    def robot_cell(self): return self._env.robot_cell()
    @property
    def registry(self): return self._env.registry
    @property
    def world_size(self): return self._env.world.n
    def show_knowledge(self, k): return self._env.show_knowledge(k)

    def _call(self, name, fn, *args):
        r = fn(*args)
        self.calls.append({'call': name, 'args': list(args), 'cell': self._env.robot_cell(),
                           'result': {k: v for k, v in r.items() if k != 'image'}})
        return r

    def move(self, cell): return self._call('move', self._env.move, cell)
    def perceive(self): return self._call('perceive', self._env.perceive)
    def grab(self): return self._call('grab', self._env.grab)


def _blocks(text):
    out = []
    for part in text.split(','):
        a, _, b = part.partition('-')
        out += list(range(int(a), int(b or a) + 1))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--size', type=int, default=5)
    ap.add_argument('--blocks', default='1', help="LW1's hidden blocks broken-hidden/h<k>.pddl: '1-10' or '1,4'")
    ap.add_argument('--domain', default='d2')
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--expect', help="gw1_summary.py's traces JSON for this size and domain (G-W3)")
    ap.add_argument('--max-steps', type=int, default=500)
    ap.add_argument('--max-time', type=int, default=10800)
    ap.add_argument('--vis', type=int, default=0)
    a = ap.parse_args(argv)
    from wumpus.env import WumpusEnv
    from wumpus.world import WumpusWorld
    expect = {}
    if a.expect:
        with open(a.expect) as f:
            expect = json.load(f)
    os.makedirs(a.out_dir, exist_ok=True)
    rows = []
    for k in _blocks(a.blocks):
        hfile = os.path.join(BENCH, f'p{a.size:02d}-1f', 'broken-hidden', f'h{k:03d}.pddl')
        with open(hfile) as f:
            world = WumpusWorld.from_hidden(a.size, f.read())
        env = WumpusEnv(world, gui=bool(a.vis))
        rec = _Recorded(env)
        t0 = time.time()
        try:
            res = run_lw1(rec, max_steps=a.max_steps, domain=a.domain, max_time=a.max_time)
        finally:
            env.close()
        # the ground truth beside each observation (the driver never had it)
        wrong = [s['k'] for s in res['steps'] if s['obs'] is not None
                 and s['obs'] != tr.percept_obs(world, s['cell'])]
        n_obs = sum(1 for s in res['steps'] if s['obs'] is not None)
        div = None
        lt = expect.get(f'h{k:03d}.txt')
        if lt is not None:
            div = tr.first_divergence([tr.step(s['action'], s.get('obs')) for s in lt], res['trace'])
        row = {'size': a.size, 'block': k, 'domain': a.domain, 'instance': world.to_dict(),
               'outcome': res['outcome'], 'reason': res['reason'], 'actions': len(res['steps']),
               'plans': len(res['plans']), 'percepts': n_obs, 'percepts_wrong': wrong,
               'g_w3': None if lt is None else {'divergence': div, 'passed': div is None},
               'lw1': res['lw1'], 'wall_s': time.time() - t0,
               'robot_s': sum(s['env_s'] for s in res['steps'])}
        with open(os.path.join(a.out_dir, f'p{a.size:02d}_h{k:03d}.json'), 'w') as f:
            json.dump({**row, 'trace': res['trace'], 'steps': res['steps'], 'plans_detail': res['plans'],
                       'env_calls': rec.calls}, f, indent=1, default=float)
        rows.append(row)
        st = res['lw1']['stats'] or {}
        print(f"P {a.size}x{a.size} h{k:03d}: {res['outcome']} ({res['reason']}), "
              f"{len(res['steps'])} actions, LW1 plan-size {st.get('plan')}, calls {st.get('calls')}, "
              f"percepts wrong {len(wrong)}/{n_obs}, G-W3 "
              f"{'n/a' if lt is None else ('PASS' if div is None else 'FAIL ' + json.dumps(div))}, "
              f"{row['wall_s']:.1f} s", flush=True)
    with open(os.path.join(a.out_dir, f'p{a.size:02d}_summary.json'), 'w') as f:
        json.dump(rows, f, indent=1, default=float)
    return 0 if all(r['outcome'] == 'success' for r in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
