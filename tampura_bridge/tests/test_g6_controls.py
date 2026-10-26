"""#P4 B0: the G6 scoring-channel controls (PAPER_AUDIT.txt #P4, G6).

They exist from B0 on and FAIL until B2 (scoring.py, env_adapter.py) and B7
(a full episode) make them pass; the plan's deliverable for B0 is exactly
that.  The positive controls run first and must pass before any fault
injection counts:
  (1) a verified two-pad hold of the die body with the arm at
      DEFAULT_ARM_POS gives get_reward 1.0;
  (2) the same hold of a cup body gives 0.0.
Then the fault injections, each ending with rewards[-1] == 0.0:
  (3) go_home with no path;  (4) a failed lift;  (5) a slip after the lift.
The set-up calls these controls need (holds, faults) sit in
tools/bridge_gates_allowlist.txt as 'test control' when they are written.
Run in the arm-O venv (D12) with their trees on PYTHONPATH.
"""
import pytest


def _harness():
    """B2 replaces this with the real one: their FindDiceEnv on seed 0, the
    env adapter, the scoring adapter and TAMPURA's own get_reward."""
    from tampura_bridge import env_adapter, scoring  # noqa: F401  (B2)
    raise NotImplementedError('G6 control harness: written in B2')


def test_1_positive_die_hold_scores_one():
    _harness()


def test_2_positive_cup_hold_scores_zero():
    _harness()


def test_3_fault_go_home_without_path_scores_zero():
    _harness()


def test_4_fault_failed_lift_scores_zero():
    _harness()


def test_5_fault_slip_after_lift_scores_zero():
    _harness()


def test_readbacks_bit_identical_and_no_post_hoc_step():
    """G6: the arm readback at main() return equals the one at observation
    build bit for bit, and the executing client takes 0 physics steps
    between the last dispatched action and the observation build."""
    _harness()


def test_rollout_history_loads_in_their_venv():
    """G6 / D12: the RolloutHistory pickle loads in arm T's venv without
    tampura_bridge on PYTHONPATH (B1(j) tests the round trip)."""
    _harness()
