#!/bin/bash
# usage: py.sh <script in this folder> <args>: runs it in their tampura_environments cwd with arm O's venv
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels
TW=/root/tampura-work
H=$S/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/hold_physics
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW SB_REPO=$S
export PYTHONPATH=$S:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:$TW/tampura:$TW/tampura_environments:$S/tools
cd $TW/tampura_environments
s=$1; shift
exec /root/armO-venvA/bin/python $H/$s "$@" 2>&1 | grep -v "^b3Printf\|argv\|pybullet build"
