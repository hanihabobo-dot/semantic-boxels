# DECLARATION: paired set <ID> (copy this file to evals/<id>/DECLARATION.md)

Written and committed before the first run (PLAN section 8). The one block
marked `json paired-set` below is what `tools/readable/paired_sets.py`
reads; the prose is for people and must say the same. Every `<...>` and
every zero sha is a placeholder: `run` refuses a zero sha, and refuses a
stored statistics copy whose sha256 is not the declared one. Check the
block with `python tools/readable/paired_sets.py plan --set-dir evals/<id>`
and paste the run list it prints into `runs`. Once a run has started, the
declaration is not changed: the rows carry its sha256, and a changed file
leaves the set "not full". A repeat is a new declaration in a new folder.

## 1. The set and the two shas

- Kind: N (noise: the reference against itself, PLAN 24.4 (a)), S (smoke,
  end of P4), A (end of P6) or B (end of the last code phase).
- Arm A, role old: `<full 40-hex sha>`, frozen clean checkout `<path>`.
- Arm B, role new: `<full 40-hex sha>` (set N: the same sha as A),
  checkout `<path>` (set N may use the same checkout for both arms).
- Each checkout is a clean worktree of its sha: `run` checks HEAD and an
  empty `git status --porcelain` at the start and at the end (S-p).

## 2. Seeds, pairing, order

- Boxels: `random-pairs`, goal holding, 2 occluders, baseline semantic, no
  unit costs; seeds `<0 to 19 for N, A, B; 0 to 5 for S>`.
- Bridge: the shipped find_dice seeds `<0 to 19 for N, A, B; 0, 1, 5 for
  S>`, the scene the laptop's listing gives each seed (validity note 3).
- Pairing by seed: both arms run every declared seed of a world, on the
  same scene; never different counts (Hani, 14 Nov about 08:50).
- Order ABBA: worlds in `world_order`, seeds in their declared order; pair
  k runs A then B when k is even and B then A when k is odd (A B B A A B
  ...), the alternation carried from one world to the next. The full list
  with its position numbers is in `runs`.
- A pair whose two starts are more than `pair_gap_max_s` apart is flagged
  in the report (S-r).

## 3. The machine and the switches

- This laptop, WSL `Ubuntu` as root, `/root/armO-venvA/bin/python`,
  `PYTHONHASHSEED=0`, one simulation at a time: each episode script takes
  `flock /root/sb_pipeline.lock` and holds it from the statistics restore
  to the end of the episode; under 4 GB MemAvailable with the lock held the
  episode does not start (rule 16) and the set stops there.
- Every episode is started through the health gate `gate_run.ps1` (commit
  charge under 85 % and the lock free at each start; it waits at most
  `gate_max_minutes`); `pause_s` seconds between episodes.
- Per-episode wall cap (`cap_s`, GNU `timeout -k 30`, which signals the
  whole process group): boxels `<300>` s, bridge `<to decide: above the
  driver's 900 s plan cap>` s. A run killed at the cap is a failure with
  its own status (boxels `timeout`, bridge `killed`).
- Switches: launcher defaults, none (`switches: []`). Boxels runs the argv
  of `eval_runner.cell_to_argv` (`--log-level quiet --no-telemetry`); the
  bridge runs `run tampura -Headless`'s (`--vis 0 --allow-g19-mismatch 1`).
