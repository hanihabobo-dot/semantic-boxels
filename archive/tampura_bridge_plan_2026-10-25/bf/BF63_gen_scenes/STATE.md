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

1. IN PROGRESS: scenes generated (seeds 100-139), code written, tests.
2. Commit, local smoke (one scene, both arms, from a git-archive export).
3. push_snapshot.ps1 -CodeOnly; Hani's cluster approval (asked alone).
4. Submit; wait (poll sacct, never squeue alone); pull results.jsonl,
   metadata, gates and job logs into this folder (tracked).
5. Report: tools/gen_scene_eval.py --report; BF#63 entry; ledger rows.
