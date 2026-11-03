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
4. RUNNING since 2026-11-03 19:25: 10 jobs, OUT $W/results/gen_68e7434/
   <job>, 2 reps each, 900 s cap, nodes from sinfo just before:
   5061712 cn-102 100-103, 5061713 cn-103 104-107, 5061714 cn-104 108-111,
   5061715 cn-109 112-115, 5061716 cn-111 116-119, 5061717 cn-112 120-123,
   5061718 cn-113 124-127, 5061719 cn-114 128-131, 5061720 cn-115 132-135,
   5061721 cn-116 136-139.  The laptop's waiter polls sacct -X (never
   squeue alone).  Next: pull results.jsonl, metadata.json, gates_before/
   after.txt, the job log and failures/ into eval/<job>/ (tracked).
5. Report: tools/gen_scene_eval.py --report; BF#63 entry; ledger rows.
