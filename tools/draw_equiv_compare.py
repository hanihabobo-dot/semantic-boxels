"""BF#68 check: two bridge runs made with tools/draw_equiv_run.py (one with
`--draw boxels`, one without; or two without, as the control), compared record
for record.

  python tools/draw_equiv_compare.py RUN_A RUN_B --drawing none|a|b
                                     [--label-a NAME --label-b NAME]

A RUN is the --out directory of draw_equiv_run.py.  Exit code 0 iff no line is
DIFF or FAIL.

Why the comparison has two modes.  PDDLStream decides with wall clocks (its
search/sample time ratio, max_time), so the planner can return another plan on
IDENTICAL inputs when a run is slower or faster than the other, drawing or not
(seed 0 on a loaded machine: the same plan call took 25 s in one run and 46 s
in the next and picked another kin configuration).  After that point two runs
take different actions and nothing downstream is comparable.  So:

  * the two ledgers equal (plan tails aside): every stream is compared whole,
    each as its own verdict line (plans, steps, ledger, eye, episode, renders,
    final);
  * they differ: the first differing ledger row is located and classified.
    A planner row (the plan it returned, or a render the plan twin made inside
    a solve) with everything before it identical is `planner`: noise, judged
    nothing.  Anything else (a step, a sense result, an executing-client
    render, a row's inputs) is `world`: DIFF.  Every stream is then compared
    up to that point (the ledger rows before it, the eye records of the plans
    before it, every render whose ledger row lies before it), and the streams
    that do not depend on the plan are still judged whole: the gate counts,
    the bodies and body ids of every client.  The global RNG states are judged
    whole when the two planners ran the same RRT-Connect searches, and only
    then: RRT-Connect (streams.py: _random_config, the goal bias, the shortcut
    smoothing) draws from the global numpy and random generators, so a planner
    that went round a blocked path by search in one run and by a direct move
    in the other leaves another state behind (seed 106: 1 search in 3 runs,
    the same final state in all three; 0 searches in the fourth, another one).

Lines, as the verdict names them:
  floor      both runs have a ledger, eye records and renders (a missing file
             would otherwise compare as 0 rows SAME)
  inputs     what the planner's first problem is made of, byte for byte:
             problem_initial.pddl, the registry the run started from
             (boxel_data.json), the domain it loaded
  diverge    none, planner (info) or world (DIFF); the planner's solve times
  plans      the ledger's plan_call and plan rows (goal, targets, the planned
             actions cut to what the run dispatched, see plan_split)
  steps      the step and step_end rows (every dispatched action and its end)
  ledger     every ledger row except two timing rows, times, pids and object
             addresses removed (sense results, place targets, at-home tests,
             readbacks, gate counts, body counts at install and at the end)
  eye        the world eye's records (eye.jsonl: every body's true pose at
             every snapshot)
  episode    bridge_episode.json: outcome, rewards, the terminal observation,
             the gate record; with a divergence only the gate record, the
             readback check, the settle and the switches are judged
  renders    every TinyRenderer getCameraImage call (each observation: the eye,
             the wrist, the settle check, the plan twin's tests): client, size,
             view, projection and the rgb, depth and segmentation hashes
  gl panes   the hardware-renderer calls: the first is TAMPURA's own image for
             its initial belief (taken in env.initialize, before anything is
             drawn); the others refresh the GUI's panes (boxel_env.py:1805,
             1834) and nothing reads them.  The hardware renderer does draw
             debug lines, so a difference there is reported, never judged
  gates      the violation counts of the gate record (judged), and the info
             counters (reported)
  final      the bodies of every client and the exit code, after the driver
             ended
  rng        the global RNG states after the driver ended: judged when both
             planners ran the same RRT-Connect searches (read from the run
             log), reported (info) when they ran different ones
  drew       --drawing (required) names the arm that drew (a, b) or none: the
             arm that should have drawn has more debug lines and labels than
             the other (the base issues no labels), and with none neither has
             a label; a pair in which nothing was drawn would otherwise
             compare SAME
Prints each run's debug-call counts beside them."""
import argparse
import glob
import gzip
import hashlib
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
PLAN_TAG = re.compile(r'plan#(\d+)')
# The lines streams.plan_motion logs (INFO unless noted): the query (DEBUG), the
# start of an RRT-Connect search, and how it ended.
RRT_QUERY = re.compile(r'streams: plan_motion: (\S+) -> (\S+)\s')
RRT_START = 'running RRT-Connect'
RRT_END = re.compile(r'streams: plan_motion: (RRT path \d+ wps -> smoothed \d+ wps|'
                     r'RRT-Connect failed \(\d+ iters\))')
