"""TB-22: the record fields of tracks rule 18 (world_counts.py).

drops, collisions, drop_detector, collision_detector and clean_success in
every episode record; "a 0 is never written where nothing could see the
event".  Pure functions and two small files: no simulator, no episode.
"""
import json

from world import world_counts as wc

DROP = {'object': 'green_object', 'phase': 'move', 't': 12.5,
        'how': 'left the finger pads with no release commanded'}
KNOCK = {'object': 'red_object', 'phase': 'move', 't': 12.4, 'moved_mm': 8.0}


def test_every_record_carries_the_five_fields():
    for fields in (wc.not_detected(True),
                   wc.episode_fields(True, {'drops': [], 'collisions': []}),
                   wc.kinematic_arm_fields(True)):
        assert set(wc.FIELDS) <= set(fields)


def test_nothing_watched_is_not_a_zero():
    f = wc.not_detected(True)
    assert f['drops'] is None and f['collisions'] is None
    assert f['drop_detector'] == f['collision_detector'] == 'not detected'
    assert f['clean_success'] is None            # a success nobody watched
    assert wc.not_detected(False)['clean_success'] is False
    assert wc.episode_fields(True, None) == wc.not_detected(True)


def test_a_watched_episode_without_events_is_a_clean_success():
    f = wc.episode_fields(True, {'drops': [], 'collisions': []},
                          drops_noticed=0, collisions_reported=0)
    assert (f['drops'], f['collisions'], f['clean_success']) == (0, 0, True)
    assert f['drop_detector'] == wc.DROP_DETECTOR
    assert f['collision_detector'] == wc.COLLISION_DETECTOR
    assert (f['drops_noticed'], f['collisions_reported']) == (0, 0)


def test_a_drop_or_a_knock_makes_a_success_unclean():
    f = wc.episode_fields(True, {'drops': [DROP], 'collisions': []})
    assert (f['drops'], f['clean_success']) == (1, False)
    assert f['drop_events'] == [DROP]
    f = wc.episode_fields(True, {'drops': [], 'collisions': [KNOCK, KNOCK]})
    assert (f['collisions'], f['clean_success']) == (2, False)
    # a failure is never a clean success, whatever the counts
    assert wc.episode_fields(False, {'drops': [], 'collisions': []}
                             )['clean_success'] is False


def test_the_monitors_knocked_off_table_adds_a_body_once():
    events = [{'kind': 'knocked_off_table', 'object': 'blue_object',
               'label': 'move to free_3'},
              {'kind': 'knocked_off_table', 'object': 'blue_object',
               'label': 'place'},
              {'kind': 'knocked_off_table', 'object': 'red_object',
               'label': 'place'},                 # telemetry counted it
              {'kind': 'knocked_off_table', 'object': 'green_object',
               'label': 'place'},                 # that was the drop
              {'kind': 'disturbed', 'object': 'yellow_object'}]
    f = wc.episode_fields(True, {'drops': [DROP], 'collisions': [KNOCK]},
                          integrity_events=events)
    assert f['collisions'] == 2
    assert f['collision_events'][1] == {'object': 'blue_object',
                                        'phase': 'move to free_3',
                                        'source': 'knocked_off_table'}


def test_another_success_verdict_recomputes_clean_success_only():
    f = wc.episode_fields(True, {'drops': [], 'collisions': []})
    g = wc.with_success(f, False)
    assert g['clean_success'] is False and f['clean_success'] is True
    assert {k: g[k] for k in g if k != 'clean_success'} == \
        {k: f[k] for k in f if k != 'clean_success'}
    assert wc.with_success(wc.not_detected(False), True)['clean_success'] is None


def test_a_kinematic_carry_cannot_drop():
    f = wc.kinematic_arm_fields(True)
    assert f['drops'] == 0 and f['drop_detector'].startswith('cannot happen')
    # their execution reports no collision: unknown, so the success is not
    # called clean
    assert f['collisions'] is None
    assert f['collision_detector'].startswith('not detected')
    assert f['clean_success'] is None
    assert wc.kinematic_arm_fields(False)['clean_success'] is False
    g = wc.kinematic_arm_fields(True, collisions=0,
                                collision_detector='their collided place')
    assert (g['collisions'], g['clean_success']) == (0, True)


def _write(path, data):
    path.write_text(json.dumps(data), encoding='utf-8')


def test_a_run_directory_with_a_summary(tmp_path):
    fields = wc.episode_fields(True, {'drops': [DROP], 'collisions': []},
                               drops_noticed=1, collisions_reported=0)
    _write(tmp_path / wc.SUMMARY_FILE, {'success': True, **fields})
    got = wc.from_run_dir(str(tmp_path))
    assert got == fields
    # the harness's own verdict in place of the pipeline's
    assert wc.from_run_dir(str(tmp_path), success=False)['clean_success'] is False


def test_a_killed_run_keeps_its_counts(tmp_path):
    # No summary (killed at the cap): the counts file telemetry kept.
    _write(tmp_path / wc.COUNTS_FILE,
           {'drops': [DROP], 'collisions': [KNOCK], 'closed': False})
    got = wc.from_run_dir(str(tmp_path), success=False)
    assert (got['drops'], got['collisions'], got['clean_success']) == (1, 1, False)
    assert 'the run wrote no summary' in got['drop_detector']


def test_a_run_directory_with_nothing_or_an_old_summary(tmp_path):
    assert wc.from_run_dir(str(tmp_path))['drops'] is None
    assert wc.from_run_dir(None)['drop_detector'].startswith('not detected')
    # a summary written before TB-22 has no fields: not detected, never 0
    _write(tmp_path / wc.SUMMARY_FILE, {'success': True, 'plan_count': 3})
    got = wc.from_run_dir(str(tmp_path), success=True)
    assert got['drops'] is None and got['clean_success'] is None


def test_the_newest_new_run_directory_with_counts(tmp_path):
    for name in ('run_a', 'run_b', 'run_c', 'other'):
        (tmp_path / name).mkdir()
    _write(tmp_path / 'run_a' / wc.COUNTS_FILE, {})
    _write(tmp_path / 'run_b' / wc.COUNTS_FILE, {})
    _write(tmp_path / 'other' / wc.COUNTS_FILE, {})
    assert wc.newest_counts_dir(str(tmp_path), {'run_a'}) == \
        str(tmp_path / 'run_b')
    assert wc.newest_counts_dir(str(tmp_path), {'run_a', 'run_b'}) is None
    assert wc.newest_counts_dir(str(tmp_path / 'missing'), set()) is None
