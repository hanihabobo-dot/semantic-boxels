#!/bin/bash
# the coupled-finger levers on the die (120 trials) and on our cubes and their cups (60)
H=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/hold_physics
G="gear gear_iters200 gear_force5 gear_force10 gear_force20 gear_iters200_force5 gear_iters200_force10 gear_iters200_force20 gear_sq1 gear_iters200_sq1"
bash $H/sweep.sh G 120 line 10 $G
for b in cube40_0.5 cube40_0.1 a_cups_ud; do
  BODY=$b bash $H/sweep.sh G_$b 60 line 10 $G
done
cd $H/out && /root/armO-venvA/bin/python $H/sink.py G_*.json
