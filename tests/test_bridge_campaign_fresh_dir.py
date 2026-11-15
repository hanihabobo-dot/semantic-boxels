"""D-15: arm T's episode starts in an empty folder.  A folder an earlier run
left there (an episode cut by a kill and run again on resume, or a relaunch
into the same --out) is renamed to the first free sibling <name>.stale<k>,
never deleted, and the record says where it went.  No interpreter runs here:
run_capped and the history reader are patched, so these tests run under
Windows and Linux Python alike."""
import glob
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'tools'))
import _bridge_campaign as bc  # noqa: E402
import gen_scene_eval as gse  # noqa: E402

SCENE = 'find_dice_s7.json'


def _campaign_args(out):
    # the fields main() gives episode_t
    return types.SimpleNamespace(
        out=str(out), venv_t='/venv_t', venv_o='/venv_o',
        snapshot=REPO, mode='full', cap=60.0, their_envs=str(out),
        pythonhashseed='0', tampura_work='/tampura-work',
        pddlstream_lib='/pddlstream_lib', drop_t_history=False)


def _old_run(d, tag='old'):
    """What a run cut by a kill leaves: three spans of 10 s, its pickle, a
    final world that passed, its G13 file, two logs with a SymK time (one
    beside the console, one under logs/) and its console.  Returns the
    folder's listing."""
    os.makedirs(os.path.join(d, 'logs'), exist_ok=True)
    for i in range(3):
        bc.append_jsonl(os.path.join(d, 'get_action_spans.jsonl'),
                        {'step': i, 'get_action_s': 10.0, 'action': tag})
    with open(os.path.join(d, '2026-11-13_10-00-00.pkl'), 'wb') as f:
        f.write(b'old history')
    bc.write_json(os.path.join(d, 'final_world.json'), {'ok': True, 'standard_success': True})
    bc.write_json(os.path.join(d, 'g13_runtime.json'), {'ok': True})
    for name in ('run.log', os.path.join('logs', 'run.log')):
        with open(os.path.join(d, name), 'w') as f:
            f.write('Loading scene from /scenes/old.json\nTime: 12.5\n')
    with open(os.path.join(d, 'console.txt'), 'w') as f:
        f.write('Loading scene from /scenes/old.json\n')
    with open(os.path.join(d, f'marker_{tag}.txt'), 'w') as f:
        f.write(tag)
    return _listing(d)


def _listing(d):
    return sorted(os.path.relpath(os.path.join(r, n), d)
                  for r, ds, fs in os.walk(d) for n in ds + fs)


def _patch_new_run(monkeypatch):
    """The new run: its console, two spans (1 s, 2 s) appended as
    timed_policy.py appends them, no pickle, no final world, no G13 file,
    no log, rc 1.  Returns the list of (save_dir, its listing when the run
    began)."""
    starts = []

    def run_capped(cmd, cwd, env, cap, console):
        save_dir = cmd[cmd.index('--save-dir') + 1]
        starts.append((save_dir, sorted(os.listdir(save_dir))))
        with open(console, 'w') as f:
            f.write(f'Loading scene from /scenes/{SCENE}\n')
        for i, s in enumerate((1.0, 2.0)):
            bc.append_jsonl(os.path.join(save_dir, 'get_action_spans.jsonl'),
                            {'step': i, 'get_action_s': s, 'action': 'new'})
        return 1, 5.0, 5.0, False

    def read_history_t(a, save_dir):
        # as the real reader: the newest *.pkl anywhere under the folder
        pks = sorted(glob.glob(os.path.join(save_dir, '**', '*.pkl'), recursive=True),
                     key=os.path.getmtime)
        if not pks:
            return {'history': False}            # as the real reader: no pickle, no read error
        return {'history': True, 'pkl': pks[-1], 'rewards': [0.0, 1.0],
                'time_deltas': [4.0, 9.0], 'actions': ['old', 'old']}

    monkeypatch.setattr(bc, 'run_capped', run_capped)
    monkeypatch.setattr(bc, 'read_history_t', read_history_t)
    return starts


