#!/bin/bash
# usage: [HP_GEAR=1] ep.sh <seed> <tag> <hold N> <iterations> [driver flags...]  (one find_dice episode under the lock)
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels
TW=/root/tampura-work
H=$S/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/hold_physics
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
export PYTHONPATH=$S:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:$TW/tampura:$TW/tampura_environments
PY=/root/armO-venvA/bin/python
OUT=$H/runs/$2
mkdir -p $OUT
cd $TW/tampura_environments
flock /root/sb_pipeline.lock -c "timeout 600 $PY $H/ep_probe.py $OUT/carry.jsonl $3 $4 --global-seed $1 --vis 0 --allow-g19-mismatch 1 --save-dir $OUT/save ${*:5} > $OUT/stdout.txt 2>&1"
echo "exit $?"
