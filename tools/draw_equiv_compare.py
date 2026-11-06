"""BF#68 check: two bridge runs made with tools/draw_equiv_run.py (one with
`--draw boxels`, one without; or two without, for the baseline), compared
record for record.

  python tools/draw_equiv_compare.py RUN_A RUN_B [--label-a NAME --label-b NAME]

A RUN is the --out directory of draw_equiv_run.py.  Compared, each as its own
verdict line (exit code 0 iff every line is SAME):
  plans      the ledger's plan rows (goal, targets, the planned actions)
  steps      the step and step_end rows (every dispatched action and how it
             ended)
  ledger     every ledger row except the two timing rows, times, pids and
             object addresses removed (this holds the sense results, place
             targets, the at-home tests, the readbacks, the gate counts and
             the executing world's body count at install and at the end)
  eye        the world eye's records (eye.jsonl: every body's true pose at
             every snapshot, what the camera sees)
  episode    bridge_episode.json: outcome, rewards, the terminal observation,
             the gate record (timings and paths removed)
  renders    every TinyRenderer getCameraImage call (each observation: the
             eye, the wrist, the settle check): client, size, view,
             projection and the rgb, depth and segmentation hashes, in order
  gl panes   the hardware-renderer calls that only refresh the GUI's own
             panes (boxel_env.py:1805, 1834; nothing reads their image):
             reported as SAME or info, never judged
  final      the global RNG states, the bodies of every client and the exit
             code, after the driver ended
Prints each run's debug-line counts (what drawing added) beside them."""
import argparse
import glob
import gzip
import json
import os
import re
import sys

SKIP_KINDS = {'driver_clock', 'bridge_timing'}
# Left out of every comparison, and why: clocks and durations (t, wall,
# t_wall, any key ending _s), process and object identity (pid, plan_obj, the
# @address in a trajectory's name), the run's own paths, and plan_actions of an
# eye record, which carries a plan's whole action list (see plan_split).
VOLATILE_KEYS = {'t', 'wall', 't_wall', 'pid', 'plan_obj', 'run_dir',
                 'time_deltas', 'driver', 'save_dir', 'plan_actions'}
ADDR = re.compile(r'@\d+')


def _volatile(key):
    return key in VOLATILE_KEYS or key.endswith('_s')


def plan_split(ledger):
    """A plan's tail is the part its run never dispatched.  Which tail the
    planner returns depends on its wall-clock budgets (the same seed gives
    12 steps in one run and 11 in the next, with the same first two steps
    executed), so a plan is judged on the steps its run took from it, and the
    tails are reported beside, never judged.  Returns (ledger with every plan
    row cut to its executed prefix, the tails by plan id)."""
    taken = {}
    for r in ledger:
        if r.get('kind') == 'step':
            taken[r['plan']] = max(taken.get(r['plan'], 0), r['step'])
    out, tails = [], {}
    for r in ledger:
        if r.get('kind') == 'plan':
            n = taken.get(r.get('plan_id'), 0)
            acts = r.get('actions') or []
            tails[r.get('plan_id')] = acts[n:]
            r = dict(r, actions=acts[:n])
        out.append(r)
    return out, tails


def _open(path):
    return (gzip.open(path, 'rt', encoding='utf-8') if path.endswith('.gz')
            else open(path, 'r', encoding='utf-8'))


def _first(pattern):
    hits = sorted(glob.glob(pattern) + glob.glob(pattern + '.gz'))
    return hits[0] if hits else None


def _jsonl(path):
    if not path:
        return []
    with _open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _clean(x):
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items() if not _volatile(k)}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, str):
        return ADDR.sub('@N', x)
    return x


def load(run):
    ep = os.path.join(run, 'ep')
    out = {'run': run}
    with open(os.path.join(ep, 'bridge_episode.json'), 'r', encoding='utf-8') as f:
        out['episode'] = _clean(json.load(f))
    # the gate table's detail texts carry timings ("0.582 s"); its verdicts
    # (gate and PASS or FAIL) are what is compared
    out['episode']['ledger_gates'] = [r[:2] for r in
                                      out['episode'].get('ledger_gates') or []]
    ledger =_first(os.path.join(ep, 'ours', 'run_*', 'ledger.jsonl'))
    eye = _first(os.path.join(ep, 'ours', 'run_*', 'eye.jsonl'))
    out['ledger_path'] = ledger
    out['ledger'], out['tails'] = plan_split(
        [_clean(r) for r in _jsonl(ledger) if r.get('kind') not in SKIP_KINDS])
    # an eye record's tag names the plan's length ("planned (12 actions)",
    # "before action 2/12 ..."), a tail-dependent number (plan_split)
    out['eye'] = [_clean(dict(r, tag=re.sub(r'\(\d+ actions\)|(?<=action \d)/\d+|'
                                            r'(?<=action \d\d)/\d+', '/N', r.get('tag', ''))))
                  for r in _jsonl(eye)]
    out['renders'] = _jsonl(os.path.join(run, 'render_hashes.jsonl'))
    with open(os.path.join(run, 'probe_final.json'), 'r', encoding='utf-8') as f:
        out['final'] = json.load(f)
    return out


