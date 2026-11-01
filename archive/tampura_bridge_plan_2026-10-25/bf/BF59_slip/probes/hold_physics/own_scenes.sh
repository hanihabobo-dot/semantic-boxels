#!/bin/bash
# the candidate levers on our own scenes' bodies (40 mm cubes 0.1 and 0.5 kg)
# and their cups (a, c), 60 trials each; prints one summary block per body
H=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/hold_physics
L="base force10 iters200 iters100_force10 iters200_force10 iters200_force20 proll0.01 iters200_force10_proll0.01"
for b in cube40_0.5 cube40_0.1 a_cups_ud c_cups_ud; do
  BODY=$b bash $H/sweep.sh E_$b 60 line 8 $L
done
