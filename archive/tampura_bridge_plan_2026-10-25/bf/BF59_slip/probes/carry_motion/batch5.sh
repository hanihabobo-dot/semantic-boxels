#!/bin/bash
# batch 5: the pipeline's own grasp rule (wrap, M9) against flip (of the two
# pad-swapped equivalents g, g + pi the one whose hand turns least to home's)
# x the executors pipe / cont / trap at the datasheet accelerations, for a
# die that is NOT exactly face aligned (delta 3 and 10 deg, the eval's near
# face class), the edge pinch (delta 45) and the exact face (delta 0).
# 12 cells x 4 believed yaws x tilts 0, 3 = 96 carries per run; 4 at a time.
P=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/carry_motion
cd $P
Y=0,0.3927,-0.3927,0.7
jobs=()
for d in 3 10 45 0; do
  for rule in wrap flip; do
    for ex in pipe cont trap; do
      extra=""
      [ $ex = trap ] && extra="--amax ds"
      jobs+=("b5_${ex}_${rule}_d${d}|--executor $ex $extra --grasp-rule $rule --delta-deg $d --yaws $Y --tilts 0,3 --trace")
    done
  done
done
printf '%s\n' "${jobs[@]}" | xargs -P 4 -I{} bash -c 'n="${1%%|*}"; a="${1#*|}"; bash run.sh $n $a > out/$n.txt' _ {}
for f in out/b5_*.txt; do echo $f; tail -1 $f; done
