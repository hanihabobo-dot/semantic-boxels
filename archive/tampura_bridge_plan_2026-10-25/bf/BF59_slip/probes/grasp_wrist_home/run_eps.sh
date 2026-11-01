#!/bin/bash
# BF#59 grasp_wrist_home: one laptop episode each of seeds 1 and 6 with the
# switch on (IMPL_BRIEF section 3: seeds where the base lost the die), under
# the pipeline lock, outputs under episodes/s<seed>/.
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-grasp_wrist_home
TW=/root/tampura-work
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
export PYTHONPATH=$S:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:$TW/tampura:$TW/tampura_environments
PY=/root/armO-venvA/bin/python
D=$S/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/grasp_wrist_home/episodes
cd $TW/tampura_environments
for SEED in "$@"; do
  O=$D/s$SEED
  mkdir -p $O
  T0=$(date +%s)
  flock /root/sb_pipeline.lock timeout 900 $PY $S/tampura_bridge/run_bridge_on_finddice.py --global-seed $SEED --vis 0 \
    --allow-g19-mismatch 1 --slip-fixes grasp_wrist_home --save-dir $O/ep > $O/stdout.txt 2>&1
  echo "seed $SEED rc $? after $(( $(date +%s) - T0 )) s (lock wait included): $(grep -o 'outcome [a-z_]*' $O/stdout.txt | tail -1)"
  echo "  die carries $(grep -c 'firm grip on dice' $O/stdout.txt), lift losses $(grep -c 'grip lost after post-pick lift for dice' $O/stdout.txt), goal losses $(grep -c 'PHYSICAL_FAILURE (goal): (holding dice)' $O/stdout.txt), picks tried $(grep -c 'Picking dice' $O/stdout.txt)"
  echo "  refusals 'pose is too uncertain': $(grep -c 'pose is too uncertain' $O/stdout.txt)"
  L=$(ls $O/ep/ours/run_*/run_*.log 2>/dev/null | head -1)
  [ -n "$L" ] && echo "  grasp_wrist_home lines $(grep -c 'grasp_wrist_home:' $L), twin $(grep -c 'grasp_wrist_home: .*: twin' $L)"
  $PY $S/tools/episode_metrics.py $O/ep 2>&1 | grep -E '^(wall_s|plan_calls|planning_s|exec_s|steps|picks|outcome) ' | sed 's/^/  /'
done
