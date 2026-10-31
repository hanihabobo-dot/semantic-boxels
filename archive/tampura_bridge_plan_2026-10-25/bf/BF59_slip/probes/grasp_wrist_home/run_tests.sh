#!/bin/bash
# BF#59 grasp_wrist_home: the unit tests of this worktree (no planner runs
# in test_slip_grasp_wrist_home.py; the full suite goes through the lock in
# tools/slip_check.sh).
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-grasp_wrist_home
TW=/root/tampura-work
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
export PYTHONPATH=$S:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:$TW/tampura:$TW/tampura_environments
cd $S && /root/armO-venvA/bin/python -m pytest -q -p no:cacheprovider "$@" 2>&1 | tail -30
