"""console_replay.py: a recorded run played through the real Console (Phase 0, pin 27).

    python tools/readable/console_replay.py --run-dir RUN_DIR --out OUT [--env plain,ascii]
    python tools/readable/console_replay.py --made NAME --out OUT [--env ...]
    python tools/readable/console_replay.py --list-made
    python tools/readable/console_replay.py --live-check RUN_DIR --out OUT

R's pin 27 (review/map/08_randomness_tests_pins.md row 27): a recorded run's
``ledger.jsonl`` plus the stdout lines of its ``run_<stamp>.log``, fed in
order into a Console whose terminal is a pipe (static layout), with
``on_ledger_event`` and ``narration``; the ``[console]`` lines the Console
writes to its debug file are the output.  PLAN 5.2 row 27 adds the four
environment sets and the made tapes; R's plan review S-d (PLAN_REVIEW.md 7)
adds one made tape with a sample line per regex rule, one row per ledger
kind and per end status.

How a run becomes a tape (``build_run_tape``, no pipeline import):

  * the run log is split into stdout lines (what run_logger's tee handed to
    the Console's narration hook) and logging lines (``HH:MM:SS [LEVEL]
    name: message``, the file handler's format); a last line without its
    newline is dropped, as the tee's line buffer never hands it over;
  * ledger rows are placed between the lines by anchors read from
    test_full_pipeline.py (the order of its prints and ledger writes):
      - a mission ``plan`` row before the first of: its ``[eye #N] plan#k
        planned`` line, ``no mission plan with X held``, ``[timing]
        planner.plan() #k:``, ``ERROR: No plan found!`` (main 1872-1946);
      - a disposal ``plan`` row before the first of: ``note: the disposal
        no-plan``, ``ERROR: no disposal plan``, ``[timing] ... #k:``
        (main 1925-1946);
      - a ``step`` row before its ``Executing: <action>`` line (main 2025,
        2028);
      - a ``step_end`` row before the first step boundary after its step's
        ``Executing`` line: the next ``Executing:``, ``=== PLAN #``,
        ``giveup parole``, ``[M8] observe strikes of``, ``PHYSICAL_FAILURE
        (goal)``, ``[eye #N] final``, the report's ``====`` rule
        (main 1722-1754, 3033-3097);
      - an ``at_home_test`` row before its ``[D7] at-home test`` line
        (main 2172-2176);
      - every other row right before the next anchored row, in ledger
        order (the Console reads only sense_result, observe_result,
        gate_violation and belief among them, and the first two only at
        their step's end); rows after the last anchor before the report's
        opening rule; ``ledger_close`` after the summary (RunLogger.close);
  * ``header`` after the ``model tweaks:`` line (main 805-820), its
    arguments rebuilt from the run configuration block, that line, the
    first plan row's goal and, for a bridge run, bridge_episode.json;
  * ``summary`` after the report's closing rule (run_logger 673-679), its
    arguments from timing_summary.json;
  * a bridge run (bridge_episode.json two levels up) also gets the driver's
    calls outside the run log (run_bridge_on_finddice.py 255-358): the
    start-up note, the G19 note, set_context, and the gate table and the
    outcome line through ``console_ui.terminal()``, with
    tools/bridge_gates.py's SCENE_MAP and Report.show.

How a tape is played (``play``): one child interpreter per environment set,
its stdout a pipe (the terminal: static layout), its cwd and HOME a fresh
folder, PYTHONHASHSEED=0; the child freezes ``time.perf_counter`` and
``time.strftime`` (the banner's stamp, ``ready``, ``in all``) before it
imports console_ui, installs the Console as install_early does, plays the
calls (narration lines are written to stdout first, as the tee does) and
ends with ``console_ui.finish`` or an uncaught exception, as an entry point
does.  Nothing in the pipeline is patched; the times inside the output come
from the ledger rows (step durations, plan times) and are kept.

Outputs per environment set: ``console.txt`` (the ``[console]`` lines of the
debug file), ``terminal.txt`` (what the pipe got), ``debug.txt`` (the whole
debug file), ``run.json`` (exit code, how far the tape played, stderr).
Paths masked: the replay folder ``<RUN>``, the repo ``<REPO>``, the source
run ``<SRC>`` and its save folder ``<SAVE>``, the early debug file's random
name, the line numbers of this file in a traceback.

No stored golden output (R's condition): goldens are made on tag
refactor-checkpoint-2 by ``pin_outputs.py --group console``.  Runs in WSL
with /root/armO-venvA/bin/python under ``flock /root/sb_pipeline.lock``
(console_ui is a pipeline module; no pybullet, no physics client).
"""
import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve()
CHILD_TIMEOUT_S = 120
FROZEN_PERF = 1000.0
FROZEN_STAMP = '2000-01-01 00:00'
BANNER = '=' * 60

# The environment sets (PLAN 5.2 row 27): static layout, colour off and on,
# unicode and ASCII glyphs.  R's pin 27 names the colourless static layout;
# the two FORCE_COLOR sets are PLAN's addition.
ENV_SETS = {
    'plain': {'NO_COLOR': '1'},
    'ascii': {'NO_COLOR': '1', 'SB_CONSOLE_ASCII': '1'},
    'color': {'FORCE_COLOR': '1'},
    'color_ascii': {'FORCE_COLOR': '1', 'SB_CONSOLE_ASCII': '1'},
}
DEFAULT_ENVS = tuple(ENV_SETS)
CALL_KINDS = ('attach', 'line', 'stdout', 'log', 'ledger', 'header', 'summary', 'startup',
              'set_context', 'say', 'warn', 'stderr', 'terminal', 'detach', 'finish', 'raise')
RAISABLE = ('SystemExit', 'RuntimeError', 'KeyboardInterrupt')


# ---------------------------------------------------------------------------
# Reading a run
# ---------------------------------------------------------------------------

LOG_LINE = re.compile(r'^(\d\d:\d\d:\d\d) \[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*\] (\S+?): (.*)$')


def read_ledger(path):
    rows = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def read_run_log(path):
    """(events, partial): one event per complete line of the run log, a
    stdout line {'m': 'line'} or a logging line {'m': 'log'}; partial is a
    last line without its newline (never handed to the narration)."""
    text = Path(path).read_bytes().decode('utf-8', errors='replace')
    parts = text.split('\n')
    partial = parts.pop()
    events = []
    for line in parts:
        m = LOG_LINE.match(line)
        if m:
            events.append({'m': 'log', 'a': [m.group(2), m.group(3), m.group(4)]})
        else:
            events.append({'m': 'line', 'a': [line]})
    return events, partial


def find_run_log(run_dir):
    run_dir = Path(run_dir)
    own = run_dir / f'{run_dir.name}.log'
    if own.exists():
        return own
    logs = sorted(run_dir.glob('run_*.log'))
    if not logs:
        raise FileNotFoundError(f'no run_*.log in {run_dir}')
    return logs[0]


def run_config_block(lines):
    """The '--- Run configuration ---' block of main (key = value lines)."""
    rc, inside = {}, False
    for t in lines:
        s = t.strip()
        if s == '--- Run configuration ---':
            inside = True
            continue
        if inside:
            if not s:
                break
            m = re.match(r'^(\w+)\s+= (.*)$', s)
            if m:
                rc[m.group(1)] = m.group(2)
    return rc


# ---------------------------------------------------------------------------
# Anchors (test_full_pipeline.py at refactor-checkpoint-1; see the docstring)
# ---------------------------------------------------------------------------

DISPOSAL_START = re.compile(r'^no mission plan with \S+ held')
DISPOSAL_NOTE = re.compile(r'^note: the disposal no-plan')
DISPOSAL_ERR = re.compile(r'^ERROR: no disposal plan for ')
NO_PLAN = re.compile(r'^ERROR: No plan found!')
AT_HOME = re.compile(r'^\[D7\] at-home test (passed|FAILED):')
STEP_BOUNDARY = re.compile(
    r'^(Executing: |=== PLAN #\d+ ===$|giveup parole |\[M8\] observe strikes of '
    r'|PHYSICAL_FAILURE \(goal\)|\[eye #\d+\] final |={60}$)')


def _eye_planned(k):
    return re.compile(rf'^\[eye #\d+\] plan#{k} planned')


def _timing(k):
    return re.compile(rf'^\[timing\] planner\.plan\(\) #{k}:')


