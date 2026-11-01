#!/bin/bash
# batch 6: (a) the quarter-turn class (minturn) against flip at 10 deg;
# (b) flip on an RRT-like bent path (via); (c) the hold at home, 2 s more;
# (d) the band edge at 20 deg; (e) our own bodies (the 40 mm 100 g cube,
# the 60 mm 500 g block) under wrap / flip x pipe / trap.  4 at a time.
P=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/carry_motion
cd $P
Y=0,0.3927,-0.3927,0.7
C="--yaws $Y --tilts 0,3 --trace"
jobs=(
 "b6_pipe_minturn_d10|--executor pipe --grasp-rule minturn --delta-deg 10 $C"
 "b6_cont_minturn_d10|--executor cont --grasp-rule minturn --delta-deg 10 $C"
 "b6_trap_minturn_d10|--executor trap --amax ds --grasp-rule minturn --delta-deg 10 $C"
 "b6_pipe_flip_d10_via|--executor pipe --path via --grasp-rule flip --delta-deg 10 $C"
 "b6_trap_flip_d10_via|--executor trap --amax ds --path via --grasp-rule flip --delta-deg 10 $C"
 "b6_pipe_wrap_d10_via|--executor pipe --path via --grasp-rule wrap --delta-deg 10 $C"
 "b6_trap_flip_d10_after|--executor trap --amax ds --grasp-rule flip --delta-deg 10 --after 480 $C"
 "b6_pipe_wrap_d10_after|--executor pipe --grasp-rule wrap --delta-deg 10 --after 480 $C"
 "b6_trap_flip_d20|--executor trap --amax ds --grasp-rule flip --delta-deg 20 $C"
 "b6_pipe_wrap_d20|--executor pipe --grasp-rule wrap --delta-deg 20 $C"
)
for pl in cube100g block500g; do
  for d in 0 3; do
    [ $pl = block500g ] && [ $d = 3 ] && continue
    for rule in wrap flip; do
      jobs+=("b6_${pl}_pipe_${rule}_d${d}|--payload $pl --executor pipe --grasp-rule $rule --delta-deg $d $C")
      jobs+=("b6_${pl}_trap_${rule}_d${d}|--payload $pl --executor trap --amax ds --grasp-rule $rule --delta-deg $d $C")
    done
  done
done
printf '%s\n' "${jobs[@]}" | xargs -P 4 -I{} bash -c 'n="${1%%|*}"; a="${1#*|}"; bash run.sh $n $a > out/$n.txt' _ {}
for f in out/b6_*.txt; do echo $f; tail -1 $f; done
