#!/bin/bash
# usage: run_episode.sh <seed> <tag> [driver flags...]   (one find_dice episode under the lock)
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels
TW=/root/tampura-work
P=$S/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/loss_dynamics
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
export PYTHONPATH=$S:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:$TW/tampura:$TW/tampura_environments
PY=/root/armO-venvA/bin/python
OUT=$P/runs/$2
mkdir -p $OUT
cd $TW/tampura_environments
flock /root/sb_pipeline.lock -c "timeout 600 $PY $P/run_probe.py $OUT/carry.jsonl --global-seed $1 --vis 0 --allow-g19-mismatch 1 --save-dir $OUT/save ${*:3} > $OUT/stdout.txt 2>&1"
echo "exit $?"
