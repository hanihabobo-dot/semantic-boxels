#!/bin/bash
# Review probes (REVIEW.md). Same run line as the author's probes: their venv,
# PYTHONPATH to their two trees, no bytecode, cwd /root/ps_probe (which holds
# only the author's env_configs symlink; nothing is written there).
# Every output goes to this review_probe folder.
set -u
RP=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/puck_slide/review_probe
PS=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/puck_slide
PY=/root/tampura-work/.venv/bin/python
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/root/tampura-work/tampura:/root/tampura-work/tampura_environments
cd /root/ps_probe || exit 1
echo "== probe_analysis.py rerun on the author's JSON"
$PY -B $PS/probe_analysis.py $PS/probe_puck_physics_out.json > $RP/probe_analysis_rerun_out.txt 2>&1
echo "rc=$?"
echo "== probe_puck_physics2.py rerun (reproducibility)"
$PY -B $PS/probe_puck_physics2.py $RP/probe_puck_physics2_rerun_out.json > $RP/probe_puck_physics2_rerun_log.txt 2>&1
echo "rc=$?"
echo "== rp_damping.py"
$PY -B $RP/rp_damping.py $RP/rp_damping_out.json > $RP/rp_damping_log.txt 2>&1
echo "rc=$?"
echo "== rp_launch.py"
$PY -B $RP/rp_launch.py $RP/rp_launch_out.json > $RP/rp_launch_log.txt 2>&1
echo "rc=$?"
ls -la /root/ps_probe
