"""The time and action metrics of one pipeline run, side by side for several
(PAPER_AUDIT BF#52: the baseline Hani's GUI run of 2026-10-30 18:09 set before
the sense-from-anywhere change, and every later run against it).

  python tools/episode_metrics.py RUN [RUN ...] [--json OUT.json]

RUN is a run directory (ours/run_<stamp>: ledger.jsonl, eye.jsonl,
timing_summary.json) or a watch/bridge directory holding one such run
(bridge_episode.json beside ours/).  With two or more runs the last column
is the change of each later run against the first.  Everything is read from
the run's own records; nothing is recomputed from the simulator.

Metrics (seconds unless named otherwise):
  wall_s            ledger open to close (main(): set-up, planning, execution)
  loop_s            the bridge's rollout time (bridge_episode.json), if any
  plan_calls, planning_s, planning_first_s, planning_rest_mean_s
  m8_build_s        the M8 init facts (twin renders, look IK) over all calls
  exec_s            dispatched steps, start to end
  steps, moves, picks, places, senses, observes
  move_s, pick_s, place_s, sense_s, observe_s
  home_for_sense    moves to a view configuration that a sense follows
  home_for_sense_s  their time
  goal_home_moves   the plan's final move to q_home (the goal's conjunct)
  retract_for_sense moves to a sense_retract view that a sense follows
  look_moves        moves to a look configuration (observe follows)
  outcome           success / failure as the run recorded it
"""
import argparse
import json
import os
import sys
from collections import Counter, OrderedDict

SENSE_VIEWS = ('view__q_home',)
HOME_IDS = ('view__q_home', 'home')


def _find_run_dir(path):
    path = os.path.abspath(path)
    if os.path.isfile(os.path.join(path, 'ledger.jsonl')):
        return path
    ours = os.path.join(path, 'ours')
    for base in (ours, path):
        if os.path.isdir(base):
            runs = sorted(d for d in os.listdir(base)
                          if d.startswith('run_') and
                          os.path.isfile(os.path.join(base, d, 'ledger.jsonl')))
            if runs:
                return os.path.join(base, runs[-1])
    raise SystemExit(f"no run directory (ledger.jsonl) under {path}")


def _rows(path):
    out = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def _bridge_json(run_dir):
    for up in (os.path.dirname(os.path.dirname(run_dir)), os.path.dirname(run_dir)):
        p = os.path.join(up, 'bridge_episode.json')
        if os.path.isfile(p):
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
    return None


