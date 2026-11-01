## Our arms (one row per arm and job; base runs in every job)

Wall "all" is the process wall of every episode with the timeouts at the cap (median and mean); "finished" the pipeline's own wall over the episodes that reached an outcome, so an arm that times out on the slow seeds looks faster there than it is: the paired ratios in the next tables compare the same seeds.

| job | arm | episodes | success | timeouts | carries | losses | loss/carry [95 %] | pick tries | wall s all: median | mean | wall s finished | planning s | exec s | mixed seeds | job elapsed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_5006486 | base | 60 | 44 | 8 | 52 | 8 | 0.15 [0.07, 0.28] | 52 | 39.1 | 117.5 | 26.4 | 13.3 | 11.5 | 8/20 (1,2,4,5,6,8,18,19) | 05:18:21 |
| A_5006486 | solver_iters | 60 | 26 | 4 | 57 | 31 | 0.54 [0.41, 0.68] | 57 | 41.3 | 96.5 | 28.4 | 13.7 | 13.0 | 7/20 (4,5,9,10,11,13,18) | 05:18:21 |
| A_5006486 | solver_iters+force_hold | 60 | 54 | 5 | 54 | 0 | 0.00 [0.00, 0.07] | 57 | 40.0 | 99.7 | 25.4 | 12.9 | 12.7 | 3/20 (5,6,13) | 05:18:21 |
| B_5006487 | base | 60 | 40 | 8 | 51 | 11 | 0.22 [0.11, 0.35] | 51 | 39.3 | 113.8 | 26.9 | 13.9 | 11.4 | 7/20 (1,5,8,11,15,18,19) | 05:39:44 |
| B_5006487 | pose_radius_keep | 60 | 39 | 1 | 59 | 20 | 0.34 [0.22, 0.47] | 59 | 39.6 | 53.3 | 27.7 | 13.7 | 12.0 | 10/20 (1,4,5,8,10,11,12,13,15,17) | 05:39:44 |
| B_5006487 | pose_radius_keep+grasp_wrist_home | 60 | 49 | 10 | 50 | 1 | 0.02 [0.00, 0.11] | 50 | 50.5 | 170.1 | 33.3 | 22.0 | 14.9 | 5/20 (3,4,14,15,18) | 05:39:44 |
| C_5006488 | base | 60 | 42 | 6 | 54 | 12 | 0.22 [0.12, 0.36] | 54 | 39.2 | 105.4 | 26.8 | 13.6 | 11.5 | 5/20 (1,3,6,18,19) | 06:37:52 |
| C_5006488 | carry_hold_check | 60 | 42 | 10 | 51 | 9 | 0.18 [0.08, 0.31] | 54 | 40.4 | 137.8 | 24.1 | 13.7 | 11.8 | 7/20 (1,5,8,10,14,18,19) | 06:37:52 |
| C_5006488 | pose_radius_keep+grasp_wrist_home+carry_trapezoid | 60 | 54 | 5 | 54 | 0 | 0.00 [0.00, 0.07] | 54 | 53.0 | 152.7 | 38.4 | 23.0 | 14.6 | 5/20 (1,3,4,15,18) | 06:37:52 |
| D_5006489 | base | 60 | 42 | 9 | 51 | 9 | 0.18 [0.08, 0.31] | 51 | 40.5 | 129.1 | 26.9 | 14.3 | 11.5 | 6/20 (1,5,8,10,14,18) | 02:48:56 |
| D_5006489 | solver_iters+force_hold+pose_radius_keep+grasp_wrist_home | 60 | 60 | 0 | 60 | 0 | 0.00 [0.00, 0.06] | 60 | 42.5 | 37.8 | 30.4 | 14.3 | 13.9 | 0/20 | 02:48:56 |
| all | base (pooled) | 240 | 168 | 31 | 208 | 40 | 0.19 [0.14, 0.25] | 208 | 39.4 | 116.5 | 26.8 | 13.7 | 11.5 | 13/20 | - |

## Times paired with the base of the same job (the same seed and repetition, both finished)

