# Usage: bash run.sh <script.py> <args...>   (runs a HERE script with cwd /root/task_shots)
HERE=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/class_uncertain/tasks_page
cd /root/task_shots
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/root/tampura-work/tampura:/root/tampura-work/tampura_environments
export MPLBACKEND=Agg
script=$1; shift
/root/tampura-work/.venv/bin/python -B "$HERE/$script" "$@"
