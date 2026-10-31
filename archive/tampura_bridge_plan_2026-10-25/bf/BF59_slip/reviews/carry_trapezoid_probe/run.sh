#!/bin/bash
# BF#59 carry_trapezoid real-pick check (physics only, no planner, no lock):
# the carry_motion review's flip cell (hand yaw 180, grasp_geometry's
# real-pick probe) under today's per-pair carry and under the branch's
# trapezoid stream, the same 64 trial configurations each.
#   bash run.sh [hand yaw deg, default 180]   (outputs beside this script)
set -u
D=$(cd $(dirname $0) && pwd)
REPO=/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-carry_trapezoid
LIB=/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib
TW=/root/tampura-work
PY=/root/armO-venvA/bin/python
export PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 TAMPURA_WORK=$TW
export PYTHONPATH=$REPO:$REPO/tools:$LIB:$TW/tampura:.
cd $TW/tampura_environments
HY=${1:-180}
ARGS="--hand-yaw-deg=$HY --cells 8 --deltas 0,3,6,10 --k90 0,1 --aperture-sized 1"
for M in pipeline trapezoid; do
  ( T0=$(date +%s); $PY $D/probe_trap_realpick.py --out $D/hy${HY}_$M.json $ARGS --carry-mode $M \
      > $D/hy${HY}_$M.log 2>&1; echo "$M rc $? after $(( $(date +%s) - T0 )) s" >> $D/hy${HY}_$M.log ) &
done
wait
tail -n 2 $D/hy${HY}_pipeline.log $D/hy${HY}_trapezoid.log
