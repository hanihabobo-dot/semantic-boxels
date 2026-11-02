"""BF#59: tools/slip_eval.py's counting of the die's carries, losses and
pick tries from an episode's files.  The fixtures copy the campaign's check
episodes (2026-10-31): the driver's stdout.txt is the curated console (the
verified pick, the echoed ERROR lines, the goal check), the pipeline's
run_*.log holds every pipeline print once, and console_debug.log holds the
run log plus a "[console]" echo of every ERROR, action and curated line.
Each event must count once, whichever files exist."""
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
