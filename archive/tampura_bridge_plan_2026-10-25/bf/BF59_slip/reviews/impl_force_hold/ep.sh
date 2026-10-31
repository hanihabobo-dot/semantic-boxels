#!/bin/bash
# BF#59 force_hold implementation check: one laptop episode of the
# slip/force_hold worktree with 200 iterations (ep_iters.py) and
# --slip-fixes solver_iters,force_hold, under the pipeline lock.
#   bash ep.sh <seed> <tag>
set -u
SEED=${1:?seed}
TAG=${2:?tag}
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-force_hold
HERE=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/reviews/impl_force_hold
TW=/root/tampura-work
export S PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
export PYTHONPATH=$S:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:$TW/tampura:$TW/tampura_environments
PY=/root/armO-venvA/bin/python
OUT=$HERE/runs/$TAG
mkdir -p $OUT
cd $TW/tampura_environments
T0=$(date +%s)
flock /root/sb_pipeline.lock timeout 900 $PY $HERE/ep_iters.py --global-seed $SEED --vis 0 \
  --allow-g19-mismatch 1 --slip-fixes solver_iters,force_hold --save-dir $OUT/save > $OUT/stdout.txt 2>&1
echo "rc $? after $(( $(date +%s) - T0 )) s: $(grep -o 'outcome [a-z_]*' $OUT/stdout.txt | tail -1)"
grep -c 'firm grip on dice' $OUT/stdout.txt | sed 's/^/die carries /'