RNG_KEYS = ('numpy_state', 'random_state')
# What of the episode record is judged when the runs took different plans (the
# gate record's counters follow the steps taken, so the `gates` and `bodies`
# lines judge its violation counts and body counts instead).
JUDGED_WITH_DIVERGENCE = ('readback_identical', 'scene_file', 'seed', 'settle',
                          'scene_changed_by_settle', 'switches', 'g13_runtime')
BAD = ('DIFF', 'FAIL')


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


def rrt_runs(log_path):
    """The RRT-Connect searches the planner ran, in order, read from the run
    log: (the motion query 'from -> to', how the search ended).  They matter
    because each search draws from the global RNG (see the module docstring);
    the same searches from the same state draw the same numbers."""
    runs, query = [], None
    opener = gzip.open if log_path.endswith('.gz') else open
    with opener(log_path, 'rt', encoding='utf-8', errors='replace') as f:
        for line in f:
            m = RRT_QUERY.search(line)
            if m:
                query = f"{m.group(1)} -> {m.group(2)}"
            elif RRT_START in line:
                runs.append([query, None])
            else:
                m = RRT_END.search(line)
                if m and runs and runs[-1][1] is None:
                    runs[-1][1] = m.group(1)
    return [tuple(r) for r in runs]


def _open(path):
    return (gzip.open(path, 'rt', encoding='utf-8') if path.endswith('.gz')
            else open(path, 'r', encoding='utf-8'))


def _newest(pattern):
    """The newest match of a glob (a run's folder name carries its start
    time), with a note when there is more than one: a run repeated into the
    same --out leaves the earlier run's folder beside it."""
    hits = sorted(glob.glob(pattern) + glob.glob(pattern + '.gz'))
    return (hits[-1] if hits else None), len(hits)


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


def align(renders, lrows):
    """Which harness render is which ledger `render` row.  The harness hashes
    every getCameraImage call (TAMPURA's own first image included, which
    precedes the gates); the ledger logs the calls from the moment the gates
    were installed, in the same order, on whichever client made them.  So the
    ledger's rows are a contiguous run of the harness's list, found by the
    sequence of client ids (the harness keeps hashes of the matrices, not the
    matrices, and the long 0, 0, 2, 2, 2 ... pattern does not fit anywhere
    else).  Returns (a list parallel to renders: the raw ledger index of its
    row, None where it has none; whether the two lists fit together)."""
    n, m = len(renders), len(lrows)
    lix = [None] * n
    if m == 0 or n < m:
        return lix, False
    clients = [l.get('client') for _, l in lrows]
    fits = [off for off in range(n - m + 1)
            if all(renders[off + j].get('client') == clients[j] for j in range(m))]
    if len(fits) != 1:
        return lix, False          # none, or ambiguous
    for j, (i, _) in enumerate(lrows):
        lix[fits[0] + j] = i
    return lix, True


