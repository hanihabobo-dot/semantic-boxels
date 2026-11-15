"""BF#59: tools/slip_eval.py's counting of the die's carries, losses and
pick tries from an episode's files.  The fixtures copy the campaign's check
episodes (2026-10-31): the driver's stdout.txt is the curated console (the
verified pick, the echoed ERROR lines, the goal check), the pipeline's
run_*.log holds every pipeline print once, and console_debug.log holds the
run log plus a "[console]" echo of every ERROR, action and curated line.
Each event must count once, whichever files exist."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tools'))
import slip_eval  # noqa: E402

# Two verified picks; the first lost after the lift, the second lost in the
# carry (carry_hold_check) and then found lost again by the goal check as a
# physics mismatch (a third loss, as base's goal check reports one).
RUN_LOG = """    Picking dice from dice...
    ERROR: grip lost after post-pick lift for dice — pad contacts=none (need both [12, 13]), obj_z=0.1
    Picking dice from dice...
    carry_hold_check: move to home holding dice: fingers 9.7/9.7 mm at the start, 9.8/9.8 mm at the end, width growth +0.100 mm, wrist travel 167.4 deg, pads at the end none (0 points, 0.00 N), position hold: LOST
    ERROR: grip lost in the carry for dice: pad contacts=none (need both [12, 13]), pad_normal_force=0.00N after the move to home. Opening gripper and replanning (BF#59 carry_hold_check).
    transit loss 1/3 for dice (review-fix strike counter)
  PHYSICAL_FAILURE (goal): (holding dice) — finger-pad contact incomplete: links none (need both [12, 13])
"""
STDOUT = """● Picking dice …
  ⎿ I have a firm grip on dice: its half-width is 10.2 mm, I expected 8.2 mm
⚠ ERROR: grip lost after post-pick lift for dice — pad contacts=none (need both [12, 13]), obj_z=0.1
● Picking dice …
  ⎿ I have a firm grip on dice: its half-width is 10.1 mm, I expected 8.2 mm
⚠ ERROR: grip lost in the carry for dice: pad contacts=none (need both [12, 13]), pad_normal_force=0.00N after the move to home. Opening gripper and replanning (BF#59 carry_hold_check).
⚠ PHYSICAL_FAILURE (goal): (holding dice) — finger-pad contact incomplete: links none (need both [12, 13])
✘ Failed. Belief said target was found but physics check disagreed (physics_mismatch)
"""
CONSOLE = RUN_LOG + ''.join(f"[console] {line}\n" for line in STDOUT.splitlines())


def _episode(tmp_path, stdout=STDOUT, run_log=RUN_LOG, console=CONSOLE):
    run = tmp_path / 'ours' / 'run_2026-10-31_20-03-53'
    run.mkdir(parents=True)
    if stdout is not None:
        (tmp_path / 'stdout.txt').write_text(stdout, encoding='utf-8')
    if run_log is not None:
        (run / 'run_2026-10-31_20-03-53.log').write_text(run_log, encoding='utf-8')
    if console is not None:
        (run / 'console_debug.log').write_text(console, encoding='utf-8')
    return str(tmp_path)


def test_each_event_counted_once(tmp_path):
    assert slip_eval.count_carries(_episode(tmp_path)) == (2, 3, 2)


def test_console_debug_is_the_fallback_without_its_echoes(tmp_path):
    assert slip_eval.count_carries(_episode(tmp_path, run_log=None)) == (2, 3, 2)


def test_stdout_alone(tmp_path):
    # A crash before the pipeline wrote its logs: the curated console only
    # (its echoed ERROR lines count, each once).
    assert slip_eval.count_carries(_episode(tmp_path, run_log=None, console=None)) == (2, 3, 2)


def test_no_stdout(tmp_path):
    # The verified picks come from the console log's curated lines then.
    assert slip_eval.count_carries(_episode(tmp_path, stdout=None)) == (2, 3, 2)


def test_empty_gripper_at_the_goal_is_not_a_loss(tmp_path):
    run_log = RUN_LOG.replace(
        "finger-pad contact incomplete: links none (need both [12, 13])",
        "no held object (gripper is empty)")
    stdout = STDOUT.replace(
        "finger-pad contact incomplete: links none (need both [12, 13])",
        "no held object (gripper is empty)")
    console = run_log + ''.join(f"[console] {line}\n" for line in stdout.splitlines())
    assert slip_eval.count_carries(_episode(tmp_path, stdout, run_log, console)) == (2, 2, 2)


def test_a_graze_at_the_goal_is_a_loss(tmp_path):
    run_log = RUN_LOG.replace(
        "finger-pad contact incomplete: links none (need both [12, 13])",
        "pads touch but squeeze force 0.12 N < 0.5 N — a graze, not a grasp")
    assert slip_eval.count_carries(_episode(tmp_path, run_log=run_log, console=None)) == (2, 3, 2)


def test_nothing(tmp_path):
    assert slip_eval.count_carries(str(tmp_path)) == (0, 0, 0)


@pytest.mark.parametrize('arm, fixes', [('base', 'none'), ('a', 'a'), ('a+b', 'a,b')])
def test_arm_fixes(arm, fixes):
    assert slip_eval.arm_fixes(arm) == fixes


# ---- path 14's find_dice check of the candidate defaults (2026-11-13):
# an arm with a driver flag, --scenes, --rotate.  No simulator: the driver
# is a stub that writes down what it was given.

@pytest.mark.parametrize('arm, fixes, args', [
    ('a+b@corridor_object', 'a,b', ['--corridor-test', 'object']),
    ('base@corridor_object', 'none', ['--corridor-test', 'object']),
    ('a+b', 'a,b', []),
])
def test_an_arm_carries_a_driver_flag(arm, fixes, args):
    assert slip_eval.arm_fixes(arm) == fixes
    assert slip_eval.arm_args(arm) == args


@pytest.mark.parametrize('arm', ['a@nonsense', 'a@corridor_object@corridor_object', '@corridor_object'])
def test_a_malformed_flag_arm_fails_before_any_run(arm):
    with pytest.raises(SystemExit):
        slip_eval.arm_fixes(arm)


def test_arm_order_rotates_by_seed_and_repetition():
    arms = ['p', 'q', 'r']
    assert slip_eval.arm_order(arms, 0, 0, False) == ['p', 'q', 'r']
    assert slip_eval.arm_order(arms, 5, 2, False) == ['p', 'q', 'r']
    assert [slip_eval.arm_order(arms, k, 0, True)[0] for k in range(4)] == ['p', 'q', 'r', 'p']
    assert slip_eval.arm_order(arms, 1, 1, True) == ['r', 'p', 'q']


STUB_DRIVER = r'''
import argparse, json, os, sys
ap = argparse.ArgumentParser()
for flag in ('--global-seed', '--vis', '--save-dir', '--allow-g19-mismatch', '--slip-fixes'):
    ap.add_argument(flag)
CORRIDOR_LINE
a = ap.parse_args()
problems = os.path.join('tampura_environments', 'find_dice', 'problems')
files = sorted(os.listdir(problems))
scene = files[int(a.global_seed) % len(files)]
print('Loading scene from ' + os.path.join(problems, scene))
print('config: ' + open(os.path.join('env_configs', 'find_dice.yml')).read().strip())
with open(os.path.join(a.save_dir, 'argv.json'), 'w') as f:
    json.dump({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'scenes': files}, f)
switches = {'slip_fixes': a.slip_fixes}
if hasattr(a, 'corridor_test'):
    switches['corridor_test'] = a.corridor_test
with open(os.path.join(a.save_dir, 'bridge_episode.json'), 'w') as f:
    json.dump({'outcome': {'status': 'success'}, 'rewards': [1.0], 'switches': switches,
               'scene_file': os.path.join(problems, scene)}, f)
'''
STUB_FIXES = '''
ENABLED = set()
def configure(value):
    ENABLED.clear()
    ENABLED.update(n for n in value.split(',') if n and n != 'none')
'''


def _snapshot(tmp_path, corridor=True):
    """A stand-in snapshot (a stub driver, a stub registry), their envs with
    two shipped scenes, and a scenes folder with a manifest."""
    snap = tmp_path / 'sb_stub'
    (snap / 'tampura_bridge').mkdir(parents=True)
    line = ("ap.add_argument('--corridor-test', default='cell+object')" if corridor else '')
    (snap / 'tampura_bridge' / 'run_bridge_on_finddice.py').write_text(
        STUB_DRIVER.replace('CORRIDOR_LINE', line), encoding='utf-8')
    (snap / 'test_full_pipeline.py').write_text('', encoding='utf-8')
    (snap / 'slip_fixes.py').write_text(STUB_FIXES, encoding='utf-8')
    envs = tmp_path / 'tampura_environments'
    (envs / 'env_configs').mkdir(parents=True)
    (envs / 'env_configs' / 'find_dice.yml').write_text('stub config\n', encoding='utf-8')
    shipped = envs / 'tampura_environments' / 'find_dice' / 'problems'
    shipped.mkdir(parents=True)
    for name in ('shipped_a.json', 'shipped_b.json'):
        (shipped / name).write_text('{}', encoding='utf-8')
    scenes = tmp_path / 'gen_scenes'
    scenes.mkdir()
    manifest = {'scenes': {'100': 'gen_s100.json', '101': 'gen_s101.json'}}
    for name in manifest['scenes'].values():
        (scenes / name).write_text('{}', encoding='utf-8')
    (scenes / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return str(snap), str(envs), str(scenes)


def _rows(out):
    with open(os.path.join(out, 'results.jsonl'), 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def _argv(row):
    with open(os.path.join(row['save_dir'], 'argv.json'), 'r', encoding='utf-8') as f:
        return json.load(f)


needs_linux = pytest.mark.skipif(not hasattr(os, 'uname'), reason='the harness runs in WSL or on a node')


@needs_linux
def test_scenes_flag_arm_and_rotation_end_to_end(tmp_path, monkeypatch):
    snap, envs, scenes = _snapshot(tmp_path)
    out = str(tmp_path / 'out')
    monkeypatch.setattr(slip_eval, 'pipeline_alive', lambda pid: [])
    monkeypatch.setenv('BRIDGE_SCENE_MANIFEST', os.path.join(scenes, 'manifest.json'))
    co = 'a+b@corridor_object'
    rc = slip_eval.main(['--snapshot', snap, '--out', out, '--arms', f'a,{co}',
                         '--seeds', '100-101', '--reps', '2', '--rep-seeds', '100-101',
                         '--cap', '60', '--python', sys.executable, '--cwd', envs,
                         '--scenes', scenes, '--rotate'])
    assert rc == 0
    rows = _rows(out)
    # every seed twice under both arms; the first arm changes by seed and repetition
    assert [(r['rep'], r['seed'], r['arm']) for r in rows] == [
        (0, 100, 'a'), (0, 100, co), (0, 101, co), (0, 101, 'a'),
        (1, 100, co), (1, 100, 'a'), (1, 101, 'a'), (1, 101, co)]
    for r in rows:
        seen = _argv(r)
        want = f"gen_s{r['seed']}.json"
        # the episode's folder held its one scene, and the row says so
        assert seen['scenes'] == [want]
        assert (r['scene'], r['scene_seen'], r['scene_ok']) == (want, want, True)
        assert r['bridge_status'] == 'success'
        i = seen['argv'].index('--slip-fixes')
        if r['arm'] == co:
            assert seen['argv'][i:i + 4] == ['--slip-fixes', 'a,b', '--corridor-test', 'object']
            assert r['arm_args'] == ['--corridor-test', 'object'] and r['fixes'] == 'a,b'
            # the driver's own record of what it ran with reaches the row
            assert r['switches'] == {'slip_fixes': 'a,b', 'corridor_test': 'object'}
        else:
            assert seen['argv'][i:i + 2] == ['--slip-fixes', 'a'] and '--corridor-test' not in seen['argv']
            assert 'arm_args' not in r
            assert r['switches'] == {'slip_fixes': 'a', 'corridor_test': 'cell+object'}
        # rule 18's fields are in every row (not detected here: the stub ran no pipeline)
        assert {'drops', 'collisions', 'clean_success'} <= set(r)
    # the episodes' folders are gone, the records stay
    assert os.listdir(os.path.join(out, 'cwd')) == []
    with open(os.path.join(out, 'metadata.json'), 'r', encoding='utf-8') as f:
        md = json.load(f)
    assert md['scenes'] == scenes and md['rotate'] is True
    assert md['arm_args'] == {'a': [], co: ['--corridor-test', 'object']}
    assert os.path.isfile(os.path.join(out, 'summary.txt'))


@needs_linux
def test_without_scenes_the_driver_runs_from_their_envs(tmp_path, monkeypatch):
    # BF#59's way, unchanged: the working directory is --cwd, the arms in the order given
    snap, envs, _ = _snapshot(tmp_path)
    out = str(tmp_path / 'out')
    monkeypatch.setattr(slip_eval, 'pipeline_alive', lambda pid: [])
    assert slip_eval.main(['--snapshot', snap, '--out', out, '--arms', 'base,a', '--seeds', '0-1',
                           '--cap', '60', '--python', sys.executable, '--cwd', envs]) == 0
    rows = _rows(out)
    assert [(r['seed'], r['arm']) for r in rows] == [(0, 'base'), (0, 'a'), (1, 'base'), (1, 'a')]
    for r in rows:
        seen = _argv(r)
        assert os.path.realpath(seen['cwd']) == os.path.realpath(envs)
        assert seen['scenes'] == ['shipped_a.json', 'shipped_b.json']
        assert 'scene' not in r and 'scene_ok' not in r
    assert not os.path.exists(os.path.join(out, 'cwd'))


@needs_linux
def test_a_flag_the_driver_lacks_fails_before_any_episode(tmp_path, monkeypatch):
    snap, envs, _ = _snapshot(tmp_path, corridor=False)
    out = str(tmp_path / 'out')
    monkeypatch.setattr(slip_eval, 'pipeline_alive', lambda pid: [])
    with pytest.raises(SystemExit) as e:
        slip_eval.main(['--snapshot', snap, '--out', out, '--arms', 'a,a@corridor_object',
                        '--seeds', '0', '--cap', '60', '--python', sys.executable, '--cwd', envs])
    assert '--corridor-test' in str(e.value)
    assert not os.path.exists(os.path.join(out, 'results.jsonl'))


def test_load_scenes_needs_the_seeds_and_the_pinned_manifest(tmp_path, monkeypatch):
    _, _, scenes = _snapshot(tmp_path)
    manifest = os.path.join(scenes, 'manifest.json')
    monkeypatch.delenv('BRIDGE_SCENE_MANIFEST', raising=False)
    with pytest.raises(SystemExit):            # G19 would not pin these seeds
        slip_eval.load_scenes(scenes, [100])
    monkeypatch.setenv('BRIDGE_SCENE_MANIFEST', manifest)
    assert slip_eval.load_scenes(scenes, [101, 100]) == {101: 'gen_s101.json', 100: 'gen_s100.json'}
    with pytest.raises(SystemExit):            # no scene for seed 102
        slip_eval.load_scenes(scenes, [100, 102])
    with pytest.raises(SystemExit):            # no manifest
        slip_eval.load_scenes(str(tmp_path), [100])


def test_scene_seen_falls_back_to_the_console(tmp_path):
    (tmp_path / 'stdout.txt').write_text(
        'x\nLoading scene from tampura_environments/find_dice/problems/gen_s100.json\n', encoding='utf-8')
    assert slip_eval.scene_seen({'scene_file': 'gen_s101.json', 'save_dir': str(tmp_path)}) == 'gen_s101.json'
    assert slip_eval.scene_seen({'scene_file': 'None', 'save_dir': str(tmp_path)}) == 'gen_s100.json'
    assert slip_eval.scene_seen({'save_dir': str(tmp_path / 'nothing')}) is None
