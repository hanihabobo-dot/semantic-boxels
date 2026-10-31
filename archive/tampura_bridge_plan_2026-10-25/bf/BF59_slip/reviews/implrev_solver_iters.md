# BF#59 implementation review: solver_iters (slip/solver_iters 2252af5)

Reviewed 2026-10-31 18:55 by the orchestrating session from the diff
against 05dcaf3 (174 added lines, 5 files, nothing removed) and the
implementer's report reviews/impl_solver_iters.md.

## Verdict: accept, no change requested

1. The switch. `slip_fixes.register('solver_iters', ...)` at boxel_env's
   import (imported on the bridge path through test_full_pipeline and on
   our own path), `slip_fixes.on('solver_iters')` at three places, each a
   self-contained block after the existing code: policy.py d9_setup after
   setTimeStep (their world, the executing client), boxel_env.__init__
   guarded by `not self._adopted` (our own world; the adopted executing
   world is d9_setup's), boxel_env.reset() after the client loop (the
   review's gap: resetSimulation returns the iterations to 50). The plan
   twin keeps 50 and never steps. With the switch off no line changes
   behaviour. One constant, robot_utils.SOLVER_ITERATIONS, with a
   narration comment citing the proposal's numbers.
2. The deviation is right and binding for every physics switch: d9_setup
   runs inside execute_fn before main() configures the switches, so
   execute_fn now calls `slip_fixes.configure(cfg.switches.get(
   'slip_fixes', ''))` first (main() configures the same names again,
   idempotent). At the campaign merge this call must exist exactly once;
   force_hold was told to add the identical lines. configure() refuses
   unknown names, so every switch must be registered by a module that is
   imported before execute_fn runs: all seven candidates register in
   modules test_full_pipeline imports (boxel_env, robot_utils,
   pose_belief, streams, execution, policy), checked at the merge.
3. The gates. setPhysicsEngineParameter is a G1 write; three allowlist
   lines with reviewed reasons and a comment line. check_allowlisted
   matches on (file, function, source text), line numbers are
   informational, so the merge cannot stale them.
4. Logging. One line per place with the value read back
   (getPhysicsEngineParameters), printed; the console log of the run
   captures it (seen in the check's console_debug.log). Acceptable: the
   pipeline's run log is print-based on this path.
5. Rules. Pipeline-wide (our world and the bridge's executing world, one
   value); not TAMPURA-matched (their world runs PyBullet's 50 and arm T
   keeps it: the audit entry and the paper must say so). Model side (a
   world setting). No truth read.
6. Tests. Six, every value read back on a fresh DIRECT client: off keeps
   50 in d9_setup and in BoxelTestEnv including after reset(); on gives
   200 in both and after reset(), the plan client 50; the bridge configures
   the switch before d9_setup (a source-order test). Checks green on and
   off (59 unit, 89 bridge, gates PASS, seed 0 success, the run record's
   slip_fixes right).
7. Accepted gap. test_full_pipeline 2995's scene-acceptance probe env runs
   at 50 with the switch on: our scenes only, a planning-time acceptance
   check that carries nothing. Recorded, not fixed.
8. Cost. The check episodes cannot measure it (different plans, the
   laptop under four agents' load); the resting bench is a floor. The
   cluster arm measures it against base in the same job (the review's
   budget: +24 % of wall at the median, +77 to +184 s on capped
   episodes).

## For the merge

- Keep the execute_fn configure call once.
- Re-run `tools/bridge_gates.py static` after the merge (the allowlist
  entries are matched by text, not line).