def _diff_rows(a, b, show=3):
    """(equal, text) for two lists of rows, the first differences named."""
    if a == b:
        return True, f"{len(a)} rows"
    notes = [f"{len(a)} rows against {len(b)}"]
    shown = 0
    for i in range(max(len(a), len(b))):
        ra = a[i] if i < len(a) else None
        rb = b[i] if i < len(b) else None
        if ra != rb:
            if isinstance(ra, dict) and isinstance(rb, dict):
                # the keys that differ, each with both values
                keys = [k for k in sorted(set(ra) | set(rb)) if ra.get(k) != rb.get(k)]
                notes.append(f"row {i} ({ra.get('kind', ra.get('tag', '?'))}) differs in "
                             + '; '.join(
                                 f"{k}: {json.dumps(ra.get(k), sort_keys=True)[:140]}"
                                 f"  <>  {json.dumps(rb.get(k), sort_keys=True)[:140]}"
                                 for k in keys[:4]))
            else:
                notes.append(f"row {i}: {json.dumps(ra, sort_keys=True)[:200]}"
                             f"  <>  {json.dumps(rb, sort_keys=True)[:200]}")
            shown += 1
            if shown >= show:
                break
    return False, '; '.join(notes)


def compare(A, B):
    rows = []

    def add(name, equal, detail):
        rows.append((name, 'SAME' if equal else 'DIFF', detail))

    def kind(rs, *kinds):
        return [r for r in rs if r.get('kind') in kinds]

    add('plans', *_diff_rows(kind(A['ledger'], 'plan_call', 'plan'),
                             kind(B['ledger'], 'plan_call', 'plan')))
    # What the planner returned beyond the steps its run took: reported, not
    # judged (see plan_split); the same two runs without drawing differ here.
    ta, tb = A['tails'], B['tails']
    rows.append(('plan tails', 'SAME' if ta == tb else 'info',
                 f"{len(ta)} plans" if ta == tb else
                 'planned beyond the steps taken, per plan (A against B): '
                 + ', '.join(f"{k}: {len(ta.get(k, []))} vs {len(tb.get(k, []))}"
                             f"{'' if ta.get(k) == tb.get(k) else ' (differ)'}"
                             for k in sorted(set(ta) | set(tb)))))
    add('steps', *_diff_rows(kind(A['ledger'], 'step', 'step_end'),
                             kind(B['ledger'], 'step', 'step_end')))
    add('ledger', *_diff_rows(A['ledger'], B['ledger']))
    add('eye', *_diff_rows(A['eye'], B['eye']))
    ea, eb = A['episode'], B['episode']
    keys = sorted(set(ea) | set(eb))
    differing = [k for k in keys if ea.get(k) != eb.get(k)]
    add('episode', not differing,
        f"{len(keys)} fields" if not differing else
        'differing: ' + '; '.join(
            f"{k}: {json.dumps(ea.get(k), sort_keys=True)[:200]} <> "
            f"{json.dumps(eb.get(k), sort_keys=True)[:200]}" for k in differing[:3]))
    tiny = lambda R: [r for r in R['renders'] if r.get('tiny')]
    pane = lambda R: [r for r in R['renders'] if not r.get('tiny')]
    add('renders', *_diff_rows(tiny(A), tiny(B)))
    # The hardware renderer only refreshes the GUI's own panes (nothing reads
    # its image); a difference there is reported, not judged.
    same, text = _diff_rows(pane(A), pane(B))
    rows.append(('gl panes', 'SAME' if same else 'info', text))
    fa ={k: v for k, v in A['final'].items() if k != 'debug_calls'}
    fb = {k: v for k, v in B['final'].items() if k != 'debug_calls'}
    add('final', fa == fb,
        'RNG states, bodies per client, exit code' if fa == fb else
        f"{json.dumps(fa, sort_keys=True)[:300]} <> {json.dumps(fb, sort_keys=True)[:300]}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run_a')
    ap.add_argument('run_b')
    ap.add_argument('--label-a', default='A')
    ap.add_argument('--label-b', default='B')
    a = ap.parse_args()
    A, B = load(a.run_a), load(a.run_b)
    rows = compare(A, B)
    print(f"{a.label_a}: {a.run_a}\n{a.label_b}: {a.run_b}")
    for name, status, detail in rows:
        print(f"{name:<9} {status:<5} {detail}")
    for label, R in ((a.label_a, A), (a.label_b, B)):
        pl = [r for r in R['ledger'] if r.get('kind') == 'plan']
        st = [r for r in R['ledger'] if r.get('kind') == 'step']
        out = R['episode'].get('outcome', {})
        print(f"{label}: {len(pl)} plans, {len(st)} steps, {len(R['renders'])} renders, "
              f"outcome {out.get('status')}, rewards {R['episode'].get('rewards')}, "
              f"debug calls {R['final'].get('debug_calls')}, "
              f"bodies {R['final'].get('clients')}"[:400])
    return 0 if all(s in ('SAME', 'info') for _, s, _ in rows) else 1


if __name__ == '__main__':
    sys.exit(main())
