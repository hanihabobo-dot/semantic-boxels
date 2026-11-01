#!/bin/bash
# batch 3: the order of the wrist's two rotations (pitch 35 deg about the
# pinch axis, spin 90 deg about the approach axis), slow and fast
P=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/carry_motion
cd $P
Y=0,1.5708,0.7854
for path in pitchspin spinpitch; do
  for ang in 90 -90; do
    bash run.sh b3_${path}_${ang}_slow --executor cont --steps 12 --path $path --angle $ang --pitch 35 --cells 6 --yaws $Y --trace > out/b3_${path}_${ang}_slow.txt &
    bash run.sh b3_${path}_${ang}_fast --executor cont --steps 3 --path $path --angle $ang --pitch 35 --cells 6 --yaws $Y --trace > out/b3_${path}_${ang}_fast.txt &
  done
done
wait
cat out/b3_*.txt
