# BF#59 implementation report: solver_iters

Started 2026-10-31 by the implementing agent (phase 5, round 1). Filled as
the work goes.

## Branch and commits

Worktree `C:\Users\HaniAlassiriAlhabbou\git\sb-slip-solver_iters`, branch
`slip/solver_iters`, from tampura-bridge at 05dcaf3.

- 2252af5 `BF#59 solver_iters: 200 solver iterations on the executing world
  and our own (after reset too), switch default off, tests, allowlist`
  (5 files, 174 insertions, no line changed or removed). Not pushed.

## Files and functions changed (line numbers at 2252af5)

- `robot_utils.py` 170 to 177: `SOLVER_ITERATIONS = 200`, the one constant
  both call sites read, beside `SIM_TIMESTEP`, with the narration comment
  (0 of 113 dice lost at 200 iterations under the 10 N force hold; about
  1.9 against 1.0 ms per step; proposals/hold_physics.md 2.2). No import
  added to robot_utils.
- `boxel_env.py` 16: `import slip_fixes`; 28 to 33: the registration at
  import, `slip_fixes.register('solver_iters', '200 contact-solver
  iterations per step on the executing world (d9_setup and boxel_env,
  re-applied after reset)')`. Registered here because boxel_env is imported
  on both paths (test_full_pipeline 82, tampura_bridge/env_adapter 25), so
  the name exists before main() or execute_fn configures.
- `boxel_env.py` `BoxelTestEnv.__init__` 568 to 578: after the existing
  `if not self._adopted:` block (resetSimulation, setGravity,
  setRealTimeSimulation, setAdditionalSearchPath), a separate block
  `if not self._adopted and slip_fixes.on('solver_iters'):` sets
  `numSolverIterations=robot_utils.SOLVER_ITERATIONS` on `self.client_id`.
  The plan client is not touched (it never steps).
- `boxel_env.py` `BoxelTestEnv.reset` 2025 to 2035: after the existing
  per-client loop, the same write on `self.client_id`, because
  resetSimulation sets the iterations back to 50 (the review's gap).
- `tampura_bridge/policy.py` 37: `import slip_fixes`; `d9_setup` 70 to 80:
  directly after `setTimeStep`, the same write on the executing client `c`
  (phase setup, so gate_hooks' G14 body-less writer check does not fire).
- `tampura_bridge/policy.py` `make_execute_fn.execute_fn` 201 to 204:
  `slip_fixes.configure(cfg.switches.get('slip_fixes', ''))` right before
  `d9_setup(world, model)`. See the deviations: without it d9_setup never
  sees the switch.
- `tools/bridge_gates_allowlist.txt` 136 to 139: one comment line and three
  G1 lines (d9_setup: D9 set-up; BoxelTestEnv.__init__ and
  BoxelTestEnv.reset: unreachable on the bridge path), the count the review
  asked for.
- `tests/test_slip_solver_iters.py`: new, six tests.

## The switch, on and off

Off (the default, the base arm): no new pybullet call runs; the only new
code executed is the `slip_fixes.configure` call in execute_fn, which sets
the same names main() sets later (empty for base), so base's numbers and
log lines are unchanged. Every world runs PyBullet's 50 iterations.

On: the bridge's executing client gets 200 in d9_setup (after gravity and
timestep, before any step); our own world gets 200 at construction and
again after every reset(). The planner's twin and the kin stream (the
plan client) keep 50; they never step. Arm T is untouched (their world at
50, kinematic carry).

## Where the fix logs

One print line per world through the run's logger (RunLogger tees stdout
into the run's console log), with the value read back by
`getPhysicsEngineParameters`, not the constant:
- `  solver_iters: numSolverIterations 200 on the executing world (client
  0, D9 set-up)` (d9_setup);
- `  solver_iters: numSolverIterations 200 on our world (client N)`
  (BoxelTestEnv construction);
- `  solver_iters: numSolverIterations 200 on our world after reset
  (client N)` (BoxelTestEnv.reset).
No ledger row (the run record's "slip_fixes" already names the arm).

## Tests

`tests/test_slip_solver_iters.py` (fixture: the registry as the imports
left it, every switch off, KNOWN and ENABLED restored after each test):
1. the name is registered and off by default; the constant is 200; a bare
   DIRECT client reports 50;
2. off: d9_setup on a fresh DIRECT client (stub world, no bodies) leaves
   the default;
3. on: d9_setup sets 200 (read back) and prints the solver_iters line;
4. off: BoxelTestEnv(gui=False) reports the default, also after reset();
5. on: BoxelTestEnv reports 200, the plan client the default, still 200
   after reset() (the plan client still the default), both log lines;
6. the bridge's execute_fn configures the switch before d9_setup (source
   order).
Local run (with test_slip_fixes.py): 12 passed in 6.3 s; static gates
PASS (G1 79 hits, G2 46 hits, all reviewed).

## Checks (IMPL_BRIEF section 3)

Both runs of the main checkout's `tools/slip_check.sh` on the worktree at
2252af5 are green. The folders are under the worktree's
`archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/checks/`:

| | fix on (`solver_iters`) | base (no fix) |
|---|---|---|
| folder | `2026-10-31_18-25-34_s0_solver_iters` | `2026-10-31_18-33-09_s0` |
| unit tests | 59 passed | 59 passed |
| bridge tests | 89 passed, 3 skipped | 89 passed, 3 skipped |
| static gates | PASS (G1 G2 G7 G11(i) G17) | PASS |
| seed 0 outcome | success, reward 1.0, rc 0 | success, reward 1.0, rc 0 |
| run record "slip_fixes" | "solver_iters" | "" |
| die carries | 1 (held) | 1 (held) |
| the log line | `solver_iters: numSolverIterations 200 on the executing world (client 0, D9 set-up)` in console_debug.log | none |