def load(run):
    ep = os.path.join(run, 'ep')
    out = {'run': run, 'label': os.path.basename(run.rstrip('/\\')),
           'missing': [], 'notes': []}

    def read_json(path, what):
        if not os.path.exists(path):
            out['missing'].append(what)
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    out['episode'] = _clean(read_json(os.path.join(ep, 'bridge_episode.json'),
                                      'bridge_episode.json'))
    # the gate table's detail texts carry timings ("0.582 s"); its verdicts
    # (gate and PASS or FAIL) are what is compared
    out['episode']['ledger_gates'] = [r[:2] for r in
                                      out['episode'].get('ledger_gates') or []]
    out['final'] = read_json(os.path.join(run, 'probe_final.json'), 'probe_final.json')
    ledger, n = _newest(os.path.join(ep, 'ours', 'run_*', 'ledger.jsonl'))
    eye, _ = _newest(os.path.join(ep, 'ours', 'run_*', 'eye.jsonl'))
    # the planner's RRT-Connect searches, from the run log of the same folder
    # (None when there is no log to read: the RNG states are then judged)
    log = None
    if ledger:
        log, _ = _newest(os.path.join(os.path.dirname(ledger), 'run_*.log'))
    out['rrt'] = rrt_runs(log) if log else None
    if n > 1:
        out['notes'].append(f"{n} run folders under ep/ours: the newest is used")
    if not ledger:
        out['missing'].append('ledger.jsonl')
    if not eye:
        out['missing'].append('eye.jsonl')
    raw = _jsonl(ledger)
    out['raw'] = raw
    # What the planner was given for its first plan: the PDDL problem, the
    # registry the run started from, the domain it loaded (byte hashes).
    base = os.path.dirname(ledger) if ledger else None
    out['inputs'] = {}
    for rel in ('problem_initial.pddl', 'boxel_data.json', 'work/temp/domain.pddl'):
        path = os.path.join(base, *rel.split('/')) if base else None
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                out['inputs'][rel] = hashlib.sha256(f.read()).hexdigest()[:16]
    kept = [(i, r) for i, r in enumerate(raw) if r.get('kind') not in SKIP_KINDS]
    out['ledger'], out['tails'] = plan_split([_clean(r) for _, r in kept])
    out['raw_ix'] = [i for i, _ in kept]
    out['solve'] = {r.get('plan_id'): r.get('plan_time_s')
                    for r in raw if r.get('kind') == 'plan'}
    out['twin'] = {r.get('client') for r in raw
                   if r.get('kind') == 'gate_info' and r.get('note') == 'wrist_robot'}
    # an eye record's tag names the plan's length ("planned (12 actions)",
    # "before action 2/12 ..."), a tail-dependent number (plan_split)
    raw_eye = _jsonl(eye)
    out['eye'] = [_clean(dict(r, tag=re.sub(r'\(\d+ actions\)|(?<=action \d)/\d+|'
                                            r'(?<=action \d\d)/\d+', '/N', r.get('tag', ''))))
                  for r in raw_eye]
    plan_of, cur = [], 0
    for r in raw_eye:
        m = PLAN_TAG.search(r.get('tag', ''))
        if m:
            cur = int(m.group(1))
        plan_of.append(cur)
    out['eye_plan'] = plan_of
    out['renders'] = _jsonl(os.path.join(run, 'render_hashes.jsonl'))
    out['lix'], out['aligned'] = align(
        out['renders'], [(i, r) for i, r in enumerate(raw) if r.get('kind') == 'render'])
    if not out['renders']:
        out['missing'].append('render_hashes.jsonl')
    return out


def _row_note(i, ra, rb):
    """What differs in row i of two lists: the keys, each with both values."""
    if isinstance(ra, dict) and isinstance(rb, dict):
        keys = [k for k in sorted(set(ra) | set(rb)) if ra.get(k) != rb.get(k)]
        return (f"row {i} ({ra.get('kind', ra.get('tag', '?'))}) differs in "
                + '; '.join(f"{k}: {json.dumps(ra.get(k), sort_keys=True)[:140]}"
                            f"  <>  {json.dumps(rb.get(k), sort_keys=True)[:140]}"
                            for k in keys[:4]))
    return (f"row {i}: {json.dumps(ra, sort_keys=True)[:200]}"
            f"  <>  {json.dumps(rb, sort_keys=True)[:200]}")


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
            notes.append(_row_note(i, ra, rb))
            shown += 1
            if shown >= show:
                break
    return False, '; '.join(notes)


def first_difference(a, b):
    """Index of the first row at which two lists differ; None when equal."""
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def classify(A, B, D):
    """('planner' | 'world', text) for the first differing ledger row D."""
    ra = A['ledger'][D] if D < len(A['ledger']) else None
    rb = B['ledger'][D] if D < len(B['ledger']) else None
    twin = A['twin'] | B['twin']
    what = _row_note(D, ra, rb)
    if ra and rb and ra.get('kind') == rb.get('kind') == 'plan':
        return 'planner', f"{what}  [the planner's answer for plan {ra.get('plan_id')}]"
    if (ra and rb and ra.get('kind') == rb.get('kind') == 'render'
            and ra.get('client') in twin and rb.get('client') in twin):
        # a render the plan twin made: the planner's own sampling, when it
        # lies between a plan_call and the plan row that answers it
        for r in reversed(A['ledger'][:D]):
            if r.get('kind') in ('plan_call', 'plan'):
                if r.get('kind') == 'plan_call':
                    return 'planner', f"{what}  [a render of the plan twin inside a solve]"
                break
    return 'world', what


