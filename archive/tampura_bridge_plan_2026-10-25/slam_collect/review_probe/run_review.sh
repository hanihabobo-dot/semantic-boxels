#!/bin/bash
# Reviewer's runner (copy of ../probe/run.sh with this folder as HERE).
# Runs a script from review_probe/ with cwd /root/sc_probe (the author's env_configs symlink),
# their venv, their two packages on PYTHONPATH, no bytecode. Outputs go to review_probe/out;
# the env's save folders are new /root/sc_probe/run_review_* folders. Nothing under /root/tampura-work.
HERE=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/slam_collect/review_probe
[ -e /root/sc_probe/env_configs ] || { echo "no /root/sc_probe/env_configs"; exit 1; }
cd /root/sc_probe || exit 1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/root/tampura-work/tampura:/root/tampura-work/tampura_environments
export MPLBACKEND=Agg
export PATH=/root/tampura-work/.venv/bin:$PATH
export VIRTUAL_ENV=/root/tampura-work/.venv
script=$1; shift
/root/tampura-work/.venv/bin/python -B "$HERE/$script" "$@"
