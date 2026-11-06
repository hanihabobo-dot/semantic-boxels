#!/bin/bash
# Reviewer: the S4n rule (S4o without its clearance clause) on the author's seeds and noise seeds,
# seeds 0 to 19 x 3 and held-out 100 to 119 x 2, through the review copies. Outputs in review_probe/out.
RP=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/slam_collect/review_probe
date
bash $RP/run_review.sh p6_two_beliefs.py S4n 3 20 0 > $RP/out/repro_console_S4n.txt 2>&1
echo "seeds 0-19 exit $?"
date
bash $RP/run_review.sh p6_two_beliefs.py S4n 2 20 100 > $RP/out/repro_console_S4n_seeds100.txt 2>&1
echo "seeds 100-119 exit $?"
date
