#!/bin/bash
# usage: run.sh <args of hp_probe.py>
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels
TW=/root/tampura-work
H=$S/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/hold_physics
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW SB_REPO=$S
export PYTHONPATH=$S:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:$TW/tampura:$TW/tampura_environments:$S/tools
cd $TW/tampura_environments
exec /root/armO-venvA/bin/python $H/hp_probe.py "$@" 2>&1 | grep -v "^b3Printf\|argv\|pybullet build"
