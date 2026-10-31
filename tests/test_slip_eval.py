"""BF#59: tools/slip_eval.py's counting of the die's carries, losses and
pick tries from an episode's files, each line counted in one file (the
campaign's check episodes showed the pipeline's prints in both
console_debug.log and run_*.log, and the curated console lines in
stdout.txt and console_debug.log)."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tools'))
import slip_eval  # noqa: E402

STDOUT = """[console]   ⎿ I have a firm grip on dice: its half-width is 10.2 mm, I expected 8.2 mm
some driver line
[console]   ⎿ I have a firm grip on dice: its half-width is 10.1 mm, I expected 8.2 mm
  PHYSICAL_FAILURE (goal): (holding dice) not satisfied in the world
  PHYSICAL_FAILURE (goal): (holding dice) repeated by the driver
"""
PIPE = """    Picking dice from dice...
[console]   ⎿ I have a firm grip on dice: its half-width is 10.2 mm, I expected 8.2 mm
    ERROR: grip lost after post-pick lift for dice, pad contacts=none (need both [12, 13])
    Picking dice from dice...
[console]   ⎿ I have a firm grip on dice: its half-width is 10.1 mm, I expected 8.2 mm
    carry_hold_check: move to home holding dice: fingers 9.7/9.7 mm at the start, 9.8/9.8 mm at the end, width growth +0.100 mm, wrist travel 167.4 deg, pads at the end none (0 points, 0.00 N), position hold: LOST
    ERROR: grip lost in the carry for dice: pad contacts=none (need both [12, 13]), pad_normal_force=0.00N after the move to home. Opening gripper and replanning (BF#59 carry_hold_check).
"""
RUN_LOG = PIPE.replace("[console]   ⎿ I have a firm grip on dice: its half-width is 10.2 mm, I expected 8.2 mm\n", "") \
              .replace("[console]   ⎿ I have a firm grip on dice: its half-width is 10.1 mm, I expected 8.2 mm\n", "")


def _episode(tmp_path, stdout=STDOUT, console=PIPE, run_log=RUN_LOG):
    run = tmp_path / 'ours' / 'run_2026-10-31_20-03-53'
    run.mkdir(parents=True)
    if stdout is not None:
        (tmp_path / 'stdout.txt').write_text(stdout, encoding='utf-8')
    if console is not None:
        (run / 'console_debug.log').write_text(console, encoding='utf-8')
    if run_log is not None:
        (run / 'run_2026-10-31_20-03-53.log').write_text(run_log, encoding='utf-8')
    return str(tmp_path)


def test_each_line_counted_once(tmp_path):
    # Two verified picks, one lift loss, one carry loss, one goal loss
    # (printed twice by the driver), two pick tries; the run log repeats
    # the pipeline's prints and must not double them.
    assert slip_eval.count_carries(_episode(tmp_path)) == (2, 3, 2)


def test_run_log_is_the_fallback(tmp_path):
    assert slip_eval.count_carries(_episode(tmp_path, console=None)) == (2, 3, 2)


def test_stdout_alone(tmp_path):
    # A crash before the pipeline wrote its logs: the curated console only.
    assert slip_eval.count_carries(_episode(tmp_path, console=None, run_log=None)) == (2, 1, 0)


def test_nothing(tmp_path):
    assert slip_eval.count_carries(str(tmp_path)) == (0, 0, 0)


@pytest.mark.parametrize('arm, fixes', [('base', ''), ('a', 'a'), ('a+b', 'a,b')])
def test_arm_fixes(arm, fixes):
    assert slip_eval.arm_fixes(arm) == fixes