def metrics(run_dir):
    """The metrics of one run directory as an ordered dict."""
    rows = _rows(os.path.join(run_dir, 'ledger.jsonl'))
    m = OrderedDict()
    m['run'] = os.path.basename(run_dir)
    opens = [r for r in rows if r.get('kind') == 'ledger_open']
    closes = [r for r in rows if r.get('kind') == 'ledger_close']
    m['wall_s'] = (closes[-1]['t'] - opens[0]['t']) if opens and closes else None
    bridge = _bridge_json(run_dir)
    deltas = (bridge or {}).get('time_deltas') or []
    m['loop_s'] = float(deltas[-1]) if deltas else None

    # planning: timing_summary.json first, the ledger's plan_call/plan pairs else
    ts_path = os.path.join(run_dir, 'timing_summary.json')
    ts = {}
    if os.path.isfile(ts_path):
        with open(ts_path, 'r', encoding='utf-8') as f:
            ts = json.load(f)
    per_call = list(ts.get('per_call_planning_time_s') or [])
    if not per_call:
        calls = [r['t'] for r in rows if r.get('kind') == 'plan_call']
        plans = [r['t'] for r in rows if r.get('kind') == 'plan']
        per_call = [b - a for a, b in zip(calls, plans)]
    m['plan_calls'] = len(per_call)
    m['planning_s'] = round(sum(per_call), 3)
    m['planning_first_s'] = round(per_call[0], 3) if per_call else None
    m['planning_rest_mean_s'] = (round(sum(per_call[1:]) / len(per_call[1:]), 3)
                                 if len(per_call) > 1 else None)
    m8 = (ts.get('m8') or {}).get('per_plan') or []
    m['m8_build_s'] = round(sum(float(x.get('build_s', 0.0)) for x in m8), 3) if m8 else None

    # the dispatched steps
    steps = {(r['plan'], r['step']): r for r in rows if r.get('kind') == 'step'}
    ends = {(r['plan'], r['step']): r for r in rows if r.get('kind') == 'step_end'}
    plan_rows = {r.get('plan_id'): r for r in rows if r.get('kind') == 'plan'}
    counts = Counter()
    times = Counter()
    home_for_sense = home_for_sense_s = 0.0
    retract_for_sense = retract_for_sense_s = 0.0
    look_moves = goal_home_moves = 0
    exec_s = 0.0
    for key in sorted(steps):
        s, e = steps[key], ends.get(key)
        dt = (e['t'] - s['t']) if e else 0.0
        act = s.get('action')
        counts[act] += 1
        times[act] += dt
        exec_s += dt
        if act == 'move':
            dest = str((s.get('args') or ['', '', ''])[2])
            nxt = steps.get((key[0], key[1] + 1))
            sense_next = nxt is not None and nxt.get('action') == 'sense'
            n_actions = len((plan_rows.get(key[0]) or {}).get('actions') or [])
            if dest in SENSE_VIEWS and sense_next:
                home_for_sense += 1
                home_for_sense_s += dt
            elif dest.startswith('view__sense_retract') and sense_next:
                retract_for_sense += 1
                retract_for_sense_s += dt
            elif dest.startswith('view__look_'):
                look_moves += 1
            elif dest in HOME_IDS and key[1] == n_actions:
                goal_home_moves += 1
    m['exec_s'] = round(exec_s, 3)
    m['steps'] = sum(counts.values())
    for act in ('move', 'pick', 'place', 'sense', 'observe'):
        m[act + 's'] = counts.get(act, 0)
    for act in ('move', 'pick', 'place', 'sense', 'observe'):
        m[act + '_s'] = round(times.get(act, 0.0), 3)
    m['home_for_sense'] = int(home_for_sense)
    m['home_for_sense_s'] = round(home_for_sense_s, 3)
    m['retract_for_sense'] = int(retract_for_sense)
    m['retract_for_sense_s'] = round(retract_for_sense_s, 3)
    m['look_moves'] = look_moves
    m['goal_home_moves'] = goal_home_moves
    reasons = Counter(r.get('reason') for r in rows if r.get('kind') == 'sense_result')
    m['sense_outcomes'] = ', '.join(f"{k} x{v}" for k, v in sorted(reasons.items())) or None
    # M7 (Hani, 2026-11-20): every F9 give-up suspension, its start and end
    # in seconds from the ledger's opening, from the ledger's m7_suspension
    # rows (so a run killed at the cap has them too); [] when M7 is on and
    # nothing was suspended, absent with M7 off.
    if 'm7_suspend_s' in ts or any(r.get('kind') == 'm7_suspension' for r in rows):
        t0 = opens[0]['t'] if opens else 0.0
        susp, open_rows = [], {}
        for r in rows:
            if r.get('kind') != 'm7_suspension':
                continue
            if r.get('op') == 'start':
                open_rows[r.get('region')] = row = {
                    'region': r.get('region'), 'bodies': r.get('bodies'),
                    'plan': r.get('plan'), 'start_s': round(r['t'] - t0, 3),
                    'seconds': r.get('seconds'), 'end_s': None,
                    'ended_by': 'open_at_end'}
                susp.append(row)
            elif r.get('op') == 'end' and r.get('region') in open_rows:
                row = open_rows.pop(r.get('region'))
                row['end_s'] = round(r['t'] - t0, 3)
                row['ended_by'] = r.get('ended_by')
        m['m7_suspend_s'] = ts.get('m7_suspend_s')
        m['m7_suspensions'] = susp
    if 'success' in ts:
        m['outcome'] = ('success' if ts.get('success') else
                        f"failure ({ts.get('exit_reason')})")
    elif bridge is not None:
        m['outcome'] = str((bridge.get('outcome') or {}).get('status'))
    else:
        m['outcome'] = None
    return m


def _fmt(v):
    if v is None:
        return '-'
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def _delta(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool):
        d = b - a
        if isinstance(d, float):
            pct = f" ({100.0 * d / a:+.0f}%)" if a else ''
            return f"{d:+.1f}{pct}"
        return f"{d:+d}"
    return ''


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('runs', nargs='+')
    ap.add_argument('--json', help='write every run\'s metrics to this file')
    a = ap.parse_args(argv)
    ms = [metrics(_find_run_dir(r)) for r in a.runs]
    keys = list(ms[0].keys())
    width = max(len(k) for k in keys)
    cols = [max([12] + [len(_fmt(m[k])) for k in keys]) for m in ms]
    head ='metric'.ljust(width) + ''.join(f"  {m['run'][-19:]:>{c}}" for m, c in zip(ms, cols))
    if len(ms) > 1:
        head += '  ' + 'last vs first'
    print(head)
    for k in keys:
        if k == 'run':
            continue
        line = k.ljust(width) + ''.join(f"  {_fmt(m.get(k)):>{c}}" for m, c in zip(ms, cols))
        if len(ms) > 1:
            line += '  ' + _delta(ms[0].get(k), ms[-1].get(k))
        print(line)
    if a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump([dict(m) for m in ms], f, indent=1)
        print(f"written {a.json}")


if __name__ == '__main__':
    main()