- Library: `pddlstream_lib` at `<path>`; its commit and the venv's `pip
  freeze` sha256 are stored at the start and the end of the set.

## 4. The planner's statistics file (PLAN 24.4 (e), R's note 3)

- Boxels: one stored copy of the reference's accumulated
  `statistics/py3/boxel-streams.pkl`, taken before set N: `<path>`, sha256
  `<64 hex>`. It is restored into the arm's checkout before every boxels
  episode of both arms, under the same hold of the lock as the episode;
  every row records the sha256 it started from (and the one it left) and
  its position in the run sequence. The file does not accumulate during a
  set (the one point where this departs from Hani's Q15 answer, named to
  him with D10). The stored copy is a data file: DATA_LEDGER, not git.
- Bridge: each episode starts, as the reference does, in its own fresh
  `work/` folder under its run directory (`tampura_bridge/policy.py:185-189`),
  so it starts from no statistics file; the rows' sha256 is null.

## 5. What is compared, and the pass rule

- Per arm and world: success; the outcome status; the multiset of exit
  reasons; the failed gates without G19 (bridge); crashes. Plan counts per
  seed, wall and planning times: information only (24.4 (c)).
- Bridge success: reward 1.0 and no failed gate other than G19 (S-q); the
  scene file is checked equal per pair.
- Set N: recorded; its net one-way flips per world give item 3's threshold
  of A and B (3 or more: the threshold is N's count plus 1, and R is told
  before set A runs).
- Set S: passes with no crash and no exit reason or outcome kind that the
  old arm never shows.
- Sets A and B, per world (24.4 (b)): fail on (1) a crash of the new arm
  that its review pair puts on the migration; (2) an exit reason, outcome
  kind or failed gate (G19 aside) in the new arm that neither the old arm
  nor set N shows; (3) net one-way flips against the new arm at or above
  the threshold (3, or N's count plus 1); (4) an exact two-sided McNemar
  test on the flips below 0.05. Noise set: `<evals/N folder>`.

## 6. Crashes and counting (PLAN 8, 22, 24.4 (f))

- A crash is found from the run's files, not from the exit code: boxels,
  no `timing_summary.json` in a new run directory, an exit code other than
  0 or 1, or a traceback in stdout, stderr or the run directory's logs;
  bridge, `bridge_episode.json` says crashed or has an error, is missing
  without a G19 or G13 stop, or a traceback is in the console or the run
  log.
- One result per seed and arm, the first attempt; a crash is a failure in
  both arms; no rerun counts or replaces. Each crash gets a record (seed,
  arm, traceback, log path, cause); a crash of the new arm gets an agent
  review pair on Opus 5.5 before the set counts.
- Full: every declared run has one start and one end row matching this
  declaration, none is not started, vanished or on the wrong scene. The
  numbers are recomputed from `results.jsonl` by `paired_sets.py analyse`.

## 7. Validity notes (printed with every number of this set)

(1) An episode's first plan is not repeatable (TB-24): the arms are
compared as distributions over paired seeds, never episode by episode.
(2) Plan time caps are wall clock, so laptop load changes plans; times are
not compared. (3) The laptop's scene listing for the shipped bridge seeds
differs from the cluster's pinned one: these numbers are not comparable
with the paper's; both arms see the same scene per seed.

## 8. The machine-read block

```json paired-set
{
  "declaration_version": 1,
  "set_id": "N",
  "kind": "N",
  "arms": {
    "A": {"role": "old", "sha": "0000000000000000000000000000000000000000",
          "checkout": "<checkouts>/sb-ref"},
    "B": {"role": "new", "sha": "0000000000000000000000000000000000000000",
          "checkout": "<checkouts>/sb-ref"}
  },
  "worlds": {
    "boxels": {
      "seeds": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
      "cell": {"scene": "random-pairs", "goal": "holding", "n_occluders": 2,
               "baseline": "semantic", "unit_costs": false},
      "cap_s": 300
    },
    "bridge": {
      "seeds": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
      "cap_s": 1200
    }
  },
  "world_order": ["boxels", "bridge"],
  "pairing": "by_seed",
  "order": "ABBA",
  "switches": [],
  "machine": {
    "python": "/root/armO-venvA/bin/python",
    "pythonhashseed": "0",
    "lock": "/root/sb_pipeline.lock",
    "gate_script": "<the health gate script, a Windows path>",
    "gate_max_minutes": 180,
    "mem_available_min_gb": 4,
    "pause_s": 60,
    "wsl_distro": "Ubuntu",
    "tampura_work": "/root/tampura-work",
    "pddlstream_lib": "<checkouts>/pddlstream_lib"
  },
  "statistics_file": {
    "boxels": {"stored_copy": "<checkouts>/sb-ref-stats/boxel-streams.pkl",
               "sha256": "0000000000000000000000000000000000000000000000000000000000000000"},
    "bridge": {"start": "a fresh work folder per episode, no file", "sha256": null}
  },
  "noise_set_dir": null,
  "pair_gap_max_s": 3600,
  "runs": null
}
```
