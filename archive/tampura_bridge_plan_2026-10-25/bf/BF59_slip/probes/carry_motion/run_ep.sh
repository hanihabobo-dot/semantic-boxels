#!/bin/bash
# usage: CM_FLIP=1 CM_TRAP=1 run_ep.sh <seed> <tag>   (one find_dice episode under the lock)
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels
TW=/root/tampura-work
P=$S/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/carry_motion
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW CM_FLIP CM_TRAP
export PYTHONPATH=$S:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:$TW/tampura:$TW/tampura_environments
PY=/root/armO-venvA/bin/python
OUT=$P/episodes/$2
mkdir -p $OUT
cd $TW/tampura_environments
flock /root/sb_pipeline.lock -c "timeout 600 $PY $P/episode_fix.py $OUT/carry.jsonl --global-seed $1 --vis 0 --allow-g19-mismatch 1 --save-dir $OUT/save > $OUT/stdout.txt 2>&1"
echo "exit $?"
