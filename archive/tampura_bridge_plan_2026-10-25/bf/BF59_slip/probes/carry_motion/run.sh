#!/bin/bash
# usage: run.sh <out name> <probe args...>   (physics only, no lock needed)
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels
P=$S/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/carry_motion
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=/root/tampura-work
export PYTHONPATH=$S:$S/tools:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:/root/tampura-work/tampura:/root/tampura-work/tampura_environments
name=$1; shift
cd /root/tampura-work/tampura_environments && timeout 900 /root/armO-venvA/bin/python $P/probe_carry_motion.py "$@" --out $P/out/$name.json 2>&1 | grep -v "^pybullet\|^argv\|^b3\|UserWarning\|_warnings.warn" | tail -8
