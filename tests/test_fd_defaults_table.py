"""Path 14 (2026-11-13): tools/fd_defaults_table.py, the table of the
find_dice check of the candidate defaults.  Its tests against hand-counted
values, and its counting rules (void, incomplete, the cap, the sets) on rows
built here; no simulator and no run."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tools'))
import fd_defaults_table as t  # noqa: E402

ARMS = [t.DEF, t.DEFTRAP, t.TRAP, t.CO]
NAMES = {'def': t.DEF, 'deftrap': t.DEFTRAP, 'trap': t.TRAP, 'deftrap_co': t.CO}


def test_mcnemar_exact():
    assert t.mcnemar_exact(0, 0) == 1.0
    assert t.mcnemar_exact(6, 0) == pytest.approx(0.03125)
    assert t.mcnemar_exact(0, 5) == pytest.approx(0.0625)
    assert t.mcnemar_exact(5, 1) == pytest.approx(0.21875)
    assert t.mcnemar_exact(3, 3) == 1.0


def test_fisher_two_sided():
    # 5 of 5 against 0 of 5: the two extreme tables of C(10, 5) = 252
    assert t.fisher_two_sided(5, 5, 0, 5) == pytest.approx(2 / 252)
    # 4 of 52 against 0 of 60: C(52, 4) / C(112, 4); the other extreme is likelier
    assert t.fisher_two_sided(4, 52, 0, 60) == pytest.approx(270725 / 6210820)
    assert t.fisher_two_sided(0, 60, 0, 60) == 1.0
    assert t.fisher_two_sided(3, 10, 3, 10) == 1.0
    assert t.fisher_two_sided(1, 0, 0, 5) == 1.0


def test_clopper_pearson():
    lo, hi = t.clopper_pearson(0, 60)
    assert lo == 0.0 and hi == pytest.approx(1 - 0.025 ** (1 / 60), abs=1e-6)
    lo, hi = t.clopper_pearson(60, 60)
    assert hi == 1.0 and lo == pytest.approx(0.025 ** (1 / 60), abs=1e-6)
    lo, hi = t.clopper_pearson(1, 10)          # the textbook interval of 1 of 10
    assert lo == pytest.approx(0.00253, abs=1e-4) and hi == pytest.approx(0.44502, abs=1e-4)


def flat(text):
    """The table with every run of blanks as one: the asserts do not count columns."""
    return ' '.join(text.split())


def row(arm, seed, rep=0, status='success', outcome='success', carries=1, losses=0,
        timed_out=False, planning=2.0, calls=1, wall=30.0, exec_s=10.0, **more):
    r = {'arm': arm, 'seed': seed, 'rep': rep, 'bridge_status': status, 'timed_out': timed_out,
         'carries': carries, 'losses': losses, 'pick_tries': carries,
         'drops': 0, 'collisions': 0, 'clean_success': status == 'success' and outcome == 'success',
         'metrics': {'outcome': outcome, 'wall_s': wall, 'planning_s': planning,
                     'plan_calls': calls, 'exec_s': exec_s}}
    r.update(more)
    return r


def job(tmp_path, name, rows, scenes=None, snapshot='sb_abc1234', arms=ARMS):
    d = tmp_path / name
    d.mkdir()
    (d / 'metadata.json').write_text(json.dumps(
        {'snapshot_name': snapshot, 'arms': arms, 'scenes': scenes, 'host': 'cn-1', 'job': name,
         'cap_s': 900 if scenes else 600}), encoding='utf-8')
    (d / 'results.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    return str(d)


def base_rows(seeds, reps=(0,), **more):
    return {(arm, s, rep): row(arm, s, rep, **more) for rep in reps for s in seeds for arm in ARMS}


def test_the_declared_comparisons_on_set_s(tmp_path):
    rows = base_rows(range(6))
    for s in (0, 1, 2, 3):                     # trap loses the die on four seeds
        rows[(t.TRAP, s, 0)] = row(t.TRAP, s, status='failure',
                                   outcome='failure (physics_mismatch)', losses=1)
    rows[(t.TRAP, 5, 0)] = row(t.TRAP, 5, status=None, outcome=None, timed_out=True, carries=0)
    rows[(t.CO, 4, 0)] = row(t.CO, 4, status='failure', outcome=t.NO_PLAN, carries=0,
                             planning=6.0, calls=2, wall=40.0)
    for s in range(6):                         # the trapezoid's execution takes a fifth longer
        rows[(t.DEFTRAP, s, 0)]['metrics']['exec_s'] = 12.0
    text = flat(t.table([job(tmp_path, 'S_1', list(rows.values()))], NAMES))
    assert '== set S, the shipped scenes: snapshot sb_abc1234, 24 rows, 6 seed-and-repetition pairs' in text
    assert 'losses per carry: trap 4 of 5, def 0 of 6' in text
    assert f"Fisher's exact p = {t.fisher_two_sided(4, 5, 0, 6):.3f}" in text
    # the cap is a failure of its arm and not void
    assert 'at the cap 1 of 6' in text
    assert 'success, by seed and repetition, 6 pairs: both 1, only def 5, only trap 0, neither 0, exact McNemar p = 0.062' in text
    assert 'at the cap, by seed and repetition, 6 pairs: both 0, only def 0, only trap 1' in text
    assert ('ended with no plan, by seed and repetition, 6 pairs: both 0, only deftrap 0, '
            'only deftrap_co 1, neither 5') in text
    # the times are paired over the pairs both ran to the close: all six, the no-plan one slower
    assert 'planning time per plan call, 6 pairs both ran to the close' in text
    assert 'deftrap_co slower in 1, faster in 0' in text
    assert 'cost: execution time of deftrap over def, 6 pairs both ran to the close: median ratio x1.20' in text
    assert 'by scene' not in text              # set S has no scene line
    assert 'deftrap_co seed 4 rep 0: failure (planner_failed)' in text
    assert ' trap seed 5 rep 0: at the cap' in text


def test_a_crash_voids_its_seed_and_repetition_for_every_arm(tmp_path):
    rows = base_rows(range(4))
    rows[(t.DEFTRAP, 2, 0)] = row(t.DEFTRAP, 2, status=None, outcome=None, carries=0)
    del rows[(t.CO, 3, 0)]                     # a cut job: one arm has no row
    text = flat(t.table([job(tmp_path, 'S_1', list(rows.values()))], NAMES))
    assert '2 seed-and-repetition pairs counted for every arm' in text
    assert 'void for every arm (a crash or another scene): s2r0' in text
    assert 'incomplete (an arm has no row): s3r0' in text
    assert text.count(': 2 episodes') == 4     # every arm on the same two pairs


def test_set_g_another_scene_is_void_and_the_first_repetition_stands_alone(tmp_path):
    rows = base_rows((100, 101, 102), reps=(0, 1), scene_ok=True)
    rows[(t.TRAP, 101, 1)]['scene_ok'] = False
    rows[(t.TRAP, 100, 0)] = row(t.TRAP, 100, status='failure', outcome='failure (pick_giveup)',
                                 losses=1, scene_ok=True)
    half = list(rows.values())
    text = flat(t.table([job(tmp_path, 'G_1', half[:12], scenes='/x/gen'),
                    job(tmp_path, 'G_2', half[12:], scenes='/x/gen')], NAMES))
    assert '== set G, the generated scenes' in text and '5 seed-and-repetition pairs' in text
    assert 'void for every arm (a crash or another scene): s101r1' in text
    assert 'success, by scene (the first repetition alone), 3 pairs: both 2, only def 1, only trap 0' in text
    assert 'success, by seed and repetition, 5 pairs: both 4, only def 1, only trap 0' in text


def test_the_corridor_test_each_arm_ran_with(tmp_path):
    rows = base_rows(range(3))
    for (arm, _, _), r in rows.items():
        r['switches'] = {'corridor_test': 'object' if arm == t.CO else 'cell+object'}
    rows[(t.CO, 1, 0)]['switches'] = {'corridor_test': 'cell+object'}    # the flag did not arrive
    del rows[(t.TRAP, 2, 0)]['switches']                                  # a run that left no record
    text = flat(t.table([job(tmp_path, 'S_1', list(rows.values()))], NAMES))
    assert ' def cell+object in 3 of 3, not recorded in 0' in text
    assert ' trap cell+object in 2 of 3, not recorded in 1' in text
    assert ('deftrap_co object in 2 of 3, not recorded in 0, ANOTHER VALUE in 1: '
            'the arm did not run as named') in text
    # a driver without the pass-through records no value: nothing is called wrong
    plain = flat(t.table([job(tmp_path, 'S_2', list(base_rows(range(2)).values()))], NAMES))
    assert 'deftrap_co object in 0 of 2, not recorded in 2' in plain and 'ANOTHER VALUE' not in plain


def test_the_sets_are_separate_and_other_code_is_refused(tmp_path):
    s = job(tmp_path, 'S_1', list(base_rows(range(2)).values()))
    g = job(tmp_path, 'G_1', list(base_rows((100,), scene_ok=True).values()), scenes='/x/gen')
    text = flat(t.table([s, g], NAMES))
    assert text.index('== set S') < text.index('== set G')
    assert '8 rows, 2 seed-and-repetition pairs' in text and '4 rows, 1 seed-and-repetition pairs' in text
    other = job(tmp_path, 'S_2', list(base_rows((5,)).values()), snapshot='sb_fffffff')
    with pytest.raises(SystemExit):
        t.table([s, other], NAMES)


def test_main_writes_the_table(tmp_path, capsys):
    s = job(tmp_path, 'S_1', list(base_rows(range(2)).values()))
    out = tmp_path / 'table.txt'
    assert t.main([s, '--out', str(out)]) == 0
    assert out.read_text(encoding='utf-8').strip() == capsys.readouterr().out.strip()
