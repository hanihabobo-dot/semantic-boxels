#!/bin/bash
# batch 1: the executors side by side, 12 cells x 5 yaws x tilts 0,8 = 120 carries each
P=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/carry_motion
cd $P
bash run.sh b1_pipe --executor pipe --trace > out/b1_pipe.txt &
bash run.sh b1_hop --executor hop --trace > out/b1_hop.txt &
bash run.sh b1_cont --executor cont --trace > out/b1_cont.txt &
bash run.sh b1_trap8 --executor trap --amax 8 --trace > out/b1_trap8.txt &
bash run.sh b1_slow05 --executor slow --scale 0.5 --trace > out/b1_slow05.txt &
bash run.sh b1_via_pipe --executor pipe --path via --trace > out/b1_via_pipe.txt &
bash run.sh b1_via_cont --executor cont --path via --trace > out/b1_via_cont.txt &
bash run.sh b1_via_trap8 --executor trap --path via --amax 8 --trace > out/b1_via_trap8.txt &
wait
cat out/b1_*.txt
