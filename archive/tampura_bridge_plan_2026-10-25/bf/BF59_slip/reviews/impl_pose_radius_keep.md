# BF#59 implementation report: pose_radius_keep

Written 2026-10-31 by the implementing agent, filled as it went. Worktree
`C:\Users\HaniAlassiriAlhabbou\git\sb-slip-pose_radius_keep`, branch
`slip/pose_radius_keep`, base 05dcaf3 (tampura-bridge).

Status: DONE. Code and tests committed (e0e81e1); both checks green;
seeds 6 and 1 run on the laptop with the fix on (die held in both).

## 1. Branch and commits

- e0e81e1 `BF#59 pose_radius_keep: min(r_new, r_ref + centre shift) and
  the wrist yaw kept over a consistent eye detection, tests`

## 2. Files and functions changed (line numbers at e0e81e1)

- `pose_belief.py`
  - 17 to 30: `import slip_fixes`, `slip_fixes.register('pose_radius_keep',
    ...)` at the module's import, with a narration comment.
  - 263 `_fuse`: now returns True when it fused, False on the "not fused"
    outlier return (its only caller that reads it is the fix; with the
    switch off the value is ignored, the body is unchanged).
  - 297 `record_detection`: with the switch on, the belief before the
    detection is captured (`_prk_prior`, before the fusion overwrites the
    yaw) and, after the A formula set the radius, `_prk_apply` runs. With
    the switch off the function runs exactly the old statements.
  - 330 to 357: the rule's narration comment (the review's numbers) and
    `_PRK_BOX_TOL` = 0.5 mm.
  - 360 `_prk_centres`, 370 `_prk_prior`, 380 `_prk_apply`: the rule.
- `tests/test_slip_pose_radius_keep.py` (new, 11 tests).

No other file changed. The callers of `record_detection` (execution.py
2139 refresh_object_aabbs 'eye', 2481 and 2581 and 2817 and 3164 first
registrations 'eye', 2613 handle_observe_action 'wrist';
test_full_pipeline.py 2458 the post-place writer 'eye') already name the
camera, so the detection's source needed no new parameter.

## 3. What the switch does

Off: today's behaviour, the latest complete detection sets the radius by
A's formula and `_fuse` sets yaw = latest. No new attribute is written,
no new log line.

On, at every radius write of `record_detection` (complete, or first):

1. The reference disc: the measured detection whose own radius set the
   current bound (its radius r_ref, its AABB centre and rectangle centre,
   its camera), stored on the boxel as `_prk_ref` with the radius the rule
   wrote and the box centre that write's caller put the box at.
2. The reference is valid only when this is not a first registration, the
   radius at entry is finite and is the one the rule last wrote (so
   `mark_pose_unknown`, `mark_pose_commanded`, M10's touched bodies and
   any other radius writer invalidate it) and the box still sits within
   0.5 mm of where that write's caller put it (so a place, which moves the
   box before the post-place writer runs, or a re-pose from a partial
   detection invalidates it).
3. Radius: r = min(r_new, r_ref + shift), shift = the larger of the AABB
   centre's and the rectangle centre's distance between this detection
   and the reference (the bound holds for whichever centre the pick aims
   at). If the bound wins the reference stays; otherwise this detection
   becomes the reference.