def compare(A, B, drawing=None):
    rows = []

    def add(name, status, detail):
        rows.append((name, status, detail))

    def same(name, equal, detail):
        add(name, 'SAME' if equal else 'DIFF', detail)

    def kind(rs, *kinds):
        return [r for r in rs if r.get('kind') in kinds]

    # --- floor: the runs have something to compare
    gone = [f"{R['label']}: {', '.join(R['missing'])}" for R in (A, B) if R['missing']]
    for R in (A, B):
        for field in ('ledger', 'eye', 'renders'):
            if not R['missing'] and not R[field]:
                gone.append(f"{R['label']}: no {field} rows")
    if gone:
        add('floor', 'FAIL', '; '.join(gone))
        return rows
    add('floor', 'SAME', f"ledger {len(A['ledger'])}/{len(B['ledger'])} rows, eye "
        f"{len(A['eye'])}/{len(B['eye'])}, renders {len(A['renders'])}/{len(B['renders'])}")
    for R in (A, B):
        for note in R['notes']:
            add('note', 'info', f"{R['label']}: {note}")

    # inputs: the files the planner's first problem is made of, byte for byte
    both = sorted(set(A['inputs']) & set(B['inputs']))
    if both:
        bad = [k for k in both if A['inputs'][k] != B['inputs'][k]]
        add('inputs', 'DIFF' if bad else 'SAME',
            ('differ: ' + ', '.join(bad)) if bad else
            'byte-identical: ' + ', '.join(f"{k} ({A['inputs'][k]})" for k in both))
    else:
        add('inputs', 'info', 'no planner input files recorded in both runs')

    D = first_difference(A['ledger'], B['ledger'])
    la, lb = A['ledger'], B['ledger']
    ea, eb = A['episode'], B['episode']
    solve = ', '.join(
        f"plan {k}: {A['solve'].get(k, 0) or 0:.1f} s / {B['solve'].get(k, 0) or 0:.1f} s"
        for k in sorted(set(A['solve']) | set(B['solve']), key=lambda x: (x is None, x)))

    if D is None:
        add('diverge', 'SAME', 'none: the ledgers agree (plan tails aside)')
        same('plans', *_diff_rows(kind(la, 'plan_call', 'plan'), kind(lb, 'plan_call', 'plan')))
        steps = _diff_rows(kind(la, 'step', 'step_end'), kind(lb, 'step', 'step_end'))
        same('steps', *steps)
        same('ledger', *_diff_rows(la, lb))
        same('eye', *_diff_rows(A['eye'], B['eye']))
        differing = [k for k in sorted(set(ea) | set(eb)) if ea.get(k) != eb.get(k)]
        same('episode', not differing,
             f"{len(set(ea) | set(eb))} fields" if not differing else
             'differing: ' + '; '.join(
                 f"{k}: {json.dumps(ea.get(k), sort_keys=True)[:200]} <> "
                 f"{json.dumps(eb.get(k), sort_keys=True)[:200]}" for k in differing[:3]))
        tiny = lambda R: [r for r in R['renders'] if r.get('tiny')]
        same('renders', *_diff_rows(tiny(A), tiny(B)))
    else:
        verdict, text = classify(A, B, D)
        rD = A['raw_ix'][D] if D < len(A['raw_ix']) else None
        if verdict == 'planner':
            add('diverge', 'info', f"planner on identical inputs: rows 0 to {D - 1} "
                f"agree, then {text}")
            add('solve', 'info', f"planner time per plan, A / B: {solve}")
        else:
            add('diverge', 'DIFF', f"the executing world differs: {text}")
        # the first plan whose solve diverged: the eye records of the plans
        # before it are compared
        P = 1 + sum(1 for r in la[:D] if r.get('kind') == 'plan')
        pre_a, pre_b = la[:D], lb[:D]
        same('plans', *_diff_rows(kind(pre_a, 'plan_call', 'plan'),
                                  kind(pre_b, 'plan_call', 'plan')))
        same('steps', *_diff_rows(kind(pre_a, 'step', 'step_end'),
                                  kind(pre_b, 'step', 'step_end')))
        same('ledger', *_diff_rows(pre_a, pre_b))
        ey = lambda R: [r for r, p in zip(R['eye'], R['eye_plan']) if p < P]
        eq, text_e = _diff_rows(ey(A), ey(B))
        de = first_difference(A['eye'], B['eye'])
        late = (f"; the first differing record is no. {de} (plan {A['eye_plan'][de]}: "
                f"{A['eye'][de].get('tag')})" if de is not None and de < len(A['eye'])
                else '')
        same('eye', eq, f"the records of plans before plan {P}: {text_e}{late}")
        # renders: those whose ledger row lies before the divergence
        if A['aligned'] and B['aligned'] and rD is not None:
            def prefix(R):
                for k, ix in enumerate(R['lix']):
                    if ix is not None and ix >= rD:
                        return R['renders'][:k]
                return R['renders']
            pa, pb = prefix(A), prefix(B)
            same('renders', *_diff_rows([r for r in pa if r.get('tiny')],
                                        [r for r in pb if r.get('tiny')]))
            dr = first_difference(A['renders'], B['renders'])
            if dr is not None and dr < len(A['renders']):
                ra = A['renders'][dr]
                add('first render difference', 'info',
                    f"harness render {dr} (client {ra.get('client')}, "
                    f"{'tiny' if ra.get('tiny') else 'hardware'}), "
                    f"{'after' if (A['lix'][dr] or 0) >= (rD or 0) else 'BEFORE'} the divergence")
        else:
            add('renders', 'info', 'the harness renders could not be matched to the '
                'ledger: first difference at harness render '
                f"{first_difference(A['renders'], B['renders'])}")
        # what the runs did after it: reported
        sa, sb = len(kind(la, 'step')), len(kind(lb, 'step'))
        add('after', 'info',
            f"A {sa} steps, outcome {ea.get('outcome', {}).get('status')}; "
            f"B {sb} steps, outcome {eb.get('outcome', {}).get('status')}")
        judged = [k for k in JUDGED_WITH_DIVERGENCE if ea.get(k) != eb.get(k)]
        same('episode', not judged,
             f"{len(JUDGED_WITH_DIVERGENCE)} fields judged (the plan-dependent ones are not)"
             if not judged else 'differing: ' + '; '.join(
                 f"{k}: {json.dumps(ea.get(k), sort_keys=True)[:200]} <> "
                 f"{json.dumps(eb.get(k), sort_keys=True)[:200]}" for k in judged[:3]))
    # What the planner returned beyond the steps its run took: reported, not
    # judged (see plan_split); the same two runs without drawing differ here.
    ta, tb = A['tails'], B['tails']
    add('plan tails', 'SAME' if ta == tb else 'info',
        f"{len(ta)} plans" if ta == tb else
        'planned beyond the steps taken, per plan (A against B): '
        + ', '.join(f"{k}: {len(ta.get(k, []))} vs {len(tb.get(k, []))}"
                    f"{'' if ta.get(k) == tb.get(k) else ' (differ)'}"
                    for k in sorted(set(ta) | set(tb), key=lambda x: (x is None, x))))
    pane = lambda R: [r for r in R['renders'] if not r.get('tiny')]
    ok, text = _diff_rows(pane(A), pane(B))
    add('gl panes', 'SAME' if ok else 'info', text)
    # gates: the violation counts are judged, the info counters reported
    ga, gb = ea.get('gates') or {}, eb.get('gates') or {}
    same('gates', ga.get('counts') == gb.get('counts'),
         f"violations A {json.dumps(ga.get('counts'))}, B {json.dumps(gb.get('counts'))}")
    ia, ib = ga.get('info') or {}, gb.get('info') or {}
    body_keys = ('executing_bodies_at_install', 'executing_bodies_now')
    same('bodies', all(ia.get(k) == ib.get(k) for k in body_keys),
         ', '.join(f"{k} {ia.get(k)}/{ib.get(k)}" for k in body_keys))
    skipped = ('debug_calls', 'renders') + RNG_KEYS
    fa = {k: v for k, v in A['final'].items() if k not in skipped}
    fb = {k: v for k, v in B['final'].items() if k not in skipped}
    same('final', fa == fb,
         'bodies and ids per client, exit code' if fa == fb else
         f"{json.dumps(fa, sort_keys=True)[:300]} <> {json.dumps(fb, sort_keys=True)[:300]}")
    # rng: the global RNG states.  The planner's RRT-Connect searches draw from
    # them, so they are judged only between runs whose planners searched alike.
    rrt_a, rrt_b = A.get('rrt'), B.get('rrt')
    rng_a = tuple(A['final'].get(k) for k in RNG_KEYS)
    rng_b = tuple(B['final'].get(k) for k in RNG_KEYS)
    searches = lambda rs: ('none' if not rs else
                           '; '.join(f"{q} ({e})" for q, e in rs))
    if rrt_a is None or rrt_b is None or rrt_a == rrt_b:
        known = ('RRT-Connect searches, both runs: ' + searches(rrt_a)
                 if rrt_a is not None and rrt_b is not None else
                 "no run log in both runs: the planners' searches were not compared")
        same('rng', rng_a == rng_b,
             f"numpy and random states equal after the same planner searches ({known})"
             if rng_a == rng_b else
             f"{json.dumps(rng_a)[:200]} <> {json.dumps(rng_b)[:200]} ({known})")
    elif rng_a == rng_b:
        add('rng', 'SAME', 'numpy and random states equal although the planners '
            f"searched differently (A: {searches(rrt_a)}; B: {searches(rrt_b)})")
    else:
        add('rng', 'info', "the states differ and so do the planners' RRT-Connect "
            f"searches, which draw from them (A: {searches(rrt_a)}; B: "
            f"{searches(rrt_b)}): the planner's own answer, not judged")
    # drew: a pair in which nothing was drawn must not pass as a pair
    dca, dcb = A['final'].get('debug_calls') or {}, B['final'].get('debug_calls') or {}
    if drawing in ('a', 'b'):
        d, o, dn, on = (dca, dcb, 'A', 'B') if drawing == 'a' else (dcb, dca, 'B', 'A')
        ok = (d.get('text', 0) > o.get('text', 0)) and (d.get('line', 0) > o.get('line', 0))
        add('drew', 'ok' if ok else 'FAIL',
            f"{dn} has {d.get('line')} lines and {d.get('text')} labels against "
            f"{on}'s {o.get('line')} and {o.get('text')}"
            + ('' if ok else ': the arm that should draw did not'))
    elif drawing == 'none':
        ok = dca.get('text', 0) == 0 and dcb.get('text', 0) == 0
        add('drew', 'ok' if ok else 'FAIL',
            f"labels A {dca.get('text')}, B {dcb.get('text')} (both 0: nobody drew)")
    else:
        add('drew', 'info', 'not checked (--drawing none|a|b not given)')
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run_a')
    ap.add_argument('run_b')
    ap.add_argument('--label-a', default='A')
    ap.add_argument('--label-b', default='B')
    # required: a pair in which nothing was drawn must not pass as a pair
    ap.add_argument('--drawing', choices=('none', 'a', 'b'), required=True,
                    help='which run drew (a, b), or none of them')
    a = ap.parse_args()
    A, B = load(a.run_a), load(a.run_b)
    A['label'], B['label'] = a.label_a, a.label_b
    rows = compare(A, B, a.drawing)
    print(f"{a.label_a}: {a.run_a}\n{a.label_b}: {a.run_b}")
    for name, status, detail in rows:
        print(f"{name:<12} {status:<5} {detail}")
    for label, R in ((a.label_a, A), (a.label_b, B)):
        if R['missing']:
            continue
        pl = [r for r in R['ledger'] if r.get('kind') == 'plan']
        st = [r for r in R['ledger'] if r.get('kind') == 'step']
        out = R['episode'].get('outcome', {})
        rrt = R.get('rrt')
        print(f"{label}: {len(pl)} plans, {len(st)} steps, {len(R['renders'])} renders, "
              f"outcome {out.get('status')}, rewards {len(R['episode'].get('rewards') or [])}, "
              f"RRT-Connect searches {'n/a' if rrt is None else len(rrt)}, "
              f"debug calls {R['final'].get('debug_calls')}, "
              f"bodies {R['final'].get('clients')}"[:400])
    bad = [n for n, s, _ in rows if s in BAD]
    diverge = [s for n, s, _ in rows if n == 'diverge']
    if bad:
        print(f"RESULT: DIFFERENT ({', '.join(bad)})")
    elif diverge == ['info']:
        print("RESULT: identical until the planner's own answer differed on identical "
              "inputs; nothing else differs (info lines are reported, not judged)")
    else:
        print("RESULT: SAME")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
