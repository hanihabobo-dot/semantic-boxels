"""Path 6: tools/p6_report.py, the phase 1a report.  Synthetic job folders in the
layout tools/cluster/p6_tabletop.sbatch leaves (header.txt, io_probe.tsv, A/ and B/
with slot_N/cells/<tag>/{timing_summary.json, stdout.log, run_dir.txt}).

Pinned here: the statistics (Wilson, Newcombe, Fisher, McNemar against known
values), the validity rule (what counts, what does not, B's re-rolled seed), the
timeout label rule, the first attempt that counts, the pooled A against B numbers,
B against the thesis sweep paired on the seed actually run, the stall rule, the
final pass list, targets.json and the merged sweep folders."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'tools'))
import p6_report as pr  # noqa: E402
import p6_slots as ps  # noqa: E402


# ---------------------------------------------------------------------------
# statistics against known values
# ---------------------------------------------------------------------------

def test_wilson():
    lo, hi = pr.wilson(40, 60)
    assert 0.53 < lo < 0.55 and 0.77 < hi < 0.79
    assert pr.wilson(0, 10)[0] == 0.0 and pr.wilson(10, 10)[1] == 1.0


def test_newcombe_matches_the_papers_example():
    d, lo, hi = pr.newcombe(56, 70, 48, 80)          # Newcombe 1998, example 1 (method 10)
    assert abs(d - 0.2) < 1e-9 and abs(lo - 0.0524) < 0.002 and abs(hi - 0.3339) < 0.002


def test_fisher_exact():
    assert abs(pr.fisher_exact(3, 4, 1, 4) - 0.4857142857) < 1e-9     # the tea-tasting table
    assert abs(pr.fisher_exact(8, 10, 1, 6) - 0.0350) < 0.002          # [[8, 2], [1, 5]]
    assert pr.fisher_exact(5, 10, 5, 10) == 1.0
    assert pr.fisher_exact(0, 5, 0, 5) == 1.0


def test_mcnemar_exact():
    assert pr.mcnemar_exact(0, 0) == 1.0
    assert abs(pr.mcnemar_exact(10, 0) - 2 / 2 ** 10) < 1e-12
    assert pr.mcnemar_exact(3, 3) == 1.0


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

def pipeline_summary(cell, success, reason=None, wall=30.0, seed=None, plan_time=5.0):
    rc = {'scene': cell['scene'], 'seed': cell['seed'] if seed is None else seed, 'goal': cell['goal'],
          'baseline': 'semantic', 'unit_costs': False,
          'n_occluders': cell['n_occluders'] if cell['scene'] == 'random-pairs' else 0,
          'stack_height': cell['n_occluders']}
    return {'run_config': rc, 'success': success, 'exit_reason': reason, 'plan_count': 2,
            'total_planning_time_s': plan_time, 'wall_clock_s': wall,
            'boxel_counts_per_replan': [{'plan_index': 1, 'n_object_boxels': 2, 'n_shadow_boxels': 2,
                                         'n_free_space_boxels': 13}]}


def stub(cell, reason, wall=12.0, **extra):
    return dict({k: cell[k] for k in ('scene', 'n_occluders', 'seed', 'goal', 'baseline', 'unit_costs')},
                success=False, exit_reason=reason, wall_clock_s=wall, **extra)


def put(job, arm, label, cell, ts, stdout='', run_dir=None, mtime=None):
    d = job / arm / label / 'cells' / ps.expected_tag(cell)
    d.mkdir(parents=True, exist_ok=True)
    if ts is not None:
        (d / 'timing_summary.json').write_text(json.dumps(ts))
        if mtime is not None:
            os.utime(d / 'timing_summary.json', (mtime, mtime))
    if stdout is not None:
        (d / 'stdout.log').write_text(stdout)
    elif (d / 'stdout.log').exists():
        (d / 'stdout.log').unlink()                 # None models a cell that has no stdout.log
    if run_dir:
        (d / 'run_dir.txt').write_text(run_dir)


def make_job(root, name, header='host node-a  job 1  now  mode 0  A sb_a  B sb_b  cap 1800s  out x\n'
                                 'cpu Xeon  threads 96\n'
                                 'snapshot A sb_a: 251 files, tree hash aaaa\nsnapshot B sb_b: 47 files, tree hash bbbb\n'):
    job = root / name
    job.mkdir(parents=True)
    (job / 'header.txt').write_text(header)
    return job


def cell_of(arm, goal, difficulty, slot=0):
    for c in ps.slot_cells(arm, slot):
        if c['goal'] == goal and c['n_occluders'] == difficulty:
            return c
    raise KeyError((arm, goal, difficulty, slot))


def classify_one(arm, cell, ts, stdout='', cap=1800, job_void=None):
    att = {'arm': arm, 'tag': ps.expected_tag(cell), 'job': 'j', 'label': 'slot_0', 'redo': False,
           'void': job_void, 'ts': ts, 'stdout': stdout, 'run_dir': None, 'mtime': None}
    return pr.classify(att, cell, cap)


# ---------------------------------------------------------------------------
# the validity rule and the labels
# ---------------------------------------------------------------------------

def test_success_and_failure_labels():
    cell = cell_of('A', 'holding', 2)
    assert classify_one('A', cell, pipeline_summary(cell, True))['status'] == 'success'
    for reason, label in (('planner_failed', 'no plan found'), ('all_searched', 'search exhausted'),
                          ('physics_mismatch', 'false success (physics mismatch)'),
                          ('pick_giveup', 'pick given up'), ('something_new', 'something_new')):
        c = classify_one('A', cell, pipeline_summary(cell, False, reason))
        assert (c['status'], c['failure']) == ('failure', label)


def test_timeout_label_rule():
    stack_b = cell_of('B', 'stack', 4)
    rp_a = cell_of('A', 'holding', 3)
    # a runner stub at the cap is the only plain timeout
    c = classify_one('B', stack_b, stub(stack_b, 'timeout', wall=1800.4))
    assert (c['status'], c['failure']) == ('timeout', 'timed out at the cap')
    # a pipeline row labelled timeout after 12 s on B's stack: a false success rejected at the end (CB#122)
    c = classify_one('B', stack_b, pipeline_summary(stack_b, False, 'timeout', wall=12.0))
    assert (c['status'], c['failure']) == ('failure', 'false success rejected at the end (CB#122)')
    # the same on arm A, or on another goal: no give-up reason, to check
    c = classify_one('A', rp_a, pipeline_summary(rp_a, False, 'timeout', wall=300.0))
    assert c['failure'] == 'no give-up reason (to check)'
    c = classify_one('A', cell_of('A', 'stack', 2), pipeline_summary(cell_of('A', 'stack', 2), False, 'timeout', wall=12.0))
    assert c['failure'] == 'no give-up reason (to check)'
    # a pipeline row labelled timeout that ran to the cap is a timeout
    c = classify_one('A', rp_a, pipeline_summary(rp_a, False, 'timeout', wall=1795.0))
    assert c['failure'] == 'timed out at the cap'


def test_what_does_not_count():
    cell = cell_of('A', 'find-and-tray-stack', 2)
    assert classify_one('A', cell, stub(cell, 'crash_exit139'))['status'] == 'crash'
    assert classify_one('A', cell, stub(cell, 'no_summary'))['status'] == 'no_summary'
    assert classify_one('A', cell, stub(cell, 'summary_mismatch', summary_mismatch='goal=...'))['status'] == 'summary_mismatch'
    assert classify_one('A', cell, stub(cell, 'preflight_rejected', preflight_message='[pre-flight] seed 5 rejected: x'))['status'] == 'preflight_rejected'
    # a no_summary stub whose output shows the rejection is a pre-flight rejection too
    c = classify_one('A', cell, stub(cell, 'no_summary'), stdout='...\n[pre-flight] seed 5 rejected: no hidden target\n')
    assert c['status'] == 'preflight_rejected'
    assert classify_one('A', cell, None)['status'] == 'missing'
    assert classify_one('A', cell, pipeline_summary(cell, True), job_void='tree check failed')['status'] == 'void'
    for bad in (dict(goal='holding'), dict(scene='stack')):           # another cell's summary
        ts = pipeline_summary(cell, True)
        ts['run_config'].update(bad)
        assert classify_one('A', cell, ts)['status'] == 'summary_mismatch'
    ts = pipeline_summary(cell, True)
    ts['run_config']['n_occluders'] = 3                                  # the neighbouring difficulty
    assert classify_one('A', cell, ts)['status'] == 'summary_mismatch'
    stack = cell_of('A', 'stack', 3)
    ts = pipeline_summary(stack, True)
    ts['run_config']['stack_height'] = 4
    assert classify_one('A', stack, ts)['status'] == 'summary_mismatch'


def test_a_changed_seed_counts_only_for_b_with_the_reroll_in_its_output():
    cell = cell_of('B', 'find-and-tray-stack', 4)
    ts = pipeline_summary(cell, True, seed=777)
    out = '[retry 1/10] placement failed (x); rerolling to seed=555\n[retry 2/10] placement failed (y); rerolling to seed=777\n'
    c = classify_one('B', cell, ts, stdout=out)
    # the replacement scene is never the cell's result (15 Nov): its own run is kept as an extra number
    assert (c['status'], c['rerolled'], c['eff_seed'], c['rerolled_success']) == ('rerolled', True, 777, True)
    assert c['success'] is False and not pr.in_set(c['status'])
    # the chain must end in the seed that ran
    assert classify_one('B', cell, pipeline_summary(cell, True, seed=555), stdout=out)['status'] == 'summary_mismatch'
    assert classify_one('B', cell, ts, stdout='')['status'] == 'summary_mismatch'
    # arm A has no re-roll: a changed seed is another cell's summary
    cell_a = cell_of('A', 'find-and-tray-stack', 4)
    assert classify_one('A', cell_a, pipeline_summary(cell_a, True, seed=777), stdout=out)['status'] == 'summary_mismatch'


def attempt_of(cell, ts, job='job00', label='slot_0', redo=False, void=None, arm='A'):
    return {'arm': arm, 'tag': ps.expected_tag(cell), 'job': job, 'label': label, 'redo': redo, 'void': void,
            'ts': ts, 'stdout': '', 'run_dir': None, 'mtime': None}


def test_the_first_real_attempt_is_the_cell_and_a_rerun_never_counts():
    cell = cell_of('A', 'holding', 2)
    attempts = [attempt_of(cell, stub(cell, 'crash_exit1')),
                attempt_of(cell, pipeline_summary(cell, True), job='redo_9', label='redo_1', redo=True)]
    rec = pr.final_cells(attempts)['A'][ps.expected_tag(cell)]
    assert [a['status'] for a in rec['attempts']] == ['crash', 'success']
    assert rec['final']['status'] == 'crash' and not rec['final']['success']      # the crash is the result: a failure
    assert [r['status'] for r in rec['reruns']] == ['success']                       # listed, never counted
    # a cell that never started (a missing summary, a void job) is skipped: the next attempt is its first
    first = [attempt_of(cell, None), attempt_of(cell, pipeline_summary(cell, True), job='redo_9', label='redo_1', redo=True)]
    rec = pr.final_cells(first)['A'][ps.expected_tag(cell)]
    assert rec['final']['status'] == 'success' and rec['reruns'] == []
    voided = pr.final_cells([attempt_of(cell, pipeline_summary(cell, True), void='tree check failed')])['A'][ps.expected_tag(cell)]
    assert voided['final']['status'] == 'void' and not pr.in_set('void')
    # a pre-flight rejection is final: nothing re-runs it
    cell2 = cell_of('A', 'find-and-tray-stack', 2)
    rej = [attempt_of(cell2, stub(cell2, 'preflight_rejected', preflight_message='x'))]
    assert pr.final_cells(rej)['A'][ps.expected_tag(cell2)]['final']['status'] == 'preflight_rejected'
    assert pr.final_cells([])['A'][ps.expected_tag(cell)]['final'] is None


def test_what_is_in_the_set(monkeypatch):
    for s in ('success', 'failure', 'timeout', 'crash', 'no_summary', 'summary_mismatch'):
        assert pr.in_set(s)
    for s in ('preflight_rejected', 'rerolled', 'void', 'missing'):
        assert not pr.in_set(s)
    monkeypatch.setattr(pr, 'PREFLIGHT_POLICY', 'failure')           # the one switch: a rejection is then a failure
    assert pr.in_set('preflight_rejected') and pr.in_set('rerolled') and not pr.in_set('void')


# ---------------------------------------------------------------------------
# a complete synthetic dataset
# ---------------------------------------------------------------------------

def outcome(arm, cell):
    """A deterministic outcome per cell: success unless a rule says otherwise."""
    gi = ps.RP_GOALS.index(cell['goal']) if cell['goal'] in ps.RP_GOALS else 2
    h = (cell['seed'] * 7 + cell['n_occluders'] * 3 + gi * 5 + (11 if arm == 'B' else 0)) % 10
    return h >= (3 if arm == 'B' else 2)        # A about 80 %, B about 70 %


def fill_job(root, name='job00', arms=ps.ARMS, mtime=None, tweak=None, slots=range(ps.N_SLOTS)):
    job = make_job(root, name)
    for arm in arms:
        for slot in slots:
            for cell in ps.slot_cells(arm, slot):
                ok = outcome(arm, cell)
                ts = pipeline_summary(cell, ok, None if ok else 'planner_failed')
                stdout = f"  Target: tgt_{cell['seed']}_{cell['n_occluders']}\n" if cell['goal'] == 'holding' else ''
                put(job, arm, f'slot_{slot}', cell, ts, stdout, mtime=mtime)
    if tweak:
        tweak(job)
    return job


def expected_counts(arm, goals, difficulty=None, slots=range(ps.N_SLOTS)):
    k = n = 0
    for slot in slots:
        for c in ps.slot_cells(arm, slot):
            if c['goal'] in goals and (difficulty is None or c['n_occluders'] == difficulty):
                n += 1
                k += outcome(arm, c)
    return k, n


def test_pooled_a_against_b_numbers(tmp_path):
    fill_job(tmp_path)
    text, res = pr.build_report([str(tmp_path)])
    ka, na = expected_counts('A', ('find-and-tray-stack', 'stack'))
    kb, nb = expected_counts('B', ('find-and-tray-stack', 'stack'))
    assert (na, nb) == (180, 180)
    d, lo, hi = pr.newcombe(ka, na, kb, nb)
    p = pr.fisher_exact(ka, na, kb, nb)
    line = (f"A {ka}/{na} = {100 * ka / na:.1f} %, B {kb}/{nb} = {100 * kb / nb:.1f} %; "
            f"A - B = {100 * d:+.1f} points, 95 % Newcombe [{100 * lo:+.1f}, {100 * hi:+.1f}]; "
            f"Fisher exact p = {p:.3g} (unpaired)")
    assert line in text
    # holding is on its own line, descriptive, and says why it is not tested
    hk, hn = expected_counts('A', ('holding',))
    assert f"holding              A {hk:3d}/{hn:3d}" in text and 'two different claims' in text
    assert 'measures our code and the benchmark together' in text
    # per arm, per cell: every one of the 270 cells counted
    assert 'arm A: 270 cells: 270 success' not in text and 'arm A: 270 cells:' in text
    assert 'MORE THAN ONE SNAPSHOT' not in text
    assert 'snapshot A: sb_a tree hash aaaa' in text


def rejected_tweak(job):                              # A's three tray-stack cells at 3 occluders: rejected
    for slot in (0, 1, 2):
        cell = cell_of('A', 'find-and-tray-stack', 3, slot)
        put(job, 'A', f'slot_{slot}', cell, stub(cell, 'preflight_rejected', preflight_message='[pre-flight] seed 1 rejected: x'), None)


def test_a_preflight_rejection_is_left_out_and_named_by_default(tmp_path):
    fill_job(tmp_path, tweak=rejected_tweak)
    text, res = pr.build_report([str(tmp_path)])
    t = pr.tally(pr.group_cells(res, 'A', 'find-and-tray-stack', 3))
    assert t['all'] == 30 and t['n'] == 27 and t['other'] == {'preflight_rejected': 3} and t['crashed'] == {}
    k, n = expected_counts('A', ('find-and-tray-stack',), 3)
    k -= sum(outcome('A', cell_of('A', 'find-and-tray-stack', 3, s)) for s in (0, 1, 2))
    assert t['k'] == k
    assert 'declared  30' in text and 'left out: 3 preflight_rejected' in text
    assert 'over all' not in text and 'cells that built' not in text            # one rate, no second one
    assert 'PREFLIGHT_POLICY = out' in text


def test_the_preflight_policy_failure_counts_a_rejection_as_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, 'PREFLIGHT_POLICY', 'failure')
    fill_job(tmp_path, tweak=rejected_tweak)
    text, res = pr.build_report([str(tmp_path)])
    t = pr.tally(pr.group_cells(res, 'A', 'find-and-tray-stack', 3))
    assert t['all'] == 30 and t['n'] == 30 and t['other'] == {} and t['crashed'] == {}
    k, _ = expected_counts('A', ('find-and-tray-stack',), 3)
    assert t['k'] == k - sum(outcome('A', cell_of('A', 'find-and-tray-stack', 3, s)) for s in (0, 1, 2))
    assert 'PREFLIGHT_POLICY = failure' in text and 'left out: 3 preflight' not in text


def test_a_crash_is_a_failure_with_the_count_named_beside_the_rate(tmp_path):
    def tweak(job):                                   # A: one crash and one hang; B: one banked summary of another cell
        c1, c2 = cell_of('A', 'holding', 2, 0), cell_of('A', 'holding', 2, 1)
        put(job, 'A', 'slot_0', c1, stub(c1, 'crash_exit139'), None)
        put(job, 'A', 'slot_1', c2, stub(c2, 'no_summary'), None)
        c3 = cell_of('B', 'stack', 3, 0)
        bad = pipeline_summary(c3, True)
        bad['run_config']['goal'] = 'holding'
        put(job, 'B', 'slot_0', c3, bad, '')
    fill_job(tmp_path, tweak=tweak)
    text, res = pr.build_report([str(tmp_path)])
    t = pr.tally(pr.group_cells(res, 'A', 'holding', 2))
    assert t['n'] == 30 and t['all'] == 30 and t['crashed'] == {'crash': 1, 'no_summary': 1}
    expect, _ = expected_counts('A', ('holding',), 2)
    expect -= sum(outcome('A', cell_of('A', 'holding', 2, s)) for s in (0, 1))
    assert t['k'] == expect                                                       # both are failures in the numerator's complement
    assert f"crashed: 2 of {t['n']} (1 crash, 1 no_summary)" in text
    tb = pr.tally(pr.group_cells(res, 'B', 'stack', 3))
    assert tb['crashed'] == {'summary_mismatch': 1} and f"crashed: 1 of {tb['n']} (1 summary_mismatch)" in text
    assert '1 summary of another cell (D-08, a failure)' in text                  # in the failure modes
    # a cell with a crash is not in the redo list: only cells that never started are
    out = tmp_path / 'out'
    pr.build_report([str(tmp_path)], out_dir=str(out))
    assert (out / 'redo_list.txt').read_text() == ''


def test_the_redo_list_and_targets(tmp_path):
    def tweak(job):
        c1 = cell_of('A', 'holding', 2, 4)
        put(job, 'A', 'slot_4', c1, stub(c1, 'crash_exit139'), None)
        c2 = cell_of('B', 'stack', 3, 9)
        put(job, 'B', 'slot_9', c2, stub(c2, 'no_summary'), None)
        c3 = cell_of('A', 'holding', 3, 5)                     # a timeout stub keeps no stdout.log
        put(job, 'A', 'slot_5', c3, stub(c3, 'timeout', wall=1800.2), None)
    fill_job(tmp_path, tweak=tweak, slots=range(10))
    out = tmp_path / 'out'
    text, res = pr.build_report([str(tmp_path)], out_dir=str(out))
    redo = (out / 'redo_list.txt').read_text().splitlines()      # only the 20 slots nobody ran: never started
    assert [r.split()[0] for r in redo] == ['A', 'B']
    for line, cell in ((redo[0], cell_of('A', 'holding', 2, 4)), (redo[1], cell_of('B', 'stack', 3, 9)),
                       (redo[0], cell_of('A', 'holding', 3, 5))):           # a crash, a hang and a timeout ran: not listed
        assert ps.expected_tag(cell) not in line.split()[1].split(',')
    assert len(redo[0].split()[1].split(',')) == 20 * 9 and len(redo[1].split()[1].split(',')) == 20 * 9
    assert 'NOT FULL' in text and 'crashes of arm A, ours' in text
    t2 = json.loads((out / 'targets_occ2.json').read_text())
    assert len(t2) == 9 and t2[str(ps.S_A[0])] == f"tgt_{ps.S_A[0]}_2" and str(ps.S_A[4]) not in t2   # the crashed cell has none
    t3 = json.loads((out / 'targets_occ3.json').read_text())
    assert len(t3) == 9 and str(ps.S_A[5]) not in t3 and 'timeout stubs keep no stdout.log' in text
    # merged sweep folders for the plotter: one row per cell with the cell's own fields
    rows = [json.loads(l) for l in (out / 'sweep_A' / 'aggregated.jsonl').read_text().splitlines()]
    assert len(rows) == 90 and all('p6_tag' in r and 'seed' in r and 'goal' in r for r in rows)   # the cells with an attempt
    assert (out / 'sweep_B' / 'aggregated.csv').exists() and (out / 'sweep_B' / 'matrix.json').exists()


def test_trouble_is_listed_and_unknown_cells_are_named(tmp_path):
    def tweak(job):
        c = cell_of('A', 'stack', 2, 3)
        put(job, 'A', 'slot_3', c, stub(c, 'crash_exit1', wall=3.0), None)
        d = job / 'A' / 'slot_3' / 'cells' / 'randpairs_occ2_seed99_holding_uc0_semantic'
        d.mkdir(parents=True)
        (d / 'timing_summary.json').write_text('{}')
    fill_job(tmp_path, tweak=tweak, slots=range(4))
    text, _ = pr.build_report([str(tmp_path)])
    assert 'crash (crash_exit1)' in text and 'CELL FOLDERS NO SLOT NAMES (1)' in text


def test_a_void_job_counts_nothing(tmp_path):
    job = fill_job(tmp_path, slots=range(2))
    (job / 'VOID').write_text('arm A after: ./tools/x.py: FAILED\n')
    text, res = pr.build_report([str(tmp_path)])
    ran = [rec for rec in res['A'].values() if rec['attempts']]
    assert len(ran) == 18 and all(rec['final']['status'] == 'void' for rec in ran)
    assert 'VOID: arm A after' in text and 'final pass list' not in text            # no --out: nothing written
    out = tmp_path / 'o'
    pr.build_report([str(tmp_path)], out_dir=str(out))
    assert len((out / 'redo_list.txt').read_text().splitlines()) == 2                # both arms re-run


# ---------------------------------------------------------------------------
# B against the thesis sweep, the identical-layout stack cells, the stall rule
# ---------------------------------------------------------------------------

def sweep_rows_like_b():
    rows = []
    for slot in range(ps.N_SLOTS):
        for cell in ps.slot_cells('B', slot):
            ok = outcome('B', cell)
            row = pipeline_summary(cell, ok, None if ok else 'planner_failed')
            row['run_config']['min_boxel_size'] = None
            rows.append(row)
    return rows


def test_b_against_the_sweep_pairs_on_the_seed_actually_run(tmp_path):
    cell = cell_of('B', 'find-and-tray-stack', 4, 7)

    def tweak(job):                                    # B re-rolled this cell to seed 777 and it failed
        put(job, 'B', 'slot_7', cell, pipeline_summary(cell, False, 'planner_failed', seed=777),
            '[retry 1/10] placement failed (x); rerolling to seed=777\n')
    fill_job(tmp_path, tweak=tweak, slots=range(10))
    rows = sweep_rows_like_b()
    # the sweep's row of the same effective seed, with the opposite outcome; the cell's own seed has no row
    rows = [r for r in rows if not (r['run_config']['goal'] == cell['goal'] and r['run_config']['n_occluders'] == 4
                                    and r['run_config']['seed'] == cell['seed'])]
    row = pipeline_summary(cell, True, seed=777)
    row['run_config']['min_boxel_size'] = None
    rows.append(row)
    # a non-semantic or cell-size row must not pair
    junk = pipeline_summary(cell, True, seed=777)
    junk['run_config'].update(baseline='uniform', min_boxel_size=None)
    rows.append(junk)
    text, res = pr.build_report([str(tmp_path)], sweep=rows)
    final = res['B'][ps.expected_tag(cell)]['final']
    assert final['status'] == 'rerolled' and final['rerolled'] and not pr.in_set(final['status'])
    assert f"re-rolled (cell seed to the seed that ran, the replacement never counts): occ4 {cell['seed']}>777" in text
    assert "B's runs on the replacement seeds, an extra number apart from every rate: 0/1" in text
    # the re-rolled cell is out of the rate and out of the pairing; the 89 others pair on their own seed
    assert '89 cells paired on the cell\'s own seed' in text and 'have no sweep row' not in text
    assert 'only the sweep 0, neither' in text and 'only the cluster 0' in text
    assert 'exact McNemar p = 1;' in text
    assert 'agreement 100.0 %' in text
    assert any('left out:' in l and '1 rerolled' in l for l in text.splitlines())


def test_identical_layout_stack_cells_are_a_paired_subset(tmp_path):
    fill_job(tmp_path, slots=range(3))
    identical = [[ps.S_B[i], h] for i in range(3) for h in (2, 3)]
    text, res = pr.build_report([str(tmp_path)], identical=identical)
    both = a_only = b_only = neither = 0
    for seed, h in identical:
        a = outcome('A', ps.stack_cell(h, seed))
        b = outcome('B', ps.stack_cell(h, seed))
        both += a and b
        a_only += a and not b
        b_only += b and not a
        neither += (not a) and (not b)
    assert (f"the 6 cells whose spawned layout is identical in both commits (a code-only paired subset): 6 counted in both arms; "
            f"both succeed {both}, only A {a_only}, only B {b_only}, neither {neither}; "
            f"exact McNemar p = {pr.mcnemar_exact(a_only, b_only):.3g}") in text


def test_the_stall_rule_lists_the_cells_and_prints_the_test_again(tmp_path):
    t0 = 1_700_000_000
    job = fill_job(tmp_path, mtime=t0 + 1000, slots=range(3))          # every cell ended at t0+1000 after 30 s
    (job / 'io_probe.tsv').write_text(
        'time\tepoch\tw_open_s\tw_write_fsync_s\tlocal_write_fsync_s\n'
        f'a\t{t0 + 900}\t0.01\t0.01\t0.01\n'
        f'b\t{t0 + 980}\t3.2\t0.5\t0.01\n'            # a single slow row is not a stall
        f'c\t{t0 + 1000}\t0.01\t0.01\t0.01\n'
        f'd\t{t0 + 1020}\t1.0\t0.5\t0.01\n'
        f'e\t{t0 + 1040}\t2.5\t0.5\t0.01\n')          # two in a row: a stall from t0+1020 to t0+1060
    # cells that ended at t0+1000 with a wall of 30 s ran t0+970..1000: they miss the stall window,
    # so move three of them into it
    for slot in (0, 1, 2):
        cell = cell_of('B', 'stack', 2, slot)
        put(job, 'B', f'slot_{slot}', cell, pipeline_summary(cell, True), '', mtime=t0 + 1050)
    wins = pr.stall_windows(str(job))
    assert wins == [(t0 + 1020, t0 + 1040 + pr.PROBE_PERIOD_S)]
    text, _ = pr.build_report([str(tmp_path)])
    assert 'stall rule: 1 stalls in 1 probes (job00 1); 3 cells overlap one' in text
    assert 'TEST 1 again without the cells that overlap a stall' in text
    # without a stall nothing is printed twice
    (job / 'io_probe.tsv').write_text('time\tepoch\tw_open_s\tw_write_fsync_s\tlocal_write_fsync_s\n')
    text, _ = pr.build_report([str(tmp_path)])
    assert 'stall rule: 0 stalls' in text and 'again without' not in text


def test_completeness_zero_crash_and_both_failed_lines(tmp_path):
    def tweak(job):
        a1 = cell_of('A', 'stack', 2, 3)
        put(job, 'A', 'slot_3', a1, stub(a1, 'crash_exit1', wall=3.0), None)
        b1 = cell_of('B', 'stack', 2, 3)                              # the same cell crashes in B too
        put(job, 'B', 'slot_3', b1, stub(b1, 'no_summary'), None)
    fill_job(tmp_path, tweak=tweak, slots=range(4))
    text, _ = pr.build_report([str(tmp_path)])
    block = text.split('completeness (planned runs', 1)[1].split('\n\n')[0]
    assert 'NOT FULL' in block and 'planned 270, rows 36; never started 234' in block      # 4 of 30 slots ran
    assert 'crashed 1' in block
    assert 'crashes of arm A, ours (zero-crash rule: each needs a BUGS.md entry' in block and ': 1: ' in block
    assert 'cells where A and B both failed to run (crash, no summary, mismatch): 1' in block
    # a full dataset says so
    full = tmp_path / 'full'
    full.mkdir()
    fill_job(full)
    text2, _ = pr.build_report([str(full)])
    assert 'full: every planned cell has a first attempt and none crashed' in text2 and 'NOT FULL' not in text2
    assert 'crashes of arm A, ours (zero-crash rule: each needs a BUGS.md entry with its investigated cause): 0' in text2


def test_the_cli_preflight_switch(tmp_path, capsys):
    fill_job(tmp_path / 'jobs', slots=range(1))
    try:
        assert pr.main(['--results', str(tmp_path / 'jobs'), '--preflight', 'failure']) == 0
        assert 'PREFLIGHT_POLICY = failure' in capsys.readouterr().out
        assert pr.main(['--results', str(tmp_path / 'jobs')]) == 0
        assert 'PREFLIGHT_POLICY = out' in capsys.readouterr().out
    finally:
        pr.PREFLIGHT_POLICY = 'out'


def test_the_cli_writes_the_report(tmp_path, capsys):
    fill_job(tmp_path / 'jobs', slots=range(2))
    out = tmp_path / 'out'
    assert pr.main(['--results', str(tmp_path / 'jobs'), '--out', str(out)]) == 0
    printed = capsys.readouterr().out
    assert (out / 'report.txt').read_text().strip() == printed.strip()
    assert 'TEST 1: A against B pooled over find-and-tray-stack and stack' in printed


def test_two_snapshots_in_the_jobs_are_flagged(tmp_path):
    fill_job(tmp_path, 'job00', slots=range(1))
    j2 = make_job(tmp_path, 'job01', header='host node-b  job 2  now  mode 1  A sb_a  B sb_b  cap 1800s  out x\n'
                                            'cpu Xeon  threads 96\nsnapshot A sb_other: 251 files, tree hash cccc\n')
    text, _ = pr.build_report([str(tmp_path)])
    assert 'MORE THAN ONE SNAPSHOT' in text


# ---------------------------------------------------------------------------
# rule 16: the memory block (tools/memwatch.py's records, the jobs' own lines, sacct)

GB = 1024 * 1024        # kB


def mem_rec(tag, avail_min=8 * GB, peak=2 * GB, group=3 * GB, over=False, leftover=(), shm_new=()):
    return {'tag': tag, 'started_epoch': 1.0, 'ended_epoch': 2.0, 'peak_over_6gb': over,
            'mem': {'avail_start_kb': 9 * GB, 'avail_end_kb': 8 * GB, 'avail_min_kb': avail_min, 'peak_rss_kb': peak,
                    'peak_exact': True, 'children_hwm_kb': peak, 'group_peak_kb': group, 'polls': 5,
                    'batch_rss_kb': 100_000, 'leftover': list(leftover), 'shm_new': list(shm_new),
                    'min_avail_limit_kb': 4 * GB, 'peak_limit_kb': 6 * GB, 'peak_over_limit': over}}


def put_mem(job, arm, label, recs, stop=None):
    d = job / arm / label
    d.mkdir(parents=True, exist_ok=True)
    (d / 'mem_cells.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in recs))
    if stop:
        (d / 'STOPPED_LOW_MEMORY.txt').write_text(stop)


def header_with(job_id, extra=''):
    return (f'host node-a  job {job_id}  now  mode 0  A sb_a  B sb_b  cap 1800s  out x\n'
            f'cpu Xeon  threads 96\n{extra}snapshot A sb_a: 251 files, tree hash aaaa\n')


def memory_block(text):
    return text.split('memory (rule 16', 1)[1]


def test_the_memory_block_counts_records_and_flags_what_is_over(tmp_path):
    job = fill_job(tmp_path, slots=range(1))
    tags = [ps.expected_tag(c) for c in ps.slot_cells('A', 0)]
    put_mem(job, 'A', 'slot_0', [
        mem_rec(tags[0]),
        mem_rec(tags[1], peak=7 * GB, group=7 * GB, over=True),
        mem_rec(tags[2], avail_min=5 * GB, leftover=[{'pid': 4242, 'comm': 'downward', 'rss_kb': 1000}],
                shm_new=['psm_x'])])
    text, _ = pr.build_report([str(tmp_path)])
    block = memory_block(text)
    n = sum(len(ps.slot_cells(arm, 0)) for arm in ps.ARMS)
    assert f'  3 of {n} cell attempts carry a memory record (a cell without one was banked' in block
    assert 'memory: 3 episodes recorded; lowest MemAvailable 5.00 GB' in block
    assert f'memory: OVER the peak limit: job00 A slot_0 {tags[1]}, peak RSS 7.00 GB' in block
    assert f'job00 A slot_0 {tags[2]} left 1 pipeline process(es) behind' in block
    assert f"job00 A slot_0 {tags[2]}: new in /dev/shm: ['psm_x']" in block
    assert 'no STOPPED_LOW_MEMORY file' in block
    assert 'job00: no memory lines in header.txt (a job from before rule 16)' in block
    assert 'sacct' not in block                       # without --sacct nothing is said about it
    # memory never changes a count: the same cells without any memory record give the same report above the block
    plain = tmp_path / 'plain'
    plain.mkdir()
    fill_job(plain, slots=range(1))
    assert pr.build_report([str(plain)])[0].split('memory (rule 16', 1)[0] == text.split('memory (rule 16', 1)[0]


def test_a_stopped_file_and_the_jobs_own_memory_lines_are_printed(tmp_path):
    extra = ('memory at the start: MemTotal: 196000000 kB  MemAvailable: 150000000 kB  local fs /tmp xfs (tmpfs is RAM)\n'
             'memory after the job: 0 pipeline processes of ours alive, 0 names in /dev/shm, MemAvailable 149000000 kB\n')
    job = fill_job(tmp_path, slots=range(1), tweak=lambda j: (j / 'header.txt').write_text(header_with(77, extra)))
    (job / 'strays.txt').write_text('after arm A slot_0 2026-11-07T20:00:00:\n 4242 1 90 python test_full_pipeline.py\n'
                                    'after arm B slot_0 2026-11-07T20:30:00:\n')
    put_mem(job, 'B', 'slot_0', [mem_rec('t1', avail_min=3 * GB)],
            stop='STOPPED_LOW_MEMORY: t1 end: MemAvailable 3.00 GB under the limit 4.00 GB\nwhere end\n')
    block = memory_block(pr.build_report([str(tmp_path)])[0])
    assert '  STOPPED_LOW_MEMORY: t1 end: MemAvailable 3.00 GB under the limit 4.00 GB  (job00 B slot_0)' in block
    assert 'no STOPPED_LOW_MEMORY file' not in block
    assert 'job00: memory at the start: MemTotal: 196000000 kB' in block
    assert 'job00: memory after the job: 0 pipeline processes of ours alive, 0 names in /dev/shm' in block
    assert 'job00: 1 pipeline process(es) listed in strays.txt after the arms' in block
    assert 'no memory lines in header.txt' not in block


SACCT = ('JobID|JobName|State|Elapsed|MaxRSS|ReqMem|NodeList\n'
         '77|p6-tabletop|COMPLETED|01:00:00||12G|node-a\n'
         '77.batch|batch|COMPLETED|01:00:00|2345678K||node-a\n'
         '77.extern|extern|COMPLETED|01:00:00|0||node-a\n'
         '88|p6-tabletop|OUT_OF_MEMORY|00:10:00||12G|node-b\n'
         '88.batch|batch|OUT_OF_MEMORY|00:10:00|7000000K||node-b\n')


def test_slurm_sizes_and_sacct_rows():
    assert [pr.slurm_kb(x) for x in ('1234K', '2M', '3G', '12Gn', '4000Mc', '0', '17')] == [
        1234, 2048, 3 * 1024 ** 2, 12 * 1024 ** 2, 4000 * 1024, 0, 17]
    assert pr.slurm_kb('') is None and pr.slurm_kb('x') is None and pr.slurm_kb(None) is None
    info = pr.parse_sacct(SACCT)
    assert info['77'] == {'max_rss_kb': 2345678, 'name': 'p6-tabletop', 'state': 'COMPLETED',
                          'elapsed': '01:00:00', 'req_mem': '12G', 'node': 'node-a'}
    assert info['88']['max_rss_kb'] == 7000000 and info['88']['state'] == 'OUT_OF_MEMORY'
    assert pr.parse_sacct('') == {} and pr.parse_sacct('nothing useful\n') == {}
    assert pr.parse_sacct('MaxRSS|JobID\n5K|9.batch\n') == {'9': {'max_rss_kb': 5}}      # columns are found by name


def test_sacct_rows_join_the_jobs_by_the_slurm_id_in_their_header(tmp_path):
    fill_job(tmp_path, 'job00', slots=range(1), tweak=lambda j: (j / 'header.txt').write_text(header_with(77)))
    fill_job(tmp_path, 'job01', slots=range(1), tweak=lambda j: (j / 'header.txt').write_text(header_with(99)))
    assert pr.header_job_id(str(tmp_path / 'job00')) == '77' and pr.header_job_id(str(tmp_path / 'nope')) is None
    block = memory_block(pr.build_report([str(tmp_path)], sacct=SACCT)[0]).splitlines()
    assert '  sacct job 77 (job00): MaxRSS 2.24 GB, requested 12G, COMPLETED, 01:00:00, node-a' in block
    assert '  sacct: no row for job01 (job 99)' in block
    assert ('  sacct job 88 (not among the results folders): MaxRSS 6.68 GB, requested 12G, OUT_OF_MEMORY, '
            '00:10:00, node-b  OVER 6 GB (report it)') in block


def test_the_cli_takes_sacct_and_a_missing_file_is_an_error(tmp_path, capsys):
    fill_job(tmp_path / 'jobs', slots=range(1), tweak=lambda j: (j / 'header.txt').write_text(header_with(77)))
    (tmp_path / 'sacct.txt').write_text(SACCT)
    assert pr.main(['--results', str(tmp_path / 'jobs'), '--out', str(tmp_path / 'out'),
                    '--sacct', str(tmp_path / 'sacct.txt')]) == 0
    assert 'sacct job 77 (job00)' in capsys.readouterr().out
    with pytest.raises(SystemExit):
        pr.main(['--results', str(tmp_path / 'jobs'), '--sacct', str(tmp_path / 'missing.txt')])


# ---------------------------------------------------------------------------
# rule 18: drops, collisions and clean success (a run's summary carries the fields since TB-22)
# ---------------------------------------------------------------------------

A_DET = {'drop_detector': 'telemetry counts: a carried body left both finger pads',
         'collision_detector': 'telemetry counts: distinct (action, body) pairs'}


def with_counts(ts, drops, collisions, det=A_DET):
    return dict(ts, drops=drops, collisions=collisions, clean_success=None, **det)


def rule18_block(text):
    return text.split('drops and collisions (rule 18', 1)[1].split('\n\n')[0]


def a_counts_tweak(drops_at, collisions_at, no_count_at=()):
    """Arm A's slot-0 cells rewritten with the fields: one drop on the cells of drops_at, two collisions on
    those of collisions_at, no count at all on those of no_count_at ((goal, difficulty) pairs)."""
    def tweak(job):
        for cell in ps.slot_cells('A', 0):
            key = (cell['goal'], cell['n_occluders'])
            ok = outcome('A', cell)
            ts = pipeline_summary(cell, ok, None if ok else 'planner_failed')
            if key in no_count_at:
                ts = with_counts(ts, None, None, {'drop_detector': 'not detected (no summary and no counts file)',
                                                  'collision_detector': 'not detected (no summary and no counts file)'})
            else:
                ts = with_counts(ts, 1 if key in drops_at else 0, 2 if key in collisions_at else 0)
            put(job, 'A', 'slot_0', cell, ts,
                f"  Target: tgt_{cell['seed']}_{cell['n_occluders']}\n" if cell['goal'] == 'holding' else '')
    return tweak


def test_classify_carries_the_runs_own_counts():
    cell = cell_of('A', 'holding', 2)
    c = classify_one('A', cell, with_counts(pipeline_summary(cell, True), 1, 0))
    assert (c['drops'], c['collisions']) == (1, 0) and c['drop_detector'].startswith('telemetry counts')
    assert pr.clean_of(c) is False
    assert pr.clean_of(classify_one('A', cell, with_counts(pipeline_summary(cell, True), 0, 0))) is True
    # a summary without the fields (the thesis commit): unknown on a success, never clean by default
    plain = classify_one('B', cell_of('B', 'holding', 2), pipeline_summary(cell_of('B', 'holding', 2), True))
    assert plain['drops'] is None and pr.clean_of(plain) is None
    # a runner stub at the cap keeps the counts its run wrote up to the kill
    s = classify_one('A', cell, dict(stub(cell, 'timeout', wall=1800.0), drops=2, collisions=0, **A_DET))
    assert s['status'] == 'timeout' and s['drops'] == 2 and pr.clean_of(s) is False


def test_the_rule_18_block_counts_clean_success_for_a_and_says_b_is_not_measured(tmp_path):
    drops_at = {('holding', 2), ('find-and-tray-stack', 3)}
    collisions_at = {('stack', 4)}
    fill_job(tmp_path, slots=range(1), tweak=a_counts_tweak(drops_at, collisions_at))
    text, res = pr.build_report([str(tmp_path)])
    block = rule18_block(text)
    cells = ps.slot_cells('A', 0)
    ok = [c for c in cells if outcome('A', c)]
    dirty = drops_at | collisions_at
    clean = [c for c in ok if (c['goal'], c['n_occluders']) not in dirty]
    lo, hi = pr.wilson(len(clean), len(cells))
    line = next(l for l in block.splitlines() if l.split()[:1] == ['all'])
    assert line.split() == ['all', str(len(cells)), str(len(ok)), str(len(clean)),
                            f"[{100 * lo:4.1f},".strip(), f"{100 * hi:4.1f}]".strip(), '0', '2', '2', '1', '2', '0']
    assert '    drop_detector (9 cells): telemetry counts: a carried body left both finger pads' in block
    assert ("  arm B: its summaries carry no drop or collision field (the thesis code records neither and holds "
            "the object by a weld constraint): clean success is not measured for it") in block
    assert '  A against B on clean success: not printed (it is measured for A only)' in block
    # the rates above the block are the ones without the fields: nothing changed
    t = pr.tally(pr.group_cells(res, 'A'))
    assert t['k'] == len(ok) and t['n'] == len(cells)


def test_a_cell_nothing_counted_makes_clean_success_a_lower_bound(tmp_path):
    cells = ps.slot_cells('A', 0)
    first_ok = next(c for c in cells if outcome('A', c))
    key = (first_ok['goal'], first_ok['n_occluders'])
    fill_job(tmp_path, slots=range(1), tweak=a_counts_tweak(set(), set(), no_count_at={key}))
    block = rule18_block(pr.build_report([str(tmp_path)])[0])
    line = next(l for l in block.splitlines() if l.split()[:1] == ['all'])
    n_ok = sum(outcome('A', c) for c in cells)
    # "at least k" in place of the count, no interval, one unknown, one cell without a count
    assert line.split() == ['all', str(len(cells)), str(n_ok), 'at', 'least', str(n_ok - 1), '-', '1',
                            '0', '0', '0', '0', '1']
    assert 'not detected (no summary and no counts file)' in block


def test_summaries_without_the_fields_print_no_zero(tmp_path):
    fill_job(tmp_path, slots=range(1))
    block = rule18_block(pr.build_report([str(tmp_path)])[0])
    assert '  arm A: its summaries carry no drop or collision field (a snapshot from before TB-22?)' in block
    assert '(it is measured for neither arm)' in block
    assert not any(l.split()[:1] == ['all'] for l in block.splitlines())