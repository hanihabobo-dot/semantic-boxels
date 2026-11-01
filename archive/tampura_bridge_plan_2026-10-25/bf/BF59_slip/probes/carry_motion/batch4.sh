#!/bin/bash
# batch 4: the grasp-yaw rule (same face as the die's yaw, or the equivalent
# face whose hand turns least to home's) under pipe, cont and trap; 7 die yaws
P=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/carry_motion
cd $P
Y=0,0.3927,0.7854,1.1781,1.5708,-0.3927,-0.7854
for rule in same minturn; do
  bash run.sh b4_pipe_$rule --executor pipe --grasp-rule $rule --yaws $Y --trace > out/b4_pipe_$rule.txt &
  bash run.sh b4_cont_$rule --executor cont --grasp-rule $rule --yaws $Y --trace > out/b4_cont_$rule.txt &
  bash run.sh b4_trap8_$rule --executor trap --amax 8 --grasp-rule $rule --yaws $Y --trace > out/b4_trap8_$rule.txt &
done
wait
for f in out/b4_*.txt; do echo $f; cat $f; done
