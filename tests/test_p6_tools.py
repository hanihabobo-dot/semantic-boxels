"""Path 6: the phase 1a tools: the seed slots (tools/p6_slots.py), the per-slot
runner that injects the cells into an arm's own eval_runner
(tools/cluster/p6_run.py) and the cluster smoke's verdict
(tools/p6_smoke_check.py).

What these tests pin: the seed lists are the corpus files' first thirty seeds;
every slot is nine cells and the 30 slots cover each arm's 270 cells once; the
tags the tools expect are the tags both commits' runners build (the thesis
commit 6b00cd7's runner is read with git show); p6_run passes the runner its
preset and nothing else (no --extra-arg), runs from the arm's own directory
and tells a fatal runner exit from a result; the smoke verdict stops, pauses
and passes as PLAN.md section 11 declares."""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for p in (REPO, os.path.join(REPO, 'tools'), os.path.join(REPO, 'tools', 'cluster')):
    if p not in sys.path:
        sys.path.insert(0, p)
import eval_runner as er_tag  # noqa: E402  (the tag's runner: arm A's)
import p6_run  # noqa: E402
import p6_slots as ps  # noqa: E402
import p6_smoke_check as sc  # noqa: E402

THESIS_COMMIT = '6b00cd7'


@pytest.fixture
def restore_runner_modules(monkeypatch):
    """p6_run puts the working directory first on sys.path and imports
    eval_runner from it: give each test its own sys.path and module cache."""
    monkeypatch.setattr(sys, 'path', list(sys.path))
    if 'eval_runner' in sys.modules:
        monkeypatch.setitem(sys.modules, 'eval_runner', sys.modules['eval_runner'])
    yield
    # monkeypatch restores sys.path and an existing eval_runner entry; drop one it did not know
    if sys.modules.get('eval_runner') is not er_tag:
        sys.modules['eval_runner'] = er_tag


def test_seed_lists_are_the_corpus_files_first_thirty():
    with open(os.path.join(REPO, 'eval_corpus.json')) as f:
        assert ps.S_A == json.load(f)['seeds'][:30]
    with open(os.path.join(REPO, 'eval_corpus_2026-05-15.json')) as f:
        assert ps.S_B == json.load(f)['seeds'][:30]
    assert len(ps.S_A) == len(ps.S_B) == ps.N_SLOTS == 30
    assert len(set(ps.S_A)) == len(set(ps.S_B)) == 30


def test_a_slot_is_nine_cells_and_the_slots_cover_each_arm_once():
    for arm in ps.ARMS:
        all_tags = []
        for slot in range(ps.N_SLOTS):
            cells = ps.slot_cells(arm, slot)
            assert len(cells) == 9
            rp = [c for c in cells if c['scene'] == 'random-pairs']
            st = [c for c in cells if c['scene'] == 'stack']
            assert len(rp) == 6 and len(st) == 3
            rp_seed, stack_seed = ps.slot_seeds(arm, slot)
            assert {c['seed'] for c in rp} == {rp_seed} and {c['seed'] for c in st} == {stack_seed}
            assert stack_seed == ps.S_B[slot]
            assert rp_seed == (ps.S_A if arm == 'A' else ps.S_B)[slot]
            assert sorted({(c['goal'], c['n_occluders']) for c in rp}) == sorted(
                (g, n) for g in ps.RP_GOALS for n in (2, 3, 4))
            assert sorted(c['n_occluders'] for c in st) == [2, 3, 4]
            assert all(c['baseline'] == 'semantic' and c['unit_costs'] is False for c in cells)
            all_tags += [ps.expected_tag(c) for c in cells]
        assert len(all_tags) == len(set(all_tags)) == 270
    # stack runs the thesis list in both arms: its 90 tags are the same
    a_stack = {ps.expected_tag(c) for s in range(30) for c in ps.slot_cells('A', s) if c['scene'] == 'stack'}
    b_stack = {ps.expected_tag(c) for s in range(30) for c in ps.slot_cells('B', s) if c['scene'] == 'stack'}
    assert a_stack == b_stack and len(a_stack) == 90


