#!/bin/bash
# BF#59 force_hold jam probe, batch 1: every lever at both places, 8 reps,
# six probes at a time (physics only, no lock).
H=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/force_hold
mkdir -p $H/out
run() { bash $H/run.sh --lever $1 --iters $2 --place $3 --reps 8 --trace 0 --out $H/out/b1_$1_i$2_p$3.json > $H/out/b1_$1_i$2_p$3.txt 2>&1; }
N=0
for PL in ep000 003; do
  for L in fh base fh_nogear fh_reach1 fh_f20; do
    run $L 200 $PL &
    N=$((N+1)); if [ $((N % 6)) -eq 0 ]; then wait; fi
  done
  run fh 50 $PL &
  run base 50 $PL &
  N=$((N+2)); wait
done
wait
grep -h SUMMARY $H/out/b1_*.txt
