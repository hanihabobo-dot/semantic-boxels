# BF#59 implementation review: pose_radius_keep (slip/pose_radius_keep e0e81e1)

Reviewed 2026-10-31 19:20 by the orchestrating session from the diff
against 05dcaf3 (pose_belief.py +146 -5, tests +210), the implementer's
report reviews/impl_pose_radius_keep.md, and the two call sites in
execution.py (refresh_object_aabbs 2139, handle_observe_action 2613).

## Verdict: accept, no change requested

1. The switch. Registered at pose_belief's import; read once in
   record_detection. Off: the prior is not captured, `_fuse` is called as
   before (its new bool return is ignored), no attribute is set, no line
   printed. On: after the A formula sets r_new, `_prk_apply` bounds it.
2. The rule is the review's, done right. r = min(r_new, r_ref + shift)
   around the NEW centre, with the reference the measured detection whose
   own radius set the current bound, so repeated eye refreshes measure
   their shift from the wrist's centre and do not add up (the proposal's
   min(old, new) was rejected by the review; the implementer's reference
   choice is stricter than "r_old" and gives the brief's 2.05 mm for one
   refresh). The shift is the larger of the AABB-centre and the fitted
   rectangle-centre shifts, so the bound holds for whichever centre the
   pick aims at (M9 aims at the rectangle). A moved body has a large
   shift, r_new wins, today's behaviour returns.
3. The validity test is sound against the call order. Both callers call
   record_detection BEFORE writing the box (execution.py 2139 then 2146,
   2613 then 2618), so the prior box is the box the last write put there;
   the reference stores that detection's AABB centre
   (det.est_center = (est_min + est_max) / 2, perception.py 371, the same
   centre_xy the callers write), and the 0.5 mm tolerance covers the
   callers' unchanged-box early returns (1e-4 and _aabb_tol). Any other
   radius writer (mark_pose_unknown, mark_pose_commanded, M10's touched
   bodies) breaks the `written` equality; a box moved by a place or by a
   partial detection's re-pose breaks the position test. Both are the
   right invalidations: a disc from before a move must not survive it.
4. The yaw keep is conservative: eye after wrist only, the belief's yaw
   valid, the reference valid, the discs overlapping, and the eye's
   aligned yaw within the two cameras' noise (9.68 deg) of the wrist's;
   otherwise the eye's yaw is taken as today and the camera recorded. The
   fused extents stay the eye's (consistent: `_fuse` aligned them to the
   stored yaw before the max).
5. The commit check and G15 are untouched: pose_known compares the radius
   with believed_margin (the code unchanged); the yaw keep only changes
   the yaw that the margin and the sampler both read. Confirmed by the
   implementer with line numbers and by the off/on seed-0 checks.
6. Rules. Model side (the belief). Pipeline-wide: every body, both
   cameras, no size or class condition. No truth read (detections only).
   Prose and comments fine; the narration comment states the derivation
   and the numbers.
7. Tests (11): off path, the 2.05 mm case with the yaw kept, a moved
   body, a first detection, repeated refreshes not accumulating, another
   radius writer invalidating, a box moved without the rule invalidating,
   an eye yaw outside the noise taken, a wrist detection after the eye
   being latest. Checks green on and off (63 unit, 89 bridge, gates PASS,
   seed 0 success). Laptop seed 1 on: the rule fired 30 times on three
   cups, the pick committed on a 2.63 mm kept bound; seed 6 on: the rule
   never fired (the cup was behind the arm at the refresh), held.
8. Open, not this fix's to solve: the wrist's centres from different
   look configurations disagree by 2 to 3 mm while it claims 0.39 to
   0.68 mm (the M8 calibration question in the loss_dynamics review); the
   kept bound inherits it, so some refreshes still refuse. For the audit
   entry.

## For the merge

- pose_belief.py is also touched by grasp_wrist_home (the wrap and the
  candidates); the two blocks do not overlap (record_detection and the
  new helpers against _wrap and fitted_grasp_candidates), so the merge
  should be textual.
