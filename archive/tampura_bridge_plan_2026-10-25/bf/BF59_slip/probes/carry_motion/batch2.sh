#!/bin/bash
# batch 2: quasi-static pure rotations of the hand (20 deg/s) about the pinch
# axis (y), across it (x) and about the approach axis (z); and the pipe
# executor again with the rotation axis recorded
P=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/carry_motion
cd $P
Y=0,1.5708,0.7854
bash run.sh b2_pitchy --executor cont --steps 12 --path pitchy --angle 60 --cells 6 --yaws $Y --trace > out/b2_pitchy.txt &
bash run.sh b2_pitchx --executor cont --steps 12 --path pitchx --angle 60 --cells 6 --yaws $Y --trace > out/b2_pitchx.txt &
bash run.sh b2_spinz --executor cont --steps 12 --path spinz --angle 90 --cells 6 --yaws $Y --trace > out/b2_spinz.txt &
bash run.sh b2_spinz_fast --executor cont --steps 2 --path spinz --angle 90 --cells 6 --yaws $Y --trace > out/b2_spinz_fast.txt &
bash run.sh b2_pipe --executor pipe --cells 6 --yaws $Y --trace > out/b2_pipe.txt &
bash run.sh b2_trap8 --executor trap --amax 8 --cells 6 --yaws $Y --trace > out/b2_trap8.txt &
wait
cat out/b2_*.txt