def test_jobs_cover_the_slots_once_and_alternate_the_arm_order():
    slots = [s for j in range(ps.N_JOBS) for s in ps.job_slots(j)]
    assert slots == list(range(30))
    assert ps.arm_order(0) == ('A', 'B') and ps.arm_order(1) == ('B', 'A')
    for j in range(ps.N_JOBS):                     # A, B, B, A in every job: the node meets both arms alike
        first, second = ps.job_slots(j)
        assert ps.arm_order(first) + ps.arm_order(second) == ('A', 'B', 'B', 'A')
    with pytest.raises(ValueError):
        ps.job_slots(15)
    with pytest.raises(ValueError):
        ps.slot_cells('C', 0)


def test_the_job_script_reads_slots_and_order_from_the_tool(capsys):
    assert ps.main(['job-slots', '7']) == 0
    assert capsys.readouterr().out.split() == ['14', '15']
    assert ps.main(['arm-order', '14']) == 0
    assert capsys.readouterr().out.split() == ['A', 'B']
    assert ps.main(['arm-order', '15']) == 0
    assert capsys.readouterr().out.split() == ['B', 'A']
    assert ps.main(['job-slots', '08']) == 0       # int() takes a leading zero (bash's printf would not)
    assert capsys.readouterr().out.split() == ['16', '17']


def _every_cell_tag_matches(runner):
    for arm in ps.ARMS:
        for slot in range(ps.N_SLOTS):
            cells = ps.slot_cells(arm, slot)
            expanded = list(runner.iterate_matrix(ps.as_matrix(cells)))
            assert [runner.cell_tag(c) for c in expanded] == [ps.expected_tag(c) for c in cells]
            for c, e in zip(cells, expanded):
                assert (e['scene'], e['seed'], e['goal'], e['n_occluders'], e['baseline'], e['unit_costs'],
                        e['n_hidden'], e.get('n_targets')) == (
                    c['scene'], c['seed'], c['goal'], c['n_occluders'], c['baseline'], c['unit_costs'],
                    c['n_hidden'], c.get('n_targets'))


def test_the_tags_are_the_tags_of_the_tags_runner():
    _every_cell_tag_matches(er_tag)
    for c in ps.smoke_cells():                      # the smoke's cells are three of the slot cells' kind
        assert er_tag.cell_tag(next(iter(er_tag.iterate_matrix(ps.as_matrix([c]))))) == ps.expected_tag(c)


