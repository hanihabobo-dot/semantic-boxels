# BF#63 generated-scene eval: live state (hand-over for any session)

Started 2026-11-03 by Hani's request: "as quickly and as reliably get me
numbers of our approach vs tampura on find die ... at least 20 seeds vs 20
seeds that work ... no incomparable results" and, to the option of scenes
from their own generator ("20 new ones, one per seed, both arms on each,
their code untouched"): "yes, maximally so".

## Why

TAMPURA's paper (arXiv 2403.10454 v2, Task C) publishes no seeds and no
scenes; its released find_dice (tampura_environments, first public commit
2025-05-14) ships three scene files, so the campaign's seeds 0-19 are three
layouts. Their generator (find_dice/env_generator.py, 1 to 5 upside-down
cups and the die, the die hidden from the home camera) makes more.

## Design (declared before any run)

- Scenes: tools/gen_find_dice_scenes.py runs their env_generator.py
  unmodified (runpy, a scratch cwd, so it writes nothing into their tree);
  scene s = the first scene it accepts after random.seed(s) and
  numpy.random.seed(s); seeds 100-139 (outside the campaign's 0-19).
  Deterministic: seeds 100 and 101 generated twice gave byte-identical files.
  Output tampura_bridge/gen_scenes/find_dice/ (40 JSON + manifest.json with
  sha256, their file name, categories, cups). Nothing filtered.
- Loading: their loader does random.choice(os.listdir(
  'tampura_environments/find_dice/problems')) from the cwd, so each episode
  runs in a fresh directory holding only its scene (plus a link to their
  env_configs/). G19 pins seeds 100-139 to their scenes through
  BRIDGE_SCENE_MANIFEST (tools/bridge_gates.py merge_scene_manifest; the
  campaign's 0-19 cannot be re-pinned).
- Harness tools/gen_scene_eval.py: per repetition, scenes outer, both arms
  back to back per scene (T then O) on the same node; arm T =
  _bridge_campaign.episode_t (their planner as shipped, success
  rewards[-1] == 1.0), arm O = slip_eval.run_episode with BF#62's four
  switches named (success = bridge outcome success AND the pipeline's goal
  check); 900 s cap for both (B8's D10 value; BF#59's 600 s never bound
  TAMPURA on the shipped scenes, up to 415 s, but the new ones have up to
  five cups); global seed = scene seed.
- VALIDITY: an episode counts if it loaded its own scene and ended with an
  outcome (success, failure, or the cap = a failure). Crash, gate failure
  or wrong scene: run once more; if it fails to count again, that scene's
  repetition leaves the pairs for both arms and is listed.
- Cluster job tools/cluster/gen_eval.sbatch (gates before, tree after,
  prune_work), one job per group of scenes, one job per node.

## Phases

1. DONE: 40 scenes generated (seeds 100-139; cups 1: 7 scenes, 2: 9,
   3: 8, 4: 8, 5: 8; 14 to 385 s each), code written, 6 tests pass.
   Committed 6519b8e (tampura-bridge, not pushed).
2. DONE: local smoke from a git-archive export of 6519b8e (scratchpad
   bf63_smoke.sh, WSL, under the pipeline lock), scene 113 (1 cup), rep 0:
   static gates PASS; arm T success, wall 115.1 s (their loop 92.7 s); arm
   O success, wall 29.9 s, 1 die carry, 0 losses; both loaded
   find_dice_gen_s113.json; G19 pinned through the manifest, no mismatch.
   It showed two of the new tests failing when BRIDGE_SCENE_MANIFEST is set
   (the merge at import); the test now loads bridge_gates without it
   (passes with and without the variable). The smoke's outputs (9 MB in
   WSL /root, 1.2 MB tarball) deleted after this line (ledger).
3. DONE 2026-11-03 19:25.  68e7434 added the failure screenshots (Hani:
   every run that is not a counted success keeps its last two camera
   views and its metadata under OUT/failures/<arm>_s<seed>_r<rep>_a<n>/).
   The session that wrote it smoked the commit's own files in WSL
   (/root/bf63_smoke2.sh, scene 113, --shots all, blobs checked): arm T
   success 129.8 s, its one look's camera view kept; arm O success 33.2 s,
   4 eye images taken, the last 2 kept; the RolloutHistory pickle deleted
   after reading.  push_snapshot.ps1 -CodeOnly -Commit 68e7434 ->
   $W/sb_68e7434 (1.2 MB archive; the harness files' blobs checked on
   cn-04, LF).  Counted cluster usage before the run 495 MiB of 1024.
   Hani's cluster approval asked alone: "Yes, submit".  sb_6519b8e
   (pushed 18:56, before the screenshots) is referenced by no job.
4. FAILED, NOTHING RUN (2026-11-03 19:25 to 19:39): 10 jobs, OUT
   $W/results/gen_68e7434/<job>, 2 reps each, 900 s cap, nodes from sinfo
   just before: 5061712 cn-102 100-103, 5061713 cn-103 104-107, 5061714
   cn-104 108-111, 5061715 cn-109 112-115, 5061716 cn-111 116-119, 5061717
   cn-112 120-123, 5061718 cn-113 124-127, 5061719 cn-114 128-131, 5061720
   cn-115 132-135, 5061721 cn-116 136-139.  All ten stopped at the per-run
   gates before the first episode, each on the same line: "G13 FAIL arm
   T's installed tampura: arm T imports the checkout itself, not the
   install G13 expects".  Cause: gen_eval.sbatch exported arm O's
   PYTHONPATH (with $TW/tampura) before bridge_gates.py all and tree, and
   the gate's import check (_run) inherits the environment; slip_t.sbatch
   and b8_campaign.sbatch run the gates without it.  Arm T's episodes
   never see it (child_env sets their PYTHONPATH to the snapshot), so only
   the gate step was wrong.  Reproduced in WSL: with that PYTHONPATH G13
   FAILs (and pip freeze hashes differently), without it PASSes (2502 of
   2506 tracked files byte-equal, the line of job 5006490).  The smokes ran
   the harness, never the job script.  Seven jobs sat 5 to 10 min in a
   cluster stall (both gateways timed out 19:33 to 19:37; six ended at
   19:36:38, three at 19:37:07); 5061719 and 5061720 failed in under a
   minute.  Fix b2c6c5d: env -u PYTHONPATH on both gate calls.  The ten job
   logs are in eval/failed_g13_68e7434/ (tracked); the ten gate-only
   result folders, sb_68e7434 and sb_6519b8e deleted 19:50 (ledger).
5. Meanwhile another session committed 21226c8 and 811eda1: arm O's final
   scene from two fixed cameras (overview_final*.png, the die ringed),
   kept first among its failure screenshots.  Local end-to-end check of
   811eda1's job script (scratchpad bf63_e2e.sh: the snapshot laid out
   like $W under WSL /root/bf63_e2e, gen_eval.sbatch as is on scene 113,
   then the harness with --shots all, both under the pipeline lock),
   2026-11-03 19:52 to 19:57: the job script STOPS AT THE STATIC GATES
   (rc 1 after 37 s, nothing run): G2 FAIL "unlisted tampura_bridge/
   run_bridge_on_finddice.py:120 _save_overview: die_pos =
   c.getBasePositionAndOrientation(die)..." and G7 FAIL ":102 'die'" (the
   ring's ground-truth read and its label); G13 now PASSes (the fix
   holds).  The harness alone (--shots all) passes: T success 135.8 s, O
   success 41.8 s; O's failures/ folder holds overview_final.png (28 kB),
   overview_final_top.png (6 kB), two eye images, console_tail.txt,
   eye_last.json, meta.json; T's one camera view and meta.json; no image
   outside failures/, no RolloutHistory pickle left.  The main session is
   told (811eda1 is its commit).  The same check of b2c6c5d (68e7434 +
   21226c8's overviews without the ring + the G13 fix), 20:01 to 20:11:
   CLEAN.  Job script rc 0 after 352 s: every gate PASS before (G2 46
   hits all reviewed, G7 no scene literal, G13 with arm T's install), T
   success 185.6 s, O success 50.5 s (1 carry, 0 losses), the tree check
   after "unchanged", prune_work 8 MiB, GEN_DONE; no image outside
   failures/.  With --shots all: T success 161.4 s, O success 35.4 s; O's
   failures/ holds overview_final.png (21.5 kB), overview_final_top.png
   (7.9 kB), two eye images, console_tail.txt, eye_last.json, meta.json; T
   its camera view and meta.json.  (Laptop walls, not comparable with the
   cluster's.)
6. DONE 2026-11-03 20:36 to 22:38 (all ten COMPLETED, 1 h 27 to 1 h 59;
   every job's gates PASS before, tree unchanged after, harness rc 0).
   Hani, asked alone (sb_b2c6c5d now,
   or the ring made gate-clean first): "Yes, run b2c6c5d".  (The main
   session had meanwhile committed d344d17 at 20:08, the ring from the
   world eye's last record, gate-clean by its note; not known when the
   question was asked and not in this run.)  push_snapshot.ps1 -CodeOnly
   -Commit b2c6c5d -> $W/sb_b2c6c5d (six files' blobs checked on cn-04,
   LF); counted 490 MiB before.  10 jobs, OUT $W/results/gen_b2c6c5d/
   <job>, 2 reps, 900 s cap, nodes by idle CPUs just before: 5063076
   cn-102 100-103, 5063077 cn-103 104-107, 5063078 cn-104 108-111,
   5063079 cn-109 112-115, 5063080 cn-110 116-119, 5063081 cn-111
   120-123, 5063082 cn-112 124-127, 5063083 cn-113 128-131, 5063084
   cn-114 132-135, 5063085 cn-115 136-139.  The laptop's waiter polls
   sacct -X; an early look reports the first finished scene.
7. DONE 2026-11-03 22:40 to 23:10.  Pulled into eval/<job>/ (results.jsonl,
   metadata.json, gates, g13_before.json, failures/ with 138 images, the
   job log; 2 MB, tracked) through one tarball (deleted after, both ends).
   eval/REPORT.txt (the harness's report), TABLES.txt, O_FAILURES.txt,
   REPS.txt with their scripts.  Result, the load confound of repetition
   1, our failure mode (the die under a cup without a registered shadow:
   17 of our 23 failures) and the not-counted runs (TAMPURA's
   ZeroDivisionError in print_F, 9 runs; scene 138 out of the pairs): the
   BF#63 entry in PAPER_AUDIT.txt.  sb_b2c6c5d deleted (ledger).  Open
   for Hani: a re-run on reserved nodes (--exclusive) to remove the load
   confound; the analysis of the under-the-cup failures; whether a later
   run carries d344d17's ring (its job script unchecked).
8. PLANNED 2026-11-04 (Hani, to "Plan a re-run on reserved nodes to remove
   the load confound?": "Yes, plan it").  The confound was not busy nodes
   (BF#63 THE SLOW HOUR, eval/WINDOW.txt): from about 21:00 to 22:00 the
   NFS volume under $W slowed every episode's planning on all ten nodes at
   once (planning 15 to 24 times slower, execution steps unchanged, other
   users' CPUs on the nodes flat); all 14 TAMPURA timeouts began in that
   hour; outside it the pairs split 11 to 5 (p = 0.21, 45 pairs).
   Reserved nodes would not remove it (they reserve CPUs and memory, not
   the volume) and none is free (all 16 rleap_cpu nodes shared, 221 jobs
   pending at 11:40; BF#53 found an 11 h wait).  At 11:53 the volume still
   took up to 0.93 s to open a file and 0.96 s for a 4 kB write with fsync
   from cn-04 (local disk 0.02 s).
   RUN 2, declared before it runs:
   - What changes: gen_eval.sbatch's P4_LOCAL=1 mode.  The job's whole
     folder (episode folders, where planning writes its PDDL and temp
     files; records; failures/) is on the node's own /tmp, and at the end
     it becomes one tarball, $W/results/gen_<sha>/<job>.tar.gz.  The code
     and the venvs stay on $W (only read; 5.4 + 6.8 GB, too big to copy
     per node).  An I/O probe logs every 20 s (OUT/io_probe.tsv) the
     seconds to open a file on $W, to write 4 kB with fsync there and the
     same on the local disk.
   - Code: the commit of this phase = f07eef2 + the job script; its
     pipeline differs from run 1's b2c6c5d only in the final overviews
     (811eda1, d344d17: the die ringed from the world eye's last record,
     1024 x 768), drawn after the rollout and its record.  Before the push:
     git diff --stat b2c6c5d <sha> lists no other pipeline file.
   - The same as run 1: scenes 100-139, 2 repetitions, scenes outer, T then
     O per scene on one node, the 900 s cap, BF#62's four switches, the
     validity rule, --shots failures, 10 jobs of 4 scenes (100-103 ...
     136-139), one per node (-w, nodes by free CPUs just before), 8 CPUs
     and 24 GB each.  Submit: sbatch -w cn-1xx --export=ALL,P4_LOCAL=1
     $W/sb_<sha>/tools/cluster/gen_eval.sbatch sb_<sha> <seeds> 2
     $W/results/gen_<sha>
   - Headline: run 2 alone, reported as run 1 (REPORT.txt: per arm the
     counted runs, successes with Wilson 95 %, timeouts, not counted; the
     pairs with the exact McNemar p; per cup; walls).  Runs 1 and 2 are
     not pooled; run 1 stays in BF#63 with its slow hour.  Beside it: the
     agreement of runs 1 and 2 per (arm, scene, repetition).
   - Stall rule (fixed now): run 2's episodes write nothing to $W, so what
     can still slow them is opening files there (every start-up imports
     some thousand files from the venvs and the snapshot).  A stall is two
     consecutive probe rows (40 s) with the open on $W at 1 s or more
     (some 200 times a normal open).  The report lists every pair whose T
     or O run overlaps a stall and gives the result without them beside
     the headline; the write latencies on $W are reported per job (median,
     maximum) as the volume's state, not used to flag.  No pair is re-run
     for a stall; if stalls overlap more than a tenth of the pairs, the
     run is reported as it is and a further run is Hani's call.  Read
     beside it: arm O's planning-call times against run 1's outside the
     slow hour.
   - Time: about an hour (run 1's first repetition took 14 to 23 min per
     job outside the slow hour; one job at most 4 scenes x 2 repetitions x
     2 arms x 900 s = 4 h).  Data: about 324 MiB as run 1, as ten
     tarballs; counted usage 816 MiB of 1024 before, and the push's
     prune_work compacts slip_cff9bc5 (490 MiB, due since 00:50).
   - Pull: from each tarball the evidence files (results.jsonl,
     metadata.json, the gates, g13_before.json, io_probe.tsv, failures/)
     and the job log into eval2/<job>/; the tarballs stay under
     prune_work's retention.
   Checked on the laptop before asking (scratchpad trap_test.sh and
   bf63_e2e2.sh): the exit paths on stubs (the gates fail: rc 1 and the
   tarball; SIGTERM to the process group mid-harness: rc 143 and the
   tarball; an existing tarball: nothing run; no local folder, probe file
   or process left in each), then the job script end to end with
   P4_LOCAL=1 in WSL on scene 113 (f07eef2's code-only archive with the
   new job script, P4_WORK and P4_LOCAL_DIR under /root/bf63_e2e, under
   the pipeline lock), 12:05 to 12:15: rc 0 after 264 s; every gate PASS
   before (G2 46 hits all reviewed and G7 no scene literal, with the ring
   code), T success 154.7 s, O success 44.1 s (1 carry, 0 losses), the
   tree check after "unchanged", one tarball (92 kB: results.jsonl,
   metadata.json, the gates, g13_before.json, io_probe.tsv with 13 rows,
   T/ and O/), the local folder removed, no probe file left, prune_work,
   GEN_DONE.  Then the harness alone with --shots all: rc 0, T success
   190.8 s, O success 14.9 s; O's folder holds overview_final.png with the
   die ringed and named in the gripper (looked at), overview_final_top.png
   (the held die outside its frame, so no ring), two eye images,
   eye_last.json, the console tail and meta.json.  A first attempt at
   12:03 ran no episode: the harness's MACHINE check found another
   pipeline process alive (the parent session's headless watch run of
   seed 118) and stopped, as it should.  Between the check and the
   commit, HEAD moved from f07eef2 to 330e5e8 (README.md, run.ps1,
   tools/watch.ps1: laptop launcher files the cluster never runs).