def merge(events, rows, header=None, summary=None, post_rows_calls=()):
    """Place the ledger rows, the header and the summary among the log's
    events.  Returns (calls, report)."""
    n = len(events)

    def text(i):
        e = events[i]
        return e['a'][0].strip() if e['m'] == 'line' else None

    def find(start, pred):
        for i in range(max(0, start), n):
            t = text(i)
            if t is not None and pred(t):
                return i
        return None

    def back_over_blank(i, floor):
        while i - 1 >= floor and text(i - 1) == '':
            i -= 1
        return i

    slots = defaultdict(list)
    report = {'anchored': Counter(), 'missed': [], 'unanchored': Counter(), 'notes': []}

    # The report block (run_logger.report_run_outcome): its opening rule,
    # the SUCCESS!/FAILED line, the closing rule; summary() after that.
    res_i = None
    for i in range(1, n):
        t = text(i)
        if t is not None and (t == 'SUCCESS!' or t.startswith('FAILED')) and text(i - 1) == BANNER:
            res_i = i
    report_start = summary_slot = None
    if res_i is not None:
        report_start = back_over_blank(res_i - 1, 0)
        end_i = find(res_i + 1, lambda t: t == BANNER)
        summary_slot = (end_i + 1) if end_i is not None else n

    head_slot = None
    if header is not None:
        i = find(0, lambda t: t.startswith('model tweaks: '))
        head_slot = i + 1 if i is not None else 0
        slots[head_slot].append({'m': 'header', 'kw': header})

    cursor, exec_idx, pending, closing = 0, -1, [], []
    for row in rows:
        kind = row.get('kind')
        if closing or kind == 'ledger_close':
            closing.append(row)
            continue
        j = None
        if kind == 'plan':
            k = row.get('plan_id')
            if row.get('call') == 'disposal':
                pats = (DISPOSAL_NOTE, DISPOSAL_ERR, _timing(k))
                start = cursor
            else:
                pats = (_eye_planned(k), DISPOSAL_START, _timing(k), NO_PLAN)
                s = find(cursor, lambda t, k=k: t == f'=== PLAN #{k} ===')
                start = s if s is not None else cursor
            j = find(start, lambda t: any(p.match(t) for p in pats))
        elif kind == 'step':
            want = f"Executing: {row.get('action')}"
            i = find(cursor, lambda t: t == want)
            if i is not None:
                exec_idx = i
                j = back_over_blank(i, cursor)
        elif kind == 'step_end':
            start = max(cursor, exec_idx + 1)
            i = find(start, lambda t: bool(STEP_BOUNDARY.match(t)))
            j = back_over_blank(i if i is not None else n, start)
        elif kind == 'at_home_test':
            j = find(cursor, lambda t: bool(AT_HOME.match(t)))
        else:
            pending.append(row)
            report['unanchored'][kind] += 1
            continue
        if j is None:
            report['missed'].append({'kind': kind, 'plan': row.get('plan', row.get('plan_id')),
                                     'step': row.get('step'), 'placed_at_event': cursor})
            j = cursor
        else:
            report['anchored'][kind] += 1
        for r in pending:
            slots[j].append({'m': 'ledger', 'a': [r.get('kind'), r]})
        pending = []
        slots[j].append({'m': 'ledger', 'a': [kind, row]})
        cursor = j
    # Rows after the last anchored row: before the report block (or at the
    # end of a run without one); ledger_close after the summary.
    tail = max(cursor, report_start) if report_start is not None else n
    for r in pending:
        slots[tail].append({'m': 'ledger', 'a': [r.get('kind'), r]})
    end = max(tail, summary_slot) if summary_slot is not None else n
    if summary is not None and summary_slot is not None:
        slots[end].append({'m': 'summary', 'kw': summary})
    elif summary is not None:
        report['notes'].append('summary arguments known but no report block in the log: summary not called')
    for r in closing:
        slots[end].append({'m': 'ledger', 'a': [r.get('kind'), r]})
    calls = []
    for i in range(n + 1):
        calls.extend(slots.get(i, ()))
        if i < n:
            calls.append(events[i])
    calls.extend(post_rows_calls)
    report['anchored'] = dict(report['anchored'])
    report['unanchored'] = dict(report['unanchored'])
    report['report_block'] = res_i is not None
    return calls, report


# ---------------------------------------------------------------------------
# A run directory as a tape
# ---------------------------------------------------------------------------

