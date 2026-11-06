# BF#65 the die under a cup lies in none of our hiding regions (live state)

Started 2026-11-04 by the session "Diagnose BF#63: the die under a cup gets
no shadow" (local_d587c23c).  Its brief, from the BF#63 eval session, was
dropped on arrival at 11:30; Hani resumed it with "continue" at 14:34 and
"Try again" on 2026-11-06.  Brief: find why the occlusion model registers
no hiding region for the upside-down cup over the die, write it up as a BF#
finding with fix options for Hani, fix nothing, reproduce locally under the
pipeline lock, no cluster runs.  BF#65 checked free on 2026-11-04 14:50 and
again on 2026-11-06 (no BF#65 or BF65 elsewhere in the checkout).

## Status: DONE, entry written and committed (2026-11-06)

The BF#65 entry is in PAPER_AUDIT.txt after BF#63, before "#P5." (BF#64
has no entry: its number stays with the fix, for whoever commits it).

- The cause: a shadow starts at its caster's back face
  (shadow_calculator.py:226-236), so the die under an upside-down cup is in
  no region, in every find_dice scene (shipped ones included).
- We find it only by lifting its cup to look behind it, then F20 registers
  it: 57 of 57 successes in BF#63 and 653 of 653 in BF#59's eval
  (HOW_FOUND.txt); no sense ever found the die.
- The failures by cause:
  - (a) BF#64's W clip: 16 of 17 all_searched runs.
  - (b) 100: the F16 sweep sees the 2.3 cm sliver behind b empty.
  - (c) 128, 135: the reach gate refuses the shadow centre as the pick
    target (streams.py:1516, 1532).
  - (d) 104: the die is in view, but no look config exists under the cup
    (observe_views.py:227-269).
  - (e) 101, 124: M8/M9 on a far cup (M9 refuses the 2 mm larger
    rectangle, parks the cup; pose_radius_keep loop).
- Fix options in the entry: 1 a region under a cup (default-off switch,
  A/B), 2 narrow fixes per cause, 3 a limitation in the paper.  Hani's
  call; nothing changed.

## Split with BF#64 (unchanged)

BF#64 (bf/BF64_shadow_table) found the W clip.  Its env_adapter.py fix
stays in the checkout, uncommitted, not ours: Hani stopped that work on
2026-11-04 14:50 ("some other agents are working on it").  The reruns
cited here are BF#64's batch (check.sh, 2026-11-04 14:18 to 14:41, HEAD
bf2c4bc plus that fix).

## Evidence in this folder (tracked)

- runs/s<seed>/: console.txt and the run log for 100, 101, 104, 111, 128
  and 135; for 124 the console and the first 1000 of its 8063 log lines
  (every cited line is in them).
- EYE.txt: the cited poses, boxes and shadows from the runs' eye records,
  made by bf65_eye_dump.py and bf65_eye_track.py.
- HOW_FOUND.txt from bf65_how_found.py (the run records of BF#63 and
  BF#59).

## Open

1. DONE 2026-11-06 11:11: WSL /root/bf64_check (14 MB) deleted by path on
   Hani's OK by the session that made the TAMPURA tasks page, logged in
   DATA_LEDGER.md under Deleted.
2. Hani's choice among the fix options.  Option 1 or any fix is new work;
   the 40-scene comparison after a fix needs a cluster run, asked alone.