def _assert_only_the_new_run(rec):
    assert rec['get_action_spans'] == [1.0, 2.0]
    assert rec['get_action_actions'] == ['new', 'new']
    assert rec['planning_s'] == 3.0
    assert rec['status'] == 'crashed' and rec['censored'] and not rec['success']
    assert rec['history_read'] == {'history': False}
    assert rec['final_world'] is None
    assert rec['standard_read'] is False and rec['standard_success'] is False
    assert rec['g13_ok'] is None
    assert rec['scene_file'] == f'/scenes/{SCENE}' and rec['scene_ok'] is True
    assert rec['symk_solve_s'] is None


def test_a_fresh_folder_is_made_and_nothing_moves(tmp_path, monkeypatch):
    starts = _patch_new_run(monkeypatch)
    rec = bc.episode_t(_campaign_args(tmp_path), 0, 7, 0, {7: SCENE}, [])
    t_dir = os.path.join(str(tmp_path), 'rep0', 'T')
    save_dir = os.path.join(t_dir, 'seed7')
    assert rec['save_dir'] == save_dir and starts == [(save_dir, [])]
    assert rec['stale_dir_moved_to'] is None
    assert rec['note'] == ''
    assert os.listdir(t_dir) == ['seed7']
    _assert_only_the_new_run(rec)


def test_a_resume_after_a_kill_reads_only_the_new_run(tmp_path, monkeypatch):
    t_dir = os.path.join(str(tmp_path), 'rep0', 'T')
    save_dir = os.path.join(t_dir, 'seed7')
    old = _old_run(save_dir)
    starts = _patch_new_run(monkeypatch)
    rec = bc.episode_t(_campaign_args(tmp_path), 0, 7, 0, {7: SCENE}, [])
    stale = os.path.join(t_dir, 'seed7.stale1')
    assert starts == [(save_dir, [])]
    _assert_only_the_new_run(rec)
    assert rec['stale_dir_moved_to'] == stale
    assert f'moved to {stale}; ' in rec['note']
    assert sorted(os.listdir(t_dir)) == ['seed7', 'seed7.stale1']
    assert _listing(stale) == old
    assert len(bc.read_jsonl(os.path.join(stale, 'get_action_spans.jsonl'))) == 3


def test_a_second_relaunch_takes_the_next_free_name(tmp_path, monkeypatch):
    t_dir = os.path.join(str(tmp_path), 'rep0', 'T')
    save_dir = os.path.join(t_dir, 'seed7')
    first = _old_run(os.path.join(t_dir, 'seed7.stale1'), 'first')
    second = _old_run(save_dir, 'second')
    _patch_new_run(monkeypatch)
    rec = bc.episode_t(_campaign_args(tmp_path), 0, 7, 0, {7: SCENE}, [])
    assert rec['stale_dir_moved_to'] == os.path.join(t_dir, 'seed7.stale2')
    assert sorted(os.listdir(t_dir)) == ['seed7', 'seed7.stale1', 'seed7.stale2']
    assert _listing(os.path.join(t_dir, 'seed7.stale1')) == first
    assert _listing(os.path.join(t_dir, 'seed7.stale2')) == second
    _assert_only_the_new_run(rec)


def test_an_empty_folder_is_not_moved(tmp_path, monkeypatch):
    t_dir = os.path.join(str(tmp_path), 'rep0', 'T')
    os.makedirs(os.path.join(t_dir, 'seed7'))
    _patch_new_run(monkeypatch)
    rec = bc.episode_t(_campaign_args(tmp_path), 0, 7, 0, {7: SCENE}, [])
    assert rec['stale_dir_moved_to'] is None
    assert rec['note'] == ''
    assert os.listdir(t_dir) == ['seed7']
    _assert_only_the_new_run(rec)