def _bridge_gates():
    """tools/bridge_gates.py (stdlib only), loaded as the driver loads it;
    BRIDGE_SCENE_MANIFEST is left out while it is read (it merges another
    scene map into SCENE_MAP at import)."""
    import importlib.util
    mod = sys.modules.get('_readable_bridge_gates')
    if mod is not None:
        return mod
    saved = os.environ.pop('BRIDGE_SCENE_MANIFEST', None)
    try:
        spec = importlib.util.spec_from_file_location('_readable_bridge_gates',
                                                      str(REPO / 'tools' / 'bridge_gates.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if saved is not None:
            os.environ['BRIDGE_SCENE_MANIFEST'] = saved
    sys.modules['_readable_bridge_gates'] = mod
    return mod


def _switch_text(lines):
    import ast
    for t in lines:
        s = t.strip()
        if s.startswith('model tweaks: '):
            body = s[len('model tweaks: '):].split('; domain', 1)[0]
            try:
                d = ast.literal_eval(body)
            except Exception:
                return None
            return ', '.join(f"{k} {'on' if v else 'off'}" for k, v in d.items())
    return None


def _goal_parts(goal):
    """(target, at_home) from a plan row's goal list."""
    target, home = None, False
    clauses = goal[1:] if isinstance(goal, list) and goal and goal[0] == 'and' else [goal]
    for c in clauses:
        if isinstance(c, list) and len(c) >= 2:
            if c[0] == 'holding':
                target = c[1]
            if c[0] == 'at_config' and c[1] == 'q_home':
                home = True
    return target, home


def derive_header(lines, rows, rc, episode):
    """main's console_ui.header() arguments (test_full_pipeline.py 808-820)
    from the run's own files; the sources are in the returned 'from'."""
    src = {}
    first = next((r for r in rows if r.get('kind') == 'plan'), None)
    goal = first.get('goal') if first else None
    target, home = _goal_parts(goal) if goal is not None else (None, False)
    if rc:
        # The boxels entry (test_full_pipeline.py __main__) calls main()
        # without target_name: Phase 4 picks the target after the header.
        target = None
        src['target'] = 'none: the boxels entry passes no target_name'
    else:
        src['target'] = "the first plan row's holding clause (the bridge passes target_name)"
    goal_kind = rc.get('goal')
    src['goal_kind'] = 'run configuration' if goal_kind else 'first plan row'
    if not goal_kind:
        goal_kind = 'holding' if target else (goal[0] if isinstance(goal, list) and goal else None)
    goal_text = None
    if goal_kind:
        goal_text = goal_kind + (f' {target}' if goal_kind == 'holding' and target else '') + (
            ' at home' if home else '')
    scene = None
    if rc:
        scene = (f"{rc.get('scene')} seed {rc.get('seed')}, {rc.get('n_occluders')} occluders, "
                 f"{rc.get('n_targets')} targets, {rc.get('n_hidden')} hidden")
    sw = (episode or {}).get('switches', {})
    st = _switch_text(lines)
    squeeze = rc.get('grip_squeeze_mm') or sw.get('grip_squeeze_mm')
    planner = rc.get('planner')
    src['planner'] = 'run configuration' if planner else "parse_pipeline_args' default (not in the run's files)"
    planner = planner or 'ff-astar2'
    slip = rc.get('slip_fixes') if 'slip_fixes' in rc else sw.get('slip_fixes')
    if slip is not None:
        names = sorted(x for x in str(slip).split(',') if x and x != 'none')
        slip = ','.join(names) if names else 'none'
    switches = None
    if st is not None:
        switches = (f"{st}, grip squeeze {float(squeeze):g} mm, planner {planner}"
                    if squeeze is not None else f"{st}, planner {planner}")
        if slip:
            switches += f', slip fixes {slip}'
    return {'scene': scene, 'goal': goal_text, 'switches': switches}, src


def derive_summary(run_dir, lines, rows):
    ts = Path(run_dir) / 'timing_summary.json'
    if ts.exists():
        d = json.loads(ts.read_text(encoding='utf-8'))
        return {'success': bool(d.get('success')), 'exit_reason': d.get('exit_reason'),
                'plan_count': d.get('plan_count', 0),
                'plan_times': list(d.get('per_call_planning_time_s') or []),
                'total_plan_time': d.get('total_planning_time_s', 0.0),
                'log_path': '<LOG>'}, 'timing_summary.json'
    plans = [r for r in rows if r.get('kind') == 'plan']
    times = [float(r.get('plan_time_s') or 0.0) for r in plans]
    ok = any(t.strip() == 'SUCCESS!' for t in lines)
    return {'success': ok, 'exit_reason': None,
            'plan_count': len([r for r in plans if r.get('call') != 'disposal']),
            'plan_times': times, 'total_plan_time': sum(times), 'log_path': '<LOG>'}, \
        'the ledger and the log (no timing_summary.json)'


def _bridge_calls(episode, save_dir):
    """The driver's console calls outside the run log (pre, post)."""
    pre, post, notes = [], [], []
    try:
        gates = _bridge_gates()
    except Exception as e:                      # the record says so
        notes.append(f'tools/bridge_gates.py not loaded ({type(e).__name__}: {e}): '
                     f'no start-up note, G19 note or gate table')
        return pre, post, notes, None
    seed = episode.get('seed')
    name_seen = episode.get('scene_file')
    pinned = gates.SCENE_MAP.get(seed)
    mismatch = name_seen is None or pinned is None or pinned not in name_seen
    if name_seen is not None:
        pre.append({'m': 'startup', 'a': [f'Loading scene from {name_seen}' + (
            '' if mismatch else " (the campaign's pinned scene for this seed)")]})
    if mismatch:
        note = (f"G19: seed {seed} loaded {name_seen}, the campaign "
                f"pins {pinned}: a watching or diagnostic run, never scored "
                f"(the ledger's G19 gate records the mismatch)")
        pre.append({'m': 'stdout', 'a': [note]})
        pre.append({'m': 'warn', 'a': [note]})
    pre.append({'m': 'set_context', 'kw': {'scene': f'find_dice seed {seed}'}})
    rows = episode.get('ledger_gates')
    outcome = (episode.get('outcome') or {})
    rewards = episode.get('rewards') or []
    if rows is not None:
        rep = gates.Report()
        for r in rows:
            rep.add(*r)
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rep.show()
        lines = buf.getvalue().split('\n')
        if lines and lines[-1] == '':
            lines.pop()
        reward = rewards[-1] if rewards else None
        lines.append(f"seed {seed}: outcome {outcome.get('status')}, their "
                     f"RolloutHistory rewards[-1] = {reward}; details in {save_dir}")
        post.append({'m': 'terminal', 'a': [lines]})
    else:
        notes.append('bridge_episode.json has no ledger_gates: no gate table')
    code = (0 if outcome.get('success') else 1) if outcome else None
    return pre, post, notes, code


def build_run_tape(run_dir):
    """(tape, info) of a run directory (ledger.jsonl and run_<stamp>.log)."""
    run_dir = Path(run_dir).resolve()
    rows = read_ledger(run_dir / 'ledger.jsonl')
    log = find_run_log(run_dir)
    events, partial = read_run_log(log)
    lines = [e['a'][0] for e in events if e['m'] == 'line']
    rc = run_config_block(lines)
    save_dir = run_dir.parent.parent
    ep_file = save_dir / 'bridge_episode.json'
    episode = json.loads(ep_file.read_text(encoding='utf-8')) if ep_file.exists() else None
    header, header_src = derive_header(lines, rows, rc, episode)
    summary, summary_src = derive_summary(run_dir, lines, rows)
    info = {'source': str(run_dir), 'run_log': log.name, 'kind': 'bridge' if episode else 'boxels',
            'ledger_rows': len(rows), 'log_lines': len(lines),
            'log_records': sum(1 for e in events if e['m'] == 'log'),
            'dropped_partial_line': partial, 'header': header, 'header_from': header_src,
            'summary': summary, 'summary_from': summary_src, 'notes': []}
    pre, post = [], []
    code = 0 if summary.get('success') else 1
    if episode is not None:
        pre, post, notes, bridge_code = _bridge_calls(episode, save_dir)
        if bridge_code is not None:
            code = bridge_code                  # the driver's main() return value
        info['notes'] += notes
    calls, report = merge(events, rows, header=header, summary=summary)
    info['anchors'] = report
    tape = {'name': run_dir.name, 'source': info['source'], 'save_dir': str(save_dir) if episode else None,
            'calls': pre + [{'m': 'attach', 'a': [run_dir.name]}] + calls
            + [{'m': 'detach'}] + post + [{'m': 'finish', 'a': [code]}]}
    return tape, info


# ---------------------------------------------------------------------------
# The made tapes (R's plan review S-d): sample lines for the rules, a row of
# every ledger kind, every end status
# ---------------------------------------------------------------------------

class Made:
    def __init__(self, name):
        self.name, self.calls, self.t, self.ctx = name, [], 5000.0, None

    def c(self, m, *a, **kw):
        call = {'m': m}
        if a:
            call['a'] = list(a)
        if kw:
            call['kw'] = kw
        self.calls.append(call)

    def line(self, *texts):
        for t in texts:
            self.c('line', t)

    def row(self, kind, dt=0.4, **fields):
        self.t = round(self.t + dt, 6)
        row = {'t': self.t, 'wall': round(1.79e9 + self.t, 6), 'kind': kind}
        if self.ctx is not None:
            row['plan'], row['step'] = self.ctx
        row.update(fields)
        self.c('ledger', kind, row)

    def plan(self, pid, actions, call='mission', dt=1.25, goal=None):
        self.ctx = None
        self.row('plan', plan_id=pid, call=call, goal=goal or ['holding', 'dice'], targets=['dice'],
                 actions=actions, plan_obj=(1000 + pid if actions is not None else None),
                 plan_time_s=dt)

    def step(self, pid, idx, action, *args):
        self.ctx = (pid, idx)
        self.row('step', action=action, args=list(args), plan_obj=1000 + pid)

    def end(self, status, dt=0.75):
        self.row('step_end', dt=dt, status=status)
        self.ctx = None

    def tape(self):
        return {'name': self.name, 'source': f'made:{self.name}', 'save_dir': None, 'calls': self.calls}


def _made_holding():
    r = Made('holding')
    r.c('startup', 'Loading scene from 1747173591.670785.json (pinned 1747173590)')
    r.c('stderr', '[random-pairs] seed 4: 3 occluders, 1 hidden target\n')
    r.c('stderr', 'pybullet build time: Jan  1 2000 00:00:00\n')
    r.c('attach', 'run_made_holding')
    r.c('log', 'INFO', 'root', 'Run started  : 2000-01-01_00-00-00')
    r.row('ledger_open', pid=1)
    r.line(BANNER, 'FULL PIPELINE: PDDLStream + Replanning', BANNER, '',
           "  model tweaks: {'M8': True, 'M9': False}; domain domain_pddlstream_m8.pddl")
    r.c('header', scene='random-pairs seed 4, 3 occluders, 1 targets, 1 hidden', goal='holding dice at home',
        switches='M8 on, M9 off, grip squeeze 0.5 mm, planner ff-astar2, slip fixes none')
    r.row('episode', seed=4, scene_file='made.json')
    r.row('driver_clock', initialize_call=0.0)
    r.row('gate_info', gates=['G3'])
    r.row('gate_phase', phase='setup')
    r.row('bridge_timing', initialize_s=1.0)
    r.row('after_settle', moved=[])
    r.row('render', purpose='eye', n=1)
    r.row('domain', file='domain_pddlstream_m8.pddl')
    r.line('', '--- Phase 1: Environment Setup ---',
           '  [D7] initial arm readback is not at q_home (max |dq| 2.1e-03 rad)',
           '  7 boxels, 3 shadows, 3 occluders',
           '  9 boxels, 0 shadows, 1 occluders',
           '  1 boxels, 2 shadows, 1 occluders',
           '  Target: dice (given; not in the first observation; the robot must search)',
           '  Target: cup at boxel box_3 (given; in the first observation, direct pick)',
           '  Target: ball at boxel box_4 (direct pick)',
           '  Target: dice',
           '  ORACLE: Actually hidden in shadow_of_cup__02 (camera-ray occlusion)',
           '  ORACLE: Actually hidden by camera-ray occlusion but inside NO shadow',
           '  Stack goal: no stack in this mission',
           '  Find-and-tray-stack goal: none',
           '  2-cube tray tower: none',
           '  [D9] the die is VISIBLE in the first observation',
           '  [eye] snapshot initial failed: no render',
           '  [pre-flight] seed 4 accepted',
           '  [warn] a made warning',
           '  NOTE: a made note',
           '  WARNING: a made warning line',
           '  stop_before_planning: returning (made line)',
           '  -> cup: object boxel + 3 shadow fragments',
           '  -> ball: object boxel + 1 shadow fragment',
           '  [F20] cup is visible in this observation but had no boxel; registered (185 px); '
           'the SEARCH TARGET, directly pickable',
           '  [F20] ball is visible in this observation but had no boxel; registered (90 px); '
           'an occluder with 2 shadow fragments',
           '  [F20] box is visible in this observation but had no boxel; registered (40 px); a bystander',
           '  [F20] cup is visible (120 px) but partly behind the arm',
           '  [F20] peg is visible (12 px) but lies below the table',
           '  a line no rule reads')
    r.c('log', 'WARNING', 'streams', 'a made warning record (stays in the run log)')
    r.c('log', 'ERROR', 'execution', 'a made error record')
    r.c('log', 'CRITICAL', 'root', 'a made critical record')
    # plan 1: every move destination kind, observe, an integrity replan
    acts1 = [['move', 'cfg:q_home', 'cfg:look_cup_0', 'view__look_cup_0', 'Trajectory@1'],
             ['observe', 'cup', 'cfg:look_cup_0'],
             ['move', 'cfg:look_cup_0', 'cfg:q1', 'free_003', 'Trajectory@2'],
             ['move', 'cfg:q1', 'cfg:q_home', 'q_home', 'Trajectory@3'],
             ['pick', 'dice', 'shadow_of_cup__01', 'Grasp@4', 'cfg:q2'],
             ['place', 'dice', 'free_003', 'cfg:q3'],
             ['place_hiding', 'dice', 'shadow_of_ball', 'cfg:q4'],
             ['stack', 'dice', 'cube_1', 'cfg:q5'],
             ['sense', 'cup', 'shadow_of_dice'],
             ['sense', 'dice', 'free_009'],
             ['observe', 'dice', 'cfg:q6'],
             ['wave', 'dice']]
    r.line('', '=== PLAN #1 ===', 'Unknown shadows remaining: 3',
           'no unknown shadows remain, but dice is registered at shadow_of_cup__02',
           'Stack progress: 1 of 3 placed', 'Tray-stack progress: 0 of 2',
           '  [M8] dice pose_radius 0.031 m is outside its commit margin 0.020 m',
           '  [#76-diag] outcome=plan_found, elapsed=1.250s')
    r.plan(1, acts1)
    r.row('plan_call', plan_id=1)
    r.line('    [eye #2] plan#1 planned (12 actions) | held=none',
           '  [timing] planner.plan() #1: 1.250s (cumulative 1.250s)', 'Plan: 12 actions')
    dests = [('view__look_cup_0', 'ok'), ('view__sense_retract_0', 'ok'), ('view__q_home', 'ok'),
             ('view__corner', 'ok'), ('free_003', 'ok'), ('shadow_of_cup__01', 'ok'),
             ('cup', 'ok'), ('home', 'ok')]
    idx = 0
    for dest, status in dests:
        idx += 1
        r.line('', '  Executing: move')
        r.step(1, idx, 'move', 'cfg:q', 'cfg:q_next', dest, 'Trajectory@9')
        r.row('move_resolve', resolved=True)
        r.line(f'    Moving to {dest} (10 waypoints)...', f'    -> Arrived at {dest}')
        r.end(status)
    idx += 1
    r.line('', '  Executing: observe')
    r.step(1, idx, 'observe', 'cup', 'cfg:look_cup_0')
    r.line('    [F20] cup is visible (120 px) but partly behind the arm')
    r.row('observe_result', obj='cup', status='observe_ok', lost=False)
    r.row('render', purpose='observe', n=2)
    r.end('observe_ok')
    idx += 1
    r.line('', '  Executing: move')
    r.step(1, idx, 'move', 'cfg:q', 'cfg:q_home', 'q_home', 'Trajectory@10')
    r.row('readback_check', ok=True)
    r.row('at_home_test', passed=True, max_abs_err=1.7e-4, hold_steps=22, consecutive_misses=0,
          config='q_home')
    r.line('    [D7] at-home test passed: max |dq| 1.70e-04 rad after a 22-step hold (config q_home)')
    r.row('at_home_test', passed=False, max_abs_err=3.2e-3, hold_steps=120, consecutive_misses=1,
          config='q_readback_1')
    r.line('    [D7] at-home test FAILED: max |dq| 3.20e-03 rad after a 120-step hold (config q_readback_1)')
    r.row('at_home_test', passed=False, max_abs_err='n/a', hold_steps=0, consecutive_misses=2,
          config='q_readback_2')
    r.line('    [integrity] disturbed: cup after plan#1 move(q_home)',
           '    [integrity] toppled: ball after plan#1 move(q_home)',
           '    [integrity] off_support: box after plan#1 move(q_home)',
           '    [integrity] knocked_off_table: peg after plan#1 move(q_home)',
           '    [integrity] lost: cube_1 after plan#1 move(q_home)',
           '    [integrity] wobbled: cube_2 after plan#1 move(q_home)',
           '    [integrity] cup disturbed 3 times in this plan, giving up')
    r.end('integrity_replan')
    # plan 2: sense outcomes, each reason and the fallback
    reasons = ['sense_clear_but_empty', 'sense_contains_nontarget', 'sense_still_blocked',
               'sense_missing_shadow', 'sense_contains_unlocalizable', 'sense_made_up_reason']
    acts2 = [['sense', 'dice', f'shadow_of_cup__0{i}'] for i in range(1, 7)]
    r.line('', '  [M8] observe strikes of cup reset (re-registered or re-posed)',
           '  giveup parole 1/2: ball re-enters the grasp stream after 4 replans (#P1 non-absorbing giveup)',
           '', '=== PLAN #2 ===', 'Unknown shadows remaining: 2')
    r.plan(2, acts2, dt=0.5)
    r.line('    [eye #3] plan#2 planned (6 actions) | held=none',
           '  [timing] planner.plan() #2: 0.500s (cumulative 1.750s)')
    for i, reason in enumerate(reasons, 1):
        r.line('', '  Executing: sense')
        r.step(2, i, 'sense', 'dice', f'shadow_of_cup__0{i}')
        r.line(f'    Sensing shadow_of_cup__0{i} (fixed camera)...')
        r.row('sense_result', reason=reason, region=f'shadow_of_cup__0{i}')
        r.row('belief', region=f'shadow_of_cup__0{i}', op='status', status='not_here',
              channel='planned_sense_render')
        r.end('sense_outcome')
    # plan 3: the target found, picked, a firm grip, a pick failure
    r.line('', '=== PLAN #3 ===', 'Unknown shadows remaining: 1')
    r.plan(3, [['move', 'cfg:q', 'cfg:q7', 'shadow_of_cup__07', 'Trajectory@11'],
               ['sense', 'dice', 'shadow_of_cup__07'], ['pick', 'dice', 'shadow_of_cup__07', 'Grasp@5', 'cfg:q8'],
               ['pick', 'dice', 'dice', 'Grasp@6', 'cfg:q9']], dt=0.75)
    r.line('    [eye #4] plan#3 planned (4 actions) | held=none',
           '  [timing] planner.plan() #3: 0.750s (cumulative 2.500s)')
    r.line('', '  Executing: sense')
    r.step(3, 1, 'sense', 'dice', 'shadow_of_cup__07')
    r.row('sense_result', reason='sense_found_target', region='shadow_of_cup__07')
    r.row('belief', region='shadow_of_cup__07', op='status', status='found', channel='planned_sense_render')
    r.line('    *** TARGET FOUND in shadow_of_cup__07! (ray-cast) ***')
    r.end('ok')
    r.line('', '  Executing: pick')
    r.step(3, 2, 'pick', 'dice', 'shadow_of_cup__07', 'Grasp@5', 'cfg:q8')
    r.line('    Grip verified for dice: both pads in contact, pad_normal_force=34.43N, '
           'measured half-width 10.3 mm vs estimate 10.1 mm',
           '    [M10] dice touched by the pads, pose uncertain', '    *** dice PICKED UP! ***')
    r.end('ok')
    r.line('', '  Executing: pick')
    r.step(3, 3, 'pick', 'cup', 'cup', 'Grasp@6', 'cfg:q9')
    r.line('    ERROR: Cannot pick cup (made): gripper already holds dice.',
           '    IK or grip failure during pick of cup', '    pick failure 1/3 for cup')
    r.end('pick_failure')
    # plan 4: the disposal, its no-plan, a stale precondition, a release
    # that did not verify, every reason rule
    r.line('', '=== PLAN #4 ===', 'Unknown shadows remaining: 0')
    r.plan(4, None, dt=2.5)
    r.line('    [eye #5] plan#4 planned (no plan) | held=dice',
           '  no mission plan with dice held: planning a disposal place instead (audit #58 drop '
           'retired 2026-08-21).')
    r.plan(4, [['move', 'cfg:q', 'cfg:q10', 'free_011', 'Trajectory@12'],
               ['place', 'dice', 'free_011', 'cfg:q11']], call='disposal', dt=0.5)
    r.line('  [timing] planner.plan() #4: 3.000s (cumulative 5.500s)')
    r.line('', '  Executing: move')
    r.step(4, 1, 'move', 'cfg:q', 'cfg:q10', 'free_011', 'Trajectory@12')
    r.line('    ERROR: Cannot resolve the trajectory (made)')
    r.end('motion_resolve_failed')
    r.line('', '  Executing: place')
    r.step(4, 2, 'place', 'dice', 'free_011', 'cfg:q11')
    r.row('place_target', centre=[0.1, 0.2, 0.3])
    r.line('    IK failure during place of dice', '    drop-verify failed for dice after place',
           '    [release-obs] dice on free_011: observed 150 px, top 0.45, shift 0.2 mm',
           '    [release-obs] dice: observed 140 px, top 0.45, shift 12.7 mm')
    r.end('place_failure')
    r.line('', '  Executing: stack')
    r.step(4, 3, 'stack', 'dice', 'cube_1', 'cfg:q12')
    r.line('    IK failure during stack of dice', '    stack failure 2/3 for dice')
    r.end('stack_failure')
    r.line('', '  Executing: place')
    r.step(4, 4, 'place', 'dice', 'free_011', 'cfg:q11')
    r.line('    empty hand at place entry (dice)', '    empty hand at stack entry (dice)')
    r.end('empty_hand')
    r.line('', '  Executing: pick')
    r.step(4, 5, 'pick', 'dice', 'dice', 'Grasp@7', 'cfg:q13')
    r.line('    ERROR: no registry estimate for the held dice', '    transit loss 2/3 for dice')
    r.end('stale_precondition')
    r.line('', '  Executing: place_hiding')
    r.step(4, 6, 'place_hiding', 'dice', 'shadow_of_ball', 'cfg:q14')
    r.line('    [M8] observe strike 1/3 for ball; look view__look_ball_1 removed',
           '    [M8] observe strike 3/3 for ball; look view__look_ball_2 removed PARKED')
    r.end('ok')
    r.line('', '  Executing: observe')
    r.step(4, 7, 'observe', 'ball', 'cfg:look_ball_3')
    r.row('observe_result', obj='ball', status='observe_incomplete', lost=False)
    r.end('observe_incomplete')
    r.line('', '  Executing: observe')
    r.step(4, 8, 'observe', 'peg', 'cfg:look_peg_1')
    r.row('observe_result', obj='peg', status='observe_incomplete', lost=True)
    r.end('observe_incomplete')
    r.line('', '  Executing: observe')
    r.step(4, 9, 'observe', 'box', 'cfg:look_box_1')
    r.row('observe_result', obj='box', status='observe_made_up', lost=False)
    r.end('observe_ok')
    r.line('', '  Executing: move')
    r.step(4, 10, 'move', 'cfg:q', 'cfg:q_home', 'q_home', 'Trajectory@13')
    r.row('gate_violation', gate='G7', fn='move_robot_smooth', detail='unlisted call (made)')
    r.line('ERROR: two consecutive planned moves to q_home left TAMPURA\'s at-home test false; ending '
           'the episode (home_not_reached, D7 (vi)).')
    r.end('home_not_reached')
    r.line('', '  Executing: stack')
    r.step(4, 11, 'stack', 'dice')
    r.end('unlabelled')
    r.line('', '  Executing: sense')
    r.step(4, 12, 'sense', 'dice')
    r.end('a_made_up_status')
    r.row('step_end', status='ok')                      # no open step: ignored
    # plan 5: a WARNING while thinking, an empty plan
    r.line('', '=== PLAN #5 ===', 'WARNING: nothing to plan for (made)')
    r.plan(5, [], dt=0.25)
    r.line('    [eye #6] plan#5 planned (0 actions) | held=none',
           '  [timing] planner.plan() #5: 0.250s (cumulative 5.750s)')
    r.row('main_return_readback', ok=True)
    r.row('gate_record', counts={})
    r.row('belief', region='shadow_of_cup__07', op='target_found_in', value='picked')
    r.c('say', 'a made line said verbatim')
    r.c('say', 'G19: seed 4 said through say()')
    r.c('warn', 'G19: seed 4 warned through warn()')
    r.c('warn', 'a made warning through warn()')
    r.c('stderr', 'usage: test_full_pipeline.py [-h] [--scene SCENE]\n'
                  '                             [--seed SEED]\n'
                  'test_full_pipeline.py: error: argument --seed: invalid int value\n')
    r.c('stderr', '[pre-flight] seed 4 rejected (made)\n[warn] a made stderr warning\n'
                  'G13 runtime check failed: made\nERROR: made stderr error\nWARNING: made\n'
                  'PHYSICAL_FAILURE: made\nG19: seed 4 made stderr\nTraceback (not shown)\n')
    r.line('  PHYSICAL_FAILURE (goal): (holding dice), made','    [eye #7] final (SUCCESS: None) | held=dice',
           '', BANNER, 'SUCCESS!', '  Target: dice', '  Found in: shadow_of_cup__07',
           '  Shadows searched: 7 (1 unresolved)', '  Plans executed: 5',
           '  Stack goal: none', '  Final on-relations: {}', '  Target: after the rows', '',
           '--- Planning timing summary ---', '  Total plan() calls       : 5', BANNER)
    r.c('summary', success=True, exit_reason=None, plan_count=5, plan_times=[1.25, 0.5, 0.75, 3.0, 0.25],
        total_plan_time=5.75, log_path='<LOG>')
    r.row('ledger_close', write_errors=0)
    r.c('detach')
    r.c('terminal', ['a made line printed inside terminal()', 'G3       PASS  made row'])
    r.c('stderr', 'PHYSICAL_FAILURE: a last stderr line without its newline')
    r.c('finish', 0)
    return r.tape()


def _made_stack():
    r = Made('stack')
    r.c('attach', 'run_made_stack')
    r.line("  model tweaks: {'M8': False}; domain domain_pddlstream.pddl")
    r.c('header', scene='stack seed 2, 0 occluders, 3 targets, 0 hidden', goal='stack', switches='M8 off')
    r.line('  6 boxels, 0 shadows, 0 occluders', '  Stack goal: red_object on orange_object',
           '', '=== PLAN #1 ===')
    r.plan(1, [['move', 'cfg:q0', 'cfg:q1', 'red_object', 'Trajectory@1'],
               ['pick', 'red_object', 'red_object', 'Grasp@1', 'cfg:q1'],
               ['move', 'cfg:q1', 'cfg:q2', 'orange_object', 'Trajectory@2'],
               ['stack', 'red_object', 'orange_object', 'cfg:q2']],
           goal=['and', ['on', 'red_object', 'orange_object']])
    r.line('  [timing] planner.plan() #1: 1.250s (cumulative 1.250s)')
    r.line('', '  Executing: pick')
    r.step(1, 1, 'pick', 'red_object', 'red_object', 'Grasp@1', 'cfg:q1')
    r.end('ok')
    r.line('', '  Executing: stack')
    r.step(1, 2, 'stack', 'red_object', 'orange_object', 'cfg:q2')
    r.line('    drop-verify failed for red_object after stack', '    stack failure 1/3 for red_object')
    r.end('stack_failure')
    r.line('', '=== PLAN #2 ===')
    r.plan(2, None, dt=2.0, goal=['and', ['on', 'red_object', 'orange_object']])
    r.line('  [timing] planner.plan() #2: 2.000s (cumulative 3.250s)', 'ERROR: No plan found!',
           '', BANNER, 'FAILED: no plan for the stack goal', '  Stack goal: 0 of 1',
           '  Final on-relations: {}', '  Plans executed: 2', '--- Planning timing summary ---', BANNER)
    r.c('summary', success=False, exit_reason='planner_failed', plan_count=2, plan_times=[1.25, 2.0],
        total_plan_time=3.25, log_path='<LOG>')
    r.row('ledger_close', write_errors=0)
    r.c('detach')
    r.c('finish', 1)
    return r.tape()


def _made_tray():
    r = Made('tray')
    r.c('attach', 'run_made_tray')
    r.c('header', scene=None, goal='find-and-tray-stack', switches=None)
    r.line('  2-cube tray tower: cube_h on tray', '', '=== PLAN #1 ===', 'Tray-stack progress: 0 of 1')
    r.plan(1, [['pick', 'cube_h', 'box_9', 'Grasp@1', 'cfg:q1'], ['stack', 'cube_h', 'tray', 'cfg:q2']],
           goal=['and', ['on', 'cube_h', 'tray']])
    r.line('', '  Executing: pick')
    r.step(1, 1, 'pick', 'cube_h', 'box_9', 'Grasp@1', 'cfg:q1')
    r.end('ok')
    r.line('', '  Executing: stack')
    r.step(1, 2, 'stack', 'cube_h', 'tray', 'cfg:q2')
    r.end('ok')
    r.line('', BANNER, 'SUCCESS!', '  Stack goal: 1 of 1', '  Plans executed: 1',
           '--- Planning timing summary ---', BANNER)
    r.c('summary', success=True, exit_reason=None, plan_count=1, plan_times=[1.25], total_plan_time=1.25,
        log_path=None)
    r.c('detach')
    r.c('finish', 0)
    return r.tape()


def _made_plain_goal():
    r = Made('plain_goal')
    r.c('attach', 'run_made_plain_goal')
    r.c('header', scene='default seed 0', goal='holding', switches=None)
    r.line('', '=== PLAN #1 ===')
    r.plan(1, [['move', 'cfg:q0', 'cfg:q1', 'orange_object', 'Trajectory@1'],
               ['pick', 'orange_object', 'orange_object', 'Grasp@1', 'cfg:q1']])
    r.line('', '  Executing: move')
    r.step(1, 1, 'move', 'cfg:q0', 'cfg:q1', 'orange_object', 'Trajectory@1')
    r.end('ok')
    r.line('', BANNER, 'SUCCESS!', BANNER)
    r.c('summary', success=True, exit_reason=None, plan_count=1, plan_times=[1.25], total_plan_time=1.25,
        log_path=None)
    r.c('header', scene=None, goal='push the button', switches=None)
    r.c('summary', success=True, exit_reason=None, plan_count=0, plan_times=None, total_plan_time=0.0,
        log_path=None)
    r.c('summary', success=False, exit_reason=None, plan_count=0, plan_times=None, total_plan_time=0.0,
        log_path=None)
    r.c('detach')
    r.c('finish', 0)
    return r.tape()


def _made_bridge():
    r = Made('bridge')
    r.c('startup', 'Loading scene from 1747173591.670785.json')
    r.c('stdout', 'G19: seed 7 loaded 1747173593.json, the campaign pins 1747173590: made')
    r.c('warn', 'G19: seed 7 loaded 1747173593.json, the campaign pins 1747173590: made')
    r.c('set_context', scene='find_dice seed 7')
    r.c('attach', 'run_made_bridge')
    r.c('header', scene=None, goal='holding dice at home', switches=None)
    r.line('', '=== PLAN #1 ===')
    r.plan(1, [['move', 'cfg:q0', 'cfg:look', 'view__look_cup_0', 'Trajectory@1'], ['observe', 'cup', 'cfg:look']],
           goal=['and', ['holding', 'dice'], ['at_config', 'q_home']])
    r.line('', '  Executing: move')
    r.step(1, 1, 'move', 'cfg:q0', 'cfg:look', 'view__look_cup_0', 'Trajectory@1')
    r.end('ok')
    _made_bridge_tag2(r)
    r.line('', BANNER, 'FAILED', BANNER)
    r.c('summary', success=False, exit_reason='physics_mismatch', plan_count=1, plan_times=[1.25],
        total_plan_time=1.25, log_path='<LOG>')
    r.row('ledger_close', write_errors=0)
    r.c('detach')
    r.c('terminal', ['ledger   PASS  12 rows, complete', 'G3       PASS  1 steps over 1 plans',
                     'G7       FAIL  call to p.getBasePositionAndOrientation outside the whitelist',
                     'G13      WARN  runtime check slow (3.1 s)', 'G10      SKIP  no stream text',
                     'G21      INFO  made',
                     'seed 7: outcome gate_failed, their RolloutHistory rewards[-1] = 0.0; details in '
                     '/tmp/made/bridge_7'])
    r.c('finish', 1)
    return r.tape()


def _made_bridge_tag2(r):
    """Gate 7 (SPEC D14, R's ruling of 21 Nov 10:08): what the console gained since checkpoint 1,
    in the bridge tape after plan 1.  (a) A sample line for each new rule: the interior_of_ names
    (in the plan's actions and the rows' regions), the M7 suspension and its end; every line is
    copied from its print site (file:line on the tag, beside it) with sample values.  (b) The end
    statuses look_outcome, action_failed and dead.  (c) A row of each ledger kind new since the
    checkpoint, with its call site's keyword names (pin 40's schema.json): interior_region (both
    sites), look_reveals, look_result, seen_under, seen_under_released, sense_discovery and
    m7_suspension (start and end)."""
    goal = ['and', ['holding', 'dice'], ['at_config', 'q_home']]
    r.line('    [interior] interior_of_cup: the space under cup (6.0 x 6.0 x 9.5 cm) is a hiding region, '
           'unknown; searched by moving cup away')                            # interior_regions.py:259-261
    r.row('interior_region', obj='cup', cast=True, region='interior_of_cup', min_corner=[0.47, -0.03, 0.625],
          max_corner=[0.53, 0.03, 0.72], first_observation=False)             # interior_regions.py:262-264
    r.line('    [interior] ball: the space it now covers lay in free space, observed empty before it came '
           'to stand there; no region under it (D6 status rule)')             # interior_regions.py:223-225
    r.row('interior_region', obj='ball', cast=False, reason='observed_before_placement')  # interior_regions.py:226-227
    r.line("    [interior] dice is in view (85 px) inside cup's box: it lies under that cover, where no look "
           "and no grasp reaches it.  Not registered as an object; interior_of_cup is where to look once cup "
           "is moved (BF#65 (d))")                                           # interior_regions.py:389-394
    r.row('seen_under', target='dice', cover='cup', region='interior_of_cup', pixels=85)  # interior_regions.py:395-396
    # plan 2: a look of cup whose own region stays blocked (look_blocked: the target was not seen in
    # it, look_action.py:494-504; a boxel look that does not go on only ends, test_full_pipeline.py:
    # 2559-2606), then a sense whose body reaches M7's F9 give-up (the region suspended, not marked
    # empty)
    r.line('', '=== PLAN #2 ===', 'Unknown shadows remaining: 2')              # test_full_pipeline.py:1902, 1907
    r.plan(2, [['look', 'cup', 'shadow_of_cup__01', 'view__look_cup_1', 'cfg:look_cup_1'],
               ['sense', 'dice', 'shadow_of_cup__02'], ['sense', 'dice', 'interior_of_cup']], goal=goal)
    r.line('', '  Executing: look')                                            # test_full_pipeline.py:2200
    r.step(2, 1, 'look', 'cup', 'shadow_of_cup__01', 'view__look_cup_1', 'cfg:look_cup_1')
    r.line('    look shadow_of_cup__01: still_blocked (40% hidden)',           # look_action.py:437-438
           '    look: shadow_of_cup__01 blocked [strike 1/3]',                 # look_action.py:485
           "    look cup from look_cup_1: look_blocked; named regions ['shadow_of_cup__01'], "
           "objects ['cup'], re-posed [], registered []")                     # look_action.py:505-507
    r.row('look_reveals', config='look_cup_1', named=['shadow_of_cup__01', 'cup'])  # test_full_pipeline.py:2545
    r.row('look_result', reason='look_blocked', continue_=False, obj='cup', region='shadow_of_cup__01',
          config='look_cup_1', outcomes={'shadow_of_cup__01': 'still_blocked'},
          hidden={'shadow_of_cup__01': 0.4}, reposed=[], found_in=None, registered=[],
          blocked=['shadow_of_cup__01'], parked=[])                           # test_full_pipeline.py:2546-2555
    r.end('look_outcome')                                                      # test_full_pipeline.py:2605
    r.line('', '  Executing: sense')                                           # test_full_pipeline.py:2200
    r.step(2, 2, 'sense', 'dice', 'shadow_of_cup__02')
    # in the tag's order: handle_sense_action prints and suspends (execution.py:3393-3403), writes
    # the discovery row in its loop over the bodies found (3484, 3689), and returns; then main
    # writes sense_result and ends the step (test_full_pipeline.py:2461-2464)
    r.line('    Sensing shadow_of_cup__02 (fixed camera)...')                  # execution.py:3027
    r.line('    shadow_of_cup__02: a body found in it reaches the F9 give-up, so nothing re-covers what it '
           'hides; suspending shadow_of_cup__02 for 120 s instead of marking it empty (M7): ball '
           'rediscovered 3 times')                                            # execution.py:3395-3400
    r.row('belief', region='shadow_of_cup__02', op='status', status='unresolved',
          channel='strike_park')                                              # belief.py:112 (execution.py:3401-3403)
    r.row('m7_suspension', op='start', region='shadow_of_cup__02', bodies={'ball': 3},
          seconds=120.0)                                                      # belief.py:140-141
    r.row('sense_discovery', body='ball', region='shadow_of_cup__02', rediscovery=True, kept=['shadow_of_ball'],
          recast=[], giveup=True, parked=True)                                # execution.py:3689-3694
    r.row('sense_result', reason='sense_contains_nontarget', continue_=False)  # test_full_pipeline.py:2461-2462
    r.end('sense_outcome')                                                     # test_full_pipeline.py:2464
    # the loop head of plan 3: the suspension's time is over (test_full_pipeline.py:1845-1849)
    r.row('belief', region='shadow_of_cup__02', op='status', status='unknown',
          channel='suspension_over')                                          # belief.py:155
    r.row('m7_suspension', op='end', region='shadow_of_cup__02', ended_by='released')  # belief.py:162-163
    r.line('  [M7] shadow_of_cup__02 is back in the search: its 120 s suspension at the F9 give-up is '
           'over')                                                            # test_full_pipeline.py:1847-1849
    # plan 3: no plan through the region dice was seen under
    r.line('', '=== PLAN #3 ===', 'Unknown shadows remaining: 2')              # test_full_pipeline.py:1902, 1907
    r.plan(3, None, dt=1.5, goal=goal)
    r.line("  [interior] no plan through interior_of_cup alone: the record 'dice seen under a cover' ends; "
           "every unknown region is on offer again (BF#65 (d))")              # interior_regions.py:415-417
    r.row('seen_under_released', target='dice', region='interior_of_cup', reason='no_plan')  # interior_regions.py:418-419
    # plan 4: the Wumpus world's two statuses (wumpus/narrate.py:128, an action that returned not
    # ok and a move into a pit or the wumpus's cell); a bridge run never writes them, the console
    # reads every status of run_logger.STEP_END_STATUSES
    r.line('', '=== PLAN #4 ===')                                              # test_full_pipeline.py:1902
    r.plan(4, [['move', 'p1-2'], ['move', 'p2-2']], dt=0.25, goal=['holding', 'gold'])
    r.step(4, 1, 'move', 'p1-2')
    r.end('action_failed')
    r.step(4, 2, 'move', 'p2-2')
    r.end('dead')


def _made_g19_stop():
    r = Made('g19_stop')
    r.c('startup', 'Loading scene from 1747173593.826745.json')
    r.c('raise', 'SystemExit', 'G19: seed 10 loaded 1747173593.826745.json, pinned 1747173590')
    return r.tape()


def _made_crash():
    r = Made('crash')
    r.c('attach', 'run_made_crash')
    r.c('header', scene='random-pairs seed 0, 2 occluders, 1 targets, 1 hidden', goal='holding orange_object',
        switches='M8 on')
    r.line('', '=== PLAN #1 ===', 'Unknown shadows remaining: 2')
    r.plan(1, [['move', 'cfg:q0', 'cfg:q1', 'green_object', 'Trajectory@1']], goal=['holding', 'orange_object'])
    r.line('', '  Executing: move')
    r.step(1, 1, 'move', 'cfg:q0', 'cfg:q1', 'green_object', 'Trajectory@1')
    r.c('raise', 'RuntimeError', 'a made crash inside a step')
    return r.tape()


def _made_interrupt():
    r = Made('interrupt')
    r.c('attach', 'run_made_interrupt')
    r.line('', '=== PLAN #1 ===')
    r.c('raise', 'KeyboardInterrupt')
    return r.tape()


MADE = {
    'holding': _made_holding, 'stack': _made_stack, 'tray': _made_tray, 'plain_goal': _made_plain_goal,
    'bridge': _made_bridge, 'g19_stop': _made_g19_stop, 'crash': _made_crash, 'interrupt': _made_interrupt,
}


def made_tape(name):
    return MADE[name]()


# ---------------------------------------------------------------------------
# Checking a tape and what it reaches
# ---------------------------------------------------------------------------

def check_tape(tape):
    """Problems of a tape's form (an empty list when it is well formed)."""
    bad = []
    for k, c in enumerate(tape.get('calls', [])):
        m = c.get('m')
        if m not in CALL_KINDS:
            bad.append(f'call {k}: unknown kind {m!r}')
        elif m == 'raise' and (c.get('a') or [None])[0] not in RAISABLE:
            bad.append(f'call {k}: cannot raise {c.get("a")}')
        elif m == 'ledger' and not (isinstance(c.get('a'), list) and len(c['a']) == 2
                                    and isinstance(c['a'][1], dict)):
            bad.append(f'call {k}: a ledger call needs [kind, row]')
    return bad


def tape_texts(tape):
    """Every text a tape hands the Console: narration lines (stripped, as
    narration matches them), say, warn, startup notes, stderr and terminal()
    lines, and the names in ledger rows."""
    out = []
    for c in tape['calls']:
        m, a = c['m'], c.get('a', [])
        if m == 'line':
            out.append(a[0].strip())
        elif m in ('say', 'warn', 'startup'):
            out.append(a[0])
        elif m == 'stderr':
            out.extend(a[0].split('\n'))
        elif m == 'terminal':
            out.extend(a[0])
        elif m == 'log':
            out.append(a[2])
        elif m == 'ledger':
            row = a[1]
            for key in ('args', 'region', 'obj'):
                v = row.get(key)
                out.extend(x for x in (v if isinstance(v, list) else [v]) if isinstance(x, str))
            for act in row.get('actions') or []:
                out.extend(x for x in act if isinstance(x, str))
    return [t for t in out if t]


def console_rules(cu):
    """(name, compiled pattern) of every regex rule in console_ui: the
    module's compiled patterns, _reason_rules() and _note_rules()."""
    rules = [(name, v) for name, v in sorted(vars(cu).items()) if isinstance(v, re.Pattern)]
    rules += [(f'_reason_rules[{i}]', p) for i, (p, _) in enumerate(cu._reason_rules())]
    rules += [(f'_note_rules[{i}]', p) for i, (p, _) in enumerate(cu._note_rules())]
    return rules


def coverage(tapes, cu=None, statuses=None):
    """What the tapes reach: per rule the number of texts it matches, the
    ledger kinds, end statuses, sense reasons and observe statuses fed."""
    if cu is None:
        sys.path.insert(0, str(REPO))
        import console_ui as cu
    texts = []
    kinds, ends, senses, observes, methods = Counter(), Counter(), Counter(), Counter(), Counter()
    for t in tapes:
        texts += tape_texts(t)
        for c in t['calls']:
            methods[c['m']] += 1
            if c['m'] == 'ledger':
                kind, row = c['a']
                kinds[kind] += 1
                if kind == 'step_end':
                    ends[str(row.get('status'))] += 1
                elif kind == 'sense_result':
                    senses[str(row.get('reason'))] += 1
                elif kind == 'observe_result':
                    observes[f"{row.get('status')} lost={bool(row.get('lost'))}"] += 1
    rules = {}
    for name, pat in console_rules(cu):
        rules[name] = sum(1 for s in texts if pat.match(s))
    res = {'rules': rules, 'rules_not_reached': sorted(k for k, v in rules.items() if not v),
           'ledger_kinds': dict(sorted(kinds.items())), 'step_end_statuses': dict(sorted(ends.items())),
           'sense_reasons': dict(sorted(senses.items())), 'observe_results': dict(sorted(observes.items())),
           'calls': dict(sorted(methods.items()))}
    if statuses is not None:
        res['statuses_not_reached'] = sorted(set(statuses) - set(ends))
    res['sense_texts_not_reached'] = sorted(set(cu._SENSE_TEXT) - set(senses))
    return res


# ---------------------------------------------------------------------------
# Playing a tape
# ---------------------------------------------------------------------------

class Masks:
    def __init__(self, pairs, regexes=()):
        self.pairs = sorted(((str(a), b) for a, b in pairs if a), key=lambda t: -len(t[0]))
        self.regexes = list(regexes)

    def __call__(self, s):
        for a, b in self.pairs:
            if a in s:
                s = s.replace(a, b)
        for pat, rep in self.regexes:
            s = pat.sub(rep, s)
        return s


BASE_REGEXES = [
    (re.compile(r'console_debug_[A-Za-z0-9_]+\.log'), 'console_debug_<X>.log'),
    (re.compile(r'(console_replay\.py", line )\d+'), r'\g<1><N>'),
]


def masks_for(root, tape):
    pairs = [(root, '<RUN>'), (os.path.realpath(root), '<RUN>'), (REPO, '<REPO>')]
    src = tape.get('source') or ''
    if src and not src.startswith('made:'):
        pairs += [(src, '<SRC>')]
    if tape.get('save_dir'):
        pairs += [(tape['save_dir'], '<SAVE>')]
    return Masks(pairs, BASE_REGEXES)


def variant_env(name, home):
    env = dict(os.environ)
    for k in ('FORCE_COLOR', 'NO_COLOR', 'SB_CONSOLE_ASCII', 'SB_AUDIO', 'SB_VOICE', 'PYTHONSTARTUP',
              'PYTHONINSPECT', 'COLORTERM', 'WT_SESSION', 'LC_CTYPE', 'BRIDGE_SCENE_MANIFEST'):
        env.pop(k, None)
    env.update({'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1', 'LC_ALL': 'C.UTF-8',
                'LANG': 'C.UTF-8', 'TERM': 'dumb', 'HOME': str(home), 'PYTHONIOENCODING': 'utf-8',
                'PYTHONPATH': str(REPO)})
    env.update(ENV_SETS[name])
    return env


def play_variant(tape, base, variant):
    """Play the tape in one child (terminal a pipe); returns the raw result
    and the replay folder (deleted by the caller)."""
    root = Path(base) / variant
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    tape_file = root / 'tape.json'
    tape_file.write_text(json.dumps(tape, ensure_ascii=False), encoding='utf-8')
    try:
        proc = subprocess.run([sys.executable, str(HERE), '--child', str(tape_file), '--root', str(root)],
                              cwd=str(root), env=variant_env(variant, root), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=CHILD_TIMEOUT_S)
        rc, out, err, status = proc.returncode, proc.stdout, proc.stderr, 'ended'
    except subprocess.TimeoutExpired as e:        # subprocess.run killed its own child
        rc, out, err, status = None, e.stdout or b'', e.stderr or b'', 'timeout'
    played = root / 'PLAYED.json'
    debug = sorted(p for p in root.rglob('console_debug*.log'))
    return {'root': root, 'rc': rc, 'status': status, 'terminal': out.decode('utf-8', errors='replace'),
            'stderr': err.decode('utf-8', errors='replace'),
            'played': json.loads(played.read_text(encoding='utf-8')) if played.exists() else None,
            'debug': [(p, p.read_bytes().decode('utf-8', errors='replace')) for p in debug]}


def write_variant(res, folder, mask, n_calls):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    debug_text = ''.join(t for _, t in res['debug'])
    console = [ln for ln in debug_text.split('\n') if ln.startswith('[console] ')]

    def put(name, text):
        (folder / name).write_text(mask(text), encoding='utf-8', newline='\n')
    put('console.txt', '\n'.join(console) + ('\n' if console else ''))
    put('terminal.txt', res['terminal'])
    put('debug.txt', debug_text)
    played = res['played'] or {}
    info = {'exit_code': res['rc'], 'status': res['status'], 'tape_calls': n_calls,
            'played_to': played.get('call'), 'ended_by': played.get('by'),
            'debug_files': [mask(str(p)) for p, _ in res['debug']],
            'stderr_pipe': mask(res['stderr'])}
    put('run.json', json.dumps(info, indent=1, ensure_ascii=False) + '\n')
    return info, console


def play(tape, out_dir, envs=DEFAULT_ENVS, keep=False):
    """Play the tape once per environment set into out_dir/<set>/.  Returns
    {set: run.json content}."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='console_replay_'))
    results = {}
    try:
        for variant in envs:
            res = play_variant(tape, base, variant)
            mask = masks_for(res['root'], tape)
            results[variant], _ = write_variant(res, out_dir / variant, mask, len(tape['calls']))
    finally:
        if not keep:
            shutil.rmtree(base, ignore_errors=True)
    return results


def write_inputs(out_dir, tape, info=None, cov=None):
    """inputs.json (compared), INFO_tape.json and INFO_coverage.json (not)."""
    out_dir = Path(out_dir)
    mask = masks_for(Path('/nonexistent-replay-root'), tape)
    counts = Counter(c['m'] for c in tape['calls'])
    kinds = Counter(c['a'][0] for c in tape['calls'] if c['m'] == 'ledger')
    d = {'tape': tape['name'], 'source': mask(tape['source']), 'calls': dict(sorted(counts.items())),
         'ledger_kinds': dict(sorted(kinds.items()))}
    if info is not None:
        d.update({k: info[k] for k in ('kind', 'run_log', 'ledger_rows', 'log_lines', 'log_records',
                                       'dropped_partial_line', 'header', 'header_from', 'summary',
                                       'summary_from', 'anchors', 'notes')})
    (out_dir / 'inputs.json').write_text(mask(json.dumps(d, indent=1, ensure_ascii=False)) + '\n',
                                         encoding='utf-8', newline='\n')
    (out_dir / 'INFO_tape.json').write_text(mask(json.dumps(tape, indent=1, ensure_ascii=False)) + '\n',
                                            encoding='utf-8', newline='\n')
    if cov is not None:
        (out_dir / 'INFO_coverage.json').write_text(json.dumps(cov, indent=1) + '\n',
                                                    encoding='utf-8', newline='\n')


# ---------------------------------------------------------------------------
# The live check: a smart run's own [console] lines against its replay
# ---------------------------------------------------------------------------

TIME_TEXT = re.compile(r'\d+\.\d s')
STAMP_TEXT = re.compile(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}$')


def live_check(run_dir, out_dir):
    """Replay a smart run (one that has console_debug.log) in the 'plain'
    set and compare its [console] lines with the live ones, times, the
    banner stamp and the run folder masked.  Returns the verdict dict."""
    run_dir = Path(run_dir).resolve()
    live_file = run_dir / 'console_debug.log'
    if not live_file.exists():
        raise FileNotFoundError(f'{live_file}: not a smart run')
    tape, info = build_run_tape(run_dir)
    out_dir = Path(out_dir)
    play(tape, out_dir, envs=('plain',))
    write_inputs(out_dir, tape, info)
    rel = None
    try:
        rel = run_dir.relative_to(REPO).as_posix()
    except ValueError:
        pass
    save = tape.get('save_dir')
    pairs = [(str(run_dir), f'<RUN>/{run_dir.name}')]
    if rel:
        pairs.append((rel, f'<RUN>/{run_dir.name}'))
    if save:
        pairs.append((save, '<SAVE>'))
        try:
            pairs.append((Path(save).relative_to(REPO).as_posix(), '<SAVE>'))
        except ValueError:
            pass
    live_mask = Masks(pairs)

    def norm(lines):
        return [STAMP_TEXT.sub('<STAMP>', TIME_TEXT.sub('<T> s', ln)) for ln in lines]
    live = norm([live_mask(ln) for ln in live_file.read_text(encoding='utf-8', errors='replace').split('\n')
                 if ln.startswith('[console] ')])
    replay = norm((out_dir / 'plain' / 'console.txt').read_text(encoding='utf-8').splitlines())
    diff = list(difflib.unified_diff(live, replay, 'live', 'replay', lineterm='', n=1))
    verdict = {'run': run_dir.name, 'live_lines': len(live), 'replay_lines': len(replay),
               'equal': live == replay, 'diff_first_80': diff[:80], 'anchors': info['anchors']}
    (out_dir / 'live_check.json').write_text(json.dumps(verdict, indent=1, ensure_ascii=False) + '\n',
                                             encoding='utf-8', newline='\n')
    return verdict


# ---------------------------------------------------------------------------
# The child: one tape through the real Console
# ---------------------------------------------------------------------------

def _played(root, k, by):
    (Path(root) / 'PLAYED.json').write_text(json.dumps({'call': k, 'by': by}), encoding='utf-8')


def child_main(tape_path, root):
    import logging
    import time as _time
    _time.perf_counter = lambda: FROZEN_PERF                 # the replay's clock: frozen
    _time.strftime = lambda fmt, *t: FROZEN_STAMP
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import console_ui
    tape = json.loads(Path(tape_path).read_text(encoding='utf-8'))
    calls = tape['calls']
    console_ui.install()                                    # as install_early does
    hook = handler = log_path = None
    for k, call in enumerate(calls):
        m, a, kw = call['m'], call.get('a', []), call.get('kw', {})
        if m == 'attach':
            run_dir = Path(root) / a[0]
            run_dir.mkdir(parents=True, exist_ok=True)
            log_path = run_dir / f'{a[0]}.log'
            c = console_ui.attach(run_dir, log_path)
            hook = c.narration if c is not None else None
            handler = c.log_handler() if c is not None else None
        elif m == 'line':                                   # run_logger._TeeStream.write
            sys.stdout.write(a[0] + '\n')
            if hook is not None:
                hook(a[0])
        elif m == 'stdout':
            sys.stdout.write(a[0] + '\n')
        elif m == 'log':                                    # the console's handler, as callHandlers
            level, name, msg = a
            levelno = logging.getLevelName(level)
            if isinstance(levelno, int) and levelno >= logging.INFO:
                sys.stdout.write(f'[{level:<7}] {msg}\n')      # RunLogger's console handler
            if handler is not None and isinstance(levelno, int) and levelno >= handler.level:
                handler.handle(logging.LogRecord(name, levelno, '', 0, msg, None, None))
        elif m == 'ledger':
            console_ui.on_ledger_event(a[0], a[1])
        elif m == 'header':
            console_ui.header(**kw)
        elif m == 'summary':
            kw = dict(kw)
            if kw.get('log_path') == '<LOG>':
                kw['log_path'] = str(log_path) if log_path is not None else None
            console_ui.summary(**kw)
        elif m in ('startup', 'say', 'warn'):
            getattr(console_ui, m)(a[0])
        elif m == 'set_context':
            console_ui.set_context(**kw)
        elif m == 'stderr':
            sys.stderr.write(a[0])
        elif m == 'terminal':
            with console_ui.terminal():
                for line in a[0]:
                    print(line)
        elif m == 'detach':
            console_ui.detach()
        elif m == 'finish':
            _played(root, k, 'finish')
            console_ui.finish(a[0] if a else 0)              # os._exit with the console
        elif m == 'raise':
            _played(root, k, 'raise')
            exc = {'SystemExit': SystemExit, 'RuntimeError': RuntimeError,
                   'KeyboardInterrupt': KeyboardInterrupt}[a[0]]
            raise exc(*a[1:])                                # uncaught, as an entry point's
        else:
            raise ValueError(f'unknown call {m!r}')
    _played(root, len(calls), 'end')
    console_ui.finish(0)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--run-dir')
    ap.add_argument('--made')
    ap.add_argument('--list-made', action='store_true')
    ap.add_argument('--live-check')
    ap.add_argument('--out')
    ap.add_argument('--env', default=','.join(DEFAULT_ENVS))
    ap.add_argument('--child', help=argparse.SUPPRESS)
    ap.add_argument('--root', help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.child:
        child_main(a.child, a.root)
        return 0
    if a.list_made:
        for name in MADE:
            print(name)
        return 0
    if not a.out:
        ap.error('--out is needed')
    envs = [e for e in a.env.split(',') if e]
    unknown = [e for e in envs if e not in ENV_SETS]
    if unknown:
        ap.error(f'unknown environment set(s) {unknown}; known: {sorted(ENV_SETS)}')
    if a.live_check:
        v = live_check(a.live_check, a.out)
        print(f"live check {v['run']}: {'equal' if v['equal'] else 'DIFFERS'} "
              f"({v['live_lines']} live, {v['replay_lines']} replayed lines)")
        return 0 if v['equal'] else 1
    if a.made:
        tape, info = made_tape(a.made), None
    elif a.run_dir:
        tape, info = build_run_tape(a.run_dir)
    else:
        ap.error('--run-dir, --made, --list-made or --live-check')
    bad = check_tape(tape)
    if bad:
        raise SystemExit('bad tape: ' + '; '.join(bad[:5]))
    out = Path(a.out)
    res = play(tape, out, envs)
    write_inputs(out, tape, info, coverage([tape]))
    for v, r in res.items():
        print(f"{tape['name']} {v}: exit {r['exit_code']}, played to {r['played_to']} of "
              f"{r['tape_calls']} by {r['ended_by']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
