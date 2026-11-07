#!/bin/bash
# Usage: bash run.sh <script.py> <args...>
# Runs a script from this folder with cwd /root/sc_probe (env_configs symlinked to
# their read-only tree), their venv, their two packages on PYTHONPATH, no bytecode.
# Nothing is written under /root/tampura-work.
HERE=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/slam_collect/probe
mkdir -p /root/sc_probe
[ -e /root/sc_probe/env_configs ] || ln -s /root/tampura-work/tampura_environments/env_configs /root/sc_probe/env_configs
cd /root/sc_probe || exit 1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/root/tampura-work/tampura:/root/tampura-work/tampura_environments
export MPLBACKEND=Agg
# SymK's translate and search shell out to a bare 'python' (as tools/tampura_sweep_cluster.py:159-164 notes)
export PATH=/root/tampura-work/.venv/bin:$PATH
export VIRTUAL_ENV=/root/tampura-work/.venv
script=$1; shift
/root/tampura-work/.venv/bin/python -B "$HERE/$script" "$@"
