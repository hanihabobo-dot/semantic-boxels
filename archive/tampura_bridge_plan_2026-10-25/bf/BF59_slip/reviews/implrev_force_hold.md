# BF#59 implementation review: force_hold (slip/force_hold d3a0411)

Reviewed 2026-10-31 by the orchestrating session: the code read at 19:45
from the diff against 05dcaf3 (robot_utils +99, policy.py +27,
boxel_env +26, allowlist +4, tests +248), the verdict at 20:25 after the
implementer's jam probe (reviews/impl_force_hold.md, "Jam probe").

## Verdict: accept, no change requested; the cup release jam is base's own

1. The switch. Registered at robot_utils' import (imported on both
   paths); `slip_fixes.on('force_hold')` at three places, each a block
   after the existing code: the hold in close_gripper_until_contact after
   the 60-step position hold (target width - 4 mm per finger at 10 N,
   persisting through the lift and the carry until open_gripper's 0.04 m
   at 200 N replaces it; the returned width is the touch's as today), the
   JOINT_GEAR constraint (ratio -1, erp 0.1, maxForce 50) in d9_setup's
   setup phase on the executing client and in boxel_env._setup_scene on
   our physics client (rebuilt by reset(), none on the plan client). Off:
   nothing differs. The pad forces are read where the force hold takes
   over, one "force_hold:" line per hold.
2. The refusal. force_hold_requires_solver_iters raises in d9_setup, in
   _setup_scene and at the hold unless solver_iters is on: a wrong arm
   spec fails every episode loudly instead of wasting an arm (a 10 N hold
   at 50 iterations expels the die, 108 of 113). The check-only escape
   SLIP_FORCE_HOLD_NO_ITERS_CHECK=1 logs a warning at every use; nothing
   on the cluster sets it (the sbatch files do not). The campaign's arm
   is `solver_iters+force_hold`, never force_hold alone.
3. Unchanged under the switch, confirmed with line numbers: grip
   verification (link identity), width plausibility (the touch width),
   the post-lift re-verify, _verify_holding, the place release. The eval's
   counted lines untouched.
4. The gates: four G1 lines (the gear's create and change on each world)
   with reviewed reasons; matched by text, so the merge keeps them. The
   configure call before d9_setup is byte-identical to solver_iters'
   (the merge sees one hunk).
5. Rules. Pipeline-wide: one hold law for every body on both worlds (the
   die, the cups, our cubes); the numbers are the proposal's measured
   ones, not a find_dice tuning. Model side (the executor's hold law and
   the hand's own coupling, which their URDF declares and PyBullet
   ignores). No truth read. Narration kept.
6. Tests (9): the switch, the refusal and the escape, d9_setup's gear and
   its absence without the switch, our world's gear on the physics client
   only and after reset(), the hold law's last commands on and off, a
   centred box held with coupled fingers.
7. Checks. Off: green (62 + 89 tests, gates PASS, seed 0 success). On with
   the escape at 50 iterations: red by design (the die lost in the carry);
   one bridge test flaked under load and passed alone (the goal-at-home
   family every worktree hit). At 200 iterations through the wrapper
   ep_iters.py: seed 1 held, seed 6 held, seed 0 held once and failed once
   with the cup release jam below. The branch's real configuration
   (solver_iters+force_hold) runs for the first time on the campaign
   branch's check.
8. The cup release jam, probed (jam_probe.py, 7 levers, 2 places, 8
   trials each, the per-step traces in probes/force_hold/out/): the jam
   happens under every hold law, base included: base 8 of 32 releases
   (25 %), every force_hold variant 9 of 64 (14 %), force_hold as
   implemented 2 of 16 (Fisher p 0.26 and 0.46: not separable, if
   anything fewer). 17 of 18 jams are light (one pad still touching the
   cup after the open at up to 0.9 mm and 7.7 N, the cup leaning on a
   finger); the one deep jam is base's (the cup slipped 8 to 11 mm and
   turned 15 deg in the carry). Base's own episodes have it (loss_dynamics'
   s14_base_r1, three failed releases of e_cups_ud). Under the force hold
   the cup moves less in the carry (turn median 1.0 to 1.6 deg against
   base's 3.2 to 7.4) and the pads sit shallower in the descent (-0.26 to
   -0.30 mm against -0.91 to -1.08). The hypotheses of the request are all
   answered no: the cup (0.019 kg) cannot slip under 24 N of friction
   capacity, the descent does not drive the pads in, the open clears an
   upright centred cup by 5.8 mm (ray profile: a 32 to 33 mm wall, a
   37.8 mm lip in the bottom 8 mm, the fingers' inner faces at 38.9 mm),
   the gear's 50 N cannot hold a finger against the 200 N open. The
   mechanism is the release's: the fingers open in place, a cup leaning
   on a finger stays there through the three retries because the hand
   does not move between them, and _release_and_verify_drop reads the
   contact as a failed drop. The episode's deep jam (a pad 10.6 mm inside
   the hull) did not recur in 64 force-hold releases; it stays an open
   observation, not attributable to the switch.
9. Decisions. No change on the branch. The 60-step position hold stays
   as the tested start. The per-carry fields (|q1 - q2|, the sink) stay
   unlogged; the eval counts losses. The release jam becomes its own
   finding for the audit (a candidate fix outside this campaign: a retreat
   along the approach axis after the open before the contact verify, the
   physical justification execute_place's comment asks for before
   restoring audit #85's removed pre-release lift; model side, every
   place and stack). It affects every arm alike (base has it), so the
   campaign's success column carries it as noise, and the per-arm pick
   tries and successes show it. pad_rolling, the fallback for a failed
   force_hold, is not needed.

## For the merge

- The configure hunk and `import slip_fixes` in policy.py are identical
  to solver_iters' (one copy after the merge; check the count).
- robot_utils' block imports sit mid-file with the block (noqa E402); the
  allowlist's four lines sit mid-file.
- Run `tools/bridge_gates.py static` and the check with
  solver_iters,force_hold on (the real configuration, never run before).