The fix-on episode's one failed step was a `stale_precondition` replan
(the ledger's step_end statuses: 14 ok, 2 observe_ok, 1 sense_outcome,
1 stale_precondition), not a grip or physics failure. The die was picked
once, "firm grip on dice" (half-width 10.3 mm), and held at home.
No episode of a die-losing seed was run: the fix changes neither the
carry nor the hold, and its loss effect is predicted null.

## Step-time cost

From tools/episode_metrics.py on the two runs, with the simulation steps
from G21's step counts (outside plus inside dispatch):

| | fix on | base |
|---|---|---|
| wall ("in all") | 70.6 s | 22.3 s |
| planning | 15.1 s (5 plans) | 4.6 s (3 plans) |
| exec_s | 18.5 s | 4.1 s |
| simulation steps | 5386 (50 + 5336) | 3295 (50 + 3245) |
| dispatched steps | 18 (11 moves, 3 picks, 1 sense, 2 observes) | 10 (6 moves, 2 picks) |
| exec_s per simulation step | 3.43 ms | 1.24 ms |

These two episodes do not measure the cost per step. They planned
different routes: seed 0's plan diverges between runs (the timing
non-determinism of STATE.md), and the fix-on run sensed once and replanned
twice more. The machine was also loaded differently. Planning never steps
the physics, yet it took 3.3 times as long in the fix-on run (first plan
4.5 s against 1.8 s, the M8 build 7.4 s against 1.9 s), so the other
round-1 agents' tests or probes were running beside it (the lock
serialises only episodes and pytest). exec_s also holds renders, IK and
the observes, not only stepping. The raw +2.2 ms per step is an upper
bound that load and work content contaminate, not a cost.

A physics-only benchmark (`checks/solver_iters_bench/bench.py`, our default
scene in a DIRECT BoxelTestEnv, bodies at rest, 5 blocks of 1200 steps per
setting, alternated 50/200 in one process) gives 0.118 ms per step at 50
against 0.133 ms at 200 (medians; ranges 0.110 to 0.154 and 0.113 to
0.146), which is within noise. Resting bodies sleep and the solver stops once
converged, so this is the floor, not the grip cost. The relevant figure
is still the proposal's grip probe: 1.0 against 1.9 ms per step, +0.9 ms,
with a die between the pads. The cluster arm, with base in the same job,
is where the cost gets measured; the review's budget is exec_s per seed at
most 2x base's, and at most 2 of 60 episodes newly capped.

## Deviations from the proposal and why

1. `slip_fixes.configure` in the bridge's execute_fn before d9_setup
   (policy.py 201 to 204). The registry is configured by main()
   (test_full_pipeline 566 to 567), and D9's set-up runs before main(),
   so without this line `slip_fixes.on('solver_iters')` is always False
   in d9_setup and the bridge never gets the setting. It configures from
   the same flag main() reads (`cfg.switches['slip_fixes']`, which
   run_bridge_on_finddice passes) and main() then sets the same names
   again. force_hold's gear in d9_setup needs the same thing, so on a
   merge this line must exist once. A test pins the order.
2. Registered in boxel_env.py, not policy.py: boxel_env is imported on
   both paths before configure runs, and one registration keeps the line
   from drifting between two copies.
3. The constant lives in robot_utils.py beside SIM_TIMESTEP, as the
   proposal said, so both call sites read the same value.
4. The value is logged from a getPhysicsEngineParameters read-back (not
   gated: not in G1/G2), not from the constant, so the log line proves
   the setting took.
5. The d9_setup block sits right after setTimeStep (as STATE.md says)
   rather than at the end of d9_setup, so it does not collide with
   force_hold's or pad_rolling's blocks after the finger loop. The
   boxel_env blocks are after the existing code of their spots (the
   `if not self._adopted:` block in __init__, the client loop in reset).
6. No D9 disclosure text changed (policy.py's docstring lists D9's steps
   (1) to (4)). The review asks that the D9 disclosure and the paper's
   set-up text name the setting (arm T stays at 50). That is prose for
   the audit entry and the paper, left to the orchestrator so the
   docstring hunk does not collide with other branches.

## Open questions for the implementation reviewer

- `test_full_pipeline.py` 2995: the `__main__` scene-acceptance probe env
  (a BoxelTestEnv built and settled before main() configures) runs at 50
  even with the switch on. It decides only whether a scene is accepted
  and is closed before main(); on our own scenes with the switch on, the
  accepted-scene set could differ from the env main() runs, in principle.
  Not on the bridge path. Leave it, or configure earlier in `__main__`?
- force_hold must refuse without solver_iters. With this branch it can
  check `slip_fixes.on('solver_iters')` at configure time in execute_fn
  (the line above) or at the first hold.
- The settle under 200 iterations (D9 (5), settle_max_dxy_m) and our own
  scenes' G4 or stacks are not measured here; the cluster arm reads them.

## Data generated and deleted

All under the worktree's `archive/tampura_bridge_plan_2026-10-25/bf/
BF59_slip/checks/` (untracked; DATA_LEDGER.md row 29 already covers
`checks/<stamp>`: kept for the implementation review, garbage once it is
recorded):
- `2026-10-31_18-25-34_s0_solver_iters/` 418,850 bytes (the fix-on check);
- `2026-10-31_18-33-09_s0/` 326,314 bytes (the base check);
- `solver_iters_bench/` 2,393 bytes (bench.py, bench.sh, bench.txt).
Scratch scripts t1.sh and m1.sh in the session scratchpad (outside the
repo). Nothing deleted: the check folders are the review's evidence.
