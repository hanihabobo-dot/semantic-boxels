"""Rule 18's five fields (wumpus/incidents.py), pure: no env, no PyBullet."""
from wumpus import incidents as inc


def test_a_success_without_incidents_is_clean():
    f = inc.fields(True, 0, 0)
    assert f == {'drops': 0, 'collisions': 0, 'drop_detector': inc.DROP_DETECTOR,
                 'collision_detector': inc.COLLISION_DETECTOR, 'clean_success': True}


def test_a_drop_or_a_collision_makes_a_success_unclean():
    assert inc.fields(True, 1, 0)['clean_success'] is False
    assert inc.fields(True, 0, 2)['clean_success'] is False


def test_a_failure_is_never_a_clean_success():
    assert inc.fields(False, 0, 0)['clean_success'] is False
    assert inc.fields(False, None, None)['clean_success'] is False


def test_no_detector_writes_not_detected_never_a_zero():
    f = inc.fields(True, None, None)
    assert f['drops'] is None and f['collisions'] is None
    assert f['drop_detector'] == f['collision_detector'] == 'not detected'
    assert f['clean_success'] is None            # a success, but nobody looked
    assert inc.fields(True, 0, None)['clean_success'] is None


def test_record_reads_the_env_or_says_not_detected():
    class Detecting:
        drops, collisions = 1, 0
        incidents = [{'kind': 'drop', 'how': 'the bar left the gripper'}]

    class Blind:                                  # a stand-in env without detectors
        pass
    r = inc.record(Detecting(), True)
    assert (r['drops'], r['collisions'], r['clean_success']) == (1, 0, False)
    assert r['incidents'] == Detecting.incidents and r['incidents'] is not Detecting.incidents
    b = inc.record(Blind(), True)
    assert b['drop_detector'] == 'not detected' and b['incidents'] == [] and b['clean_success'] is None


def test_line_prints_success_with_clean_success_beside_it():
    assert inc.line(inc.fields(True, 0, 0)) == 'drops 0, collisions 0, clean success yes'
    assert inc.line(inc.fields(True, 0, 1)) == 'drops 0, collisions 1, clean success no'
    assert inc.line(inc.fields(True, None, None)) == ('drops not detected, collisions not detected, '
                                                      'clean success not known')