| job | arm | pairs | wall s median arm / base | median of the per-pair ratio | planning s arm / base | ratio | exec s arm / base | ratio | process wall all 60, mean arm / base |
|---|---|---|---|---|---|---|---|---|---|
| A_5006486 | solver_iters | 50 | 27.6 / 26.4 | x1.08 | 12.8 / 13.1 | x1.02 | 12.2 / 10.4 | x1.15 | 96.5 / 117.5 |
| A_5006486 | solver_iters+force_hold | 50 | 18.2 / 23.9 | x1.06 | 9.7 / 12.7 | x0.99 | 7.8 / 8.7 | x1.15 | 99.7 / 117.5 |
| B_5006487 | pose_radius_keep | 51 | 26.9 / 26.9 | x1.00 | 13.3 / 13.7 | x0.99 | 11.2 / 11.0 | x1.00 | 53.3 / 113.8 |
| B_5006487 | pose_radius_keep+grasp_wrist_home | 42 | 21.6 / 17.1 | x1.01 | 11.3 / 9.8 | x1.03 | 8.7 / 5.8 | x1.04 | 170.1 / 113.8 |
| C_5006488 | carry_hold_check | 50 | 24.1 / 26.7 | x1.02 | 12.2 / 13.3 | x1.02 | 8.7 / 11.2 | x1.05 | 137.8 / 105.4 |
| C_5006488 | pose_radius_keep+grasp_wrist_home+carry_trapezoid | 49 | 37.4 / 26.8 | x1.07 | 21.7 / 13.3 | x1.04 | 14.1 / 11.2 | x1.22 | 152.7 / 105.4 |
| D_5006489 | solver_iters+force_hold+pose_radius_keep+grasp_wrist_home | 51 | 28.4 / 26.9 | x1.07 | 13.6 / 13.8 | x0.97 | 12.9 / 9.2 | x1.15 | 37.8 / 129.1 |

## Per scene: successes/episodes and losses/carries

| job | arm | 1747173590 (seeds 5,6,10,17,19) | 1747173591 (seeds 0,7,9,11,12,13,16) | 1747173593 (seeds 1,2,3,4,8,14,15,18) |
|---|---|---|---|---|
| A_5006486 | base | 7/15, losses 0/7 | 21/21, losses 0/21 | 16/24, losses 8/24 |
| A_5006486 | solver_iters | 5/15, losses 7/12 | 6/21, losses 14/20 | 15/24, losses 10/25 |
| A_5006486 | solver_iters+force_hold | 10/15, losses 0/10 | 20/21, losses 0/20 | 24/24, losses 0/24 |
| B_5006487 | base | 6/15, losses 1/7 | 20/21, losses 1/21 | 14/24, losses 9/23 |
| B_5006487 | pose_radius_keep | 11/15, losses 4/15 | 18/21, losses 2/20 | 10/24, losses 14/24 |
| B_5006487 | pose_radius_keep+grasp_wrist_home | 15/15, losses 0/15 | 21/21, losses 0/21 | 13/24, losses 1/14 |
| C_5006488 | base | 9/15, losses 0/9 | 21/21, losses 0/21 | 12/24, losses 12/24 |
| C_5006488 | carry_hold_check | 3/15, losses 3/6 | 21/21, losses 0/21 | 18/24, losses 6/24 |
| C_5006488 | pose_radius_keep+grasp_wrist_home+carry_trapezoid | 15/15, losses 0/15 | 21/21, losses 0/21 | 18/24, losses 0/18 |
| D_5006489 | base | 3/15, losses 3/6 | 21/21, losses 0/21 | 18/24, losses 6/24 |
| D_5006489 | solver_iters+force_hold+pose_radius_keep+grasp_wrist_home | 15/15, losses 0/15 | 21/21, losses 0/21 | 24/24, losses 0/24 |

## Each arm against base (Fisher's exact test, two-sided)

| job | arm | losses/carries arm vs base of its job | p | vs pooled base | p | success arm vs base of its job | p | vs pooled base | p |
|---|---|---|---|---|---|---|---|---|---|
| A_5006486 | solver_iters | 31/57 vs 8/52 | 2.28e-05 | 31/57 vs 40/208 | 4.53e-07 | 26/60 vs 44/60 | 0.00152 | 26/60 vs 168/240 | 0.000238 |
| A_5006486 | solver_iters+force_hold | 0/54 vs 8/52 | 0.0025 | 0/54 vs 40/208 | 6.69e-05 | 54/60 vs 44/60 | 0.0321 | 54/60 vs 168/240 | 0.00153 |
| B_5006487 | pose_radius_keep | 20/59 vs 11/51 | 0.203 | 20/59 vs 40/208 | 0.0217 | 39/60 vs 40/60 | 1 | 39/60 vs 168/240 | 0.533 |
| B_5006487 | pose_radius_keep+grasp_wrist_home | 1/50 vs 11/51 | 0.00383 | 1/50 vs 40/208 | 0.00109 | 49/60 vs 40/60 | 0.0943 | 49/60 vs 168/240 | 0.0773 |
| C_5006488 | carry_hold_check | 9/51 vs 12/54 | 0.63 | 9/51 vs 40/208 | 1 | 42/60 vs 42/60 | 1 | 42/60 vs 168/240 | 1 |
| C_5006488 | pose_radius_keep+grasp_wrist_home+carry_trapezoid | 0/54 vs 12/54 | 0.000246 | 0/54 vs 40/208 | 6.69e-05 | 54/60 vs 42/60 | 0.011 | 54/60 vs 168/240 | 0.00153 |
| D_5006489 | solver_iters+force_hold+pose_radius_keep+grasp_wrist_home | 0/60 vs 9/51 | 0.000602 | 0/60 vs 40/208 | 2.02e-05 | 60/60 vs 42/60 | 1.7e-06 | 60/60 vs 168/240 | 1.16e-08 |