4. Yaw: when the detection fused, is from the eye, the stored yaw came
   from the wrist, the reference is valid, the discs overlap (shift <=
   r_ref + r_new) and the eye's aligned, deadbanded yaw is within
   YAW_NOISE eye + wrist (9.68 deg) of the stored one, the wrist's yaw is
   restored after `_fuse`; extents and the rectangle centre stay the
   fused ones (the eye's centre, as the box). Otherwise yaw = latest and
   the yaw's camera becomes this one.

## 4. Logging

Through print, which the run logger tees into console_debug.log (as the
[M9] and [M8] lines):

    pose_radius_keep: <id> radius kept 2.05 mm (this eye detection's 5.49 mm; the wrist detection's 0.39 mm + centre shift 1.66 mm)
    pose_radius_keep: <id> yaw kept 5.00 deg (wrist) over this eye detection's 0.00 deg (centre shift 1.66 mm)

One line per kept radius, one per kept yaw that differs from the eye's.

## 5. Tests

`tests/test_slip_pose_radius_keep.py`, 11 tests, the A formula stubbed to
0.39 mm (wrist) and 5.49 mm (eye), a cup of 69.6 mm box and 51 mm top:
registered and off by default; off: the eye refresh after the wrist
observe sets 5.49 mm, yaw 0, the commit check refuses, no log, no
attribute; on: 2.05 mm, the wrist's 5 deg kept, the commit check commits
(margin 3.2 mm from believed_margin), both log lines exact, the
rectangle centre the eye's; a 100 mm shift takes 5.49 mm and the eye's
yaw; a first detection is unchanged; a second refresh 0.3 mm across is
bounded from the wrist's disc (2.08 mm), not 2.35 mm; mark_pose_commanded
and mark_pose_unknown invalidate the reference; a box moved without the
rule (a partial detection's re-pose) invalidates it; an eye yaw 30 deg
off is taken; a wrist after an eye is latest. The slip registry and the
pose switches are restored after each test.
Result with test_pose_writers, test_pose_belief, test_slip_fixes: 35
passed (5 s).

## 6. Checks

Paths below are under the worktree's
`archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/checks/`.

- Fix on, `slip_check.sh ... 0 pose_radius_keep` ->
  `2026-10-31_18-26-10_s0_pose_radius_keep/`: 63 unit tests passed, bridge
  tests 89 passed 3 skipped, static gates PASS (G1 76 hits reviewed, G2 46
  hits reviewed, G7, G11(i), G17; run in full separately, every line
  PASS), episode seed 0 success, run record `"slip_fixes":
  "pose_radius_keep"`, 1 die carry, 3 solve calls, 3295 dispatch steps,
  23.8 s episode time (the script's 226 s include the wait for the lock).
  No `pose_radius_keep:` line: the cup was behind the arm at the refresh
  after its observe, so the refresh kept the estimate and nothing was
  refused.
- Fix off, `slip_check.sh ... 0` -> `2026-10-31_18-41-16_s0/`: 63 passed,
  89 passed 3 skipped, gates PASS, seed 0 success, `"slip_fixes": ""`,
  1 die carry, 7 solve calls, 6828 steps, 29.5 s. This run shows the cup
  loop twice ("d_cups_ud pose_radius 5.40 mm is outside its commit
  margin", plans 1 and 2) before the third pick, and no
  `pose_radius_keep:` line: the off path is today's.
- Seed 6 on the laptop, the fix on, `--allow-g19-mismatch 1`, under the
  lock -> `2026-10-31_18-56-59_s6_pose_radius_keep/`: the die held at
  home (their reward 1.0); the outcome label is gate_failed for G19 only
  (the laptop loads 1747173593 for seed 6, pinned 1747173590, the known
  BF#39 mismatch); every other ledger gate PASS (G15: 2 senses, each
  classified); 4 plans, 17 steps, planning 30.9 s, 78.7 s in all; no pick
  refused; the keep never fired (after the e_cups_ud observe, 0.49 mm, the
  refresh found the cup partly behind the arm and kept the estimate).
- Seed 1 on the laptop, the fix on (added because seed 6 did not exercise
  the rule; the proposal's s1_r3 loop was a laptop seed-1 run) ->
  `2026-10-31_19-02-12_s1_pose_radius_keep/`: the die held at home
  (reward 1.0), gate_failed for G19 only (1747173590, pinned
  1747173593), 12 plans, 40 steps (39 done, 1 failed), planning 69.0 s,
  138.8 s in all. The rule fired 30 times on three cups, for example
  "d_cups_ud radius kept 2.63 mm (this eye detection's 5.49 mm; the wrist
  detection's 0.39 mm + centre shift 2.24 mm)", after which the pick
  committed and gripped d_cups_ud; "e_cups_ud radius kept 2.82 mm (...
  0.69 mm + centre shift 2.14 mm)"; d_cups_ud 4.38 mm (0.64 + 3.74) and
  a_cups_ud 4.3 mm (0.45 + 3.85), still above the margin; yaw kept 5
  times, all a_cups_ud, -18.25 deg (wrist) over the eye's -25.87 deg. One
  refusal in the episode (plan 9, d_cups_ud 5.49 mm): the wrist observe
  from look 2 put the AABB centre at (0.5891, -0.2261), the eye refresh
  at (0.5926, -0.2294), 4.8 mm apart, so 0.68 + 4.8 reached the eye's
  5.49 mm and the eye's radius stood (the rule as specified); the next
  observe from look 0 (0.39 mm, 2.24 mm from the eye) committed.

## 7. The commit check and G15 (read at e0e81e1)

- The pick's commit check, test_full_pipeline.py 2116 to 2125, calls
  `pose_belief.pose_known` (246): `pose_radius <= believed_margin`
  (222 to 243). The fix changes only the inputs it is meant to change:
  the radius (the kept bound) and, through the yaw keep, the yaw that
  `fitted_grasp_candidates` (190) sizes the families with, which is the
  yaw the sampler (streams.sample_grasp) aims at too, so the margin and
  the grasp stay consistent. The margin's code is unchanged. With the
  cup of the tests (69.6 mm box, 51 mm top, half opening 40 mm) the
  margin is 3.2 mm: 2.05 mm commits, 5.49 mm refuses (tested).
- The pre-grasp aperture, execution.py 1132 (`pinch_half + pose_radius +
  8 mm`, capped at the opening), shrinks with the kept radius; for the
  cups the cap binds anyway.
- G15, tools/bridge_gates.py 877 to 885: it checks that every sense step
  has its `sense_result` row; nothing in the sense classification reads
  `pose_radius` (its only readers in execution.py are 1132 and the
  observe's print at 2625), so G15 is unaffected (PASS in every episode
  above).

## 8. Deviations from the proposal and the brief

1. The rule is the review's, not the proposal's min(old, new).
2. The reference disc is the measured detection whose own radius set the
   current bound, not the radius last stored: with one refresh the two
   are identical (the brief's 0.39 + 1.66 = 2.05 mm), but a stored bound
   would add every later refresh's shift on top (2.05 + 0.3 for a second
   refresh 0.3 mm across, against 0.39 + 1.69 = 2.08 mm from the wrist's
   disc, tested). Both are honest; this one does not drift.
3. "A body whose pose is already known": the rule does not call
   `pose_known` (record_detection has no grasp numbers); it requires a
   finite radius that this rule itself wrote last, with the box where
   that write's caller put it (0.5 mm). Any finite earlier disc is a
   valid bound to intersect with. The two validity conditions are
   additions: without them a body placed back within r_old + r_new of
   its old centre (the post-place writer moves the box before it calls
   record_detection), or re-posed from a partial detection, would keep
   a disc that no longer bounds it. mark_pose_unknown, mark_pose_commanded
   and M10's touched bodies invalidate it by the radius condition.
4. The shift is the larger of the AABB centre's and the rectangle
   centre's (the pick aims at the AABB centre, or at the rectangle centre
   under M9), so the bound holds for either aim.
5. The yaw keep also requires the eye's aligned yaw to agree with the
   wrist's within YAW_NOISE eye + wrist (9.68 deg), the review's
   "consistent within its noise", besides the overlapping discs; extents
   and the rectangle centre stay the fused ones.
6. `_fuse` returns whether it fused (the keep must not log or restore a
   yaw the outlier rule never replaced). Off, the value is ignored.
7. The source camera needed no new parameter: every caller already names
   'eye' or 'wrist'.
8. One more laptop episode than asked (seed 1), because seed 6 never
   exercised the rule.

## 9. Open questions for the implementation reviewer

1. The wrist's centres disagree between look configurations by more than
   its radius claims: seed 1, d_cups_ud AABB centre (0.5891, -0.2281)
   after one observe, (0.5891, -0.2261) after the look-2 observe,
   (0.5915, -0.2284) after the look-0 observe, each with a radius of 0.39
   to 0.68 mm. The kept bound inherits the wrist's claim. This is the M8
   calibration question the review raised (section 3 there), not this
   fix's; it also makes the eye-to-wrist shift 2 to 4.8 mm on these cups,
   larger than the review's 1.66 mm, so some refreshes still refuse.
2. The yaw keep fires on cups (a_cups_ud), whose round footprint makes
   the yaw arbitrary; harmless, but the log counts are dominated by
   cups. The die never reached the keep in these episodes.
3. A body nudged by less than the 0.5 mm box tolerance without a
   detected disturbance keeps its reference; the eye's centre still
   tracks it and the bound grows with the shift.

## 10. Data generated and deleted

Under the worktree's `archive/tampura_bridge_plan_2026-10-25/bf/
BF59_slip/checks/` (untracked):

- `2026-10-31_18-26-10_s0_pose_radius_keep/` 0.33 MB (21 files)
- `2026-10-31_18-41-16_s0/` 0.49 MB
- `2026-10-31_18-56-59_s6_pose_radius_keep/` 0.70 MB
- `2026-10-31_19-02-12_s1_pose_radius_keep/` 1.16 MB

About 2.7 MB in all, kept for the implementation review (the seed-1
console_debug.log and eye.jsonl are quoted in section 6); garbage after
it. Not yet in DATA_LEDGER.md (the brief keeps me to the worktree and
this report; the orchestrator ledgers the rows). Four helper scripts in
the session scratchpad (prk_unit.sh, prk_gates.sh, prk_s6.sh, prk_s1.sh,
outside the repo). Nothing deleted.
