# BF#64 the shadow caster on their shortened table: live state

Started 2026-11-04 by Hani: "fix the seed 118 issue. theres two object but
it only looks behind one."  BF#64 checked free on 2026-11-04 (no match in
the checkout); the BF#63 eval session was told this number.

## Status: stopped and handed over (2026-11-04 14:50)

Hani, 14:50: "you dont need to fix it. some other agents are working on
it."  This session ("Project status (fork)", the one that started the
BF#63 eval) stopped its batch, commits no fix and writes no BF#64 entry.
Handed over:
- The fix: the _adopt_scene hunk in tampura_bridge/env_adapter.py, in the
  checkout, uncommitted (Fix, below).  BF#65 (bf/BF65_cup_residuals,
  session local_d587c23c) studies what still fails with it in place, so
  it stays there until the session that takes the fix commits or drops
  it.
- WSL /root/bf64_check (14 MB, DATA_LEDGER.md Kept): seed 118's run and
  the batch's 13 run directories with SUMMARY.txt.  Its SUMMARY.txt and
  seed 118's record are copied here; BF#65 copies the runs it cites and
  then deletes it by path and logs it (handed over 14:50).
- The number BF#64 stays with this finding: the session that commits the
  fix writes the entry (after BF#63, before "#P5.") and cites this folder.

## Cause (found)

- tampura_bridge/env_adapter.py passed D8's window W (task_spec WINDOW_X
  0.35..0.74, WINDOW_Y -0.28..0.34; BF#11 (e)) as the shadow caster's table
  ranges (boxel_env.py:617-620).  shadow_calculator.py clamps every ray hit
  and the shadow AABB to those ranges (:170-171, :190-191, :208-212).
- Seed 118 (2 cups): b_cups_ud's believed box y -0.334..-0.274 (true centre
  y -0.304); the die y -0.316..-0.288, outside W.  The back-corner rays land
  at y about -0.38 and are clamped to -0.28, on the camera's side of the
  cup's centre, so the mean hit minus the centre (:226-228) points toward
  the camera (+0.024 y against +0.013 x), y becomes the dominant axis, and
  the subtraction (:233-236) leaves a box 0 thick; the #P1 F3 guard (:300)
  drops it.  The logged extent [0.0901, 0.0, 0.0651] matches this to the
  digit.  The plan then lifts only d_cups_ud and ends all_searched.
- TAMPURA's generator samples centres x U(0.3, 0.7), y U(-0.4, 0.4)
  (find_dice/env_generator.py:114-118) and puts the die at a cup's pose
  (:126-127).  The die's centre is outside W in 15 of the 40 scenes: 11 of
  our 12 failing scenes, 4 of the 28 we always solved (115, 130, 133, 138).
  The one failing scene with the die inside W is 101 (5 cups).
- Our own environment gives the shadow caster the logical table and free
  space the safe ranges (boxel_env.py:616-636, 908-909, 1059-1060).

## Fix (in the checkout, not committed)

- env_adapter.py _adopt_scene: table_x_range / table_y_range from their
  panda_env_utils.get_shortened_table_dims (x 0.10..0.85, y -0.61..0.61, the
  table BF#11 (e) cut W from); _SAFE_TABLE_* keep W (free space,
  placement).  Nothing else in the pipeline reads table_*_range (grep).
  shadow_calculator.py unchanged (its direction from clamped hits stays a
  latent flaw at the table's edge; their generator keeps every centre at
  least 15 cm inside the shortened table).

## Checks

- Seed 118 after the fix (headless, `run tampura -Seed 118 -Gen -Headless
  -Args '--save-dir /root/bf64_check/s118'`): success, 25.5 s, "2 spaces
  hidden", lifts b_cups_ud, sees the die, picks it, home, every gate PASS,
  reward 1.0.  Its record and run log: s118_bridge_episode.json and
  s118_run.log here.
- Static gates PASS (G1 83 hits and G2 46 all reviewed, G7, G11(i), G17),
  rc 0.
- The batch (check.sh here, its SUMMARY.txt here, 14:18 to 14:50) was
  stopped after 13 of its 31 seeds; the seed 110 run it cut off was
  deleted.  Failing in BF#63, with the fix: 102, 103, 107, 111, 127
  success; 100 all_searched; 104 planner_failed; 128 and 135
  no_plan_binding_death; 124 at the 900 s cap (its console ends replanning
  after "e_cups_ud's pose is too uncertain"); 101 planner_failed.  Solved
  in BF#63, still solved: 105, 106.  Not run: 110 112 114 115 120 122 126
  130 133 134 138 108 113 and the shipped seeds 0 1 2 5 6, so the fix's
  effect on scenes we solved is checked on 105 and 106 alone.  BF#65
  diagnoses the residuals (bf/BF65_cup_residuals/STATE.md).

## Next steps (for the session that takes the fix)

1. The rest of the batch, into an output folder of its own (BF#65 deletes
   /root/bf64_check), under the pipeline lock (`run ps` first):
   wsl -e bash -c "tr -d '\r' < /mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF64_shadow_table/check.sh | bash -s -- /root/<out> 110 112 114 115 120 122 126 130 133 134 138 108 113 0 1 2 5 6"
2. Bridge tests in WSL after the batch, never during it (pddlstream
   temp/): tampura_bridge/tests and tests/test_gen_scene_eval.py.
3. PAPER_AUDIT.txt: the BF#64 entry after BF#63, before "#P5.", staged
   alone (other sessions hold unstaged hunks there).  DATA_LEDGER.md rows.
   One commit with env_adapter.py; one-line subject, no trailer, never
   push.
4. The 40-scene comparison with the fix needs a cluster run, asked of Hani
   alone; use gen_eval.sbatch's P4_LOCAL=1 (BF#63's slow hour was the NFS
   volume under $W).  BF#63's run 2 is pinned to 11744fd (env_adapter.py
   byte-equal to run 1's b2c6c5d), so it has no BF#64 fix in it; its
   result goes into BF#63.
