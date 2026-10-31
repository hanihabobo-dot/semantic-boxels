#!/bin/bash
# BF#59 force_hold jam probe: run.sh <jam_probe.py args>  (physics only, no lock)
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-force_hold
TW=/root/tampura-work
H=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/force_hold
export S PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW SB_REPO=$S
export PYTHONPATH=$S:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:$TW/tampura:$TW/tampura_environments:$S/tools
cd $TW/tampura_environments
/root/armO-venvA/bin/python $H/jam_probe.py "$@" 2>&1 | grep -v "^b3Printf\|argv\|pybullet build"