## Replication: outcomes per seed (S success, F failure, T timeout; repetitions in order)

| job | arm | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_5006486 | base | SSS | FSS | SSF | SSS | FSS | TSS | TTS | SSS | FSS | SSS | SSS | SSS | SSS | SSS | FFF | SSS | SSS | TTT | SFS | STT |
| A_5006486 | solver_iters | SSS | SSS | FFF | SSS | FFS | FFS | TTT | FFF | SSS | FSF | FSF | SSF | FFF | TFF | FFF | SSS | FFF | FFF | FSS | SSS |
| A_5006486 | solver_iters+force_hold | SSS | SSS | SSS | SSS | SSS | STS | SST | SSS | SSS | SSS | SSS | SSS | SSS | FSS | SSS | SSS | SSS | TTT | SSS | SSS |
| B_5006487 | base | SSS | FFS | SSS | SSS | SSS | SFT | TTT | SSS | SFS | SSS | SSS | FSS | SSS | SSS | FFF | FSF | SSS | TTT | SFF | STS |
| B_5006487 | pose_radius_keep | SSS | SFS | FFF | SSS | FSS | SSF | SSS | SSS | FFS | SSS | SSF | SST | SFS | FSS | FFF | SFS | SSS | FSF | FFF | SSS |
| B_5006487 | pose_radius_keep+grasp_wrist_home | SSS | TTT | SSS | TSS | TST | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | TST | TSS | SSS | SSS | SFT | SSS |
| C_5006488 | base | SSS | SSF | FFF | SSF | SSS | SSS | TST | SSS | FFF | SSS | SSS | SSS | SSS | SSS | FFF | SSS | SSS | TTT | FSS | SST |
| C_5006488 | carry_hold_check | SSS | TFS | SSS | SSS | SSS | SFT | TTT | SSS | FSS | SSS | FSS | SSS | SSS | SSS | SFF | SSS | SSS | TTT | SFS | TFT |
| C_5006488 | pose_radius_keep+grasp_wrist_home+carry_trapezoid | SSS | STS | SSS | STS | STF | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | TSS | SSS | SSS | TSS | SSS |
| D_5006489 | base | SSS | FSS | SSS | SSS | SSS | SFF | TTT | SSS | FSS | SSS | SSF | SSS | SSS | SSS | FFS | SSS | SSS | TTT | FSF | TTT |
| D_5006489 | solver_iters+force_hold+pose_radius_keep+grasp_wrist_home | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS | SSS |

## TAMPURA (arm T, job T_5006490, elapsed 02:50:28)

- episodes 60, successes 40 (67 %, exact 95 % [53, 78] %), crashed 1, censored at the cap 1
- per repetition: rep 1: 13/20; rep 2: 14/20; rep 3: 13/20
- per scene: 1747173590: 7/15; 1747173591: 19/21; 1747173593: 14/24
- times (finished episodes, n=59): median loop 153.4 s, wall 165.3 s, planning 131.5 s; successes only: loop 92.7 s, time to success 92.7 s
- replication: 9/20 seeds mixed (1, 3, 4, 9, 14, 15, 16, 18, 19); per seed: 0:SSS, 1:FSS, 2:FFF, 3:FFS, 4:SFS, 5:SSS, 6:SSS, 7:SSS, 8:SSS, 9:SSC, 10:FFF, 11:SSS, 12:SSS, 13:SSS, 14:SSF, 15:SFS, 16:SSF, 17:FFF, 18:FSS, 19:FSF