def test_the_stall_rerun_folder_takes_the_same_path(tmp_path, monkeypatch):
    t_dir = os.path.join(str(tmp_path), 'rep0', 'T')
    rerun = os.path.join(t_dir, 'seed7_rerun')
    old = _old_run(rerun)
    starts = _patch_new_run(monkeypatch)
    rec = bc.episode_t(_campaign_args(tmp_path), 0, 7, 0, {7: SCENE}, [], stall_rerun=True)
    stale = os.path.join(t_dir, 'seed7_rerun.stale1')
    assert rec['save_dir'] == rerun and starts == [(rerun, [])]
    assert rec['stall_rerun'] is True
    assert rec['stale_dir_moved_to'] == stale
    assert sorted(os.listdir(t_dir)) == ['seed7_rerun', 'seed7_rerun.stale1']
    assert _listing(stale) == old
    _assert_only_the_new_run(rec)


def test_gen_scene_eval_run_one_moves_an_old_folder_the_same_way(tmp_path, monkeypatch):
    # run_one builds episode_t's arguments itself (out = OUT/T on attempt 1);
    # os.uname and the episode's working folder are patched as in
    # test_gen_scene_eval.py
    monkeypatch.setattr(os, 'uname', lambda: types.SimpleNamespace(nodename='testnode'),
                        raising=False)

    def plain_cwd(a, arm, seed, rep, attempt, scene):
        d = os.path.join(str(tmp_path), 'cwd', f'{arm}_s{seed}_r{rep}_a{attempt}')
        os.makedirs(d, exist_ok=True)
        return d
    monkeypatch.setattr(gse, 'episode_cwd', plain_cwd)
    monkeypatch.setattr(bc, 'machine_check', lambda: [])
    a = types.SimpleNamespace(out=os.path.join(str(tmp_path), 'OUT'), snapshot=REPO,
                              venv_t='/venv_t', tampura_work='/tampura-work', cap=60.0,
                              shots='none', cups={})
    t_dir = os.path.join(a.out, 'T', 'rep0', 'T')
    save_dir = os.path.join(t_dir, 'seed7')
    old = _old_run(save_dir)
    starts = _patch_new_run(monkeypatch)
    row = gse.run_one(a, 'T', 7, 0, 1, SCENE, 0)
    rec = row['rec']
    stale = os.path.join(t_dir, 'seed7.stale1')
    assert starts == [(save_dir, [])]
    assert rec['save_dir'] == save_dir and rec['stale_dir_moved_to'] == stale
    assert sorted(os.listdir(t_dir)) == ['seed7', 'seed7.stale1']
    assert _listing(stale) == old
    _assert_only_the_new_run(rec)
    # the patched run ends without a readable result: since 14 Nov that is a failure of the arm and counts
    assert row['counts'] and not row['success']


def test_a_stall_rerun_leaves_the_stalled_run_in_place(tmp_path, monkeypatch):
    # main(): a stalled episode's record cites seed7; its re-run goes to
    # seed7_rerun and must not move seed7
    t_dir = os.path.join(str(tmp_path), 'rep0', 'T')
    _patch_new_run(monkeypatch)
    a = _campaign_args(tmp_path)
    stalled = bc.episode_t(a, 0, 7, 0, {7: SCENE}, [])
    kept = _listing(stalled['save_dir'])
    rec = bc.episode_t(a, 0, 7, 1, {7: SCENE}, [], stall_rerun=True)
    assert stalled['stale_dir_moved_to'] is None and rec['stale_dir_moved_to'] is None
    assert sorted(os.listdir(t_dir)) == ['seed7', 'seed7_rerun']
    assert _listing(stalled['save_dir']) == kept
    assert len(bc.read_jsonl(os.path.join(stalled['save_dir'], 'get_action_spans.jsonl'))) == 2
    _assert_only_the_new_run(rec)


def test_a_file_with_the_next_name_counts_as_taken(tmp_path):
    d = os.path.join(str(tmp_path), 'seed7')
    _old_run(d)
    with open(d + '.stale1', 'w') as f:
        f.write('not a folder')
    assert bc.move_stale_dir(d) == d + '.stale2'
    assert sorted(os.listdir(str(tmp_path))) == ['seed7.stale1', 'seed7.stale2']
    assert bc.move_stale_dir(d) is None