def _thesis_runner(tmp_path):
    try:
        src = subprocess.run(['git', '-C', REPO, 'show', f'{THESIS_COMMIT}:eval_runner.py'],
                             capture_output=True, check=True).stdout
        corpus = subprocess.run(['git', '-C', REPO, 'show', f'{THESIS_COMMIT}:eval_corpus.json'],
                                capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip(f'commit {THESIS_COMMIT} is not reachable from this checkout')
    d = tmp_path / 'thesis'
    d.mkdir()
    (d / 'eval_runner.py').write_bytes(src)
    (d / 'eval_corpus.json').write_bytes(corpus)
    spec = importlib.util.spec_from_file_location('eval_runner_thesis', str(d / 'eval_runner.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_tags_are_the_tags_of_the_thesis_runner(tmp_path):
    thesis = _thesis_runner(tmp_path)
    _every_cell_tag_matches(thesis)


def test_the_arms_run_their_own_way(tmp_path):
    """B's runner passes --seed-retry on random-pairs (as the sweep ran) and no --no-telemetry; A's
    does the opposite; neither passes a cell-size flag (auto cell)."""
    thesis = _thesis_runner(tmp_path)
    rp = ps.rp_cell(3, 7, 'holding')
    st = ps.stack_cell(4, 94)
    a_rp, b_rp = er_tag.cell_to_argv(rp, []), thesis.cell_to_argv(rp, [])
    assert '--seed-retry' in b_rp and '--seed-retry' not in a_rp
    assert '--no-telemetry' in a_rp and '--no-telemetry' not in b_rp
    for argv in (a_rp, b_rp, er_tag.cell_to_argv(st, []), thesis.cell_to_argv(st, [])):
        assert '--min-boxel-size' not in argv and '--unit-costs' not in argv
        assert argv[argv.index('--baseline') + 1] == 'semantic'
    assert er_tag.cell_to_argv(st, [])[-2:] == ['--stack-height', '4']
    assert thesis.cell_to_argv(st, [])[-2:] == ['--stack-height', '4']


def test_dry_run_prints_the_slot_and_passes_no_extra_arg(monkeypatch, capsys, tmp_path, restore_runner_modules):
    monkeypatch.chdir(REPO)
    assert p6_run.main(['--arm', 'A', '--slot', '3', '--out', str(tmp_path / 'o'), '--dry-run']) == 0
    out = capsys.readouterr().out
    assert out.count('randpairs_occ') == 6 and out.count('_stack_uc0_semantic') == 3
    assert f"seed{ps.S_A[3]}_" in out and f"seed{ps.S_B[3]}_stack" in out
    runner_argv = out.strip().splitlines()[-1]
    assert runner_argv.startswith('runner argv: --matrix p6-slot --output ')
    assert '--extra-arg' not in out
    assert runner_argv.endswith('--timeout 1800.0 --skip-existing')
    assert not (tmp_path / 'o').exists()           # a dry run writes nothing


FAKE_RUNNER = '''
import p6_slots
MATRIX_PRESETS = {}
CALLS = []
RETURN = 1


def iterate_matrix(matrix):
    for sub in matrix:
        c = {k: v[0] for k, v in sub.items() if not k.startswith('_')}
        c['n_hidden'] = 0
        yield c


def cell_tag(c):
    return p6_slots.expected_tag(c)


def cell_to_argv(c, extra):
    return ['python', 'test_full_pipeline.py'] + list(extra)


def main(argv=None):
    CALLS.append((list(argv), list(MATRIX_PRESETS['p6-slot'])))
    return RETURN
'''


def _fake_code_dir(tmp_path, name='codeB'):
    d = tmp_path / name
    d.mkdir()
    (d / 'eval_runner.py').write_text(FAKE_RUNNER)
    return d


def test_p6_run_gives_the_runner_its_preset_and_nothing_else(tmp_path, monkeypatch, restore_runner_modules):
    code = _fake_code_dir(tmp_path)
    monkeypatch.chdir(code)
    monkeypatch.delitem(sys.modules, 'eval_runner', raising=False)
    out = tmp_path / 'out' / 'B' / 'slot_3'
    monkeypatch.setenv('SLURM_JOB_ID', '4242')
    rc = p6_run.main(['--arm', 'B', '--slot', '3', '--out', str(out)])
    fake = sys.modules['eval_runner']
    assert rc == 0                                  # the fake runner returned 1: some cell failed, a result
    (argv, preset), = fake.CALLS
    assert argv == ['--matrix', 'p6-slot', '--output', str(out), '--timeout', '1800.0', '--skip-existing']
    assert '--extra-arg' not in argv
    assert len(preset) == 9 and preset == ps.as_matrix(ps.slot_cells('B', 3))
    meta = json.loads((out / 'p6_run.json').read_text())
    assert (meta['arm'], meta['slot'], meta['set'], meta['job'], meta['runner_rc']) == ('B', 3, 'slot', '4242', 1)
    assert meta['cells'] == [ps.expected_tag(c) for c in ps.slot_cells('B', 3)]
    assert meta['eval_runner'] == os.path.realpath(code / 'eval_runner.py')
    assert len(meta['eval_runner_sha256']) == 64


def test_a_fatal_runner_exit_is_the_scripts_exit(tmp_path, monkeypatch, restore_runner_modules):
    code = _fake_code_dir(tmp_path)
    (code / 'eval_runner.py').write_text(FAKE_RUNNER.replace('RETURN = 1', 'RETURN = 2'))
    monkeypatch.chdir(code)
    monkeypatch.delitem(sys.modules, 'eval_runner', raising=False)
    assert p6_run.main(['--arm', 'A', '--slot', '0', '--out', str(tmp_path / 'o')]) == 2


def test_p6_run_needs_the_arms_own_directory(tmp_path, monkeypatch, restore_runner_modules):
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)                    # eval_runner (the tag's) is already imported: not from here
    with pytest.raises(SystemExit) as e:
        p6_run.main(['--arm', 'A', '--slot', '0', '--out', str(tmp_path / 'o'), '--dry-run'])
    assert 'working directory' in str(e.value)


def test_smoke_cells_and_only_tags(tmp_path, monkeypatch, capsys, restore_runner_modules):
    code = _fake_code_dir(tmp_path)
    monkeypatch.chdir(code)
    monkeypatch.delitem(sys.modules, 'eval_runner', raising=False)
    assert p6_run.main(['--arm', 'B', '--set', 'smoke', '--out', str(tmp_path / 's')]) == 0
    fake = sys.modules['eval_runner']
    (argv, preset), = fake.CALLS
    assert len(preset) == 3
    # a final pass: any cell of the arm by its tag, nothing else
    wanted = [ps.expected_tag(ps.slot_cells('A', 5)[0]), ps.expected_tag(ps.slot_cells('A', 20)[8])]
    fake.CALLS.clear()
    assert p6_run.main(['--arm', 'A', '--set', 'all', '--only-tags', ','.join(wanted),
                        '--out', str(tmp_path / 'redo')]) == 0
    (_, preset), = fake.CALLS
    assert [ps.expected_tag(c) for c in ps.slot_cells('A', 5)[:1] + ps.slot_cells('A', 20)[8:]] == wanted
    assert len(preset) == 2
    with pytest.raises(SystemExit):                 # a tag of another arm's seed list is not in A's set
        p6_run.main(['--arm', 'A', '--set', 'all', '--only-tags',
                     ps.expected_tag(ps.rp_cell(2, 4, 'holding')), '--out', str(tmp_path / 'x')])


# ---------------------------------------------------------------------------
# TB-24: pddlstream's stream statistics are not carried from cell to cell
# ---------------------------------------------------------------------------

def _stats(code, name='boxel-streams.pkl', py='py3'):
    d = code / 'statistics' / py
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(b'x')
    return d / name


def _runner_with_cells(code, seen):
    """A stand-in for an arm's runner: run_cell notes whether the statistics file was there when
    the cell started and writes one, as a pipeline run does."""
    from types import SimpleNamespace

    def run_cell(cell, sweep_dir, timeout_s, extra_args, skip_existing):
        seen.append((cell['tag'], (code / 'statistics' / 'py3' / 'boxel-streams.pkl').exists()))
        _stats(code)
        return {'tag': cell['tag']}
    return SimpleNamespace(run_cell=run_cell, cell_tag=lambda c: c['tag'])


def test_fresh_statistics_removes_the_file_before_every_cell_that_runs(tmp_path):
    code = tmp_path / 'codeA'
    code.mkdir()
    seen, log = [], []
    er = _runner_with_cells(code, seen)
    sweep = tmp_path / 'sweep'
    p6_run.install_fresh_statistics(er, str(code), log=log.append)
    for tag in ('c1', 'c2', 'c3'):
        assert er.run_cell({'tag': tag}, sweep, 1800.0, [], True) == {'tag': tag}
    # without the switch the second and third cell would have started with the file of the one before
    assert seen == [('c1', False), ('c2', False), ('c3', False)]
    assert len(log) == 2 and 'stats c2: removed' in log[0] and '(1 file(s))' in log[0]
    # a banked cell (its summary exists, --skip-existing) is not an episode: nothing is removed for it
    (sweep / 'cells' / 'c4').mkdir(parents=True)
    (sweep / 'cells' / 'c4' / 'timing_summary.json').write_text('{}')
    er.run_cell({'tag': 'c4'}, sweep, 1800.0, [], True)
    assert seen[-1] == ('c4', True)


def test_without_the_switch_the_file_is_carried(tmp_path):
    code = tmp_path / 'codeA'
    code.mkdir()
    seen = []
    er = _runner_with_cells(code, seen)
    for tag in ('c1', 'c2'):
        er.run_cell({'tag': tag}, tmp_path / 'sweep', 1800.0, [], True)
    assert seen == [('c1', False), ('c2', True)]


def test_fresh_statistics_removes_nothing_it_does_not_know(tmp_path):
    code = tmp_path / 'codeA'
    code.mkdir()
    _stats(code)
    assert len(p6_run.statistics_files(str(code / 'statistics'))) == 1
    for foreign in (code / 'statistics' / 'notes.txt', code / 'statistics' / 'py3' / 'data.json',
                    code / 'statistics' / 'other' / 'x.pkl', code / 'statistics' / 'py3' / 'deep' / 'x.pkl'):
        foreign.parent.mkdir(parents=True, exist_ok=True)
        foreign.write_text('mine')
        with pytest.raises(SystemExit) as e:
            p6_run.statistics_files(str(code / 'statistics'))
        assert 'nothing removed' in str(e.value)
        foreign.unlink()
    seen = []
    er = _runner_with_cells(code, seen)
    p6_run.install_fresh_statistics(er, str(code), log=lambda s: None)
    (code / 'statistics' / 'keep.txt').write_text('mine')
    with pytest.raises(SystemExit):
        er.run_cell({'tag': 'c1'}, tmp_path / 'sweep', 1800.0, [], True)
    assert (code / 'statistics' / 'keep.txt').exists() and seen == []      # nothing removed, nothing run


def test_the_switch_is_recorded_and_needs_run_cell(tmp_path, monkeypatch, restore_runner_modules):
    code = _fake_code_dir(tmp_path)                 # this fake runner has no run_cell
    monkeypatch.chdir(code)
    monkeypatch.delitem(sys.modules, 'eval_runner', raising=False)
    with pytest.raises(SystemExit) as e:
        p6_run.main(['--arm', 'B', '--slot', '3', '--out', str(tmp_path / 'o'), '--fresh-stream-stats'])
    assert 'run_cell' in str(e.value)
    assert json.loads((tmp_path / 'o' / 'p6_run.json').read_text())['fresh_stream_stats'] is True
    assert p6_run.main(['--arm', 'B', '--slot', '3', '--out', str(tmp_path / 'p')]) == 0
    assert json.loads((tmp_path / 'p' / 'p6_run.json').read_text())['fresh_stream_stats'] is False


def test_the_job_script_passes_the_switch_only_when_asked():
    text = open(os.path.join(REPO, 'tools', 'cluster', 'p6_tabletop.sbatch'), encoding='utf-8').read()
    assert '[ "${P6_FRESH_STATS:-0}" = 1 ] && STATS_ARG=--fresh-stream-stats' in text
    assert 'p6_run.py --arm $arm "$@" $STATS_ARG \\' in text
    assert 'stream statistics (TB-24)' in text
    assert '\r' not in text                         # the script runs under bash: LF only


# ---------------------------------------------------------------------------
# the smoke verdict
# ---------------------------------------------------------------------------

def _smoke_folder(tmp_path, b_counts=None, wall_scale=1.0, drop=None, arm_a_stub=None):
    for arm in ('A', 'B'):
        for tag, exp in sc.EXPECTED_B.items():
            if drop == (arm, tag):
                continue
            counts = (b_counts or {}).get(tag, exp['counts']) if arm == 'B' else (1, 1, 1)
            ts = {'run_config': {'scene': 'x'}, 'success': True, 'plan_count': 2,
                  'total_planning_time_s': 5.0, 'wall_clock_s': exp['sweep_wall_s'] * wall_scale,
                  'boxel_counts_per_replan': [{'plan_index': 1, 'n_object_boxels': counts[0],
                                               'n_shadow_boxels': counts[1], 'n_free_space_boxels': counts[2]}]}
            if arm_a_stub and arm == 'A' and tag == arm_a_stub:
                ts = {'success': False, 'exit_reason': 'crash_exit139', 'wall_clock_s': 3.0}
            d = tmp_path / arm / 'slot_smoke' / 'cells' / tag
            d.mkdir(parents=True)
            (d / 'timing_summary.json').write_text(json.dumps(ts))
    return str(tmp_path)


def test_smoke_passes_when_b_reproduces_the_sweeps_counts(tmp_path):
    rc, text = sc.check(_smoke_folder(tmp_path, wall_scale=1.5))
    assert rc == 0 and 'SMOKE_VERDICT PASS' in text
    assert 'median wall-time ratio to the sweep' in text and '1.50' in text


def test_smoke_stops_when_a_deterministic_count_differs(tmp_path):
    tag = 'randpairs_occ2_seed2_find-and-tray-stack_uc0_semantic'
    rc, text = sc.check(_smoke_folder(tmp_path, b_counts={tag: (4, 5, 17)}))
    assert rc == 3 and 'SMOKE_VERDICT STOP' in text and 'DIFFERS' in text


def test_smoke_stops_on_a_missing_or_stub_cell_of_either_arm(tmp_path):
    tag = 'occ2_tgt3_hid0_seed0_stack_uc0_semantic'
    rc, text = sc.check(_smoke_folder(tmp_path / 'one', drop=('B', tag)))
    assert rc == 3 and 'no pipeline summary' in text
    rc, text = sc.check(_smoke_folder(tmp_path / 'two', arm_a_stub=tag))
    assert rc == 3 and 'crash_exit139' in text


def test_smoke_pauses_above_the_wall_ratio(tmp_path):
    rc, text = sc.check(_smoke_folder(tmp_path / 'slow', wall_scale=3.4))
    assert rc == 4 and 'SMOKE_VERDICT PAUSE' in text
    rc, text = sc.check(_smoke_folder(tmp_path / 'edge', wall_scale=3.0))
    assert rc == 0                                   # above 3.0 pauses, 3.0 itself does not

# ---------------------------------------------------------------------------
# the scene merge (phase 1b)
# ---------------------------------------------------------------------------
import hashlib  # noqa: E402
import p6_merge_scenes as pm  # noqa: E402


def _scene_folder(root, seeds, no_scene=(), manifest_extra=None):
    root.mkdir(parents=True)
    scenes, details = {}, {}
    for s in seeds:
        if s in no_scene:
            details[str(s)] = {'scene': None, 'gen_s': 600.0, 'error': 'no scene in 600.0 s'}
            continue
        name = f'find_dice_gen_s{s}.json'
        data = json.dumps({'seed': s}).encode()
        (root / name).write_bytes(data)
        scenes[str(s)] = name
        details[str(s)] = {'scene': name, 'sha256': hashlib.sha256(data).hexdigest(), 'n_cups': 2}
    man = {'what': 'w', 'generator': {'sha256': 'g'}, 'scenes': scenes, 'details': details, 'made': 'now'}
    man.update(manifest_extra or {})
    (root / 'manifest.json').write_text(json.dumps(man))
    return root


def test_merge_keeps_the_old_seeds_and_lists_a_seed_without_a_scene(tmp_path):
    old = _scene_folder(tmp_path / 'old', [100, 101])
    gen = _scene_folder(tmp_path / 'gen', [140, 141, 142], no_scene=(142,))
    old_manifest = json.loads((old / 'manifest.json').read_text())
    merged = pm.merge(str(gen), str(old))
    assert set(merged['scenes']) == {'100', '101', '140', '141'}
    assert merged['details']['142']['scene'] is None and '142' not in merged['scenes']
    assert {k: merged['details'][k] for k in ('100', '101')} == {k: old_manifest['details'][k] for k in ('100', '101')}
    assert merged['made'] == 'now' and merged['extensions'][0]['seeds'] == '140-142'
    assert merged['extensions'][0]['n_scenes'] == 2
    on_disk = json.loads((old / 'manifest.json').read_text())
    assert on_disk == merged
    for s in (100, 101, 140, 141):
        name = f'find_dice_gen_s{s}.json'
        assert hashlib.sha256((old / name).read_bytes()).hexdigest() == on_disk['details'][str(s)]['sha256']
    assert not (old / 'find_dice_gen_s142.json').exists()


def test_merge_never_replaces_a_seed_and_checks_the_hashes(tmp_path):
    old = _scene_folder(tmp_path / 'old', [100])
    with pytest.raises(SystemExit):                                   # seed 100 is in both
        pm.merge(str(_scene_folder(tmp_path / 'g1', [100, 140])), str(old))
    g2 = _scene_folder(tmp_path / 'g2', [140])
    (g2 / 'find_dice_gen_s140.json').write_bytes(b'tampered')
    with pytest.raises(SystemExit):
        pm.merge(str(g2), str(old))
    g3 = _scene_folder(tmp_path / 'g3', [141])
    (g3 / 'find_dice_gen_s999.json').write_bytes(b'{}')               # a file the manifest does not list
    with pytest.raises(SystemExit):
        pm.merge(str(g3), str(old))
    g4 = _scene_folder(tmp_path / 'g4', [142])
    (old / 'find_dice_gen_s142.json').write_bytes(b'{}')              # a file in the repo the manifest does not list
    with pytest.raises(SystemExit):
        pm.merge(str(g4), str(old))
    assert json.loads((old / 'manifest.json').read_text())['scenes'] == {'100': 'find_dice_gen_s100.json'}


def test_a_dry_run_changes_nothing(tmp_path):
    old = _scene_folder(tmp_path / 'old', [100])
    gen = _scene_folder(tmp_path / 'gen', [140])
    before = (old / 'manifest.json').read_text()
    assert pm.main([str(gen), '--scenes-dir', str(old), '--dry-run']) == 0
    assert (old / 'manifest.json').read_text() == before
    assert not (old / 'find_dice_gen_s140.json').exists()
