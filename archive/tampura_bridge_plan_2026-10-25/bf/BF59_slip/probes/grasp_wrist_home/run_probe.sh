#!/bin/bash
# BF#59 grasp_wrist_home: the joint-7 formula against the kin stream's IK
# (kinematics only, no planner: no lock needed).
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-grasp_wrist_home
TW=/root/tampura-work
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
export PYTHONPATH=$S:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:$TW/tampura:$TW/tampura_environments
PY=/root/armO-venvA/bin/python
D=$S/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/grasp_wrist_home
cd $TW/tampura_environments && $PY $D/probe_wrist_formula.py $D/formula.json 2>&1 | grep -v '^b3Printf\|^argv\|^startThreads\|^Version\|^Vendor\|^Renderer' | tail -20
