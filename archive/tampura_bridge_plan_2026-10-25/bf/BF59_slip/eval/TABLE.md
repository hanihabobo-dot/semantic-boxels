## Our arms (one row per arm and job; base runs in every job)

Wall "all" is the process wall of every episode with the timeouts at the cap (median and mean); "finished" the pipeline's own wall over the episodes that reached an outcome, so an arm that times out on the slow seeds looks faster there than it is: the paired ratios in the next tables compare the same seeds.

| job | arm | episodes | success | timeouts | carries | losses | loss/carry [95 %] | pick tries | wall s all: median | mean | wall s finished | planning s | exec s | mixed seeds | job elapsed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_5006486 | base | 60 | 44 | 8 | 52 | 8 | 0.15 [0.07, 0.28] | 52 | 39.1 | 117.5 | 26.4 | 13.3 | 11.5 | 8/20 (1,2,4,5,6,8,18,19) | 05:18:21 |
| A_5006486 | solver_iters | 60 | 26 | 4 | 57 | 31 | 0.54 [0.41, 0.68] | 57 | 41.3 | 96.5 | 28.4 | 13.7 | 13.0 | 7/20 (4,5,9,10,11,13,18) | 05:18:21 |
| A_5006486 | solver_iters+force_hold | 60 | 54 | 5 | 54 | 0 | 0.00 [0.00, 0.07] | 57 | 40.0 | 99.7 | 25.4 | 12.9 | 12.7 | 3/20 (5,6,13) | 05:18:21 |
| D_5006489 | base | 60 | 42 | 9 | 51 | 9 | 0.18 [0.08, 0.31] | 51 | 40.5 | 129.1 | 26.9 | 14.3 | 11.5 | 6/20 (1,5,8,10,14,18) | 02:48:56 |
| D_5006489 | solver_iters+force_hold+pose_radius_keep+grasp_wrist_home | 60 | 60 | 0 | 60 | 0 | 0.00 [0.00, 0.06] | 60 | 42.5 | 37.8 | 30.4 | 14.3 | 13.9 | 0/20 | 02:48:56 |
| all | base (pooled) | 120 | 86 | 17 | 103 | 17 | 0.17 [0.10, 0.25] | 103 | 39.4 | 123.3 | 26.5 | 13.7 | 11.5 | 10/20 | - |

## Times paired with the base of the same job (the same seed and repetition, both finished)

| job | arm | pairs | wall s median arm / base | median of the per-pair ratio | planning s arm / base | ratio | exec s arm / base | ratio | process wall all 60, mean arm / base |
|---|---|---|---|---|---|---|---|---|---|
| A_5006486 | solver_iters | 50 | 27.6 / 26.4 | x1.08 | 12.8 / 13.1 | x1.02 | 12.2 / 10.4 | x1.15 | 96.5 / 117.5 |
| A_5006486 | solver_iters+force_hold | 50 | 18.2 / 23.9 | x1.06 | 9.7 / 12.7 | x0.99 | 7.8 / 8.7 | x1.15 | 99.7 / 117.5 |
| D_5006489 | solver_iters+force_hold+pose_radius_keep+grasp_wrist_home | 51 | 28.4 / 26.9 | x1.07 | 13.6 / 13.8 | x0.97 | 12.9 / 9.2 | x1.15 | 37.8 / 129.1 |

## Per scene: successes/episodes and losses/carries

| job | arm | 1747173590 (seeds 5,6,10,17,19) | 1747173591 (seeds 0,7,9,11,12,13,16) | 1747173593 (seeds 1,2,3,4,8,14,15,18) |
|---|---|---|---|---|
| A_5006486 | base | 7/15, losses 0/7 | 21/21, losses 0/21 | 16/24, losses 8/24 |
| A_5006486 | solver_iters | 5/15, losses 7/12 | 6/21, losses 14/20 | 15/24, losses 10/25 |
| A_5006486 | solver_iters+force_hold | 10/15, losses 0/10 | 20/21, losses 0/20 | 24/24, losses 0/24 |
| D_5006489 | base | 3/15, losses 3/6 | 21/21, losses 0/21 | 18/24, losses 6/24 |
| D_5006489 | solver_iters+force_hold+pose_radius_keep+grasp_wrist_home | 15/15, losses 0/15 | 21/21, losses 0/21 | 24/24, losses 0/24 |

## Each arm against base (Fisher's exact test, two-sided)

| job | arm | losses/carries arm vs base of its job | p | vs pooled base | p | success arm vs base of its job | p | vs pooled base | p |
|---|---|---|---|---|---|---|---|---|---|
| A_5006486 | solver_iters | 31/57 vs 8/52 | 2.28e-05 | 31/57 vs 17/103 | 1.47e-06 | 26/60 vs 44/60 | 0.00152 | 26/60 vs 86/120 | 0.000311 |
| A_5006486 | solver_iters+force_hold | 0/54 vs 8/52 | 0.0025 | 0/54 vs 17/103 | 0.000695 | 54/60 vs 44/60 | 0.0321 | 54/60 vs 86/120 | 0.00713 |
| D_5006489 | solver_iters+force_hold+pose_radius_keep+grasp_wrist_home | 0/60 vs 9/51 | 0.000602 | 0/60 vs 17/103 | 0.00031 | 60/60 vs 42/60 | 1.7e-06 | 60/60 vs 86/120 | 2.66e-07 |

## Replication: outcomes per seed (S success, F failure, T timeout; repetitions in order)

| job | arm | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_5006486 | base | SSS | FSS | SSF | SSS | FSS | TSS | TTS | SSS | FSS | SSS | SSS | SSS | SSS | SSS | FFF | SSS | SSS | TTT | SFS | STT |
| A_5006486 | solver_iters | SSS | SSS | FFF | SSS | FFS | FFS | TTT | FFF | SSS | FSF | FSF | SSF | FFF | TFF | FFF | SSS | FFF | FFF | FSS | SSS |
| A_5006486 | solver_iters+force_hold | SSS | SSS | SSS | SSS | SSS | STS | SST | SSS | SSS | SSS | SSS | SSS | SSS | FSS | SSS | SSS | SSS | TTT | SSS | SSS |
| D_5006489 | base | SSS | FSS | SSS | SSS | SSS | SFF | TTT | SSS | FSS | SSS | SSF | SSS | SSS | SSS | FFS | SSS | SSS | TTT | FSF | TTT |
| D_5006489 | solver_iters+force_hold+pose_radius_keep+grasp_wrist_home | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS |

## TAMPURA (arm T, job T_5006490, elapsed 02:50:28)

- episodes 60, successes 40 (67 %, exact 95 % [53, 78] %), crashed 1, censored at the cap 1
- per repetition: rep 1: 13/20; rep 2: 14/20; rep 3: 13/20
- per scene: 1747173590: 7/15; 1747173591: 19/21; 1747173593: 14/24
- times (finished episodes, n=59): median loop 153.4 s, wall 165.3 s, planning 131.5 s; successes only: loop 92.7 s, time to success 92.7 s
- replication: 9/20 seeds mixed (1, 3, 4, 9, 14, 15, 16, 18, 19); per seed: 0:SSS, 1:FSS, 2:FFF, 3:FFS, 4:SFS, 5:SSS, 6:SSS, 7:SSS, 8:SSS, 9:SSC, 10:FFF, 11:SSS, 12:SSS, 13:SSS, 14:SSF, 15:SFS, 16:SSF, 17:FFF, 18:FSS, 19:FSF

